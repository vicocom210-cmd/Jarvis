"""
Uy kameralari (Hikvision va boshqa IP kameralar) bilan ishlash.

  Rasm olish  — ISAPI orqali (kameradan to'g'ridan-to'g'ri tayyor JPG, tez va yengil):
                http://IP/ISAPI/Streaming/channels/101/picture   (Digest parol bilan)
                Bo'lmasa — RTSP videodan bitta kadr (OpenCV).
  Kuzatish    — RTSP'ning yengil oqimi (102) dan harakatni sezadi va rasm bilan xabar beradi.

Hikvision manzillari:
  rtsp://login:parol@IP:554/Streaming/Channels/101   — asosiy oqim (sifatli)
  rtsp://login:parol@IP:554/Streaming/Channels/102   — yengil oqim (kuzatish uchun)
  NVR (videoregistrator)da 2-kamera: 201/202, 3-kamera: 301/302 ...
"""
import datetime
import os
import threading
import time
import urllib.parse
import urllib.request

import sozlamalar

PAPKA = os.path.join(sozlamalar.PAPKA, "kamera")      # olingan rasmlar (chatda ko'rinadi)


def _kanal(k, yengil=False):
    """101 -> 101 (asosiy) yoki 102 (yengil). Foydalanuvchi 1 yozsa ham 101 deb tushunamiz."""
    kanal = str(k.get("kanal") or "101").strip()
    if kanal.isdigit() and len(kanal) <= 2:          # "1" -> "101", "3" -> "301"
        kanal = f"{int(kanal)}01"
    if yengil and kanal.endswith("01"):
        kanal = kanal[:-2] + "02"
    return kanal


def rtsp_manzil(k, yengil=False):
    login = urllib.parse.quote(str(k.get("login") or "admin"), safe="")
    parol = urllib.parse.quote(str(k.get("parol") or ""), safe="")     # @ # : kabi belgilar buzmasin
    port = int(k.get("rtsp_port") or 554)
    return f"rtsp://{login}:{parol}@{k['ip']}:{port}/Streaming/Channels/{_kanal(k, yengil)}"


def _yangi_yol(k, qoshimcha=""):
    os.makedirs(PAPKA, exist_ok=True)
    nom = "".join(c for c in str(k.get("nom") or "kamera") if c.isalnum()) or "kamera"
    return os.path.join(PAPKA, f"{nom}-{datetime.datetime.now():%Y%m%d-%H%M%S}{qoshimcha}.jpg")


def _isapi_rasm(k, timeout=8):
    """Hikvision ISAPI: kameradan tayyor JPG. Baytlar yoki None."""
    port = int(k.get("http_port") or 80)
    asos = f"http://{k['ip']}" + ("" if port == 80 else f":{port}")
    parollar = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    parollar.add_password(None, asos, str(k.get("login") or "admin"), str(k.get("parol") or ""))
    ochuvchi = urllib.request.build_opener(urllib.request.HTTPDigestAuthHandler(parollar),
                                           urllib.request.HTTPBasicAuthHandler(parollar))
    for yol in (f"/ISAPI/Streaming/channels/{_kanal(k)}/picture",
                f"/Streaming/channels/{_kanal(k)}/picture"):             # eski proshivkalar
        try:
            with ochuvchi.open(asos + yol, timeout=timeout) as javob:
                malumot = javob.read()
                if malumot[:2] == b"\xff\xd8":                         # haqiqatan JPG
                    return malumot
        except urllib.error.HTTPError as xato:
            if xato.code == 401:
                raise PermissionError("Login yoki parol noto'g'ri") from xato
        except OSError:
            continue
    return None


def _rtsp_kadr(k, yengil=False, timeout=12):
    """RTSP videodan bitta kadr (OpenCV). numpy rasm yoki None."""
    try:
        import cv2
    except ImportError:
        return None
    os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")   # barqarorroq
    video = cv2.VideoCapture(rtsp_manzil(k, yengil), cv2.CAP_FFMPEG)
    try:
        tugash = time.time() + timeout
        while time.time() < tugash:
            ok, kadr = video.read()
            if ok and kadr is not None:
                return kadr
            time.sleep(0.2)
    finally:
        video.release()
    return None


