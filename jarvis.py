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
import os
import sys

# EXE (oynali rejim)da konsol yo'q — barcha xabar va xatolar log faylga yoziladi:
# %APPDATA%\Jarvis\jarvis.log
if getattr(sys, "frozen", False) and sys.stdout is None:
    _log_papka = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Jarvis")
    os.makedirs(_log_papka, exist_ok=True)
    sys.stdout = sys.stderr = open(os.path.join(_log_papka, "jarvis.log"), "a",
                                   encoding="utf-8", buffering=1)

# "Jarvis.exe --chat URL" — faqat chat oynasi (alohida jarayon). Og'ir qismlarni yuklamaymiz.
if "--chat" in sys.argv:
    import chat_oyna
    _i = sys.argv.index("--chat")
    chat_oyna.och(sys.argv[_i + 1] if len(sys.argv) > _i + 1 else chat_oyna.STANDART_URL)
    sys.exit(0)

import asyncio
import atexit
import audioop
import datetime
import difflib
import io
import json
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

import arxiv
import bilim
import boshqaruv
import bulut
import himoya
import kamera
import yuz
import kompyuter
import qulayliklar
import sayt
import sozlamalar
import suhbat
import server
import sun_iy
import telefon
import telegram_bot
from tarjima import tarjima

# Ovoz, til, rang va ism — oynadagi ⚙ menyusidan yoki ovoz bilan o'zgartiriladi
SOZ = sozlamalar.yukla()
ISM = SOZ["ism"]                 # Jarvis sizni shunday chaqiradi
if SOZ.get("groq_kalit") and not os.environ.get("GROQ_API_KEY"):
    os.environ["GROQ_API_KEY"] = SOZ["groq_kalit"]     # chatdagi sozlamalarda kiritilgan AI kaliti
if SOZ.get("claude_kalit") and not os.environ.get("ANTHROPIC_API_KEY"):
    os.environ["ANTHROPIC_API_KEY"] = SOZ["claude_kalit"]   # pullik Claude — savol va buyruqlar uchun
os.environ["JARVIS_CLAUDE_MODEL"] = SOZ.get("claude_model") or "claude-sonnet-5"
SUHBAT_VAQTI = 8                 # buyruqdan keyin shuncha soniya "Jarvis" demasdan gapirsa bo'ladi

try:
    pygame.mixer.init()
except pygame.error as _xato:            # karnay/ovoz qurilmasi yo'q — dastur baribir ishlasin
    print(f"(Ovoz qurilmasi topilmadi: {_xato})")
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


def gapir(matn, tarjima_qil=True, ovoz=None, uzilmas=False, rasm=None):
    """Jarvis ichida hamma javob o'zbekcha yoziladi; boshqa til tanlangan bo'lsa,
    gapirishdan oldin o'sha tilga tarjima qilinadi.
    uzilmas=True — bu gapni bo'lib bo'lmaydi."""
    global hozirgi_gap, uzish_mumkin
    if tarjima_qil and til() != "uz":
        matn = tarjima(matn, "uz", til())
    print(f"Jarvis: {matn}")
    ui_navbat.put(("jarvis", matn))
    arxiv.yoz("jarvis", matn, rasm=rasm)
    yiguvchi = getattr(web_holati, "yig", None)
    if yiguvchi is not None:        # buyruq telefon ilovasidan keldi — javobni to'playmiz
        yiguvchi.append(matn)
        return
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


EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2190-\u21FF\u2B00-\u2BFF\uFE0F\u200D]+")


def _gapir(matn, ovoz=None):
    try:
        matn = EMOJI_RE.sub("", matn).strip() or matn      # emojilarni ovoz chiqarib o'qimaymiz
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


# Mikrofon holati — chatdagi sozlamalarda ko'rinadi (nosozlikni topish oson bo'lsin)
MIK_HOLAT = {"nomi": "", "ishlayapti": False, "xato": "", "chegara": 0, "daraja": 0,
             "oxirgi": "", "vaqt": 0}
mik_qayta = threading.Event()         # sozlama o'zgardi — mikrofonni qayta ochish
# Sezgirlik (1..5) -> ovoz chegarasining yuqori chegarasi: qancha past bo'lsa, shuncha sezgir
SEZGIRLIK_CHEGARA = {1: 420, 2: 320, 3: 230, 4: 160, 5: 100}
PAST_CHEGARA = 70                     # bundan past — shovqinni ham gap deb oladi


def mikrofonlar():
    """Kompyuterdagi mikrofonlar (faqat ovoz yozadiganlari): [(indeks, nomi), ...]"""
    royxat, korilgan = [], set()
    try:
        pa = sr.Microphone.get_pyaudio().PyAudio()
        try:
            for i in range(pa.get_device_count()):
                info = pa.get_device_info_by_index(i)
                nom = str(info.get("name", "")).strip()
                if info.get("maxInputChannels", 0) > 0 and nom and nom not in korilgan \
                        and not re.search(r"stereo mix|стерео микшер|what u hear|loopback", nom, re.I):
                    korilgan.add(nom)
                    royxat.append((i, nom))
        finally:
            pa.terminate()
    except Exception as xato:
        print(f"(Mikrofonlar ro'yxatini olib bo'lmadi: {xato})")
    return royxat


def _standart_mikrofon_nomi():
    try:
        pa = sr.Microphone.get_pyaudio().PyAudio()
        try:
            return str(pa.get_default_input_device_info().get("name", "Windows standarti"))
        finally:
            pa.terminate()
    except Exception:
        return "Windows standarti"


def _mikrofon_top():
    """Ishlaydigan mikrofonni topadi: avval tanlangani, keyin Windows standarti,
    keyin boshqa mikrofonlar (avtomatik). (Microphone, nomi) yoki (None, xato)."""
    royxat = mikrofonlar()
    tanlangan = SOZ.get("mikrofon") or ""
    sinovlar = [i for i, n in royxat if n == tanlangan]
    sinovlar.append(None)                                   # Windows standarti
    sinovlar += [i for i, n in royxat if i not in sinovlar]
    oxirgi_xato = "Mikrofon topilmadi — ulanganini tekshiring"
    for indeks in sinovlar:
        try:
            mik = sr.Microphone(device_index=indeks)
            with mik:                                       # ochilishini sinab ko'ramiz
                pass
            nom = dict(royxat).get(indeks) if indeks is not None else _standart_mikrofon_nomi()
            return mik, nom
        except Exception as xato:
            oxirgi_xato = str(xato) or oxirgi_xato
    return None, oxirgi_xato


def _chegarani_sozla():
    """Ovoz chegarasini sezgirlik oralig'ida ushlaymiz (juda baland bo'lib ketib, gapni eshitmay qolmasin)."""
    yuqori = SEZGIRLIK_CHEGARA.get(int(SOZ.get("sezgirlik", 3) or 3), 230)
    tanib.energy_threshold = max(PAST_CHEGARA, min(tanib.energy_threshold, yuqori))
    MIK_HOLAT["chegara"] = int(tanib.energy_threshold)


def mikrofon_ishi():
    """Alohida thread: doim tinglaydi va eshitganini kirish_navbat'ga qo'yadi.
    Mikrofon ochilmasa yoki uzilib qolsa — o'zi qayta urinadi (avtomatik)."""
    tanib.pause_threshold = 0.8          # gap orasidagi kichik to'xtashda kesib qo'ymaydi
    tanib.non_speaking_duration = 0.4    # gap boshi/oxiridagi jimlikni ham oladi ("Jar-vis" kesilmasin)
    tanib.dynamic_energy_threshold = True    # atrof shovqiniga o'zi moslashadi
    xabar_berildi = False
    while True:
        mik, nomi = _mikrofon_top()
        if mik is None:
            MIK_HOLAT.update(ishlayapti=False, xato=nomi, nomi="")
            if not xabar_berildi:
                print(f"(Mikrofon ishlamayapti: {nomi}) — qayta urinaman. Hozircha chatga yozing.")
                xabar_berildi = True
            time.sleep(5)
            continue
        xabar_berildi = False
        MIK_HOLAT.update(ishlayapti=True, xato="", nomi=nomi)
        print(f"🎙️ Mikrofon: {nomi}")
        mik_qayta.clear()
        try:
            with mik as mic:
                _tinglash_sikli(mic)
        except Exception as xato:
            print(f"(Mikrofon uzildi: {xato}) — qayta ulanaman.")
            MIK_HOLAT.update(ishlayapti=False, xato=str(xato))
            time.sleep(2)


def _tinglash_sikli(mic):
    """Mikrofon ochiq ekan tinglaydi. Sozlama o'zgarsa yoki mikrofon buzilsa — qaytadi."""
    tanib.adjust_for_ambient_noise(mic, duration=1)
    _chegarani_sozla()
    oxirgi_sozlash = oxirgi_gap = time.time()
    xatolar = 0
    while not mik_qayta.is_set():
        if time.time() - oxirgi_sozlash > 60:    # har daqiqada shovqinga qayta moslashadi
            try:
                tanib.adjust_for_ambient_noise(mic, duration=0.3)
            except Exception:
                pass
            _chegarani_sozla()
            oxirgi_sozlash = time.time()
        # Uzoq vaqt hech narsa eshitilmasa — sezgirlikni asta oshiramiz (avtomatik)
        if time.time() - oxirgi_gap > 45 and tanib.energy_threshold > PAST_CHEGARA * 1.3:
            tanib.energy_threshold *= 0.85
            _chegarani_sozla()
            oxirgi_gap = time.time()
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
            audio = tanib.listen(mic, timeout=3, phrase_time_limit=5 if gapirganda else 9)
            xatolar = 0
        except sr.WaitTimeoutError:
            _chegarani_sozla()
            continue
        except Exception as xato:           # mikrofon uzilsa ham thread to'xtamasin
            xatolar += 1
            print(f"(Mikrofon xatosi: {xato})")
            if xatolar >= 3:
                raise                        # qayta ochamiz (boshqa mikrofon bo'lishi mumkin)
            time.sleep(1)
            continue
        _chegarani_sozla()
        oxirgi_gap = time.time()
        try:
            MIK_HOLAT["daraja"] = int(audioop.rms(audio.frame_data, audio.sample_width))
        except Exception:
            pass
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


def _variantlar(audio, til_kodi):
    """Google bergan barcha taxminlar (eng ishonchlisi birinchi)."""
    try:
        javob = tanib.recognize_google(audio, language=til_kodi, show_all=True)
    except sr.UnknownValueError:
        return []
    if not isinstance(javob, dict):
        return []
    return [a["transcript"] for a in javob.get("alternative", []) if a.get("transcript")]


def _jarvis_bormi(matn):
    return chaqiruvni_ajrat(normallashtir(matn))[0]


def matnga_aylantir(audio, gapirganda=False, jarvis_gapi=""):
    try:
        variantlar = _variantlar(audio, sozlamalar.TILLAR[til()]["google"])
        matn = variantlar[0] if variantlar else ""
        # Kutish rejimida "Jarvis"ni aniq ilg'ash: o'zbekcha tanishda "Jarvis" ko'pincha
        # "kar", "dar" bo'lib chiqadi. Avval boshqa taxminlarga qaraymiz, bo'lmasa
        # shu ovozni inglizcha ham tanib ko'ramiz ("Jarvis" — inglizcha ism).
        if not gapirganda and joriy_holat == "kutish" and not _jarvis_bormi(matn):
            topildi = next((v for v in variantlar if _jarvis_bormi(v)), None)
            if topildi:
                matn = topildi
            elif any(_jarvis_bormi(v) for v in _variantlar(audio, "en-US")):
                # "kar youtube och" -> "jarvis youtube och" (buzilgan birinchi so'z = Jarvis)
                matn = "jarvis " + " ".join(matn.split()[1:])
        if not matn.strip():
            return
    except sr.RequestError:
        print("(Internet bilan muammo bor)")
        MIK_HOLAT["xato"] = "Ovozni tanish uchun internet kerak"
        return
    if gapirganda:
        if aks_sadomi(matn, jarvis_gapi):
            return                          # o'z ovozim — e'tibor bermayman
        print(f"✋ Gapimni bo'ldingiz: {matn}")
        uzildi.set()                        # Jarvis darhol jim bo'ladi
        kirish_navbat.put(("uzish", normallashtir(matn), time.time()))
        return
    print(f"Eshitildi: {matn}")
    MIK_HOLAT.update(oxirgi=matn, vaqt=time.time(), xato="")
    kirish_navbat.put(("ovoz", normallashtir(matn), time.time()))


def keyingi_gap(kutish):
    """Navbatdan keyingi gapni oladi (ovoz yoki yozuv). Jarvis gapirib bo'lishidan
    oldin eshitilgan eski gaplar tashlab yuboriladi."""
    global asl_matn
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
        if manba == "chat_och":                 # sharni o'ng tugma bilan bosdi — sozlamalar
            chat_och(sozlama=(matn == "soz"))
            continue
        if manba == "ovoz_sinov":               # menyuda "Eshitib ko'rish" bosildi
            gapir(f"Salom, {ISM}! Men shu ovozda gapiraman.",
                  ovoz=sozlamalar.TILLAR[til()][matn])
            continue
        asl = matn
        if manba in ("yozuv", "telegram", "chat"):
            matn = normallashtir(matn)
        if vaqt >= gap_tugadi or manba == "uzish":
            asl_matn = asl                      # xabar yozishda asl harflar kerak bo'ladi
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
    arxiv.yoz("siz", asl_matn or gap[1], gap[0])
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
              else SOZLAMA_JAVOBLARI.get(kalit, "Sozlama saqlandi."))
        if kalit in ("telegram_token", "telegram_egasi"):
            telegram_ishga_tushir()             # yangi token yoki uzildi — bot qayta ulanadi


# ---------- 2.2. TELEGRAM BOT (telefondan boshqarish) ----------
oxirgi_manba = ""                 # hozirgi buyruq qayerdan keldi: ovoz, yozuv, telegram, uzish
bot = None                        # ishlab turgan Telegram bot
web_holati = threading.local()    # telefon ilovasidan kelgan buyruq javobini to'plash uchun
web_qulfi = threading.Lock()      # bir vaqtda bitta web buyruq bajariladi
javob_telegramga = False          # hozirgi buyruq telefondan keldimi (javob ham o'sha yoqqa)
asl_matn = ""                     # hozirgi buyruqning asl yozuvi (katta-kichik harflari bilan)
xom_rejim = False                 # buyruq '/' bilan boshlandi — xabar aynan yozilgandek ketadi
eslatmalar = None                 # qulayliklar.Eslatmalar — miya() ishga tushganda yaratiladi


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
    orta = " ".join(sozlar[boshi + 1:]).strip()
    # FAQAT oxiridagi belgi so'zlarni ("... deb yoz", "... de", "... yozib ber") olib tashlaymiz
    # (gap o'rtasidagi "yoz"ga tegmaymiz)
    orta = re.sub(r"(\s+(deb|de|degin|yozib|yoz|yozgin|yubor|yuboring|jo'nat|ber|bering))+\s*$",
                  "", orta, flags=re.IGNORECASE).strip()
    # ko'p bosqichli gapdagi ortiqcha so'zlar
    filtr = {"kirib", "kir", "kirgin", "kirvol", "qidir", "qidirib", "qidirgin", "va", "keyin",
             "otib", "o'tib", "otgin", "chatga", "chat", "chatiga", "messagega", "messages",
             "message", "direct", "xabarga", "xabar", "yozishma", "topib", "top", "ochib", "och",
             "so'ng", "unga", "shundan", "deb", "de", "yoz", "yozib", "profilga", "profiliga",
             "manashu", "mana", "shu", "o'sha", "osha", "menga", "iltimos"}
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
            nom = [w for w in orta[:j] if w not in filtr]
            return " ".join(nom).strip("\"'«»"), " ".join(orta[j + 1:]).strip()
        if s.endswith("ga") and len(s) > 3 and not s.endswith(("chatga", "messagega", "profilga")):
            nom = [w for w in orta[:j] if w not in filtr] + [s[:-2]]
            return " ".join(nom).strip("\"'«»"), " ".join(orta[j + 1:]).strip()
    return None, None


# ---------- 2.2.1. XABARNI CHIROYLI QILISH ----------
# Oddiy tuzatish (AI kaliti bo'lmasa ham ishlaydi): ko'p uchraydigan imlo xatolari
IMLO = {"suniy": "sun'iy", "sunniy": "sun'iy", "intelekt": "intellekt", "intelektiman": "intellektman",
        "intelektman": "intellektman", "malumot": "ma'lumot", "manba": "manba", "rahmat": "rahmat",
        "raxmat": "rahmat", "iltimos": "iltimos", "xop": "xo'p", "hop": "xo'p", "yaxshimisz": "yaxshimisiz",
        "qalesan": "qalaysan", "qalesiz": "qalaysiz", "tugulgan": "tug'ilgan", "tugilgan": "tug'ilgan",
        "jarvis": "Jarvis", "ertaga": "ertaga", "bugun": "bugun", "togri": "to'g'ri", "notogri": "noto'g'ri",
        "yoq": "yo'q", "boldi": "bo'ldi", "bolsa": "bo'lsa", "kerak": "kerak", "ozbek": "o'zbek"}
# Mazmunga mos emoji (AI bo'lmasa)
EMOJILAR = [(("salom", "assalom"), "👋"), (("rahmat", "tashakkur"), "🙏"),
            (("tug'ilgan kun", "tabrik", "muborak"), "🎉"), (("sevaman", "yaxshi ko'raman"), "❤️"),
            (("jarvis", "sun'iy intellekt", "robot"), "🤖"), (("uxla", "tun", "xayrli tun"), "🌙"),
            (("tong", "xayrli tong"), "☀️"), (("kechir", "uzr"), "🙏"), (("kul", "hazil", "haha"), "😄"),
            (("ovqat", "osh", "tushlik"), "🍽️"), (("futbol", "o'yin"), "⚽"), (("dars", "o'qish"), "📚")]


def asl_korinish(qism):
    """Buyruq ichidagi qismni ASL ko'rinishida (katta-kichik harflari bilan) qaytaradi.
    normallashtir() hamma harfni kichik qiladi — xabar uchun asl yozuv kerak."""
    asl = asl_matn or ""
    kichik = normallashtir(asl) if asl else ""
    if asl and len(kichik) == len(asl.strip()):
        i = kichik.find(qism)
        if i >= 0:
            return asl.strip()[i:i + len(qism)]
    return qism


