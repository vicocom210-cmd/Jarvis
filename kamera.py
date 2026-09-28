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
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request


def rasmlar_papkasi():
    """Windows'ning "Rasmlar" (Pictures) papkasi — OneDrive'ga ko'chirilgan bo'lsa ham to'g'ri topadi."""
    if os.name == "nt":
        import ctypes
        joy = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x27, None, 0, joy) == 0:   # CSIDL_MYPICTURES
            return joy.value
    return os.path.join(os.path.expanduser("~"), "Pictures")


# Kamera rasmlari: Rasmlar\Jarvis\Kamera\2026-09-28\Hovli-....jpg (ish stolini to'ldirmaydi)
PAPKA = os.path.join(rasmlar_papkasi(), "Jarvis", "Kamera")


def jarvis_rasm_yoli(bolim, nom):
    """Jarvis olgan boshqa rasmlar uchun: Rasmlar\Jarvis\<bolim>\<nom> (papka o'zi yaratiladi)."""
    papka = os.path.join(rasmlar_papkasi(), "Jarvis", bolim)
    os.makedirs(papka, exist_ok=True)
    return os.path.join(papka, nom)


def nisbiy(yol):
    """Chat uchun: kamera papkasiga nisbatan yo'l ('2026-09-28/Hovli-...jpg')."""
    try:
        return os.path.relpath(yol, PAPKA).replace(os.sep, "/")
    except ValueError:
        return os.path.basename(yol)


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
    hozir = datetime.datetime.now()
    papka = os.path.join(PAPKA, f"{hozir:%Y-%m-%d}")                 # har kun alohida papka
    os.makedirs(papka, exist_ok=True)
    nom = "".join(c for c in str(k.get("nom") or "kamera") if c.isalnum()) or "kamera"
    return os.path.join(papka, f"{nom}-{hozir:%H-%M-%S}-{hozir.microsecond // 1000:03d}{qoshimcha}.jpg")


class BloklanganXato(PermissionError):
    """Hikvision ko'p marta noto'g'ri paroldan keyin login'ni vaqtincha bloklaydi (odatda 30 daqiqa)."""


def _bloklanganmi(tana):
    """401/403 javobi ichida 'lock' / 'unlockTime' bo'lsa — blok. Qolgan daqiqalar (yoki 30) yoki None."""
    if not re.search(r"lock|unlockTime", tana, re.I) or \
            re.search(r"<lockStatus>\s*unlock\s*</lockStatus>", tana, re.I):
        return None
    son = re.search(r"<unlockTime>\s*(\d+)", tana)
    return max(1, round(int(son.group(1)) / 60)) if son else 30


def _isapi(k, yol, usul="GET", malumot=None, timeout=8):
    """Hikvision ISAPI so'rovi (Digest yoki Basic). (kod, baytlar). Parol bilan faqat BIR marta
    urinadi (urllib qayta-qayta urinib, kamerani bloklatib qo'ymasin) va xato javob matnini saqlaydi —
    unda 'bloklangan' belgisi bo'ladi."""
    port = int(k.get("http_port") or 80)
    asos = f"http://{k['ip']}" + ("" if port == 80 else f":{port}")
    login, parol = str(k.get("login") or "admin").strip(), str(k.get("parol") or "")
    sarlavha = {"Content-Type": "application/xml"} if malumot is not None else {}

    def yubor(auth=None):
        sorov = urllib.request.Request(asos + yol, data=malumot, method=usul, headers=dict(sarlavha))
        if auth:
            sorov.add_unredirected_header("Authorization", auth)
        try:
            with urllib.request.urlopen(sorov, timeout=timeout) as javob:
                return javob.status, javob.read(), javob.headers, sorov
        except urllib.error.HTTPError as xato:
            try:
                tana = xato.read()
            except Exception:
                tana = b""
            return xato.code, tana, xato.headers, sorov

    kod, tana, sarl, sorov = yubor()
    if kod != 401:
        return kod, tana
    chaqiriq = " ".join(sarl.get_all("WWW-Authenticate") or [])
    if _bloklanganmi(tana.decode("utf-8", "ignore")):
        return kod, tana
    if re.search(r"\bdigest\b", chaqiriq, re.I):
        qism = re.search(r"digest\s+(.*)", chaqiriq, re.I | re.S).group(1)
        chal = urllib.request.parse_keqv_list(filter(None, urllib.request.parse_http_list(qism)))
        parollar = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        parollar.add_password(None, asos, login, parol)
        imzo = urllib.request.HTTPDigestAuthHandler(parollar).get_authorization(sorov, chal)
        if not imzo:
            return kod, tana
        kod, tana, _, _ = yubor("Digest " + imzo)
    else:
        import base64
        kod, tana, _, _ = yubor("Basic " + base64.b64encode(f"{login}:{parol}".encode()).decode())
    return kod, tana


