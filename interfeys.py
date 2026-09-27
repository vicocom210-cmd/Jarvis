"""
Jarvis'ning ko'rinishi: minglab nuqtalardan iborat aylanuvchi 3D shar.

Bu oyna ASOSIY thread'da ishlaydi. Tinglash va buyruqlar boshqa thread'da.
Ular bir-biri bilan ikkita navbat (queue) orqali gaplashadi:
  ui_navbat     — Jarvis -> oyna:  ("holat", "kutish"), ("siz", matn), ("jarvis", matn),
                                    ("ovoz", balandliklar, boshlanish_vaqti), ("yopil",)
  kirish_navbat — oyna -> Jarvis:  ("yozuv", matn)  — pastdagi maydonga yozilgan buyruq
"""
import math
import os
import queue
import random
import time

import pygame

ENI, BOYI = 340, 500          # oyna o'lchami
SHAR_MARKAZI = (ENI // 2, 170)
SHAR_RADIUSI = 95
NUQTALAR_SONI = 2200
FPS = 40
FON = (0, 0, 0)               # shu rang shaffof bo'ladi (Windows)
PANEL = (10, 16, 28)

# Har bir holat: rang, kattalik, aylanish tezligi, yorqinlik
HOLATLAR = {
    "kutish":   {"rang": (40, 95, 210),  "kattalik": 0.80, "tezlik": 0.25, "yorqinlik": 0.55},
    "tinglash": {"rang": (70, 205, 255), "kattalik": 1.00, "tezlik": 0.95, "yorqinlik": 1.00},
    "o'ylash":  {"rang": (60, 150, 255), "kattalik": 0.92, "tezlik": 1.60, "yorqinlik": 0.85},
    "gapirish": {"rang": (90, 215, 255), "kattalik": 0.95, "tezlik": 0.60, "yorqinlik": 1.00},
    "shazam":   {"rang": (175, 80, 255), "kattalik": 1.00, "tezlik": 1.20, "yorqinlik": 1.00},
}


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


def nuqta_rasmlari():
    """Oldindan chizilgan yumshoq porlovchi nuqtalar (kul rangda; keyin bo'yaladi).
    [kattalik][yorqinlik] — har kadrda aylana chizishdan ancha tez."""
    rasmlar = []
    for rad in (1.6, 2.3, 3.2):
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


def yadro_nuri(radius):
    """Shar ichidagi yumshoq yorug'lik (radial gradient)."""
    s = pygame.Surface((radius * 2, radius * 2))
    s.fill((0, 0, 0))
    for r in range(radius, 0, -2):
        q = int(70 * (1 - r / radius) ** 2)
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
    def __init__(self, ui_navbat, kirish_navbat):
        self.ui_navbat = ui_navbat
        self.kirish_navbat = kirish_navbat

        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.user32.SetProcessDPIAware()     # xira bo'lmasin
            except Exception:
                pass
        pygame.display.init()
        pygame.font.init()
        chap, tepa, ong, past = ish_maydoni()
        os.environ["SDL_VIDEO_WINDOW_POS"] = f"{ong - ENI - 16},{past - BOYI - 16}"
        self.ekran = pygame.display.set_mode((ENI, BOYI), pygame.NOFRAME)
        pygame.display.set_caption("Jarvis")
        pygame.display.set_icon(self._ikonka())
        windows_sozla()
        pygame.key.start_text_input()

        self.nuqtalar = fibonacci_shar(NUQTALAR_SONI)
        self.rasmlar = nuqta_rasmlari()
        self.yadro = yadro_nuri(SHAR_RADIUSI)
        self.shar_qatlami = pygame.Surface((ENI, 340))
        self.shrift = pygame.font.SysFont("segoeui,arial", 15)
        self.shrift_kichik = pygame.font.SysFont("segoeui,arial", 12)

        self.holat = "kutish"
        h = HOLATLAR["kutish"]
        self.rang, self.kattalik = h["rang"], h["kattalik"]
        self.tezlik, self.yorqinlik = h["tezlik"], h["yorqinlik"]
        self.burchak = 0.0
        self.ovoz = ([], 0.0)             # (balandliklar ro'yxati, boshlanish vaqti)
        self.daraja = 0.0                 # hozirgi ovoz balandligi 0..1

        self.siz_matni = ""
        self.jarvis_matni = "Salom! Jarvis deb chaqiring yoki pastga yozing."
        self.yozuv = ""
        self.yozuv_faol = False
        self.surish = None                # sichqoncha bilan surish boshlangan joy
        self.ishlayapti = True

        self.yozuv_joyi = pygame.Rect(14, BOYI - 50, ENI - 28, 36)
        self.yopish_joyi = pygame.Rect(ENI - 30, 6, 24, 24)

    def _ikonka(self):
        s = pygame.Surface((32, 32))
        s.fill((0, 0, 0))
        pygame.draw.circle(s, (30, 90, 200), (16, 16), 14)
        pygame.draw.circle(s, (90, 200, 255), (16, 16), 9)
        pygame.draw.circle(s, (220, 245, 255), (13, 12), 3)
        return s

    # ----- navbatdan kelgan xabarlar -----
    def xabarlarni_ol(self):
        while True:
            try:
                xabar = self.ui_navbat.get_nowait()
            except queue.Empty:
                return
            tur = xabar[0]
            if tur == "holat" and xabar[1] in HOLATLAR:
                self.holat = xabar[1]
            elif tur == "siz":
                self.siz_matni = xabar[1]
            elif tur == "jarvis":
                self.jarvis_matni = xabar[1]
            elif tur == "ovoz":
                self.ovoz = (xabar[1], xabar[2])
            elif tur == "yopil":
                self.ishlayapti = False

    # ----- sichqoncha va klaviatura -----
    def hodisalar(self):
        for h in pygame.event.get():
            if h.type == pygame.QUIT:
                self.ishlayapti = False
            elif h.type == pygame.MOUSEBUTTONDOWN and h.button == 1:
                if self.yopish_joyi.collidepoint(h.pos):
                    self.ishlayapti = False
                elif self.yozuv_joyi.collidepoint(h.pos):
                    self.yozuv_faol = True
                else:
                    self.yozuv_faol = False
                    mx, my = sichqoncha_ekranda()
                    ox, oy = oyna_joyi()
                    self.surish = (mx - ox, my - oy)
            elif h.type == pygame.MOUSEBUTTONUP and h.button == 1:
                self.surish = None
            elif h.type == pygame.MOUSEMOTION and self.surish:
                mx, my = sichqoncha_ekranda()
                oynani_sur(mx - self.surish[0], my - self.surish[1])
            elif h.type == pygame.TEXTINPUT and self.yozuv_faol:
                if len(self.yozuv) < 200:
                    self.yozuv += h.text
            elif h.type == pygame.KEYDOWN and self.yozuv_faol:
                if h.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    matn = self.yozuv.strip()
                    if matn:
                        self.kirish_navbat.put(("yozuv", matn, time.time()))
                    self.yozuv = ""
                elif h.key == pygame.K_BACKSPACE:
                    self.yozuv = self.yozuv[:-1]
                elif h.key == pygame.K_ESCAPE:
                    self.yozuv, self.yozuv_faol = "", False
                elif h.key == pygame.K_v and h.mod & pygame.KMOD_CTRL:
                    try:
                        import pyperclip
                        self.yozuv += pyperclip.paste().replace("\n", " ")[:200]
                    except Exception:
                        pass

    # ----- chizish -----
    def holatni_yangila(self, dt):
        maqsad = HOLATLAR[self.holat]
        t = min(1.0, dt * 4)                  # yangi holatga silliq o'tish
        self.rang = rang_aralashtir(self.rang, maqsad["rang"], t)
        self.kattalik = aralashtir(self.kattalik, maqsad["kattalik"], t)
        self.tezlik = aralashtir(self.tezlik, maqsad["tezlik"], t)
        self.yorqinlik = aralashtir(self.yorqinlik, maqsad["yorqinlik"], t)
        self.burchak += self.tezlik * dt

        balandliklar, boshlandi = self.ovoz
        yangi = 0.0
        if balandliklar:
            i = int((time.time() - boshlandi) * 30)
            if 0 <= i < len(balandliklar):
                yangi = balandliklar[i]
        # tez ko'tariladi, sekin tushadi — pulsatsiya tabiiyroq ko'rinadi
        self.daraja = yangi if yangi > self.daraja else aralashtir(self.daraja, yangi, min(1, dt * 8))

    def shar_chiz(self, vaqt):
        q = self.shar_qatlami
        q.fill((0, 0, 0))
        cx, cy = ENI // 2, 170
        R = SHAR_RADIUSI * self.kattalik
        ca, sa = math.cos(self.burchak), math.sin(self.burchak)
        egilish = 0.35
        ce, se = math.cos(egilish), math.sin(egilish)
        daraja = self.daraja
        nafas_t = vaqt * 1.6
        tolqin_t = vaqt * 9
        rasmlar = self.rasmlar
        ro_yxat = []
        sin = math.sin
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

        yr = int(R * 1.1)
        yadro = pygame.transform.smoothscale(self.yadro, (yr * 2, yr * 2))
        q.blit(yadro, (cx - yr, cy - yr), special_flags=pygame.BLEND_ADD)
        q.blits([(r, j, None, pygame.BLEND_ADD) for r, j in ro_yxat], doreturn=False)

        # Iron Man uslubidagi aylanuvchi yoylar
        halqa = int(SHAR_RADIUSI * 1.35)
        to_rt = pygame.Rect(cx - halqa, cy - halqa, halqa * 2, halqa * 2)
        a = vaqt * 0.6
        for boshi, uzunligi in ((0, 1.2), (2.2, 0.6), (3.6, 1.5)):
            pygame.draw.arc(q, (90, 90, 90), to_rt, a + boshi, a + boshi + uzunligi, 2)
        to_rt2 = to_rt.inflate(14, 14)
        for boshi in (0.5, 2.6, 4.7):
            pygame.draw.arc(q, (45, 45, 45), to_rt2, -a * 0.7 + boshi, -a * 0.7 + boshi + 0.8, 1)

        # kul rangdagi rasmni holat rangiga bo'yaymiz
        q.fill(tuple(int(c) for c in self.rang), special_flags=pygame.BLEND_MULT)
        self.ekran.blit(q, (0, 0), special_flags=pygame.BLEND_ADD)

    def matnlarni_chiz(self):
        panel = pygame.Rect(10, 335, ENI - 20, 100)
        pygame.draw.rect(self.ekran, PANEL, panel, border_radius=12)
        pygame.draw.rect(self.ekran, (30, 60, 100), panel, 1, border_radius=12)
        y = panel.y + 8
        if self.siz_matni:
            for qator in matnni_bol(self.shrift, "Siz: " + self.siz_matni, panel.w - 20, 2):
                self.ekran.blit(self.shrift.render(qator, True, (200, 210, 225)), (panel.x + 10, y))
                y += 19
        for qator in matnni_bol(self.shrift, "Jarvis: " + self.jarvis_matni, panel.w - 20,
                                max(1, (panel.bottom - y - 4) // 19)):
            self.ekran.blit(self.shrift.render(qator, True, (110, 215, 255)), (panel.x + 10, y))
            y += 19

        # yozish maydoni
        m = self.yozuv_joyi
        pygame.draw.rect(self.ekran, PANEL, m, border_radius=10)
        pygame.draw.rect(self.ekran, (70, 170, 255) if self.yozuv_faol else (30, 60, 100),
                         m, 1, border_radius=10)
        if self.yozuv or self.yozuv_faol:
            korinadi = self.yozuv
            while self.shrift.size(korinadi)[0] > m.w - 24 and korinadi:
                korinadi = korinadi[1:]
            kursor = "|" if self.yozuv_faol and int(time.time() * 2) % 2 == 0 else ""
            yuza = self.shrift.render(korinadi + kursor, True, (225, 235, 245))
        else:
            yuza = self.shrift.render("Shu yerga yozing va Enter bosing…", True, (90, 110, 140))
        self.ekran.blit(yuza, (m.x + 12, m.y + (m.h - yuza.get_height()) // 2))

        # yopish tugmasi
        yx = self.yopish_joyi
        pygame.draw.circle(self.ekran, PANEL, yx.center, 11)
        c = yx.center
        pygame.draw.line(self.ekran, (150, 170, 200), (c[0] - 4, c[1] - 4), (c[0] + 4, c[1] + 4), 2)
        pygame.draw.line(self.ekran, (150, 170, 200), (c[0] - 4, c[1] + 4), (c[0] + 4, c[1] - 4), 2)

        nom = {"kutish": "Kutish rejimi — Jarvis deng", "tinglash": "Tinglayapman…",
               "o'ylash": "Bajaryapman…", "gapirish": "Gapiryapman…",
               "shazam": "Musiqani tinglayapman…"}[self.holat]
        yuza = self.shrift_kichik.render(nom, True, (80, 130, 180))
        fon = pygame.Rect(0, 0, yuza.get_width() + 16, 20)
        fon.center = (ENI // 2, 318)
        pygame.draw.rect(self.ekran, PANEL, fon, border_radius=10)
        self.ekran.blit(yuza, (fon.x + 8, fon.y + 3))

    def ishga_tushir(self):
        soat = pygame.time.Clock()
        boshlanish = time.time()
        while self.ishlayapti:
            dt = soat.tick(FPS) / 1000
            self.xabarlarni_ol()
            self.hodisalar()
            self.holatni_yangila(dt)
            self.ekran.fill(FON)
            pygame.draw.circle(self.ekran, (5, 9, 18), SHAR_MARKAZI, 142)
            self.shar_chiz(time.time() - boshlanish)
            self.matnlarni_chiz()
            pygame.display.flip()
        pygame.quit()