def oddiy_tuzat(matn):
    """AI'siz tuzatish: bo'shliqlar, tinish belgilari, gap boshidagi katta harf, emoji."""
    matn = re.sub(r"\s+", " ", matn).strip()
    matn = re.sub(r"\s+([.,!?;:])", r"\1", matn)               # "man ." -> "man."
    matn = re.sub(r"([.,!?;:])(?=\S)", r"\1 ", matn)            # "man.men" -> "man. men"
    sozlar = []
    for soz in matn.split(" "):
        toza = soz.strip(".,!?;:").lower()
        if toza in IMLO:
            soz = soz.lower().replace(toza, IMLO[toza])
        sozlar.append(soz)
    matn = " ".join(sozlar)
    matn = re.sub(r"\bjarvis man\b", "Jarvisman", matn, flags=re.IGNORECASE)
    matn = re.sub(r"(^|[.!?]\s+)(\w)", lambda m: m.group(1) + m.group(2).upper(), matn)
    if ISM:
        matn = re.sub(rf"\b{re.escape(ISM.lower())}", ISM, matn)
    if matn and matn[-1] not in ".!?…" and not re.search(r"[\U0001F300-\U0001FAFF]$", matn):
        matn += "."
    kichik = matn.lower()
    emoji = next((e for sozlar_, e in EMOJILAR if any(s in kichik for s in sozlar_)), "🙂")
    return f"{matn} {emoji}"


def xabarni_tayyorla(xabar):
    """Yuboriladigan xabarni tayyorlaydi.
    '/' bilan boshlangan buyruq yoki xabar — AYNAN siz yozgandek ketadi.
    Aks holda — imlo xatolari tuzatiladi va mos emoji qo'shiladi."""
    xom = xom_rejim
    asl = asl_korinish(xabar).strip()
    if asl.startswith("/"):
        xom, asl = True, asl[1:].strip()
    if xom:
        return asl
    asl = asl.strip('"“”«»\'').strip()
    tuzatilgan = sun_iy.tahrir(asl, til()) if sun_iy.bormi() else None
    return tuzatilgan or oddiy_tuzat(asl)


def telegramda_yoz(gap):
    nom, xabar = telegram_xabar_qismlari(gap)
    if not nom or not xabar:
        gapir("Kimga va nima deb yozay? Masalan: telegramdan Alisherga salom deb yoz.")
        return
    for kalit, haqiqiy in TELEGRAM_NOMLAR.items():        # noto'g'ri eshitilgan nomlarni to'g'rilaymiz
        if kalit in nom:
            nom = haqiqiy
    xabar = xabarni_tayyorla(xabar)
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
    xabar = xabarni_tayyorla(xabar)
    if oxirgi_manba == "ovoz" and not tasdiqla(
            f"{ilova} da {nom} ga {xabar} deb yozaymi?"):
        gapir("Bekor qilindi.")
        return
    gapir(f"{ilova} ochilmoqda. {nom} ga xabar yozaman.")
    fonda(_ilovada_yoz_fonda, ilova, nom, xabar)


def _ilovada_yoz_fonda(ilova, nom, xabar):
    jarvisni_yashir(50)                          # butun jarayon davomida yashirin turadi
    if ilova == "instagram":
        _instagramda_yoz(nom, xabar)
    else:
        webbrowser.open(WEB_ILOVALAR[ilova][0])
        time.sleep(9)
        if not boshqaruv.kalitlardan_bos(QIDIRUV_KALITLARI):
            pyautogui.hotkey("ctrl", "k")
        time.sleep(1)
        boshqaruv.matn_yoz(nom)
        time.sleep(3)
        pyautogui.press("enter")
        time.sleep(3)
        boshqaruv.kalitlardan_bos(XABAR_KALITLARI)
        time.sleep(0.5)
        boshqaruv.matn_yoz(xabar)
        time.sleep(0.4)
        pyautogui.press("enter")
        time.sleep(1)
    gapir(f"{ilova} da {nom} ga yozdim: {xabar}")
    telegramga_ekran()
    ui_navbat.put(("korsat",))


def _instagramda_yoz(nom, xabar):
    """Instagram DM: qutini ochib, yangi xabar -> username qidirish -> chat -> yozish.
    Ekrandagi yozuvlarni o'qib bosadi (username matni bo'yicha aniq topadi)."""
    webbrowser.open("https://www.instagram.com/direct/inbox/")
    time.sleep(10)                               # Instagram sekin yuklanadi
    # 1) "Send message" (bo'sh qutidagi tugma) yoki qalam (yangi xabar) belgisini bosamiz
    boshqaruv.kalitlardan_bos(("send message", "xabar yuborish", "new message", "отправить"))
    time.sleep(2)
    # 2) "To:" qidiruv maydoni odatda avtomatik faol — username yozamiz
    boshqaruv.matn_yoz(nom.replace(" ", ""))
    time.sleep(3)
    # 3) natijalardan aynan shu username ustiga bosamiz (matni bo'yicha aniq)
    if not boshqaruv.kalitlardan_bos((nom.replace(" ", ""), nom)):
        pyautogui.press("tab")                   # topolmasa, klaviatura bilan tanlaymiz
    time.sleep(1)
    # 4) "Chat"/"Next" tugmasi bilan suhbatga o'tamiz
    boshqaruv.kalitlardan_bos(("chat", "next", "keyingi", "davom", "далее", "начать"))
    time.sleep(4)
    # 5) xabar maydonini topib yozamiz
    boshqaruv.kalitlardan_bos(("message", "xabar", "write a message", "message…", "сообщение"))
    time.sleep(0.5)
    boshqaruv.matn_yoz(xabar)
    time.sleep(0.4)
    pyautogui.press("enter")
    time.sleep(1)


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


# ---------- TELEFON (ADB orqali) ----------
def telefon_holati_ayt(holat):
    xabarlar = {
        "yoq_adb": "Telefon boshqaruvi uchun ADB dasturi kerak. Uni o'rnatishni tushuntiraman.",
        "yoq_telefon": "Telefon topilmadi. Kabel bilan ulang va telefonda USB debugging yoqing.",
        "ruxsat": "Telefon ekranida 'USB debugging'ga ruxsat bering, keyin qayta urinib ko'ring."}
    gapir(xabarlar.get(holat, "Telefon bilan bog'lana olmadim."))


def telefon_amal(b):
    """Telefon buyrug'ini bajaradi. Bajarilsa True qaytaradi."""
    # Wi-Fi juftlash/ulanish — telefon ulanmagan bo'lsa ham ishlashi kerak (eng birinchi)
    adreslar = re.findall(r"\d{1,3}(?:\.\d{1,3}){3}[:\s]+\d{2,5}", b.replace(" : ", ":"))
    adreslar = [a.replace(" ", ":") for a in adreslar]
    kod6 = re.search(r"\b\d{6}\b", b)
    if bor(b, "juftla", "pair", "juft qil") and adreslar and kod6:
        gapir("Telefonni juftlayapman.")
        ok, chiqish = telefon.juftla(adreslar[0], kod6.group())
        gapir("Juftlandi. Endi 'telefonga ulan' deb ulanish manzilini ayting." if ok
              else "Juftlab bo'lmadi. Kod va manzilni tekshiring.")
        return True
    if bor(b, "ulan", "connect", "bog'lan") and adreslar:
        gapir("Telefonga simsiz ulanyapman.")
        ok, chiqish = telefon.wifi_ulan(adreslar[0])
        if ok:
            sozlama_ozgartir("telefon_adres", adreslar[0], ayt=False)
            gapir("Telefonga ulandim.")
        else:
            gapir("Ulana olmadim. Kompyuter va telefon bir Wi-Fi'da ekanini tekshiring.")
        return True
    if bor(b, "ulan", "connect") and bor(b, "wifi", "wi-fi", "vayfay", "simsiz") \
            and SOZ.get("telefon_adres"):
        gapir("Oldingi manzilga ulanyapman.")
        ok, _ = telefon.wifi_ulan(SOZ["telefon_adres"])
        gapir("Telefonga ulandim." if ok else "Ulana olmadim.")
        return True

    if bor(b, "ulan", "connect", "juftla") and bor(b, "wifi", "wi-fi", "vayfay", "simsiz") \
            and not SOZ.get("telefon_adres"):
        gapir("Simsiz ulash uchun telefonda Dasturchi sozlamalari > Wireless debugging'ni yoqing, "
              "'Pair device with pairing code'ni oching, keyin chiqqan manzil va 6 xonali kodni "
              "menga ayting yoki yozing.")
        return True

    ulangan, holat = telefon.ulanganmi()
    if not ulangan:
        if SOZ.get("telefon_adres"):             # avval simsiz ulangan — qayta urinamiz
            telefon.wifi_ulan(SOZ["telefon_adres"])
            ulangan, holat = telefon.ulanganmi()
    if not ulangan:
        telefon_holati_ayt(holat)
        return True

    if bor(b, "ulan") and bor(b, "wifi", "wi-fi", "vayfay", "simsiz"):
        gapir("Telefon allaqachon ulangan.")
        return True

    if bor(b, "ekran") and bor(b, "rasm", "surat", "skrin", "screenshot", "ol", "yubor", "ko'rsat"):
        gapir("Telefon ekranini olyapman.")
        yol = os.path.join(tempfile.gettempdir(), "jarvis_telefon_ekran.png")
        if not telefon.ekran_rasm(yol):
            gapir("Telefon ekranini ololmadim.")
            return True
        if javob_telegramga and bot:
            fonda(bot.fayl_yubor, yol, "Telefon ekrani")
            gapir("Telefon ekranini yubordim.")
        else:
            manzil = kamera.jarvis_rasm_yoli(
                "Telefon", datetime.datetime.now().strftime("Telefon ekrani %Y-%m-%d %H-%M-%S.png"))
            shutil.copy(yol, manzil)
            gapir("Telefon ekrani Rasmlar papkasidagi Jarvis, Telefon papkasiga saqlandi.")
        return True

    if bor(b, "rasm", "surat", "foto", "video", "galere") and bor(
            b, "ko'chir", "kochir", "olib kel", "kompyuter", "yuklab", "tashla", "yubor"):
        gapir("Telefondagi rasm va videolarni kompyuterga ko'chiryapman. Bu biroz vaqt oladi.")
        fonda(_telefon_rasmlarini_kochir)
        return True

    if bor(b, "uy", "home", "bosh ekran", "asosiy ekran"):
        telefon.tugma("KEYCODE_HOME")
        gapir("Bosh ekranga qaytdim.")
        return True
    if bor(b, "orqaga", "back", "ortga") and not bor(b, "ilova"):
        telefon.tugma("KEYCODE_BACK")
        gapir("Orqaga qaytdim.")
        return True

    # ilova ochish: "telefonda instagramni och"
    if bor(b, "och", "kir", "ishga", "yoq"):
        nom = telefon_ilova_nomi(b)
        paket = telefon.ilova_paketi(nom) if nom else None
        if paket:
            if telefon.ilova_och(paket):
                gapir(f"Telefonda {nom} ochildi.")
            else:
                gapir(f"Telefonda {nom} ochilmadi.")
            return True
        gapir("Telefonda qaysi ilovani ochay? Masalan: telefonda instagramni och.")
        return True

    return False                                 # telefon buyrug'i emas — boshqa ishlov beriladi


def telefon_ilova_nomi(gap):
    ortiqcha = ("telefon", "телефон", "smartfon", "och", "kir", "ishga", "tushir", "dagi",
                "dan", "da", "ilova", "dastur", "menga", "ber")
    sozlar = []
    for s in gap.split():
        if s.startswith(ortiqcha):
            continue
        if len(s) > 4 and s.endswith(("ni", "ga", "di")):
            s = s[:-2]
        sozlar.append(s)
    return " ".join(sozlar).strip()


def _telefon_rasmlarini_kochir():
    manzil = kamera.jarvis_rasm_yoli("Telefon", datetime.datetime.now().strftime("Telefon rasmlari %Y-%m-%d"))
    muvaffaqiyat, chiqish = telefon.fayllarni_olib_kel("/sdcard/DCIM/Camera", manzil)
    if muvaffaqiyat:
        gapir(f"Telefon rasmlari ko'chirildi. Papka nomi: {os.path.basename(manzil)}.")
    else:
        gapir("Rasmlarni ko'chira olmadim. Telefonda ruxsatlarni tekshiring.")


# ---------- TELEFON ILOVASI SERVERI ----------
def web_tasdiqla_ogohlantir():
    """Web (telefon ilovasi) rejimida xavfli buyruq tasdiqlanmaydi — xavfsizlik uchun."""
    return False


# ---------- TELEGRAM AKKAUNT: do'stlardan kelgan xabarni o'qish va javob yozish ----------
tga = None                        # telegram_akkaunt.Akkaunt
tg_navbat = queue.Queue()         # kelgan xabarlar — Jarvis bo'sh bo'lganda birma-bir so'raladi
tg_oqilmagan = []                 # "yo'q" deyilganlari — keyin "xabarlarni o'qi" desangiz o'qiladi
TG_TURLARI = {"ovoz": "ovozli xabar yubordi", "video": "video yubordi", "rasm": "rasm yubordi",
              "stiker": "stiker yubordi", "fayl": "fayl yubordi"}


def tga_ishga_tushir():
    """Kompyuter yonganda — saqlangan sessiya bilan o'zi ulanadi (kod qayta so'ralmaydi)."""
    global tga
    if not (SOZ.get("tga_api_id") and SOZ.get("tga_api_hash")):
        return None
    try:
        import telegram_akkaunt
    except ImportError:
        print("(Telegram akkaunt uchun: pip install telethon)")
        return None
    if tga is None:
        tga = telegram_akkaunt.Akkaunt(lambda x: tg_navbat.put(x))
    tga.dostlar = list(SOZ.get("tga_dostlar") or [])
    tga.hammasi = bool(SOZ.get("tga_hammasi"))
    try:
        return tga.ishga_tushir(SOZ["tga_api_id"], SOZ["tga_api_hash"])
    except Exception as xato:
        tga.holat = "xato"
        tga.oxirgi_xato = telegram_akkaunt.xato_matni(xato)
        print(f"(Telegram akkauntga ulanib bo'lmadi: {type(xato).__name__}: {xato})")
        return None


def _tg_xabar_matni(x):
    if x["tur"] == "matn":
        return f"{x['kim']} yozibdi: {x['matn']}"
    gap = f"{x['kim']} {TG_TURLARI.get(x['tur'], 'xabar yubordi')}"
    if x["tur"] == "rasm" and x.get("rasm") and sun_iy.bormi():
        tavsif = sun_iy.rasm_tahlil(x["rasm"], "Do'stim Telegramda yuborgan rasm. Unda nima bor?", til())
        if tavsif:                                       # rasm — bepul Groq ko'radi
            gap += f". Rasmda: {tavsif}"
    if x.get("emoji"):
        gap += f" {x['emoji']}"
    if x["matn"]:
        gap += f". Izohi: {x['matn']}"
    return gap


def tg_xabarni_ol(x, soradi=False):
    """Do'stdan xabar keldi: o'qib beraymi? -> o'qiydi -> javob yozaymi? -> nima deb? -> to'g'rimi? -> yuboradi."""
    global javob_telegramga, oxirgi_manba
    javob_telegramga, oxirgi_manba = False, "ovoz"       # kompyuterda ovoz chiqarib so'raymiz
    kim = x["kim"]
    ui_navbat.put(("korsat",))
    if not soradi and not tasdiqla(f"{ISM}, {kim}dan xabar keldi. O'qib beraymi?"):
        tg_oqilmagan.append(x)
        gapir("Mayli. Keyin o'qish uchun: xabarlarni o'qi, deng.")
        return
    gapir("📩 " + _tg_xabar_matni(x))
    fonda(tga.oqildi, x["chat_id"], x["xabar_id"])      # Telegram'da "o'qildi" bo'ladi
    if not tasdiqla(f"{kim}ga javob yozaymi?"):
        gapir("Mayli.")
        return
    for _ in range(3):
        gapir("Nima deb yozay?")
        aytgan = eshit(20)
        if not aytgan:
            gapir("Eshitmadim.")
            continue
        if bor(aytgan, "bekor", "kerak emas", "yozma", "qo'y", "отмена"):
            gapir("Bekor qildim.")
            return
        tayyor = xabarni_tayyorla(asl_matn or aytgan)     # imlo tuzatiladi, emoji qo'shiladi ('/' — aynan)
        if tasdiqla(f"{kim}ga shunday yozaman: {tayyor}. To'g'ri yozdimmi?"):
            try:
                tga.yubor(x["chat_id"], tayyor)
            except Exception as xato:
                print(f"(Telegram yuborish xatosi: {xato})")
                gapir("Yubora olmadim. Internetni tekshiring.")
                return
            gapir(f"✉️ {kim}ga yuborildi.")
            return
        gapir("Mayli, qaytadan ayting.")
    gapir("Bekor qildim.")


def tg_oqilmaganlarni_oqi():
    if not tga or tga.holat != "ulangan":
        gapir("Telegram akkaunt ulanmagan. Chat sozlamalarida Telegram akkaunt bo'limidan ulang.")
        return
    if not tg_oqilmagan:
        gapir("Yangi xabar yo'q.")
        return
    while tg_oqilmagan:
        tg_xabarni_ol(tg_oqilmagan.pop(0), soradi=True)


# ---------- INSTAGRAM (rasmiy API): Reels joylash, izohlar, statistika ----------
_ig = None


def ig_ol():
    """Ulangan Instagram (yoki None). Birinchi chaqiruvda akkaunt id'si topiladi."""
    global _ig
    if not SOZ.get("ig_token"):
        return None
    if _ig is None or _ig.token != SOZ["ig_token"]:
        import instagram
        _ig = instagram.Instagram(SOZ["ig_token"])
        _ig.id, _ig.username = SOZ.get("ig_id"), SOZ.get("ig_username")
        if not _ig.id:
            _ig.ulan()
    return _ig


def _ig_vaqt(b):
    """'ertaga soat 19 da' / 'soat 20:30 da' -> unix vaqt yoki None."""
    m = re.search(r"soat (\d{1,2})(?:[:.](\d{2}))?", b)
    if not m:
        return None
    hozir = datetime.datetime.now()
    vaqt = hozir.replace(hour=int(m.group(1)) % 24, minute=int(m.group(2) or 0), second=0, microsecond=0)
    if "ertaga" in b or vaqt <= hozir:
        vaqt += datetime.timedelta(days=1)
    return vaqt.timestamp()


def _ig_joyla_fonda(fayl, tavsif, rejadan=False):
    try:
        ig = ig_ol()
        media_id = ig.joyla(fayl, tavsif, holat=lambda m: ui_navbat.put(("jarvis", "📸 " + m)))
        havola = next((p.get("permalink") for p in ig.postlar(3) if p.get("id") == media_id), "")
        gapir("✅ Instagramga joylandi!" + (f" {havola}" if havola else ""), tarjima_qil=False)
    except Exception as xato:
        gapir(f"Instagramga joylab bo'lmadi: {xato}")
    if rejadan:
        sozlama_ozgartir("ig_rejalar", [r for r in SOZ.get("ig_rejalar", []) if r.get("fayl") != fayl], ayt=False)


