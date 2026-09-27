"""
Kompyuter bilan ishlaydigan yordamchi funksiyalar (Windows):
USB'dan nusxa olish, keshni tozalash, virus tekshiruvi, ilovalarni ochish.

Bu fayl gapirmaydi va tinglamaydi — faqat ishni bajarib, natijani qaytaradi.
Gapirish va tasdiq so'rash jarvis.py ichida.
"""
import datetime
import difflib
import os
import re
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


def qisqartma(nom):
    """'Counter-Strike 1.6' -> 'cs 1.6' (so'zlarning bosh harflari + raqamlar)."""
    bosh, raqamlar = "", []
    for soz in re.split(r"[\s\-_]+", nom.lower()):
        if not soz:
            continue
        if soz[0].isdigit():
            raqamlar.append(soz)
        else:
            bosh += soz[0]
    return " ".join([bosh] + raqamlar).strip()


def _asos_nom(nom):
    """Kengaytmasiz nom. '1.6' dagi '.6' kengaytma emas — raqam bo'lsa kesmaymiz."""
    asos, kengaytma = os.path.splitext(nom)
    if not kengaytma or kengaytma[1:].isdigit():
        return nom.lower()
    return asos.lower()


def _mos_keladimi(qidiruv, nom):
    asos = _asos_nom(nom)
    if qidiruv in asos:
        return True
    if qidiruv == qisqartma(asos) or qidiruv.replace(" ", "") == qisqartma(asos).replace(" ", ""):
        return True                                         # "cs 1.6" -> "Counter-Strike 1.6"
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
        asos = _asos_nom(os.path.basename(yol))
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


# ---------- YO'LNI TUSHUNISH: "C diskdagi games papkasidan cs 1.6 ni" ----------
DISK_RE = re.compile(r"(?:^|\s)([a-z])\s*(?:disk|диск)")
FAYL_SOZLARI = ("fayl", "file", "papka", "folder", "файл", "папк")
YOL_ORTIQCHA = ("menga", "mening", "kompyuter", "disk", "диск", "nusxa", "olib", "tashla",
                "yubor", "jo'nat", "telegram", "iltimos", "ichida", "ichidan", "jarvis",
                "hamma", "barcha", "butun", "degan", "nomli")
YOL_ANIQ = {"ber", "bering", "ni", "u", "bu", "va", "ham", "shu", "o'sha", "menga"}


def _yol_nomi(sozlar, disk_harfi):
    """So'zlar bo'lagidan papka/fayl nomini ajratadi (keraksiz so'zlarsiz)."""
    qolgan = []
    for s in sozlar:
        s = s.strip('"\'«»“”,.!?')
        if not s or s in YOL_ANIQ or s.startswith(YOL_ORTIQCHA) or s == disk_harfi:
            continue
        for qoshimcha in ("ning", "dagi", "idagi", "dan", "ni"):
            if len(s) > len(qoshimcha) + 2 and s.endswith(qoshimcha):
                s = s[:-len(qoshimcha)]
                break
        qolgan.append(s)
    return " ".join(qolgan).strip()


def yol_qismlari(gap):
    """'c diskdagi games filesidan cs 1.6 fileni tashla' -> ('C:\\', ['games', 'cs 1.6'])"""
    gap = gap.lower()
    m = DISK_RE.search(gap)
    disk = m.group(1).upper() + ":\\" if m else None
    harf = m.group(1) if m else None
    nomlar, bufer = [], []
    for soz in gap.split():
        if soz.strip('"\'«»“”,.').startswith(FAYL_SOZLARI):
            nom = _yol_nomi(bufer, harf)
            if nom:
                nomlar.append(nom)
            bufer = []
        else:
            bufer.append(soz)
    oxirgi = _yol_nomi(bufer, harf)
    if oxirgi:
        nomlar.append(oxirgi)
    return disk, nomlar


def _ichidan_top(ildiz, nom, faqat_papka, vaqt_chegarasi=15):
    """ildiz ichidan nom bo'yicha papka/fayl topadi. Avval bevosita ichidagilar, keyin chuqurroq."""
    if ildiz is None:
        for yol in fayl_qidir(nom):
            if not faqat_papka or os.path.isdir(yol):
                return yol
        return None
    qidiruv = nom.lower()
    try:
        ichidagilar = os.listdir(ildiz)
    except OSError:
        return None
    mos = [n for n in ichidagilar if _mos_keladimi(qidiruv, n)
           and (not faqat_papka or os.path.isdir(os.path.join(ildiz, n)))]
    if mos:
        mos.sort(key=lambda n: (os.path.splitext(n)[0].lower() != qidiruv, len(n)))
        return os.path.join(ildiz, mos[0])
    tugash = time.time() + vaqt_chegarasi
    for joriy, ichki, fayllar in os.walk(ildiz):
        chuqurlik = joriy[len(ildiz):].count(os.sep)
        ichki[:] = [d for d in ichki if d.lower() not in QIDIRMASLIK
                    and not d.startswith((".", "$"))] if chuqurlik < 4 else []
        for n in ichki + ([] if faqat_papka else fayllar):
            if _mos_keladimi(qidiruv, n):
                return os.path.join(joriy, n)
        if time.time() > tugash:
            break
    return None


def yol_top(disk, nomlar):
    """(topilgan_yol, None) yoki (None, topilmagan_nom)."""
    joy = disk
    if joy and not os.path.isdir(joy):
        return None, disk
    for i, nom in enumerate(nomlar):
        topildi = _ichidan_top(joy, nom, faqat_papka=i < len(nomlar) - 1)
        if not topildi:
            return None, nom
        joy = topildi
    return joy, None


def papkani_zip(papka):
    """Papkani vaqtinchalik ZIP faylga aylantiradi va yo'lini qaytaradi."""
    asos = os.path.join(tempfile.gettempdir(), "jarvis_" + os.path.basename(papka.rstrip("\\/")))
    return shutil.make_archive(asos, "zip", root_dir=os.path.dirname(papka.rstrip("\\/")),
                               base_dir=os.path.basename(papka.rstrip("\\/")))


# ---------- TIZIM: o'chirish, qayta yuklash, qulflash ----------
def kompyuterni_ochir(soniya=15):
    subprocess.run(f"shutdown /s /t {soniya}", shell=True, creationflags=KONSOLSIZ)


def kompyuterni_restart(soniya=10):
    subprocess.run(f"shutdown /r /t {soniya}", shell=True, creationflags=KONSOLSIZ)


def ochirishni_bekor():
    subprocess.run("shutdown /a", shell=True, creationflags=KONSOLSIZ)


def kompyuterni_qulfla():
    if WINDOWS:
        subprocess.run("rundll32.exe user32.dll,LockWorkStation", shell=True, creationflags=KONSOLSIZ)


def uyqu_rejimi():
    if WINDOWS:
        subprocess.run("rundll32.exe powrprof.dll,SetSuspendState 0,1,0", shell=True,
                       creationflags=KONSOLSIZ)
