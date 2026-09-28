"""
Jarvis'ning ko'rinishi.

1) Asosiy oyna — faqat minglab nuqtalardan iborat 3D shar.
   Kutishda ekran burchagida kichik, "Jarvis" deganda ekran o'rtasida katta.
   Gapirganda shar har safar boshqa shaklga kiradi (yurak, DNK, galaktika...),
   gap tugagach yana sharga qaytadi.
2) Sozlamalar — butun ekranni qoplaydigan alohida ilova (animatsiyali tugmalar bilan).

Bu oyna ASOSIY thread'da ishlaydi. Tinglash va buyruqlar boshqa thread'da.
Ular bir-biri bilan ikkita navbat (queue) orqali gaplashadi:
  ui_navbat     — Jarvis -> oyna:  ("holat", "kutish"), ("siz", matn), ("jarvis", matn),
                                    ("ovoz", balandliklar, boshlanish_vaqti),
                                    ("sozlamalar", lug'at), ("sozlamalarni_och",),
                                    ("sozlamalarni_yop",), ("yopil",)
  kirish_navbat — oyna -> Jarvis:  ("yozuv", matn, vaqt)           — pastga yozilgan buyruq
                                    ("sozlama", (kalit, qiymat), vaqt) — menyuda tanlangan
                                    ("ovoz_sinov", "ayol"/"erkak", vaqt) — ovozni eshitib ko'rish
"""
import math
import os
import sys
import queue
import random
import time

import pygame

import sozlamalar as S

NUQTALAR_SONI = 2200
FPS = 40
FON = (0, 0, 0)               # shu rang shaffof bo'ladi (Windows)
PANEL = (10, 16, 28)

# Tepadagi kichik shar (kutish rejimi) o'lchamlari
MINI_R = 36
MINI_ENI, MINI_BOYI = 110, 104
MINI_YOZ_ENI, MINI_YOZ_BOYI = 440, 104 + 60

# Holat: kattalik, aylanish tezligi, yorqinlik. Rang — tanlangan mavzudan olinadi.
HOLATLAR = {
    "kutish":   {"kattalik": 0.80, "tezlik": 0.25, "yorqinlik": 0.55},
    "tinglash": {"kattalik": 1.00, "tezlik": 0.95, "yorqinlik": 1.00},
    "o'ylash":  {"kattalik": 0.92, "tezlik": 1.60, "yorqinlik": 0.85},
    "gapirish": {"kattalik": 0.95, "tezlik": 0.60, "yorqinlik": 1.00},
    "shazam":   {"kattalik": 1.00, "tezlik": 1.20, "yorqinlik": 1.00},
}

# Ovozlarning qisqa nomlari (sozlamalar ilovasida ko'rsatiladi)
OVOZ_NOMLARI = {"uz": ("Madina", "Sardor"), "ru": ("Svetlana", "Dmitry"),
                "en": ("Jenny", "Guy"), "de": ("Katja", "Conrad")}
# Bayroq ranglari (sof qora ishlatilmaydi — u shaffof bo'lib qoladi)
BAYROQLAR = {"uz": [(30, 150, 230), (240, 240, 240), (30, 170, 80)],
             "ru": [(240, 240, 240), (30, 80, 200), (220, 40, 50)],
             "en": [(30, 60, 150), (240, 240, 240), (200, 30, 50)],
             "de": [(25, 25, 25), (220, 30, 40), (250, 200, 30)]}

# Oyna yozuvlari 4 tilda
YOZUVLAR = {
    "uz": {"kutish": "Kutish rejimi — Jarvis deng", "tinglash": "Tinglayapman…",
           "o'ylash": "Bajaryapman…", "gapirish": "Gapiryapman…",
           "shazam": "Musiqani tinglayapman…", "yozing": "Buyruq yozing…",
           "siz": "Siz", "sozlamalar": "Sozlamalar", "ovoz": "Ovoz", "ayol": "Ayol ovozi",
           "erkak": "Erkak ovozi", "til": "Til", "korinish": "Ko'rinish", "profil": "Profil",
           "haqida": "Haqida", "yopish": "Yopish", "saqlash": "Saqlash",
           "sinab": "Eshitib ko'rish", "tanlangan": "Tanlangan",
           "ovoz_izoh": "Jarvis qaysi ovozda gapirsin?",
           "til_izoh": "Jarvis qaysi tilda eshitsin va gapirsin?",
           "korinish_izoh": "Shar rangini tanlang. O'ngda — jonli ko'rinish.",
           "profil_izoh": "Jarvis sizni shu ism bilan chaqiradi.",
           "haqida_izoh": "O'zbekcha ovozli yordamchi.",
           "haqida_matn": ["\"Jarvis\" deb chaqiring yoki pastdagi maydonga yozing.",
                           "\"Yordam\" desangiz, barcha buyruqlarni aytib beraman.",
                           "Sozlamalarni ovoz bilan ham yopish mumkin: \"sozlamalarni yop\".",
                           "Gapirganimda shar har safar yangi shaklga kiradi."]},
    "ru": {"kutish": "Ожидание — скажите Джарвис", "tinglash": "Слушаю…",
           "o'ylash": "Выполняю…", "gapirish": "Говорю…", "shazam": "Слушаю музыку…",
           "yozing": "Напишите команду…", "siz": "Вы",
           "sozlamalar": "Настройки", "ovoz": "Голос", "ayol": "Женский голос",
           "erkak": "Мужской голос", "til": "Язык", "korinish": "Внешний вид",
           "profil": "Профиль", "haqida": "О программе", "yopish": "Закрыть",
           "saqlash": "Сохранить", "sinab": "Прослушать", "tanlangan": "Выбрано",
           "ovoz_izoh": "Каким голосом говорить Джарвису?",
           "til_izoh": "На каком языке Джарвис слушает и говорит?",
           "korinish_izoh": "Выберите цвет сферы. Справа — живой просмотр.",
           "profil_izoh": "Джарвис будет обращаться к вам по этому имени.",
           "haqida_izoh": "Голосовой помощник.",
           "haqida_matn": ["Скажите «Джарвис» или напишите внизу.",
                           "Скажите «помощь», и я перечислю все команды.",
                           "Настройки можно закрыть голосом.",
                           "Когда я говорю, сфера каждый раз меняет форму."]},
    "en": {"kutish": "Standby — say Jarvis", "tinglash": "Listening…",
           "o'ylash": "Working…", "gapirish": "Speaking…", "shazam": "Listening to music…",
           "yozing": "Type a command…", "siz": "You", "sozlamalar": "Settings",
           "ovoz": "Voice", "ayol": "Female voice", "erkak": "Male voice", "til": "Language",
           "korinish": "Appearance", "profil": "Profile", "haqida": "About",
           "yopish": "Close", "saqlash": "Save", "sinab": "Preview", "tanlangan": "Selected",
           "ovoz_izoh": "Which voice should Jarvis use?",
           "til_izoh": "Which language should Jarvis listen and speak in?",
           "korinish_izoh": "Choose the sphere color. Live preview on the right.",
           "profil_izoh": "Jarvis will call you by this name.",
           "haqida_izoh": "Voice assistant.",
           "haqida_matn": ["Say \"Jarvis\" or type in the box below.",
                           "Say \"help\" and I will list all commands.",
                           "You can close settings by voice too.",
                           "When I speak, the sphere morphs into a new shape."]},
    "de": {"kutish": "Bereit — sag Jarvis", "tinglash": "Ich höre zu…",
           "o'ylash": "Ich arbeite…", "gapirish": "Ich spreche…", "shazam": "Ich höre Musik…",
           "yozing": "Befehl eingeben…", "siz": "Sie",
           "sozlamalar": "Einstellungen", "ovoz": "Stimme", "ayol": "Weibliche Stimme",
           "erkak": "Männliche Stimme", "til": "Sprache", "korinish": "Aussehen",
           "profil": "Profil", "haqida": "Über", "yopish": "Schließen", "saqlash": "Speichern",
           "sinab": "Anhören", "tanlangan": "Ausgewählt",
           "ovoz_izoh": "Welche Stimme soll Jarvis verwenden?",
           "til_izoh": "In welcher Sprache soll Jarvis hören und sprechen?",
           "korinish_izoh": "Wählen Sie die Farbe der Kugel. Rechts — Live-Vorschau.",
           "profil_izoh": "Jarvis wird Sie mit diesem Namen ansprechen.",
           "haqida_izoh": "Sprachassistent.",
           "haqida_matn": ["Sagen Sie „Jarvis“ oder tippen Sie unten.",
                           "Sagen Sie „Hilfe“, und ich nenne alle Befehle.",
                           "Die Einstellungen lassen sich auch per Stimme schließen.",
                           "Wenn ich spreche, verwandelt sich die Kugel jedes Mal."]},
}
BOLIMLAR = ("ovoz", "til", "korinish", "profil", "telefon", "haqida")

# Telefon bo'limi yozuvlari (boshqa tillarda tarjimasi bo'lmasa — o'zbekcha ko'rsatiladi)
YOZUVLAR["uz"].update({
    "telefon": "Telefon", "telefon_izoh": "Telegram bot orqali telefondan boshqarish.",
    "tg_yoq": "Token kiritilmagan", "tg_kod": "Ulanish kutilmoqda — kodni botga yuboring",
    "tg_ulangan": "Ulangan — telefondan buyruq bera olasiz", "tg_xato": "Token noto'g'ri yoki internet yo'q",
    "tg_token": "Bot tokeni", "tg_uzish": "Uzish",
    "tg_qadamlar": ["1. Telegram'da @BotFather ni oching va /newbot yozing.",
                    "2. Botga nom bering — BotFather sizga token beradi.",
                    "3. Tokenni nusxalab, yuqoridagi maydonga qo'ying (Ctrl+V) va Saqlash bosing.",
                    "4. O'z botingizni oching va ekranda chiqqan 6 xonali kodni yuboring.",
                    "Tayyor! Endi botga yozing: \"yuklamalardagi rasmlarni tashla\"."]})
YOZUVLAR["uz"].update({"ong_tugma": "Sozlamalarni ochish: Jarvis ustida sichqonchaning o'ng tugmasini bosing.",
                       "ochirish": "Jarvis'ni o'chirish"})
YOZUVLAR["ru"].update({"ong_tugma": "Настройки: правый клик по Джарвису.", "ochirish": "Выключить Джарвиса"})
YOZUVLAR["en"].update({"ong_tugma": "Settings: right-click on Jarvis.", "ochirish": "Turn off Jarvis"})
YOZUVLAR["de"].update({"ong_tugma": "Einstellungen: Rechtsklick auf Jarvis.", "ochirish": "Jarvis beenden"})
YOZUVLAR["ru"].update({"telefon": "Телефон", "telefon_izoh": "Управление с телефона через Telegram-бота.",
                       "tg_yoq": "Токен не указан", "tg_kod": "Ожидание — отправьте код боту",
                       "tg_ulangan": "Подключено", "tg_xato": "Неверный токен или нет интернета",
                       "tg_token": "Токен бота", "tg_uzish": "Отключить"})
