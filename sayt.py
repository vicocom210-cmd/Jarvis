"""
Saytni o'qib, AI (Claude/Groq) bilan tahlil qilish: "cuticlehair.co saytiga kirib 1 dan 10 gacha baholab ber".

Sayt sahifasi yuklab olinadi (brauzer ochilmaydi), matni va texnik belgilari (HTTPS, tezlik,
telefonga moslik, tavsif...) AI'ga beriladi — AI so'ralgan ishni (baho, xulosa, kamchiliklar) qiladi.
"""
import html
import re
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Safari/537.36")
# fayl nomlari sayt deb olinmasin ("video.mp4", "rasm.png")
FAYL_TURLARI = {"png", "jpg", "jpeg", "gif", "mp4", "mp3", "mov", "avi", "mkv", "txt", "pdf", "doc",
                "docx", "xls", "xlsx", "ppt", "pptx", "exe", "zip", "rar", "py", "json", "wav", "webp"}
MANZIL = re.compile(r"(https?://)?((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+([a-z]{2,24}))(?![a-z0-9-])(/[^\s\"'«»“”]*)?", re.I)
# "baholab ber", "tahlil qil", "nima yozilgan", "kamchiliklari" ...
TAHLIL_SOZLARI = ("baho", "baxo", "bahol", "tahlil", "taxlil", "xulosa", "o'qi", "oqib", "o'qib", "ko'rib chiq",
                  "korib chiq", "fikr", "nima yozilgan", "nima bor", "haqida", "tekshir", "kamchilik",
                  "yaxshimi", "qanday sayt", "ball", "reyting", "rating", "rate", "review", "оцен", "анализ",
                  "проверь", "о чем", "о чём", "tushuntir", "nima qiladi", "nima sotadi", "maslahat")


class SaytXato(Exception):
    pass


def manzil_top(gap):
    """Gapdagi sayt manzili ('cuticlehair.co', 'https://kun.uz/news') -> to'liq URL yoki None."""
    for m in MANZIL.finditer(gap):
        if m.group(3).lower() in FAYL_TURLARI:
            continue
        return (m.group(1) or "https://") + m.group(2).lower() + (m.group(4) or "").rstrip(".,!?)")
    return None


def tahlilmi(gap):
    """Saytni ochish emas, balki o'qib tahlil qilish so'ralganmi?"""
    g = gap.lower()
    return bool(manzil_top(g)) and any(s in g for s in TAHLIL_SOZLARI)


class _Oquvchi(HTMLParser):
    """HTML -> ko'rinadigan matn + sarlavha, tavsif va boshqa belgilar."""
    YASHIRIN = {"script", "style", "noscript", "svg", "template", "iframe"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.matn, self.sarlavha, self.tavsif = [], "", ""
        self.viewport = False
        self.rasmlar = self.havolalar = self.rasm_altsiz = 0
        self.h1 = []
        self._yashirin = 0
        self._teg = ""
        self._h1 = None

    def handle_starttag(self, teg, attrs):
        a = dict(attrs)
        self._teg = teg
        if teg in self.YASHIRIN:
            self._yashirin += 1
        elif teg == "meta":
            nom = (a.get("name") or a.get("property") or "").lower()
            if nom in ("description", "og:description") and not self.tavsif:
                self.tavsif = (a.get("content") or "").strip()
            elif nom == "viewport":
                self.viewport = True
        elif teg == "img":
            self.rasmlar += 1
            if not (a.get("alt") or "").strip():
                self.rasm_altsiz += 1
        elif teg == "a" and a.get("href"):
            self.havolalar += 1
        if teg == "h1":
            self._h1 = []
        if teg in ("p", "div", "li", "br", "h1", "h2", "h3", "h4", "tr", "section"):
            self.matn.append("\n")

    def handle_endtag(self, teg):
        if teg in self.YASHIRIN and self._yashirin:
            self._yashirin -= 1
        elif teg == "h1" and self._h1 is not None:
            if "".join(self._h1).strip():
                self.h1.append(" ".join("".join(self._h1).split()))
            self._h1 = None
        self._teg = ""

    def handle_data(self, data):
        if self._yashirin:
            return
        if self._teg == "title" and not self.sarlavha:
            self.sarlavha = data.strip()
            return
        if self._h1 is not None:
            self._h1.append(data)
        self.matn.append(data)


def oqi(url, chegara=9000):
    """Sahifani yuklab, AI uchun qisqa hisobot matnini qaytaradi."""
    sorov = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*;q=0.8",
                                                 "Accept-Language": "en,ru;q=0.8,uz;q=0.7"})
    boshlanish = time.time()
    try:
        with urllib.request.urlopen(sorov, timeout=20) as javob:
            xom = javob.read(3_000_000)
            oxirgi_url = javob.geturl()
            kodlash = javob.headers.get_content_charset() or "utf-8"
            tur = javob.headers.get_content_type()
    except urllib.error.HTTPError as xato:
        raise SaytXato(f"sayt xato qaytardi (HTTP {xato.code})")
    except urllib.error.URLError as xato:
        sabab = str(getattr(xato, "reason", xato))
        if "getaddrinfo" in sabab or "Name or service" in sabab or "11001" in sabab:
            raise SaytXato("bunday sayt topilmadi — manzilni tekshiring")
        raise SaytXato(f"saytga ulanib bo'lmadi ({sabab[:80]})")
    except (TimeoutError, OSError) as xato:
        raise SaytXato(f"sayt javob bermadi ({str(xato)[:80]})")
    vaqt = time.time() - boshlanish
    if "html" not in tur:
        raise SaytXato(f"bu sahifa emas, fayl ekan ({tur})")
    o = _Oquvchi()
    try:
        o.feed(xom.decode(kodlash, "ignore"))
    except Exception:
        pass
    matn = re.sub(r"[ \t\r\f\v]+", " ", html.unescape("".join(o.matn)))
    matn = re.sub(r"\n\s*\n+", "\n", matn).strip()
    belgilar = [
        f"Manzil: {oxirgi_url}",
        f"HTTPS (xavfsiz ulanish): {'ha' if oxirgi_url.startswith('https://') else 'YOQ'}",
        f"Yuklanish vaqti: {vaqt:.1f} soniya, hajmi: {len(xom) // 1024} KB",
        f"Sarlavha (title): {o.sarlavha or 'YOQ'}",
        f"Tavsif (meta description): {o.tavsif[:300] or 'YOQ'}",
        f"Telefonga moslashgan (viewport): {'ha' if o.viewport else 'YOQ'}",
        f"H1 sarlavhalar: {'; '.join(o.h1[:3]) or 'YOQ'}",
        f"Rasmlar: {o.rasmlar} (alt yozuvisiz: {o.rasm_altsiz}), havolalar: {o.havolalar}",
    ]
    if len(matn) < 200:
        belgilar.append("Eslatma: sahifa matni juda kam — sayt JavaScript bilan chiziladigan bo'lishi mumkin.")
    return "\n".join(belgilar) + "\n\nSahifa matni (boshidan):\n" + matn[:chegara]
