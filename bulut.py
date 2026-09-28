"""
Bulut ko'prigi: telefon ilovasi kompyuterni ISTALGAN joydan boshqarishi uchun
(bir Wi-Fi shart emas, port ochish shart emas).

Ishlashi: kompyuter va telefon umumiy bepul MQTT serveriga (broker.hivemq.com) ulanadi.
Ular maxfiy "kanal" orqali xabar almashadi. Har bir buyruqda PIN tekshiriladi.

Kamera rasmlari, eshik va skanerlash — faqat SHIFRLANGAN holda (AES-256-GCM): kalitni telefon
uy Wi-Fi'da bir marta oladi, ochiq serverda faqat tushunarsiz baytlar ko'rinadi. Eski xabarni
qayta yuborib bo'lmaydi (vaqt belgisi + bir martalik raqam tekshiriladi).

Kerak: pip install paho-mqtt cryptography
"""
import base64
import json
import os
import threading
import time

import himoya

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None

BROKER = "broker.hivemq.com"
PORT = 1883
_klient = None


def bormi():
    return mqtt is not None


def shifrla(kalit, obj):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    nonce = os.urandom(12)
    return base64.b64encode(nonce + AESGCM(kalit).encrypt(nonce, json.dumps(obj, ensure_ascii=False).encode("utf-8"), None)).decode()


def ochish(kalit, matn):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    xom = base64.b64decode(matn)
    return json.loads(AESGCM(kalit).decrypt(xom[:12], xom[12:], None).decode("utf-8"))


_korilgan = {}                   # bir martalik raqamlar (qayta yuborishga qarshi): raqam -> vaqt


def _yangimi(sorov):
    hozir = time.time() * 1000
    if abs(hozir - float(sorov.get("t", 0))) > 120_000:          # 2 daqiqadan eski/kelajak — rad
        return False
    kalit = f"{sorov.get('t')}:{sorov.get('id')}"
    if kalit in _korilgan:
        return False
    for k, v in list(_korilgan.items()):
        if hozir - v > 300_000:
            _korilgan.pop(k, None)
    _korilgan[kalit] = hozir
    return True


def ishga_tushir(kanal, pin, bajaruvchi, kalit=None, amal=None):
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

    def shifrli_ishla(cl, malumot):
        try:
            sorov = ochish(kalit, malumot["e"])
        except Exception:
            return                                   # kalit mos emas — javob bermaymiz
        if not _yangimi(sorov):
            return
        try:
            if sorov.get("amal") == "buyruq":
                natija = {"ok": True, "javob": bajaruvchi(str((sorov.get("m") or {}).get("matn", "")))}
            elif sorov.get("amal") == "sinxron":
                natija = {"ok": False, "xato": "Bu faqat uy Wi-Fi'da"}
            else:
                natija = amal(str(sorov.get("amal", "")), sorov.get("m") or {}) if amal else {"ok": False}
        except Exception as xato:
            natija = {"ok": False, "xato": f"Xato: {xato}"}
        natija["id"] = sorov.get("id")
        cl.publish(reply_mavzu, json.dumps({"e": shifrla(kalit, natija)}))

    def xabar_kelganda(cl, foydalanuvchi, xabar):
        try:
            malumot = json.loads(xabar.payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return
        if "e" in malumot:                           # shifrlangan (kamera, eshik) — alohida thread'da
            if kalit:
                threading.Thread(target=shifrli_ishla, args=(cl, malumot), daemon=True).start()
            return
        ok, xato = himoya.tekshir("bulut", malumot.get("pin", ""), pin)
        if not ok:                                   # taxmin qilib topishga qarshi bloklash bilan
            cl.publish(reply_mavzu, json.dumps({"ok": False, "xato": xato}, ensure_ascii=False))
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