def ig_fon_bormi():
    """Orqa fon rejimi tayyormi: kutubxona bor va Instagram'ga bir marta kirilgan."""
    try:
        import instagram_brauzer
        return instagram_brauzer.bormi() and bool(SOZ.get("ig_brauzer_kirgan"))
    except Exception:
        return False


def _ig_fonda_joyla(fayl, tavsif):
    """Ko'rinmas brauzerda joylaydi — ekran, sichqoncha va klaviatura band bo'lmaydi."""
    import instagram_brauzer
    try:
        instagram_brauzer.joyla(fayl, tavsif, holat=lambda m: ui_navbat.put(("jarvis", "📸 " + m)))
        gapir("✅ Instagramga joylandi!")
    except Exception as xato:
        if "kirilmagan" in str(xato):
            sozlama_ozgartir("ig_brauzer_kirgan", False, ayt=False)
        print(f"(Instagram orqa fon xatosi: {type(xato).__name__}: {xato})")
        gapir(f"Instagramga joylab bo'lmadi: {xato}")


def _ig_rejadan_brauzerda(fayl, tavsif):
    sozlama_ozgartir("ig_rejalar", [r for r in SOZ.get("ig_rejalar", []) if r.get("fayl") != fayl], ayt=False)
    if ig_fon_bormi():
        _ig_fonda_joyla(fayl, tavsif)
    else:
        _ig_brauzerda_joyla(fayl, tavsif)


def ig_rejalarni_tikla():
    """Kompyuter qayta yonganda rejalashtirilgan postlar davom etadi (kechikkanlari darhol joylanadi)."""
    for r in list(SOZ.get("ig_rejalar", [])):
        qoldi = r["vaqt"] - time.time()
        if not os.path.exists(r["fayl"]):
            continue
        if qoldi <= 0:
            print(f"(Instagram: rejadagi post kechikdi — hozir joylayman: {os.path.basename(r['fayl'])})")
        if r.get("brauzer"):
            threading.Timer(max(qoldi, 60), _ig_rejadan_brauzerda, args=(r["fayl"], r["tavsif"])).start()
        else:
            threading.Timer(max(qoldi, 5), _ig_joyla_fonda, args=(r["fayl"], r["tavsif"], True)).start()


IG_BOSQICH = {                   # Instagram veb-sahifasidagi tugmalar (ingliz / rus / o'zbek / turk)
    "yarat": ("Create", "Создать", "Yaratish", "Oluştur"),
    "post": ("Post", "Публикация", "Gönderi"),
    "tanla": ("Select from computer", "Выбрать на компьютере", "Kompyuterdan tanlash", "Bilgisayardan seç"),
    "ok": ("OK",),
    "keyingi": ("Next", "Далее", "Keyingi", "İleri"),
    "tavsif": ("Write a caption", "Добавьте подпись", "Izoh yozing", "Açıklama yaz"),
    "ulash": ("Share", "Поделиться", "Ulashish", "Paylaş"),
    "tayyor": ("has been shared", "been shared", "опубликован", "опубликовано", "paylaşıldı", "ulashildi"),
}


def _ig_kut_bos(kalitlar, urinish=6, oraliq=2.0):
    """Ekranda tugma paydo bo'lishini kutib bosadi (sahifa sekin yuklanishi mumkin)."""
    for _ in range(urinish):
        try:
            if boshqaruv.kalitlardan_bos(kalitlar):
                return True
        except Exception as xato:
            print(f"(Ekranni o'qib bo'lmadi: {xato})")
        time.sleep(oraliq)
    return False


def _ig_brauzerda_joyla(fayl, tavsif):
    """API'siz: brauzerdagi Instagram'da (siz kirgan akkauntda) Jarvis tugmalarni o'zi bosadi.
    Oxirgi 'Ulashish' tugmasini xavfsizlik uchun SIZ bosasiz."""
    if tavsif:
        pyperclip.copy(tavsif)                         # har ehtimolga: tavsif nusxada turadi
    jarvisni_yashir(90)
    webbrowser.open("https://www.instagram.com/")
    time.sleep(9)
    qolgan = ("Qolganini qo'lda qiling: '+ Yaratish' → 'Kompyuterdan tanlash' → videoni tanlang → 'Keyingi' → "
              "'Keyingi' → tavsif joyiga Ctrl+V → 'Ulashish'.")
    if not _ig_kut_bos(IG_BOSQICH["yarat"]):
        kompyuter.papkada_korsat(fayl)
        gapir("Instagram sahifasida 'Yaratish' tugmasini topolmadim — Instagram'ga kirganmisiz? " + qolgan)
        return
    time.sleep(1.5)
    boshqaruv.kalitlardan_bos(IG_BOSQICH["post"])     # yangi menyuda 'Post' bandi bo'ladi
    if not _ig_kut_bos(IG_BOSQICH["tanla"]):
        kompyuter.papkada_korsat(fayl)
        gapir("'Kompyuterdan tanlash' tugmasini topolmadim. " + qolgan)
        return
    time.sleep(2.5)                                    # Windows fayl tanlash oynasi ochiladi
    pyperclip.copy(fayl)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.4)
    pyautogui.press("enter")
    time.sleep(6)                                      # video yuklanadi
    boshqaruv.kalitlardan_bos(IG_BOSQICH["ok"])       # "Video endi Reels bo'lib joylanadi" oynasi
    for _ in range(2):                                 # Kesish -> Tahrirlash -> Tavsif
        if not _ig_kut_bos(IG_BOSQICH["keyingi"], urinish=5):
            gapir("'Keyingi' tugmasini topolmadim. " + qolgan)
            return
        time.sleep(2.5)
    if tavsif:
        if _ig_kut_bos(IG_BOSQICH["tavsif"], urinish=4):
            time.sleep(0.5)
            pyperclip.copy(tavsif)
            pyautogui.hotkey("ctrl", "v")
        else:
            gapir("Tavsif maydonini topolmadim — uni bosib, Ctrl+V qiling.")
            return
    if not SOZ.get("ig_avto_ulash"):
        ui_navbat.put(("korsat",))
        gapir("Hammasi tayyor! Tekshirib ko'ring va 'Ulashish' (Share) tugmasini o'zingiz bosing.")
        return
    time.sleep(1)
    if not _ig_kut_bos(IG_BOSQICH["ulash"], urinish=4):
        gapir("'Ulashish' tugmasini topolmadim — uni o'zingiz bosing.")
        return
    for _ in range(30):                                # 2 daqiqagacha: "Reel ulashildi" yozuvini kutamiz
        time.sleep(4)
        try:
            rasm = os.path.join(tempfile.gettempdir(), "jarvis_ocr.png")
            pyautogui.screenshot(rasm)
            sozlar = boshqaruv.ekran_sozlari(rasm)
            if any(boshqaruv.yozuvni_top(k, sozlar) for k in IG_BOSQICH["tayyor"]):
                ui_navbat.put(("korsat",))
                gapir("✅ Instagramga joylandi!")
                return
        except Exception as xato:
            print(f"(Tekshirib bo'lmadi: {xato})")
            break
    ui_navbat.put(("korsat",))
    gapir("Ulashish tugmasini bosdim. Instagram'da joylanganini bir ko'rib qo'ying.")


def ig_joylash(b):
    try:
        ig = ig_ol()
    except Exception as xato:
        print(f"(Instagram API: {xato}) — brauzer rejimiga o'taman")
        ig = None
    import instagram
    ortiqcha = {"instagram", "instagramga", "insta", "instaga", "videoni", "video", "reels", "joyla", "yukla",
                "qo'y", "post", "qil", "ertaga", "soat", "da", "ga", "ni", "mening", "shu", "oxirgi"}
    sozlar = [s for s in re.findall(r"[\w']+", b) if s not in ortiqcha and not s.isdigit()]
    papkalar = [kompyuter.desktop_yoli(), os.path.expanduser(r"~\Videos"), os.path.expanduser(r"~\Downloads"),
                os.path.expanduser("~/Videos"), os.path.expanduser("~/Downloads")]
    fayl = instagram.video_top(sozlar, papkalar)
    if not fayl:
        gapir("Video topmadim. Videoni Ish stoliga, Videos yoki Downloads papkasiga qo'yib, qayta ayting.")
        return
    if not tasdiqla(f"{os.path.basename(fayl)} videosini Instagramga joylaymi?"):
        gapir("Mayli. Kerakli videoni Ish stoliga qo'yib, nomini aytsangiz, o'shani joylayman.")
        return
    gapir("Video nima haqida? Qisqacha ayting — tavsif va heshteglarni o'zim yozaman. Tavsifsiz desangiz, bo'sh qoladi.")
    aytgan = eshit(25)
    if bor(aytgan, "tavsifsiz", "kerak emas", "bo'sh"):
        tavsif = ""
    elif not aytgan:
        gapir("Eshitmadim. Bekor qildim.")
        return
    else:
        asl = (asl_matn or aytgan).strip()
        tavsif = asl[1:].strip() if asl.startswith("/") else (sun_iy.instagram_tavsif(asl, til()) or asl)
    if tavsif and not tasdiqla(f"Tavsif shunday bo'ladi: {tavsif}. Shu bilan joylaymi?"):
        gapir("Bekor qildim. Qaytadan urinib ko'ring.")
        return
    vaqt = _ig_vaqt(b)
    if not ig and ig_fon_bormi():                       # ko'rinmas brauzer — kompyuterdan bemalol foydalanasiz
        if vaqt:
            rejalar = [r for r in SOZ.get("ig_rejalar", []) if r.get("fayl") != fayl]
            sozlama_ozgartir("ig_rejalar", rejalar + [{"vaqt": vaqt, "fayl": fayl, "tavsif": tavsif,
                                                       "brauzer": True}], ayt=False)
            threading.Timer(vaqt - time.time(), _ig_rejadan_brauzerda, args=(fayl, tavsif)).start()
            gapir(f"Rejalashtirildi: {datetime.datetime.fromtimestamp(vaqt):%d-%m soat %H:%M} da orqa fonda "
                  "o'zim joylayman. Shu vaqtda kompyuter yoqiq bo'lsin.")
            return
        gapir("Orqa fonda joylayapman — kompyuterdan bemalol foydalanavering. Tayyor bo'lsa aytaman.")
        fonda(_ig_fonda_joyla, fayl, tavsif)
        return
    if not ig:                                          # API ulanmagan — brauzer orqali (parolsiz, xavfsiz)
        if vaqt and SOZ.get("ig_avto_ulash"):
            rejalar = [r for r in SOZ.get("ig_rejalar", []) if r.get("fayl") != fayl]
            sozlama_ozgartir("ig_rejalar", rejalar + [{"vaqt": vaqt, "fayl": fayl, "tavsif": tavsif,
                                                       "brauzer": True}], ayt=False)
            threading.Timer(vaqt - time.time(), _ig_rejadan_brauzerda, args=(fayl, tavsif)).start()
            gapir(f"Rejalashtirildi: {datetime.datetime.fromtimestamp(vaqt):%d-%m soat %H:%M} da o'zim joylayman. "
                  "Shu vaqtda kompyuter yoqiq, ekran qulflanmagan va Chrome'da Instagram'ga kirilgan bo'lsin.")
            return
        if vaqt and not tasdiqla("Vaqtga qo'yish uchun sozlamalarda Instagram bo'limida 'To'liq avtomatik'ni yoqing. "
                                 "Hozir joylaymi?"):
            gapir("Mayli.")
            return
        gapir("Instagram'ni ochib, videoni o'zim yuklayman. Bu vaqtda sichqoncha va klaviaturaga tegmang.")
        fonda(_ig_brauzerda_joyla, fayl, tavsif)
        return
    if vaqt:
        rejalar = [r for r in SOZ.get("ig_rejalar", []) if r.get("fayl") != fayl]
        sozlama_ozgartir("ig_rejalar", rejalar + [{"vaqt": vaqt, "fayl": fayl, "tavsif": tavsif}], ayt=False)
        threading.Timer(vaqt - time.time(), _ig_joyla_fonda, args=(fayl, tavsif, True)).start()
        gapir(f"Rejalashtirildi: {datetime.datetime.fromtimestamp(vaqt):%d-%m soat %H:%M} da joylayman. "
              "Shu vaqtda kompyuter yoqiq bo'lsin.")
        return
    gapir("Joylayapman. Bu bir necha daqiqa olishi mumkin — tayyor bo'lsa aytaman.")
    fonda(_ig_joyla_fonda, fayl, tavsif)


def ig_izohlar():
    try:
        ig = ig_ol()
        if not ig:
            gapir("Instagram ulanmagan. Chat sozlamalarida Instagram bo'limiga kalitni qo'ying.")
            return
        korilgan = set(SOZ.get("ig_korilgan", []))
        yangi = []
        for p in ig.postlar(3):
            for iz in ig.izohlar(p["id"]):
                if iz["id"] not in korilgan and iz.get("username") != ig.username:
                    yangi.append(iz)
    except Exception as xato:
        gapir(f"Izohlarni ololmadim: {xato}")
        return
    if not yangi:
        gapir("Yangi izoh yo'q.")
        return
    gapir(f"{len(yangi)} ta yangi izoh bor.")
    for iz in yangi[:5]:
        korilgan.add(iz["id"])
        gapir(f"{iz.get('username', 'Kimdir')} yozibdi: {iz.get('text', '')}")
        if not tasdiqla("Javob yozaymi?"):
            continue
        gapir("Nima deb yozay?")
        aytgan = eshit(20)
        if not aytgan:
            gapir("Eshitmadim, keyingisiga o'taman.")
            continue
        tayyor = xabarni_tayyorla(asl_matn or aytgan)
        if tasdiqla(f"Shunday yozaman: {tayyor}. To'g'rimi?"):
            try:
                ig.javob_yoz(iz["id"], tayyor)
                gapir("Javob yozildi.")
            except Exception as xato:
                gapir(f"Yozib bo'lmadi: {xato}")
    sozlama_ozgartir("ig_korilgan", list(korilgan)[-500:], ayt=False)


def ig_statistika():
    try:
        ig = ig_ol()
        if not ig:
            gapir("Instagram ulanmagan. Chat sozlamalarida Instagram bo'limiga kalitni qo'ying.")
            return
        a = ig.akkaunt()
        gap = f"Instagram @{a.get('username')}: {a.get('followers_count', 0)} ta obunachi, {a.get('media_count', 0)} ta post."
        postlar = ig.postlar(1)
        if postlar:
            p = postlar[0]
            s = ig.statistika(p["id"])
            qismlar = [f"{s['views']} ta ko'rish" if s.get("views") is not None else "",
                       f"{p.get('like_count', s.get('likes', 0))} ta layk", f"{p.get('comments_count', 0)} ta izoh"]
            gap += " Oxirgi post: " + ", ".join(q for q in qismlar if q) + "."
        gapir(gap)
    except Exception as xato:
        gapir(f"Statistikani ololmadim: {xato}")


def eslatma_vaqti(ish, kechikdi=False):
    """Eslatma vaqti keldi: ovoz chiqarib aytadi, Telegram'ga yuboradi, chatda ko'rinadi."""
    matn = f"⏰ {ISM}, eslatma: {ish}!"
    if kechikdi:
        matn += " (Kompyuter o'chiq bo'lgani uchun biroz kechikdi.)"
    if bot and bot.egasi and not javob_telegramga:
        fonda(bot.yoz, matn)                    # telefonda ham ko'rasiz
    ui_navbat.put(("korsat",))
    gapir(matn, uzilmas=True)


# ---------- UY KAMERALARI (Hikvision) ----------
kuzatuvchilar = {}                # kamera nomi -> kamera.Kuzatuvchi (harakatni kuzatish)


def kameralar():
    """Barcha kameralar + eshik qurilmasi (u ham kamera: jonli ko'rish, kuzatish mumkin).
    Eshik oxirida — "kamera 4" kabi raqamlar o'zgarmasin."""
    royxat = [k for k in SOZ.get("kameralar", []) if k.get("ip")]
    e = eshik_qurilmasi()
    if e and all(k.get("ip") != e["ip"] for k in royxat):
        royxat.append(e)
    return royxat


def _parolni_izla(k):
    """Kamera paroli xato bo'lsa — boshqa saqlangan kameralar/eshik parolini sinab ko'radi.
    Mos kelsa sozlamaga yozadi va yangilangan kamera sozlamasini qaytaradi, bo'lmasa None."""
    boshqalar = [x for x in SOZ.get("kameralar", []) if x.get("ip") and x.get("nom") != k.get("nom")]
    if SOZ.get("eshik", {}).get("ip") and not k.get("eshik"):
        boshqalar.append(SOZ["eshik"])
    juft = kamera.parol_izla(k, [(x.get("login"), x.get("parol")) for x in boshqalar])
    if not juft:
        return None
    login, parol = juft
    if k.get("eshik") and SOZ.get("eshik", {}).get("ip") == k.get("ip"):
        sozlama_ozgartir("eshik", dict(SOZ["eshik"], login=login, parol=parol), ayt=False)
    else:
        royxat = [dict(x, login=login, parol=parol) if x.get("nom") == k.get("nom") else x
                  for x in SOZ.get("kameralar", [])]
        sozlama_ozgartir("kameralar", royxat, ayt=False)
        if k.get("nom") in kuzatuvchilar:
            kuzatuvni_yoq(True)                               # kuzatuv yangi parol bilan qayta boshlansin
    print(f"(Kamera '{k.get('nom')}' paroli boshqa kameranikiga mos keldi — saqlandi)")
    return dict(k, login=login, parol=parol)


def eshik_qurilmasi():
    """Chatdagi 'Eshik' bo'limida qo'shilgan domofon/eshik kamerasi (bo'lmasa None)."""
    e = SOZ.get("eshik") or {}
    return dict(e, nom=e.get("nom") or "Eshik", eshik=True) if e.get("ip") else None


KAMERA_SONLARI = {"bir": 1, "birinchi": 1, "ikki": 2, "ikkinchi": 2, "uch": 3, "uchinchi": 3,
                  "to'rt": 4, "tort": 4, "to'rtinchi": 4, "tortinchi": 4, "besh": 5, "beshinchi": 5,
                  "olti": 6, "oltinchi": 6, "yetti": 7, "yettinchi": 7, "sakkiz": 8, "sakkizinchi": 8,
                  "to'qqiz": 9, "to'qqizinchi": 9, "o'n": 10, "o'ninchi": 10,
                  "один": 1, "два": 2, "три": 3, "четыре": 4, "пять": 5, "one": 1, "two": 2,
                  "three": 3, "four": 4, "five": 5}