def rasm_ol(k):
    """Kameradan rasm oladi va saqlaydi. (yo'l, None) yoki (None, xato matni)."""
    if not k.get("ip"):
        return None, "Kamera IP manzili kiritilmagan"
    try:
        malumot = _isapi_rasm(k)
    except PermissionError as xato:
        return None, str(xato)
    yol = _yangi_yol(k)
    if malumot:
        with open(yol, "wb") as f:
            f.write(malumot)
        return yol, None
    kadr = _rtsp_kadr(k)
    if kadr is not None:
        import cv2
        cv2.imwrite(yol, kadr)
        return yol, None
    return None, (f"{k['ip']} kameraga ulanib bo'lmadi. Kamera va kompyuter bitta tarmoqdami, "
                  "IP manzil to'g'rimi, tekshiring")


# ---------- HARAKATNI KUZATISH ----------
class Kuzatuvchi:
    """Kameraning yengil oqimidan harakatni sezadi. Harakat bo'lsa — rasm bilan xabar beradi
    (har 60 soniyada ko'pi bilan bir marta, xabarlar ko'payib ketmasin)."""

    def __init__(self, k, harakat_bor, holat_xabari=print, sezgirlik=0.012, tanaffus=60):
        self.k = k
        self.harakat_bor = harakat_bor            # (kamera, rasm_yoli) -> None
        self.holat_xabari = holat_xabari
        self.sezgirlik = sezgirlik                # kadrning qancha qismi o'zgarsa — harakat
        self.tanaffus = tanaffus
        self.ishlasin = True
        self.thread = threading.Thread(target=self._ishla, daemon=True)
        self.thread.start()

    def toxtat(self):
        self.ishlasin = False

    def _ishla(self):
        try:
            import cv2
        except ImportError:
            self.holat_xabari("Kuzatish uchun opencv-python kerak")
            return
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
        oxirgi_xabar = 0.0
        while self.ishlasin:
            video = cv2.VideoCapture(rtsp_manzil(self.k, yengil=True), cv2.CAP_FFMPEG)
            if not video.isOpened():
                self.holat_xabari(f"{self.k.get('nom', 'Kamera')}: ulanib bo'lmadi, 20 soniyadan keyin qayta urinaman")
                video.release()
                for _ in range(20):
                    if not self.ishlasin:
                        return
                    time.sleep(1)
                continue
            fon = None
            oxirgi_tahlil = 0.0
            xatolar = 0
            while self.ishlasin:
                ok, kadr = video.read()                 # oqimni doim o'qiymiz (kechikib qolmasin)
                if not ok:
                    xatolar += 1
                    if xatolar > 50:
                        break                           # uzildi — qayta ulanamiz
                    time.sleep(0.1)
                    continue
                xatolar = 0
                if time.time() - oxirgi_tahlil < 0.4:   # sekundiga ~2,5 marta tahlil — CPU tejaladi
                    continue
                oxirgi_tahlil = time.time()
                ulush, fon = harakat_ulushi(kadr, fon, cv2)
                if ulush >= self.sezgirlik and time.time() - oxirgi_xabar > self.tanaffus:
                    oxirgi_xabar = time.time()
                    yol = _yangi_yol(self.k, "-harakat")
                    cv2.imwrite(yol, kadr)
                    try:
                        self.harakat_bor(self.k, yol)
                    except Exception as xato:
                        print(f"(Harakat xabari xatosi: {xato})")
            video.release()


def harakat_ulushi(kadr, fon, cv2):
    """Kadrning qancha qismi (0..1) o'zgardi. Fon asta yangilanadi (yorug'lik o'zgarishi,
    shamolda barg qimirlashi kabi mayda narsalar harakat hisoblanmasin)."""
    kulrang = cv2.cvtColor(cv2.resize(kadr, (320, 180)), cv2.COLOR_BGR2GRAY)
    kulrang = cv2.GaussianBlur(kulrang, (21, 21), 0)
    if fon is None:
        return 0.0, kulrang.astype("float32")
    farq = cv2.absdiff(kulrang, cv2.convertScaleAbs(fon))
    _, niqob = cv2.threshold(farq, 25, 255, cv2.THRESH_BINARY)
    niqob = cv2.dilate(niqob, None, iterations=2)
    cv2.accumulateWeighted(kulrang, fon, 0.05)
    return cv2.countNonZero(niqob) / niqob.size, fon
