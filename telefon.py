"""
Telefonni kompyuterdan boshqarish (Android, ADB orqali).

ADB — Google'ning bepul rasmiy vositasi. Telefonga hech narsa o'rnatilmaydi,
faqat telefon sozlamalarida "USB debugging" yoqiladi va kabel bilan ulanadi
(yoki Wi-Fi orqali). Har yangi kompyuter uchun telefonda "Ruxsat berasizmi?"
deb so'raladi — bir marta "Ha, doim" desangiz bo'ldi.

ADB dasturi qayerda ekanini topish:
  1) JARVIS_ADB muhit o'zgaruvchisi (to'liq yo'l),
  2) PATH (adb buyrug'i),
  3) odatiy joylar (platform-tools papkasi).
"""
import os
import subprocess

KONSOLSIZ = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Telefon ilovalari: aytiladigan nom -> Android paket nomi
PAKETLAR = {
    "telegram": "org.telegram.messenger", "instagram": "com.instagram.android",
    "youtube": "com.google.android.youtube", "whatsapp": "com.whatsapp",
    "chrome": "com.android.chrome", "kamera": "com.android.camera",
    "galereya": "com.android.gallery3d", "gallery": "com.android.gallery3d",
    "qo'ng'iroq": "com.android.dialer", "telefon": "com.android.dialer",
    "xabar": "com.google.android.apps.messaging", "sms": "com.google.android.apps.messaging",
    "sozlama": "com.android.settings", "kalkulyator": "com.android.calculator2",
    "playmarket": "com.android.vending", "play market": "com.android.vending",
    "maps": "com.google.android.apps.maps", "xarita": "com.google.android.apps.maps",
    "gmail": "com.google.android.gm", "tiktok": "com.zhiliaoapp.musically",
    "facebook": "com.facebook.katana", "spotify": "com.spotify.music",
}
TUGMALAR = {"uy": "KEYCODE_HOME", "home": "KEYCODE_HOME", "orqaga": "KEYCODE_BACK",
            "back": "KEYCODE_BACK", "menyu": "KEYCODE_MENU", "power": "KEYCODE_POWER",
            "ovozni oshir": "KEYCODE_VOLUME_UP", "ovozni pasaytir": "KEYCODE_VOLUME_DOWN",
            "keyingi": "KEYCODE_MEDIA_NEXT", "oldingi": "KEYCODE_MEDIA_PREVIOUS",
            "pauza": "KEYCODE_MEDIA_PLAY_PAUSE"}

_adb_yoli = None


def adb_yoli():
    """adb.exe qayerdaligini topadi (bir marta) yoki None."""
    global _adb_yoli
    if _adb_yoli:
        return _adb_yoli
    nomzodlar = [os.environ.get("JARVIS_ADB"), "adb"]
    for asos in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("USERPROFILE", ""),
                 r"C:\platform-tools", r"C:\adb", os.path.dirname(os.path.abspath(__file__))):
        if asos:
            nomzodlar.append(os.path.join(asos, "platform-tools", "adb.exe"))
            nomzodlar.append(os.path.join(asos, "adb.exe"))
    for yol in nomzodlar:
        if not yol:
            continue
        try:
            subprocess.run([yol, "version"], capture_output=True, timeout=10,
                           creationflags=KONSOLSIZ)
            _adb_yoli = yol
            return yol
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def adb(*argumentlar, timeout=60, ikkilik=False):
    """adb buyrug'ini bajaradi. (returncode, chiqish) qaytaradi.
    ikkilik=True bo'lsa, chiqish xom baytlarda (ekran rasmi uchun)."""
    yol = adb_yoli()
    if not yol:
        return -1, b"" if ikkilik else "ADB topilmadi"
    try:
        natija = subprocess.run([yol, *argumentlar], capture_output=True, timeout=timeout,
                                creationflags=KONSOLSIZ)
    except (OSError, subprocess.SubprocessError) as xato:
        return -1, b"" if ikkilik else str(xato)
    if ikkilik:
        return natija.returncode, natija.stdout
    return natija.returncode, (natija.stdout + natija.stderr).decode("utf-8", "ignore").strip()


def ulanganmi():
    """Telefon ulanganmi? (kod, holat) qaytaradi.
    holat: 'ok', 'yoq_adb', 'yoq_telefon', 'ruxsat' (unauthorized)."""
    if not adb_yoli():
        return False, "yoq_adb"
    kod, chiqish = adb("devices")
    if kod != 0:
        return False, "yoq_adb"
    qatorlar = [q for q in chiqish.splitlines()[1:] if q.strip()]
    for q in qatorlar:
        if q.endswith("\tdevice") or q.endswith(" device"):
            return True, "ok"
        if "unauthorized" in q:
            return False, "ruxsat"
    return False, "yoq_telefon"


# ---------- ILOVA VA TUGMALAR ----------
def ilova_paketi(nom):
    nom = nom.lower().strip()
    if nom in PAKETLAR:
        return PAKETLAR[nom]
    for kalit, paket in PAKETLAR.items():
        if kalit in nom or nom in kalit:
            return paket
    return None


def ilova_och(paket):
    return adb("shell", "monkey", "-p", paket, "-c", "android.intent.category.LAUNCHER",
               "1")[0] == 0


def tugma(keycode):
    adb("shell", "input", "keyevent", keycode)


def matn_yoz(matn):
    """Telefonga matn yozadi (bo'sh joy %s bilan almashtiriladi)."""
    xavfsiz = matn.replace(" ", "%s")
    adb("shell", "input", "text", xavfsiz)


def tap(x, y):
    adb("shell", "input", "tap", str(x), str(y))


def surish(x1, y1, x2, y2, ms=300):
    adb("shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(ms))


# ---------- EKRAN VA FAYLLAR ----------
def ekran_rasm(yol):
    """Telefon ekranini rasmga oladi va faylga saqlaydi. Muvaffaqiyat -> True."""
    kod, malumot = adb("exec-out", "screencap", "-p", ikkilik=True, timeout=30)
    if kod == 0 and malumot:
        with open(yol, "wb") as f:
            f.write(malumot)
        return True
    return False


def rasmlar_royxati(papka="/sdcard/DCIM/Camera"):
    """Telefondagi rasm/videolar ro'yxati (eng yangisi oxirida)."""
    kod, chiqish = adb("shell", "ls", papka)
    if kod != 0:
        return []
    return [q.strip() for q in chiqish.splitlines() if q.strip() and "No such" not in q]


def fayllarni_olib_kel(masofa, mahalliy_papka):
    """Telefondan fayl(lar)ni kompyuterga ko'chiradi (adb pull)."""
    os.makedirs(mahalliy_papka, exist_ok=True)
    kod, chiqish = adb("pull", masofa, mahalliy_papka, timeout=600)
    return kod == 0, chiqish


def faylni_yubor(mahalliy, masofa="/sdcard/Download/"):
    """Kompyuterdagi faylni telefonga yuboradi (adb push)."""
    kod, chiqish = adb("push", mahalliy, masofa, timeout=600)
    return kod == 0, chiqish


# ---------- Wi-Fi ULANISH ----------
def wifi_ulan(ip_port):
    """Wi-Fi orqali ulanadi (masalan '192.168.1.5:5555'). (muvaffaqiyat, xabar)."""
    kod, chiqish = adb("connect", ip_port, timeout=20)
    return kod == 0 and "connected" in chiqish.lower(), chiqish