def _isapi_rasm(k, timeout=8):
    """Hikvision ISAPI: kameradan tayyor JPG. Baytlar yoki None.
    Parol xato — PermissionError, login bloklangan — BloklanganXato."""
    rad = None
    for yol in (f"/ISAPI/Streaming/channels/{_kanal(k)}/picture",
                f"/Streaming/channels/{_kanal(k)}/picture"):             # eski proshivkalar
        try:
            kod, malumot = _isapi(k, yol, timeout=timeout)
        except (OSError, ValueError):
            continue
        if kod == 200 and malumot[:2] == b"\xff\xd8":                   # haqiqatan JPG
            return malumot
        if kod in (401, 403):
            daqiqa = _bloklanganmi(malumot.decode("utf-8", "ignore"))
            if daqiqa:                                  # boshqa yo'lni sinamaymiz — blok uzayadi
                raise BloklanganXato(f"Kamera login'ni ~{daqiqa} daqiqaga BLOKLAGAN (ko'p marta noto'g'ri "
                                     "parol kiritilgan). Shuncha kuting yoki kamerani o'chirib-yoqing")
            if kod == 401:
                qoldi = re.search(r"<retryLoginTime>\s*(\d+)", malumot.decode("utf-8", "ignore"))
                raise PermissionError("Login yoki parol noto'g'ri" + (
                    f" (kamera bloklanishiga {qoldi.group(1)} ta urinish qoldi)" if qoldi else ""))
            rad = "Bu foydalanuvchiga rasm olishga ruxsat yo'q (HTTP 403)"
    if rad:
        raise PermissionError(rad)
    return None


PAROL_MASLAHAT = ("Bu kameraning paroli boshqasinikidan farq qilishi mumkin: brauzerda http://{ip} ni ochib, "
                  "shu login-parol bilan kirib ko'ring. Parol — kamera faollashtirilganda qo'yilgan parol yoki "
                  "kamera yorlig'idagi 6 ta katta harfli tasdiqlash kodi (Verification code). "
                  "To'g'ri parolni ✏️ tugmasi bilan kiriting")


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
    kirish_xato = None
    try:
        malumot = _isapi_rasm(k)
    except BloklanganXato as xato:
        return None, str(xato)                       # RTSP ham sinalsa — blok uzayadi
    except PermissionError as xato:
        malumot, kirish_xato = None, str(xato)       # ba'zi kameralarda ISAPI yopiq, RTSP ishlaydi
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
    if kirish_xato:
        return None, f"{kirish_xato}. " + PAROL_MASLAHAT.format(ip=k["ip"])
    return None, (f"{k['ip']} kameraga ulanib bo'lmadi. Kamera va kompyuter bitta tarmoqdami, "
                  "IP manzil to'g'rimi, tekshiring")