def _kamera_raqami(b):
    """'kamera 4', '4-kamera', 'to'rtinchi kamera', 'kamera to'rt' -> 4. Topilmasa None."""
    son = r"(\d{1,3}|" + "|".join(sorted(map(re.escape, KAMERA_SONLARI), key=len, reverse=True)) + ")"
    for naqsh in (r"(?:kamera|камера|camera)\w*\s*(?:raqam\w*\s*|№\s*|#\s*)?" + son
                  + r"(?:ni|ning|ga|dan|da|dagi|chi|inchi|nchi)?\b",
                  son + r"\s*-?\s*(?:chi|inchi|nchi|ninchi)?\s*(?:kamera|камера|camera)"):
        m = re.search(naqsh, b)
        if m:
            q = m.group(1)
            return int(q) if q.isdigit() else KAMERA_SONLARI.get(q)
    return None


def kamera_tanla(b):
    """Gapdagi kamerani tanlaydi: aniq nomi ("hovli"), raqami ("kamera 4", "to'rtinchi kamera"),
    bo'lmasa birinchisi. (Avval "kamera" so'zining o'zi mos kelib, boshqa kamera tanlanardi.)"""
    royxat = kameralar()
    if not royxat:
        return None
    # 1) to'liq nom gapda bor — eng uzun nom birinchi ("Kamera 12" "Kamera 1"dan oldin)
    for k in sorted(royxat, key=lambda k: -len(k.get("nom", ""))):
        nom = normallashtir(k.get("nom", ""))
        if nom and re.search(r"(?<!\w)" + re.escape(nom) + r"(?!\d)", b):
            return k
    # 2) raqam: nomida shu raqam bor kamera, bo'lmasa ro'yxatdagi tartib raqami
    n = _kamera_raqami(b)
    if n is not None:
        for k in royxat:
            if re.search(rf"(?<!\d){n}(?!\d)", k.get("nom", "")) or k.get("ip", "").endswith(f".{n}"):
                return k
        if 1 <= n <= len(royxat):
            return royxat[n - 1]
    # 3) nomdagi ma'noli so'z ("hovli", "eshik", "ko'cha") — umumiy "kamera" so'zi hisobga olinmaydi
    for k in royxat:
        for soz in normallashtir(k.get("nom", "")).split():
            if len(soz) >= 4 and soz not in ("kamera", "camera", "камера") and not soz.isdigit() \
                    and soz[:max(4, len(soz) - 2)] in b:
                return k
    return royxat[0]


def uy_kamera_rasmi(b):
    """Uy kamerasidan rasm: chatda ko'rsatadi, AI bo'lsa — rasmda nima borligini aytadi,
    telefondan so'ralgan bo'lsa — Telegram'ga yuboradi."""
    k = kamera_tanla(b)
    if not k:
        gapir("Hali kamera qo'shilmagan. Chatdagi Sozlamalar, Kamera bo'limida qo'shing.")
        return
    gapir(f"{k['nom']} kamerasiga ulanyapman.")
    yol, xato = kamera.rasm_ol(k)
    if not yol:
        gapir(f"Rasm ololmadim: {xato}.")
        return
    tavsif = sun_iy.rasm_tahlil(yol, "", til()) if sun_iy.bormi() else None
    matn = f"📹 {k['nom']}: " + (tavsif or "hozirgi holat.")
    telefondan = javob_telegramga or oxirgi_manba == "web"
    if bot and bot.egasi and telefondan:
        fonda(bot.rasm_yubor, yol, matn)
        matn += " Rasmni Telegramga yubordim."
    if oxirgi_manba in ("ovoz", "yozuv") and (chat_jarayon is None or chat_jarayon.poll() is not None):
        chat_och()                                     # rasm chatda ko'rinadi
    gapir(matn, tarjima_qil=not tavsif, rasm=yol)


def kamera_harakat(k, yol, soni=0):
    """Kamerada odam paydo bo'ldi: kompyuterda jonli video o'zi ochiladi (chat yopiq bo'lsa ham),
    chatga va Telegram'ga belgilangan rasm bilan xabar keladi."""
    kim = f"{soni} ta odam" if soni > 1 else "odam"
    if soni == 0:
        kim = "harakat"                                     # odam modeli yo'q — eski usul
    # Avval jonli videoni ochamiz — kutib o'tirmasdan, nima bo'layotganini darhol ko'rasiz
    if chat_jarayon is None or chat_jarayon.poll() is not None:
        chat_och(jonli=k["nom"])
    tavsif = sun_iy.rasm_tahlil(yol, "Uy kamerasida odam paydo bo'ldi. Kim, nima qilyapti?",
                                til()) if sun_iy.bormi() else None
    matn = f"🚨 {k['nom']}: {kim} ko'rindi! {datetime.datetime.now():%H:%M:%S}" + (f" — {tavsif}" if tavsif else "")
    print(matn)
    arxiv.yoz("jarvis", matn, "kamera", rasm=yol, jonli=k["nom"])   # chat ochiq bo'lsa — jonli video o'zi chiqadi
    if bot and bot.egasi:
        bot.rasm_yubor(yol, matn)
    if SOZ.get("kamera_ovoz"):
        gapir(f"Diqqat! {k['nom']} kamerasida {kim} bor.", uzilmas=True)


def kuzatuvni_yoq(yoqilsin=True):
    """Barcha kameralarda harakatni kuzatishni yoqadi/o'chiradi. Nechta kamera kuzatilyapti — qaytaradi."""
    for kuz in kuzatuvchilar.values():
        kuz.toxtat()
    kuzatuvchilar.clear()
    if yoqilsin:
        for k in kameralar():
            kuzatuvchilar[k["nom"]] = kamera.Kuzatuvchi(k, kamera_harakat)
    if SOZ.get("kamera_kuzatuv") != yoqilsin:
        sozlama_ozgartir("kamera_kuzatuv", yoqilsin, ayt=False)   # qayta ishga tushganda ham davom etadi
    return len(kuzatuvchilar)


# ---------- ESHIK VA YUZ TANISH ----------
# Faqat aniq ibora: "eshikni och", "darvozani ochib ber", "открой дверь".
# ("eshik oldidagi kamerani och" — eshikni OCHMAYDI)
ESHIK_OCH_RE = re.compile(r"\b(eshik|darvoza|kalitka)(ni)?\s+(och|ochib|ochgin|ochvor|ochib ber|ochiver)\b"
                          r"|открой\s+двер|open the door")
qorovullar = {}                   # kamera nomi -> yuz.EshikQorovuli


def eshik_kamerasi():
    """Eshik: 'Eshik' bo'limidagi qurilma; bo'lmasa eshik deb belgilangan kamera; bo'lmasa birinchisi."""
    e = eshik_qurilmasi()
    if e:
        return e
    royxat = [k for k in SOZ.get("kameralar", []) if k.get("ip")]
    return next((k for k in royxat if k.get("eshik")), royxat[0] if royxat else None)


def _kamerani_saqla(k):
    if eshik_qurilmasi() and k.get("ip") == eshik_qurilmasi()["ip"]:
        sozlama_ozgartir("eshik", {x: v for x, v in k.items() if x != "eshik"}, ayt=False)
        return
    royxat = [x if x.get("nom") != k.get("nom") else k for x in SOZ.get("kameralar", [])]
    sozlama_ozgartir("kameralar", royxat, ayt=False)


def eshikni_och(kim="", k=None):
    """Eshikni ochadi va egasiga xabar beradi. (ok, xabar)."""
    k = k or eshik_kamerasi()
    if not k:
        return False, "Eshik kamerasi qo'shilmagan"
    ok, xabar, usul = kamera.eshik_och(k)
    if ok:
        if usul and k.get("eshik_usul") != usul:
            _kamerani_saqla(dict(k, eshik_usul=usul))       # keyingi safar darhol shu usul
        izoh = f"🚪 Eshik ochildi ({k['nom']}){' — ' + kim if kim else ''} {datetime.datetime.now():%H:%M}"
        arxiv.yoz("jarvis", izoh, "kamera")
        if bot and bot.egasi and not javob_telegramga:
            fonda(bot.yoz, izoh)
    return ok, xabar


def eshik_buyrugi():
    k = eshik_kamerasi()
    if not k:
        gapir("Hali kamera qo'shilmagan. Chatdagi Sozlamalar, Kamera bo'limida qo'shing.")
        return
    # Ovoz bilan — tasdiq so'raymiz (tashqaridan baqirib ochirib bo'lmasin).
    # Telefon/Telegram/chat — egasi ekani tasdiqlangan (PIN / juftlangan bot / shu kompyuter).
    if oxirgi_manba == "ovoz" and not tasdiqla("Eshikni ochaymi?"):
        gapir("Yaxshi, ochmadim.")
        return
    if oxirgi_manba == "web" and len(str(SOZ.get("telefon_pin") or "")) < 6:
        gapir("Xavfsizlik uchun telefondan eshik ochish uchun PIN kamida 6 raqam bo'lishi kerak. "
              "Kompyuterdagi chat sozlamalarida PIN'ni almashtiring.")
        return
    manba = {"ovoz": "ovoz bilan", "web": "telefon ilovasidan", "telegram": "Telegramdan",
             "chat": "chatdan"}.get(oxirgi_manba, "")
    ok, xabar = eshikni_och(manba, k)
    gapir("Eshik ochildi. 🚪" if ok else f"Eshikni ocha olmadim: {xabar}.")


def eshik_skaner(och=True):
    """Eshik oldidagi yuzni HOZIR tekshiradi (avtomatik kuzatuv tanimagan bo'lsa ham):
    ~3 soniya kadrlar olinadi, tanish yuz 2 kadrda aniq tanilsa — eshik ochiladi.
    (ok, xabar, rasm_yoli) qaytaradi."""
    import cv2
    k = eshik_kamerasi()
    if not k:
        return False, "Eshik qurilmasi qo'shilmagan", None
    try:
        t = yuz.Tanuvchi.ol()
    except Exception as xato:
        return False, f"Yuz tanish modeli yuklanmadi: {xato}", None
    if not t.odamlar():
        return False, "Hali hech kimning yuzi o'rgatilmagan", None
    tugash = time.time() + 3.5
    tanishlar, eng_yaxshi, eng_rasm, yuzli_kadr = {}, (None, 0.0), None, 0
    for rasm in kamera.kadrlar(k, fps=5, ishlasin=lambda: time.time() < tugash):
        yuzlar = t.yuzlar(rasm)
        if not yuzlar:
            eng_rasm = eng_rasm if eng_rasm is not None else rasm
            continue
        yuzli_kadr += 1
        ism, ball = t.kim(yuzlar[0][1])
        if ball > eng_yaxshi[1]:
            eng_yaxshi, eng_rasm = (ism, ball), rasm
        if ism and ball >= yuz.ESHIK_CHEGARA:
            tanishlar[ism] = tanishlar.get(ism, 0) + 1
    if eng_rasm is None:
        return False, "Eshik kamerasidan rasm olib bo'lmadi", None
    yol = kamera._yangi_yol(k, "-skaner")
    cv2.imwrite(yol, eng_rasm)
    tanilgan = max(tanishlar, key=tanishlar.get) if tanishlar else None
    if tanilgan and tanishlar[tanilgan] >= 2:
        if not och:
            return True, f"👤 Eshik oldida {tanilgan}", yol
        ok, xabar = eshikni_och(f"{tanilgan} (skanerlash)", k)
        return ok, (f"✅ {tanilgan} tanildi ({int(eng_yaxshi[1] * 100)}%) — eshik ochildi" if ok
                    else f"{tanilgan} tanildi, lekin eshik ochilmadi: {xabar}"), yol
    if not yuzli_kadr:
        return False, "Eshik oldida yuz ko'rinmadi — kameraga to'g'ri qarang va qayta skanerlang", yol
    return False, "Tanish yuz topilmadi — eshik ochilmadi", yol


def eshik_skaner_buyrugi():
    gapir("Eshik oldini skanerlayapman.")
    ok, xabar, yol = eshik_skaner(och=True)
    if yol and bot and bot.egasi and (javob_telegramga or oxirgi_manba == "web"):
        fonda(bot.rasm_yubor, yol, xabar)
    gapir(xabar, rasm=yol)


def yuz_qosh(ism, manba="veb"):
    """Odamni yuzidan tanishni o'rgatadi. manba: 'veb' (kompyuter kamerasi) yoki kamera nomi."""
    try:
        t = yuz.Tanuvchi.ol()
    except Exception as xato:
        return False, f"Yuz tanish modeli yuklanmadi: {xato}"
    if manba == "veb":
        rasmlar = kamera.veb_kamera_kadrlari()
    else:
        k = next((x for x in kameralar() if x["nom"] == manba), None)
        if not k:
            return False, "Kamera topilmadi"
        rasmlar, tugash = [], time.time() + 6
        for r in kamera.kadrlar(k, fps=3, ishlasin=lambda: time.time() < tugash):
            rasmlar.append(r)
    if not rasmlar:
        return False, "Kameradan rasm olib bo'lmadi"
    soni = t.qosh(ism, rasmlar)
    if not soni:
        return False, "Rasmlarda yuz topilmadi — kameraga yaqinroq, yorug' joyda to'g'ri qarang"
    jami = t.odamlar().get(ism, soni)
    return True, f"{ism} yuzini eslab qoldim ({jami} ta namuna). Turli burchakdan yana qo'shsangiz, aniqroq taniyman."


def _yuz_tanildi(k, ism, ball, rasm, ochsin):
    import cv2
    yol = kamera._yangi_yol(k, "-yuz")
    cv2.imwrite(yol, rasm)
    if ochsin:
        ok, xabar = kamera.eshik_och(k)[:2]
        matn = (f"🚪 {ism} tanildi ({int(ball * 100)}%) — eshik ochildi" if ok
                else f"⚠️ {ism} tanildi, lekin eshik ochilmadi: {xabar}")
    else:
        matn = f"👤 Eshik oldida {ism} ({int(ball * 100)}%)"
    matn += f" · {datetime.datetime.now():%H:%M:%S}"
    print(matn)
    arxiv.yoz("jarvis", matn, "kamera", rasm=yol)
    if bot and bot.egasi:
        bot.rasm_yubor(yol, matn)


def _notanish_odam(k, rasm):
    import cv2
    yol = kamera._yangi_yol(k, "-notanish")
    cv2.imwrite(yol, rasm)
    tavsif = sun_iy.rasm_tahlil(yol, "Eshik oldida notanish odam. Uni qisqa tasvirlab ber.", til()) \
        if sun_iy.bormi() else None
    matn = f"🚨 {k['nom']}: eshik oldida notanish odam · {datetime.datetime.now():%H:%M}" + (f" — {tavsif}" if tavsif else "")
    arxiv.yoz("jarvis", matn, "kamera", rasm=yol)
    if bot and bot.egasi:
        bot.rasm_yubor(yol, matn + "\nEshikni ochish uchun: 'eshikni och' deb yozing.")


def yuz_eshikni_yoq(yoqilsin=True):
    """Tanish yuzda eshikni avtomatik ochish (yoki faqat xabar)ni yoqadi/o'chiradi."""
    for q in qorovullar.values():
        q.toxtat()
    qorovullar.clear()
    k = eshik_kamerasi()
    if yoqilsin and k:
        qorovullar[k["nom"]] = yuz.EshikQorovuli(
            k, lambda ishlasin: kamera.kadrlar(k, fps=4, ishlasin=ishlasin),
            _yuz_tanildi, _notanish_odam, ochsin=SOZ.get("yuz_eshik_och", True))
    if SOZ.get("yuz_eshik") != yoqilsin:
        sozlama_ozgartir("yuz_eshik", yoqilsin, ayt=False)
    return bool(qorovullar)


def jonli_kamera(b):
    k = kamera_tanla(b)
    if not k:
        gapir("Hali kamera qo'shilmagan.")
        return
    if javob_telegramga or oxirgi_manba == "web":           # telefonda — Telegram'da yangilanib turuvchi rasm
        if not (bot and bot.egasi):
            gapir("Jonli ko'rish uchun Telegram bot ulangan bo'lishi kerak.")
            return
        gapir(f"{k['nom']} kamerasini 2 daqiqa jonli ko'rsataman.")
        fonda(_telegramda_jonli, k, 120)
        return
    if chat_jarayon is None or chat_jarayon.poll() is not None:
        chat_och()
    arxiv.yoz("jarvis", f"📺 {k['nom']} — jonli", "kamera", jonli=k["nom"])
    gapir(f"{k['nom']} kamerasini jonli ochdim.", tarjima_qil=False)


def _telegramda_jonli(k, soniya):
    yol, xato = kamera.rasm_ol(k)
    if not yol:
        bot.yoz(f"Kameraga ulanib bo'lmadi: {xato}")
        return
    xabar_id = bot.rasm_yubor(yol, f"🔴 {k['nom']} — jonli")
    tugash = time.time() + soniya
    while xabar_id and time.time() < tugash and not uzildi.is_set():
        time.sleep(2.5)
        yol, _ = kamera.rasm_ol(k)
        if yol:
            bot.rasm_yangila(xabar_id, yol)
    bot.yoz(f"⏹ {k['nom']} jonli ko'rsatish tugadi.")


chat_jarayon = None               # chat oynasi (alohida jarayon)


