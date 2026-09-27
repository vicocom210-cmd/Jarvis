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
import kompyuter

ISM = "Abdulloh"                 # Jarvis sizni shunday chaqiradi
OVOZ = "uz-UZ-SardorNeural"      # ayol ovozi uchun: "uz-UZ-MadinaNeural"
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
gapiryapti = threading.Event()    # Jarvis gapirayotganda mikrofon o'z ovozini eshitmasin
gap_tugadi = 0.0                  # Jarvis oxirgi marta qachon gapirib bo'ldi


def gapir(matn):
    print(f"Jarvis: {matn}")
    ui_navbat.put(("jarvis", matn))
    with ovoz_qulfi:
        oldingi = joriy_holat
        gapiryapti.set()
        try:
            _gapir(matn)
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


def _gapir(matn):
    try:
        asyncio.run(edge_tts.Communicate(matn, OVOZ).save(AUDIO_FAYL))
        tovush = pygame.mixer.Sound(AUDIO_FAYL)
        try:
            ui_navbat.put(("ovoz", ovoz_balandliklari(tovush), time.time()))
        except Exception:
            pass
        holat("gapirish")
        kanal = tovush.play()
        while kanal.get_busy():
            time.sleep(0.05)
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
            if gapiryapti.is_set():
                time.sleep(0.1)
                continue
            boshlandi = time.time()
            try:
                audio = tanib.listen(mic, timeout=3, phrase_time_limit=7)
            except sr.WaitTimeoutError:
                continue
            except Exception as xato:           # mikrofon uzilsa ham thread to'xtamasin
                print(f"(Mikrofon xatosi: {xato})")
                time.sleep(1)
                continue
            if gapiryapti.is_set() or gap_tugadi > boshlandi:
                continue                    # bu Jarvisning o'z ovozi edi
            threading.Thread(target=matnga_aylantir, args=(audio,), daemon=True).start()


def matnga_aylantir(audio):
    try:
        matn = tanib.recognize_google(audio, language="uz-UZ")
    except sr.UnknownValueError:
        return
    except sr.RequestError:
        print("(Internet bilan muammo bor)")
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
        if manba == "yozuv":
            matn = normallashtir(matn)
        if vaqt >= gap_tugadi:
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
    return gap[1]


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
    return any(s in ("ha", "xa", "ha'", "albatta", "roziman") for s in javob)


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
             "ko'rsat", "topib", "qidir", "ochib", "kerak", "keker", "iltimos")
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
    gapir("Musiqani yoqing, 10 soniya tinglayman.")
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
def ilova_nomi(gap):
    """'photoshopni ochib ber' -> 'photoshop'"""
    ortiqcha = ("och", "ishga", "tushir", "dastur", "ilova", "programma", "menga",
                "iltimos", "ber", "yoq")
    sozlar = []
    for s in gap.split():
        if s.startswith(ortiqcha):
            continue
        if len(s) > 4 and s.endswith(("ni", "ga")):
            s = s[:-2]
        sozlar.append(s)
    return " ".join(sozlar).strip()


def ilova_och(gap):
    nom = ilova_nomi(gap)
    if not nom:
        gapir("Qaysi dasturni ochay?")
        return
    topildi = kompyuter.ilova_top(nom)
    if not topildi:
        gapir(f"{nom} degan dastur topilmadi.")
        return
    nomi, yol = topildi
    try:
        kompyuter.ilova_och(yol)
        gapir(f"{nomi} ochildi.")
    except OSError:
        gapir(f"{nomi} ochilmadi.")


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
    javob, havola = bilim.javob_top(gap)
    if javob:
        gapir(javob)
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
                "To'xtatish uchun xayr deng.")


# ---------- 6. BUYRUQLAR (faqat ruxsat berilganlar) ----------
def bajar(b):
    """False qaytarsa, dastur to'xtaydi."""
    if bor(b, "xayr", "to'xta"):
        gapir(f"Xayr, {ISM}!")
        return False

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

    elif bor(b, "kompyuter") and bor(b, "o'chir"):
        if tasdiqla("Rostdan kompyuterni o'chiraymi?"):
            gapir("10 soniyadan keyin o'chadi.")
            subprocess.run("shutdown /s /t 10", shell=True)
        else:
            gapir("Bekor qilindi.")

    elif any(s.startswith("och") for s in b.split()) or bor(b, "ishga tushir"):
        ilova_och(b)

    elif b:
        javob_ber(b)

    return True


# ---------- ASOSIY SIKL (miya thread'i) ----------
def miya():
    global media_boshlandi
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
        ui_navbat.put(("siz", gap))
        if not buyruq:
            gapir(f"Labbay, {ISM}?")
            suhbat_tugashi = time.time() + SUHBAT_VAQTI
            continue

        holat("o'ylash")
        media_boshlandi = False
        try:
            davom = bajar(buyruq)
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
    oyna = interfeys.Oyna(ui_navbat, kirish_navbat)     # oyna — asosiy thread'da
    threading.Thread(target=mikrofon_ishi, daemon=True).start()
    threading.Thread(target=miya, daemon=True).start()
    oyna.ishga_tushir()
