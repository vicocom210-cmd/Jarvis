"""
O'zbekcha JARVIS — Windows uchun ovozli yordamchi (3-versiya)
Ishga tushirish:  jarvis.bat  (yoki PyCharm'dagi yashil ▶ tugma)
Chaqirish:  "Jarvis" deng (yoki "Jarvis, youtubeni och" deb bitta gapda ayting).
Oynaning pastiga yozib ham buyruq bersa bo'ladi.

Tuzilishi (3 ta thread):
  asosiy thread  — oyna va shar animatsiyasi (interfeys.py)
  mikrofon       — doim tinglaydi, eshitganini kirish_navbat'ga qo'yadi
  miya           — kirish_navbat'dan gap olib, buyruqni bajaradi (bajar)
"""
import asyncio
import audioop
import datetime
import difflib
import io
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import webbrowser

import edge_tts
import pyautogui
import pygame
import pyperclip
import speech_recognition as sr

import bilim
import boshqaruv
import kompyuter
import sozlamalar
import telegram_bot
from tarjima import tarjima

# Ovoz, til, rang va ism — oynadagi ⚙ menyusidan yoki ovoz bilan o'zgartiriladi
SOZ = sozlamalar.yukla()
ISM = SOZ["ism"]                 # Jarvis sizni shunday chaqiradi
SUHBAT_VAQTI = 8                 # buyruqdan keyin shuncha soniya "Jarvis" demasdan gapirsa bo'ladi

pygame.mixer.init()
tanib = sr.Recognizer()
AUDIO_FAYL = os.path.join(tempfile.gettempdir(), "jarvis_javob.mp3")

# Thread'lar orasidagi navbatlar
ui_navbat = queue.Queue()        # miya -> oyna: holat, matnlar, ovoz balandligi
kirish_navbat = queue.Queue()    # mikrofon va oyna -> miya: ("ovoz"/"yozuv", matn, vaqt)
yozib_ber_navbat = queue.Queue() # Shazam -> mikrofon: "10 soniya yozib ber"


def holat(nom):
    """Shar ko'rinishini o'zgartiradi: kutish, tinglash, o'ylash, gapirish, shazam."""
    global joriy_holat
    joriy_holat = nom
    ui_navbat.put(("holat", nom))


joriy_holat = "kutish"


# ---------- 1. GAPIRISH ----------
ovoz_qulfi = threading.Lock()     # ikki ish bir vaqtda gapirmoqchi bo'lsa, navbat bilan gapiradi
gapiryapti = threading.Event()    # Jarvis hozir gapiryaptimi
uzildi = threading.Event()        # siz Jarvisning gapini bo'ldingiz — u darhol jim bo'ladi
gap_tugadi = 0.0                  # Jarvis oxirgi marta qachon gapirib bo'ldi
hozirgi_gap = ""                  # Jarvis hozir aytayotgan matn (o'z aks-sadosini tanish uchun)
uzish_mumkin = True               # False — bu gapni bo'lib bo'lmaydi (masalan, Shazam paytida)
_ovoz_xotira = {}                 # qisqa gaplar ovozi xotirada — "Labbay" darhol aytiladi


def til():
    return SOZ["til"]


def ovoz_nomi():
    return sozlamalar.TILLAR[til()][SOZ["ovoz"]]


def gapir(matn, tarjima_qil=True, ovoz=None, uzilmas=False):
    """Jarvis ichida hamma javob o'zbekcha yoziladi; boshqa til tanlangan bo'lsa,
    gapirishdan oldin o'sha tilga tarjima qilinadi.
    uzilmas=True — bu gapni bo'lib bo'lmaydi."""
    global hozirgi_gap, uzish_mumkin
    if tarjima_qil and til() != "uz":
        matn = tarjima(matn, "uz", til())
    print(f"Jarvis: {matn}")
    ui_navbat.put(("jarvis", matn))
    if javob_telegramga:
        if bot:
            bot.yoz(matn)           # buyruq telefondan keldi — javob ham telefonga
        return                      # kompyuterda ovoz chiqarmaymiz
    if uzildi.is_set():
        return                  # gapini bo'ldingiz — javobning qolganini ovoz chiqarib aytmaydi
    with ovoz_qulfi:
        oldingi = joriy_holat
        hozirgi_gap, uzish_mumkin = matn, not uzilmas
        gapiryapti.set()
        try:
            _gapir(matn, ovoz)
        finally:
            global gap_tugadi
            gap_tugadi = time.time()
            gapiryapti.clear()
            holat(oldingi)


def ovoz_balandliklari(tovush):
    """Har 1/30 soniyadagi ovoz balandligi (0..1) — shar shunga qarab pulsatsiya qiladi."""
    chastota, _, kanallar = pygame.mixer.get_init()
    qadam = chastota // 30 * kanallar * 2          # 16-bit = 2 bayt
    xom = tovush.get_raw()
    return [min(1.0, audioop.rms(xom[i:i + qadam], 2) / 7000)
            for i in range(0, len(xom), qadam)]


def _ovoz_yasa(matn, ovoz):
    """Matnni ovozga aylantiradi. Qisqa gaplar xotirada saqlanadi — keyingi safar darhol."""
    kalit = (matn, ovoz)
    if kalit in _ovoz_xotira:
        return _ovoz_xotira[kalit]
    asyncio.run(edge_tts.Communicate(matn, ovoz).save(AUDIO_FAYL))
    with open(AUDIO_FAYL, "rb") as f:
        malumot = f.read()
    if len(matn) <= 60 and len(_ovoz_xotira) < 100:
        _ovoz_xotira[kalit] = malumot
    return malumot


def _gapir(matn, ovoz=None):
    try:
        malumot = _ovoz_yasa(matn, ovoz or ovoz_nomi())
        try:
            tovush = pygame.mixer.Sound(file=io.BytesIO(malumot))
        except Exception:
            tovush = pygame.mixer.Sound(AUDIO_FAYL)
        try:
            ui_navbat.put(("ovoz", ovoz_balandliklari(tovush), time.time()))
        except Exception:
            pass
        holat("gapirish")
        kanal = tovush.play()
        while kanal.get_busy():
            if uzildi.is_set():             # gapimni bo'ldingiz — darhol jim bo'laman
                kanal.stop()
                break
            time.sleep(0.03)
    except Exception as xato:
        print(f"(Ovoz chiqmadi: {xato})")


# ---------- 2. ESHITISH ----------
def normallashtir(matn):
    for belgi in "‘’ʻʼ`":
        matn = matn.replace(belgi, "'")
    return matn.lower().strip()


def mikrofon_ishi():
    """Alohida thread: doim tinglaydi va eshitganini kirish_navbat'ga qo'yadi."""
    try:
        mikrofon = sr.Microphone()
    except Exception as xato:
        print(f"(Mikrofon topilmadi: {xato}) — pastdagi maydonga yozib buyruq bering.")
        return
    tanib.pause_threshold = 0.6         # gap tugaganini tezroq sezadi (standart 0.8)
    tanib.non_speaking_duration = 0.4
    with mikrofon as mic:
        tanib.adjust_for_ambient_noise(mic, duration=1)
        while True:
            # Shazam so'rasa — musiqani yozib beramiz
            try:
                soniya, javob = yozib_ber_navbat.get_nowait()
                javob.put(tanib.record(mic, duration=soniya))
                continue
            except queue.Empty:
                pass
            if gapiryapti.is_set() and not uzish_mumkin:
                time.sleep(0.1)
                continue
            boshlandi = time.time()
            # Jarvis gapirayotganda ham tinglaymiz — shunda uning gapini bo'lish mumkin
            gapirganda = gapiryapti.is_set()
            try:
                audio = tanib.listen(mic, timeout=3, phrase_time_limit=4 if gapirganda else 7)
            except sr.WaitTimeoutError:
                continue
            except Exception as xato:           # mikrofon uzilsa ham thread to'xtamasin
                print(f"(Mikrofon xatosi: {xato})")
                time.sleep(1)
                continue
            gapirganda = gapirganda or gapiryapti.is_set() or gap_tugadi > boshlandi
            if gapirganda and not uzish_mumkin:
                continue
            threading.Thread(target=matnga_aylantir, args=(audio, gapirganda, hozirgi_gap),
                             daemon=True).start()


def aks_sadomi(eshitilgan, jarvis_gapi):
    """Mikrofon Jarvisning o'z ovozini (karnaydan) eshitdimi?
    Eshitilgan so'zlarning yarmidan ko'pi Jarvis aytgan gapda bo'lsa — ha."""
    sozlar = normallashtir(eshitilgan).split()
    jarvis_sozlari = normallashtir(jarvis_gapi).replace(",", " ").replace(".", " ").split()
    if not sozlar:
        return True
    mos = sum(1 for s in sozlar
              if s in jarvis_sozlari or difflib.get_close_matches(s, jarvis_sozlari, 1, 0.75))
    return mos / len(sozlar) >= 0.5