YOZUVLAR["en"].update({"telefon": "Phone", "telefon_izoh": "Control from your phone via a Telegram bot.",
                       "tg_yoq": "No token entered", "tg_kod": "Waiting — send the code to your bot",
                       "tg_ulangan": "Connected", "tg_xato": "Wrong token or no internet",
                       "tg_token": "Bot token", "tg_uzish": "Disconnect"})
YOZUVLAR["de"].update({"telefon": "Telefon", "telefon_izoh": "Steuerung vom Handy über einen Telegram-Bot.",
                       "tg_yoq": "Kein Token", "tg_kod": "Warte — Code an den Bot senden",
                       "tg_ulangan": "Verbunden", "tg_xato": "Falscher Token oder kein Internet",
                       "tg_token": "Bot-Token", "tg_uzish": "Trennen"})


# ---------- WINDOWS: shaffof fon, doim ustida, joylashuv ----------
HWND_TOPMOST = -1


def _u32():
    """user32 funksiyalari TO'G'RI turlar bilan. Muhim: 64-bitli EXE'da turlarsiz chaqirilsa,
    HWND_TOPMOST (-1) 32-bitli son bo'lib ketadi va Windows buyruqni rad etadi —
    oyna na ustida turadi, na o'rtaga suriladi."""
    import ctypes
    import ctypes.wintypes as w
    u = ctypes.windll.user32
    if not getattr(u, "_jarvis_turlar", False):
        u.SetWindowPos.argtypes = [w.HWND, w.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_uint]
        u.SetWindowPos.restype = w.BOOL
        u.ShowWindow.argtypes = [w.HWND, ctypes.c_int]
        u.GetWindowLongW.argtypes = [w.HWND, ctypes.c_int]
        u.GetWindowLongW.restype = ctypes.c_long
        u.SetWindowLongW.argtypes = [w.HWND, ctypes.c_int, ctypes.c_long]
        u.SetWindowLongW.restype = ctypes.c_long
        u.SetLayeredWindowAttributes.argtypes = [w.HWND, w.COLORREF, ctypes.c_ubyte, w.DWORD]
        u.GetWindowRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
        u._jarvis_turlar = True
    return u


def ustida_ushla():
    """Oynani barcha ilovalar ustida ushlaydi (fokusni o'g'irlamasdan)."""
    if os.name == "nt" and _hwnd():
        _u32().SetWindowPos(_hwnd(), HWND_TOPMOST, 0, 0, 0, 0, 0x2 | 0x1 | 0x10)  # NOMOVE|NOSIZE|NOACTIVATE


def _hwnd():
    try:
        return pygame.display.get_wm_info()["window"]
    except (KeyError, pygame.error):
        return None


def windows_sozla(shaffoflik=255):
    """Qora rangni shaffof qiladi, oynani doim boshqa oynalar ustida ushlaydi.
    shaffoflik (0..255) — butun oynaning ko'rinishi (sozlamalar silliq ochilishi uchun)."""
    if os.name != "nt":
        return
    u32 = _u32()
    hwnd = _hwnd()
    if not hwnd:
        return
    GWL_EXSTYLE, WS_EX_LAYERED = -20, 0x80000
    uslub = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    u32.SetWindowLongW(hwnd, GWL_EXSTYLE, uslub | WS_EX_LAYERED)
    u32.SetLayeredWindowAttributes(hwnd, 0x000000, int(shaffoflik), 0x1 | 0x2)  # COLORKEY | ALPHA
    u32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, 0x2 | 0x1 | 0x10)   # NOMOVE|NOSIZE|NOACTIVATE


def shaffoflik_ber(qiymat):
    if os.name == "nt" and _hwnd():
        _u32().SetLayeredWindowAttributes(_hwnd(), 0, int(qiymat), 0x1 | 0x2)


def oyna_korinishi(korinsin):
    """Oynani vaqtincha yashiradi yoki qayta ko'rsatadi (fokusni o'g'irlamasdan)."""
    if os.name != "nt" or not _hwnd():
        return
    _u32().ShowWindow(_hwnd(), 4 if korinsin else 0)       # 4 = SW_SHOWNOACTIVATE, 0 = SW_HIDE
    if korinsin:
        ustida_ushla()


def ish_maydoni():
    """Ekranning vazifalar paneli (taskbar)siz qismi: (chap, tepa, o'ng, past)."""
    if os.name == "nt":
        import ctypes
        import ctypes.wintypes
        rect = ctypes.wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(rect), 0):
            return rect.left, rect.top, rect.right, rect.bottom
    info = pygame.display.Info()
    return 0, 0, info.current_w, info.current_h - 48


def ekran_olchami():
    """Butun ekran (vazifalar paneli bilan birga)."""
    if os.name == "nt":
        import ctypes
        u32 = ctypes.windll.user32
        return u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)
    info = pygame.display.Info()
    return info.current_w, info.current_h


def oyna_joyi():
    if os.name == "nt":
        import ctypes
        import ctypes.wintypes
        rect = ctypes.wintypes.RECT()
        _u32().GetWindowRect(_hwnd(), ctypes.byref(rect))
        return rect.left, rect.top
    return 0, 0


def oynani_sur(x, y):
    if os.name == "nt":
        _u32().SetWindowPos(_hwnd(), HWND_TOPMOST, int(x), int(y), 0, 0, 0x1 | 0x10)  # NOSIZE|NOACTIVATE


def sichqoncha_ekranda():
    if os.name == "nt":
        import ctypes
        import ctypes.wintypes
        nuqta = ctypes.wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(nuqta))
        return nuqta.x, nuqta.y
    return pygame.mouse.get_pos()


# ---------- SHAR VA SHAKLLAR ----------
def fibonacci_shar(n):
    """Shar sirtida bir tekis joylashgan n ta nuqta (Fibonacci sphere usuli)."""
    oltin_burchak = math.pi * (3 - math.sqrt(5))
    nuqtalar = []
    for i in range(n):
        y = 1 - 2 * (i + 0.5) / n                 # -1 dan 1 gacha
        r = math.sqrt(1 - y * y)
        burchak = oltin_burchak * i
        nuqtalar.append((math.cos(burchak) * r, y, math.sin(burchak) * r,
                         random.uniform(0, 2 * math.pi),    # nafas fazasi
                         random.uniform(0.94, 1.04)))        # zarracha bulut bo'lib ko'rinsin
    return nuqtalar


