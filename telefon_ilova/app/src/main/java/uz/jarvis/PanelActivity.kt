package uz.jarvis

import android.content.Intent
import android.os.Bundle
import android.view.WindowManager

// Bixby'dek suzuvchi panel: boshqa ilova ustida shaffof oyna sifatida ochiladi
// (orqa fon xiralashadi). MainActivity mantig'ini to'liq qayta ishlatadi —
// faqat sahifa "panel" rejimida yuklanadi va shaffof ko'rinadi.
class PanelActivity : MainActivity() {

    override fun sahifaManzili() = "file:///android_asset/index.html?panel=1"
    override val shaffof = true

    override fun onCreate(saved: Bundle?) {
        super.onCreate(saved)
        // Panel pastda tursin va tashqarisiga tegilsa yopilsin
        window.setGravity(android.view.Gravity.BOTTOM)
        setFinishOnTouchOutside(true)
    }

    override fun onDestroy() {
        // Panel yopildi -> suzuvchi shar yana "Jarvis"ni tinglashni davom ettirsin
        try {
            startService(Intent(this, OverlayService::class.java).setAction("panel_yopildi"))
        } catch (e: Exception) {}
        super.onDestroy()
    }
}
