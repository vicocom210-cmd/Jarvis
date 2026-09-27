package uz.jarvis

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.os.Handler
import android.os.Looper
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.PermissionRequest
import java.util.Locale

// Jarvis telefon ilovasi: ko'rinish va mantiq assets/index.html ichida (HTML/JS).
// Bu Kotlin qismi faqat mikrofon (ovozni matnga) va ovoz chiqarish (matnni ovozga) ni ulaydi.
class MainActivity : android.app.Activity() {

    private lateinit var web: WebView
    private var tts: TextToSpeech? = null
    private var sr: SpeechRecognizer? = null
    private val asosiy = Handler(Looper.getMainLooper())

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(saved: Bundle?) {
        super.onCreate(saved)
        web = WebView(this)
        setContentView(web)
        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        web.settings.mediaPlaybackRequiresUserGesture = false
        web.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest) {
                request.grant(request.resources)
            }
        }
        web.addJavascriptInterface(Kopruk(), "Android")
        web.loadUrl("file:///android_asset/index.html")

        // Avval o'zbek; bo'lmasa turk (lotin yozuvga eng yaqin), keyin rus, keyin standart
        fun tilTanla() {
            val m = tts ?: return
            for (til in listOf(Locale("uz", "UZ"), Locale("uz"), Locale("tr", "TR"),
                    Locale("tr"), Locale("ru"), Locale.getDefault())) {
                if (m.isLanguageAvailable(til) >= TextToSpeech.LANG_AVAILABLE) {
                    m.language = til
                    break
                }
            }
        }
        // Google TTS'da o'zbek ovozi bor — avval uni sinaymiz, bo'lmasa standartga o'tamiz
        tts = TextToSpeech(this, { holat ->
            if (holat == TextToSpeech.SUCCESS) tilTanla()
            else {
                tts?.shutdown()
                tts = TextToSpeech(this) { h -> if (h == TextToSpeech.SUCCESS) tilTanla() }
            }
        }, "com.google.android.tts")

        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 1)
        }
        uygonTekshir(intent)
    }

    override fun onNewIntent(i: Intent?) {
        super.onNewIntent(i)
        setIntent(i)
        uygonTekshir(i)
    }

    // Suzuvchi shardan "uygon" bilan ochilsa — darhol tinglashni boshlaymiz
    private fun uygonTekshir(i: Intent?) {
        if (i?.getBooleanExtra("uygon", false) == true) {
            val buyruq = i.getStringExtra("buyruq")
            asosiy.postDelayed({
                if (buyruq.isNullOrBlank()) web.evaluateJavascript("window.uygon && window.uygon()", null)
                else {
                    val x = buyruq.replace("\\", "\\\\").replace("'", "\\'")
                    web.evaluateJavascript("window.uygonBuyruq && window.uygonBuyruq('$x')", null)
                }
            }, 900)
        }
    }

    // JS -> Kotlin ko'prigi
    inner class Kopruk {
        @JavascriptInterface
        fun gapir(matn: String) {
            asosiy.post { tts?.speak(matn, TextToSpeech.QUEUE_FLUSH, null, "jarvis") }
        }

        @JavascriptInterface
        fun toxtat() {
            asosiy.post { tts?.stop() }
        }

        @JavascriptInterface
        fun tingla() {
            asosiy.post { boshlaTinglash() }
        }

        @JavascriptInterface
        fun suzuvchiYoq() {
            asosiy.post {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M && !Settings.canDrawOverlays(this@MainActivity)) {
                    // "Boshqa ilovalar ustida ko'rsatish" ruxsatini so'raymiz
                    startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        Uri.parse("package:$packageName")))
                } else {
                    startForegroundService(Intent(this@MainActivity, OverlayService::class.java))
                }
            }
        }

        @JavascriptInterface
        fun suzuvchiOchir() {
            asosiy.post { stopService(Intent(this@MainActivity, OverlayService::class.java)) }
        }
    }

    private fun boshlaTinglash() {
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), 1)
            return
        }
        sr?.destroy()
        sr = SpeechRecognizer.createSpeechRecognizer(this)
        val intent = android.content.Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "uz-UZ")
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
        }
        sr?.setRecognitionListener(object : android.speech.RecognitionListener {
            override fun onReadyForSpeech(p: Bundle?) { jsChaqir("tinglashBoshlandi") }
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(v: Float) {}
            override fun onBufferReceived(b: ByteArray?) {}
            override fun onEndOfSpeech() { beepOchir(false) }
            override fun onError(xato: Int) { beepOchir(false); jsChaqir("tinglashTugadi") }
            override fun onResults(natijalar: Bundle?) {
                beepOchir(false)
                val ro = natijalar?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                val matn = ro?.firstOrNull() ?: ""
                jsNatija(matn)
            }
            override fun onPartialResults(p: Bundle?) {}
            override fun onEvent(t: Int, p: Bundle?) {}
        })
        beepOchir(true)                    // tinglash "biq" tovushini o'chiramiz
        sr?.startListening(intent)
    }

    // SpeechRecognizer'ning "biq" tovushini vaqtincha o'chiradi (musiqa oqimi)
    private val am by lazy { getSystemService(AUDIO_SERVICE) as android.media.AudioManager }
    private fun beepOchir(ochir: Boolean) {
        try {
            val oqimlar = intArrayOf(android.media.AudioManager.STREAM_MUSIC,
                android.media.AudioManager.STREAM_NOTIFICATION,
                android.media.AudioManager.STREAM_SYSTEM)
            for (o in oqimlar) am.adjustStreamVolume(o,
                if (ochir) android.media.AudioManager.ADJUST_MUTE
                else android.media.AudioManager.ADJUST_UNMUTE, 0)
        } catch (e: Exception) {}
    }

    private fun jsNatija(matn: String) {
        val xavfsiz = matn.replace("\\", "\\\\").replace("'", "\\'")
        web.post { web.evaluateJavascript("window.natija && window.natija('$xavfsiz')", null) }
    }

    private fun jsChaqir(funksiya: String) {
        web.post { web.evaluateJavascript("window.$funksiya && window.$funksiya()", null) }
    }

    override fun onDestroy() {
        tts?.shutdown()
        sr?.destroy()
        super.onDestroy()
    }
}