def _chat_ilova_buyrugi(url):
    """Chat oynasini haqiqiy dastur sifatida ochish buyrug'i (pywebview). Bo'lmasa — None."""
    if getattr(sys, "frozen", False):                   # Jarvis.exe ichida hammasi bor
        return [sys.executable, "--chat", url]
    import importlib.util
    if importlib.util.find_spec("webview") is None:     # pip install pywebview qilinmagan
        return None
    return [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_oyna.py"), url]


def _brauzerda_och(url):
    """Zaxira: pywebview ishlamasa — Edge/Chrome "ilova" rejimida, u ham bo'lmasa oddiy brauzerda."""
    if os.name == "nt":
        yollar = [os.path.expandvars(p) for p in (
            r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
            r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
            r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
            r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
            r"%LocalAppData%\Google\Chrome\Application\chrome.exe")]
        for yol in yollar:
            if os.path.exists(yol):
                try:
                    subprocess.Popen([yol, f"--app={url}", "--window-size=1150,780"])
                    return
                except OSError:
                    pass
    webbrowser.open(url)


def chat_och(sozlama=False, jonli=None):
    """Chat oynasini alohida dastur oynasi qilib ochadi (brauzer emas, internet shart emas).
    sozlama=True — darhol sozlamalar bo'limida. Oyna ochiq bo'lsa — qayta ochiladi (oldinga chiqadi)."""
    global chat_jarayon
    url = f"http://127.0.0.1:{server.PORT}/chat" + ("?soz=1" if sozlama else "") + \
        (("&" if sozlama else "?") + "jonli=" + urllib.parse.quote(jonli) if jonli else "")
    if chat_jarayon is not None and chat_jarayon.poll() is None:
        try:
            chat_jarayon.terminate()                    # eski oynani yopib, yangisini ochamiz
        except OSError:
            pass
    buyruq = _chat_ilova_buyrugi(url)
    if not buyruq:
        print("(Chat oynasini dastur qilib ochish uchun: pip install pywebview)")
        _brauzerda_och(url)
        return
    try:
        chat_jarayon = subprocess.Popen(buyruq)
    except OSError as xato:
        print(f"(Chat oynasi ochilmadi: {xato})")
        _brauzerda_och(url)
        return

    def tekshir(jarayon):                               # darhol yiqilsa (WebView2 yo'q) — zaxira
        time.sleep(4)
        if jarayon.poll() not in (None, 0):
            print("(Chat oynasi ishlamadi — Microsoft Edge WebView2 kerak. Brauzerda ochyapman.)")
            _brauzerda_och(url)
    threading.Thread(target=tekshir, args=(chat_jarayon,), daemon=True).start()


def chat_yop():
    """Jarvis yopilganda chat oynasi ham yopiladi."""
    if chat_jarayon is not None and chat_jarayon.poll() is None:
        try:
            chat_jarayon.terminate()
        except OSError:
            pass


atexit.register(chat_yop)


def internetni_kuzat():
    """Internet bor-yo'qligini kuzatadi — chat oynasida ko'rinadi.
    Internetsiz ham chat, dasturlar, fayllar ishlaydi; faqat ovoz tanish/gapirish va AI ishlamaydi."""
    import socket
    oldingi = None
    while True:
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=3).close()
            bor_ = True
        except OSError:
            bor_ = False
        server.internet_bor = bor_
        if bor_ != oldingi and oldingi is not None:
            print("🌐 Internet qaytdi." if bor_ else "⚠️ Internet yo'q — ovozli buyruqlar ishlamaydi, chatga yozing.")
        oldingi = bor_
        time.sleep(15)


def chat_sozlamalari():
    """Chatdagi sozlamalar bo'limi uchun joriy holat (maxfiy kalitlar ko'rsatilmaydi)."""
    token = SOZ.get("telegram_token", "")
    return {
        "qiymatlar": {"ism": SOZ["ism"], "ovoz": SOZ["ovoz"], "til": SOZ["til"], "rang": SOZ["rang"],
                      "shahar": SOZ.get("shahar", "toshkent"), "chat_avto": SOZ.get("chat_avto", True),
                      "telefon_pin": str(SOZ.get("telefon_pin") or "0000")},
        "tillar": {k: v["nomi"] for k, v in sozlamalar.TILLAR.items()},
        "ranglar": {k: {"nomi": v["nomi"], "rang": "#%02x%02x%02x" % v["yorqin"]}
                    for k, v in sozlamalar.RANGLAR.items()},
        "shaharlar": {k: v[1] for k, v in qulayliklar.SHAHARLAR.items() if k != "fargona"},
        "ai": {"bor": sun_iy.bormi(), "ozimizniki": bool(SOZ.get("groq_kalit")),
               "claude": bool(SOZ.get("claude_kalit")), "claude_model": SOZ.get("claude_model") or "claude-sonnet-5",
               "claude_modellar": sun_iy.CLAUDE_MODELLAR, "claude_xato": sun_iy.claude_xato},
        "ig": {"bor": bool(SOZ.get("ig_token")), "username": SOZ.get("ig_username") or "",
               "avto": bool(SOZ.get("ig_avto_ulash")), "fon": ig_fon_bormi(),
               "fon_kirgan": bool(SOZ.get("ig_brauzer_kirgan")),
               "rejalar": len(SOZ.get("ig_rejalar", []))},
        "tga": {"holat": tga.holat if tga else "ulanmagan", "men": tga.men if tga else None,
                "api_bor": bool(SOZ.get("tga_api_id") and SOZ.get("tga_api_hash")),
                "dostlar": SOZ.get("tga_dostlar") or [], "hammasi": bool(SOZ.get("tga_hammasi"))},
        "telegram": {"token": ("•••• " + token[-4:]) if token else "", "egasi": bool(SOZ.get("telegram_egasi")),
                     "ishlayapti": bool(bot)},
        "telefon": {"ip": server.ip_manzil(), "port": server.PORT, "kanal": SOZ.get("telefon_kanal", "")},
        "avtostart": kompyuter.avtostart_bormi(),
        "papka": sozlamalar.PAPKA,
        "kamera": {"royxat": [{"nom": k.get("nom", ""), "ip": k.get("ip", ""), "kanal": k.get("kanal", "101"),
                               "login": k.get("login", "admin"), "http_port": k.get("http_port", 80), "kuzatilyapti": k.get("nom") in kuzatuvchilar,
                               "eshik": k is eshik_kamerasi()}
                              for k in SOZ.get("kameralar", []) if k.get("ip")],
                   "kuzatuv": bool(SOZ.get("kamera_kuzatuv")), "ovoz": bool(SOZ.get("kamera_ovoz")),
                   "yuz_eshik": bool(SOZ.get("yuz_eshik")), "yuz_eshik_och": bool(SOZ.get("yuz_eshik_och", True)),
                   "yuz_ishlayapti": bool(qorovullar), "odamlar": _odamlar(),
                   "eshik": ({"nom": eshik_qurilmasi()["nom"], "ip": eshik_qurilmasi()["ip"],
                              "kanal": eshik_qurilmasi().get("kanal", "1"),
                              "login": eshik_qurilmasi().get("login", "admin"),
                              "raqam": eshik_qurilmasi().get("eshik_raqami", 1),
                              "usul": eshik_qurilmasi().get("eshik_usul", "")} if eshik_qurilmasi() else None),
                   "pin_qisqa": len(str(SOZ.get("telefon_pin") or "")) < 6},
        "mikrofon": {"holat": dict(MIK_HOLAT, oldin=int(time.time() - MIK_HOLAT["vaqt"])
                                   if MIK_HOLAT["vaqt"] else None),
                     "qurilmalar": [n for _, n in mikrofonlar()],
                     "tanlangan": SOZ.get("mikrofon", ""), "sezgirlik": int(SOZ.get("sezgirlik", 3) or 3)},
    }


def _odamlar():
    """Yuzi o'rgatilgan odamlar: {ism: namunalar soni} (og'ir modelni yuklamasdan, fayldan)."""
    if yuz.Tanuvchi._nusxa is not None:
        return yuz.Tanuvchi._nusxa.odamlar()
    try:
        with open(yuz.BAZA_FAYL, encoding="utf-8") as f:
            return {ism: len(n) for ism, n in json.load(f).items()}
    except (OSError, ValueError):
        return {}


def _eshik_kuzatuvini_avto_yoq():
    """Eshik ulangan va kamida bitta yuz o'rgatilgan bo'lsa — eshik doim kuzatilsin
    (foydalanuvchi o'zi o'chirmagan bo'lsa: yuz_eshik None — hali tanlanmagan)."""
    if SOZ.get("yuz_eshik") is None and eshik_kamerasi() and _odamlar() and not qorovullar:
        yuz_eshikni_yoq(True)


