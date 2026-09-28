package uz.jarvis

import android.util.Base64
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.security.SecureRandom

// Kompyuter o'chiq bo'lsa ham telefon kameralarni ko'rsin: Hikvision ISAPI'ga to'g'ridan-to'g'ri
// (uy Wi-Fi ichida) ulanadi. Android'ning HttpURLConnection'i Digest kirishni bilmaydi —
// shuning uchun Digest (MD5 / SHA-256) imzosini o'zimiz hisoblaymiz. Parol bilan faqat BIR marta
// urinadi (kamera ko'p xato urinishda telefonni bloklab qo'ymasin).
object Kamera {

    class Javob(val kod: Int, val tana: ByteArray)

    private fun ulan(url: String, usul: String, auth: String?, tana: ByteArray?, soniya: Int): Pair<Javob, Map<String, List<String>>> {
        val c = URL(url).openConnection() as HttpURLConnection
        c.connectTimeout = soniya * 1000
        c.readTimeout = soniya * 1000
        c.requestMethod = usul
        c.instanceFollowRedirects = false
        if (auth != null) c.setRequestProperty("Authorization", auth)
        if (tana != null) {
            c.doOutput = true
            c.setRequestProperty("Content-Type", "application/xml")
            c.outputStream.use { it.write(tana) }
        }
        try {
            val kod = c.responseCode
            val oqim = if (kod < 400) c.inputStream else c.errorStream
            val baytlar = oqim?.use { it.readBytes() } ?: ByteArray(0)
            return Pair(Javob(kod, baytlar), c.headerFields.filterKeys { it != null })
        } finally {
            c.disconnect()
        }
    }

    private fun xesh(alg: String, s: String): String {
        val nom = if (alg.uppercase().startsWith("SHA-256")) "SHA-256" else "MD5"
        return MessageDigest.getInstance(nom).digest(s.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }
    }

    // 'realm="x", nonce="y", qop="auth"' -> xarita
    private fun ajrat(s: String): Map<String, String> {
        val natija = HashMap<String, String>()
        Regex("""(\w+)\s*=\s*(?:"([^"]*)"|([^,\s]*))""").findAll(s).forEach {
            natija[it.groupValues[1].lowercase()] = it.groupValues[2].ifEmpty { it.groupValues[3] }
        }
        return natija
    }

    private fun digest(chal: Map<String, String>, usul: String, yol: String, login: String, parol: String): String? {
        val alg = chal["algorithm"] ?: "MD5"
        if (alg.uppercase() !in listOf("MD5", "MD5-SESS", "SHA-256", "SHA-256-SESS")) return null
        val realm = chal["realm"] ?: ""
        val nonce = chal["nonce"] ?: return null
        val cnonce = ByteArray(8).also { SecureRandom().nextBytes(it) }.joinToString("") { "%02x".format(it) }
        val nc = "00000001"
        var ha1 = xesh(alg, "$login:$realm:$parol")
        if (alg.uppercase().endsWith("-SESS")) ha1 = xesh(alg, "$ha1:$nonce:$cnonce")
        val ha2 = xesh(alg, "$usul:$yol")
        val qoplar = (chal["qop"] ?: "").split(",").map { it.trim() }.filter { it.isNotEmpty() }
        val sb = StringBuilder("Digest username=\"$login\", realm=\"$realm\", nonce=\"$nonce\", uri=\"$yol\", algorithm=$alg")
        if ("auth" in qoplar) {
            sb.append(", response=\"${xesh(alg, "$ha1:$nonce:$nc:$cnonce:auth:$ha2")}\", qop=auth, nc=$nc, cnonce=\"$cnonce\"")
        } else if (qoplar.isNotEmpty()) {
            return null
        } else {
            sb.append(", response=\"${xesh(alg, "$ha1:$nonce:$ha2")}\"")
        }
        chal["opaque"]?.let { sb.append(", opaque=\"$it\"") }
        return sb.toString()
    }