# ---------- HARAKATNI KUZATISH ----------
class Kuzatuvchi:
    """Kamerada ODAM paydo bo'lsa xabar beradi (shunchaki harakat emas).
    1) Arzon harakat tekshiruvi — kadr o'zgardimi;  2) o'zgargan bo'lsa neyron tarmoq (odam.py)
    u yerda odam bormi tekshiradi;  3) odam ketma-ket 2 kadrda ko'rinsa — rasm bilan xabar.
    Mushuk, barg, soya, yorug'lik — xabar bermaydi. Har kamera uchun 60 soniyada ko'pi bilan bir xabar."""

    def __init__(self, k, harakat_bor, holat_xabari=print, sezgirlik=0.012, tanaffus=60, odam_ishonch=0.55):
        self.k = k
        self.harakat_bor = harakat_bor            # (kamera, rasm_yoli, odamlar_soni) -> None
        self.odam_ishonch = odam_ishonch
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
        try:
            import odam
            aniqlagich = odam.OdamAniqlagich.ol()
        except Exception as xato:                  # model yo'q — eski usul (harakat)
            print(f"(Odamni aniqlash modeli yuklanmadi: {xato}) — harakat bo'yicha xabar beraman")
            aniqlagich = None
        oxirgi_xabar = 0.0
        muvaffaqiyatsiz, oxirgi_sabab = 0, None
        ketma = 0                                  # odam ketma-ket nechta kadrda ko'rindi
        while self.ishlasin:
            video = cv2.VideoCapture(rtsp_manzil(self.k, yengil=True), cv2.CAP_FFMPEG)
            if not video.isOpened():
                video.release()
                muvaffaqiyatsiz += 1
                kutish = min(20 * 2 ** (muvaffaqiyatsiz - 1), 600)     # 20s, 40s, 80s ... 10 daqiqagacha
                sabab = "ulanib bo'lmadi"
                try:
                    _isapi_rasm(self.k, timeout=5)      # sababini bilib olamiz (parolmi, tarmoqmi)
                except BloklanganXato as xato:
                    sabab, kutish = str(xato), 1800     # bloklangan — urinish blokni uzaytiradi
                except PermissionError as xato:
                    sabab, kutish = str(xato), max(kutish, 600)   # parol xato — tez-tez urinsak bloklaydi
                except Exception:
                    pass
                if sabab != oxirgi_sabab:               # bir xil xabarni qayta-qayta chiqarmaymiz
                    self.holat_xabari(f"{self.k.get('nom', 'Kamera')}: {sabab}. "
                                      f"{kutish // 60 or 1} daqiqadan keyin qayta urinaman")
                    oxirgi_sabab = sabab
                for _ in range(kutish):
                    if not self.ishlasin:
                        return
                    time.sleep(1)
                continue
            muvaffaqiyatsiz, oxirgi_sabab = 0, None
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
                if ulush < self.sezgirlik:
                    ketma = 0
                    continue
                if time.time() - oxirgi_xabar <= self.tanaffus:
                    continue
                if aniqlagich is None:
                    odamlar, belgilangan = [None], kadr
                else:
                    odamlar = aniqlagich.odamlar(kadr, self.odam_ishonch)
                    ketma = ketma + 1 if odamlar else 0
                    if ketma < 2:                       # bitta kadrdagi xato ko'rinish emas — ikkitasida
                        continue
                    import odam
                    belgilangan = odam.belgila(kadr, odamlar)
                oxirgi_xabar = time.time()
                ketma = 0
                yol = _yangi_yol(self.k, "-odam" if aniqlagich else "-harakat")
                cv2.imwrite(yol, belgilangan)
                try:
                    self.harakat_bor(self.k, yol, len(odamlar) if aniqlagich else 0)
                except Exception as xato:
                    print(f"(Ogohlantirish xatosi: {xato})")
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


# ---------- TARMOQDAN QIDIRISH (Hikvision SADP) ----------
SADP_GURUH, SADP_PORT = "239.255.255.250", 37020


def sadp_javobini_oqi(xml):
    """SADP javobi (XML) -> {ip, seriya, tur, http_port, faol} yoki None."""
    import re

    def ol(teg):
        m = re.search(rf"<{teg}>([^<]*)</{teg}>", xml)
        return m.group(1).strip() if m else ""
    if ol("Types").lower() == "inquiry" or not ol("IPv4Address"):
        return None                                  # bu bizning o'z so'rovimiz
    return {"ip": ol("IPv4Address"), "seriya": ol("DeviceSN"), "tur": ol("DeviceType") or ol("DeviceDescription"),
            "http_port": int(ol("HttpPort") or 80), "faol": ol("Activated").lower() != "false",
            "mac": ol("MAC")}


