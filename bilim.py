"""
Savollarga javob: o'zbekcha Vikipediyadan qidirib, qisqa javob qaytaradi.
Bepul, API kalit shart emas.
"""
import json
import re
import urllib.parse
import urllib.request

# Qo'shimchalari bilan keladigan savol so'zlari (qayerda, qanchaga, nechanchi...)
SAVOL_BOSHLARI = ("qachon", "qayer", "qancha", "nechta", "necha", "qanday", "nimaga",
                  "haqida", "degani", "ma'lumot")
# Qisqa so'zlar faqat to'liq mos kelsa tashlanadi ("bu" tashlanadi, "Buxoro" emas)
SAVOL_SOZLARI = {"kim", "kimning", "kimga", "kimdir", "nima", "nimani", "nimaning", "nega",
                 "qaysi"}
ORTIQCHA = SAVOL_SOZLARI | {"menga", "ayt", "aytib", "aytchi", "ber", "gapir", "gapirib",
                            "bilasanmi", "bilasan", "edi", "ekan", "o'zi", "iltimos", "bu",
                            "u", "haqda", "jarvis"}
BRAUZER = {"User-Agent": "JarvisUz/1.0 (shaxsiy ovozli yordamchi)"}


def savolmi(gap):
    sozlar = [s.strip("?,.!") for s in gap.split()]
    return "?" in gap or any(s in SAVOL_SOZLARI or s.startswith(SAVOL_BOSHLARI) for s in sozlar)


def savol_mavzusi(gap):
    """'amir temur kim edi' -> 'amir temur'"""
    sozlar = [s.strip("?,.!") for s in gap.split()]
    return " ".join(s for s in sozlar
                    if s and s not in ORTIQCHA and not s.startswith(SAVOL_BOSHLARI)).strip()


def _ol(url):
    sorov = urllib.request.Request(url, headers=BRAUZER)
    with urllib.request.urlopen(sorov, timeout=8) as javob:
        return json.loads(javob.read().decode("utf-8"))


def vikipediya(mavzu, til="uz"):
    """Mavzu bo'yicha maqolaning birinchi 2 gapini qaytaradi yoki None."""
    qidiruv = _ol(f"https://{til}.wikipedia.org/w/api.php?action=query&list=search"
                  f"&format=json&srlimit=1&srsearch=" + urllib.parse.quote(mavzu))
    topildi = qidiruv.get("query", {}).get("search", [])
    if not topildi:
        return None
    sarlavha = topildi[0]["title"]
    xulosa = _ol(f"https://{til}.wikipedia.org/api/rest_v1/page/summary/"
                 + urllib.parse.quote(sarlavha.replace(" ", "_")))
    matn = xulosa.get("extract", "")
    matn = re.sub(r"\s*\([^)]*\)", "", matn)          # qavs ichini o'qimaymiz (sana, talaffuz)
    gaplar = re.split(r"(?<=[.!?])\s+", matn.strip())
    javob = " ".join(gaplar[:2]).strip()
    return javob or None


def javob_top(gap):
    """(javob, None) yoki (None, google_havolasi)"""
    mavzu = savol_mavzusi(gap) or gap
    try:
        javob = vikipediya(mavzu)
        if javob:
            return javob, None
    except Exception as xato:
        print(f"(Vikipediya xatosi: {xato})")
    return None, "https://www.google.com/search?q=" + urllib.parse.quote(gap)
