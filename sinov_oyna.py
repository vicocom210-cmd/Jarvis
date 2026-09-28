"""
Windows'da (GitHub Actions) Jarvis oynasini haqiqatan ochib tekshiradi:
  - oyna barcha ilovalar USTIDA turadimi (WS_EX_TOPMOST)
  - kutishda — ekran tepasining o'rtasida, 'Jarvis'da — ekran o'rtasida, bosilganda yonga surilmaydimi
Ishga tushirish: python sinov_oyna.py   (xato bo'lsa — chiqish kodi 1)
"""
import os
import queue
import sys
import time

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
import pygame  # noqa: E402

import interfeys  # noqa: E402

ui = queue.Queue()
o = interfeys.Oyna(ui, queue.Queue(), None)


def kadr(n=15):
    for _ in range(n):
        o.xabarlarni_ol()
        o.hodisalar()
        o.holatni_yangila(0.03)
        o.ekran.fill(interfeys.FON)
        o.shar_chiz(time.time())
        o.matnlarni_chiz(0.03)
        pygame.display.flip()
        time.sleep(0.02)


xatolar = []


def tekshir(nomi, rejim):
    kadr()
    joy = interfeys.oyna_joyi()
    kerak = o.rejim_joyi(rejim)
    ustida = bool(interfeys._u32().GetWindowLongW(interfeys._hwnd(), -20) & 0x8)   # WS_EX_TOPMOST
    olcham = o.ekran.get_size()
    ok = o.rejim == rejim and joy == kerak and ustida
    print(f"{'OK ' if ok else 'XATO'} {nomi}: rejim={o.rejim} joy={joy} kerak={kerak} "
          f"o'lcham={olcham} ustida={ustida}")
    if not ok:
        xatolar.append(nomi)


print("Ekran ish maydoni:", interfeys.ish_maydoni(), "| 64-bit:", sys.maxsize > 2 ** 32)
tekshir("kutish — tepada kichik shar", "mini")
o.mini_yozish = True
tekshir("sharni bosdi — yozish joyi (yonga surilmasin)", "mini_yoz")
ui.put(("holat", "tinglash"))
tekshir("'Jarvis' — o'rtada katta", "katta")
ui.put(("holat", "kutish"))
o.kutish_boshlandi = time.time() - 5
o.mini_yozish = False
tekshir("tugadi — yana tepada", "mini")
pygame.quit()
if xatolar:
    print("Muammolar:", xatolar)
    sys.exit(1)
print("Hammasi joyida.")