def matnga_aylantir(audio, gapirganda=False, jarvis_gapi=""):
    try:
        matn = tanib.recognize_google(audio, language=sozlamalar.TILLAR[til()]["google"])
    except sr.UnknownValueError:
        return
    except sr.RequestError:
        print("(Internet bilan muammo bor)")
        return
    if gapirganda:
        if aks_sadomi(matn, jarvis_gapi):
            return                          # o'z ovozim — e'tibor bermayman
        print(f"✋ Gapimni bo'ldingiz: {matn}")
        uzildi.set()                        # Jarvis darhol jim bo'ladi
        kirish_navbat.put(("uzish", normallashtir(matn), time.time()))
        return
    print(f"Eshitildi: {matn}")
    kirish_navbat.put(("ovoz", normallashtir(matn), time.time()))


def keyingi_gap(kutish):
    """Navbatdan keyingi gapni oladi (ovoz yoki yozuv). Jarvis gapirib bo'lishidan
    oldin eshitilgan eski gaplar tashlab yuboriladi."""
    tugash = time.time() + kutish
    while True:
        qoldi = tugash - time.time()
        if qoldi <= 0:
            return None
        try:
            manba, matn, vaqt = kirish_navbat.get(timeout=qoldi)
        except queue.Empty:
            return None
        if manba == "sozlama":                  # oynadagi menyuda tanlandi
            sozlama_ozgartir(*matn)
            continue
        if manba == "ovoz_sinov":               # menyuda "Eshitib ko'rish" bosildi
            gapir(f"Salom, {ISM}! Men shu ovozda gapiraman.",
                  ovoz=sozlamalar.TILLAR[til()][matn])
            continue
        if manba in ("yozuv", "telegram"):
            matn = normallashtir(matn)
        if vaqt >= gap_tugadi or manba == "uzish":
            uzildi.clear()                      # yangi gap keldi — Jarvis yana gapira oladi
            return manba, matn


def eshit(kutish=8):
    """Savolga javobni kutadi (masalan, "ha" yoki "yo'q"). Bo'sh qator — javob bo'lmadi."""
    oldingi = joriy_holat
    holat("tinglash")
    gap = keyingi_gap(kutish)
    holat(oldingi)
    if not gap:
        return ""
    ui_navbat.put(("siz", gap[1]))
    return ichki_tilga(gap[1])


def ichki_tilga(matn):
    """Boshqa tilda aytilgan gapni o'zbekchaga o'giradi (buyruqlar o'zbekcha tekshiriladi)."""
    if til() == "uz" or not matn:
        return matn
    # "auto" — tilni Google o'zi aniqlaydi: o'zbekcha aytilsa ham to'g'ri tushunadi
    return normallashtir(tarjima(matn, "auto", "uz"))


# ---------- 2.1. SOZLAMALAR ----------
SOZLAMA_JAVOBLARI = {
    "telegram_token": "Telegram bot ulanmoqda.",
    "telegram_egasi": "Telegram uzildi. Qayta ulash uchun yangi kod ekranda.",
    "ovoz": "Ovozim o'zgardi. Endi shunday gapiraman.",
    "til": "Til o'zgardi. Endi shu tilda gaplashamiz.",
    "rang": "Rangim o'zgardi.",
}


def sozlama_ozgartir(kalit, qiymat, ayt=True):
    global ISM
    SOZ[kalit] = qiymat
    sozlamalar.saqla(SOZ)
    ISM = SOZ["ism"]
    ui_navbat.put(("sozlamalar", dict(SOZ)))
    if ayt:
        gapir(f"Yaxshi, endi sizni {ISM} deb chaqiraman." if kalit == "ism"
              else SOZLAMA_JAVOBLARI[kalit])
        if kalit in ("telegram_token", "telegram_egasi"):
            telegram_ishga_tushir()             # yangi token yoki uzildi — bot qayta ulanadi


# ---------- 2.2. TELEGRAM BOT (telefondan boshqarish) ----------
oxirgi_manba = ""                 # hozirgi buyruq qayerdan keldi: ovoz, yozuv, telegram, uzish
bot = None                        # ishlab turgan Telegram bot
javob_telegramga = False          # hozirgi buyruq telefondan keldimi (javob ham o'sha yoqqa)


def telegram_holati(holat_, qiymat):
    ui_navbat.put(("telegram_holat", holat_, qiymat))
    if holat_ == "kod":
        ui_navbat.put(("jarvis", f"Telegram juftlash kodi: {qiymat}"))


def telegram_ishga_tushir():
    global bot
    if bot:
        bot.ishlasin = False                    # eski bot to'xtaydi
        bot = None
    token = SOZ.get("telegram_token", "").strip()
    if not token:
        ui_navbat.put(("telegram_holat", "yoq", ""))
        return
    bot = telegram_bot.Bot(
        token, SOZ.get("telegram_egasi", 0),
        xabar_keldi=lambda matn: kirish_navbat.put(("telegram", matn, time.time())),
        egasi_ozgardi=lambda egasi: sozlama_ozgartir("telegram_egasi", egasi, ayt=False),
        holat_ozgardi=telegram_holati,
        saqlash_papkasi=lambda: os.path.join(kompyuter.desktop_yoli(), "Telefondan"))
    threading.Thread(target=bot.ishla, daemon=True).start()


