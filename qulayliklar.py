"""
Kundalik qulayliklar (hammasi bepul, kalitsiz):
  - Ob-havo (wttr.in)                 — "ob-havo qanday", "Samarqandda ob-havo"
  - Valyuta kursi (O'zbekiston Markaziy banki, cbu.uz) — "dollar kursi"
  - Eslatma / taymer                  — "10 daqiqadan keyin choy ichishni eslat", "soat 18:30 da ..."
  - Qaydlar (eslab qolish)            — "eslab qol: wifi paroli 12345", "qaydlarimni ayt"
  - Kompyuter holati                  — xotira, batareya, disk, qancha vaqtdan beri yoniq
  - Tonggi brifing                    — "xayrli tong"
"""
import ctypes
import datetime
import json
import os
import re
import shutil
import threading
import time
import urllib.parse
import urllib.request

import sozlamalar

WINDOWS = os.name == "nt"
BRAUZER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0 Safari/537.36"}


def _json(url, timeout=10):
    with urllib.request.urlopen(urllib.request.Request(url, headers=BRAUZER), timeout=timeout) as j:
        return json.loads(j.read().decode("utf-8"))


# ---------- OB-HAVO ----------
SHAHARLAR = {  # aytilishi -> wttr.in uchun nomi, chiroyli nomi
    "toshkent": ("Tashkent", "Toshkent"), "buxoro": ("Bukhara", "Buxoro"),
    "samarqand": ("Samarkand", "Samarqand"), "andijon": ("Andijan", "Andijon"),
    "farg'ona": ("Fergana", "Farg'ona"), "fargona": ("Fergana", "Farg'ona"),
    "namangan": ("Namangan", "Namangan"), "qarshi": ("Qarshi", "Qarshi"),
    "navoiy": ("Navoiy", "Navoiy"), "jizzax": ("Jizzakh", "Jizzax"), "urganch": ("Urgench", "Urganch"),
    "xiva": ("Khiva", "Xiva"), "nukus": ("Nukus", "Nukus"), "termiz": ("Termez", "Termiz"),
    "guliston": ("Gulistan", "Guliston"), "qo'qon": ("Kokand", "Qo'qon"), "kogon": ("Kogon", "Kogon"),
    "moskva": ("Moscow", "Moskva"), "istanbul": ("Istanbul", "Istanbul"), "dubay": ("Dubai", "Dubay"),
    "seul": ("Seoul", "Seul"), "london": ("London", "London"), "nyu-york": ("New York", "Nyu-York"),
}
# wttr.in ob-havo kodlari -> o'zbekcha
HAVO_KODLARI = {
    113: "quyoshli ☀️", 116: "biroz bulutli ⛅", 119: "bulutli ☁️", 122: "qalin bulutli ☁️",
    143: "tumanli 🌫️", 248: "tumanli 🌫️", 260: "qalin tuman 🌫️", 176: "vaqti-vaqti bilan yomg'ir 🌦️",
    263: "mayda yomg'ir 🌦️", 266: "mayda yomg'ir 🌦️", 293: "yengil yomg'ir 🌧️", 296: "yengil yomg'ir 🌧️",
    299: "yomg'ir 🌧️", 302: "yomg'ir 🌧️", 305: "kuchli yomg'ir 🌧️", 308: "jala 🌧️", 353: "yengil jala 🌦️",
    356: "jala 🌧️", 359: "kuchli jala ⛈️", 200: "momaqaldiroq ⛈️", 386: "momaqaldiroqli yomg'ir ⛈️",
    389: "kuchli momaqaldiroq ⛈️", 179: "biroz qor 🌨️", 227: "qor bo'roni ❄️", 230: "kuchli bo'ron ❄️",
    323: "yengil qor 🌨️", 326: "qor 🌨️", 329: "qor ❄️", 332: "qor ❄️", 335: "kuchli qor ❄️",
    338: "kuchli qor ❄️", 368: "yengil qor 🌨️", 371: "qor ❄️", 182: "qorli yomg'ir 🌨️", 317: "qorli yomg'ir 🌨️",
}


def shahar_top(gap, standart="toshkent"):
    """Gapdan shaharni topadi: 'samarqandda ob-havo' -> ('Samarkand', 'Samarqand')."""
    for soz, qiymat in SHAHARLAR.items():
        if soz in gap:
            return qiymat
    return SHAHARLAR.get((standart or "toshkent").lower(), (standart, standart.title()))