def _shakl_nuqtasi(nom, i, n, t):
    """Bitta shaklning bitta nuqtasi. t — 0..1 oralig'idagi tasodifiy son.
    Ekranda y pastga qarab o'sadi, shuning uchun "tepa" — manfiy y."""
    u, v = random.random(), random.random()
    if nom == "kub":
        a, b = u * 2 - 1, v * 2 - 1
        yuz = i % 6
        o = 1 if yuz % 2 else -1
        x, y, z = [(o, a, b), (a, o, b), (a, b, o)][yuz // 2]
        return x * 0.72, y * 0.72, z * 0.72
    if nom == "halqa":                                  # tor (donut)
        a, b = u * 2 * math.pi, v * 2 * math.pi
        return (0.8 + 0.3 * math.cos(b)) * math.cos(a), 0.3 * math.sin(b), \
               (0.8 + 0.3 * math.cos(b)) * math.sin(a)
    if nom == "galaktika":
        qol = i % 3
        r = t ** 0.7 * 1.15
        a = r * 4.2 + qol * 2 * math.pi / 3 + random.gauss(0, 0.18)
        return r * math.cos(a), random.gauss(0, 0.05) * (1.2 - r), r * math.sin(a)
    if nom == "dnk":
        y = t * 2.2 - 1.1
        a = y * 5
        if i % 5 == 0:                                  # zinapoyalar
            k = v * 2 - 1
            return 0.45 * math.cos(a) * k, y, 0.45 * math.sin(a) * k
        a += math.pi * (i % 2)
        return 0.45 * math.cos(a), y, 0.45 * math.sin(a)
    if nom == "yulduz":
        y = 1 - 2 * t
        r = math.sqrt(max(0.0, 1 - y * y))
        a = 2 * math.pi * u
        x, z = math.cos(a) * r, math.sin(a) * r
        tikan = max(abs(x), abs(y), abs(z)) ** 14
        k = 0.62 + 0.55 * tikan
        return x * k, y * k, z * k
    if nom == "yurak":
        while True:                                     # yurak ichidagi nuqta
            x, y, z = (random.uniform(-1.3, 1.3) for _ in range(3))
            if (x * x + 2.25 * z * z + y * y - 1) ** 3 - x * x * y ** 3 - 0.1125 * z * z * y ** 3 < 0:
                return x * 0.78, -y * 0.78 + 0.05, z * 0.78
    if nom == "atom":
        if i % 4 == 0:                                  # yadro
            y = 1 - 2 * t
            r = math.sqrt(max(0.0, 1 - y * y)) * 0.25
            a = 2 * math.pi * u
            return math.cos(a) * r, y * 0.25, math.sin(a) * r
        a = 2 * math.pi * u                             # 3 ta orbita, har biri boshqa tekislikda
        x, y, z = math.cos(a) * 1.05, 0.0, math.sin(a) * 1.05
        y, z = y * math.cos(1.2) - z * math.sin(1.2), y * math.sin(1.2) + z * math.cos(1.2)
        e = (i % 3) * 2 * math.pi / 3
        return x * math.cos(e) + z * math.sin(e), y, z * math.cos(e) - x * math.sin(e)
    if nom == "piramida":
        yuz = i % 5
        if yuz == 4:                                    # asos
            return (u * 2 - 1) * 0.85, 0.6, (v * 2 - 1) * 0.85
        a, b = u, v * (1 - u)
        burchaklar = [(-0.85, -0.85), (0.85, -0.85), (0.85, 0.85), (-0.85, 0.85)]
        p1, p2 = burchaklar[yuz], burchaklar[(yuz + 1) % 4]
        x = p1[0] * (1 - a - b) + p2[0] * b
        z = p1[1] * (1 - a - b) + p2[1] * b
        return x, 0.6 - a * 1.5, z
    if nom == "tolqin":
        x, z = u * 2 - 1, v * 2 - 1
        return x, 0.25 * math.sin(x * 4) * math.cos(z * 3), z
    return 0.0, 0.0, 0.0


SHAKLLAR = ("kub", "halqa", "galaktika", "dnk", "yulduz", "yurak", "atom", "piramida", "tolqin")


def shakllar_yasa(n):
    """Har bir shakl uchun n ta nuqta. Balandligi (y) bo'yicha tartiblanadi — shunda
    shardagi yuqori nuqtalar shaklning ham yuqorisiga uchadi va o'tish chiroyli bo'ladi."""
    natija = {}
    for nom in SHAKLLAR:
        nuqtalar = [_shakl_nuqtasi(nom, i, n, random.random()) for i in range(n)]
        nuqtalar.sort(key=lambda p: -p[1])
        natija[nom] = nuqtalar
    return natija


def nuqta_rasmlari(koef=1.0, tiniq=False):
    """Oldindan chizilgan nuqtalar (kul rangda; keyin bo'yaladi).
    [kattalik][yorqinlik] — har kadrda aylana chizishdan ancha tez.
    tiniq=True — asosiy oyna uchun: nuqtalar doim yorqin, chetlari aniq. Shaffof oynada
    to'q piksellar ish stolida qora dog' bo'lib ko'rinadi, shuning uchun ular ishlatilmaydi."""
    if tiniq:
        rasmlar = []
        for rad in (1.3 * koef, 1.8 * koef, 2.4 * koef):
            qator = []
            o_lcham = int(rad * 2) + 3
            m = (o_lcham - 1) / 2
            for daraja in range(8):
                yorug = 150 + daraja * 15                     # 150..255 — hech qachon to'q emas
                s = pygame.Surface((o_lcham, o_lcham))
                s.fill((0, 0, 0))
                for px in range(o_lcham):
                    for py in range(o_lcham):
                        if math.hypot(px - m, py - m) <= rad:
                            s.set_at((px, py), (yorug,) * 3)
                qator.append(s)
            rasmlar.append(qator)
        return rasmlar
    rasmlar = []
    for rad in (1.6 * koef, 2.3 * koef, 3.2 * koef):
        qator = []
        o_lcham = int(rad * 2) + 3
        m = (o_lcham - 1) / 2
        for daraja in range(8):
            yorug = 70 + daraja * 26                          # 70..252
            s = pygame.Surface((o_lcham, o_lcham))
            s.fill((0, 0, 0))
            for px in range(o_lcham):
                for py in range(o_lcham):
                    d = math.hypot(px - m, py - m) / rad
                    if d < 1:
                        q = int(yorug * (1 - d) ** 1.6)
                        s.set_at((px, py), (q, q, q))
            qator.append(s)
        rasmlar.append(qator)
    return rasmlar


def yadro_nuri(radius, kuch=70, daraja=2):
    """Yumshoq yorug'lik (radial gradient)."""
    s = pygame.Surface((radius * 2, radius * 2))
    s.fill((0, 0, 0))
    for r in range(radius, 0, -2):
        q = int(kuch * (1 - r / radius) ** daraja)
        pygame.draw.circle(s, (q, q, q), (radius, radius), r)
    return s


def aralashtir(a, b, t):
    return a + (b - a) * t


def rang_aralashtir(a, b, t):
    return tuple(aralashtir(x, y, t) for x, y in zip(a, b))


def yumshoq(t):
    """0..1 ni silliq egri chiziqqa aylantiradi (animatsiya tabiiyroq ko'rinadi)."""
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def holat_rangi(holat, rang_kaliti):
    mavzu = S.RANGLAR[rang_kaliti]
    xira, yorqin = mavzu["xira"], mavzu["yorqin"]
    if holat == "kutish":
        return xira
    if holat == "o'ylash":
        return rang_aralashtir(xira, yorqin, 0.5)
    if holat == "shazam":
        return (255, 190, 70) if rang_kaliti == "binafsha" else (175, 80, 255)
    return yorqin


def matnni_bol(shrift, matn, eni, max_qator):
    """Uzun matnni oynaga sig'adigan qatorlarga bo'ladi."""
    qatorlar, joriy = [], ""
    for soz in matn.split():
        sinov = (joriy + " " + soz).strip()
        if shrift.size(sinov)[0] <= eni:
            joriy = sinov
        else:
            if joriy:
                qatorlar.append(joriy)
            joriy = soz
    if joriy:
        qatorlar.append(joriy)
    if len(qatorlar) > max_qator:
        qatorlar = qatorlar[:max_qator]
        qatorlar[-1] = qatorlar[-1].rstrip(".,") + "…"
    return qatorlar


# ---------- ANIMATSIYALI TUGMA ----------
class Tugma:
    """Har bir tugmaning animatsiya holati: sichqoncha ustida (hover),
    bosilgandagi siqilish va tarqaluvchi to'lqin (ripple)."""

    def __init__(self):
        self.joy = pygame.Rect(0, 0, 0, 0)
        self.ustida = 0.0          # 0..1 — sichqoncha ustiga kelganda silliq ortadi
        self.bosish = 0.0          # 1 — hozirgina bosildi, keyin 0 ga tushadi
        self.tolqinlar = []        # [(x, y, boshlangan_vaqt)]

    def yangila(self, dt, sichqoncha):
        maqsad = 1.0 if self.joy.collidepoint(sichqoncha) else 0.0
        self.ustida = aralashtir(self.ustida, maqsad, min(1.0, dt * 12))
        self.bosish = max(0.0, self.bosish - dt * 5)
        hozir = time.time()
        self.tolqinlar = [t for t in self.tolqinlar if hozir - t[2] < 0.6]

    def bosildi(self, joy):
        self.bosish = 1.0
        self.tolqinlar.append((joy[0] - self.joy.x, joy[1] - self.joy.y, time.time()))

    def korinish(self):
        """Chizish uchun joy: ustida bo'lsa biroz kattalashadi, bosilsa siqiladi."""
        o_sish = int(self.ustida * 4 - self.bosish * 6)
        return self.joy.inflate(o_sish, o_sish)


class Oyna:
    def __init__(self, ui_navbat, kirish_navbat, sozlama=None):
        self.ui_navbat = ui_navbat
        self.kirish_navbat = kirish_navbat
        self.sozlama = dict(sozlama or S.STANDART)

        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.user32.SetProcessDPIAware()     # xira bo'lmasin
            except Exception:
                pass
        pygame.display.init()
        pygame.font.init()

        # Uch o'lcham: kichik (burchakda), katta (o'rtada), sozlamalar (butun ekran)
        self.maydon = ish_maydoni()
        chap, tepa, ong, past = self.maydon
        koef = max(0.6, min(1.0, (past - tepa - 40) / 760))
        self.olchamlar = {"kichik": (340, 500), "katta": (int(600 * koef), int(760 * koef)),
                          "sozlama": ekran_olchami(),
                          "mini": (MINI_ENI, MINI_BOYI),              # tepada o'rtada kichik shar
                          "mini_yoz": (MINI_YOZ_ENI, MINI_YOZ_BOYI)}  # + ostida yozish joyi
        self.katta_koef = koef
        self.kichik_joy = (ong - 340 - 16, past - 500 - 16)
        # Kutishda — ekran tepasining o'rtasida kichik zarrachali shar
        self.mini_yozish = False          # mini shar bosildi — ostida yozish joyi ochiq
        self.kerakli_joy = self.rejim_joyi("mini")
        self.joy_tekshir_gacha = 0.0
        os.environ["SDL_VIDEO_WINDOW_POS"] = f"{self.kerakli_joy[0]},{self.kerakli_joy[1]}"
        self.rejim = "mini"
        self.ekran = pygame.display.set_mode(self.olchamlar["mini"], pygame.NOFRAME)
        pygame.display.set_caption("Jarvis")
        pygame.display.set_icon(self._ikonka())
        windows_sozla()
        pygame.key.start_text_input()

        self.nuqtalar = fibonacci_shar(NUQTALAR_SONI)
        self.shar_nuqtalari = [(x, y, z) for x, y, z, _, _ in self.nuqtalar]
        self.mini_nuqtalar = fibonacci_shar(420)     # tepadagi kichik shar — siyrak, mayda zarrachalar
        self.shakllar = shakllar_yasa(NUQTALAR_SONI)
        self.shakl_nomi = SHAKLLAR[0]
        self.shakl_m = 0.0                # 0 = shar, 1 = to'liq shakl
        self.rasmlar_to_plami = {"kichik": nuqta_rasmlari(1.0, tiniq=True),
                                 "mini": nuqta_rasmlari(0.62, tiniq=True),
                                 "katta": nuqta_rasmlari(1.35, tiniq=True),
                                 "soz": nuqta_rasmlari(1.0), "soz_katta": nuqta_rasmlari(1.35)}

        f = "segoeui,arial"
        self.shrift = pygame.font.SysFont(f, 18, bold=True)
        self.shrift_kichik = pygame.font.SysFont(f, 14, bold=True)
        self.shrift_yozuv = pygame.font.SysFont(f, 18)
        self._matn_xotira = {}
        self.yozuv_nur = 0.0
        self.yuborish_joyi = pygame.Rect(0, 0, 0, 0)
        sk = max(0.85, min(1.5, self.olchamlar["sozlama"][1] / 1080))
        self.sk = sk
        self.sh = {"izoh": pygame.font.SysFont(f, int(16 * sk)),
                   "matn": pygame.font.SysFont(f, int(17 * sk)),
                   "tugma": pygame.font.SysFont(f, int(16 * sk), bold=True),
                   "karta": pygame.font.SysFont(f, int(20 * sk), bold=True),
                   "sarlavha": pygame.font.SysFont(f, int(34 * sk), bold=True),
                   "logo": pygame.font.SysFont(f, int(22 * sk), bold=True),
                   "katta": pygame.font.SysFont(f, int(40 * sk), bold=True)}

        self.holat = "kutish"
        self.kutish_boshlandi = time.time()
        h = HOLATLAR["kutish"]
        self.rang = holat_rangi("kutish", self.sozlama["rang"])
        self.kattalik, self.tezlik, self.yorqinlik = h["kattalik"], h["tezlik"], h["yorqinlik"]
        self.burchak = 0.0
        self.kirish = 1.0                 # katta bo'lib chiqish animatsiyasi (0 -> 1)
        self.ovoz = ([], 0.0)             # (balandliklar ro'yxati, boshlanish vaqti)
        self.daraja = 0.0                 # hozirgi ovoz balandligi 0..1

        self.siz_matni = ""
        self.jarvis_matni = ""
        self.matnlar = {"yozuv": "", "ism": self.sozlama["ism"],
                        "token": self.sozlama.get("telegram_token", "")}
        self.tg_holat, self.tg_qiymat = ("yoq", "")
        self.faol = None                  # qaysi maydonga yozilyapti: "yozuv" yoki "ism"
        self.surish = None                # sichqoncha bilan surish boshlangan joy
        self.surildi = False
        self.bosgan_joy = (0, 0)
        self.ishlayapti = True

        # sozlamalar ilovasi
        self.sozlama_ochiq = False
        self.soz_t = 0.0                  # ochilish animatsiyasi 0..1
        self.bolim = "ovoz"
        self.bolim_t = 1.0                # bo'lim almashganda kontent silliq kirib keladi
        self.belgi_y = None               # yon menyudagi tanlov belgisining y joyi (sirpanadi)
        self.tugmalar = {}                # id -> Tugma (animatsiya holati saqlanadi)
        self.chizilgan = []               # shu kadrda chizilgan tugmalar id'lari
        self.sichqoncha = (0, 0)
        self.yashirin_gacha = 0           # shu vaqtgacha oyna yashirin
        self.yashirin = False
        self.joylash()

    def _ikonka(self):
        asos = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        try:
            return pygame.transform.smoothscale(pygame.image.load(os.path.join(asos, "jarvis.png")), (64, 64))
        except (pygame.error, FileNotFoundError):
            pass
        s = pygame.Surface((32, 32))
        s.fill((0, 0, 0))
        pygame.draw.circle(s, (30, 90, 200), (16, 16), 14)
        pygame.draw.circle(s, (90, 200, 255), (16, 16), 9)
        pygame.draw.circle(s, (220, 245, 255), (13, 12), 3)
        return s

    def y(self, kalit):
        """Oyna yozuvi tanlangan tilda (tarjimasi bo'lmasa — o'zbekcha)."""
        return YOZUVLAR.get(self.sozlama["til"], YOZUVLAR["uz"]).get(kalit, YOZUVLAR["uz"][kalit])

    @property
    def yorqin(self):
        return S.RANGLAR[self.sozlama["rang"]]["yorqin"]

    # ----- o'lchamga qarab joylashuv -----
    def joylash(self):
        eni, boyi = self.olchamlar[self.rejim]
        self.eni, self.boyi = eni, boyi
        if self.rejim == "sozlama":
            self.soz_fon = self._sozlama_foni(eni, boyi)
            self.kontent = pygame.Surface((eni, boyi), pygame.SRCALPHA)
            self.rasmlar = self.rasmlar_to_plami["soz"]
            self.R0 = int(34 * self.sk)
            self.yadro = yadro_nuri(self.R0)
            self.shar_qatlami = pygame.Surface((int(self.R0 * 3.2), int(self.R0 * 3.2)))
            self.oldindan_R = int(min(boyi * 0.22, eni * 0.14))
            self.oldindan_qatlam = pygame.Surface((self.oldindan_R * 3, self.oldindan_R * 3))
            self.oldindan_yadro = yadro_nuri(self.oldindan_R)
            return
        if self.rejim in ("mini", "mini_yoz"):
            self.R0 = MINI_R
            self.markaz = (eni // 2, MINI_BOYI // 2)
            self.rasmlar = self.rasmlar_to_plami["mini"]
            self.yadro = yadro_nuri(self.R0)
            self.shar_qatlami = pygame.Surface((eni, MINI_BOYI))
            self.holat_y = MINI_BOYI
            self.panel = pygame.Rect(0, 0, 0, 0)
            self.yozuv_joyi = pygame.Rect(14, MINI_BOYI + 6, eni - 28, 46)
            self.yopish_joyi = self.sozlama_joyi = pygame.Rect(-50, -50, 1, 1)
            return
        katta = self.rejim == "katta"
        k = self.katta_koef if katta else 1.0
        self.R0 = int((175 if katta else 95) * k)
        self.markaz = (eni // 2, int((300 if katta else 170) * k))
        chegara = int(self.R0 * 1.5)
        self.rasmlar = self.rasmlar_to_plami[self.rejim]
        self.yadro = yadro_nuri(self.R0)
        self.shar_qatlami = pygame.Surface((eni, self.markaz[1] + chegara + 4))
        pastki = self.markaz[1] + chegara
        self.holat_y = pastki + 12
        self.panel = pygame.Rect(10, pastki + 24, eni - 20, boyi - pastki - 24 - 72)
        self.yozuv_joyi = pygame.Rect(16, boyi - 62, eni - 32, 46)
        self.yopish_joyi = pygame.Rect(eni - 30, 6, 24, 24)
        self.sozlama_joyi = pygame.Rect(6, 6, 24, 24)

    def _sozlama_foni(self, eni, boyi):
        """Sozlamalar foni: to'q ko'k gradient + burchakda yumshoq nur.
        Sof qora (0,0,0) ishlatilmaydi — u Windows'da shaffof bo'lib qoladi."""
        fon = pygame.Surface((eni, boyi))
        for y in range(0, boyi, 2):
            t = y / boyi
            pygame.draw.rect(fon, (int(9 - 4 * t), int(14 - 6 * t), int(26 - 10 * t)), (0, y, eni, 2))
        nur = yadro_nuri(int(boyi * 0.6), kuch=40, daraja=2.2)
        nur.fill(self.yorqin, special_flags=pygame.BLEND_MULT)
        fon.blit(nur, (eni - int(boyi * 0.9), -int(boyi * 0.35)), special_flags=pygame.BLEND_ADD)
        return fon

    def rejim_joyi(self, rejim):
        """Har bir rejimda oyna qayerda turadi (ekrandagi chap-yuqori burchagi)."""
        eni, boyi = self.olchamlar[rejim]
        chap, tepa, ong, past = self.maydon
        if rejim == "sozlama":
            return (0, 0)
        if rejim == "katta":
            return ((chap + ong - eni) // 2, (tepa + past - boyi) // 2)      # ekran o'rtasi
        if rejim in ("mini", "mini_yoz"):
            return ((chap + ong - eni) // 2, tepa + 6)                      # tepada, o'rtada
        return self.kichik_joy

    def rejimga_ot(self, rejim):
        if rejim == self.rejim:
            return
        if self.rejim == "kichik":
            self.kichik_joy = oyna_joyi() if os.name == "nt" else self.kichik_joy
        if rejim == "katta":
            self.mini_yozish = False             # katta Jarvis chiqdi — mini yozish joyi yopiladi
        self.rejim = rejim
        eni, boyi = self.olchamlar[rejim]
        joy = self.rejim_joyi(rejim)
        # pygame o'lcham o'zgarganda oynani SDL_VIDEO_WINDOW_POS joyiga qaytaradi —
        # shuning uchun avval yangi joyni aytamiz (aks holda burchakda qolib ketadi)
        os.environ["SDL_VIDEO_WINDOW_POS"] = f"{joy[0]},{joy[1]}"
        self.ekran = pygame.display.set_mode((eni, boyi), pygame.NOFRAME)
        windows_sozla(0 if rejim == "sozlama" else 255)
        oynani_sur(*joy)
        self.kerakli_joy = joy
        self.joy_tekshir_gacha = time.time() + 1.5          # bir necha kadr davomida tekshirib turamiz
        self.joylash()
        self.kirish = 0.0

    # ----- navbatdan kelgan xabarlar -----
    def xabarlarni_ol(self):
        while True:
            try:
                xabar = self.ui_navbat.get_nowait()
            except queue.Empty:
                return
            tur = xabar[0]
            if tur == "holat" and xabar[1] in HOLATLAR:
                if xabar[1] == "kutish" and self.holat != "kutish":
                    self.kutish_boshlandi = time.time()
                if xabar[1] == "gapirish" and self.holat != "gapirish" and self.shakl_m < 0.05:
                    # har safar yangi shakl (oldingisidan boshqa)
                    self.shakl_nomi = random.choice([s for s in SHAKLLAR if s != self.shakl_nomi])
                self.holat = xabar[1]
            elif tur == "siz":
                self.siz_matni = xabar[1]
            elif tur == "jarvis":
                self.jarvis_matni = xabar[1]
            elif tur == "ovoz":
                self.ovoz = (xabar[1], xabar[2])
            elif tur == "sozlamalar":
                eski_rang = self.sozlama.get("rang")
                self.sozlama = dict(xabar[1])
                if self.faol != "ism":
                    self.matnlar["ism"] = self.sozlama["ism"]
                if self.faol != "token":
                    self.matnlar["token"] = self.sozlama.get("telegram_token", "")
                if self.rejim == "sozlama" and eski_rang != self.sozlama["rang"]:
                    self.soz_fon = self._sozlama_foni(self.eni, self.boyi)
            elif tur == "telegram_holat":
                self.tg_holat, self.tg_qiymat = xabar[1], xabar[2]
            elif tur == "sozlamalarni_och":
                self.sozlamani_och()
            elif tur == "sozlamalarni_yop":
                self.sozlama_ochiq = False
                self.faol = None
            elif tur == "yashir":                    # tugma bosilayotganda xalaqit bermasin
                oyna_korinishi(False)
                self.yashirin_gacha = time.time() + xabar[1]
            elif tur == "korsat":
                self.yashirin_gacha = 0
            elif tur == "yopil":
                self.ishlayapti = False

    def sozlamani_och(self):
        self.sozlama_ochiq = True
        self.faol = None
        self.bolim_t = 0.0

    def sozlama_yubor(self, kalit, qiymat):
        self.sozlama[kalit] = qiymat
        if kalit == "rang" and self.rejim == "sozlama":
            self.soz_fon = self._sozlama_foni(self.eni, self.boyi)
        self.kirish_navbat.put(("sozlama", (kalit, qiymat), time.time()))

    # ----- sichqoncha va klaviatura -----
    def hodisalar(self):
        for h in pygame.event.get():
            if h.type == pygame.QUIT:
                self.ishlayapti = False
            elif h.type == pygame.MOUSEBUTTONDOWN and h.button == 3 and self.rejim != "sozlama":
                self.kirish_navbat.put(("chat_och", "soz", time.time()))   # o'ng tugma — sozlamalar
            elif h.type == pygame.MOUSEBUTTONDOWN and h.button == 1:
                if self.rejim == "sozlama":
                    self.sozlamada_bosildi(h.pos)
                else:
                    self.bosildi(h.pos)
            elif h.type == pygame.MOUSEBUTTONUP and h.button == 1:
                # sharni sichqoncha bilan surmasdan bosgan bo'lsa (tap) — uyg'otamiz
                if (self.surish and not self.surildi and self.rejim != "sozlama"
                        and math.hypot(h.pos[0] - self.markaz[0], h.pos[1] - self.markaz[1])
                        < self.R0 * 1.5):
                    if self.rejim in ("mini", "mini_yoz"):
                        # tepadagi sharni bosdi — ostida yozish joyi ochiladi/yopiladi
                        self.mini_yozish = not self.mini_yozish
                        self.faol = "yozuv" if self.mini_yozish else None
                    else:
                        self.kirish_navbat.put(("uygon", "", time.time()))
                self.surish = None
                self.surildi = False
            elif h.type == pygame.MOUSEMOTION and self.surish:
                mx, my = sichqoncha_ekranda()
                if abs(mx - self.bosgan_joy[0]) + abs(my - self.bosgan_joy[1]) > 5:
                    self.surildi = True      # sezilarli siljidi — bu surish, tap emas
                oynani_sur(mx - self.surish[0], my - self.surish[1])
            elif h.type == pygame.TEXTINPUT and self.faol:
                if len(self.matnlar[self.faol]) < 200:
                    self.matnlar[self.faol] += h.text
            elif h.type == pygame.KEYDOWN:
                if h.key == pygame.K_ESCAPE and self.rejim == "sozlama" and self.faol not in ("ism", "token"):
                    self.sozlama_ochiq = False
                elif h.key == pygame.K_ESCAPE and self.rejim == "mini_yoz":
                    self.mini_yozish, self.faol = False, None    # yozish joyini yopamiz
                elif self.faol:
                    self.tugma_bosildi(h)

    def bosildi(self, joy):
        if self.yuborish_joyi.collidepoint(joy):
            matn = self.matnlar["yozuv"].strip()
            if matn:
                self.kirish_navbat.put(("yozuv", matn, time.time()))
                self.matnlar["yozuv"] = ""
            return
        if self.yozuv_joyi.collidepoint(joy):
            self.faol = "yozuv"
            return
        self.faol = None
        mx, my = sichqoncha_ekranda()
        ox, oy = oyna_joyi()
        self.surish = (mx - ox, my - oy)
        self.bosgan_joy = (mx, my)          # tap yoki surish ekanini bilish uchun
        self.surildi = False

    def sozlamada_bosildi(self, joy):
        if self.soz_t < 0.6:
            return
        for tid in reversed(self.chizilgan):
            tugma = self.tugmalar[tid]
            if tugma.joy.collidepoint(joy):
                tugma.bosildi(joy)
                self.amal(tid)
                return
        if self.faol in ("ism", "token"):
            self.faol = None

    def amal(self, tid):
        """Sozlamalardagi tugma bosilganda nima bo'ladi."""
        tur, _, qiymat = tid.partition(":")
        if tur == "yopish":
            self.sozlama_ochiq = False
            self.faol = None
        elif tur == "jarvis_ochir":
            self.ishlayapti = False
        elif tur == "bolim" and qiymat != self.bolim:
            self.bolim, self.bolim_t, self.faol = qiymat, 0.0, None
        elif tur in ("ovoz", "til", "rang"):
            self.sozlama_yubor(tur, qiymat)
        elif tur == "sinov":
            self.kirish_navbat.put(("ovoz_sinov", qiymat, time.time()))
        elif tur == "ism_maydon":
            self.faol = "ism"
        elif tur == "token_maydon":
            self.faol = "token"
        elif tur == "token_saqlash":
            self.sozlama_yubor("telegram_token", self.matnlar["token"].strip())
            self.faol = None
        elif tur == "tg_uzish":
            self.sozlama_yubor("telegram_egasi", 0)
        elif tur == "saqlash":
            ism = self.matnlar["ism"].strip()
            if ism:
                self.sozlama_yubor("ism", ism)
            self.faol = None

    def tugma_bosildi(self, h):
        maydon = self.faol
        if h.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            matn = self.matnlar[maydon].strip()
            if maydon == "yozuv":
                if matn:
                    self.kirish_navbat.put(("yozuv", matn, time.time()))
                self.matnlar["yozuv"] = ""
            elif maydon == "token":
                self.sozlama_yubor("telegram_token", matn)
                self.faol = None
            elif matn:
                self.sozlama_yubor("ism", matn)
                self.faol = None
        elif h.key == pygame.K_BACKSPACE:
            self.matnlar[maydon] = self.matnlar[maydon][:-1]
        elif h.key == pygame.K_ESCAPE:
            if maydon == "yozuv":
                self.matnlar["yozuv"] = ""
            elif maydon == "token":
                self.matnlar["token"] = self.sozlama.get("telegram_token", "")
            else:
                self.matnlar["ism"] = self.sozlama["ism"]
            self.faol = None
        elif h.key == pygame.K_v and h.mod & pygame.KMOD_CTRL:
            try:
                import pyperclip
                self.matnlar[maydon] += pyperclip.paste().replace("\n", " ").strip()[:200]
            except Exception:
                pass

    # ----- holat va animatsiya -----
    def holatni_yangila(self, dt):
        # Avval o'lcham va joy (o'rtada katta / sozlamalar — butun ekran), keyin ko'rsatamiz —
        # shunda oyna eski o'lchamda miltillab ko'rinmaydi.
        if self.sozlama_ochiq or self.soz_t > 0.01:
            self.rejimga_ot("sozlama")
        elif self.holat != "kutish":
            self.rejimga_ot("katta")                 # "Jarvis" — o'rtada katta
        elif self.rejim in ("mini", "mini_yoz") or time.time() - self.kutish_boshlandi > 1.2:
            self.rejimga_ot("mini_yoz" if self.mini_yozish else "mini")   # tepada kichik shar

        # Oyna doim ko'rinadi (kutishda — tepada kichik shar). Faqat tugma bosish kabi
        # ishlarda vaqtincha yashiriladi (yashirin_gacha).
        yashirin = time.time() < self.yashirin_gacha
        if yashirin != self.yashirin:
            self.yashirin = yashirin
            oyna_korinishi(not yashirin)
            if not yashirin:
                self.joy_tekshir_gacha = time.time() + 1.0   # qayta chiqdi — joyi to'g'rimi?
        # Boshqa ilova ochilsa ham shar ustida tursin — vaqti-vaqti bilan qayta tiklaymiz
        if not self.yashirin and time.time() - getattr(self, "_ustida_vaqt", 0) > 1.5:
            ustida_ushla()
            self._ustida_vaqt = time.time()
        # Oyna kerakli joyda (o'rtada) ekanini tekshiramiz — Windows/SDL siljitib qo'ysa, qaytaramiz
        if os.name == "nt" and not self.yashirin and time.time() < self.joy_tekshir_gacha \
                and not self.surish and oyna_joyi() != tuple(self.kerakli_joy):
            oynani_sur(*self.kerakli_joy)

        if self.rejim == "sozlama":
            oldingi = self.soz_t
            maqsad = 1.0 if self.sozlama_ochiq else 0.0
            self.soz_t = max(0.0, min(1.0, self.soz_t + (dt * 4 if maqsad else -dt * 5)))
            if self.soz_t != oldingi:
                shaffoflik_ber(255 * yumshoq(self.soz_t))
            self.bolim_t = min(1.0, self.bolim_t + dt * 3.5)

        maqsad = HOLATLAR[self.holat]
        t = min(1.0, dt * 4)                  # yangi holatga silliq o'tish
        self.rang = rang_aralashtir(self.rang, holat_rangi(self.holat, self.sozlama["rang"]), t)
        self.kattalik = aralashtir(self.kattalik, maqsad["kattalik"], t)
        self.tezlik = aralashtir(self.tezlik, maqsad["tezlik"], t)
        self.yorqinlik = aralashtir(self.yorqinlik, maqsad["yorqinlik"], t)
        self.burchak += self.tezlik * dt
        self.kirish = min(1.0, self.kirish + dt * 2.5)
        # gapirganda shaklga kiradi, gap tugagach sharga qaytadi
        shakl_maqsad = 1.0 if self.holat == "gapirish" else 0.0
        qadam = dt * (1.8 if shakl_maqsad else 1.4)
        self.shakl_m = min(shakl_maqsad, self.shakl_m + qadam) if shakl_maqsad > self.shakl_m \
            else max(shakl_maqsad, self.shakl_m - qadam)

        balandliklar, boshlandi = self.ovoz
        yangi = 0.0
        if balandliklar:
            i = int((time.time() - boshlandi) * 30)
            if 0 <= i < len(balandliklar):
                yangi = balandliklar[i]
        # tez ko'tariladi, sekin tushadi — pulsatsiya tabiiyroq ko'rinadi
        self.daraja = yangi if yangi > self.daraja else aralashtir(self.daraja, yangi, min(1, dt * 8))

    # ----- shar -----
    def zarrachalar(self, q, cx, cy, R, rasmlar, yadro, vaqt, nuqtalar=None):
        """Zarrachalarni q ga chizadi (kul rangda). Shar yoki shakl — shakl_m ga qarab.
        nuqtalar — kichik shar uchun alohida (siyrakroq) nuqtalar: aks holda bir tekis dog' bo'ladi."""
        ca, sa = math.cos(self.burchak), math.sin(self.burchak)
        egilish = 0.35
        ce, se = math.cos(egilish), math.sin(egilish)
        daraja = self.daraja
        nafas_t = vaqt * 1.6
        tolqin_t = vaqt * 9
        m = yumshoq(self.shakl_m)
        if nuqtalar is None:
            nuqtalar = self.nuqtalar
            maqsad = self.shakllar[self.shakl_nomi] if m > 0.001 else self.shar_nuqtalari
        else:
            m = 0.0                                  # kichik shar shaklga kirmaydi
            maqsad = [(x, y, z) for x, y, z, _, _ in nuqtalar]
        yorqinlik = self.yorqinlik
        ro_yxat = []
        sin = math.sin
        for (x, y, z, faza, uzoq), (tx, ty, tz) in zip(nuqtalar, maqsad):
            if m > 0.001:
                x += (tx - x) * m
                y += (ty - y) * m
                z += (tz - z) * m
            # nafas olish + ovozga qarab tashqariga to'lqin
            k = uzoq + 0.03 * sin(nafas_t + faza)
            if daraja > 0.01:
                k += daraja * (0.10 + 0.12 * sin(y * 7 - tolqin_t))
            x2 = x * ca + z * sa                 # Y o'qi atrofida aylanish
            z2 = z * ca - x * sa
            y2 = y * ce - z2 * se                # biroz egilgan holda ko'rinadi
            z3 = y * se + z2 * ce
            chuqurlik = (z3 + 1.2) * 0.42        # 0 = orqada, 1 = oldida
            if chuqurlik < 0:
                chuqurlik = 0
            elif chuqurlik > 1:
                chuqurlik = 1
            kat = 0 if chuqurlik < 0.45 else (1 if chuqurlik < 0.85 else 2)
            rasm = rasmlar[kat][int(chuqurlik * 7.99 * yorqinlik)]
            yarim = rasm.get_width() >> 1
            ro_yxat.append((rasm, (cx + x2 * R * k - yarim, cy + y2 * R * k - yarim)))

        # ichki yumshoq nur — shaklga o'tganda so'nadi
        yr = int(R * 1.1)
        if yadro is not None and m < 0.95:
            yadro_ = pygame.transform.smoothscale(yadro, (yr * 2, yr * 2))
            if m > 0.01:
                q_ = int(255 * (1 - m))
                yadro_.fill((q_, q_, q_), special_flags=pygame.BLEND_MULT)
            q.blit(yadro_, (cx - yr, cy - yr), special_flags=pygame.BLEND_ADD)
        q.blits([(r, j, None, pygame.BLEND_ADD) for r, j in ro_yxat], doreturn=False)

    def shar_chiz(self, vaqt):
        q = self.shar_qatlami
        q.fill((0, 0, 0))
        cx, cy = self.markaz
        # katta bo'lib chiqish: 0.6 dan 1.0 gacha silliq kattalashadi
        ochilish = 1 - (1 - self.kirish) ** 3
        R = self.R0 * self.kattalik * (0.6 + 0.4 * ochilish)
        mini = self.rejim in ("mini", "mini_yoz")
        self.zarrachalar(q, cx, cy, R, self.rasmlar, None, vaqt,     # ichki nursiz — to'q dog' bo'lmasin
                         self.mini_nuqtalar if mini else None)
        # kul rangdagi rasmni holat rangiga bo'yaymiz (kichik shar — biroz yorqinroq, ko'zga tashlansin)
        rang = rang_aralashtir(self.rang, self.yorqin, 0.5) if mini else self.rang
        q.fill(tuple(int(c) for c in rang), special_flags=pygame.BLEND_MULT)
        # Deyarli qora piksellarni butunlay qora (= shaffof) qilamiz: aks holda ish stolida
        # shar atrofida to'q dog' ko'rinadi. Nuqtalar tiniqroq bo'ladi.
        q.fill((22, 22, 22), special_flags=pygame.BLEND_SUB)
        self.ekran.blit(q, (0, 0), special_flags=pygame.BLEND_ADD)

    # ----- asosiy oyna yozuvlari -----
    def maydon_chiz(self, sirt, joy, maydon, bosh_matn, shrift, yashirin=False):
        faol = self.faol == maydon
        pygame.draw.rect(sirt, PANEL, joy, border_radius=10)
        pygame.draw.rect(sirt, self.yorqin if faol else (35, 60, 100), joy,
                         2 if faol else 1, border_radius=10)
        matn = self.matnlar[maydon]
        if yashirin and not faol and len(matn) > 10:
            matn = matn[:10] + "•" * 12                  # maxfiy token to'liq ko'rinmasin
        if matn or faol:
            while shrift.size(matn)[0] > joy.w - 28 and matn:
                matn = matn[1:]
            kursor = "|" if faol and int(time.time() * 2) % 2 == 0 else ""
            yuza = shrift.render(matn + kursor, True, (225, 235, 245))
        else:
            yuza = shrift.render(bosh_matn, True, (90, 110, 140))
        sirt.blit(yuza, (joy.x + 14, joy.y + (joy.h - yuza.get_height()) // 2))

    def kichik_tugma(self, joy, belgi, sichqoncha):
        ustida = joy.collidepoint(sichqoncha)
        rang = self.yorqin if ustida else (150, 170, 200)
        pygame.draw.circle(self.ekran, PANEL, joy.center, 12 if ustida else 11)
        c = joy.center
        if belgi == "x":
            pygame.draw.line(self.ekran, rang, (c[0] - 4, c[1] - 4), (c[0] + 4, c[1] + 4), 2)
            pygame.draw.line(self.ekran, rang, (c[0] - 4, c[1] + 4), (c[0] + 4, c[1] - 4), 2)
        else:                                            # tishli g'ildirak (⚙)
            a0 = time.time() * 2 if ustida else 0        # ustiga kelsa aylanadi
            for i in range(8):
                b = a0 + i * math.pi / 4
                pygame.draw.line(self.ekran, rang, (c[0] + math.cos(b) * 4, c[1] + math.sin(b) * 4),
                                 (c[0] + math.cos(b) * 8, c[1] + math.sin(b) * 8), 2)
            pygame.draw.circle(self.ekran, rang, c, 5, 2)

    def soyali_matn(self, matn, shrift, rang):
        """Tiniq matn: silliqlashsiz (shaffof fonda xiralashmaydi) va 1 piksel ingichka
        to'q chegara — och fonda ham, to'q fonda ham aniq o'qiladi.
        Tayyor rasm xotirada saqlanadi (har kadrda qayta chizmaslik uchun)."""
        kalit = (matn, rang, id(shrift))
        yuza = self._matn_xotira.get(kalit)
        if yuza is None:
            asosiy = shrift.render(matn, False, rang)
            chegara = shrift.render(matn, False, (14, 18, 28))
            yuza = pygame.Surface((asosiy.get_width() + 2, asosiy.get_height() + 2))
            yuza.fill((0, 0, 0))
            yuza.set_colorkey((0, 0, 0))
            for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2)):
                yuza.blit(chegara, (dx, dy))
            yuza.blit(asosiy, (1, 1))
            if len(self._matn_xotira) > 200:
                self._matn_xotira.clear()
            self._matn_xotira[kalit] = yuza
        return yuza

    def yozish_joyi_chiz(self, sichqoncha, dt):
        """Zamonaviy yozish joyi (veb-saytlardagi kabi): to'liq yumaloq, tekis rang,
        ingichka chegara; bosilganda chegara mavzu rangiga silliq o'tadi."""
        joy = self.yozuv_joyi
        faol = self.faol == "yozuv"
        yorqin = self.yorqin
        ustida = joy.collidepoint(sichqoncha)
        self.yozuv_nur = aralashtir(self.yozuv_nur, 1.0 if faol else (0.35 if ustida else 0.0),
                                    min(1.0, dt * 10))
        r = joy.h // 2
        fon = rang_aralashtir((24, 29, 40), (30, 36, 50), self.yozuv_nur)
        pygame.draw.rect(self.ekran, tuple(int(c) for c in fon), joy, border_radius=r)
        chegara = rang_aralashtir((58, 66, 84), yorqin, self.yozuv_nur)
        pygame.draw.rect(self.ekran, tuple(int(c) for c in chegara), joy,
                         2 if faol else 1, border_radius=r)

        # chapda qidiruv (lupa) belgisi
        lx, ly = joy.x + 22, joy.centery - 1
        lrang = tuple(int(c) for c in rang_aralashtir((130, 140, 160), yorqin, self.yozuv_nur))
        pygame.draw.circle(self.ekran, lrang, (lx, ly), 6, 2)
        pygame.draw.line(self.ekran, lrang, (lx + 4, ly + 4), (lx + 8, ly + 8), 2)

        # o'ngda yuborish tugmasi — faqat matn yozilganda yorishadi
        self.yuborish_joyi = pygame.Rect(joy.right - joy.h + 6, joy.y + 6, joy.h - 12, joy.h - 12)
        yj = self.yuborish_joyi
        bor_matn = bool(self.matnlar["yozuv"].strip())
        if bor_matn:
            trang = rang_aralashtir(yorqin, (255, 255, 255), 0.25 if yj.collidepoint(sichqoncha) else 0)
            pygame.draw.circle(self.ekran, tuple(int(c) for c in trang), yj.center, yj.w // 2)
            cx, cy = yj.center
            pygame.draw.line(self.ekran, (16, 20, 30), (cx, cy + 6), (cx, cy - 6), 2)
            pygame.draw.lines(self.ekran, (16, 20, 30), False,
                              [(cx - 5, cy - 1), (cx, cy - 6), (cx + 5, cy - 1)], 2)

        # matn
        matn = self.matnlar["yozuv"]
        chap = joy.x + 40
        eni = yj.x - chap - 8
        if matn or faol:
            while self.shrift_yozuv.size(matn)[0] > eni and matn:
                matn = matn[1:]
            kursor = "|" if faol and int(time.time() * 2) % 2 == 0 else ""
            yuza = self.shrift_yozuv.render(matn + kursor, True, (236, 240, 248), fon)
        else:
            yuza = self.shrift_yozuv.render(self.y("yozing"), True, (120, 130, 150), fon)
            if yuza.get_width() > eni:
                yuza = yuza.subsurface((0, 0, eni, yuza.get_height()))
        self.ekran.blit(yuza, (chap, joy.centery - yuza.get_height() // 2))

    def matnlarni_chiz(self, dt=0.025):
        yorqin = self.yorqin
        sichqoncha = pygame.mouse.get_pos()
        if self.rejim == "mini":
            return                                   # faqat shar
        if self.rejim == "mini_yoz":
            self.yozish_joyi_chiz(sichqoncha, dt)    # shar + ostida yozish joyi
            return

        # siz va Jarvis gaplari — ramkasiz, markazda, soyali
        maydon = self.panel
        qatorlar = []
        if self.siz_matni:
            for qator in matnni_bol(self.shrift, self.siz_matni, maydon.w - 16, 2):
                qatorlar.append((qator, (205, 214, 230)))
        if self.jarvis_matni:
            qolgan = max(1, (maydon.h - len(qatorlar) * 23) // 23)
            for qator in matnni_bol(self.shrift, self.jarvis_matni, maydon.w - 16, qolgan):
                qatorlar.append((qator, yorqin))
        y = maydon.y + 4
        for qator, rang in qatorlar:
            yuza = self.soyali_matn(qator, self.shrift, rang)
            self.ekran.blit(yuza, (self.eni // 2 - yuza.get_width() // 2, y))
            y += 23

        self.yozish_joyi_chiz(sichqoncha, dt)

        yuza = self.soyali_matn(self.y(self.holat), self.shrift_kichik, yorqin)
        self.ekran.blit(yuza, (self.eni // 2 - yuza.get_width() // 2, self.holat_y - 9))


    # ----- SOZLAMALAR ILOVASI -----
    def tugma(self, tid, joy):
        """Tugmani ro'yxatga oladi va animatsiya holatini qaytaradi."""
        t = self.tugmalar.get(tid)
        if t is None:
            t = self.tugmalar[tid] = Tugma()
        t.joy = pygame.Rect(joy)
        self.chizilgan.append(tid)
        return t

    def tolqinlar_chiz(self, sirt, t, joy, radius):
        """Bosilganda tugma ichida tarqaluvchi yorug' to'lqin."""
        hozir = time.time()
        for x, y, boshlandi in t.tolqinlar:
            o = (hozir - boshlandi) / 0.6
            qatlam = pygame.Surface(joy.size, pygame.SRCALPHA)
            pygame.draw.circle(qatlam, (*self.yorqin, int(90 * (1 - o))), (x, y),
                               int(max(joy.w, joy.h) * 1.2 * o))
            maska = pygame.Surface(joy.size, pygame.SRCALPHA)
            pygame.draw.rect(maska, (255, 255, 255, 255), maska.get_rect(), border_radius=radius)
            qatlam.blit(maska, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            sirt.blit(qatlam, joy.topleft)

    def karta(self, sirt, t, tanlangan, radius=16):
        """Animatsiyali karta foni: ustiga kelsa yorishadi, tanlangan bo'lsa chegarasi porlaydi."""
        joy = t.korinish()
        yorqin = self.yorqin
        asos = rang_aralashtir((16, 24, 42), (24, 36, 62), t.ustida)
        if tanlangan:
            asos = rang_aralashtir(asos, tuple(c * 0.25 for c in yorqin), 0.6)
        if tanlangan or t.ustida > 0.05:                 # tashqi nur
            puls = 0.5 + 0.5 * math.sin(time.time() * 3) if tanlangan else 0
            kuch = int(40 + 50 * max(t.ustida, puls * 0.6))
            nur = pygame.Surface((joy.w + 24, joy.h + 24), pygame.SRCALPHA)
            for i in range(6, 0, -1):
                pygame.draw.rect(nur, (*yorqin, kuch // (i + 1)), nur.get_rect().inflate(-i * 2, -i * 2),
                                 border_radius=radius + 6)
            sirt.blit(nur, (joy.x - 12, joy.y - 12))
        pygame.draw.rect(sirt, tuple(int(c) for c in asos), joy, border_radius=radius)
        chegara = yorqin if tanlangan else rang_aralashtir((45, 65, 100), yorqin, t.ustida * 0.6)
        pygame.draw.rect(sirt, tuple(int(c) for c in chegara), joy, 2 if tanlangan else 1,
                         border_radius=radius)
        self.tolqinlar_chiz(sirt, t, joy, radius)
        return joy

    def belgi_chiz(self, sirt, nom, c, rang, o=10):
        """Yon menyu belgilari (oddiy chiziqlardan)."""
        x, y = c
        if nom == "ovoz":
            for i, h in enumerate((0.5, 1.0, 0.7, 0.35)):
                pygame.draw.line(sirt, rang, (x - 6 + i * 4, y - o * h), (x - 6 + i * 4, y + o * h), 2)
        elif nom == "til":
            pygame.draw.circle(sirt, rang, c, o, 2)
            pygame.draw.ellipse(sirt, rang, (x - o // 2, y - o, o, o * 2), 1)
            pygame.draw.line(sirt, rang, (x - o, y), (x + o, y), 1)
        elif nom == "korinish":
            for i in range(3):
                b = i * 2.094 + 0.5
                pygame.draw.circle(sirt, rang, (x + math.cos(b) * 5, y + math.sin(b) * 5), 5, 2)
        elif nom == "profil":
            pygame.draw.circle(sirt, rang, (x, y - 4), 5, 2)
            pygame.draw.arc(sirt, rang, (x - 9, y + 1, 18, 16), 0, math.pi, 2)
        elif nom == "telefon":
            pygame.draw.rect(sirt, rang, (x - 6, y - o, 12, o * 2), 2, border_radius=3)
            pygame.draw.line(sirt, rang, (x - 2, y + o - 4), (x + 2, y + o - 4), 2)
        else:
            pygame.draw.circle(sirt, rang, c, o, 2)
            pygame.draw.line(sirt, rang, (x, y - 1), (x, y + 5), 2)
            pygame.draw.circle(sirt, rang, (x, y - 5), 1)

    def sozlamalarni_chiz(self, vaqt, dt):
        sk = self.sk
        eni, boyi = self.eni, self.boyi
        yorqin = self.yorqin
        self.chizilgan = []
        sichqoncha = pygame.mouse.get_pos()
        self.ekran.blit(self.soz_fon, (0, 0))

        # ---- yon menyu ----
        yon_eni = int(300 * sk)
        pygame.draw.rect(self.ekran, (8, 13, 24), (0, 0, yon_eni, boyi))
        pygame.draw.line(self.ekran, (25, 40, 65), (yon_eni, 0), (yon_eni, boyi))
        # logotip: jonli kichik shar
        q = self.shar_qatlami
        q.fill((0, 0, 0))
        qc = q.get_width() // 2
        self.zarrachalar(q, qc, qc, self.R0 * self.kattalik, self.rasmlar, self.yadro, vaqt)
        q.fill(tuple(int(c) for c in self.rang), special_flags=pygame.BLEND_MULT)
        lx, ly = int(30 * sk), int(28 * sk)
        self.ekran.blit(q, (lx - qc + self.R0, ly - qc + self.R0), special_flags=pygame.BLEND_ADD)
        self.ekran.blit(self.sh["logo"].render("JARVIS", True, (235, 242, 255)),
                        (lx + self.R0 * 2 + int(16 * sk), ly + int(10 * sk)))
        self.ekran.blit(self.sh["izoh"].render(self.y("sozlamalar"), True, (110, 130, 160)),
                        (lx + self.R0 * 2 + int(16 * sk), ly + int(38 * sk)))

        element_y = ly + self.R0 * 2 + int(50 * sk)
        balandlik = int(56 * sk)
        tanlangan_y = element_y + BOLIMLAR.index(self.bolim) * (balandlik + int(6 * sk))
        self.belgi_y = tanlangan_y if self.belgi_y is None else aralashtir(
            self.belgi_y, tanlangan_y, min(1.0, dt * 14))    # sirpanuvchi belgi
        belgi = pygame.Rect(int(16 * sk), int(self.belgi_y), yon_eni - int(32 * sk), balandlik)
        pygame.draw.rect(self.ekran, tuple(int(c * 0.22) for c in yorqin), belgi, border_radius=12)
        pygame.draw.rect(self.ekran, yorqin, (belgi.x, belgi.y + 12, 4, belgi.h - 24), border_radius=2)
        for i, nom in enumerate(BOLIMLAR):
            joy = pygame.Rect(int(16 * sk), element_y + i * (balandlik + int(6 * sk)),
                              yon_eni - int(32 * sk), balandlik)
            t = self.tugma(f"bolim:{nom}", joy)
            t.yangila(dt, sichqoncha)
            if nom != self.bolim and t.ustida > 0.02:
                qatlam = pygame.Surface(joy.size, pygame.SRCALPHA)
                pygame.draw.rect(qatlam, (255, 255, 255, int(14 * t.ustida)), qatlam.get_rect(),
                                 border_radius=12)
                self.ekran.blit(qatlam, joy.topleft)
            self.tolqinlar_chiz(self.ekran, t, joy, 12)
            rang = yorqin if nom == self.bolim else rang_aralashtir((150, 165, 190), (235, 242, 255), t.ustida)
            rang = tuple(int(c) for c in rang)
            self.belgi_chiz(self.ekran, nom, (joy.x + int(30 * sk) + int(t.ustida * 3), joy.centery), rang)
            yuza = self.sh["matn"].render(self.y(nom), True, rang)
            self.ekran.blit(yuza, (joy.x + int(56 * sk) + int(t.ustida * 4),
                                   joy.centery - yuza.get_height() // 2))

        # ---- yopish tugmasi ----
        yuza = self.sh["tugma"].render(f"{self.y('yopish')}  (Esc)", True, (230, 238, 250))
        joy = pygame.Rect(0, 0, yuza.get_width() + int(70 * sk), int(46 * sk))
        joy.topright = (eni - int(36 * sk), int(28 * sk))
        t = self.tugma("yopish", joy)
        t.yangila(dt, sichqoncha)
        k = self.karta(self.ekran, t, False, radius=joy.h // 2)
        xc, yc, r = k.x + int(26 * sk), k.centery, int(6 * sk)
        b = t.ustida * math.pi / 2                       # ustiga kelsa × aylanadi
        for ug in (math.pi / 4, 3 * math.pi / 4):
            dx, dy = math.cos(ug + b) * r, math.sin(ug + b) * r
            pygame.draw.line(self.ekran, (230, 238, 250), (xc - dx, yc - dy), (xc + dx, yc + dy), 2)
        self.ekran.blit(yuza, (k.x + int(46 * sk), k.centery - yuza.get_height() // 2))

        # ---- bo'lim kontenti: silliq kirib keladi ----
        kt = yumshoq(self.bolim_t)
        c = self.kontent
        c.fill((0, 0, 0, 0))
        x0 = yon_eni + int(64 * sk)
        siljish = int(40 * sk * (1 - kt))
        sarlavha = self.sh["sarlavha"].render(self.y(self.bolim), True, (240, 245, 255))
        c.blit(sarlavha, (x0 + siljish, int(40 * sk)))
        izoh = self.sh["izoh"].render(self.y(self.bolim + "_izoh"), True, (120, 140, 170))
        c.blit(izoh, (x0 + siljish, int(40 * sk) + sarlavha.get_height() + int(6 * sk)))
        y0 = int(150 * sk)
        getattr(self, "bolim_" + self.bolim)(c, x0 + siljish, y0, dt, sichqoncha, vaqt)
        c.set_alpha(int(255 * kt))
        self.ekran.blit(c, (0, 0))

    def _karta_tugmasi(self, c, tid, joy, tanlangan, dt, sichqoncha):
        t = self.tugma(tid, joy)
        t.yangila(dt, sichqoncha)
        return t, self.karta(c, t, tanlangan)

    def _belgi(self, c, joy):
        """Tanlangan kartaning burchagidagi ✓ belgisi."""
        m = (joy.right - int(24 * self.sk), joy.y + int(24 * self.sk))
        pygame.draw.circle(c, self.yorqin, m, int(11 * self.sk))
        r = self.sk
        pygame.draw.lines(c, (10, 16, 28), False,
                          [(m[0] - 5 * r, m[1]), (m[0] - 1 * r, m[1] + 4 * r), (m[0] + 6 * r, m[1] - 4 * r)], 3)

    def bolim_ovoz(self, c, x0, y0, dt, sichqoncha, vaqt):
        sk = self.sk
        nomlar = OVOZ_NOMLARI[self.sozlama["til"]]
        ke, kb = int(360 * sk), int(210 * sk)
        for i, turi in enumerate(("ayol", "erkak")):
            joy = pygame.Rect(x0 + i * (ke + int(28 * sk)), y0, ke, kb)
            tanlangan = self.sozlama["ovoz"] == turi
            t, k = self._karta_tugmasi(c, f"ovoz:{turi}", joy, tanlangan, dt, sichqoncha)
            # jonli to'lqin chiziqlari (ustiga kelsa yoki tanlangan bo'lsa harakatlanadi)
            faol = max(t.ustida, 1.0 if tanlangan else 0.25)
            for j in range(18):
                h = (0.25 + 0.75 * abs(math.sin(vaqt * 5 * faol + j * 0.7 + i))) * faol
                bx = k.x + int(28 * sk) + j * int(9 * sk)
                bb = int(34 * sk * h) + 2
                rang = self.yorqin if tanlangan else (90, 110, 150)
                pygame.draw.line(c, rang, (bx, k.y + int(60 * sk) - bb // 2),
                                 (bx, k.y + int(60 * sk) + bb // 2), max(2, int(3 * sk)))
            c.blit(self.sh["karta"].render(self.y(turi), True, (240, 245, 255)),
                   (k.x + int(28 * sk), k.y + int(100 * sk)))
            c.blit(self.sh["izoh"].render(nomlar[i], True, (130, 150, 180)),
                   (k.x + int(28 * sk), k.y + int(132 * sk)))
            if tanlangan:
                self._belgi(c, k)
            # "Eshitib ko'rish" tugmasi
            yuza = self.sh["tugma"].render(self.y("sinab"), True, (235, 242, 255))
            tj = pygame.Rect(0, 0, yuza.get_width() + int(54 * sk), int(36 * sk))
            tj.bottomright = (k.right - int(18 * sk), k.bottom - int(16 * sk))
            st = self.tugma(f"sinov:{turi}", tj)
            st.yangila(dt, sichqoncha)
            sk_ = self.karta(c, st, False, radius=tj.h // 2)
            px, py, u = sk_.x + int(20 * sk), sk_.centery, int(6 * sk)     # ▶ uchburchak
            pygame.draw.polygon(c, self.yorqin, [(px, py - u), (px, py + u), (px + u * 1.6, py)])
            c.blit(yuza, (sk_.x + int(38 * sk), sk_.centery - yuza.get_height() // 2))

    def bolim_til(self, c, x0, y0, dt, sichqoncha, vaqt):
        sk = self.sk
        ke, kb = int(250 * sk), int(170 * sk)
        for i, (kalit, til) in enumerate(S.TILLAR.items()):
            qator, ustun = divmod(i, 2)
            joy = pygame.Rect(x0 + ustun * (ke + int(26 * sk)), y0 + qator * (kb + int(26 * sk)), ke, kb)
            tanlangan = self.sozlama["til"] == kalit
            t, k = self._karta_tugmasi(c, f"til:{kalit}", joy, tanlangan, dt, sichqoncha)
            # bayroq chiziqlari
            for j, rang in enumerate(BAYROQLAR[kalit]):
                pygame.draw.rect(c, rang, (k.x + int(24 * sk), k.y + int(24 * sk) + j * int(9 * sk),
                                           int(54 * sk), int(9 * sk)))
            c.blit(self.sh["katta"].render(kalit.upper(), True, (240, 245, 255)),
                   (k.x + int(24 * sk), k.y + int(64 * sk)))
            c.blit(self.sh["matn"].render(til["nomi"], True, (140, 160, 190)),
                   (k.x + int(24 * sk), k.y + int(118 * sk)))
            if tanlangan:
                self._belgi(c, k)

    def bolim_korinish(self, c, x0, y0, dt, sichqoncha, vaqt):
        sk = self.sk
        ke, kb = int(170 * sk), int(150 * sk)
        for i, (kalit, mavzu) in enumerate(S.RANGLAR.items()):
            qator, ustun = divmod(i, 3)
            joy = pygame.Rect(x0 + ustun * (ke + int(22 * sk)), y0 + qator * (kb + int(22 * sk)), ke, kb)
            tanlangan = self.sozlama["rang"] == kalit
            t, k = self._karta_tugmasi(c, f"rang:{kalit}", joy, tanlangan, dt, sichqoncha)
            m = (k.centerx, k.y + int(58 * sk))
            r = int((30 + 4 * t.ustida) * sk)
            for j in range(5, 0, -1):                   # porlovchi rang doirasi
                pygame.draw.circle(c, (*mavzu["yorqin"], 25), m, r + j * int(3 * sk))
            pygame.draw.circle(c, mavzu["xira"], m, r)
            pygame.draw.circle(c, mavzu["yorqin"], m, int(r * 0.7))
            pygame.draw.circle(c, (255, 255, 255), (m[0] - r // 3, m[1] - r // 3), max(2, r // 6))
            yuza = self.sh["matn"].render(mavzu["nomi"], True, (225, 235, 250))
            c.blit(yuza, (k.centerx - yuza.get_width() // 2, k.bottom - int(40 * sk)))
            if tanlangan:
                self._belgi(c, k)
        # o'ngda: jonli ko'rinish (katta shar)
        R = self.oldindan_R
        oq = self.oldindan_qatlam
        oq.fill((0, 0, 0))
        oc = oq.get_width() // 2
        self.zarrachalar(oq, oc, oc, R, self.rasmlar_to_plami["soz_katta"], self.oldindan_yadro, vaqt)
        oq.fill(tuple(int(v) for v in holat_rangi("tinglash", self.sozlama["rang"])),
                special_flags=pygame.BLEND_MULT)
        px = x0 + 3 * (ke + int(22 * sk)) + int(40 * sk)
        if px + oq.get_width() <= self.eni:
            self.ekran.blit(oq, (px, y0 - int(30 * sk)), special_flags=pygame.BLEND_ADD)

    def bolim_profil(self, c, x0, y0, dt, sichqoncha, vaqt):
        sk = self.sk
        joy = pygame.Rect(x0, y0, int(520 * sk), int(56 * sk))
        t = self.tugma("ism_maydon", joy)
        t.yangila(dt, sichqoncha)
        if t.ustida > 0.05 and self.faol != "ism":
            pygame.draw.rect(c, (*self.yorqin, int(60 * t.ustida)), joy.inflate(6, 6), 2, border_radius=12)
        self.maydon_chiz(c, joy, "ism", self.sozlama["ism"], self.sh["matn"])
        yuza = self.sh["tugma"].render(self.y("saqlash"), True, (10, 16, 28))
        sj = pygame.Rect(joy.right + int(18 * sk), y0, yuza.get_width() + int(56 * sk), int(56 * sk))
        st = self.tugma("saqlash", sj)
        st.yangila(dt, sichqoncha)
        k = st.korinish()
        pygame.draw.rect(c, rang_aralashtir(self.yorqin, (255, 255, 255), st.ustida * 0.25), k,
                         border_radius=14)
        self.tolqinlar_chiz(c, st, k, 14)
        c.blit(yuza, (k.centerx - yuza.get_width() // 2, k.centery - yuza.get_height() // 2))

    def bolim_telefon(self, c, x0, y0, dt, sichqoncha, vaqt):
        sk = self.sk
        # holat kartasi
        ranglar = {"yoq": (120, 130, 150), "kod": (255, 190, 70), "ulangan": (80, 230, 140),
                   "xato": (255, 90, 90)}
        rang = ranglar.get(self.tg_holat, (120, 130, 150))
        karta = pygame.Rect(x0, y0, int(640 * sk), int(90 * sk))
        pygame.draw.rect(c, (16, 24, 42), karta, border_radius=16)
        pygame.draw.rect(c, rang, karta, 1, border_radius=16)
        puls = 0.6 + 0.4 * math.sin(vaqt * 4)
        m = (karta.x + int(34 * sk), karta.centery)
        pygame.draw.circle(c, (*rang, int(70 * puls)), m, int(14 * sk))
        pygame.draw.circle(c, rang, m, int(7 * sk))
        c.blit(self.sh["matn"].render(self.y("tg_" + self.tg_holat), True, (230, 238, 250)),
               (karta.x + int(64 * sk), karta.y + int(18 * sk)))
        if self.tg_holat == "kod":
            c.blit(self.sh["katta"].render("  ".join(self.tg_qiymat), True, rang),
                   (karta.right + int(24 * sk), karta.y + int(14 * sk)))
        elif self.tg_holat == "ulangan" and self.tg_qiymat:
            c.blit(self.sh["izoh"].render("@" + self.tg_qiymat, True, (130, 150, 180)),
                   (karta.x + int(64 * sk), karta.y + int(50 * sk)))
        if self.tg_holat == "ulangan":
            yuza = self.sh["tugma"].render(self.y("tg_uzish"), True, (255, 150, 150))
            uj = pygame.Rect(0, 0, yuza.get_width() + int(40 * sk), int(40 * sk))
            uj.midright = (karta.right - int(20 * sk), karta.centery)
            ut = self.tugma("tg_uzish", uj)
            ut.yangila(dt, sichqoncha)
            k = self.karta(c, ut, False, radius=uj.h // 2)
            c.blit(yuza, (k.centerx - yuza.get_width() // 2, k.centery - yuza.get_height() // 2))

        # token maydoni
        y = karta.bottom + int(34 * sk)
        c.blit(self.sh["izoh"].render(self.y("tg_token"), True, (140, 160, 190)), (x0, y))
        y += int(28 * sk)
        joy = pygame.Rect(x0, y, int(520 * sk), int(56 * sk))
        t = self.tugma("token_maydon", joy)
        t.yangila(dt, sichqoncha)
        if t.ustida > 0.05 and self.faol != "token":
            pygame.draw.rect(c, (*self.yorqin, int(60 * t.ustida)), joy.inflate(6, 6), 2, border_radius=12)
        self.maydon_chiz(c, joy, "token", "123456789:AAE...", self.sh["matn"], yashirin=True)
        yuza = self.sh["tugma"].render(self.y("saqlash"), True, (10, 16, 28))
        sj = pygame.Rect(joy.right + int(18 * sk), y, yuza.get_width() + int(56 * sk), int(56 * sk))
        st = self.tugma("token_saqlash", sj)
        st.yangila(dt, sichqoncha)
        k = st.korinish()
        pygame.draw.rect(c, rang_aralashtir(self.yorqin, (255, 255, 255), st.ustida * 0.25), k,
                         border_radius=14)
        self.tolqinlar_chiz(c, st, k, 14)
        c.blit(yuza, (k.centerx - yuza.get_width() // 2, k.centery - yuza.get_height() // 2))

        # qadamlar
        y = joy.bottom + int(40 * sk)
        for i, qator in enumerate(self.y("tg_qadamlar")):
            rang_ = self.yorqin if i == 4 else (200, 212, 232)
            c.blit(self.sh["matn"].render(qator, True, rang_), (x0, y + i * int(36 * sk)))

    def bolim_haqida(self, c, x0, y0, dt, sichqoncha, vaqt):
        sk = self.sk
        qatorlar = self.y("haqida_matn") + [self.y("ong_tugma")]
        for i, qator in enumerate(qatorlar):
            y = y0 + i * int(46 * sk)
            pygame.draw.circle(c, self.yorqin, (x0 + int(8 * sk), y + int(12 * sk)), int(4 * sk))
            c.blit(self.sh["matn"].render(qator, True, (205, 215, 235)), (x0 + int(28 * sk), y))
        yuza = self.sh["tugma"].render(self.y("ochirish"), True, (255, 170, 170))
        joy = pygame.Rect(x0, y0 + len(qatorlar) * int(46 * sk) + int(20 * sk),
                          yuza.get_width() + int(56 * sk), int(48 * sk))
        t = self.tugma("jarvis_ochir", joy)
        t.yangila(dt, sichqoncha)
        k = self.karta(c, t, False, radius=joy.h // 2)
        c.blit(yuza, (k.centerx - yuza.get_width() // 2, k.centery - yuza.get_height() // 2))

    # ----- asosiy sikl -----
    def ishga_tushir(self):
        soat = pygame.time.Clock()
        boshlanish = time.time()
        while self.ishlayapti:
            dt = soat.tick(FPS) / 1000
            self.xabarlarni_ol()
            self.hodisalar()
            self.holatni_yangila(dt)
            vaqt = time.time() - boshlanish
            if self.rejim == "sozlama":
                self.sozlamalarni_chiz(vaqt, dt)
            else:
                self.ekran.fill(FON)
                self.shar_chiz(vaqt)
                self.matnlarni_chiz(dt)
            pygame.display.flip()
        pygame.quit()