FAYL_TURLARI = {
    "rasm": ({".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".heic"},
             ("rasm", "foto", "surat", "photo", "фото"), "Pictures"),
    "video": ({".mp4", ".mov", ".avi", ".mkv", ".webm", ".3gp"}, ("video", "видео"), "Videos"),
    "musiqa": ({".mp3", ".wav", ".m4a", ".ogg", ".flac"}, ("musiqa", "qo'shiq", "audio"), "Music"),
    "hujjat": ({".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt"},
               ("hujjat", "dokument", "pdf", "word", "excel"), "Documents"),
}
PAPKA_SOZLARI = [(("yuklama", "yuklab ol", "zagruz", "download", "загруз"), "Downloads"),
                 (("ish stol", "desktop", "rabochi", "рабоч"), "Desktop"),
                 (("hujjatlar papka", "documents"), "Documents"),
                 (("rasmlar papka", "pictures"), "Pictures"),
                 (("videolar papka", "videos"), "Videos")]


def papka_yoli(nom):
    if nom == "Desktop":
        return kompyuter.desktop_yoli()
    return os.path.join(os.path.expanduser("~"), nom)


def telegramga_yubor(gap):
    """'yuklamalardagi rasmlarni tashla' -> Downloads'dagi rasmlarni Telegram'ga yuboradi."""
    if not bot or not bot.egasi:
        gapir("Telegram bot ulanmagan. Sozlamalarning Telefon bo'limida ulang.")
        return
    tur = next((t for t, (_, sozlar, _) in FAYL_TURLARI.items() if bor(gap, *sozlar)), None)
    papka = next((papka_yoli(p) for sozlar, p in PAPKA_SOZLARI if bor(gap, *sozlar)), None)
    disk, nomlar = kompyuter.yol_qismlari(gap)
    if tur:                                     # "rasmlar", "videolar" — nom emas, fayl turi
        nomlar = [n for n in nomlar if not bor(n, *FAYL_TURLARI[tur][1])]
    if papka is not None and not disk:          # "yuklamalardagi" — tanish papka, nom emas
        nomlar = []

    if disk or nomlar:
        # aniq yo'l: "C diskdagi games papkasidan cs 1.6 ni", "hisobot faylini"
        yol, topilmadi = kompyuter.yol_top(disk, nomlar) if nomlar else (disk, None)
        if not yol:
            gapir(f"{topilmadi} topilmadi." + (f" {disk} diskida qidirdim." if disk else ""))
            return
        if os.path.isfile(yol):
            gapir(f"{os.path.basename(yol)} ni yuboryapman.")
            fonda(_telegramga_yubor_fonda, [yol])
            return
        if not tur:                             # papkaning o'zi so'raldi — ZIP qilib yuboramiz
            papkani_yubor(yol)
            return
        papka = yol
    elif papka is None and tur:
        papka = papka_yoli(FAYL_TURLARI[tur][2])
    elif papka is None:
        gapir("Qaysi fayl yoki papkani yuboray? Masalan: yuklamalardagi rasmlarni tashla.")
        return

    kengaytmalar = FAYL_TURLARI[tur][0] if tur else None
    try:
        fayllar = [os.path.join(papka, f) for f in os.listdir(papka)
                   if os.path.isfile(os.path.join(papka, f))
                   and (not kengaytmalar or os.path.splitext(f)[1].lower() in kengaytmalar)]
    except OSError:
        fayllar = []
    fayllar.sort(key=os.path.getmtime, reverse=True)       # eng yangilari birinchi
    jami = len(fayllar)
    fayllar = fayllar[:20]
    if not fayllar:
        gapir(f"{os.path.basename(papka.rstrip(os.sep)) or papka} papkasida mos fayl topilmadi.")
        return
    if jami > len(fayllar):
        gapir(f"{jami} ta fayl topildi. Eng yangi {len(fayllar)} tasini yuboryapman.")
    else:
        gapir(f"{len(fayllar)} ta fayl yuboryapman.")
    fonda(_telegramga_yubor_fonda, fayllar)


def papkani_yubor(papka):
    """Papkani ZIP qilib yuboradi (Telegram botlari 50 MB gacha yubora oladi)."""
    nom = os.path.basename(papka.rstrip(os.sep)) or papka
    hajm = kompyuter.papka_hajmi(papka)
    if hajm > 3 * telegram_bot.MAX_FAYL:          # siqilganda ham 50 MB ga tushmaydi
        gapir(f"{nom} papkasi {kompyuter.hajm_matn(hajm)}. Telegram bot 50 megabaytdan "
              "katta faylni yubora olmaydi.")
        return
    gapir(f"{nom} papkasini ZIP qilib yuboryapman.")
    fonda(_papkani_yubor_fonda, papka, nom)


def _papkani_yubor_fonda(papka, nom):
    try:
        zip_yol = kompyuter.papkani_zip(papka)
    except OSError as xato:
        gapir(f"ZIP qilib bo'lmadi: {xato}")
        return
    if os.path.getsize(zip_yol) > telegram_bot.MAX_FAYL:
        gapir(f"{nom} ZIP qilingandan keyin ham {kompyuter.hajm_matn(os.path.getsize(zip_yol))}. "
              "Telegram bot 50 megabaytdan kattasini yubora olmaydi.")
    else:
        _telegramga_yubor_fonda([zip_yol])
    try:
        os.remove(zip_yol)
    except OSError:
        pass


def _telegramga_yubor_fonda(fayllar):
    yuborildi = sum(1 for yol in fayllar if bot and bot.fayl_yubor(yol))
    gapir(f"{yuborildi} ta fayl yuborildi." if yuborildi else "Fayllarni yuborib bo'lmadi.")


# ---------- 2.3. ILOVA ICHIDA ISHLASH ----------
BOS_SOZLARI = {"bos", "bosing", "bosgin", "bosib", "bosvor", "bosvoring", "bosing", "click",
               "klik", "нажми", "нажмите"}
OLDINGI_ORTIQCHA = {"jarvis", "menga", "iltimos", "o'sha", "osha", "shu", "ilovadagi",
                    "oynadagi", "dasturdagi", "ekrandagi", "o'yindagi", "ichidagi", "ga", "ni", "ning"}


def bosish_buyrugimi(gap):
    sozlar = gap.split()
    return any(s in BOS_SOZLARI for s in sozlar) and (bor(gap, "tugma", "knopka", "кнопк", "button")
                                                      or len(sozlar) <= 6)


def telegram_xabar_qismlari(gap):
    """'telegramdan "my bro" ga salom deb yoz' -> ('my bro', 'salom')
    'telegramda alisherga ertaga boraman deb yoz' -> ('alisher', 'ertaga boraman')"""
    sozlar = gap.split()
    ilova_prefikslari = ("telegram", "телеграм", "instagram", "инстаграм", "insta", "whatsapp",
                         "vatsap", "votsap", "ватсап", "messenger", "мессенджер", "vkontakte", "вк")
    boshi = next((i for i, s in enumerate(sozlar) if s.startswith(ilova_prefikslari)), -1)
    oxiri = len(sozlar) - 1 - sozlar[::-1].index("deb")
    orta = " ".join(sozlar[boshi + 1:oxiri]).strip()
    # ko'p bosqichli gapdagi ortiqcha so'zlar ("chromega kirib ... qidir va kirib chatga otib")
    filtr = {"kirib", "kir", "kirgin", "qidir", "qidirib", "qidirgin", "qidirib", "va", "keyin",
             "otib", "o'tib", "otgin", "chatga", "chat", "messagega", "message", "direct",
             "xabarga", "yozishma", "topib", "top", "ochib", "och", "so'ng", "unga", "shundan",
             "deb", "kirvol", "kir"}
    qoshtirnoq = re.match(r'["“«\']([^"”»\']+)["”»\']\s*(?:ga|ni|ning)?\s*(.*)$', orta)
    if qoshtirnoq:
        nom = qoshtirnoq.group(1).strip()
        xabar = [w for w in qoshtirnoq.group(2).split()
                 if not w.startswith(("guruh", "gurux", "kanal", "chat"))]
        return nom, " ".join(xabar)
    orta = [s for s in orta.split() if s not in filtr]
    # BIRINCHI "ga" — undan oldingisi kimga, keyingisi xabar
    for j, s in enumerate(orta):
        if s == "ga" and j > 0:                            # "my bro ga salom"
            return " ".join(orta[:j]).strip("\"'«»"), " ".join(orta[j + 1:]).strip()
        if s.endswith("ga") and len(s) > 3 and not s.endswith(("chatga", "messagega")):
            return " ".join(orta[:j] + [s[:-2]]).strip("\"'«»"), " ".join(orta[j + 1:]).strip()
    return None, None


def telegramda_yoz(gap):
    nom, xabar = telegram_xabar_qismlari(gap)
    if not nom or not xabar:
        gapir("Kimga va nima deb yozay? Masalan: telegramdan Alisherga salom deb yoz.")
        return
    for kalit, haqiqiy in TELEGRAM_NOMLAR.items():        # noto'g'ri eshitilgan nomlarni to'g'rilaymiz
        if kalit in nom:
            nom = haqiqiy
    # Ovoz bilan aytilgan bo'lsa — Google noto'g'ri eshitgan bo'lishi mumkin, so'rab olamiz
    if oxirgi_manba == "ovoz" and not tasdiqla(f"Telegramda {nom} ga {xabar} deb yozaymi?"):
        gapir("Bekor qilindi.")
        return
    jarvisni_yashir(10)                                  # klaviatura Telegram'ga borsin
    telegram_och()
    telegram_chat_och(nom)
    time.sleep(1.5)
    pyperclip.copy(xabar)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(1)
    gapir(f"{nom} ga yozildi: {xabar}")
    telegramga_ekran()                                   # telefonda natijani ko'rasiz
    ui_navbat.put(("korsat",))


# Brauzerda ochiladigan ilovalar: nomi -> (xabarlar sahifasi, tanish so'zlari)
WEB_ILOVALAR = {
    "instagram": ("https://www.instagram.com/direct/inbox/", ("instagram", "инстаграм", "insta", "ig")),
    "whatsapp": ("https://web.whatsapp.com/", ("whatsapp", "vatsap", "votsap", "ватсап")),
    "messenger": ("https://www.facebook.com/messages/", ("messenger", "мессенджер")),
    "vk": ("https://vk.com/im", ("vkontakte", "вконтакте", "вк")),
}
# Ilova ichida: qidiruv maydoni va xabar maydonini topish uchun kalit so'zlar
QIDIRUV_KALITLARI = ("search", "qidir", "поиск", "искать", "search input")
XABAR_KALITLARI = ("message", "xabar", "написать", "type a message", "сообщение", "yozing")


def ilova_xabar_qismlari(gap):
    """'instagramda alisher blog ga salom deb yoz' -> ('instagram', 'alisher blog', 'salom')"""
    sozlar = gap.split()
    ilova = None
    for nom, (_, sozlari) in WEB_ILOVALAR.items():
        if bor(gap, *sozlari):
            ilova = nom
            break
    if bor(gap, "telegram", "телеграм"):
        ilova = "telegram"
    # kimga va xabar — telegram bilan bir xil ajratish
    nom, xabar = telegram_xabar_qismlari(gap)
    return ilova, nom, xabar


def ilovada_yoz(gap):
    """Har qanday ilova/saytda kontaktga xabar yozadi (Instagram, WhatsApp va h.k.).
    Ochish, qidirish, kontaktni tanlash va yozish — ekrandagi yozuvlarni o'qib bajariladi."""
    ilova, nom, xabar = ilova_xabar_qismlari(gap)
    if ilova == "telegram":
        telegramda_yoz(gap)
        return
    if not ilova or not nom or not xabar:
        gapir("Qaysi ilovada, kimga va nima deb yozay? Masalan: "
              "instagramda Alisherga salom deb yoz.")
        return
    if oxirgi_manba == "ovoz" and not tasdiqla(
            f"{ilova} da {nom} ga {xabar} deb yozaymi?"):
        gapir("Bekor qilindi.")
        return
    url = WEB_ILOVALAR[ilova][0]
    gapir(f"{ilova} ochilmoqda. {nom} ni topib, xabar yozaman.")
    fonda(_ilovada_yoz_fonda, ilova, url, nom, xabar)


def _ilovada_yoz_fonda(ilova, url, nom, xabar):
    jarvisni_yashir(45)                          # butun jarayon davomida yashirin turadi
    webbrowser.open(url)
    time.sleep(9)                                # sahifa yuklanishini kutamiz
    # 1) qidiruvni ochamiz va kontakt nomini yozamiz
    if not boshqaruv.kalitlardan_bos(QIDIRUV_KALITLARI):
        pyautogui.hotkey("ctrl", "k")           # ba'zi saytlarda qidiruv shu tugma bilan ochiladi
    time.sleep(1)
    boshqaruv.matn_yoz(nom)
    time.sleep(3)                               # natijalar chiqishini kutamiz
    pyautogui.press("enter")                    # birinchi natijani ochamiz
    time.sleep(3)
    # 2) xabar maydonini topib, matnni yozamiz
    boshqaruv.kalitlardan_bos(XABAR_KALITLARI)
    time.sleep(0.5)
    boshqaruv.matn_yoz(xabar)
    time.sleep(0.4)
    pyautogui.press("enter")
    time.sleep(1)
    gapir(f"{ilova} da {nom} ga yozdim: {xabar}")
    telegramga_ekran()
    ui_navbat.put(("korsat",))


def ekranni_kuzat(soniya=120, oraliq=3):
    """Ekranni Telegram'ga jonli uzatadi: bitta rasmni har bir necha soniyada yangilaydi.
    'to'xta' desangiz to'xtaydi."""
    if not bot or not bot.egasi:
        gapir("Buning uchun avval Telegram botni ulang.")
        return
    gapir("Ekranni Telegram'ga jonli uzatyapman. To'xtatish uchun to'xta deng.")
    fonda(_ekranni_kuzat_fonda, soniya, oraliq)


def _ekranni_kuzat_fonda(soniya, oraliq):
    yol = os.path.join(tempfile.gettempdir(), "jarvis_jonli.png")
    try:
        pyautogui.screenshot(yol)
    except Exception:
        gapir("Ekran rasmini ololmadim. pillow kutubxonasini o'rnating.")
        return
    xabar_id = bot.rasm_yubor(yol, "🔴 Jonli ekran")
    if not xabar_id:
        gapir("Jonli uzatishni boshlolmadim.")
        return
    uzildi.clear()
    tugash = time.time() + soniya
    while time.time() < tugash and not uzildi.is_set():
        time.sleep(oraliq)
        try:
            pyautogui.screenshot(yol)
            bot.rasm_yangila(xabar_id, yol)
        except Exception:
            break
    bot.yoz("⏹ Jonli ekran to'xtadi.")


def tugma_nomi(gap):
    """'enter the game tugmasini bos' -> 'enter the game'"""
    sozlar = [s.strip('"\'«»“”,.') for s in gap.split()]
    for i, s in enumerate(sozlar):
        if s.startswith(("tugma", "knopka", "кнопк", "button")) or s in BOS_SOZLARI:
            sozlar = sozlar[:i]
            break
    sozlar = [s for s in sozlar if s not in OLDINGI_ORTIQCHA]
    if sozlar:                                      # "startni" -> "start", "playga" -> "play"
        for qoshimcha in ("ning", "ni", "ga"):
            if len(sozlar[-1]) > len(qoshimcha) + 2 and sozlar[-1].endswith(qoshimcha):
                sozlar[-1] = sozlar[-1][:-len(qoshimcha)]
                break
    return " ".join(sozlar).strip()


def jarvisni_yashir(soniya):
    """Jarvis oynasi bosiladigan tugmani yopib qolmasin — bir necha soniya yashirinadi."""
    ui_navbat.put(("yashir", soniya))
    time.sleep(0.5)


def telegramga_ekran():
    if javob_telegramga and bot:
        yol = os.path.join(tempfile.gettempdir(), "jarvis_ekran.png")
        try:
            pyautogui.screenshot(yol)
            bot.fayl_yubor(yol, "Ekran hozir shunday")
        except Exception:
            pass


def tugma_bos(gap):
    nom = tugma_nomi(gap)
    if not nom:
        gapir("Qaysi tugmani bosay? Masalan: enter the game tugmasini bos.")
        return
    jarvisni_yashir(6)
    natija = boshqaruv.tugmani_bos(nom)
    time.sleep(1)
    if natija:
        gapir(f"{nom} bosildi.")
    else:
        gapir(f"Ekranda {nom} degan tugmani topa olmadim.")
    telegramga_ekran()                              # telefonda nima bo'lganini ko'rasiz
    ui_navbat.put(("korsat",))


def matn_yozish(gap):
    """'salom dunyo deb yoz' -> faol maydonga 'salom dunyo' yozadi."""
    sozlar = gap.split()
    i = sozlar.index("deb")
    matn = " ".join(s for s in sozlar[:i] if s != "jarvis")
    if not matn:
        gapir("Nima deb yozay?")
        return
    jarvisni_yashir(3)
    boshqaruv.matn_yoz(matn)
    ui_navbat.put(("korsat",))
    gapir("Yozildi.")


def oynani_yop():
    if boshqaruv.faol_oyna_nomi() in ("", "Jarvis"):
        gapir("Avval yopiladigan oynani tanlang, keyin ayting.")
        return
    nom = boshqaruv.faol_oyna_nomi()
    if tasdiqla(f"{nom} oynasini yopaymi? Saqlanmagan narsalar yo'qolishi mumkin."):
        pyautogui.hotkey("alt", "f4")
        gapir("Yopildi.")
    else:
        gapir("Bekor qilindi.")


def kamera_rasmi():
    """Veb-kameradan surat olib, egasiga (Telegram yoki ish stoli) beradi.
    Egasi kompyuterida kim borligini ko'rishi uchun."""
    gapir("Kameradan surat olyapman.")
    yol = os.path.join(tempfile.gettempdir(), "jarvis_kamera.jpg")
    natija = kompyuter.kamera_rasm(yol)
    if natija == "kutubxona":
        gapir("Buning uchun opencv-python kutubxonasini o'rnating.")
        return
    if not natija:
        gapir("Kameradan surat ololmadim. Kamera boshqa dasturda ochiq bo'lishi mumkin.")
        return
    if javob_telegramga and bot:
        fonda(bot.fayl_yubor, yol, "Kamera surati")
        gapir("Kamera suratini yubordim.")
    else:
        manzil = os.path.join(kompyuter.desktop_yoli(),
                              datetime.datetime.now().strftime("Kamera %Y-%m-%d %H-%M-%S.jpg"))
        shutil.copy(yol, manzil)
        gapir("Kamera surati ish stoliga saqlandi.")


def ekran_rasmi():
    yol = os.path.join(tempfile.gettempdir(), "jarvis_ekran.png")
    try:
        pyautogui.screenshot(yol)
    except Exception as xato:
        print(f"(Ekran rasmi xatosi: {xato})")
        gapir("Ekran rasmini ololmadim. Buning uchun pillow kutubxonasini o'rnating.")
        return
    if javob_telegramga and bot:
        gapir("Ekran rasmini yuboryapman.")
        fonda(bot.fayl_yubor, yol, "Ekran rasmi")
    else:
        manzil = os.path.join(kompyuter.desktop_yoli(),
                              datetime.datetime.now().strftime("Ekran rasmi %Y-%m-%d %H-%M-%S.png"))
        shutil.copy(yol, manzil)
        gapir("Ekran rasmi ish stoliga saqlandi.")


TIL_SOZLARI = {"ru": ("rus", "русск"), "en": ("ingliz", "english", "англий"),
               "de": ("nemis", "german", "deutsch", "немец"), "uz": ("o'zbek", "uzbek", "узбек")}
RANG_SOZLARI = {"kok": ("ko'k", "moviy", "havorang"), "yashil": ("yashil",),
                "qizil": ("qizil",), "oltin": ("oltin", "sariq", "tilla"),
                "binafsha": ("binafsha", "siyoh"), "oq": ("oq ", "oqqa", "oppoq")}


def ism_ajrat(gap):
    """'mening ismim abdulloh' -> 'Abdulloh';  'meni ali deb chaqir' -> 'Ali'"""
    sozlar = gap.split()
    for i, s in enumerate(sozlar):
        if s.startswith("ismim") and i + 1 < len(sozlar):
            return " ".join(sozlar[i + 1:i + 3]).replace(" deb", "").title()
    if "deb" in sozlar:
        oldin = [s for s in sozlar[:sozlar.index("deb")] if s not in ("meni", "endi", "jarvis")]
        if oldin:
            return oldin[-1].title()
    return ""


def sozlama_buyrugi(b):
    """Ovoz bilan sozlash. Bajarilsa True qaytaradi."""
    if bor(b, "sozlama", "nastroyka", "настрой"):
        # "sozlamalarni yop", "sozlamalardan chiq" — yopish; qolgani — ochish
        if bor(b, "yop", "chiq", "berk", "ket", "закр", "выйд", "close", "schlie"):
            ui_navbat.put(("sozlamalarni_yop",))
            gapir("Sozlamalar yopildi.")
        else:
            ui_navbat.put(("sozlamalarni_och",))
            gapir("Sozlamalarni ochdim.")
        return True
    if bor(b, "ovoz") and bor(b, "ayol", "qiz", "xotin", "женск"):
        sozlama_ozgartir("ovoz", "ayol")
        return True
    if bor(b, "ovoz") and bor(b, "erkak", "o'g'il", "yigit", "мужск"):
        sozlama_ozgartir("ovoz", "erkak")
        return True
    if bor(b, "til", "язык", "language", "sprache"):
        for kalit, sozlar in TIL_SOZLARI.items():
            if bor(b, *sozlar):
                sozlama_ozgartir("til", kalit)
                return True
    if bor(b, "rang"):
        for kalit, sozlar in RANG_SOZLARI.items():
            if bor(b + " ", *sozlar):
                sozlama_ozgartir("rang", kalit)
                return True
    if bor(b, "ismim") or (bor(b, "chaqir") and "deb" in b.split()):
        ism = ism_ajrat(b)
        if ism:
            sozlama_ozgartir("ism", ism)
            return True
    return False


# ---------- 3. SO'Z QIDIRISH (xato yozilganini ham topadi) ----------
def bor(gap, *sozlar):
    """Gapda shu so'zlardan biri yoki unga juda o'xshash so'z bormi?
    Masalan: 'telegrem' ham 'telegram' deb tushuniladi."""
    gapdagi_sozlar = gap.split()
    for soz in sozlar:
        if soz in gap:
            return True
        if len(soz) >= 5 and difflib.get_close_matches(soz, gapdagi_sozlar, n=1, cutoff=0.8):
            return True
    return False


def tasdiqla(savol):
    """Xavfli ishdan oldin so'raydi. Faqat "ha" desangiz True qaytaradi."""
    gapir(savol + " Ha yoki yo'q deng.")
    javob = eshit().split()
    return any(s.strip(".,!") in ("ha", "xa", "ha'", "albatta", "roziman", "да", "yes", "ja")
               for s in javob)


def fonda(ish, *qiymatlar):
    """Uzoq ishni (nusxalash, virus tekshiruvi) orqa fonda bajaradi,
    shunda Jarvis bu vaqtda boshqa buyruqlarni ham eshitaveradi."""
    threading.Thread(target=ish, args=qiymatlar).start()


# ---------- 3.1. "JARVIS" DEB CHAQIRISH (wake word) ----------
KIRILL_LOTIN = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ж": "j",
                "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
                "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
                "х": "x", "ц": "s", "ч": "ch", "ш": "sh", "ы": "i", "э": "e", "ю": "yu",
                "я": "ya", "ё": "yo", "ғ": "g'", "қ": "q", "ҳ": "h", "ў": "o'"}
