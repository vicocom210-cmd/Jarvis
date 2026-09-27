"""
Kompyuter bilan ishlaydigan yordamchi funksiyalar (Windows):
USB'dan nusxa olish, keshni tozalash, virus tekshiruvi, ilovalarni ochish.

Bu fayl gapirmaydi va tinglamaydi — faqat ishni bajarib, natijani qaytaradi.
Gapirish va tasdiq so'rash jarvis.py ichida.
"""
import datetime
import difflib
import os
import shutil
import stat
import string
import subprocess
import tempfile
import time

WINDOWS = os.name == "nt"
KONSOLSIZ = getattr(subprocess, "CREATE_NO_WINDOW", 0)    # qora oyna ochilmasin


def hajm_matn(bayt):
    """1536000 -> '1.5 megabayt'"""
    if bayt >= 1024 ** 3:
        return f"{bayt / 1024 ** 3:.1f} gigabayt"
    return f"{bayt / 1024 ** 2:.1f} megabayt"


def papka_hajmi(yol):
    jami = 0
    for ildiz, _, fayllar in os.walk(yol):
        for f in fayllar:
            try:
                jami += os.path.getsize(os.path.join(ildiz, f))
            except OSError:
                pass
    return jami


# ---------- USB FLESHKA ----------
def usb_disklar():
    """Kompyuterga ulangan fleshkalar: ['E:\\', 'F:\\']"""
    if not WINDOWS:
        return []
    import ctypes
    k32 = ctypes.windll.kernel32
    k32.SetErrorMode(1)                     # bo'sh kartrider uchun xato oynasi chiqmasin
    belgilar = k32.GetLogicalDrives()
    disklar = []
    for i, harf in enumerate(string.ascii_uppercase):
        yol = f"{harf}:\\"
        # 2 = DRIVE_REMOVABLE (olinadigan disk, ya'ni fleshka)
        if belgilar & (1 << i) and k32.GetDriveTypeW(yol) == 2 and os.path.exists(yol):
            disklar.append(yol)
    return disklar


def desktop_yoli():
    """Ish stoli papkasi (OneDrive'ga ko'chirilgan bo'lsa ham to'g'ri topadi)."""
    if WINDOWS:
        import ctypes
        joy = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, joy) == 0:
            return joy.value
    return os.path.join(os.path.expanduser("~"), "Desktop")


def usb_nusxa_papkasi():
    vaqt = datetime.datetime.now().strftime("%Y-%m-%d %H-%M")
    return os.path.join(desktop_yoli(), f"USB nusxa {vaqt}")


KERAKSIZ = shutil.ignore_patterns("System Volume Information", "$RECYCLE.BIN", "$Recycle.Bin")


def usb_nusxala(disklar, manzil):
    """Fleshkadagi hamma narsani manzilga NUSXALAYDI (fleshkadan hech narsa o'chmaydi).
    Ko'chmay qolgan fayllar sonini qaytaradi."""
    xatolar = 0
    for disk in disklar:
        joy = manzil if len(disklar) == 1 else os.path.join(manzil, f"Disk {disk[0]}")
        try:
            shutil.copytree(disk, joy, ignore=KERAKSIZ, dirs_exist_ok=True)
        except shutil.Error as xato:          # ba'zi fayllar ko'chmadi, qolgani ko'chdi
            xatolar += len(xato.args[0])
        except OSError:
            xatolar += 1
    return xatolar


