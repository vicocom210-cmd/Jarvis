"""
Kichik HTTP server: telefon ilovasi (APK) shu orqali kompyuterdagi Jarvis'ni boshqaradi.
Telefon va kompyuter bitta Wi-Fi'da bo'lishi kerak.

Xavfsizlik: har bir so'rovda PIN kod tekshiriladi (sozlamalarda saqlanadi).
Faqat mahalliy tarmoqdan (Wi-Fi) ishlaydi, internetga chiqmaydi.
"""
import json
import os
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import arxiv

PORT = 8770
_bajaruvchi = None          # (matn) -> javob  — jarvis.py beradi
_pin = "0000"
_server = None
_chat_qabul = None          # (matn) -> None  — chat oynasidan yozilgan gap (jarvis.py beradi)
_holat_ol = None            # () -> "kutish"/"tinglash"/"o'ylash"/"gapirish"
_sozlama_ol = None          # () -> dict  — chatdagi sozlamalar bo'limi uchun
_sozlama_yoz = None         # (kalit, qiymat) -> (ok, xabar)
internet_bor = True         # jarvis.py kuzatib turadi — chat oynasida ko'rsatiladi
kamera_ol = None            # (nom) -> kamera sozlamasi  — jonli video uchun (jarvis.py beradi)


def chat_sozla(qabul, holat_ol, sozlama_ol=None, sozlama_yoz=None):
    global _chat_qabul, _holat_ol, _sozlama_ol, _sozlama_yoz
    _chat_qabul, _holat_ol, _sozlama_ol, _sozlama_yoz = qabul, holat_ol, sozlama_ol, sozlama_yoz


def _manba_yoli(nom):
    """Fayl yo'li — oddiy ishga tushirishda ham, EXE ichida ham (PyInstaller) ishlaydi."""
    asos = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(asos, nom)