CHAQIRUV_SOZLAR = ("jarvis", "djarvis")


def chaqiruv_sozimi(soz):
    """Bu so'z "Jarvis"mi? Google turlicha yozsa ham taniydi:
    jarvis, jarvisga, djarvis, jarviz, жарвис, джарвис..."""
    soz = "".join(KIRILL_LOTIN.get(h, h) for h in soz)     # жарвис -> jarvis
    soz = soz.strip(".,!?;:-\"'")
    if len(soz) < 4:
        return False
    for asos in CHAQIRUV_SOZLAR:
        # "jarvisga" -> faqat boshini ("jarvisg") ham solishtiramiz
        bosh = soz[:len(asos) + 1]
        oxshashlik = max(difflib.SequenceMatcher(None, asos, soz).ratio(),
                         difflib.SequenceMatcher(None, asos, bosh).ratio())
        if oxshashlik >= 0.75:
            return True
    return False


def chaqiruvni_ajrat(gap):
    """Gapda "Jarvis" bormi? Bo'lsa, qolgan buyruqni qaytaradi.
    'jarvis youtubeni och' -> (True, 'youtubeni och')
    'jarvis'               -> (True, '')
    'qo'shiq so'zlari'     -> (False, '')"""
    sozlar = gap.split()
    for i, soz in enumerate(sozlar):
        if chaqiruv_sozimi(soz):
            keyin = " ".join(sozlar[i + 1:]).strip(" ,.!?")
            oldin = " ".join(sozlar[:i]).strip(" ,.!?")
            return True, keyin or oldin          # "salom jarvis" -> "salom"
    return False, ""


