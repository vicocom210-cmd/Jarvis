package uz.jarvis

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer

// Ko'rinmas fon xizmati: ekranga hech narsa chizmaydi (suzuvchi shar YO'Q).
// Faqat fonda jimgina "Jarvis" so'zini kutadi. "Jarvis" eshitilganda —
// pastdan Bixby'dek panel (PanelActivity) chiqib, buyruqni eshitib, yo'qoladi.
class OverlayService : Service() {

    private var sr: SpeechRecognizer? = null
    private var panelOchiq = false
    private val ish = Handler(Looper.getMainLooper())

    override fun onBind(i: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        oldindanEshkart()
        wakeBoshla()
    }

    override fun onStartCommand(i: Intent?, f: Int, id: Int): Int {
        if (i?.action == "panel_yopildi") {
            panelOchiq = false
            qaytaTingla()
        }
        return START_STICKY
    }

    // ----- "Jarvis" ni fonda tinglash -----
    private fun wakeIntent() = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
        putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
        putExtra(RecognizerIntent.EXTRA_LANGUAGE, "uz-UZ")
        putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true)     // "Jarvis"ni tezroq ilg'aymiz
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M)
            putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, true)  // internetsiz — ba'zi telefonda jimroq
    }

    private fun wakeBoshla() {
        if (!SpeechRecognizer.isRecognitionAvailable(this)) return
        sr = SpeechRecognizer.createSpeechRecognizer(this)
        sr?.setRecognitionListener(object : android.speech.RecognitionListener {
            override fun onResults(b: Bundle?) {
                val matn = b?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    ?.firstOrNull()?.lowercase() ?: ""
                if (jarvismi(matn)) panelniOch(matn.substringAfter("jarvis", "").trim().ifBlank { null })
                else qaytaTingla()
            }
            override fun onPartialResults(p: Bundle?) {
                val matn = p?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    ?.firstOrNull()?.lowercase() ?: ""
                if (jarvismi(matn)) {                 // gap tugashini kutmasdan darhol ochamiz
                    try { sr?.cancel() } catch (e: Exception) {}
                    panelniOch(matn.substringAfter("jarvis", "").trim().ifBlank { null })
                }
            }
            override fun onError(e: Int) { qaytaTingla() }
            override fun onReadyForSpeech(p: Bundle?) {}
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(v: Float) {}
            override fun onBufferReceived(x: ByteArray?) {}
            override fun onEndOfSpeech() {}
            override fun onEvent(t: Int, p: Bundle?) {}
        })
        beepOchir(true)
        try { sr?.startListening(wakeIntent()) } catch (e: Exception) {}
    }

    private fun jarvismi(s: String) =
        Regex("jarvis|jarbi|djarvis|jarvi|жарвис|джарвис|garvis|charvis").containsMatchIn(s)

    // Beep ("biq/klik") tovushini o'chiradi. Holatni kuzatamiz — ketma-ket MUTE
    // chaqirilib ovoz butunlay o'chib qolmasligi uchun (faqat o'zgarishda toglaydi).
    private val am by lazy { getSystemService(AUDIO_SERVICE) as android.media.AudioManager }
    private var jim = false
    private fun beepOchir(ochir: Boolean) {
        if (ochir == jim) return
        jim = ochir
        try {
            val oqimlar = intArrayOf(android.media.AudioManager.STREAM_MUSIC,
                android.media.AudioManager.STREAM_NOTIFICATION,
                android.media.AudioManager.STREAM_SYSTEM,
                android.media.AudioManager.STREAM_RING,
                android.media.AudioManager.STREAM_ALARM)
            for (o in oqimlar) am.adjustStreamVolume(o,
                if (ochir) android.media.AudioManager.ADJUST_MUTE
                else android.media.AudioManager.ADJUST_UNMUTE, 0)
        } catch (e: Exception) {}
    }

    private fun qaytaTingla() {
        if (panelOchiq) return                 // panel ochiq ekan, fon tinglashi to'xtaydi
        beepOchir(true)
        ish.postDelayed({ if (!panelOchiq) { try { sr?.startListening(wakeIntent()) } catch (e: Exception) {} } }, 600)
    }

    // Bixby'dek panelni ochamiz (boshqa ilova ustida shaffof oyna, pastdan chiqadi).
    // Fon tinglashini to'xtatib, ovozni yoqamiz (panel o'zbekcha gapiradi).
    private fun panelniOch(buyruq: String?) {
        if (panelOchiq) return
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
            .setContentTitle("Jarvis tinglayapti")
            .setContentText("\"Jarvis\" deb chaqiring — panel o'zi chiqadi")
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentIntent(ochish)
            .build()
        startForeground(7, esk)
    }

    override fun onDestroy() {
        beepOchir(false)
        try { sr?.destroy() } catch (e: Exception) {}
        super.onDestroy()
    }
}