def sadp_qidir(soniya=3.0):
    """Shu tarmoqdagi Hikvision qurilmalarini topadi (IP'ni qo'lda qidirish shart emas)."""
    import socket
    import struct
    import uuid
    topilgan = {}
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("", SADP_PORT))
        s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                     struct.pack("4sl", socket.inet_aton(SADP_GURUH), socket.INADDR_ANY))
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        s.settimeout(0.5)
        sorov = (f'<?xml version="1.0" encoding="utf-8"?><Probe><Uuid>{str(uuid.uuid4()).upper()}</Uuid>'
                 "<Types>inquiry</Types></Probe>").encode()
        tugash = time.time() + soniya
        yuborildi = 0
        while time.time() < tugash:
            if yuborildi < 3:                        # UDP yo'qolishi mumkin — 3 marta so'raymiz
                s.sendto(sorov, (SADP_GURUH, SADP_PORT))
                yuborildi += 1
            try:
                malumot, _ = s.recvfrom(65535)
            except socket.timeout:
                continue
            q = sadp_javobini_oqi(malumot.decode("utf-8", "ignore"))
            if q:
                topilgan[q["ip"]] = q
    except OSError as xato:
        print(f"(Kamera qidiruvi xatosi: {xato})")
    finally:
        s.close()
    return list(topilgan.values())


# ---------- JONLI VIDEO ----------
def jonli_kadrlar(k, fps=8, yengil=True, ishlasin=lambda: True):
    """Kameraning jonli videosi — JPG kadrlar ketma-ketligi (chatda MJPEG sifatida ko'rinadi).
    RTSP ochilmasa — ISAPI rasmlaridan (sekundiga ~2 ta)."""
    try:
        import cv2
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
        video = cv2.VideoCapture(rtsp_manzil(k, yengil), cv2.CAP_FFMPEG)
    except ImportError:
        cv2, video = None, None
    if video is not None and video.isOpened():
        oraliq, oxirgi = 1.0 / fps, 0.0
        try:
            while ishlasin():
                ok, kadr = video.read()
                if not ok:
                    break
                if time.time() - oxirgi < oraliq:
                    continue                             # oqimni o'qib turamiz, lekin kamroq yuboramiz
                oxirgi = time.time()
                ok, jpg = cv2.imencode(".jpg", kadr, [cv2.IMWRITE_JPEG_QUALITY, 75])
                if ok:
                    yield jpg.tobytes()
        finally:
            video.release()
        return
    if video is not None:
        video.release()
    while ishlasin():                                    # zaxira: ISAPI rasmlari
        try:
            jpg = _isapi_rasm(k, timeout=5)
        except PermissionError:
            return
        if not jpg:
            return
        yield jpg
        time.sleep(0.5)


# ---------- ESHIKNI OCHISH ----------
def _isapi_put(k, yol, xml, timeout=6):
    kod, tana = _isapi(k, yol, "PUT", xml.encode("utf-8"), timeout=timeout)
    if kod >= 400:
        raise urllib.error.HTTPError(yol, kod, tana.decode("utf-8", "ignore")[:200], None, None)
    return kod, tana.decode("utf-8", "ignore")


def _eshik_domofon(k, raqam):
    """Domofon / kirish nazorati (DS-KV, DS-K...): masofadan eshikni ochish."""
    kod, tana = _isapi_put(k, f"/ISAPI/AccessControl/RemoteControl/door/{raqam}",
                           "<RemoteControlDoor><cmd>open</cmd></RemoteControlDoor>")
    return kod == 200 and ("<statusCode>1</statusCode>" in tana or "OK" in tana or not tana.strip())


