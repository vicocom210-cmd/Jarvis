"""
Bulut ko'prigi: telefon ilovasi kompyuterni ISTALGAN joydan boshqarishi uchun
(bir Wi-Fi shart emas, port ochish shart emas).

Ishlashi: kompyuter va telefon umumiy bepul MQTT serveriga (broker.hivemq.com) ulanadi.
Ular maxfiy "kanal" orqali xabar almashadi. Har bir buyruqda PIN tekshiriladi.

Kerak: pip install paho-mqtt   (sof python, 32-bitda ham o'rnatiladi)
"""
import json
import threading

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

BROKER = "broker.hivemq.com"
PORT = 1883
_klient = None


def bormi():
    return mqtt is not None


def ishga_tushir(kanal, pin, bajaruvchi):
    """Bulut ko'prigini ishga tushiradi. (holat) qaytaradi:
    'ok', 'yoq_kutubxona' (paho-mqtt yo'q), 'xato' (ulanmadi)."""
    global _klient
    if mqtt is None:
        return "yoq_kutubxona"
    if _klient is not None:                          # qayta ulanish (masalan, PIN o'zgardi)
        try:
            _klient.loop_stop()
            _klient.disconnect()
        except Exception:
            pass
        _klient = None
    cmd_mavzu = f"jarvis/{kanal}/cmd"
    reply_mavzu = f"jarvis/{kanal}/reply"

    try:
        klient = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except (AttributeError, TypeError):
        klient = mqtt.Client()                       # eski paho versiyalari uchun

    def ulanganda(cl, *_):
        cl.subscribe(cmd_mavzu)
        print(f"☁️ Bulut ko'prigi ulandi (kanal: {kanal})")

    def xabar_kelganda(cl, foydalanuvchi, xabar):
        try:
            malumot = json.loads(xabar.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return
        if str(malumot.get("pin", "")) != str(pin):
            cl.publish(reply_mavzu, json.dumps({"ok": False, "xato": "PIN"}))
            return
        matn = (malumot.get("matn") or "").strip()
        if not matn:
            return
        try:
            javob = bajaruvchi(matn)
        except Exception as xato:
            javob = f"Xato: {xato}"
        cl.publish(reply_mavzu, json.dumps({"ok": True, "javob": javob}, ensure_ascii=False))

    klient.on_connect = ulanganda
    klient.on_message = xabar_kelganda
    try:
        klient.connect(BROKER, PORT, 60)
    except OSError as xato:
        print(f"(Bulut ko'prigi ulanmadi: {xato})")
        return "xato"
    klient.loop_start()
    _klient = klient
    return "ok"
