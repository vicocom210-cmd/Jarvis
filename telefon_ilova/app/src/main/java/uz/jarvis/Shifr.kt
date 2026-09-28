package uz.jarvis

import android.util.Base64
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

// Uydan tashqarida kamera va eshik buyruqlari ochiq bulut serveridan o'tadi — shuning uchun
// AES-256-GCM bilan shifrlanadi. Format (kompyuterdagi bulut.py bilan bir xil):
// base64( 12 bayt nonce + shifrlangan matn + 16 bayt teg )
object Shifr {
    private fun kalit(hex: String): SecretKeySpec {
        val b = ByteArray(hex.length / 2) { i -> hex.substring(i * 2, i * 2 + 2).toInt(16).toByte() }
        require(b.size == 32) { "kalit 32 bayt bo'lishi kerak" }
        return SecretKeySpec(b, "AES")
    }

    fun shifrla(kalitHex: String, matn: String): String {
        val nonce = ByteArray(12).also { SecureRandom().nextBytes(it) }
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.ENCRYPT_MODE, kalit(kalitHex), GCMParameterSpec(128, nonce))
        return Base64.encodeToString(nonce + c.doFinal(matn.toByteArray(Charsets.UTF_8)), Base64.NO_WRAP)
    }

    fun ochish(kalitHex: String, b64: String): String {
        val xom = Base64.decode(b64, Base64.DEFAULT)
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.DECRYPT_MODE, kalit(kalitHex), GCMParameterSpec(128, xom, 0, 12))
        return String(c.doFinal(xom, 12, xom.size - 12), Charsets.UTF_8)
    }
}