class _Handler(BaseHTTPRequestHandler):
    def _javob(self, kod, malumot):
        tana = json.dumps(malumot, ensure_ascii=False).encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")      # telefon ilovasi uchun
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(tana)))
        self.end_headers()
        self.wfile.write(tana)

    def do_OPTIONS(self):
        self._javob(200, {"ok": True})

    def _mahalliymi(self):
        """Chat va arxiv faqat shu kompyuterning o'zidan ochiladi (Wi-Fi'dagi boshqalar ko'rmaydi)."""
        if self.client_address[0] not in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
            return False
        # Brauzerdagi begona sayt localhost orqali buyruq bera olmasin (faqat chat sahifasining o'zi)
        manba = self.headers.get("Origin")
        return manba in (None, f"http://127.0.0.1:{PORT}", f"http://localhost:{PORT}")

    def do_GET(self):
        yol = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(yol.query)
        if yol.path.startswith("/holat"):
            self._javob(200, {"ok": True, "nom": "Jarvis kompyuter"})
            return
        if not (yol.path == "/chat" or yol.path.startswith("/api/")):
            self._javob(404, {"ok": False})
            return
        if not self._mahalliymi():
            self._javob(403, {"ok": False, "xato": "Chat faqat kompyuterning o'zida ochiladi"})
            return
        if yol.path == "/chat":
            try:
                with open(_manba_yoli("chat.html"), "rb") as f:
                    tana = f.read()
            except OSError:
                self._javob(500, {"ok": False, "xato": "chat.html topilmadi"})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(tana)))
            self.end_headers()
            self.wfile.write(tana)
        elif yol.path == "/api/sozlamalar":
            self._javob(200, {"ok": True, **(_sozlama_ol() if _sozlama_ol else {})})
        elif yol.path == "/api/jonli":
            self._jonli(q.get("k", [""])[0])
        elif yol.path == "/api/rasm":
            # faqat kamera papkasidagi .jpg (boshqa fayllarni o'qib bo'lmasin)
            nom = os.path.basename(q.get("f", [""])[0])
            fayl = os.path.join(arxiv.sozlamalar.PAPKA, "kamera", nom)
            if not nom.lower().endswith(".jpg") or not os.path.isfile(fayl):
                self._javob(404, {"ok": False})
                return
            with open(fayl, "rb") as f:
                tana = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(tana)))
            self.send_header("Cache-Control", "max-age=86400")
            self.end_headers()
            self.wfile.write(tana)
        elif yol.path == "/api/kunlar":
            self._javob(200, {"ok": True, "kunlar": arxiv.kunlar()})
        elif yol.path == "/api/kun":
            self._javob(200, {"ok": True, "yozuvlar": arxiv.kun(q.get("sana", [""])[0])})
        elif yol.path == "/api/qidir":
            self._javob(200, {"ok": True, "yozuvlar": arxiv.qidir(q.get("q", [""])[0])})
        elif yol.path == "/api/yangi":
            try:
                oxirgi = int(q.get("keyin", ["0"])[0])
            except ValueError:
                oxirgi = 0
            self._javob(200, {"ok": True, "yozuvlar": arxiv.keyin(oxirgi),
                              "holat": _holat_ol() if _holat_ol else "kutish",
                              "internet": internet_bor})
        else:
            self._javob(404, {"ok": False})

    def _jonli(self, nom):
        """Kameraning jonli videosi (MJPEG) — chatda oddiy <img> sifatida ko'rinadi.
        Oyna yopilsa (ulanish uzilsa) — kameraga ulanish ham yopiladi."""
        import kamera
        k = kamera_ol(nom) if kamera_ol else None
        if not k:
            self._javob(404, {"ok": False, "xato": "kamera topilmadi"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=kadr")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            for jpg in kamera.jonli_kadrlar(k, fps=10):
                self.wfile.write(b"--kadr\r\nContent-Type: image/jpeg\r\nContent-Length: " +
                                 str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            pass                                        # oyna yopildi — ulanishni tugatamiz

    def do_POST(self):
        try:
            uzunlik = int(self.headers.get("Content-Length", 0))
            malumot = json.loads(self.rfile.read(uzunlik).decode("utf-8"))
        except (ValueError, TypeError):
            self._javob(400, {"ok": False, "xato": "noto'g'ri so'rov"})
            return
        if self.path.startswith("/api/"):
            if not self._mahalliymi():
                self._javob(403, {"ok": False})
                return
            if self.path.startswith("/api/chat"):
                matn = (malumot.get("matn") or "").strip()
                if matn and _chat_qabul:
                    _chat_qabul(matn)
                self._javob(200, {"ok": bool(matn)})
            elif self.path.startswith("/api/sozlama"):
                if not _sozlama_yoz:
                    self._javob(503, {"ok": False, "xabar": "Jarvis tayyor emas"})
                    return
                qoshimcha = {}
                try:
                    natija = _sozlama_yoz(str(malumot.get("kalit", "")), malumot.get("qiymat"))
                    ok, xabar = natija[0], natija[1]
                    if len(natija) > 2:
                        qoshimcha = natija[2]                 # masalan, kamera sinovi rasmi
                except Exception as xato:
                    ok, xabar = False, f"Xato: {xato}"
                self._javob(200, {"ok": ok, "xabar": xabar, **qoshimcha})
            elif self.path.startswith("/api/ochir"):
                self._javob(200, {"ok": arxiv.ochir(malumot.get("sana", ""))})
            else:
                self._javob(404, {"ok": False})
            return
        if str(malumot.get("pin", "")) != _pin:
            self._javob(403, {"ok": False, "xato": "PIN noto'g'ri"})
            return
        matn = (malumot.get("matn") or "").strip()
        if not matn:
            self._javob(400, {"ok": False, "xato": "bo'sh buyruq"})
            return
        try:
            javob = _bajaruvchi(matn) if _bajaruvchi else "Server tayyor emas."
        except Exception as xato:
            javob = f"Xato: {xato}"
        self._javob(200, {"ok": True, "javob": javob})

    def log_message(self, *args):
        pass                    # konsolni to'ldirmaymiz


def ishga_tushir(bajaruvchi, pin="0000", port=PORT):
    """Serverni alohida thread'da ishga tushiradi."""
    global _bajaruvchi, _pin, _server
    _bajaruvchi, _pin = bajaruvchi, str(pin)
    if _server is not None:
        try:
            _server.shutdown()
        except Exception:
            pass
    try:
        _server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    except OSError as xato:
        print(f"(Server ishga tushmadi: {xato})")
        return False
    threading.Thread(target=_server.serve_forever, daemon=True).start()
    print(f"🌐 Telefon serveri ishga tushdi: port {port}")
    return True


def ip_manzil():
    """Kompyuterning Wi-Fi'dagi IP manzili (telefon shu manzilga ulanadi)."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()