def ob_havo(gap="", standart="toshkent"):
    shahar, nomi = shahar_top(gap, standart)
    try:
        d = _json(f"https://wttr.in/{urllib.parse.quote(shahar)}?format=j1")
    except Exception as xato:
        print(f"(Ob-havo xatosi: {xato})")
        return "Ob-havo ma'lumotini ololmadim. Internetni tekshiring."
    hozir = d["current_condition"][0]
    bugun = d["weather"][0]
    ertaga = d["weather"][1] if len(d.get("weather", [])) > 1 else None
    holat = HAVO_KODLARI.get(int(hozir.get("weatherCode", 0)), hozir["weatherDesc"][0]["value"])
    yomgir = max(int(s.get("chanceofrain", 0)) for s in bugun.get("hourly", [{}]))
    matn = (f"{nomi}da hozir {hozir['temp_C']}°, {holat}. Seziladi: {hozir['FeelsLikeC']}°. "
            f"Bugun {bugun['mintempC']}° dan {bugun['maxtempC']}° gacha, "
            f"shamol {hozir['windspeedKmph']} km/soat.")
    if yomgir >= 40:
        matn += f" Yomg'ir ehtimoli {yomgir}% — soyabon oling ☂️."
    if "ertaga" in gap and ertaga:
        matn += f" Ertaga {ertaga['mintempC']}° dan {ertaga['maxtempC']}° gacha."
    try:
        if int(bugun["maxtempC"]) >= 35:
            matn += " Juda issiq — ko'proq suv iching."
        elif int(bugun["mintempC"]) <= 0:
            matn += " Sovuq — issiq kiyining."
    except (KeyError, ValueError):
        pass
    return matn


# ---------- VALYUTA KURSI ----------
VALYUTALAR = {"dollar": "USD", "usd": "USD", "евро": "EUR", "yevro": "EUR", "evro": "EUR", "euro": "EUR",
              "rubl": "RUB", "рубл": "RUB", "tenge": "KZT", "lira": "TRY", "yuan": "CNY",
              "funt": "GBP", "von": "KRW", "dirham": "AED"}
VALYUTA_NOMI = {"USD": "Dollar", "EUR": "Yevro", "RUB": "Rubl", "KZT": "Tenge", "TRY": "Turk lirasi",
                "CNY": "Yuan", "GBP": "Funt", "KRW": "Koreys voni", "AED": "Dirham"}


def _son(x):
    return f"{x:,.2f}".replace(",", " ").replace(".00", "")


def kurs(gap=""):
    kerak = [k for s, k in VALYUTALAR.items() if s in gap] or ["USD", "EUR", "RUB"]
    kerak = list(dict.fromkeys(kerak))
    try:
        royxat = _json("https://cbu.uz/uz/arkhiv-kursov-valyut/json/")
    except Exception as xato:
        print(f"(Kurs xatosi: {xato})")
        return "Valyuta kursini ololmadim. Internetni tekshiring."
    kurslar = {r["Ccy"]: r for r in royxat}
    qismlar = []
    for k in kerak:
        r = kurslar.get(k)
        if not r:
            continue
        birlik = int(r.get("Nominal", "1") or 1)
        farq = float(r.get("Diff", 0) or 0)
        yon = "↑" if farq > 0 else ("↓" if farq < 0 else "")
        qismlar.append(f"{birlik if birlik > 1 else 1} {VALYUTA_NOMI.get(k, k).lower()} — "
                       f"{_son(float(r['Rate']))} so'm {yon}".strip())
    if not qismlar:
        return "Bu valyuta kursini topmadim."
    return "Markaziy bank kursi: " + "; ".join(qismlar) + "."


# ---------- ESLATMA / TAYMER ----------
SONLAR = {"bir": 1, "ikki": 2, "uch": 3, "to'rt": 4, "tort": 4, "besh": 5, "olti": 6, "yetti": 7,
          "sakkiz": 8, "to'qqiz": 9, "toqqiz": 9, "o'n": 10, "on": 10, "yigirma": 20, "o'ttiz": 30,
          "ottiz": 30, "qirq": 40, "ellik": 50, "oltmish": 60, "yarim": 0.5}
BIRLIKLAR = (("sekund", 1), ("soniya", 1), ("daqiqa", 60), ("minut", 60), ("soat", 3600), ("kun", 86400))


def _soz_son(sozlar):
    """['o'n', 'besh'] -> 15"""
    jami, bor = 0, False
    for s in sozlar:
        if s in SONLAR:
            jami += SONLAR[s]
            bor = True
        elif re.fullmatch(r"\d+([.,]\d+)?", s):
            jami += float(s.replace(",", "."))
            bor = True
    return jami if bor else None