# ---------- 4. AI (ixtiyoriy) ----------
def ai_javob(savol):
    """Faqat suhbat uchun. AI kompyuterda hech narsa bajarmaydi."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return ("Tushunmadim, boshqacha so'zlar bilan aytib ko'ring. "
                "Yordam desangiz, qanday buyruqlarni bilishimni aytaman.")
    try:
        import anthropic
        javob = anthropic.Anthropic().messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system="Sen Jarvis ismli yordamchisan. Faqat o'zbek tilida (lotin yozuvida), "
                   "qisqa, 1-3 gapda javob ber.",
            messages=[{"role": "user", "content": savol}],
        )
        return javob.content[0].text
    except Exception:
        return "AI bilan bog'lana olmadim."


# ---------- 5. DASTURLAR ----------
def telegram_och():
    yol = os.path.expandvars(r"%APPDATA%\Telegram Desktop\Telegram.exe")
    if os.path.exists(yol):
        subprocess.Popen(yol)
    else:
        try:
            os.startfile("tg://")                 # o'rnatilgan Telegram'ni ochadi
        except OSError:
            webbrowser.open("https://web.telegram.org")   # bo'lmasa, veb-versiya


# Telegramdagi guruh/chatlaringiz: "aytadigan so'z": "Telegramdagi aniq nomi"
# Google nomni noto'g'ri eshitsa ham, shu yerda to'g'rilab qo'yasiz.
TELEGRAM_NOMLAR = {
    "bikent": "Bikent 48",
    "vikend": "Bikent 48",
    "vikent": "Bikent 48",
}


def telegram_chat_nomi(gap):
    """'telegramdan vikend 48 guruhini och' -> 'Bikent 48'"""
    boshi = ("telegram", "телеграм", "guruh", "gurux", "kanal", "chat", "ochib", "kirib")
    aniq = {"och", "ber", "ga", "k", "kir", "menga", "ni"}
    qolgan = [s for s in gap.split() if not s.startswith(boshi) and s not in aniq]
    nom = " ".join(qolgan).strip()
    for kalit, haqiqiy in TELEGRAM_NOMLAR.items():
        if kalit in nom:
            return haqiqiy
    return nom


def telegram_chat_och(nom):
    """Telegram qidiruviga nomni yozib, birinchi natijani ochadi."""
    time.sleep(3)                       # Telegram ochilishini kutamiz
    pyautogui.press("esc")
    pyautogui.press("esc")              # ochiq chat bo'lsa, yopiladi
    pyautogui.hotkey("ctrl", "f")       # qidiruv maydoni
    time.sleep(0.5)
    pyperclip.copy(nom)
    pyautogui.hotkey("ctrl", "v")       # nomni qo'yamiz
    time.sleep(2)                       # natijalar chiqishini kutamiz
    pyautogui.press("enter")


YOUTUBE_SOZLAR = ("youtube", "yutub", "yutib", "youtub", "ютуб")
IJRO_SOZLAR = ("video", "rolik", "qo'y", "qo'", "ijro", "eshit", "ko'rsat", "top", "qidir", "musiq", "qo'shiq", "qo'shig", "klip")


def youtube_qidiruv_sozi(gap):
    """'youtubedan babylon musiqasini qo'y' -> 'babylon musiqa'"""
    boshi = ("youtub", "yutub", "yutib", "ютуб", "video", "rolik", "qo'y", "ijro", "eshit",
             "ko'rsat", "topib", "qidir", "ochib", "kerak", "keker", "iltimos", "yubor")
    aniq = {"och", "ber", "et", "top", "k", "menga", "qo'"}
    qolgan = [s for s in gap.split() if not s.startswith(boshi) and s not in aniq]
    # Google "youtubedan"ni "yutuqdan", "yulduzdan" deb eshitsa ham tashlab yuboramiz
    if len(qolgan) > 1 and qolgan[0].endswith("dan"):
        qolgan = qolgan[1:]
    soz = " ".join(qolgan)
    return soz.replace("musiqasini", "musiqa").replace("qo'shig'ini", "qo'shiq").strip()


# Musiqa/video qo'yilganda True bo'ladi: shunda 8 soniyalik suhbat oynasi ochilmaydi,
# aks holda mikrofon qo'shiq so'zlarini buyruq deb eshitib qolishi mumkin.
media_boshlandi = False


def youtube_ijro(soz):
    """YouTube'dan qidirib, birinchi videoni ochadi."""
    global media_boshlandi
    media_boshlandi = True
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(soz)
    try:
        sorov = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(sorov, timeout=10).read().decode("utf-8", "ignore")
        topildi = re.search(r"watch\?v=([\w-]{11})", html)
        if topildi:
            webbrowser.open("https://www.youtube.com/watch?v=" + topildi.group(1))
            return
    except Exception:
        pass
    webbrowser.open(url)          # topa olmasa, qidiruv natijalarini ochadi


