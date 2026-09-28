"""
PIN kodni taxmin qilib topishga qarshi himoya.

Telefon ilovasi (Wi-Fi) va bulut ko'prigi (internet) buyruqlarni PIN bilan qabul qiladi.
4 raqamli PIN — atigi 10 000 variant: kimdir hammasini ketma-ket sinab ko'rishi mumkin
(bu esa endi ESHIKNI ochishi mumkin). Shuning uchun:
  - 10 daqiqa ichida 5 marta noto'g'ri PIN — o'sha manba 15 daqiqaga bloklanadi
  - bloklanganda egasiga (Telegram) xabar boriladi
"""
import threading
import time

URINISHLAR = 5            # shuncha noto'g'ri urinish ...
OYNA = 10 * 60            # ... shu vaqt ichida bo'lsa
BLOK = 15 * 60            # shuncha vaqtga bloklanadi

_qulf = threading.Lock()
_xatolar = {}             # manba -> [vaqt, ...]
_bloklangan = {}          # manba -> qachongacha
ogohlantir = None         # (matn) -> None — jarvis.py beradi (Telegram'ga)


def tekshir(manba, pin, togri_pin):
    """(ok, xato_matni). manba — IP manzil yoki 'bulut'."""
    hozir = time.time()
    with _qulf:
        gacha = _bloklangan.get(manba, 0)
        if gacha > hozir:
            return False, f"Ko'p marta noto'g'ri PIN. {int((gacha - hozir) // 60) + 1} daqiqadan keyin urinib ko'ring"
        if str(pin) == str(togri_pin):
            _xatolar.pop(manba, None)
            return True, ""
        royxat = [t for t in _xatolar.get(manba, []) if hozir - t < OYNA] + [hozir]
        _xatolar[manba] = royxat
        if len(royxat) >= URINISHLAR:
            _bloklangan[manba] = hozir + BLOK
            _xatolar.pop(manba, None)
            xabar = (f"⚠️ Jarvis: {manba} dan {URINISHLAR} marta noto'g'ri PIN kiritildi — "
                     f"{BLOK // 60} daqiqaga bloklandi. Bu siz bo'lmasangiz, PIN'ni almashtiring.")
        else:
            xabar = None
    if xabar:
        print(xabar)
        if ogohlantir:
            try:
                ogohlantir(xabar)
            except Exception:
                pass
    return False, "PIN noto'g'ri"


def tozala():
    with _qulf:
        _xatolar.clear()
        _bloklangan.clear()