def eslatma_ajrat(gap, hozir=None):
    """'10 daqiqadan keyin choy ichishni eslat' -> (600, 'choy ichish')
    'soat 18:30 da onamga qo'ng'iroq qilishni eslat' -> (soniya, "onamga qo'ng'iroq qilish")
    '5 minutlik taymer' -> (300, 'taymer')"""
    hozir = hozir or datetime.datetime.now()
    gap = gap.replace("’", "'").lower()
    gap = re.sub(r"\b(bir )?soat yarim", "1.5 soat", gap)       # "soat yarimdan keyin" = 1,5 soat
    gap = re.sub(r"\bbir yarim (soat|daqiqa|minut)", r"1.5 \1", gap)
    gap = re.sub(r"\byarim (soat|daqiqa|minut)", r"0.5 \1", gap)
    # 1) aniq soat: "soat 18:30 da", "18.30 da"
    m = re.search(r"(?:soat\s*)?(\d{1,2})[:.](\d{2})\s*(?:da|ga)?", gap)
    soniya = None
    if m and int(m.group(1)) < 24 and int(m.group(2)) < 60:
        vaqt = hozir.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        if vaqt <= hozir:
            vaqt += datetime.timedelta(days=1)
        soniya = (vaqt - hozir).total_seconds()
        qolgan = gap[:m.start()] + " " + gap[m.end():]
    else:
        # 2) davomiylik: "10 daqiqadan keyin", "bir yarim soatdan so'ng", "o'n besh minutlik"
        sozlar = gap.split()
        for i, soz in enumerate(sozlar):
            birlik = next((q for b, q in BIRLIKLAR if soz.startswith(b)), None)
            if not birlik:
                continue
            j = i
            while j > 0 and (sozlar[j - 1] in SONLAR or re.fullmatch(r"\d+([.,]\d+)?", sozlar[j - 1])):
                j -= 1
            son = _soz_son(sozlar[j:i])
            if son is None:
                son = 1                                   # "bir soatdan keyin" -> "soatdan keyin"
            soniya = son * birlik
            qolgan = " ".join(sozlar[:j] + sozlar[i + 1:])
            break
    if soniya is None:
        return None, None
    # eslatiladigan ish: ortiqcha so'zlarni tozalaymiz
    qolgan = re.sub(r"\b(keyin|so'ng|song|o'tgach|dan|jarvis|menga|iltimos|eslat\w*|esimga\s+sol\w*|"
                    r"taymer\w*|budilnik\w*|qo'y\w*|lik|da|ga|ni)\b", " ", qolgan)
    qolgan = re.sub(r"\s+", " ", qolgan).strip(" ,.")
    if qolgan.endswith("ni") and len(qolgan) > 4:
        qolgan = qolgan[:-2]                                        # "ichishni" -> "ichish", "darsni" -> "dars"
    return soniya, qolgan or "vaqt bo'ldi"