def chat_sozlama_yoz(kalit, qiymat):
    """Chatdagi sozlamalar bo'limidan kelgan o'zgarish. (ok, xabar) qaytaradi."""
    if kalit == "ism":
        qiymat = str(qiymat or "").strip()[:40]
        if not qiymat:
            return False, "Ism bo'sh bo'lmasin."
        sozlama_ozgartir("ism", qiymat, ayt=False)
        return True, f"Endi sizni {qiymat} deb chaqiraman."
    if kalit == "ovoz" and qiymat in ("ayol", "erkak"):
        sozlama_ozgartir("ovoz", qiymat, ayt=False)
        return True, "Ovoz o'zgardi."
    if kalit == "ovoz_sinov" and qiymat in ("ayol", "erkak"):
        kirish_navbat.put(("ovoz_sinov", qiymat, time.time()))
        return True, "Eshiting..."
    if kalit == "til" and qiymat in sozlamalar.TILLAR:
        sozlama_ozgartir("til", qiymat, ayt=False)
        return True, "Til o'zgardi."
    if kalit == "rang" and qiymat in sozlamalar.RANGLAR:
        sozlama_ozgartir("rang", qiymat, ayt=False)
        return True, "Rang o'zgardi."
    if kalit == "shahar" and qiymat in qulayliklar.SHAHARLAR:
        sozlama_ozgartir("shahar", qiymat, ayt=False)
        return True, f"Shahar: {qulayliklar.SHAHARLAR[qiymat][1]}."
    if kalit == "kamera_qosh" and isinstance(qiymat, dict):
        ip = str(qiymat.get("ip", "")).strip().replace("http://", "").replace("https://", "").strip("/")
        if not re.fullmatch(r"[\w.-]+", ip):
            return False, "IP manzilni to'g'ri kiriting, masalan: 192.168.1.64"
        royxat = [k for k in SOZ.get("kameralar", []) if k.get("ip")]
        nom = str(qiymat.get("nom") or "").strip()[:30] or f"Kamera {len(royxat) + 1}"
        yangi = {"nom": nom, "ip": ip, "login": str(qiymat.get("login") or "admin").strip(),
                 "parol": str(qiymat.get("parol") or "").strip(), "kanal": str(qiymat.get("kanal") or "101").strip(),
                 "http_port": int(qiymat.get("http_port") or 80), "rtsp_port": int(qiymat.get("rtsp_port") or 554)}
        eski = next((k for k in royxat if k["nom"] == nom), None)
        if eski and not yangi["parol"]:
            yangi["parol"] = eski.get("parol", "")            # parol qayta yozilmasa — eskisi qoladi
        if eski:                                              # tahrirlash — o'rni o'zgarmaydi
            for kalit_ in ("eshik",):
                if kalit_ in eski:
                    yangi[kalit_] = eski[kalit_]
            royxat = [yangi if k is eski else k for k in royxat]
        else:
            royxat = royxat + [yangi]
        sozlama_ozgartir("kameralar", royxat, ayt=False)
        if kuzatuvchilar:
            kuzatuvni_yoq(True)                               # yangi kamera ham kuzatilsin
        return True, f"'{nom}' kamerasi saqlandi. Endi 'Sinash' tugmasini bosing."
    if kalit == "kamera_ochir":
        royxat = [k for k in SOZ.get("kameralar", []) if k.get("nom") != qiymat]
        sozlama_ozgartir("kameralar", royxat, ayt=False)
        if qiymat in kuzatuvchilar:
            kuzatuvchilar.pop(qiymat).toxtat()
        return True, "Kamera o'chirildi."
    if kalit == "kamera_sina":
        k = next((k for k in kameralar() if k["nom"] == qiymat), None)
        if not k:
            return False, "Kamera topilmadi."
        yol, xato = kamera.rasm_ol(k)
        if not yol and "noto'g'ri" in (xato or ""):
            topildi = _parolni_izla(k)                        # boshqa kameralarning paroli mos kelmasmikan
            if topildi:
                k = topildi
                yol, xato = kamera.rasm_ol(k)
                if yol:
                    return True, (f"✅ '{k['nom']}' ishlayapti! Paroli boshqa kameranikiga mos keldi — "
                                  "o'zim saqlab qo'ydim."), {"rasm": kamera.nisbiy(yol)}
        if not yol:
            try:
                tafsilot = kamera.tashxis(k, parol_sinalsin="noto'g'ri" not in (xato or ""))
            except Exception as xato_:
                tafsilot = [f"(tekshiruv xatosi: {xato_})"]
            print(f"Kamera tekshiruvi ({k['nom']}, {k.get('ip')}):\n  " + "\n  ".join(tafsilot))
            return False, f"Ulanib bo'lmadi: {xato}.", {"tafsilot": tafsilot}
        return True, f"✅ '{k['nom']}' ishlayapti!", {"rasm": kamera.nisbiy(yol)}
    if kalit == "eshik_saqla" and isinstance(qiymat, dict):
        ip = str(qiymat.get("ip", "")).strip().replace("http://", "").replace("https://", "").strip("/")
        if not re.fullmatch(r"[\w.-]+", ip):
            return False, "IP manzilni to'g'ri kiriting, masalan: 192.168.100.201"
        eski = SOZ.get("eshik") or {}
        eshik = {"nom": str(qiymat.get("nom") or "Eshik").strip()[:30], "ip": ip,
                 "login": str(qiymat.get("login") or "admin").strip(),
                 "parol": str(qiymat.get("parol") or "").strip() or (eski.get("parol", "") if eski.get("ip") == ip else ""),
                 "kanal": str(qiymat.get("kanal") or "1").strip(),
                 "http_port": int(qiymat.get("http_port") or 80),
                 "eshik_raqami": int(qiymat.get("eshik_raqami") or 1)}
        sozlama_ozgartir("eshik", eshik, ayt=False)
        ok, xato = kamera.rasm_ol(eshik)                  # darhol ulanishni tekshiramiz
        if qorovullar or SOZ.get("yuz_eshik"):
            yuz_eshikni_yoq(True)
        if not ok:
            return False, f"Eshik saqlandi, lekin ulanib bo'lmadi: {xato}."
        _eshik_kuzatuvini_avto_yoq()
        return True, "✅ Eshik ulandi va ishlayapti!", {"rasm": kamera.nisbiy(ok)}
    if kalit == "eshik_ochir":
        yuz_eshikni_yoq(False)
        sozlama_ozgartir("eshik", {}, ayt=False)
        return True, "Eshik qurilmasi o'chirildi."
    if kalit == "eshik_skaner":
        ok, xabar, yol = eshik_skaner(och=True)
        return ok, xabar, ({"rasm": kamera.nisbiy(yol)} if yol else {})
    if kalit == "kamera_qidir":
        topilgan = kamera.sadp_qidir()
        if not topilgan:
            return False, ("Tarmoqda Hikvision qurilma topilmadi. Kamera yoqilganmi va kompyuter bilan "
                           "bitta routerdami, tekshiring"), {"topilgan": []}
        toqnash = sorted({q["ip"] for q in topilgan if q.get("toqnashuv")})
        if toqnash:
            return True, (f"{len(topilgan)} ta qurilma topildi. ⚠️ {', '.join(toqnash)} manzilida BIR NECHTA qurilma "
                          "bor — ular bir-biriga xalaqit beradi (parol 'noto'g'ri' ko'rinishi mumkin). "
                          "SADP dasturida ulardan biriga boshqa IP bering"), {"topilgan": topilgan}
        return True, f"{len(topilgan)} ta qurilma topildi", {"topilgan": topilgan}
    if kalit == "kamera_eshik":                              # shu kamera eshikka ulangan
        royxat = [dict(k, eshik=(k.get("nom") == qiymat)) for k in SOZ.get("kameralar", [])]
        sozlama_ozgartir("kameralar", royxat, ayt=False)
        if qorovullar:
            yuz_eshikni_yoq(True)
        return True, f"'{qiymat}' — eshik kamerasi."
    if kalit == "eshik_och":
        k = next((x for x in kameralar() if x["nom"] == qiymat), None) or eshik_kamerasi()
        ok, xabar = eshikni_och("chatdan", k)
        return ok, ("🚪 Eshik ochildi" if ok else f"Ochilmadi: {xabar}")
    if kalit == "yuz_qosh" and isinstance(qiymat, dict):
        ism = str(qiymat.get("ism") or "").strip()[:30]
        if not ism:
            return False, "Ismni kiriting."
        natija = yuz_qosh(ism, str(qiymat.get("manba") or "veb"))
        _eshik_kuzatuvini_avto_yoq()
        return natija
    if kalit == "yuz_ochir":
        ok = yuz.Tanuvchi.ol().ochir(str(qiymat))
        return ok, (f"{qiymat} o'chirildi." if ok else "Topilmadi.")
    if kalit == "yuz_eshik":
        if qiymat and not _odamlar():
            return False, "Avval kamida bitta odamning yuzini qo'shing."
        ok = yuz_eshikni_yoq(bool(qiymat))
        if qiymat and not ok:
            return False, "Eshik kamerasi topilmadi."
        return True, ("Eshik kamerasini kuzatyapman." if qiymat else "O'chirildi.")
    if kalit == "yuz_eshik_och":
        sozlama_ozgartir("yuz_eshik_och", bool(qiymat), ayt=False)
        if qorovullar:
            yuz_eshikni_yoq(True)
        return True, ("Tanish yuzda eshik ochiladi." if qiymat else "Faqat xabar beraman, eshikni ochmayman.")
    if kalit == "kamera_kuzatuv":
        soni = kuzatuvni_yoq(bool(qiymat))
        return True, (f"{soni} ta kamerada harakat kuzatilyapti." if qiymat else "Kuzatuv to'xtatildi.")
    if kalit == "kamera_ovoz":
        sozlama_ozgartir("kamera_ovoz", bool(qiymat), ayt=False)
        return True, "Saqlandi."
    if kalit == "mikrofon":
        sozlama_ozgartir("mikrofon", str(qiymat or ""), ayt=False)
        mik_qayta.set()                                   # mikrofon qayta ochiladi
        return True, "Mikrofon almashtirilmoqda..."
    if kalit == "sezgirlik" and str(qiymat) in ("1", "2", "3", "4", "5"):
        sozlama_ozgartir("sezgirlik", int(qiymat), ayt=False)
        _chegarani_sozla()
        return True, "Sezgirlik o'zgardi."
    if kalit == "mik_qayta":
        mik_qayta.set()
        return True, "Mikrofon qayta sozlanmoqda — 2 soniya jim turing."
    if kalit == "chat_avto":
        sozlama_ozgartir("chat_avto", bool(qiymat), ayt=False)
        return True, "Saqlandi."
    if kalit == "avtostart":
        ok = kompyuter.avtostart(bool(qiymat))
        return ok, ("Windows bilan birga ishga tushaman." if qiymat else "Avtomatik ishga tushish o'chirildi.") \
            if ok else "Sozlab bo'lmadi."
    if kalit == "telefon_pin":
        qiymat = str(qiymat or "").strip()
        if not re.fullmatch(r"\d{4,8}", qiymat):
            return False, "PIN 4-8 ta raqamdan iborat bo'lsin."
        sozlama_ozgartir("telefon_pin", qiymat, ayt=False)
        server._pin = qiymat                            # telefon ilovasi (Wi-Fi) darhol yangi PIN bilan
        if SOZ.get("telefon_kanal"):
            fonda(bulut.ishga_tushir, SOZ["telefon_kanal"], qiymat, web_bajar)
        return True, "PIN o'zgardi. Telefon ilovasida ham yangi PIN'ni kiriting."
    if kalit == "telegram_token":
        qiymat = str(qiymat or "").strip()
        if qiymat and not re.fullmatch(r"\d{5,}:[\w-]{20,}", qiymat):
            return False, "Token noto'g'ri ko'rinishda. BotFather bergan tokenni to'liq qo'ying."
        sozlama_ozgartir("telegram_token", qiymat, ayt=False)
        telegram_ishga_tushir()
        return True, "Telegram bot ulanmoqda — Jarvis oynasida juftlash kodi chiqadi." if qiymat \
            else "Telegram bot o'chirildi."
    if kalit == "telegram_uz":
        sozlama_ozgartir("telegram_egasi", 0, ayt=False)
        telegram_ishga_tushir()
        return True, "Telegram uzildi. Qayta ulash uchun yangi kod chiqadi."
    if kalit == "groq_kalit":
        qiymat = str(qiymat or "").strip()
        if not qiymat:
            return False, "Avval kalitni maydonga qo'ying (Ctrl+V), keyin Ulash'ni bosing."
        if not qiymat.startswith("gsk_"):
            return False, "Groq kaliti 'gsk_' bilan boshlanadi. console.groq.com dan oling."
        sozlama_ozgartir("groq_kalit", qiymat, ayt=False)
        if qiymat:
            os.environ["GROQ_API_KEY"] = qiymat
            return True, "Sun'iy intellekt ulandi. Endi har qanday savolga javob beraman."
        os.environ.pop("GROQ_API_KEY", None)
        return True, "AI kaliti o'chirildi."
    if kalit == "claude_kalit":
        qiymat = str(qiymat or "").strip()
        if not qiymat:                                    # bo'sh maydon bilan "Ulash" — o'chirmaymiz
            return False, "Avval kalitni maydonga qo'ying (Ctrl+V), keyin Ulash'ni bosing."
        if qiymat == "__ochir__":
            qiymat = ""
        elif not qiymat.startswith("sk-ant-"):
            return False, "Claude kaliti 'sk-ant-' bilan boshlanadi. console.anthropic.com dan oling."
        tekshiruv = ""
        if qiymat:                                        # kalitni darhol tekshiramiz (bepul, token sarflanmaydi)
            try:
                import anthropic
                anthropic.Anthropic(api_key=qiymat, max_retries=0, timeout=15.0).models.list(limit=1)
                tekshiruv = " ✅ Kalit tekshirildi — ishlayapti."
            except Exception as xato:
                if type(xato).__name__ in ("AuthenticationError", "PermissionDeniedError"):
                    return False, "Kalit noto'g'ri yoki o'chirilgan — Console'dan qayta nusxalang yoki yangisini yarating."
                tekshiruv = " (Kalitni hozir tekshirib bo'lmadi — internetni tekshiring.)"
        sozlama_ozgartir("claude_kalit", qiymat, ayt=False)
        if qiymat:
            os.environ["ANTHROPIC_API_KEY"] = qiymat
            sun_iy.claude_xato = ""
            return True, "Claude ulandi. Savol va buyruqlar endi Claude'ga boradi, rasmlar — bepul AI'ga." + tekshiruv
        os.environ.pop("ANTHROPIC_API_KEY", None)
        return True, "Claude o'chirildi — endi faqat bepul AI ishlaydi."
    if kalit == "ig_kirish":                                     # Instagram'ning o'z sahifasida o'zi kiradi
        try:
            import instagram_brauzer
        except Exception:
            return False, "Orqa fon rejimi uchun kutubxona yo'q (playwright)."
        if not instagram_brauzer.bormi():
            return False, "Orqa fon rejimi uchun kutubxona yo'q (playwright)."

        def kir():
            try:
                ok = instagram_brauzer.kirish_oynasi()
            except Exception as xato:
                print(f"(Instagram kirish oynasi xatosi: {xato})")
                ok = False
            sozlama_ozgartir("ig_brauzer_kirgan", bool(ok), ayt=False)
            gapir("✅ Instagram'ga kirildi. Endi orqa fonda joylay olaman." if ok
                  else "Instagram'ga kirilmadi. Qaytadan urinib ko'ring.")
        fonda(kir)
        return True, ("Instagram'ning kirish oynasi ochildi — u yerga o'zingiz kiring (parol Jarvis'da saqlanmaydi). "
                      "Kirgach, oyna o'zi yopiladi.")
    if kalit == "ig_brauzer_chiqish":
        try:
            import instagram_brauzer
            instagram_brauzer.chiqish()
        except Exception:
            pass
        sozlama_ozgartir("ig_brauzer_kirgan", False, ayt=False)
        return True, "Orqa fon rejimidan chiqildi (kirish ma'lumotlari o'chirildi)."
    if kalit == "ig_avto_ulash":
        sozlama_ozgartir("ig_avto_ulash", bool(qiymat), ayt=False)
        return True, ("To'liq avtomatik: Jarvis 'Ulashish'ni ham o'zi bosadi va vaqtga qo'ya oladi." if qiymat
                      else "'Ulashish'ni endi siz bosasiz.")
    if kalit == "ig_token":
        global _ig
        token = str(qiymat or "").strip()
        if not token:
            return False, "Avval kalitni (token) maydonga qo'ying, keyin Ulash'ni bosing."
        if token == "__ochir__":
            for k in ("ig_token", "ig_id", "ig_username"):
                sozlama_ozgartir(k, "", ayt=False)
            _ig = None
            return True, "Instagram uzildi."
        import instagram
        try:
            ig = instagram.Instagram(token)
            ig.ulan()
            a = ig.akkaunt()
        except Exception as xato:
            return False, f"Ulanmadi: {xato}"
        sozlama_ozgartir("ig_token", token, ayt=False)
        sozlama_ozgartir("ig_id", ig.id, ayt=False)
        sozlama_ozgartir("ig_username", ig.username, ayt=False)
        _ig = None
        return True, (f"✅ Instagram ulandi: @{ig.username} ({a.get('followers_count', 0)} obunachi). "
                      "Endi: 'Jarvis, instagramga videoni joyla' deng.")
    if kalit == "claude_model" and qiymat in sun_iy.CLAUDE_MODELLAR:
        sozlama_ozgartir("claude_model", qiymat, ayt=False)
        os.environ["JARVIS_CLAUDE_MODEL"] = qiymat
        return True, f"Model: {sun_iy.CLAUDE_MODELLAR[qiymat]}."
    if kalit == "tga_kod" and isinstance(qiymat, dict):          # 1-qadam: api_id, api_hash, telefon
        api_id = str(qiymat.get("api_id") or "").strip()
        api_hash = str(qiymat.get("api_hash") or "").strip()
        telefon = str(qiymat.get("telefon") or "").strip()
        if not api_id.isdigit() or len(api_hash) < 20:
            return False, "api_id (raqam) va api_hash ni my.telegram.org dan to'g'ri ko'chiring."
        if not re.fullmatch(r"\+?\d{9,15}", telefon.replace(" ", "")):
            return False, "Telefon raqamini to'liq yozing, masalan: +998901234567"
        sozlama_ozgartir("tga_api_id", api_id, ayt=False)
        sozlama_ozgartir("tga_api_hash", api_hash, ayt=False)
        import telegram_akkaunt
        try:
            if tga_ishga_tushir() == "ulangan":
                return True, f"Akkaunt allaqachon ulangan: {tga.men}"
            if not tga or not tga.mijoz:
                return False, "Telegram'ga ulanib bo'lmadi: " + (getattr(tga, "oxirgi_xato", "") or
                                                                 "internetni tekshiring (jarvis.log da batafsil)")
            qayerga = tga.kod_yubor(telefon)
        except Exception as xato:
            print(f"(Telegram kod xatosi: {type(xato).__name__}: {xato})")
            return False, "Kod yuborilmadi: " + telegram_akkaunt.xato_matni(xato)
        print(f"(Telegram kodi yuborildi: {qayerga})")
        return True, f"Kod yuborildi — {qayerga}. Kodni pastga yozing."
    if kalit == "tga_qr" and isinstance(qiymat, dict):          # QR bilan kirish — kod kerak emas
        api_id = str(qiymat.get("api_id") or SOZ.get("tga_api_id") or "").strip()
        api_hash = str(qiymat.get("api_hash") or SOZ.get("tga_api_hash") or "").strip()
        if not api_id.isdigit() or len(api_hash) < 20:
            return False, "Avval api_id va api_hash ni yozing (my.telegram.org dan)."
        sozlama_ozgartir("tga_api_id", api_id, ayt=False)
        sozlama_ozgartir("tga_api_hash", api_hash, ayt=False)
        holat_ = tga_ishga_tushir()
        if holat_ == "ulangan":
            return True, f"Akkaunt allaqachon ulangan: {tga.men}"
        if not tga or not tga.mijoz:
            return False, "Telegram'ga ulanib bo'lmadi: " + (getattr(tga, "oxirgi_xato", "") or "internetni tekshiring")
        tga.qr_boshla()
        return True, "QR kod tayyorlanyapti..."
    if kalit == "tga_qr_holat":                                  # chat oynasi har 2 soniyada so'raydi
        if not tga:
            return False, "Boshlanmagan."
        qosh = {"holat": tga.holat, "men": tga.men}
        if tga.qr_url:
            try:
                import base64
                import io
                import qrcode
                rasm = qrcode.make(tga.qr_url, box_size=8, border=2)
                bufer = io.BytesIO()
                rasm.save(bufer, format="PNG")
                qosh["qr"] = "data:image/png;base64," + base64.b64encode(bufer.getvalue()).decode()
            except Exception as xato:
                qosh["url"] = tga.qr_url                          # qrcode yo'q — chat o'zi chizadi
                print(f"(QR rasm xatosi: {xato})")
        xabar = {"ulangan": f"✅ Ulandi: {tga.men}", "parol_kerak": "Ikki bosqichli parolingizni kiriting va 'Kirish'ni bosing",
                 "qr_kutilmoqda": "Telefonda skanerlang"}.get(tga.holat, tga.qr_xato or "Kutilmoqda...")
        return tga.holat != "ulanmagan" or not tga.qr_xato, xabar, qosh
    if kalit == "tga_qayta":                                     # kod kelmadi — SMS orqali
        import telegram_akkaunt
        if not tga or not tga.kod_hash:
            return False, "Avval 'Kod yuborish'ni bosing."
        try:
            qayerga = tga.qayta_yubor()
        except Exception as xato:
            print(f"(Telegram qayta kod xatosi: {type(xato).__name__}: {xato})")
            return False, "Qayta yuborilmadi: " + telegram_akkaunt.xato_matni(xato)
        return True, f"Kod qayta yuborildi — {qayerga}."
    if kalit == "tga_kirish" and isinstance(qiymat, dict):       # 2-qadam: kod (va 2 bosqichli parol)
        if not tga:
            return False, "Avval kod so'rang."
        try:
            natija = tga.kirish(str(qiymat.get("kod") or ""), str(qiymat.get("parol") or ""))
        except Exception as xato:
            import telegram_akkaunt
            print(f"(Telegram kirish xatosi: {type(xato).__name__}: {xato})")
            return False, "Kirib bo'lmadi: " + telegram_akkaunt.xato_matni(xato)
        if natija == "parol_kerak":
            return False, "Akkauntingizda ikki bosqichli parol bor — uni ham kiriting."
        return True, f"✅ Ulandi: {tga.men}. Endi kuzatiladigan do'stlarni yozing."
    if kalit == "tga_dostlar":
        dostlar = [d.strip() for d in re.split(r"[,\n;]", str(qiymat or "")) if d.strip()][:30]
        sozlama_ozgartir("tga_dostlar", dostlar, ayt=False)
        if tga:
            tga.dostlar = dostlar
        return True, (f"Kuzatiladi: {', '.join(dostlar)}. Ulardan xabar kelsa, o'qib beraymi deb so'rayman."
                      if dostlar else "Do'stlar ro'yxati tozalandi.")
    if kalit == "tga_hammasi":
        sozlama_ozgartir("tga_hammasi", bool(qiymat), ayt=False)
        if tga:
            tga.hammasi = bool(qiymat)
        return True, "Barcha shaxsiy xabarlar haqida aytaman." if qiymat else "Faqat tanlangan do'stlar."
    if kalit == "tga_chiqish":
        if tga:
            try:
                tga.chiqish()
            except Exception:
                pass
        return True, "Telegram akkaunt uzildi, kirish kaliti o'chirildi."
    return False, "Noma'lum sozlama."


def uy_tarmogidami():
    """Kompyuter kameralar bilan bitta tarmoqdami (noutbuk uydan olib ketilgan bo'lsa — yo'q)."""
    ip = server.ip_manzil()
    tarmoqlar = {".".join(str(k.get("ip", "")).split(".")[:3]) for k in kameralar() if k.get("ip")}
    return not tarmoqlar or ".".join(ip.split(".")[:3]) in tarmoqlar


UYDA_EMAS = ("Kompyuter hozir uy tarmog'ida emas — kameralarga faqat uy Wi-Fi'dagi qurilma ulana oladi. "
             "Uydan tashqarida ko'rish uchun Hik-Connect ilovasidan foydalaning (pastdagi tugma).")


def telefon_kamera_amali(amal, m):
    """Telefon ilovasining Kamera bo'limi (faqat uy Wi-Fi'da, PIN tekshirilgan)."""
    import base64
    eshik = eshik_kamerasi()
    if amal in ("rasm", "eshik", "skaner") and not uy_tarmogidami():
        return {"ok": False, "xato": UYDA_EMAS, "uyda_emas": True}
    if amal == "kameralar":
        return {"ok": True, "versiya": VERSIYA, "uyda": uy_tarmogidami(), "eshik": eshik["nom"] if eshik else None,
                "kameralar": [{"nom": k["nom"], "eshik": bool(eshik and k.get("ip") == eshik.get("ip")),
                               "ip": k.get("ip", ""), "login": k.get("login", "admin"),
                               "kanal": k.get("kanal", "1"), "http_port": k.get("http_port", 80),
                               "ozgartirsa": not k.get("eshik")}   # parol bu yerda yuborilmaydi
                              for k in kameralar()]}
    if amal == "rasm":
        k = next((x for x in kameralar() if x["nom"] == m.get("nom")), None)
        if not k:
            return {"ok": False, "xato": "Kamera topilmadi"}
        jpg, xato = kamera.rasm_baytlari(k, eni=int(m.get("eni") or 960))
        return {"ok": True, "rasm": base64.b64encode(jpg).decode()} if jpg else {"ok": False, "xato": xato}
    if amal == "eshik":
        if len(str(SOZ.get("telefon_pin") or "")) < 6:
            return {"ok": False, "xato": "Xavfsizlik uchun PIN kamida 6 raqam bo'lsin. Kompyuterdagi chat "
                                         "sozlamalarida PIN'ni almashtiring, keyin ilovada ham kiriting."}
        ok, xabar = eshikni_och("telefon ilovasidan")
        return {"ok": ok, "xabar": "🚪 Eshik ochildi" if ok else f"Ochilmadi: {xabar}"}
    if amal == "skaner":
        if len(str(SOZ.get("telefon_pin") or "")) < 6:
            return {"ok": False, "xato": "Xavfsizlik uchun PIN kamida 6 raqam bo'lsin (skanerlash eshikni ochadi)."}
        ok, xabar, yol = eshik_skaner(och=True)
        natija = {"ok": ok, "xabar": xabar}
        if yol:
            jpg = open(yol, "rb").read()
            natija["rasm"] = base64.b64encode(jpg).decode()
        return natija
    if amal in ("qosh", "ochir", "sina", "qidir", "sinxron"):   # kamera qo'shish/o'zgartirish telefondan
        if len(str(SOZ.get("telefon_pin") or "")) < 6:
            return {"ok": False, "xato": "Xavfsizlik uchun PIN kamida 6 raqam bo'lsin. Kompyuterdagi chat "
                                         "sozlamalarida PIN'ni almashtiring, keyin ilovada ham kiriting."}
        if amal == "sinxron":       # kompyuter o'chiq bo'lsa ham telefon kameralarni ko'rsin (faqat uy Wi-Fi, PIN>=6)
            return {"ok": True, "bulut_kalit": SOZ.get("bulut_kalit", ""),   # uydan tashqarida — shifrli kanal
                    "kameralar": [
                {"nom": k["nom"], "ip": k.get("ip", ""), "login": k.get("login", "admin"), "parol": k.get("parol", ""),
                 "kanal": k.get("kanal", "1"), "http_port": k.get("http_port", 80)} for k in kameralar()]}
        if amal == "qidir":
            ok, xabar, qosh = chat_sozlama_yoz("kamera_qidir", 1)
            return {"ok": ok, "xabar": xabar, "topilgan": qosh.get("topilgan", [])}
        if amal == "ochir":
            ok, xabar = chat_sozlama_yoz("kamera_ochir", str(m.get("nom") or ""))[:2]
            return {"ok": ok, "xabar": xabar}
        nom = str(m.get("nom") or "").strip()
        if amal == "qosh":
            q = {x: m.get(x) for x in ("nom", "ip", "login", "parol", "kanal", "http_port")}
            ok, xabar = chat_sozlama_yoz("kamera_qosh", q)[:2]
            if not ok:
                return {"ok": False, "xato": xabar}
            nom = (SOZ.get("kameralar") or [{}])[-1].get("nom", nom) if not nom else nom[:30]
        natija = chat_sozlama_yoz("kamera_sina", nom)
        javob = {"ok": natija[0], "xabar": natija[1], "nom": nom}
        qosh = natija[2] if len(natija) > 2 else {}
        if qosh.get("rasm"):
            fayl = os.path.join(kamera.PAPKA, qosh["rasm"].replace("/", os.sep))
            jpg = None
            try:
                import cv2
                rasm = cv2.imread(fayl)
                if rasm is not None and rasm.shape[1] > 720:
                    rasm = cv2.resize(rasm, (720, int(rasm.shape[0] * 720 / rasm.shape[1])))
                jpg = cv2.imencode(".jpg", rasm, [cv2.IMWRITE_JPEG_QUALITY, 72])[1].tobytes() if rasm is not None else None
            except Exception:
                jpg = open(fayl, "rb").read()
            if jpg:
                javob["rasm"] = base64.b64encode(jpg).decode()
        if qosh.get("tafsilot"):
            javob["tafsilot"] = qosh["tafsilot"]
        if amal == "qosh":
            javob["xabar"] = ("✅ Kamera qo'shildi va ishlayapti! Kompyuterda ham ko'rinadi." if javob["ok"] else
                              "Kamera saqlandi, lekin " + javob["xabar"].replace("Ulanib bo'lmadi:", "ulanib bo'lmadi:", 1))
            javob["saqlandi"] = True
        return javob
    return {"ok": False, "xato": "Noma'lum amal"}


VERSIYA = "3.1"          # telefon ilovasi shu orqali kompyuterdagi Jarvis yangi-eskiligini biladi