# ---------- KESHNI TOZALASH ----------
def kesh_papkalari():
    """Faqat Windows'ning vaqtinchalik (Temp) papkalari. Boshqa joyga tegmaymiz."""
    papkalar = [tempfile.gettempdir(),
                os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Temp")]
    natija = []
    for p in papkalar:
        p = os.path.abspath(p)
        # Xavfsizlik: papka nomi aynan "Temp" bo'lishi shart
        if os.path.basename(p).lower() == "temp" and os.path.isdir(p) and p not in natija:
            natija.append(p)
    return natija


def _yorliq_papkami(yol):
    """Yorliq/junction bo'lsa, ichiga kirmaymiz (boshqa papkaga olib ketishi mumkin)."""
    try:
        s = os.lstat(yol)
    except OSError:
        return True
    return stat.S_ISLNK(s.st_mode) or bool(getattr(s, "st_file_attributes", 0) & 0x400)


def _kerakli_fayl(nom):
    # _MEI... — exe fayllar (keyinchalik Jarvis.exe ham) ishlayotganda shu yerda turadi
    return nom.startswith(("_MEI", "jarvis_"))


def kesh_fayllari():
    """O'chirsa bo'ladigan vaqtinchalik fayllar: [(yol, hajm), ...].
    Oxirgi 1 soatda o'zgargan fayllarga tegmaymiz — ular hozir ishlatilayotgan bo'lishi mumkin."""
    chegara = time.time() - 3600
    topildi = []
    for papka in kesh_papkalari():
        for ildiz, ichki, fayllar in os.walk(papka):
            ichki[:] = [d for d in ichki
                        if not _kerakli_fayl(d) and not _yorliq_papkami(os.path.join(ildiz, d))]
            for f in fayllar:
                if _kerakli_fayl(f):
                    continue
                yol = os.path.join(ildiz, f)
                try:
                    s = os.lstat(yol)
                except OSError:
                    continue
                if s.st_mtime < chegara:
                    topildi.append((yol, s.st_size))
    return topildi


def kesh_ochir(fayllar):
    """(o'chirilgan fayllar soni, bo'shagan joy baytda) qaytaradi."""
    soni, bayt = 0, 0
    for yol, hajm in fayllar:
        try:
            os.remove(yol)
            soni += 1
            bayt += hajm
        except OSError:
            pass                                 # band fayl — o'tkazib yuboramiz
    for papka in kesh_papkalari():               # bo'shab qolgan papkalarni ham olib tashlaymiz
        for ildiz, ichki, _ in os.walk(papka, topdown=False):
            for d in ichki:
                yol = os.path.join(ildiz, d)
                if _kerakli_fayl(d) or _yorliq_papkami(yol):
                    continue
                try:
                    os.rmdir(yol)                # faqat bo'sh papka o'chadi
                except OSError:
                    pass
    return soni, bayt


# ---------- VIRUS TEKSHIRUVI (Windows Defender) ----------
def defender_yoli():
    """Windows'ning o'z antivirusi — MpCmdRun.exe qayerda?"""
    nomzodlar = []
    platforma = os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"),
                             "Microsoft", "Windows Defender", "Platform")
    if os.path.isdir(platforma):
        for versiya in sorted(os.listdir(platforma), reverse=True):   # eng yangisi birinchi
            nomzodlar.append(os.path.join(platforma, versiya, "MpCmdRun.exe"))
    # 32-bitli Python'da %ProgramFiles% "Program Files (x86)" bo'ladi, shuning uchun ProgramW6432
    dasturlar = os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles", r"C:\Program Files")
    nomzodlar.append(os.path.join(dasturlar, "Windows Defender", "MpCmdRun.exe"))
    for yol in nomzodlar:
        if os.path.isfile(yol):
            return yol
    return None


def virus_tekshir(yol=None):
    """yol=None — butun kompyuterni tezkor tekshirish, yol='E:\\' — faqat shu joyni.
    Natija: 'toza', 'topildi' yoki 'xato'."""
    exe = defender_yoli()
    if not exe:
        return "xato"
    if yol:
        buyruq = [exe, "-Scan", "-ScanType", "3", "-File", yol]
    else:
        buyruq = [exe, "-Scan", "-ScanType", "1"]          # 1 = tezkor tekshiruv
    try:
        natija = subprocess.run(buyruq, capture_output=True, creationflags=KONSOLSIZ,
                                timeout=2 * 3600)
    except (OSError, subprocess.TimeoutExpired):
        return "xato"
    if natija.returncode == 0:
        return "toza"
    if natija.returncode == 2:
        return "topildi"
    return "xato"


def windows_xavfsizlik_och():
    if WINDOWS:
        os.startfile("windowsdefender://threat")


# ---------- ILOVALARNI OCHISH ----------
ILOVA_SINONIMLAR = {
    "vord": "word", "ворд": "word", "eksel": "excel", "ексел": "excel", "эксел": "excel",
    "paverpoint": "powerpoint", "pauerpoint": "powerpoint", "fotoshop": "photoshop",
    "фотошоп": "photoshop", "xrom": "chrome", "krom": "chrome", "vayber": "viber",
    "skayp": "skype", "zum": "zoom", "stim": "steam", "diskord": "discord",
    "vatsap": "whatsapp", "votsap": "whatsapp", "spotifay": "spotify", "vlc": "vlc",
}
# O'chirish (uninstall) yorliqlarini hech qachon ochmaymiz
TAQIQLANGAN = ("uninstall", "удал", "o'chir", "deinstall", "remove")
_ilovalar_xotira = None


def ilovalar():
    """Start menyu va ish stolidagi yorliqlar: {'microsoft word': 'C:\\...\\Word.lnk', ...}"""
    global _ilovalar_xotira
    if _ilovalar_xotira is not None:
        return _ilovalar_xotira
    papkalar = [
        os.path.join(os.environ.get("ProgramData", ""), r"Microsoft\Windows\Start Menu\Programs"),
        os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
        desktop_yoli(),
        os.path.join(os.environ.get("PUBLIC", ""), "Desktop"),
    ]
    topildi = {}
    for papka in papkalar:
        if not os.path.isdir(papka):
            continue
        for ildiz, _, fayllar in os.walk(papka):
            for f in fayllar:
                nom, kengaytma = os.path.splitext(f)
                nom = nom.lower()
                if kengaytma.lower() in (".lnk", ".url") and not any(t in nom for t in TAQIQLANGAN):
                    topildi.setdefault(nom, os.path.join(ildiz, f))
    _ilovalar_xotira = topildi
    return topildi


