"""
Jarvis'ning ko'rinishi: minglab nuqtalardan iborat aylanuvchi 3D shar.

Kutish rejimida — ekran burchagida kichik oyna.
"Jarvis" deganda — ekran o'rtasida katta bo'lib chiqadi.

Bu oyna ASOSIY thread'da ishlaydi. Tinglash va buyruqlar boshqa thread'da.
Ular bir-biri bilan ikkita navbat (queue) orqali gaplashadi:
  ui_navbat     — Jarvis -> oyna:  ("holat", "kutish"), ("siz", matn), ("jarvis", matn),
                                    ("ovoz", balandliklar, boshlanish_vaqti),
                                    ("sozlamalar", lug'at), ("yopil",)
  kirish_navbat — oyna -> Jarvis:  ("yozuv", matn, vaqt)  — pastga yozilgan buyruq
                                    ("sozlama", (kalit, qiymat), vaqt) — menyuda tanlangan
"""
import math
import os
import queue
import random
import time

import pygame

import sozlamalar as S

NUQTALAR_SONI = 2200
ORBITA_NUQTALARI = 90
FPS = 40
FON = (0, 0, 0)               # shu rang shaffof bo'ladi (Windows)
PANEL = (10, 16, 28)
DISK = (5, 9, 18)

# Holat: kattalik, aylanish tezligi, yorqinlik. Rang — tanlangan mavzudan olinadi.
HOLATLAR = {
    "kutish":   {"kattalik": 0.80, "tezlik": 0.25, "yorqinlik": 0.55},
    "tinglash": {"kattalik": 1.00, "tezlik": 0.95, "yorqinlik": 1.00},
    "o'ylash":  {"kattalik": 0.92, "tezlik": 1.60, "yorqinlik": 0.85},
    "gapirish": {"kattalik": 0.95, "tezlik": 0.60, "yorqinlik": 1.00},
    "shazam":   {"kattalik": 1.00, "tezlik": 1.20, "yorqinlik": 1.00},
}

# Oyna yozuvlari 4 tilda
YOZUVLAR = {
    "uz": {"kutish": "Kutish rejimi — Jarvis deng", "tinglash": "Tinglayapman…",
           "o'ylash": "Bajaryapman…", "gapirish": "Gapiryapman…",
           "shazam": "Musiqani tinglayapman…", "yozing": "Shu yerga yozing va Enter bosing…",
           "siz": "Siz", "sozlamalar": "Sozlamalar", "ovoz": "Ovoz", "ayol": "Ayol",
           "erkak": "Erkak", "til": "Til", "rang": "Rang", "ism": "Ismingiz"},
    "ru": {"kutish": "Ожидание — скажите Джарвис", "tinglash": "Слушаю…",
           "o'ylash": "Выполняю…", "gapirish": "Говорю…", "shazam": "Слушаю музыку…",
           "yozing": "Напишите здесь и нажмите Enter…", "siz": "Вы",
           "sozlamalar": "Настройки", "ovoz": "Голос", "ayol": "Женский", "erkak": "Мужской",
           "til": "Язык", "rang": "Цвет", "ism": "Ваше имя"},
    "en": {"kutish": "Standby — say Jarvis", "tinglash": "Listening…",
           "o'ylash": "Working…", "gapirish": "Speaking…", "shazam": "Listening to music…",
           "yozing": "Type here and press Enter…", "siz": "You", "sozlamalar": "Settings",
           "ovoz": "Voice", "ayol": "Female", "erkak": "Male", "til": "Language",
           "rang": "Color", "ism": "Your name"},
    "de": {"kutish": "Bereit — sag Jarvis", "tinglash": "Ich höre zu…",
           "o'ylash": "Ich arbeite…", "gapirish": "Ich spreche…", "shazam": "Ich höre Musik…",
           "yozing": "Hier tippen und Enter drücken…", "siz": "Sie",
           "sozlamalar": "Einstellungen", "ovoz": "Stimme", "ayol": "Weiblich",
           "erkak": "Männlich", "til": "Sprache", "rang": "Farbe", "ism": "Ihr Name"},
}


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