def musiqani_tani():
    """Shazam kabi: atrofdagi musiqani 10 soniya tinglab, nomini topadi."""
    try:
        from shazamio import Shazam
    except ImportError:
        gapir("Buning uchun avval shazamio kutubxonasini o'rnating.")
        return
    gapir("Musiqani yoqing, 10 soniya tinglayman.", uzilmas=True)
    print("🎵 Musiqani tinglayapman...")
    holat("shazam")
    javob = queue.Queue()
    yozib_ber_navbat.put((10, javob))
    try:
        audio = javob.get(timeout=30)
    except queue.Empty:
        gapir("Mikrofondan ovoz ololmadim.")
        return
    fayl = os.path.join(tempfile.gettempdir(), "jarvis_musiqa.wav")
    with open(fayl, "wb") as f:
        f.write(audio.get_wav_data())
    try:
        natija = asyncio.run(Shazam().recognize(fayl))
    except Exception as xato:
        print(f"(Shazam xatosi: {xato})")
        gapir("Musiqani aniqlashda xato bo'ldi.")
        return
    trek = natija.get("track")
    if not trek:
        gapir("Bu musiqani taniy olmadim. Balandroq qo'yib, qayta urinib ko'ring.")
        return
    nomi, ijrochi = trek.get("title", ""), trek.get("subtitle", "")
    gapir(f"Bu {ijrochi}ning {nomi} qo'shig'i. YouTubeda qo'yaman.")
    youtube_ijro(f"{ijrochi} {nomi}")


# ---------- 5.1. KAYFIYAT ----------
KAYFIYAT_VIDEOLARI = {
    "kulgili": "eng kulgili videolar",
    "motivatsion": "motivatsion video o'zbekcha",
    "musiqa": "quvnoq o'zbek qo'shiqlari",
}


def kayfiyat_turi(gap):
    if bor(gap, "kulgi", "kulgu", "hazil", "prikol", "yumor"):
        return "kulgili"
    if bor(gap, "motiv", "ilhom"):
        return "motivatsion"
    if bor(gap, "musiq", "qo'shiq", "qo'shig", "qo'shig'"):
        return "musiqa"
    return None


def kayfiyat_kotar(gap):
    tur = kayfiyat_turi(gap)
    if not tur:
        gapir("Kayfiyatni ko'tarish uchun nima qo'yay: kulgili video, motivatsion video "
              "yoki quvnoq musiqa?")
        tur = kayfiyat_turi(eshit())
        if not tur:
            gapir("Yaxshi, unda kulgili video qo'yaman.")
            tur = "kulgili"
    nomlar = {"kulgili": "Kulgili video", "motivatsion": "Motivatsion video",
              "musiqa": "Quvnoq musiqa"}
    gapir(f"{nomlar[tur]} qo'yilmoqda. Kayfiyatingiz ko'tarilsin!")
    youtube_ijro(KAYFIYAT_VIDEOLARI[tur])


# ---------- 5.1.1. MUSIQA ----------
UMUMIY_SOZLAR = {"bir", "biror", "bitta", "musiqa", "qo'shiq", "yaxshi", "zo'r", "menga",
                 "kerak", "xohlayman", "istayman", "yoq", "ham"}


def musiqa_qoy(gap):
    """'babylon musiqasini qo'y' -> darhol qo'yadi.
    'menga bir musiqa kerak' -> nom yo'q, shuning uchun qanaqasini so'raydi."""
    soz = youtube_qidiruv_sozi(gap)
    if not [s for s in soz.split() if s not in UMUMIY_SOZLAR]:
        gapir("Qanaqa musiqa qo'yay? Qo'shiqchi yoki qo'shiq nomini ayting, "
              "yoki quvnoq, sokin deng.")
        javob = youtube_qidiruv_sozi(eshit())
        soz = f"{javob} musiqa" if javob else "eng yaxshi o'zbek qo'shiqlari"
    gapir(f"{soz} qo'yilmoqda.")
    youtube_ijro(soz)


# ---------- 5.2. USB FLESHKA ----------
def usb_nusxala():
    disklar = kompyuter.usb_disklar()
    if not disklar:
        gapir("USB fleshka topilmadi. U kompyuterga ulanganini tekshiring.")
        return
    hajm = sum(kompyuter.papka_hajmi(d) for d in disklar)
    manzil = kompyuter.usb_nusxa_papkasi()
    bosh_joy = shutil.disk_usage(kompyuter.desktop_yoli()).free
    if hajm > bosh_joy - 500 * 1024 ** 2:          # 500 MB zaxira qoldiramiz
        gapir(f"Fleshkada {kompyuter.hajm_matn(hajm)} ma'lumot bor, "
              "lekin kompyuterda joy yetmaydi.")
        return
    gapir(f"Fleshkada {kompyuter.hajm_matn(hajm)} ma'lumot bor. "
          "Ish stolidagi yangi papkaga nusxalashni boshladim, tugagach aytaman.")
    fonda(_usb_nusxala_fonda, disklar, manzil)


def _usb_nusxala_fonda(disklar, manzil):
    xatolar = kompyuter.usb_nusxala(disklar, manzil)
    papka = os.path.basename(manzil)
    if xatolar:
        gapir(f"Nusxalash tugadi, lekin {xatolar} ta fayl ko'chmadi. Papka nomi: {papka}.")
    else:
        gapir(f"Fleshkadagi hamma fayllar nusxalandi. Ish stolidagi papka nomi: {papka}.")


# ---------- 5.3. KESH ----------
def keshni_tozala():
    gapir("Vaqtinchalik fayllarni qidiryapman.")
    fayllar = kompyuter.kesh_fayllari()
    if not fayllar:
        gapir("Tozalash kerak bo'lgan kesh fayllari topilmadi.")
        return
    hajm = sum(h for _, h in fayllar)
    if not tasdiqla(f"{len(fayllar)} ta vaqtinchalik fayl topildi, jami "
                    f"{kompyuter.hajm_matn(hajm)}. O'chiraymi?"):
        gapir("Bekor qilindi.")
        return
    soni, bayt = kompyuter.kesh_ochir(fayllar)
    gapir(f"{soni} ta fayl o'chirildi, {kompyuter.hajm_matn(bayt)} joy bo'shadi.")
    if soni < len(fayllar):
        gapir("Ba'zi fayllar hozir ishlatilayotgani uchun qoldirildi.")


# ---------- 5.4. VIRUS ----------
def virus_tekshir(gap):
    if not kompyuter.defender_yoli():
        gapir("Windows antivirusini topa olmadim. Windows Xavfsizlik oynasini ochyapman.")
        kompyuter.windows_xavfsizlik_och()
        return
    if bor(gap, "usb", "fleshka", "флешка", "flesh"):
        disklar = kompyuter.usb_disklar()
        if not disklar:
            gapir("USB fleshka topilmadi.")
            return
        gapir("Fleshkani virusga tekshiryapman, tugagach aytaman.")
    else:
        disklar = [None]
        gapir("Kompyuterni tezkor virus tekshiruvidan o'tkazyapman. "
              "Bu bir necha daqiqa oladi, tugagach aytaman.")
    fonda(_virus_fonda, disklar)


def _virus_fonda(disklar):
    natijalar = [kompyuter.virus_tekshir(d) for d in disklar]
    if "topildi" in natijalar:
        gapir("Diqqat! Xavfli fayllar topildi. Windows Xavfsizlik oynasini ochyapman.")
        kompyuter.windows_xavfsizlik_och()
    elif "xato" in natijalar:
        gapir("Tekshiruvni oxiriga yetkaza olmadim. Windows Xavfsizlik oynasini ochyapman, "
              "u yerdan tekshirib ko'ring.")
        kompyuter.windows_xavfsizlik_och()
    else:
        gapir("Tekshiruv tugadi. Virus topilmadi.")


# ---------- 5.5. ILOVALAR ----------
KOMPYUTER_SOZLARI = ("kompyuter", "kampyuter", "kampiyuter", "komputer", "kompiyuter",
                     "kampuyter", "компьютер")
ALOHIDA_QOSHIMCHALAR = {"ni", "di", "ga", "da", "dan", "ning", "ham", "u", "bu"}


def ilova_nomi(gap):
    """'photoshopni ochib ber' -> 'photoshop';  'kampiyuterimdan proton vpn ni och' -> 'proton vpn'"""
    ortiqcha = ("och", "ishga", "tushir", "dastur", "ilova", "programma", "menga",
                "iltimos", "ber", "yoq") + KOMPYUTER_SOZLARI
    sozlar = []
    for s in gap.split():
        if s.startswith(ortiqcha) or s in ALOHIDA_QOSHIMCHALAR:
            continue
        if len(s) > 4 and s.endswith(("ni", "ga")):
            s = s[:-2]
        sozlar.append(s)
    return " ".join(sozlar).strip()


# Dastur sifatida topilmasa, brauzerda ochiladigan mashhur saytlar
SAYTLAR = {
    "instagram": "https://www.instagram.com", "youtube": "https://www.youtube.com",
    "facebook": "https://www.facebook.com", "telegram": "https://web.telegram.org",
    "whatsapp": "https://web.whatsapp.com", "gmail": "https://mail.google.com",
    "google": "https://www.google.com", "chatgpt": "https://chat.openai.com",
    "tiktok": "https://www.tiktok.com", "twitter": "https://twitter.com",
    "x": "https://twitter.com", "linkedin": "https://www.linkedin.com",
    "github": "https://github.com", "netflix": "https://www.netflix.com",
    "wikipedia": "https://www.wikipedia.org", "reddit": "https://www.reddit.com",
    "olx": "https://www.olx.uz", "kun": "https://kun.uz", "yandex": "https://ya.ru",
}