def ilova_top(nom):
    """'vord' -> ('microsoft word', 'C:\\...\\Word.lnk') yoki None"""
    nom = " ".join(ILOVA_SINONIMLAR.get(s, s) for s in nom.split())
    if not nom:
        return None
    royxat = ilovalar()
    ichida = [n for n in royxat if nom in n]
    if ichida:
        eng_yaxshi = min(ichida, key=len)          # "word" -> "microsoft word", "word 2016" emas
        return eng_yaxshi, royxat[eng_yaxshi]
    oxshash = difflib.get_close_matches(nom, list(royxat), n=1, cutoff=0.6)
    if oxshash:
        return oxshash[0], royxat[oxshash[0]]
    return None


def ilova_och(yol):
    os.startfile(yol)


# ---------- FAYL QIDIRISH ----------
# Bu papkalar ichiga kirmaymiz: tizim fayllari, juda katta va foydasiz joylar
QIDIRMASLIK = {"appdata", "windows", "program files", "program files (x86)", "programdata",
               "$recycle.bin", "system volume information", "node_modules", ".git",
               "__pycache__", ".venv", "venv", "recovery", "$windows.~bt", "msocache"}


def qidiruv_joylari():
    """Foydalanuvchi papkasi (C:\\Users\\Ism) va boshqa disklar (D:, E: ...)."""
    joylar = [os.path.expanduser("~")]
    if WINDOWS:
        import ctypes
        k32 = ctypes.windll.kernel32
        belgilar = k32.GetLogicalDrives()
        for i, harf in enumerate(string.ascii_uppercase):
            yol = f"{harf}:\\"
            # 3 = oddiy disk, 2 = fleshka. C: diskni butunlay qidirmaymiz — faqat foydalanuvchi papkasi
            if harf != "C" and belgilar & (1 << i) and k32.GetDriveTypeW(yol) in (2, 3):
                joylar.append(yol)
    return joylar


def _mos_keladimi(qidiruv, nom):
    asos = os.path.splitext(nom)[0].lower()
    if qidiruv in asos:
        return True
    if abs(len(asos) - len(qidiruv)) <= 3:                  # "hisobod" -> "hisobot"
        return difflib.SequenceMatcher(None, qidiruv, asos).ratio() >= 0.8
    return False


def fayl_qidir(nom, vaqt_chegarasi=30, max_natija=30):
    """Nomi o'xshash fayl va papkalarni topadi. Eng mos keladigani birinchi turadi."""
    qidiruv = nom.lower().strip()
    if len(qidiruv) < 2:
        return []
    tugash = time.time() + vaqt_chegarasi
    topildi = []
    for joy in qidiruv_joylari():
        if len(topildi) >= max_natija or time.time() > tugash:
            break
        for ildiz, ichki, fayllar in os.walk(joy):
            ichki[:] = [d for d in ichki
                        if d.lower() not in QIDIRMASLIK and not d.startswith((".", "$"))]
            for nom_ in ichki + fayllar:
                if _mos_keladimi(qidiruv, nom_):
                    topildi.append(os.path.join(ildiz, nom_))
            if len(topildi) >= max_natija or time.time() > tugash:
                break

    def tartib(yol):
        asos = os.path.splitext(os.path.basename(yol))[0].lower()
        return (asos != qidiruv, qidiruv not in asos, len(yol))
    return sorted(topildi, key=tartib)


PAPKA_NOMLARI = {"desktop": "ish stolida", "documents": "Hujjatlar papkasida",
                 "downloads": "Yuklanmalar papkasida", "pictures": "Rasmlar papkasida",
                 "music": "Musiqa papkasida", "videos": "Videolar papkasida"}


def joy_nomi(yol):
    """'C:\\Users\\VICO\\Downloads\\a.pdf' -> 'Yuklanmalar papkasida'"""
    papka = os.path.dirname(yol)
    if os.path.normcase(papka) == os.path.normcase(desktop_yoli()):
        return "ish stolida"
    nomi = os.path.basename(papka)
    if nomi.lower() in PAPKA_NOMLARI:
        return PAPKA_NOMLARI[nomi.lower()]
    disk = os.path.splitdrive(yol)[0].rstrip(":")
    if not nomi:
        return f"{disk} diskida"
    return f"{nomi} papkasida" + (f", {disk} diskida" if disk else "")


def papkada_korsat(yol):
    """Explorer'ni ochib, faylni belgilab ko'rsatadi."""
    if WINDOWS:
        subprocess.Popen(f'explorer /select,"{yol}"')