def _ishlayotgan_versiya():
    """Kompyuterda ishlab turgan Jarvis versiyasi (eski nusxalarda yo'q — None), javob bermasa ''."""
    import urllib.request as ur
    try:
        with ur.urlopen(f"http://127.0.0.1:{server.PORT}/holat", timeout=3) as j:
            return json.loads(j.read().decode("utf-8")).get("versiya")
    except Exception:
        return ""


def _eski_nusxani_yop():
    """Boshqa (ESKI) Jarvis ishlab turgan bo'lsa — masalan, jarvis.bat orqali ochilgan Python nusxasi —
    foydalanuvchidan so'rab uni yopadi. Yopilsa True (shu yangi nusxa ishlashda davom etadi)."""
    import ctypes
    import subprocess
    v = _ishlayotgan_versiya()
    if v == VERSIYA or v == "":
        return False                                      # o'sha versiya (yoki javob yo'q) — oddiy holat
    javob = ctypes.windll.user32.MessageBoxW(
        None, f"Kompyuterda ESKI Jarvis ishlab turibdi (versiya: {v or 'eski'}).\n"
              "Shuning uchun yangi funksiyalar (telefondan kamera qo'shish va h.k.) ishlamayapti.\n\n"
              "Eskisini yopib, yangisini ishga tushiraymi?", "Jarvis", 0x4 | 0x20 | 0x40000)   # Ha/Yo'q, ?, ustida
    if javob != 6:                                        # IDYES
        return False
    try:
        chiqish = subprocess.run(["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True,
                                 timeout=10, creationflags=0x08000000).stdout
        pidlar = {q.split()[-1] for q in chiqish.splitlines()
                  if f":{server.PORT} " in q and "LISTEN" in q.upper()}
        for pid in pidlar:
            if pid.isdigit() and int(pid) != os.getpid():
                subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True, timeout=10,
                               creationflags=0x08000000)
    except Exception as xato:
        print(f"(Eski Jarvis'ni yopib bo'lmadi: {xato})")
        return False
    time.sleep(1.5)                                       # port va mutex bo'shasin
    return True


def chatdan_keldi(matn):
    """Chat oynasida yozilgan gap — xuddi pastdagi maydonga yozilgandek miya'ga boradi
    (tasdiq so'ralsa, 'ha'ni ham chatdan yozish mumkin)."""
    kirish_navbat.put(("chat", matn, time.time()))


def web_bajar(matn):
    """Telefon ilovasidan kelgan buyruqni bajaradi va Jarvis javobini matn qilib qaytaradi."""
    global oxirgi_manba, asl_matn
    with web_qulfi:
        web_holati.yig = []
        oxirgi_manba = "web"
        asl_matn = matn
        arxiv.yoz("siz", matn, "telefon")
        try:
            bajar(ichki_tilga(normallashtir(matn)))
        except Exception as xato:
            print(f"(Web buyruq xatosi: {xato})")
            web_holati.yig.append("Buyruqni bajarishda xato bo'ldi.")
        javob = " ".join(web_holati.yig)
        web_holati.yig = None
    return javob or "Bajarildi."


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
        manzil = kamera.jarvis_rasm_yoli(
            "Veb-kamera", datetime.datetime.now().strftime("Kamera %Y-%m-%d %H-%M-%S.jpg"))
        shutil.copy(yol, manzil)
        gapir("Kamera surati Rasmlar papkasidagi Jarvis papkasiga saqlandi.")


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
        manzil = kamera.jarvis_rasm_yoli(
            "Ekran", datetime.datetime.now().strftime("Ekran rasmi %Y-%m-%d %H-%M-%S.png"))
        shutil.copy(yol, manzil)
        gapir("Ekran rasmi Rasmlar papkasidagi Jarvis, Ekran papkasiga saqlandi.")


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
            chat_och(sozlama=True)                 # chat oynasidagi to'liq sozlamalar bo'limi
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
    if getattr(web_holati, "yig", None) is not None:   # telefon ilovasidan — tasdiqsiz rad etamiz
        gapir(savol + " Buni xavfsizlik uchun faqat kompyuterdan tasdiqlash mumkin.")
        return False
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
CHAQIRUV_SOZLAR = ("jarvis", "djarvis", "jervis", "jarbis")
# Google "Jarvis"ni ko'pincha kesib yozadi: "jar", "jarv"... Bular faqat GAP BOSHIDA
# (yoki gap juda qisqa bo'lsa) chaqiruv hisoblanadi — "jarlik", "jarayon" kabi so'zlar emas.
QISQA_CHAQIRUV = {"jar", "jarv", "jarvi", "djar", "jarr", "jaar", "jarw", "jarb", "jarvs", "жар",
                  "джар", "жарв", "jars", "jarvy", "jarviz", "jarwis", "charvis", "garvis", "jervi"}


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
    if sozlar:
        birinchi = "".join(KIRILL_LOTIN.get(h, h) for h in sozlar[0]).strip(".,!?;:-\"'")
        if sozlar[0].strip(".,!?") in QISQA_CHAQIRUV or birinchi in QISQA_CHAQIRUV:
            return True, " ".join(sozlar[1:]).strip(" ,.!?")     # "jar youtube och" -> "youtube och"
    for i, soz in enumerate(sozlar):
        if chaqiruv_sozimi(soz):
            keyin = " ".join(sozlar[i + 1:]).strip(" ,.!?")
            oldin = " ".join(sozlar[:i]).strip(" ,.!?")
            return True, keyin or oldin          # "salom jarvis" -> "salom"
    return False, ""


# ---------- 4. AI (ixtiyoriy) ----------
def ai_javob(savol):
    """Suhbat uchun. AI kompyuterda hech narsa bajarmaydi.
    1) API'siz tayyor suhbat javobi;  2) bepul/pullik AI (kalit bo'lsa);
    3) hech biri bo'lmasa — muloyim taklif."""
    tayyor = suhbat.javob(savol, ISM)
    if tayyor and not sun_iy.bormi():
        return tayyor                            # kalit yo'q — offline javob
    aqlli = sun_iy.javob(savol, ISM, til())      # kalit bor bo'lsa — chinakam AI
    if aqlli:
        return aqlli
    if tayyor:
        return tayyor
    return ("Buni aniq bilmayman. Bepul sun'iy intellektga ulasangiz, har qanday savolga "
            "javob beraman. Yordam desangiz, qanday buyruqlarni bilishimni aytaman.")


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


def _fleshka_manbasi_bor(gap):
    """'games papkasini fleshkaga ko'chir' — ko'chiriladigan manba (disk yoki papka nomi) bormi?
    Bo'lsa: kompyuterdan -> fleshkaga. Bo'lmasa: fleshkadan -> ish stoliga (eski usul)."""
    disk, nomlar = kompyuter.yol_qismlari(gap)
    if disk:
        return True
    return any(not bor(n, "fleshka", "usb", "flesh", "флешка") for n in nomlar)


def fleshkaga_kochir(gap):
    """Kompyuterdagi papka/faylni fleshkaga ko'chiradi — LEKIN avval nimani va qayerga
    ko'chirishni ovoz bilan tasdiqlaydi (noto'g'ri eshitgan bo'lsa, siz yo'q deysiz)."""
    disk, nomlar = kompyuter.yol_qismlari(gap)
    nomlar = [n for n in nomlar if not bor(n, "fleshka", "usb", "flesh", "флешка")]
    if not (disk or nomlar):
        gapir("Nimani fleshkaga ko'chiray? Masalan: C diskdagi games papkasini fleshkaga ko'chir.")
        return
    yol, topilmadi = kompyuter.yol_top(disk, nomlar) if nomlar else (disk, None)
    if not yol or not os.path.exists(yol):
        gapir(f"{topilmadi or 'Manba'} topilmadi." + (f" {disk} diskida qidirdim." if disk else ""))
        return
    fleshkalar = kompyuter.usb_disklar()
    if not fleshkalar:
        gapir("USB fleshka topilmadi. Fleshkani ulang va qayta urinib ko'ring.")
        return
    flesh = fleshkalar[0]
    nom = os.path.basename(yol.rstrip("\\/")) or yol
    tur = "papka" if os.path.isdir(yol) else "fayl"
    # ISHONCH HOSIL QILISH — buyruqni darhol bajarmaymiz, avval so'raymiz:
    if not tasdiqla(f"{yol} degan {tur}ni {flesh} fleshkaga ko'chiraymi?"):
        gapir("Yaxshi, ko'chirishni bekor qildim.")
        return
    try:
        hajm = kompyuter.papka_hajmi(yol) if os.path.isdir(yol) else os.path.getsize(yol)
        bosh = shutil.disk_usage(flesh).free
        if hajm > bosh:
            gapir(f"{nom} hajmi {kompyuter.hajm_matn(hajm)}, lekin fleshkada joy yetmaydi "
                  f"({kompyuter.hajm_matn(bosh)} bo'sh). Boshqa fleshka ulang yoki joy bo'shating.")
            return
    except OSError:
        pass
    gapir(f"{nom} ni {flesh} fleshkaga ko'chiryapman. Bu biroz vaqt olishi mumkin, tugagach aytaman.")
    fonda(_fleshkaga_kochir_fonda, yol, flesh, nom)