    fun sorov(ip: String, port: Int, yol: String, login: String, parol: String,
              usul: String = "GET", tana: ByteArray? = null, soniya: Int = 8): Javob {
        val url = "http://$ip" + (if (port == 80) "" else ":$port") + yol
        val (birinchi, sarl) = ulan(url, usul, null, tana, soniya)
        if (birinchi.kod != 401) return birinchi
        val matn = String(birinchi.tana, Charsets.UTF_8)
        if (Regex("<lockStatus>\\s*lock\\s*</lockStatus>", RegexOption.IGNORE_CASE).containsMatchIn(matn)) return birinchi
        val chaqiriqlar = sarl.entries.filter { it.key.equals("WWW-Authenticate", true) }.flatMap { it.value }
        for (c in chaqiriqlar.filter { it.trim().startsWith("Digest", true) }) {
            val imzo = digest(ajrat(c.trim().substring(6)), usul, yol, login, parol) ?: continue
            return ulan(url, usul, imzo, tana, soniya).first
        }
        if (chaqiriqlar.any { it.trim().startsWith("Basic", true) }) {
            val b = Base64.encodeToString("$login:$parol".toByteArray(), Base64.NO_WRAP)
            return ulan(url, usul, "Basic $b", tana, soniya).first
        }
        return birinchi
    }

    // "1" -> "101", "101" -> "101"
    fun kanal(k: String): String {
        val t = k.trim().ifEmpty { "101" }
        return if (t.all { it.isDigit() } && t.length <= 2) "${t.toInt()}01" else t
    }

    // JSON-ga tayyor natija: {"ok":true,"rasm":"base64"} yoki {"ok":false,"xato":"..."}
    fun rasm(ip: String, port: Int, login: String, parol: String, kanalNom: String): String {
        if (parol.isEmpty()) {                 // parolsiz — faqat "kamera shu tarmoqdami" (xato urinish sarflamaymiz)
            return try {
                ulan("http://$ip" + (if (port == 80) "" else ":$port") + "/ISAPI/System/deviceInfo", "GET", null, null, 4)
                "{\"ok\":false,\"yetib\":true,\"parolYoq\":true,\"xato\":\"Parolni kiriting\"}"
            } catch (e: Exception) {
                xato("Kameraga ulanib bo'lmadi — telefon uy Wi-Fi'dami, kamera yoqilganmi?", false)
            }
        }
        return try {
            val j = sorov(ip, port, "/ISAPI/Streaming/channels/${kanal(kanalNom)}/picture", login, parol)
            val t = j.tana
            when {
                j.kod == 200 && t.size > 2 && t[0] == 0xFF.toByte() && t[1] == 0xD8.toByte() ->
                    "{\"ok\":true,\"rasm\":\"" + Base64.encodeToString(t, Base64.NO_WRAP) + "\"}"
                j.kod == 401 && String(t).contains("lock", true) && !String(t).contains(">unlock<", true) ->
                    xato("Kamera telefonni vaqtincha bloklagan (ko'p xato parol). Kamerani o'chirib-yoqing yoki 30 daqiqa kuting")
                j.kod == 401 -> xato("Login yoki parol noto'g'ri")
                j.kod == 403 -> xato("Bu foydalanuvchiga rasm olishga ruxsat yo'q")
                else -> xato("Kamera javobi: HTTP ${j.kod}")
            }
        } catch (e: Exception) {
            xato("Kameraga ulanib bo'lmadi — telefon uy Wi-Fi'dami, kamera yoqilganmi?", false)
        }
    }

    // yetib=true — kamera javob berdi (demak telefon uy tarmog'ida), faqat kirish muammosi
    private fun xato(m: String, yetib: Boolean = true) = "{\"ok\":false,\"yetib\":$yetib,\"xato\":\"" +
        m.replace("\\", "\\\\").replace("\"", "\\\"") + "\"}"
}
