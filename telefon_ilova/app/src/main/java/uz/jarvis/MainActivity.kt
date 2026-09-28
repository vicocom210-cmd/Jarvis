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
// PanelActivity shu klassdan meros oladi (Bixby'dek suzuvchi panel).
open class MainActivity : android.app.Activity() {

    protected lateinit var web: WebView
    private var tts: TextToSpeech? = null
    private var sr: SpeechRecognizer? = null
    private val asosiy = Handler(Looper.getMainLooper())

    // Panel (shaffof) rejimida bular boshqacha bo'ladi
    protected open fun sahifaManzili() = "file:///android_asset/index.html"
    protected open val shaffof = false

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(saved: Bundle?) {
        super.onCreate(saved)
        web = WebView(this)
        setContentView(web)
        if (shaffof) web.setBackgroundColor(0x00000000)   // panel — orqadagi ilova ko'rinsin
        web.settings.javaScriptEnabled = true
        web.settings.domStorageEnabled = true
        web.settings.mediaPlaybackRequiresUserGesture = false
        web.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest) {
                request.grant(request.resources)
            }
        }
        web.addJavascriptInterface(Kopruk(), "Android")
        web.loadUrl(sahifaManzili())

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
        // Fonda o'zi tinglaydigan eski xizmatni to'xtatamiz — endi faqat tugma bosilganda tinglaydi
        if (!shaffof) {
            try { stopService(Intent(this, OverlayService::class.java)) } catch (e: Exception) {}
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

        // Panel rejimida — javob berib bo'lgach oynani yopadi (orqadagi ilovaga qaytadi)
        @JavascriptInterface
        fun panelYop() {
            asosiy.post { finish() }
        }

        // Boshqa ilovani ochish (masalan, Hik-Connect). O'rnatilmagan bo'lsa — Play Market'da qidiradi
        @JavascriptInterface
        fun ilovaOch(paketlar: String, qidiruv: String) {
            asosiy.post {
                for (p in paketlar.split(",").map { it.trim() }.filter { it.isNotEmpty() }) {
                    val i = packageManager.getLaunchIntentForPackage(p)
                    if (i != null) { startActivity(i); return@post }
                }
                try {
                    startActivity(Intent(Intent.ACTION_VIEW, Uri.parse("market://search?q=" + Uri.encode(qidiruv))))
                } catch (e: Exception) {
                    startActivity(Intent(Intent.ACTION_VIEW,
                        Uri.parse("https://play.google.com/store/search?q=" + Uri.encode(qidiruv))))
                }
            }
        }

        // Uydan tashqarida: bulut xabarlarini AES-256-GCM bilan shifrlash (kalit uy Wi-Fi'da olinadi)
        @JavascriptInterface
        fun shifrla(kalitHex: String, matn: String): String = try { Shifr.shifrla(kalitHex, matn) } catch (e: Exception) { "" }

        @JavascriptInterface
        fun ochish(kalitHex: String, b64: String): String = try { Shifr.ochish(kalitHex, b64) } catch (e: Exception) { "" }

        // Kompyutersiz: kameradan to'g'ridan-to'g'ri rasm (uy Wi-Fi). Natija window.kameraJavob(id, json) ga
        @JavascriptInterface
        fun kameraRasm(id: Int, ip: String, port: Int, login: String, parol: String, kanal: String) {
            Thread {
                val json = Kamera.rasm(ip, if (port > 0) port else 80, login.ifBlank { "admin" }, parol, kanal)
                asosiy.post { web.evaluateJavascript("window.kameraJavob && window.kameraJavob($id, $json)", null) }
            }.start()
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

    // SpeechRecognizer'ning "biq" tovushini vaqtincha o'chiradi.
    // Holatni kuzatamiz: ketma-ket MUTE chaqirilib ovoz butunlay o'chib qolmasin.
    private val am by lazy { getSystemService(AUDIO_SERVICE) as android.media.AudioManager }
    private var jim = false
    private fun beepOchir(ochir: Boolean) {
        if (ochir == jim) return
        jim = ochir
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
        beepOchir(false)     // chiqishda ovozni albatta tiklaymiz
        tts?.shutdown()
        sr?.destroy()
        super.onDestroy()
    }
}