def _fleshkaga_kochir_fonda(yol, flesh, nom):
    try:
        if os.path.isdir(yol):
            shutil.copytree(yol, os.path.join(flesh, nom),
                            ignore=kompyuter.KERAKSIZ, dirs_exist_ok=True)
        else:
            shutil.copy2(yol, flesh)
        gapir(f"{nom} fleshkaga ko'chirildi.")
    except Exception as xato:
        print(f"(Fleshkaga ko'chirish xatosi: {xato})")
        gapir("Ko'chirishda xato bo'ldi. Fleshka to'la emasligini yoki fayl ochiq emasligini tekshiring.")


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
    ortiqcha = ("och", "kir", "ishga", "tushir", "dastur", "ilova", "programma", "menga",
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


def sayt_tahlil(gap):
    url = sayt.manzil_top(gap)
    if not sun_iy.bormi():
        webbrowser.open(url)
        gapir("Saytni baholash uchun sun'iy intellekt kaliti kerak. Hozircha saytni brauzerda ochdim.")
        return
    gapir(f"{url.split('//', 1)[-1].rstrip('/')} saytini o'qiyapman...")
    try:
        malumot = sayt.oqi(url)
    except sayt.SaytXato as xato:
        gapir(f"Saytni o'qiy olmadim: {xato}.")
        return
    javob = sun_iy.sayt_tahlil(gap, malumot, til())
    if javob:
        gapir(javob, tarjima_qil=False)
    else:
        gapir("Sun'iy intellekt javob bermadi — keyinroq qayta urinib ko'ring.")


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
    url = sayt.manzil_top(gap)                      # "olx.uz saytiga kir" kabi manzil aytilsa
    if url:
        webbrowser.open(url)
        gapir(f"{url.split('//', 1)[-1].rstrip('/')} ochildi.")
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
    """AI kalit bo'lsa — hamma narsaga AI javob beradi (aqlliroq).
    Kalit bo'lmasa — savolga Vikipediya, oddiy gapga tayyor suhbat."""
    if sun_iy.bormi():                            # bepul/pullik AI ulangan
        aqlli = sun_iy.javob(gap, ISM, til())
        if aqlli:
            gapir(aqlli, tarjima_qil=False)      # AI allaqachon kerakli tilda javob berdi
            return
        # AI ishlamadi — tayyor suhbat yoki Vikipediyaga qaytamiz
    tayyor = suhbat.javob(gap, ISM)
    if tayyor:
        gapir(tayyor)
        return
    if bilim.savolmi(gap):
        javob, havola = bilim.javob_top(gap, til())
        if javob:
            gapir(javob, tarjima_qil=False)
        else:
            webbrowser.open(havola)
            gapir("Aniq javob topa olmadim, Googledan qidirib ochdim.")
    else:
        gapir(ai_javob(gap))


YORDAM_MATNI = ("Meni chaqirish uchun avval Jarvis deng, yoki oynaning pastiga yozing. "
                "Men quyidagilarni qila olaman: YouTube, Telegram, brauzer, bloknot, "
                "kalkulyator va papkalarni ochaman. Telegramda guruhni ham ocha olaman. "
                "Soat va sanani aytaman. "
                "Ob-havoni aytaman, masalan: Samarqandda ob-havo qanday. "
                "Dollar, yevro, rubl kursini Markaziy bankdan aytaman. "
                "Eslataman, masalan: 10 daqiqadan keyin choy ichishni eslat, yoki soat 18:30 da darsni eslat. "
                "Eslab qolaman, masalan: eslab qol, wifi paroli 12345. Keyin qaydlarim deng. "
                "Xayrli tong desangiz — kunlik xulosa: ob-havo, kurs va eslatmalar. "
                "Kompyuter holatini aytaman: xotira, batareya, disk. "
                "Chatni och desangiz — barcha suhbatlarimiz arxivi ochiladi. "
                "Telegramga xabarni imlo xatosiz va emoji bilan yozaman; "
                "chiziqcha bilan, ya'ni / bilan boshlasangiz — aynan yozganingizdek yuboraman. "
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
SAVOL_SOZLAR = ("qaysi", "nima uchun", "nimaga", "nega ", "qanday qilib", "tushuntir", "haqida", "kim edi",
                "kim bo'lgan", "qachon", "farqi", "maslahat", "rejalashtir", "qanaqa", "nechanchi", "ma'nosi",
                "sababi", "nima degani", "что такое", "почему", "why ", "what is", "how to")
# Bular bo'lsa — bu buyruq (bajariladi), savol emas
BUYRUQ_FELLAR = {"och", "ochib", "ochgin", "yoz", "yozib", "yubor", "yuborib", "qo'y", "qo'yib", "o'chir",
                 "ko'chir", "top", "topib", "eslat", "ko'rsat", "bos", "yop", "saqla", "o'rnat", "yangila",
                 "joyla", "yukla", "o'qi", "o'qib"}
# Jarvis'ning o'zi aniq javob beradigan mavzular (AI bilmaydi: ob-havo, kurs, kamera...)
LOKAL_MAVZU = ("ob-havo", "ob havo", "havo ", "harorat", "gradus", "kurs", "dollar", "valyuta", "eslatma",
               "soat nech", "vaqt nech", "sana", "kamera", "eshik", "telefon", "xabar", "fayl", "papka", "musiqa",
               "qo'shiq", "youtube", "telegram", "instagram", "ovoz", "batareya", "internet", "disk", "xotira",
               "kompyuter", "noutbuk", "yuz")


def aniq_savolmi(b):
    """'O'zbekistonning eng qadimiy shahri qaysi' -> True; 'ertaga ob-havo qanday' -> False (mahalliy)."""
    s = f" {b.lower()} "
    sozlar = [w.strip(".,!?") for w in s.split()]
    if len(sozlar) < 4 or not ("?" in s or any(q in s for q in SAVOL_SOZLAR)):
        return False
    if any(w in BUYRUQ_FELLAR for w in sozlar) or any(m in s for m in LOKAL_MAVZU):
        return False
    return True


def bajar(b):
    """False qaytarsa, dastur to'xtaydi."""
    global xom_rejim
    xom_rejim = b.startswith("/")            # "/..." — xabar tuzatilmasdan, aynan ketadi
    if xom_rejim:
        b = b[1:].strip()
    sozlar = b.replace(",", " ").replace("!", " ").split()
    # Faqat "xayr" / "xayr jarvis" — "xayrli tong", "xayrli kech" dasturni yopmasin
    if "xayr" in sozlar and len(sozlar) <= 3:
        gapir(f"Xayr, {ISM}!")
        return False

    # "cuticlehair.co saytiga kirib 1 dan 10 gacha baholab ber" — saytni o'qib, AI'ga tahlil qildiramiz
    elif sayt.tahlilmi(b):
        sayt_tahlil(b)

    # Aniq savol ("... qaysi?", "nima uchun ...", "... haqida gapir") — AI'ga. Aks holda savol
    # ichidagi tasodifiy so'z ("shahri", "kamera") mahalliy buyruq bo'lib qolishi mumkin edi.
    elif sun_iy.bormi() and aniq_savolmi(b):
        javob_ber(b)

    # ----- Instagram (rasmiy API): joylash, izohlar, statistika -----
    elif bor(b, "instagram", "инстаграм", "insta") and re.search(r"\b(joyla|yukla|reels|post qil|videoni)", b) \
            and not re.search(r"\b\w+(ga|ka|qa) .+ deb yoz", b):
        ig_joylash(b)

    elif bor(b, "instagram", "инстаграм", "insta") and bor(b, "izoh", "komment", "коммент"):
        ig_izohlar()

    elif bor(b, "instagram", "инстаграм", "insta") and bor(b, "statistika", "ko'rildi", "ko'rish", "layk",
                                                            "obunachi", "podpischik", "подписчик"):
        ig_statistika()

    # Telefon buyruqlari eng birinchi tekshiriladi ("ko'chir"da "o'chir" bor kabi
    # chalkashliklar bo'lmasligi uchun)
    elif bor(b, "telefon", "телефон", "smartfon") and telefon_amal(b):
        pass

    elif (bor(b, "xabar", "sms", "сообщен") and bor(b, "o'qi", "oqi", "o'qib", "kim yoz", "keldimi", "bormi", "прочит"))\
            and not bor(b, "deb yoz", "ga yoz", "yubor"):
        tg_oqilmaganlarni_oqi()                         # "kelgan xabarlarni o'qi"

    elif (bor(b, "arxiv", "архив", "suhbatlar tarixi", "tarixni") or (
            bor(b, "chat", "чат") and bor(b, "och", "ko'rsat", "откр")))\
            and not bor(b, "yoz", "yubor", "telegram", "instagram", "whatsapp"):
        chat_och()
        gapir("Chat oynasini ochdim. Barcha suhbatlarimiz arxivda saqlangan.")

    elif bor(b, "avtomatik", "avto ishga", "windows bilan", "автозапуск", "o'zi ishga tush", "ozi ishga tush"):
        yoqilsin = not bor(b, "o'chir", "ochir", "bekor", "kerak emas")
        if kompyuter.avtostart(yoqilsin):
            gapir("Endi kompyuter yonganda men ham o'zim ishga tushaman." if yoqilsin
                  else "Avtomatik ishga tushish o'chirildi.")
        else:
            gapir("Buni sozlay olmadim.")

    # ----- eshik, yuz, jonli kamera -----
    elif bor(b, "skaner", "скан", "scan") or (bor(b, "yuz") and bor(b, "tekshir") and bor(b, "eshik")):
        eshik_skaner_buyrugi()                            # "skanerla", "eshikni skanerla"

    elif ESHIK_OCH_RE.search(b) and not bor(b, "ochma", "kamera", "ko'rsat", "yop", "berk"):
        eshik_buyrugi()                                   # faqat aniq "eshikni och" iborasi

    elif bor(b, "yuzimni", "yuzini", "meni tani", "meni eslab", "yuzimga") and bor(
            b, "eslab", "tani", "qo'sh", "o'rgan", "saqla"):
        ism = ISM
        m = re.search(r"(\w+)(?:ning|ni)? yuzini", b)
        if "yuzini" in b and m and m.group(1) not in ("uning", "mening"):
            ism = m.group(1).title()                        # "alisherning yuzini eslab qol"
        gapir(f"{ism}, kompyuter kamerasiga qarang. 5 soniya davomida rasmga olaman.")
        ok, xabar = yuz_qosh(ism, "veb")
        gapir(xabar)

    elif bor(b, "yuz", "eshik") and bor(b, "tanib", "tanish", "avtomatik") and bor(
            b, "yoq", "och", "boshla", "o'chir", "ochir", "to'xtat"):
        yoqilsin = not bor(b, "o'chir", "ochir", "to'xtat", "toxtat", "kerak emas")
        if yoqilsin and not yuz.Tanuvchi.ol().odamlar():
            gapir("Avval yuzingizni o'rgating: 'yuzimni eslab qol' deng.")
        elif yuz_eshikni_yoq(yoqilsin):
            gapir("Eshik kamerasini kuzatyapman. Tanish yuzni ko'rsam, eshikni ochaman.")
        else:
            gapir("Yuz bilan eshik ochish o'chirildi." if not yoqilsin else "Eshik kamerasi topilmadi.")

    elif kameralar() and bor(b, "jonli", "live", "онлайн", "real vaqt") and bor(b, "kamera", "hovli", "eshik", "uy"):
        jonli_kamera(b)

    # ----- uy kameralari -----
    elif bor(b, "kuzat", "qo'riqla", "qoriqla", "qo'riqlash", "ohrana", "охран", "nazorat") \
            and bor(b, "to'xtat", "toxtat", "o'chir", "ochir", "bekor", "yetarli") and not bor(b, "ekran"):
        kuzatuvni_yoq(False)
        gapir("Kamera kuzatuvi to'xtatildi.")

    elif bor(b, "kuzat", "qo'riqla", "qoriqla", "ohrana", "охран", "harakatni sez") \
            and bor(b, "kamera", "uy", "hovli", "harakat", "eshik", "qo'riqla", "qoriqla") and not bor(b, "ekran"):
        if not kameralar():
            gapir("Hali kamera qo'shilmagan. Chatdagi Sozlamalar, Kamera bo'limida qo'shing.")
        else:
            soni = kuzatuvni_yoq(True)
            qosh = "" if (bot and bot.egasi) else " Telegram ulanmagan — xabarlar faqat chatda ko'rinadi."
            gapir(f"{soni} ta kamerani kuzatyapman. Odam paydo bo'lsa, jonli videoni ochaman va rasm bilan xabar beraman."
                  f" Mushuk, soya, shamol kabi narsalarga e'tibor bermayman.{qosh}")

    elif kameralar() and (bor(b, "uy kamera", "hovli", "eshik old", "ko'cha", "hikvision", "kamerada",
                               "uyda kim", "uyda nima", "kamerani ko'rsat", "kamerani och", "kamera rasm",
                               *[normallashtir(k["nom"]) for k in kameralar() if len(k.get("nom", "")) > 3])
                          or (bor(b, "kamera", "камера") and not bor(
                              b, "kompyuter kamera", "veb", "webcam", "selfi", "selfie", "kim o'tiribdi",
                              "kim otiribdi", "noutbuk"))):
        uy_kamera_rasmi(b)

    # ----- kundalik qulayliklar -----
    elif re.search(r"\b(mening shahrim|shahrim|men yashaydigan shahar)\b", b) and "?" not in b \
            and any(s in b for s in qulayliklar.SHAHARLAR):
        shahar, nomi = qulayliklar.shahar_top(b, "")
        sozlama_ozgartir("shahar", next(k for k, v in qulayliklar.SHAHARLAR.items() if v[1] == nomi),
                         ayt=False)
        gapir(f"Eslab qoldim: shahringiz {nomi}. Endi ob-havoni shu shahar uchun aytaman.")

    elif bor(b, "xayrli tong", "brifing", "bugungi xulosa", "kunlik xulosa", "доброе утро"):
        gapir("Bir soniya, ma'lumotlarni yig'yapman.")
        gapir(qulayliklar.brifing(ISM, SOZ.get("shahar", "toshkent"),
                                  len(eslatmalar.faollar()) if eslatmalar else 0))

    elif bor(b, "ob-havo", "ob havo", "obhavo", "havo qanday", "harorat", "necha gradus",
             "погода", "weather", "yomg'ir yog'adimi", "sovuqmi", "issiqmi"):
        gapir(qulayliklar.ob_havo(b, SOZ.get("shahar", "toshkent")))

    elif bor(b, "kurs", "курс") or (bor(b, *qulayliklar.VALYUTALAR) and bor(b, "necha", "qancha", "narx")):
        gapir(qulayliklar.kurs(b))

    elif bor(b, "eslatmalar", "eslatmalarim", "taymerlar") and bor(b, "o'chir", "bekor", "tozala"):
        soni = eslatmalar.tozala() if eslatmalar else 0
        gapir(f"{soni} ta eslatma bekor qilindi." if soni else "Faol eslatma yo'q edi.")

    elif bor(b, "eslatmalarim", "eslatmalar", "taymerlar", "qanday eslatma"):
        faol = eslatmalar.faollar() if eslatmalar else []
        if not faol:
            gapir("Hozir faol eslatma yo'q.")
        else:
            gapir(f"{len(faol)} ta eslatma bor: " + "; ".join(
                f"{e['ish']} — {datetime.datetime.fromtimestamp(e['vaqt']):%H:%M} da" for e in faol[:5]) + ".")

    elif bor(b, "qaydlarni o'chir", "qaydlarimni o'chir", "eslab qolganlaringni o'chir"):
        if tasdiqla("Barcha qaydlarni o'chiraymi?"):
            qulayliklar.qaydlarni_ochir()
            gapir("Qaydlar o'chirildi.")

    elif bor(b, "qaydlarim", "nimalarni eslab qolding", "eslab qolganlaring", "qaydlarni ayt",
             "qaydlarni o'qi"):
        royxat = qulayliklar.qaydlar()
        if not royxat:
            gapir("Hali hech narsa eslab qolmadim. Masalan: eslab qol, wifi paroli 12345.")
        else:
            gapir(f"{len(royxat)} ta qayd bor. " + " ".join(
                f"{i}) {q['matn']}." for i, q in enumerate(royxat[-7:], 1)))

    elif bor(b, "eslab qol", "yodda tut", "qayd qil", "запомни"):
        matn = qulayliklar.qayd_matni(asl_korinish(b) if asl_matn else b) or qulayliklar.qayd_matni(b)
        if not matn:
            gapir("Nimani eslab qolay? Masalan: eslab qol, mashina raqami 01 A 777 AA.")
        else:
            soni = qulayliklar.qayd_qosh(matn)
            gapir(f"Eslab qoldim ✅ Bu {soni}-qayd. 'Qaydlarim' desangiz, hammasini aytaman.")

    elif bor(b, "eslat", "esimga sol", "taymer", "budilnik", "напомни", "remind") \
            and not bor(b, "deb yoz", "telegram", "instagram"):
        soniya, ish = qulayliklar.eslatma_ajrat(b)
        if not soniya:
            gapir("Qachon eslatay? Masalan: 10 daqiqadan keyin choy ichishni eslat, "
                  "yoki soat 18:30 da darsni eslat.")
        elif eslatmalar:
            eslatmalar.qosh(soniya, ish)
            vaqt = datetime.datetime.now() + datetime.timedelta(seconds=soniya)
            gapir(f"Xo'p! {qulayliklar.vaqt_matn(soniya)} keyin, soat {vaqt:%H:%M} da eslataman: {ish}. ⏰")

    elif bor(b, "kompyuter holati", "kompyuter qanday", "batareya", "zaryad", "operativ xotira",
             "kompyuter qiziyaptimi", "kompyuter sekin"):
        gapir(qulayliklar.kompyuter_holati())

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

    elif bor(b, "telegram", "телеграм", "instagram", "инстаграм", "insta", "whatsapp",
             "vatsap", "votsap", "ватсап", "messenger", "vkontakte") and " ga " in (" " + b + " ") \
            and any(s.startswith(("yoz", "yubor", "jo'nat", "xabar")) for s in b.split()):
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
            b, "nusxa", "ko'chir", "kochir", "copy", "tashla", "saqla") and not bor(
            b, "desktop", "ish stoli", "stolga") and _fleshka_manbasi_bor(b):
        # "C diskdagi games papkasini fleshkaga ko'chir" — avval tasdiq so'raydi
        fleshkaga_kochir(b)

    elif bor(b, "usb", "юсб", "fleshka", "флешка", "flesh") and bor(
            b, "nusxa", "ko'chir", "kochir", "copy", "desktop", "ish stoli"):
        if tasdiqla("Fleshkadagi hamma fayllarni ish stoliga nusxalaymi?"):
            usb_nusxala()
        else:
            gapir("Yaxshi, bekor qildim.")

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

    elif bor(b, "this pc", "bu kompyuter", "mening kompyuter", "kompyuterim", "computer",
             "мой компьютер", "этот компьютер") and bor(b, "och", "kir", "ko'rsat", "ber"):
        subprocess.Popen("explorer shell:MyComputerFolder", shell=True)
        gapir("Bu kompyuter ochildi.")

    elif bor(b, "disk", "диск") and bor(b, "och", "kir", "ko'rsat", "ber"):
        m = re.search(r"([a-z])\s*(?:disk|диск)", b)
        harf = m.group(1).upper() if m else "C"
        yol = f"{harf}:\\"
        if os.path.exists(yol):
            subprocess.Popen(f'explorer "{yol}"', shell=True)
            gapir(f"{harf} diski ochildi.")
        else:
            gapir(f"{harf} diski topilmadi.")

    elif bor(b, "yuklama", "hujjatlar papka", "rasmlar papka", "videolar papka", "musiqa papka",
             "ish stoli", "downloads", "documents", "pictures", "videos") and bor(
             b, "och", "kir", "ko'rsat", "ber"):
        papkalar = [(("yuklama", "download"), "Downloads"), (("hujjat", "document"), "Documents"),
                    (("rasm", "picture"), "Pictures"), (("video",), "Videos"),
                    (("musiqa", "music"), "Music"), (("ish stoli", "desktop"), "Desktop")]
        nom = next((p for sozlar, p in papkalar if bor(b, *sozlar)), "Downloads")
        yol = kompyuter.desktop_yoli() if nom == "Desktop" else os.path.join(os.path.expanduser("~"), nom)
        subprocess.Popen(f'explorer "{yol}"', shell=True)
        gapir(f"{nom} papkasi ochildi.")

    elif bor(b, "papka", "fayllar", "provodnik", "file explorer", "fayl menejer", "file", "fayl",
             "explorer", "проводник") and not bor(b, "yubor", "tashla", "qidir", "top"):
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


    elif any(s.startswith(("och", "kir")) for s in b.split()) or bor(b, "ishga tushir"):
        ilova_och(b)

    elif b:
        javob_ber(b)

    return True


# ---------- ASOSIY SIKL (miya thread'i) ----------
def miya():
    global media_boshlandi, javob_telegramga, oxirgi_manba, eslatmalar
    ui_navbat.put(("sozlamalar", dict(SOZ)))
    telegram_ishga_tushir()
    eslatmalar = qulayliklar.Eslatmalar(eslatma_vaqti)     # eski eslatmalar ham tiklanadi
    if SOZ.get("yuz_eshik") and kameralar():
        fonda(yuz_eshikni_yoq, True)
    if SOZ.get("kamera_kuzatuv") and kameralar():
        print(f"📹 Kamera kuzatuvi davom etyapti: {kuzatuvni_yoq(True)} ta kamera")
    fonda(tga_ishga_tushir)                         # do'stlardan kelgan Telegram xabarlari
    ig_rejalarni_tikla()                            # rejalashtirilgan Instagram postlari
    pin = str(SOZ.get("telefon_pin") or "0000")
    himoya.ogohlantir = lambda matn: bot.yoz(matn) if bot and bot.egasi else None
    server.chat_sozla(chatdan_keldi, lambda: joriy_holat, chat_sozlamalari, chat_sozlama_yoz)
    server.kamera_ol = lambda nom: next((k for k in kameralar() if k["nom"] == nom), None)
    server.tel_amal = telefon_kamera_amali
    server.versiya = VERSIYA
    threading.Thread(target=internetni_kuzat, daemon=True).start()
    ishladi = server.ishga_tushir(web_bajar, pin)
    if not ishladi and os.name == "nt" and _eski_nusxani_yop():   # port band — eski Jarvis (mutexsiz) ishlayapti
        ishladi = server.ishga_tushir(web_bajar, pin)
    if ishladi:
        print(f"📱 Telefon ilovasi (Wi-Fi): http://{server.ip_manzil()}:{server.PORT}  (PIN: {pin})")
        print(f"💬 Chat va arxiv: http://127.0.0.1:{server.PORT}/chat")
        if SOZ.get("chat_avto", True):
            chat_och()                              # chat oynasi o'zi ochiladi
    # Bulut ko'prigi — istalgan joydan ishlash uchun (bir Wi-Fi shart emas)
    kanal = SOZ.get("telefon_kanal")
    if not kanal:
        import uuid
        kanal = "jv-" + uuid.uuid4().hex[:12]
        sozlama_ozgartir("telefon_kanal", kanal, ayt=False)
    if not SOZ.get("bulut_kalit"):                  # uydan tashqarida kamera uchun shifrlash kaliti (bir marta)
        sozlama_ozgartir("bulut_kalit", os.urandom(32).hex(), ayt=False)
    try:
        import importlib
        importlib.import_module("cryptography.hazmat.primitives.ciphers.aead")
        shifr_kalit = bytes.fromhex(SOZ["bulut_kalit"])
    except BaseException as xato:                   # kutubxona yo'q yoki buzuq — Jarvis baribir ishlasin
        if isinstance(xato, (KeyboardInterrupt, SystemExit)):
            raise
        shifr_kalit = None
        print("(Uydan tashqarida kamera uchun: pip install cryptography)")
    bulut_holat = bulut.ishga_tushir(kanal, pin, web_bajar, kalit=shifr_kalit, amal=telefon_kamera_amali)
    if bulut_holat == "ok":
        print(f"☁️ Internet orqali boshqarish — Kanal: {kanal}  (PIN: {pin})")
    elif bulut_holat == "yoq_kutubxona":
        print("☁️ Internet orqali boshqarish uchun: pip install paho-mqtt")
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

        if not suhbatda and not tg_navbat.empty():          # do'stdan Telegram xabar keldi
            try:
                tg_xabarni_ol(tg_navbat.get_nowait())
            except queue.Empty:
                pass
            except Exception as xato:
                print(f"(Telegram xabar xatosi: {xato})")
            continue

        kelgan = keyingi_gap(qoldi if suhbatda else 1.0)
        if not kelgan:
            continue
        manba, gap = kelgan

        if manba == "uygon":                        # sharni bosdi — uyg'onadi
            gapir(f"Labbay, {ISM}?")
            suhbat_tugashi = time.time() + SUHBAT_VAQTI
            continue

        chaqirildi, buyruq = chaqiruvni_ajrat(gap)
        if not chaqirildi:
            if manba == "ovoz" and not suhbatda:
                continue                                # begona gap / qo'shiq — e'tibor bermaymiz
            buyruq = gap                                # yozilgan gapga "Jarvis" shart emas
        javob_telegramga = manba == "telegram"
        oxirgi_manba = "ovoz" if manba == "uzish" else manba
        ui_navbat.put(("siz", ("(Telegram) " if javob_telegramga else "") + gap))
        arxiv.yoz("siz", asl_matn if manba != "ovoz" else gap, manba)
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

        # Buyruq bajarildi — darhol kutishga qaytamiz (yana faqat "Jarvis" desangiz eshitadi,
        # boshqa ovozlarga / TV / suhbatga javob bermaydi). Oyna ekrandan yo'qoladi.
        suhbat_tugashi = 0
        if media_boshlandi:
            print("💤 Musiqa qo'yildi, faqat Jarvis desangiz eshitaman.")
        else:
            print("💤 Kutish rejimi (faqat Jarvis desangiz).")
    ui_navbat.put(("yopil",))


if __name__ == "__main__":
    import interfeys
    if "--tekshir" in sys.argv:          # EXE to'g'ri yig'ilganini tekshirish (GitHub'da)
        import speech_recognition
        import pyaudio                   # noqa: F401  — mikrofon
        flac = speech_recognition.get_flac_converter()    # Google ovoz tanishi uchun kerak
        for ixtiyoriy in ("paho.mqtt.client", "cv2", "uiautomation", "shazamio", "webview", "clr",
                          "anthropic", "telethon", "telegram_akkaunt", "qrcode", "cryptography", "instagram", "instagram_brauzer"):
            try:
                __import__(ixtiyoriy)
                print(f"  + {ixtiyoriy}")
            except Exception as xato:
                print(f"  - {ixtiyoriy}: {xato}")
        try:                             # Instagram orqa fon rejimi: playwright + Edge
            from playwright.sync_api import sync_playwright
            with sync_playwright() as _p:
                _b = _p.chromium.launch(channel="msedge", headless=True)
                _b.close()
            print("  + playwright/edge (Instagram orqa fon)")
        except Exception as xato:
            print(f"  - playwright/edge: {xato}")
        yuz.Tanuvchi.ol()                # yuz tanish modellari EXE ichida va ishlaydi
        import odam
        odam.OdamAniqlagich.ol()
        print("  + yuz tanish va odamni aniqlash modellari")
        print(f"Jarvis tayyor. Barcha modullar yuklandi. FLAC: {flac}")
        sys.exit(0)
    if os.name == "nt":                  # faqat bitta Jarvis ishlasin (mikrofon va port to'qnashmasin)
        import ctypes
        _mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Jarvis_yagona_nusxa")
        if ctypes.windll.kernel32.GetLastError() == 183:          # ERROR_ALREADY_EXISTS
            if not _eski_nusxani_yop():
                chat_och()                                        # ishlab turganining chati ochiladi
                sys.exit(0)
    oyna = interfeys.Oyna(ui_navbat, kirish_navbat, SOZ)     # oyna — asosiy thread'da
    threading.Thread(target=mikrofon_ishi, daemon=True).start()
    threading.Thread(target=miya, daemon=True).start()
    oyna.ishga_tushir()
