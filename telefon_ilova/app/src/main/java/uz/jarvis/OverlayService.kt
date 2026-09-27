package uz.jarvis

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.Build
import android.os.Bundle
import android.os.IBinder
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.view.Gravity
import android.view.MotionEvent
import android.view.View
import android.view.WindowManager
import android.widget.TextView
import kotlin.math.abs

// Ilovalar ustida suzuvchi shar (overlay). "Jarvis" desangiz yoki sharni bossangiz —
// Jarvis ilovasi ochilib, sizni tinglaydi.
class OverlayService : Service() {

    private lateinit var wm: WindowManager
    private var shar: TextView? = null
    private var sr: SpeechRecognizer? = null
    private var tinglayapti = false
    private lateinit var joy: WindowManager.LayoutParams

    override fun onBind(i: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        oldindanEshkart()
        wm = getSystemService(WINDOW_SERVICE) as WindowManager
        sharYarat()
        wakeBoshla()
    }

    override fun onStartCommand(i: Intent?, f: Int, id: Int): Int = START_STICKY

    // ----- suzuvchi shar -----
    private fun sharYarat() {
        val v = TextView(this).apply {
            text = "J"
            setTextColor(Color.WHITE)
            textSize = 22f
            gravity = Gravity.CENTER
            val fon = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                colors = intArrayOf(Color.parseColor("#4bd0ff"), Color.parseColor("#8a6bff"))
                gradientType = GradientDrawable.LINEAR_GRADIENT
            }
            background = fon
        }
        val olcham = (resources.displayMetrics.density * 58).toInt()
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
                    MotionEvent.ACTION_UP -> if (!surildi) ilovaniOch(null)
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
                    ilovaniOch(buyruq.ifBlank { null })
                } else qaytaTingla()
            }
            override fun onError(e: Int) { qaytaTingla() }
            override fun onReadyForSpeech(p: Bundle?) {}
            override fun onBeginningOfSpeech() {}
            override fun onRmsChanged(v: Float) {}
            override fun onBufferReceived(x: ByteArray?) {}
            override fun onEndOfSpeech() {}
            override fun onPartialResults(p: Bundle?) {}
            override fun onEvent(t: Int, p: Bundle?) {}
        })
        try { sr?.startListening(intent); tinglayapti = true } catch (e: Exception) {}
    }

    private fun qaytaTingla() {
        shar?.postDelayed({
            try {
                val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE, "uz-UZ")
                }
                sr?.startListening(intent)
            } catch (e: Exception) {}
        }, 800)
    }

    private fun ilovaniOch(buyruq: String?) {
        val i = Intent(this, MainActivity::class.java).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            putExtra("uygon", true)
            if (buyruq != null) putExtra("buyruq", buyruq)
        }
        startActivity(i)
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
        sr?.destroy()
        super.onDestroy()
    }
}
