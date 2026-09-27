"""
O'zbekcha JARVIS — Windows uchun ovozli yordamchi (2-versiya)
Qo'shimcha:  pip install shazamio   (musiqani tanish uchun)
Ishga tushirish:  PyCharm'dagi yashil ▶ tugma
Chaqirish:  "Jarvis" deng (yoki "Jarvis, youtubeni och" deb bitta gapda ayting)
"""
import asyncio
import datetime
import difflib
import os
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

import kompyuter

OVOZ = "uz-UZ-SardorNeural"      # ayol ovozi uchun: "uz-UZ-MadinaNeural"
MATN_REJIMI = False              # True qilsangiz, mikrofon o'rniga klaviaturadan yozasiz
SUHBAT_VAQTI = 8                 # buyruqdan keyin shuncha soniya "Jarvis" demasdan gapirsa bo'ladi

pygame.mixer.init()
tanib = sr.Recognizer()
AUDIO_FAYL = os.path.join(tempfile.gettempdir(), "jarvis_javob.mp3")


# ---------- 1. GAPIRISH ----------
ovoz_qulfi = threading.Lock()     # ikki ish bir vaqtda gapirmoqchi bo'lsa, navbat bilan gapiradi


def gapir(matn):
    print(f"Jarvis: {matn}")
    with ovoz_qulfi:
        _gapir(matn)


def _gapir(matn):
    try:
        pygame.mixer.music.unload()
        asyncio.run(edge_tts.Communicate(matn, OVOZ).save(AUDIO_FAYL))
        pygame.mixer.music.load(AUDIO_FAYL)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.music.unload()
    except Exception as xato:
        print(f"(Ovoz chiqmadi: {xato})")


# ---------- 2. ESHITISH ----------
def normallashtir(matn):
    for belgi in "‘’ʻʼ`":
        matn = matn.replace(belgi, "'")
    return matn.lower().strip()


def eshit(kutish=8, jim=False):
    """Mikrofondan bitta gapni eshitib, matnga aylantiradi.
    kutish — gap boshlanishini necha soniya kutish.
    jim=True — kutish rejimida xatolarni ovoz chiqarib aytmaydi."""
    if MATN_REJIMI:
        return normallashtir(input("Siz: "))
    with sr.Microphone() as mic:
        tanib.adjust_for_ambient_noise(mic, duration=0.5)
        print("🎤 Tinglayapman..." if not jim else "💤 Kutyapman (Jarvis deng)...")
        try:
            audio = tanib.listen(mic, timeout=kutish, phrase_time_limit=7)
        except sr.WaitTimeoutError:
            return ""
    try:
        matn = tanib.recognize_google(audio, language="uz-UZ")
        print(f"Eshitildi: {matn}")
        return normallashtir(matn)
    except sr.UnknownValueError:
        return ""
    except sr.RequestError:
        if jim:
            print("(Internet bilan muammo bor)")
        else:
            gapir("Internet bilan muammo bor.")
        return ""


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
        return "Tushunmadim. Yordam desangiz, qanday buyruqlarni bilishimni aytaman."
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
    with sr.Microphone() as mic:
        audio = tanib.record(mic, duration=10)
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


YORDAM_MATNI = ("Meni chaqirish uchun avval Jarvis deng. "
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
                "To'xtatish uchun xayr deng.")


# ---------- 6. BUYRUQLAR (faqat ruxsat berilganlar) ----------
def bajar(b):
    """False qaytarsa, dastur to'xtaydi."""
    if bor(b, "xayr", "to'xta"):
        gapir("Xayr, xo'jayin!")
        return False

    elif bor(b, "salom", "assalom"):
        gapir("Va alaykum assalom! Buyruq bering.")

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

    elif bor(b, "kesh", "кеш", "cache", "vaqtinchalik fayl", "musor", "axlat") and bor(
            b, "tozala", "o'chir", "tozalab"):
        keshni_tozala()

    elif bor(b, "usb", "юсб", "fleshka", "флешка", "flesh") and bor(
            b, "nusxa", "ko'chir", "kochir", "copy", "desktop", "ish stoli"):
        usb_nusxala()

    elif bor(b, *YOUTUBE_SOZLAR) or bor(b, "video", "klip", "rolik"):
        soz = youtube_qidiruv_sozi(b)
        if soz and bor(b, *IJRO_SOZLAR):
            gapir(f"{soz} qo'yilmoqda.")
            youtube_ijro(soz)
        else:
            webbrowser.open("https://youtube.com")
            gapir("YouTube ochildi.")

    elif bor(b, "musiq", "qo'shiq", "qo'shig") and bor(b, "qo'y", "qo'", "ijro", "eshit"):
        soz = youtube_qidiruv_sozi(b)
        gapir(f"{soz} qo'yilmoqda.")
        youtube_ijro(soz)

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
        gapir(ai_javob(b))

    return True


# ---------- ASOSIY SIKL ----------
def ishga_tushir():
    global media_boshlandi
    gapir("Salom! Men Jarvisman. Kerak bo'lsam, Jarvis deb chaqiring.")
    suhbat_tugashi = 0          # shu vaqtgacha "Jarvis" demasdan gapirsa bo'ladi

    while True:
        qoldi = suhbat_tugashi - time.time()
        suhbatda = qoldi > 0

        if suhbatda:
            gap = eshit(kutish=qoldi)                   # "Jarvis" shart emas
        else:
            gap = eshit(kutish=10, jim=True)            # faqat "Jarvis"ni kutamiz
        if not gap:
            if suhbatda and time.time() >= suhbat_tugashi:
                print("💤 Kutish rejimiga qaytdim.")
            continue

        chaqirildi, buyruq = chaqiruvni_ajrat(gap)
        if not chaqirildi:
            if not suhbatda:
                continue                                # begona gap / qo'shiq — e'tibor bermaymiz
            buyruq = gap
        elif not buyruq:
            gapir("Labbay, xo'jayin?")
            suhbat_tugashi = time.time() + SUHBAT_VAQTI
            continue

        media_boshlandi = False
        if not bajar(buyruq):
            break

        if media_boshlandi:
            suhbat_tugashi = 0                          # musiqa ketyapti — darhol kutish rejimi
            print("💤 Musiqa qo'yildi, faqat Jarvis desangiz eshitaman.")
        else:
            suhbat_tugashi = time.time() + SUHBAT_VAQTI


if __name__ == "__main__":
    ishga_tushir()