def vaqt_matn(soniya):
    soniya = int(round(soniya))
    if soniya >= 120:
        soniya = int(round(soniya / 60)) * 60          # "59 daqiqa 3 soniya" emas, "59 daqiqa"
    if soniya < 60:
        return f"{soniya} soniyadan"
    if soniya < 3600:
        d, s = divmod(soniya, 60)
        return f"{d} daqiqa" + (f" {s} soniya" if s else "") + "dan"
    s, d = divmod(soniya // 60, 60)
    return f"{s} soat" + (f" {d} daqiqa" if d else "") + "dan"


class Eslatmalar:
    """Faol eslatmalar. Vaqti kelganda qaytaruvchi (callback) chaqiriladi.
    Dastur yopilsa ham yo'qolmaydi — faylda saqlanadi va qayta ochilganda tiklanadi."""

    def __init__(self, qaytaruvchi):
        self.qaytaruvchi = qaytaruvchi
        self.fayl = os.path.join(sozlamalar.PAPKA, "eslatmalar.json")
        self.royxat = []                      # [{"vaqt": epoch, "ish": "..."}]
        self._qulf = threading.Lock()
        try:
            with open(self.fayl, encoding="utf-8") as f:
                self.royxat = json.load(f)
        except (OSError, ValueError):
            self.royxat = []
        threading.Thread(target=self._kuzat, daemon=True).start()

    def _saqla(self):
        try:
            os.makedirs(os.path.dirname(self.fayl), exist_ok=True)
            with open(self.fayl, "w", encoding="utf-8") as f:
                json.dump(self.royxat, f, ensure_ascii=False)
        except OSError:
            pass

    def qosh(self, soniya, ish):
        with self._qulf:
            self.royxat.append({"vaqt": time.time() + soniya, "ish": ish})
            self._saqla()

    def faollar(self):
        with self._qulf:
            return sorted(self.royxat, key=lambda e: e["vaqt"])

    def tozala(self):
        with self._qulf:
            soni = len(self.royxat)
            self.royxat = []
            self._saqla()
            return soni

    def _kuzat(self):
        while True:
            time.sleep(1)
            with self._qulf:
                hozir = time.time()
                vaqti_kelgan = [e for e in self.royxat if e["vaqt"] <= hozir]
                if vaqti_kelgan:
                    self.royxat = [e for e in self.royxat if e["vaqt"] > hozir]
                    self._saqla()
            for e in vaqti_kelgan:
                kechikdi = hozir - e["vaqt"] > 120     # kompyuter o'chiq bo'lgan bo'lsa
                try:
                    self.qaytaruvchi(e["ish"], kechikdi)
                except Exception as xato:
                    print(f"(Eslatma xatosi: {xato})")


# ---------- QAYDLAR (eslab qolish) ----------
QAYD_FAYL = os.path.join(sozlamalar.PAPKA, "qaydlar.json")


def qaydlar():
    try:
        with open(QAYD_FAYL, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def qayd_qosh(matn):
    royxat = qaydlar()
    royxat.append({"sana": datetime.date.today().isoformat(), "matn": matn})
    os.makedirs(os.path.dirname(QAYD_FAYL), exist_ok=True)
    with open(QAYD_FAYL, "w", encoding="utf-8") as f:
        json.dump(royxat, f, ensure_ascii=False, indent=1)
    return len(royxat)


def qaydlarni_ochir():
    try:
        os.remove(QAYD_FAYL)
    except OSError:
        pass


def qayd_matni(gap):
    """'eslab qol: wifi paroli 12345' -> 'wifi paroli 12345'"""
    m = re.search(r"(eslab qol\w*|yodda tut\w*|yozib qo'y\w*|qayd qil\w*|zapomni|запомни)[\s:,-]*(.*)", gap,
                  re.IGNORECASE)
    return (m.group(2).strip(" .") if m else "").strip()


# ---------- KOMPYUTER HOLATI ----------
def kompyuter_holati():
    qismlar = []
    if WINDOWS:
        class XOTIRA(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        x = XOTIRA()
        x.dwLength = ctypes.sizeof(XOTIRA)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(x)):
            jami = x.ullTotalPhys / 1024 ** 3
            qismlar.append(f"Operativ xotira {x.dwMemoryLoad}% band ({jami:.1f} GB dan "
                           f"{(x.ullTotalPhys - x.ullAvailPhys) / 1024 ** 3:.1f} GB)")

        class QUVVAT(ctypes.Structure):
            _fields_ = [("ACLineStatus", ctypes.c_byte), ("BatteryFlag", ctypes.c_byte),
                        ("BatteryLifePercent", ctypes.c_byte), ("SystemStatusFlag", ctypes.c_byte),
                        ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]
        q = QUVVAT()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(q)) and q.BatteryFlag != -128 \
                and 0 <= q.BatteryLifePercent <= 100:
            zaryad = "quvvatga ulangan" if q.ACLineStatus == 1 else "batareyadan ishlayapti"
            qismlar.append(f"batareya {q.BatteryLifePercent}%, {zaryad}")
        ms = ctypes.windll.kernel32.GetTickCount64
        ms.restype = ctypes.c_ulonglong
        soat = ms() / 3_600_000
        qismlar.append(f"kompyuter {int(soat)} soat {int(soat % 1 * 60)} daqiqadan beri yoniq")
    try:
        disk = "C:\\" if WINDOWS else "/"
        d = shutil.disk_usage(disk)
        qismlar.append(f"C diskida {d.free / 1024 ** 3:.0f} GB bo'sh joy bor ({d.total / 1024 ** 3:.0f} GB dan)")
        if d.free / d.total < 0.1:
            qismlar.append("disk deyarli to'lgan — keshni tozalashni maslahat beraman")
    except OSError:
        pass
    if not qismlar:
        return "Kompyuter holatini aniqlay olmadim."
    matn = "; ".join(qismlar)
    return matn[0].upper() + matn[1:] + "."


# ---------- TONGGI BRIFING ----------
HAFTA = ["dushanba", "seshanba", "chorshanba", "payshanba", "juma", "shanba", "yakshanba"]
OYLAR = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr",
         "noyabr", "dekabr"]


def salomlashuv(ism):
    s = datetime.datetime.now().hour
    if 5 <= s < 12:
        return f"Xayrli tong, {ism}!"
    if 12 <= s < 18:
        return f"Xayrli kun, {ism}!"
    if 18 <= s < 23:
        return f"Xayrli kech, {ism}!"
    return f"Salom, {ism}! Kech bo'lib qoldi, dam olishni unutmang."


def brifing(ism, shahar="toshkent", eslatmalar_soni=0):
    b = datetime.datetime.now()
    qismlar = [salomlashuv(ism),
               f"Bugun {b.day}-{OYLAR[b.month - 1]}, {HAFTA[b.weekday()]}, soat {b:%H:%M}."]
    qismlar.append(ob_havo("", shahar))
    k = kurs("dollar")
    if not k.startswith("Valyuta"):
        qismlar.append(k)
    if eslatmalar_soni:
        qismlar.append(f"Sizda {eslatmalar_soni} ta faol eslatma bor.")
    qismlar.append("Omadli kun tilayman! 💪")
    return " ".join(qismlar)