# ---------- WINDOWS: shaffof fon, doim ustida, joylashuv ----------
def _hwnd():
    try:
        return pygame.display.get_wm_info()["window"]
    except (KeyError, pygame.error):
        return None


def windows_sozla():
    """Qora rangni shaffof qiladi va oynani doim boshqa oynalar ustida ushlaydi."""
    if os.name != "nt":
        return
    import ctypes
    u32 = ctypes.windll.user32
    hwnd = _hwnd()
    if not hwnd:
        return
    GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TOOLWINDOW = -20, 0x80000, 0x80
    uslub = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    u32.SetWindowLongW(hwnd, GWL_EXSTYLE, uslub | WS_EX_LAYERED)
    u32.SetLayeredWindowAttributes(hwnd, 0x000000, 0, 0x1)          # 0x1 = LWA_COLORKEY
    HWND_TOPMOST, SWP_NOMOVE, SWP_NOSIZE = -1, 0x2, 0x1
    u32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)


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


def oyna_joyi():
    if os.name == "nt":
        import ctypes
        import ctypes.wintypes
        rect = ctypes.wintypes.RECT()
        ctypes.windll.user32.GetWindowRect(_hwnd(), ctypes.byref(rect))
        return rect.left, rect.top
    return 0, 0


def oynani_sur(x, y):
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.SetWindowPos(_hwnd(), -1, int(x), int(y), 0, 0, 0x1)  # SWP_NOSIZE


def sichqoncha_ekranda():
    if os.name == "nt":
        import ctypes
        import ctypes.wintypes
        nuqta = ctypes.wintypes.POINT()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(nuqta))
        return nuqta.x, nuqta.y
    return pygame.mouse.get_pos()


# ---------- SHAR ----------
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