def ilova_och(gap):
    nom = ilova_nomi(gap)
    if not nom:
        gapir("Qaysi dasturni ochay?")
        return
    topildi = kompyuter.ilova_top(nom)
    if topildi:
        nomi, yol = topildi
        try:
            kompyuter.ilova_och(yol)
            gapir(f"{nomi} ochildi.")
            return
        except OSError:
            pass
    # o'rnatilgan dastur topilmadi — sayt sifatida brauzerda ochamiz
    for kalit, url in SAYTLAR.items():
        if bor(nom + " ", kalit) or kalit in nom.replace(" ", ""):
            webbrowser.open(url)
            gapir(f"{kalit} brauzerda ochildi.")
            return
    if "." in nom.replace(" ", ""):                 # "olx.uz" kabi manzil aytilsa
        webbrowser.open("https://" + nom.replace(" ", ""))
        gapir(f"{nom} ochildi.")
        return
    gapir(f"{nom} degan dastur topilmadi. Sayt bo'lsa, to'liq nomini ayting, "
          "masalan: instagram, youtube.")


# ---------- 5.6. FAYL QIDIRISH ----------
def fayl_nomi(gap):
    """'kompyuterdan hisobot faylini top' -> 'hisobot'"""
    ortiqcha = ("fayl", "papka", "hujjat", "qayer", "qidir", "top", "kompyuter", "menga",
                "nomli", "degan", "joylash", "turibdi", "iltimos", "ichida", "jarvis")
    aniq = {"ber", "bor", "u", "bu", "mening", "ni", "qani"}
    sozlar = []
    for s in gap.split():
        if s.startswith(ortiqcha) or s in aniq:
            continue
        for qoshimcha in ("ning", "ni"):
            if len(s) > len(qoshimcha) + 2 and s.endswith(qoshimcha):
                s = s[:-len(qoshimcha)]
                break
        sozlar.append(s)
    return " ".join(sozlar).strip()


def fayl_top(gap):
    nom = fayl_nomi(gap)
    if not nom:
        gapir("Qaysi faylni qidiray? Nomini ayting.")
        nom = fayl_nomi(eshit())
        if not nom:
            return
    gapir(f"{nom} nomli faylni qidiryapman.")
    fonda(_fayl_top_fonda, nom)


def _fayl_top_fonda(nom):
    natijalar = kompyuter.fayl_qidir(nom)
    if not natijalar:
        gapir(f"{nom} degan fayl topilmadi.")
        return
    for yol in natijalar[:10]:
        print("  📄", yol)
    birinchi = natijalar[0]
    gapir(f"{os.path.basename(birinchi)} {kompyuter.joy_nomi(birinchi)} turibdi. "
          "Papkasini ochib ko'rsatdim.")
    kompyuter.papkada_korsat(birinchi)
    if len(natijalar) > 1:
        boshqalar = "; ".join(f"{os.path.basename(y)} — {kompyuter.joy_nomi(y)}"
                              for y in natijalar[1:4])
        gapir(f"Yana {len(natijalar) - 1} ta o'xshash fayl bor.")
        ui_navbat.put(("jarvis", "Boshqalari: " + boshqalar))


# ---------- 5.7. SAVOLLARGA JAVOB ----------
def javob_ber(gap):
    """Savol bo'lsa — Vikipediyadan javob topadi. Topolmasa — Google'ni ochadi."""
    if not bilim.savolmi(gap):
        gapir(ai_javob(gap))
        return
    javob, havola = bilim.javob_top(gap, til())
    if javob:
        gapir(javob, tarjima_qil=False)          # Vikipediya allaqachon shu tilda
    elif os.environ.get("ANTHROPIC_API_KEY"):
        gapir(ai_javob(gap))
    else:
        webbrowser.open(havola)
        gapir("Vikipediyadan topa olmadim, Googledan qidirib ochdim.")


YORDAM_MATNI = ("Meni chaqirish uchun avval Jarvis deng, yoki oynaning pastiga yozing. "
                "Men quyidagilarni qila olaman: YouTube, Telegram, brauzer, bloknot, "
                "kalkulyator va papkalarni ochaman. Telegramda guruhni ham ocha olaman. "
                "Soat va sanani aytaman. "
                "Ovozni oshiraman yoki pasaytiraman. Googledan qidiraman. "
                "YouTubedan musiqa qo'yaman, masalan: youtubedan babylon musiqasini qo'y. "
                "Musiqani tinglab, nomini ham topaman, buning uchun: bu qanaqa qo'shiq, deng. "
                "Kayfiyatingizni ko'taruvchi video qo'yaman. "
                "Fleshkadagi fayllarni ish stoliga nusxalayman. "
                "Keshni tozalayman va kompyuterni virusga tekshiraman. "
                "Kompyuterdagi dasturlarni ochaman, masalan: wordni och. "
                "Fayl qayerdaligini topaman, masalan: hisobot faylini top. "
                "Savollarga Vikipediyadan javob beraman, masalan: Amir Temur kim. "
                "Sozlamalar deng: ovozim, tilim va rangimni o'zgartirasiz. "
                "Ilova ichida tugmani bosaman, masalan: enter the game tugmasini bos. "
                "Matn yozaman, masalan: salom deb yoz. "
                "Telegram bot orqali telefondan ham boshqarasiz: fayl va rasmlarni yuboraman, "
                "ekran rasmini olaman. "
                "Gapimni bo'lish uchun shunchaki gapiring, jim bo'lishim uchun to'xta deng. "
                "Butunlay o'chishim uchun xayr deng.")


