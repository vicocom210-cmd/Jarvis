"""
Kichik HTTP server: telefon ilovasi (APK) shu orqali kompyuterdagi Jarvis'ni boshqaradi.
Telefon va kompyuter bitta Wi-Fi'da bo'lishi kerak.

Xavfsizlik: har bir so'rovda PIN kod tekshiriladi (sozlamalarda saqlanadi).
Faqat mahalliy tarmoqdan (Wi-Fi) ishlaydi, internetga chiqmaydi.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8770
_bajaruvchi = None          # (matn) -> javob  — jarvis.py beradi
_pin = "0000"
_server = None


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

    def do_GET(self):
        if self.path.startswith("/holat"):
            self._javob(200, {"ok": True, "nom": "Jarvis kompyuter"})
        else:
            self._javob(404, {"ok": False})

    def do_POST(self):
        try:
            uzunlik = int(self.headers.get("Content-Length", 0))
            malumot = json.loads(self.rfile.read(uzunlik).decode("utf-8"))
        except (ValueError, TypeError):
            self._javob(400, {"ok": False, "xato": "noto'g'ri so'rov"})
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