def _eshik_rele(k, raqam, soniya=3):
    """Kameraning rele (alarm output) chiqishiga ulangan qulf: 'high' -> kutish -> 'low'."""
    yol = f"/ISAPI/System/IO/outputs/{raqam}/trigger"
    kod, _ = _isapi_put(k, yol, "<IOPortData><outputState>high</outputState></IOPortData>")
    if kod != 200:
        return False

    def qaytar():
        time.sleep(soniya)
        try:
            _isapi_put(k, yol, "<IOPortData><outputState>low</outputState></IOPortData>")
        except OSError:
            pass
    threading.Thread(target=qaytar, daemon=True).start()
    return True


ESHIK_USULLARI = {"domofon": _eshik_domofon, "rele": _eshik_rele}


def eshik_och(k):
    """Eshikni ochadi. (ok, xabar, ishlagan_usul). Avval saqlangan usul, bo'lmasa ikkalasi sinaladi."""
    raqam = int(k.get("eshik_raqami") or 1)
    usullar = [k["eshik_usul"]] if k.get("eshik_usul") in ESHIK_USULLARI else ["domofon", "rele"]
    oxirgi = "Eshikni ochish buyrug'i qabul qilinmadi"
    for usul in usullar:
        try:
            if ESHIK_USULLARI[usul](k, raqam):
                return True, "Eshik ochildi", usul
        except urllib.error.HTTPError as xato:
            daqiqa = _bloklanganmi(str(xato.msg or "")) if xato.code in (401, 403) else None
            oxirgi = (f"Qurilma login'ni ~{daqiqa} daqiqaga bloklagan (ko'p marta noto'g'ri parol)" if daqiqa
                      else "Login yoki parol noto'g'ri" if xato.code == 401 else f"Qurilma rad etdi (HTTP {xato.code})")
            if xato.code == 401:
                break                                    # parol xato — ikkinchi usul ham bloklatmasin
        except OSError as xato:
            oxirgi = f"Qurilmaga ulanib bo'lmadi ({xato})"
    return False, oxirgi, None


def kadrlar(k, fps=4, yengil=False, ishlasin=lambda: True):
    """Yuz tanish uchun kadrlar (numpy rasmlar). Asosiy oqim — yuz aniqroq ko'rinadi."""
    import cv2
    import numpy as np
    for jpg in jonli_kadrlar(k, fps=fps, yengil=yengil, ishlasin=ishlasin):
        rasm = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
        if rasm is not None:
            yield rasm


def veb_kamera_kadrlari(soni=12, oraliq=0.4):
    """Kompyuterning o'z kamerasidan bir necha kadr (yuzni eslab qolish uchun)."""
    import cv2
    video = cv2.VideoCapture(0, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(0)
    olingan = []
    try:
        time.sleep(1.0)                                   # kamera yorug'likka moslashsin
        for _ in range(soni):
            ok, kadr = video.read()
            if ok and kadr is not None:
                olingan.append(kadr)
            time.sleep(oraliq)
    finally:
        video.release()
    return olingan


def rasm_baytlari(k, eni=960):
    """Telefon uchun kichraytirilgan JPG baytlari — faylga SAQLAMAYDI (jonli ko'rishda
    har soniyada rasm so'raladi, Rasmlar papkasi to'lib ketmasin). (baytlar, None) yoki (None, xato)."""
    kirish_xato = None
    try:
        jpg = _isapi_rasm(k)
    except BloklanganXato as xato:
        return None, str(xato)
    except PermissionError as xato:
        jpg, kirish_xato = None, str(xato)
    try:
        import cv2
        import numpy as np
    except ImportError:
        return (jpg, None) if jpg else (None, "Kameraga ulanib bo'lmadi")
    rasm = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR) if jpg else _rtsp_kadr(k, yengil=True)
    if rasm is None:
        return None, kirish_xato or "Kameraga ulanib bo'lmadi"
    if rasm.shape[1] > eni:
        rasm = cv2.resize(rasm, (eni, int(rasm.shape[0] * eni / rasm.shape[1])), interpolation=cv2.INTER_AREA)
    ok, kod = cv2.imencode(".jpg", rasm, [cv2.IMWRITE_JPEG_QUALITY, 72])
    return (kod.tobytes(), None) if ok else (None, "Rasmni tayyorlab bo'lmadi")
