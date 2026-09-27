package uz.jarvis

import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RadialGradient
import android.graphics.Shader
import android.view.View
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt

// Jonli zarrachali shar (Bixby'dagidek): aylanadi, "nafas oladi", holatga qarab
// rangi/kattaligi o'zgaradi, gapirganda pulsatsiya qiladi.
class SharView(ctx: Context) : View(ctx) {

    private val n = 420
    private val px = FloatArray(n); private val py = FloatArray(n); private val pz = FloatArray(n)
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private val nurPaint = Paint(Paint.ANTI_ALIAS_FLAG)
    private var bur = 0f
    private var kat = 0.8f; private var mKat = 0.8f
    private var tez = 0.35f
    private var daraja = 0f; private var mDaraja = 0f
    private var r = floatArrayOf(75f, 208f, 255f)
    private var mR = floatArrayOf(75f, 208f, 255f)

    init {
        val oltin = Math.PI * (3 - sqrt(5.0))
        for (i in 0 until n) {
            val y = 1 - 2 * (i + 0.5) / n
            val rad = sqrt(1 - y * y)
            val a = oltin * i
            px[i] = (cos(a) * rad).toFloat(); py[i] = y.toFloat(); pz[i] = (sin(a) * rad).toFloat()
        }
    }

    // holat: "kutish","tinglash","oylash","gapirish"
    fun holat(h: String) {
        when (h) {
            "tinglash" -> { mKat = 1.0f; tez = 0.9f; mR = floatArrayOf(75f, 208f, 255f) }
            "oylash" -> { mKat = 0.92f; tez = 1.5f; mR = floatArrayOf(138f, 107f, 255f) }
            "gapirish" -> { mKat = 0.96f; tez = 0.6f; mR = floatArrayOf(90f, 215f, 255f) }
            else -> { mKat = 0.8f; tez = 0.35f; mR = floatArrayOf(40f, 120f, 230f) }
        }
    }

    // ovoz balandligi (0..1) — gapirganda tashqariga pulsatsiya
    fun pulse(v: Float) { mDaraja = v.coerceIn(0f, 1f) }

    private val loop = object : Runnable {
        override fun run() { bur += tez * 0.02f
            for (i in 0..2) r[i] += (mR[i] - r[i]) * 0.08f
            kat += (mKat - kat) * 0.08f
            daraja += (mDaraja - daraja) * 0.2f
            mDaraja *= 0.9f
            invalidate(); postDelayed(this, 33) }
    }
    override fun onAttachedToWindow() { super.onAttachedToWindow(); post(loop) }
    override fun onDetachedFromWindow() { super.onDetachedFromWindow(); removeCallbacks(loop) }

    override fun onDraw(c: Canvas) {
        val w = width.toFloat(); val h = height.toFloat()
        val cx = w / 2; val cy = h / 2
        val rad = (minOf(w, h) / 2 * 0.82f) * kat
        val ca = cos(bur.toDouble()); val sa = sin(bur.toDouble())
        val ce = cos(0.4); val se = sin(0.4)
        // ichki nur
        nurPaint.shader = RadialGradient(cx, cy, rad * 1.4f,
            Color.argb(90, r[0].toInt(), r[1].toInt(), r[2].toInt()), Color.TRANSPARENT,
            Shader.TileMode.CLAMP)
        c.drawCircle(cx, cy, rad * 1.4f, nurPaint)
        val nafas = 1 + 0.03 * sin(System.currentTimeMillis() / 500.0) + daraja * 0.18
        for (i in 0 until n) {
            val x2 = px[i] * ca + pz[i] * sa
            val z2 = pz[i] * ca - px[i] * sa
            val y2 = py[i] * ce - z2 * se
            val z3 = py[i] * se + z2 * ce
            val ch = ((z3 + 1.2) / 2.4).toFloat().coerceIn(0f, 1f)
            val X = (cx + x2 * rad * nafas).toFloat()
            val Y = (cy + y2 * rad * nafas).toFloat()
            paint.color = Color.argb((60 + ch * 195).toInt(), r[0].toInt(), r[1].toInt(), r[2].toInt())
            c.drawCircle(X, Y, if (ch < 0.55f) 2f else 3.2f, paint)
        }
    }
}
