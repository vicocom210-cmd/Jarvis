package uz.jarvis

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.IBinder
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import kotlin.math.abs

// Ilovalar ustida suzuvchi shar (overlay). "Jarvis" desangiz yoki sharni bossangiz —
// Jarvis ilovasi ochilib, sizni tinglaydi.
class OverlayService : Service() {

    private lateinit var wm: WindowManager
    private var shar: SharView? = null
    private var sr: SpeechRecognizer? = null
    private var tinglayapti = false
    private var panelOchiq = false
    private lateinit var joy: WindowManager.LayoutParams

    override fun onBind(i: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        oldindanEshkart()
        wm = getSystemService(WINDOW_SERVICE) as WindowManager
        sharYarat()
        wakeBoshla()
    }

    override fun onStartCommand(i: Intent?, f: Int, id: Int): Int {
        if (i?.action == "panel_yopildi") {
            // Panel yopildi -> yana "Jarvis"ni fonda tinglaymiz
            panelOchiq = false
            shar?.holat("kutish")
            qaytaTingla()
        }
        return START_STICKY
    }

    // ----- suzuvchi shar -----
    private fun sharYarat() {
        val v = SharView(this)
        v.holat("kutish")
        val olcham = (resources.displayMetrics.density * 72).toInt()
        val tur = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        else @Suppress("DEPRECATION") WindowManager.LayoutParams.TYPE_PHONE
        joy = WindowManager.LayoutParams(olcham, olcham, tur,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            android.graphics.PixelFormat.TRANSLUCENT).apply {
            gravity = Gravity.TOP or Gravity.START
            x = resources.displayMetrics.widthPixels - olcham - 20
            y = resources.displayMetrics.heightPixels / 3
        }
        v.setOnTouchListener(object : View.OnTouchListener {
            var bx = 0; var by = 0; var tx = 0f; var ty = 0f; var surildi = false
            override fun onTouch(vv: View, e: MotionEvent): Boolean {
                when (e.action) {
                    MotionEvent.ACTION_DOWN -> {
                        bx = joy.x; by = joy.y; tx = e.rawX; ty = e.rawY; surildi = false
                    }
                    MotionEvent.ACTION_MOVE -> {
                        val dx = (e.rawX - tx).toInt(); val dy = (e.rawY - ty).toInt()
                        if (abs(dx) + abs(dy) > 15) surildi = true
                        joy.x = bx + dx; joy.y = by + dy
                        wm.updateViewLayout(vv, joy)
                    }
                    MotionEvent.ACTION_UP -> if (!surildi) panelniOch(null)
                }
                return true
            }
        })
        shar = v
        try { wm.addView(v, joy) } catch (e: Exception) { stopSelf() }
    }

    // ----- "Jarvis" ni fonda tinglash -----
    private fun wakeBoshla() {
        if (!SpeechRecognizer.isRecognitionAvailable(this)) return
        sr = SpeechRecognizer.createSpeechRecognizer(this)
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "uz-UZ")
        }
        sr?.setRecognitionListener(object : android.speech.RecognitionListener {
            override fun onResults(b: Bundle?) {
                val matn = b?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    ?.firstOrNull()?.lowercase() ?: ""
                if (Regex("jarvis|jarbi|djarvis|жарвис|garvis|charvis").containsMatchIn(matn)) {
                    val buyruq = matn.substringAfter("jarvis", "").trim()
                    shar?.holat("tinglash")
                    panelniOch(buyruq.ifBlank { null })
                } else qaytaTingla()
            }
            override fun onError(e: Int) { qaytaTingla() }
            override fun onReadyForSpeech(p: Bundle?) {}
            override fun onBeginningOfSpeech() {}
            // ovoz balandligiga qarab shar jonli qimirlaydi (Bixby'dek)
            override fun onRmsChanged(v: Float) { shar?.pulse(((v + 2f) / 12f)) }
            override fun onBufferReceived(x: ByteArray?) {}
            override fun onEndOfSpeech() {}
            override fun onPartialResults(p: Bundle?) {}
            override fun onEvent(t: Int, p: Bundle?) {}
        })
        beepOchir(true)
        try { sr?.startListening(intent); tinglayapti = true } catch (e: Exception) {}
    }

    // Beep ("biq") tovushini o'chiradi. Holatni kuzatamiz — ketma-ket MUTE chaqirilib
    // ovoz butunlay o'chib qolmasligi uchun (faqat o'zgarishda toglaydi).
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

    private fun tinglaBoshla() {
        try {
            val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                putExtra(RecognizerIntent.EXTRA_LANGUAGE, "uz-UZ")
            }
            sr?.startListening(intent)
        } catch (e: Exception) {}
    }

    private fun qaytaTingla() {
        if (panelOchiq) return                 // panel ochiq ekan, fon tinglashi to'xtaydi
        beepOchir(true)
        shar?.postDelayed({ if (!panelOchiq) tinglaBoshla() }, 700)
    }

    // Bixby'dek suzuvchi panelni ochamiz (boshqa ilova ustida shaffof oyna).
    // Fon tinglashini to'xtatib, ovozni yoqamiz (panel o'zbekcha gapiradi).
    private fun panelniOch(buyruq: String?) {
        panelOchiq = true
        try { sr?.cancel() } catch (e: Exception) {}
        beepOchir(false)                       // panel ovoz chiqarishi uchun jimlikni yechamiz
        val i = Intent(this, PanelActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            putExtra("uygon", true)
            if (buyruq != null) putExtra("buyruq", buyruq)
        }
        try { startActivity(i) } catch (e: Exception) { panelOchiq = false; qaytaTingla() }
    }

    // ----- fon xizmati bildirishnomasi -----
    private fun oldindanEshkart() {
        val kanal = "jarvis_overlay"
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(NotificationChannel(kanal, "Jarvis",
                NotificationManager.IMPORTANCE_LOW))
        }
        val ochish = PendingIntent.getActivity(this, 0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        val esk: Notification = Notification.Builder(this, kanal)
            .setContentTitle("Jarvis faol")
            .setContentText("\"Jarvis\" deb chaqiring yoki sharni bosing")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentIntent(ochish)
            .build()
        startForeground(7, esk)
    }

    override fun onDestroy() {
        try { shar?.let { wm.removeView(it) } } catch (e: Exception) {}
        beepOchir(false)
        sr?.destroy()
        super.onDestroy()
    }
}