def nuqta_rasmlari(koef=1.0):
    """Oldindan chizilgan yumshoq porlovchi nuqtalar (kul rangda; keyin bo'yaladi).
    [kattalik][yorqinlik] — har kadrda aylana chizishdan ancha tez."""
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
    """Yumshoq yorug'lik (radial gradient): shar ichi va atrofidagi nur uchun."""
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

        # Ikki o'lcham: kichik (burchakda) va katta (ekran o'rtasida)
        self.maydon = ish_maydoni()
        chap, tepa, ong, past = self.maydon
        koef = max(0.6, min(1.0, (past - tepa - 40) / 760))
        self.olchamlar = {"kichik": (340, 500), "katta": (int(600 * koef), int(760 * koef))}
        self.katta_koef = koef
        self.kichik_joy = (ong - 340 - 16, past - 500 - 16)
        os.environ["SDL_VIDEO_WINDOW_POS"] = f"{self.kichik_joy[0]},{self.kichik_joy[1]}"
        self.rejim = "kichik"
        self.ekran = pygame.display.set_mode(self.olchamlar["kichik"], pygame.NOFRAME)
        pygame.display.set_caption("Jarvis")
        pygame.display.set_icon(self._ikonka())
        windows_sozla()
        pygame.key.start_text_input()

        self.nuqtalar = fibonacci_shar(NUQTALAR_SONI)
        self.orbita = [(2 * math.pi * i / ORBITA_NUQTALARI, random.uniform(0.97, 1.03))
                       for i in range(ORBITA_NUQTALARI)]
        self.rasmlar_to_plami = {"kichik": nuqta_rasmlari(1.0), "katta": nuqta_rasmlari(1.35)}
        self.shrift = pygame.font.SysFont("segoeui,arial", 15)
        self.shrift_kichik = pygame.font.SysFont("segoeui,arial", 12)
        self.shrift_sarlavha = pygame.font.SysFont("segoeui,arial", 14, bold=True)

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
        self.matnlar = {"yozuv": "", "ism": self.sozlama["ism"]}
        self.faol = None                  # qaysi maydonga yozilyapti: "yozuv" yoki "ism"
        self.surish = None                # sichqoncha bilan surish boshlangan joy
        self.sozlama_ochiq = False
        self.tugmalar = []                # sozlamalar menyusidagi tugmalar
        self.ishlayapti = True
        self.joylash()

    def _ikonka(self):
        s = pygame.Surface((32, 32))
        s.fill((0, 0, 0))
        pygame.draw.circle(s, (30, 90, 200), (16, 16), 14)
        pygame.draw.circle(s, (90, 200, 255), (16, 16), 9)
        pygame.draw.circle(s, (220, 245, 255), (13, 12), 3)
        return s

    def y(self, kalit):
        """Oyna yozuvi tanlangan tilda."""
        return YOZUVLAR.get(self.sozlama["til"], YOZUVLAR["uz"])[kalit]

    # ----- o'lchamga qarab joylashuv -----
    def joylash(self):
        eni, boyi = self.olchamlar[self.rejim]
        self.eni, self.boyi = eni, boyi
        katta = self.rejim == "katta"
        k = self.katta_koef if katta else 1.0
        self.R0 = int((175 if katta else 95) * k)
        self.markaz = (eni // 2, int((300 if katta else 170) * k))
        self.disk_r = int(self.R0 * 1.5)
        self.rasmlar = self.rasmlar_to_plami[self.rejim]
        self.yadro = yadro_nuri(self.R0)
        self.halo = yadro_nuri(self.disk_r, kuch=38, daraja=1.6)
        self.shar_qatlami = pygame.Surface((eni, self.markaz[1] + self.disk_r + 4))
        pastki = self.markaz[1] + self.disk_r
        self.holat_y = pastki + 12
        self.panel = pygame.Rect(10, pastki + 28, eni - 20, boyi - pastki - 28 - 60)
        self.yozuv_joyi = pygame.Rect(14, boyi - 50, eni - 28, 36)
        self.yopish_joyi = pygame.Rect(eni - 30, 6, 24, 24)
        self.sozlama_joyi = pygame.Rect(6, 6, 24, 24)

    def rejimga_ot(self, rejim):
        if rejim == self.rejim:
            return
        if self.rejim == "kichik":
            self.kichik_joy = oyna_joyi() if os.name == "nt" else self.kichik_joy
        self.rejim = rejim
        eni, boyi = self.olchamlar[rejim]
        self.ekran = pygame.display.set_mode((eni, boyi), pygame.NOFRAME)
        windows_sozla()
        if rejim == "katta":
            chap, tepa, ong, past = self.maydon
            oynani_sur((chap + ong - eni) // 2, (tepa + past - boyi) // 2)
        else:
            oynani_sur(*self.kichik_joy)
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
                self.holat = xabar[1]
            elif tur == "siz":
                self.siz_matni = xabar[1]
            elif tur == "jarvis":
                self.jarvis_matni = xabar[1]
            elif tur == "ovoz":
                self.ovoz = (xabar[1], xabar[2])
            elif tur == "sozlamalar":
                self.sozlama = dict(xabar[1])
                if self.faol != "ism":
                    self.matnlar["ism"] = self.sozlama["ism"]
            elif tur == "sozlamalarni_och":
                self.sozlama_ochiq = True
            elif tur == "yopil":
                self.ishlayapti = False

    def sozlama_yubor(self, kalit, qiymat):
        self.sozlama[kalit] = qiymat
        self.kirish_navbat.put(("sozlama", (kalit, qiymat), time.time()))

    # ----- sichqoncha va klaviatura -----
    def hodisalar(self):
        for h in pygame.event.get():
            if h.type == pygame.QUIT:
                self.ishlayapti = False
            elif h.type == pygame.MOUSEBUTTONDOWN and h.button == 1:
                self.bosildi(h.pos)
            elif h.type == pygame.MOUSEBUTTONUP and h.button == 1:
                self.surish = None
            elif h.type == pygame.MOUSEMOTION and self.surish:
                mx, my = sichqoncha_ekranda()
                oynani_sur(mx - self.surish[0], my - self.surish[1])
            elif h.type == pygame.TEXTINPUT and self.faol:
                if len(self.matnlar[self.faol]) < 200:
                    self.matnlar[self.faol] += h.text
            elif h.type == pygame.KEYDOWN and self.faol:
                self.tugma_bosildi(h)

    def bosildi(self, joy):
        if self.yopish_joyi.collidepoint(joy):
            self.ishlayapti = False
            return
        if self.sozlama_joyi.collidepoint(joy):
            self.sozlama_ochiq = not self.sozlama_ochiq
            self.faol = None
            return
        if self.sozlama_ochiq:
            for joy_, kalit, qiymat in self.tugmalar:
                if joy_.collidepoint(joy):
                    if kalit == "ism":
                        self.faol = "ism"
                    else:
                        self.sozlama_yubor(kalit, qiymat)
                    return
        if self.yozuv_joyi.collidepoint(joy) and not self.sozlama_ochiq:
            self.faol = "yozuv"
            return
        self.faol = None
        mx, my = sichqoncha_ekranda()
        ox, oy = oyna_joyi()
        self.surish = (mx - ox, my - oy)

    def tugma_bosildi(self, h):
        maydon = self.faol
        if h.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            matn = self.matnlar[maydon].strip()
            if maydon == "yozuv":
                if matn:
                    self.kirish_navbat.put(("yozuv", matn, time.time()))
                self.matnlar["yozuv"] = ""
            elif matn:
                self.sozlama_yubor("ism", matn)
                self.faol = None
        elif h.key == pygame.K_BACKSPACE:
            self.matnlar[maydon] = self.matnlar[maydon][:-1]
        elif h.key == pygame.K_ESCAPE:
            if maydon == "yozuv":
                self.matnlar["yozuv"] = ""
            else:
                self.matnlar["ism"] = self.sozlama["ism"]
            self.faol = None
        elif h.key == pygame.K_v and h.mod & pygame.KMOD_CTRL:
            try:
                import pyperclip
                self.matnlar[maydon] += pyperclip.paste().replace("\n", " ")[:200]
            except Exception:
                pass

    # ----- holat va animatsiya -----
    def holatni_yangila(self, dt):
        # Faol bo'lsa — markazda katta; 1.5 soniya kutish rejimida tursa — burchakka qaytadi
        if self.holat != "kutish":
            self.rejimga_ot("katta")
        elif time.time() - self.kutish_boshlandi > 1.5 and not self.sozlama_ochiq:
            self.rejimga_ot("kichik")

        maqsad = HOLATLAR[self.holat]
        t = min(1.0, dt * 4)                  # yangi holatga silliq o'tish
        self.rang = rang_aralashtir(self.rang, holat_rangi(self.holat, self.sozlama["rang"]), t)
        self.kattalik = aralashtir(self.kattalik, maqsad["kattalik"], t)
        self.tezlik = aralashtir(self.tezlik, maqsad["tezlik"], t)
        self.yorqinlik = aralashtir(self.yorqinlik, maqsad["yorqinlik"], t)
        self.burchak += self.tezlik * dt
        self.kirish = min(1.0, self.kirish + dt * 2.5)

        balandliklar, boshlandi = self.ovoz
        yangi = 0.0
        if balandliklar:
            i = int((time.time() - boshlandi) * 30)
            if 0 <= i < len(balandliklar):
                yangi = balandliklar[i]
        # tez ko'tariladi, sekin tushadi — pulsatsiya tabiiyroq ko'rinadi
        self.daraja = yangi if yangi > self.daraja else aralashtir(self.daraja, yangi, min(1, dt * 8))

    # ----- chizish -----
    def shar_chiz(self, vaqt):
        q = self.shar_qatlami
        q.fill((0, 0, 0))
        cx, cy = self.markaz
        # katta bo'lib chiqish: 0.6 dan 1.0 gacha silliq kattalashadi
        ochilish = 1 - (1 - self.kirish) ** 3
        R = self.R0 * self.kattalik * (0.6 + 0.4 * ochilish)
        ca, sa = math.cos(self.burchak), math.sin(self.burchak)
        egilish = 0.35
        ce, se = math.cos(egilish), math.sin(egilish)
        daraja = self.daraja
        nafas_t = vaqt * 1.6
        tolqin_t = vaqt * 9
        rasmlar = self.rasmlar
        ro_yxat = []
        sin = math.sin

        # orqa fondagi yumshoq nur
        q.blit(self.halo, (cx - self.disk_r, cy - self.disk_r), special_flags=pygame.BLEND_ADD)

        for x, y, z, faza, uzoq in self.nuqtalar:
            # nafas olish + ovozga qarab tashqariga to'lqin
            k = uzoq + 0.03 * sin(nafas_t + faza)
            if daraja > 0.01:
                k += daraja * (0.10 + 0.12 * sin(y * 7 - tolqin_t))
            x2 = x * ca + z * sa                 # Y o'qi atrofida aylanish
            z2 = z * ca - x * sa
            y2 = y * ce - z2 * se                # biroz egilgan holda ko'rinadi
            z3 = y * se + z2 * ce
            chuqurlik = (z3 + 1) * 0.5           # 0 = orqada, 1 = oldida
            kat = 0 if chuqurlik < 0.45 else (1 if chuqurlik < 0.85 else 2)
            yor = int(chuqurlik * 7.99 * self.yorqinlik)
            rasm = rasmlar[kat][yor]
            yarim = rasm.get_width() >> 1
            ro_yxat.append((rasm, (cx + x2 * R * k - yarim, cy + y2 * R * k - yarim)))

        # shar atrofida egilgan orbitada aylanuvchi zarrachalar
        ob = -vaqt * 0.8
        oe, oes = math.cos(1.1), math.sin(1.1)
        for burchak, uzoq in self.orbita:
            b = burchak + ob
            ox, oz = math.cos(b) * 1.28 * uzoq, math.sin(b) * 1.28 * uzoq
            oy = -oz * oes
            chuqurlik = (oz * oe + 1.28) / 2.56
            rasm = rasmlar[1][int(chuqurlik * 5.99 * self.yorqinlik) + 1]
            yarim = rasm.get_width() >> 1
            ro_yxat.append((rasm, (cx + ox * R - yarim, cy + oy * R - yarim)))

        yr = int(R * 1.1)
        yadro = pygame.transform.smoothscale(self.yadro, (yr * 2, yr * 2))
        q.blit(yadro, (cx - yr, cy - yr), special_flags=pygame.BLEND_ADD)
        q.blits([(r, j, None, pygame.BLEND_ADD) for r, j in ro_yxat], doreturn=False)

        # Iron Man uslubidagi aylanuvchi yoylar
        halqa = int(self.R0 * 1.35)
        to_rt = pygame.Rect(cx - halqa, cy - halqa, halqa * 2, halqa * 2)
        a = vaqt * 0.6
        for boshi, uzunligi in ((0, 1.2), (2.2, 0.6), (3.6, 1.5)):
            pygame.draw.arc(q, (90, 90, 90), to_rt, a + boshi, a + boshi + uzunligi, 2)
        to_rt2 = to_rt.inflate(14, 14)
        for boshi in (0.5, 2.6, 4.7):
            pygame.draw.arc(q, (45, 45, 45), to_rt2, -a * 0.7 + boshi, -a * 0.7 + boshi + 0.8, 1)
        # gapirganda yorishadigan halqa
        if daraja > 0.02:
            yorug = int(40 + 160 * daraja)
            pygame.draw.circle(q, (yorug,) * 3, (cx, cy), int(self.R0 * 1.24), 1)

        # shkala chiziqlari (soat siferblati kabi), sekin aylanadi
        r1 = self.R0 * 1.44
        c_ = -vaqt * 0.15
        for i in range(72):
            b = c_ + i * math.pi / 36
            uzun = 7 if i % 6 == 0 else 3
            rang_ = (80, 80, 80) if i % 6 == 0 else (40, 40, 40)
            cb, sb = math.cos(b), math.sin(b)
            pygame.draw.line(q, rang_, (cx + cb * r1, cy + sb * r1),
                             (cx + cb * (r1 + uzun), cy + sb * (r1 + uzun)))

        # kul rangdagi rasmni holat rangiga bo'yaymiz
        q.fill(tuple(int(c) for c in self.rang), special_flags=pygame.BLEND_MULT)
        self.ekran.blit(q, (0, 0), special_flags=pygame.BLEND_ADD)

    def matn_chiz(self, matn, shrift, rang, joy):
        yuza = shrift.render(matn, True, rang)
        self.ekran.blit(yuza, joy)
        return yuza

    def maydon_chiz(self, joy, maydon, bosh_matn):
        faol = self.faol == maydon
        yorqin = S.RANGLAR[self.sozlama["rang"]]["yorqin"]
        pygame.draw.rect(self.ekran, PANEL, joy, border_radius=10)
        pygame.draw.rect(self.ekran, yorqin if faol else (30, 60, 100), joy, 1, border_radius=10)
        matn = self.matnlar[maydon]
        if matn or faol:
            while self.shrift.size(matn)[0] > joy.w - 24 and matn:
                matn = matn[1:]
            kursor = "|" if faol and int(time.time() * 2) % 2 == 0 else ""
            yuza = self.shrift.render(matn + kursor, True, (225, 235, 245))
        else:
            yuza = self.shrift.render(bosh_matn, True, (90, 110, 140))
        self.ekran.blit(yuza, (joy.x + 12, joy.y + (joy.h - yuza.get_height()) // 2))

    def matnlarni_chiz(self):
        yorqin = S.RANGLAR[self.sozlama["rang"]]["yorqin"]
        chegara = tuple(int(c * 0.4) for c in yorqin)

        if self.rejim == "katta":
            sarlavha = self.shrift_sarlavha.render("J . A . R . V . I . S", True,
                                                   tuple(int(c * 0.7) for c in yorqin))
            self.ekran.blit(sarlavha, ((self.eni - sarlavha.get_width()) // 2, 10))

        panel = self.panel
        pygame.draw.rect(self.ekran, PANEL, panel, border_radius=12)
        pygame.draw.rect(self.ekran, chegara, panel, 1, border_radius=12)
        y = panel.y + 8
        if self.siz_matni:
            for qator in matnni_bol(self.shrift, f"{self.y('siz')}: " + self.siz_matni,
                                    panel.w - 20, 2):
                self.matn_chiz(qator, self.shrift, (200, 210, 225), (panel.x + 10, y))
                y += 19
        if self.jarvis_matni:
            for qator in matnni_bol(self.shrift, "Jarvis: " + self.jarvis_matni, panel.w - 20,
                                    max(1, (panel.bottom - y - 4) // 19)):
                self.matn_chiz(qator, self.shrift, yorqin, (panel.x + 10, y))
                y += 19

        self.maydon_chiz(self.yozuv_joyi, "yozuv", self.y("yozing"))

        # holat yozuvi
        yuza = self.shrift_kichik.render(self.y(self.holat), True, tuple(int(c * 0.75) for c in yorqin))
        fon = pygame.Rect(0, 0, yuza.get_width() + 16, 20)
        fon.center = (self.eni // 2, self.holat_y)
        pygame.draw.rect(self.ekran, PANEL, fon, border_radius=10)
        self.ekran.blit(yuza, (fon.x + 8, fon.y + 3))

        # yopish (×) va sozlamalar (⚙) tugmalari
        yx = self.yopish_joyi
        pygame.draw.circle(self.ekran, PANEL, yx.center, 11)
        c = yx.center
        pygame.draw.line(self.ekran, (150, 170, 200), (c[0] - 4, c[1] - 4), (c[0] + 4, c[1] + 4), 2)
        pygame.draw.line(self.ekran, (150, 170, 200), (c[0] - 4, c[1] + 4), (c[0] + 4, c[1] - 4), 2)
        sz = self.sozlama_joyi.center
        pygame.draw.circle(self.ekran, PANEL, sz, 11)
        for i in range(8):                              # tishli g'ildirak
            b = i * math.pi / 4
            pygame.draw.line(self.ekran, (150, 170, 200), (sz[0] + math.cos(b) * 4, sz[1] + math.sin(b) * 4),
                             (sz[0] + math.cos(b) * 8, sz[1] + math.sin(b) * 8), 2)
        pygame.draw.circle(self.ekran, (150, 170, 200), sz, 5, 2)

        if self.sozlama_ochiq:
            self.sozlamalarni_chiz(yorqin, chegara)

    def sozlamalarni_chiz(self, yorqin, chegara):
        oyna = pygame.Rect(10, self.boyi - 262, self.eni - 20, 252)
        pygame.draw.rect(self.ekran, PANEL, oyna, border_radius=12)
        pygame.draw.rect(self.ekran, yorqin, oyna, 1, border_radius=12)
        self.tugmalar = []
        x0, y = oyna.x + 12, oyna.y + 10
        self.matn_chiz(self.y("sozlamalar"), self.shrift_sarlavha, yorqin, (x0, y))
        y += 26

        def tugmalar_qatori(kalit, variantlar, y):
            self.matn_chiz(self.y(kalit), self.shrift_kichik, (140, 160, 190), (x0, y))
            y += 17
            eni = (oyna.w - 24 - 6 * (len(variantlar) - 1)) // len(variantlar)
            for i, (qiymat, yozuv) in enumerate(variantlar):
                joy = pygame.Rect(x0 + i * (eni + 6), y, eni, 26)
                tanlangan = self.sozlama[kalit] == qiymat
                pygame.draw.rect(self.ekran, chegara if tanlangan else (16, 24, 40), joy, border_radius=8)
                pygame.draw.rect(self.ekran, yorqin if tanlangan else (40, 60, 90), joy, 1, border_radius=8)
                yuza = self.shrift_kichik.render(yozuv, True, (230, 240, 250))
                self.ekran.blit(yuza, (joy.centerx - yuza.get_width() // 2,
                                       joy.centery - yuza.get_height() // 2))
                self.tugmalar.append((joy, kalit, qiymat))
            return y + 34

        y = tugmalar_qatori("ovoz", [("ayol", self.y("ayol")), ("erkak", self.y("erkak"))], y)
        y = tugmalar_qatori("til", [(k, v["nomi"]) for k, v in S.TILLAR.items()], y)

        self.matn_chiz(self.y("rang"), self.shrift_kichik, (140, 160, 190), (x0, y))
        y += 17
        for i, (kalit, mavzu) in enumerate(S.RANGLAR.items()):
            markaz = (x0 + 13 + i * 36, y + 13)
            pygame.draw.circle(self.ekran, mavzu["yorqin"], markaz, 11)
            if self.sozlama["rang"] == kalit:
                pygame.draw.circle(self.ekran, (240, 245, 255), markaz, 14, 2)
            self.tugmalar.append((pygame.Rect(markaz[0] - 14, markaz[1] - 14, 28, 28), "rang", kalit))
        y += 34

        self.matn_chiz(self.y("ism"), self.shrift_kichik, (140, 160, 190), (x0, y))
        y += 17
        ism_joyi = pygame.Rect(x0, y, oyna.w - 24, 30)
        self.maydon_chiz(ism_joyi, "ism", self.sozlama["ism"])
        self.tugmalar.append((ism_joyi, "ism", None))

    def ishga_tushir(self):
        soat = pygame.time.Clock()
        boshlanish = time.time()
        while self.ishlayapti:
            dt = soat.tick(FPS) / 1000
            self.xabarlarni_ol()
            self.hodisalar()
            self.holatni_yangila(dt)
            self.ekran.fill(FON)
            pygame.draw.circle(self.ekran, DISK, self.markaz, self.disk_r)
            self.shar_chiz(time.time() - boshlanish)
            self.matnlarni_chiz()
            pygame.display.flip()
        pygame.quit()