# ---------- 6. BUYRUQLAR (faqat ruxsat berilganlar) ----------
def bajar(b):
    """False qaytarsa, dastur to'xtaydi."""
    if bor(b, "xayr"):
        gapir(f"Xayr, {ISM}!")
        return False

    elif bor(b, "musiq", "qo'shiq", "video", "pauza") and bor(b, "to'xtat", "pauza", "davom"):
        pyautogui.press("playpause")                # klaviaturadagi ⏯ tugmasi
        gapir("Bajarildi.")

    elif len(b.split()) <= 3 and {"to'xta", "jim", "bas", "yetar", "yetadi", "stop", "стоп",
                                  "хватит"} & set(b.replace(",", " ").split()):
        uzildi.set()                                # jonli ekran / uzoq ish bo'lsa to'xtaydi

    elif sozlama_buyrugi(b):
        pass

    elif bor(b, "ekran rasm", "skrinshot", "screenshot", "скриншот", "ekranni rasm",
             "ekranni ol", "ekranni suratga", "skrin", "ekran surat") or (
             bor(b, "screen") and bor(b, "ekran", "qil", "ol", "rasm")) \
            or b.strip() in ("screen", "skrin", "скрин"):
        ekran_rasmi()

    elif "deb" in b.split() and b.split()[-1].startswith(("yoz", "yubor", "jo'nat")) and (
            bor(b, "telegram", "телеграм", "instagram", "инстаграм", "insta", "whatsapp",
                "vatsap", "votsap", "ватсап", "messenger", "vkontakte") and bor(b, "ga ", "ga")):
        ilovada_yoz(b)

    elif bosish_buyrugimi(b):
        tugma_bos(b)

    elif "deb" in b.split() and b.split()[-1].startswith("yoz"):
        matn_yozish(b)

    elif bor(b, "pastga", "tepaga", "yuqoriga") and bor(b, "tushir", "aylantir", "chiq", "sur") \
            and not bor(b, "ovoz"):
        pyautogui.scroll(-600 if bor(b, "pastga") else 600)
        gapir("Bajarildi.")

    elif bor(b, "yop") and bor(b, "oyna", "dastur", "ilova", "o'yin", "programma") \
            and not bor(b, "sozlama"):
        oynani_yop()

    elif (javob_telegramga or bor(b, "telegram")) and bor(b, "tashla", "yubor", "jo'nat") \
            and not bor(b, "qo'yib", "qo'y"):
        telegramga_yubor(b)

    elif bor(b, "salom", "assalom"):
        gapir(f"Va alaykum assalom, {ISM}! Buyruq bering.")

    elif bor(b, "kimsan", "isming", "sen kim"):
        gapir(f"Men Jarvisman, {ISM}ning shaxsiy yordamchisiman.")

    elif bor(b, "qalaysan", "yaxshimisan", "ishlar qalay"):
        gapir("Rahmat, yaxshi! Sizga nima yordam kerak?")

    elif bor(b, "kayfiyat", "zerikdim", "zerikyapman", "xafaman", "zerik"):
        kayfiyat_kotar(b)

    elif bor(b, "rahmat", "zo'r", "yaxshi", "barakalla", "molodes"):
        gapir("Arzimaydi, xizmatingizdaman!")

    elif bor(b, "shazam", "tanib ol", "qanaqa qo'shiq", "qanday qo'shiq", "qaysi qo'shiq",
             "qanaqa musiqa", "qanday musiqa", "qaysi musiqa", "nima qo'shiq",
             "tinglab top", "eshitib top") or (
            bor(b, "musiq", "qo'shiq", "qo'shig")
            and bor(b, "tingla", "topib ber", "tani")
            and not bor(b, *YOUTUBE_SOZLAR)):
        musiqani_tani()

    elif bor(b, "yordam", "buyruq", "nima qila olasan", "nimalar qila"):
        gapir(YORDAM_MATNI)

    elif bor(b, "virus", "вирус"):
        virus_tekshir(b)

    elif bor(b, "tozala", "tozalab", "tozalash") or (
            bor(b, "kesh", "кеш", "cache", "vaqtinchalik fayl", "musor", "axlat")
            and bor(b, "o'chir")):
        # Google "kesh"ni "kech", "kelish", "kesish" deb yozadi — shuning uchun
        # "tozala" so'zining o'zi yetarli. O'chirishdan oldin baribir tasdiq so'raladi.
        keshni_tozala()

    elif bor(b, "usb", "юсб", "fleshka", "флешка", "flesh") and bor(
            b, "nusxa", "ko'chir", "kochir", "copy", "desktop", "ish stoli"):
        usb_nusxala()

    elif (bor(b, "fayl", "papka", "hujjat") and bor(b, "qayer", "qidir", "top")) or (
            bor(b, "kompyuter") and bor(b, "qidir", "top")):
        # USB buyrug'idan keyin turishi shart: "desktopga" so'zida ham "top" bor
        fayl_top(b)

    elif bor(b, *YOUTUBE_SOZLAR) or bor(b, "video", "klip", "rolik"):
        soz = youtube_qidiruv_sozi(b)
        if soz and bor(b, *IJRO_SOZLAR):
            gapir(f"{soz} qo'yilmoqda.")
            youtube_ijro(soz)
        else:
            webbrowser.open("https://youtube.com")
            gapir("YouTube ochildi.")

    elif bor(b, "musiq", "qo'shiq", "qo'shig") and bor(b, "qo'y", "qo'", "ijro", "eshit",
                                                       "kerak", "xohlayman", "istayman"):
        musiqa_qoy(b)

    elif bor(b, "qidir"):
        soz = b
        for ortiqcha in ["qidirib ber", "qidir", "googledan", "google"]:
            soz = soz.replace(ortiqcha, "")
        soz = soz.strip()
        webbrowser.open(f"https://www.google.com/search?q={soz}")
        gapir(f"{soz} qidirilmoqda.")

    elif bor(b, "telegram", "telegramm", "телеграм"):
        nom = telegram_chat_nomi(b)
        telegram_och()
        if nom:
            gapir(f"Telegramda {nom} ochilmoqda.")
            telegram_chat_och(nom)
        else:
            gapir("Telegram ochildi.")

    elif bor(b, "brauzer", "google", "chrome", "xrom", "internet"):
        webbrowser.open("https://google.com")
        gapir("Brauzer ochildi.")

    elif bor(b, "bloknot", "notepad"):
        subprocess.Popen("notepad")
        gapir("Bloknot ochildi.")

    elif bor(b, "kalkulyator", "kalkulator", "hisobla"):
        subprocess.Popen("calc")
        gapir("Kalkulyator ochildi.")

    elif bor(b, "papka", "fayllar", "provodnik"):
        subprocess.Popen("explorer")
        gapir("Fayllar ochildi.")

    elif bor(b, "soat", "vaqt"):
        gapir("Hozir soat " + datetime.datetime.now().strftime("%H:%M"))

    elif bor(b, "sana", "bugun"):
        gapir("Bugun " + datetime.datetime.now().strftime("%d.%m.%Y"))

    elif bor(b, "ovoz") and bor(b, "oshir", "baland", "ko'tar"):
        pyautogui.press("volumeup", presses=5)
        gapir("Ovoz oshirildi.")

    elif bor(b, "ovoz") and bor(b, "pasay", "past", "kamay"):
        pyautogui.press("volumedown", presses=5)

    elif bor(b, "ovoz") and bor(b, "o'chir"):
        pyautogui.press("volumemute")

    elif bor(b, "o'chirishni bekor") or (bor(b, "bekor") and bor(b, "o'chir", "restart", "qayta")):
        kompyuter.ochirishni_bekor()
        gapir("O'chirish bekor qilindi.")

    elif bor(b, "kompyuter", "komputer", "kompiyuter", "kampyuter", "kampiyuter", "noutbuk",
             "sistema", "kampuyter") and bor(b, "qulf", "qulufla", "quluf", "qulup", "bloklab",
                                             "blokla", "lock", "лок", "заблок"):
        gapir("Kompyuter qulflandi.")
        kompyuter.kompyuterni_qulfla()

    elif bor(b, "kompyuter", "komputer", "kompiyuter", "kampyuter", "kampiyuter", "noutbuk",
             "sistema", "kampuyter") and bor(b, "uyqu", "uxla", "sleep", "спящ"):
        if tasdiqla("Kompyuterni uyqu rejimiga o'tkazaymi?"):
            kompyuter.uyqu_rejimi()

    elif bor(b, "kompyuter", "komputer", "kompiyuter", "kampyuter", "kampiyuter", "noutbuk",
             "sistema", "kampuyter") and bor(b, "restart", "qayta yukla", "qayta ishga",
                                             "perezagruz", "перезагруз", "o'chirib yoq"):
        if tasdiqla("Kompyuterni qayta yuklaymi? Saqlanmagan ishlar yo'qoladi."):
            gapir("Kompyuter 10 soniyadan keyin qayta yuklanadi.")
            kompyuter.kompyuterni_restart()
        else:
            gapir("Bekor qilindi.")

    elif bor(b, "kompyuter", "komputer", "kompiyuter", "kampyuter", "kampiyuter", "noutbuk",
             "sistema", "kampuyter") and bor(b, "o'chir", "vikl", "выключ"):
        if tasdiqla("Rostdan kompyuterni o'chiraymi?"):
            gapir("Kompyuter 15 soniyadan keyin o'chadi. Bekor qilish uchun o'chirishni bekor qil deng.")
            kompyuter.kompyuterni_ochir()
        else:
            gapir("Bekor qilindi.")

    elif bor(b, "kamera", "камера", "webcam", "kimdir bor", "kim bor", "kim otiribdi",
             "selfie", "selfi") and not bor(b, "och"):
        kamera_rasmi()

    elif bor(b, "jonli", "efir", "kuzat", "live") and bor(b, "ekran", "screen", "экран"):
        ekranni_kuzat()


    elif any(s.startswith("och") for s in b.split()) or bor(b, "ishga tushir"):
        ilova_och(b)

    elif b:
        javob_ber(b)

    return True


# ---------- ASOSIY SIKL (miya thread'i) ----------
def miya():
    global media_boshlandi, javob_telegramga, oxirgi_manba
    ui_navbat.put(("sozlamalar", dict(SOZ)))
    telegram_ishga_tushir()
    gapir(f"Salom, {ISM}! Men Jarvisman. Kerak bo'lsam, Jarvis deb chaqiring yoki pastga yozing.")
    suhbat_tugashi = 0          # shu vaqtgacha "Jarvis" demasdan gapirsa bo'ladi

    while True:
        qoldi = suhbat_tugashi - time.time()
        suhbatda = qoldi > 0
        yangi_holat = "tinglash" if suhbatda else "kutish"
        if joriy_holat != yangi_holat:
            if yangi_holat == "kutish":
                print("💤 Kutish rejimi (Jarvis deng).")
            holat(yangi_holat)

        kelgan = keyingi_gap(qoldi if suhbatda else 1.0)
        if not kelgan:
            continue
        manba, gap = kelgan

        chaqirildi, buyruq = chaqiruvni_ajrat(gap)
        if not chaqirildi:
            if manba == "ovoz" and not suhbatda:
                continue                                # begona gap / qo'shiq — e'tibor bermaymiz
            buyruq = gap                                # yozilgan gapga "Jarvis" shart emas
        javob_telegramga = manba == "telegram"
        oxirgi_manba = "ovoz" if manba == "uzish" else manba
        ui_navbat.put(("siz", ("(Telegram) " if javob_telegramga else "") + gap))
        if javob_telegramga and not buyruq:
            buyruq = "salom"
        if not buyruq:
            gapir(f"Labbay, {ISM}?")
            suhbat_tugashi = time.time() + SUHBAT_VAQTI
            continue

        holat("o'ylash")
        media_boshlandi = False
        try:
            davom = bajar(ichki_tilga(buyruq))
        except Exception as xato:
            print(f"(Xato: {xato})")
            gapir("Buyruqni bajarishda xato bo'ldi.")
            davom = True
        if not davom:
            break

        if media_boshlandi:
            suhbat_tugashi = 0                          # musiqa ketyapti — darhol kutish rejimi
            print("💤 Musiqa qo'yildi, faqat Jarvis desangiz eshitaman.")
        else:
            suhbat_tugashi = time.time() + SUHBAT_VAQTI
    ui_navbat.put(("yopil",))


if __name__ == "__main__":
    import interfeys
    oyna = interfeys.Oyna(ui_navbat, kirish_navbat, SOZ)     # oyna — asosiy thread'da
    threading.Thread(target=mikrofon_ishi, daemon=True).start()
    threading.Thread(target=miya, daemon=True).start()
    oyna.ishga_tushir()
