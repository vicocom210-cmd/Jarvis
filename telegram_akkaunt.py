"""
Telegram AKKAUNTINGIZ orqali (bot emas): tanlangan do'stlardan kelgan xabarlarni o'qish va javob yozish.

Bot sizning shaxsiy yozishmalaringizni ko'ra olmaydi — shuning uchun Telegram'ning rasmiy
akkaunt API'si (Telethon kutubxonasi) ishlatiladi:
  1) my.telegram.org -> "API development tools" -> api_id va api_hash oling (bepul, bir marta);
  2) Jarvis chat sozlamalarida telefon raqamingizni kiriting -> Telegram'ga kelgan kodni yozing.

Kirish kaliti (sessiya) faqat shu kompyuterda saqlanadi: %APPDATA%\\Jarvis\\telegram_akkaunt.session
Bu fayl akkauntingizga kirish huquqini beradi — uni hech kimga bermang.
Kutubxona: pip install telethon
"""
import asyncio
import os
import random
import re
import threading

import sozlamalar

SESSIYA = os.path.join(sozlamalar.PAPKA, "telegram_akkaunt")
SESSIYA_BIZNES = os.path.join(sozlamalar.PAPKA, "telegram_biznes")   # 2-akkaunt (masalan, kompaniya)
TELEGRAM_XIZMAT = 777000                  # Telegram'ning rasmiy chati (kirish kodlari) — hech qachon tegilmaydi

KOD_TURLARI = {
    "SentCodeTypeApp": "boshqa qurilmangizdagi Telegram ilovasiga — \"Telegram\" nomli rasmiy chatni oching (ko'k belgili)",
    "SentCodeTypeSms": "SMS orqali telefoningizga",
    "SentCodeTypeSmsWord": "SMS orqali (kod — so'z)",
    "SentCodeTypeSmsPhrase": "SMS orqali (kod — ibora)",
    "SentCodeTypeFirebaseSms": "SMS orqali telefoningizga",
    "SentCodeTypeFragmentSms": "Fragment (fragment.com) orqali — raqamingiz Fragment raqami",
    "SentCodeTypeCall": "qo'ng'iroq orqali — kodni ovozda aytishadi",
    "SentCodeTypeFlashCall": "qo'ng'iroq orqali — kod qo'ng'iroq qilgan raqamning oxirgi raqamlari",
    "SentCodeTypeMissedCall": "qo'ng'iroq orqali — kod qo'ng'iroq qilgan raqamning oxirgi raqamlari",
    "SentCodeTypeEmailCode": "Telegram'ga bog'langan email pochtangizga",
    "SentCodeTypeSetUpEmailRequired": "email kerak — avval Telegram ilovasida login email'ini sozlang",
}


# Oddiy emoji (bayroq, teri rangi va ZWJ birikmalari bilan)
EMOJI = re.compile("(?:[\U0001F1E6-\U0001F1FF]{2}|[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u2300-\u23FF\u2190-\u21FF]"
                   "\uFE0F?(?:\u200D[\U0001F000-\U0001FAFF\u2600-\u27BF]\uFE0F?)*)")
STIKER_BELGI = re.compile(r"\[\s*STIKER\s*:\s*([^\]]{1,12})\]", re.I)


def _toza(emoji):
    return (emoji or "").replace("\uFE0F", "").strip()


def _u16(matn):
    return len(matn.encode("utf-16-le")) // 2


def _qayerga(natija):
    tur = type(getattr(natija, "type", None)).__name__
    matn = KOD_TURLARI.get(tur, "Telegram'ga")
    keyingi = type(getattr(natija, "next_type", None) or object()).__name__
    if keyingi.startswith("CodeType"):              # next_type nomlari: CodeTypeSms, CodeTypeCall...
        keyingi = "Sent" + keyingi
    if keyingi in KOD_TURLARI and keyingi != tur:
        matn += ". Kelmasa — 'SMS orqali qayta yuborish'ni bosing (" + KOD_TURLARI[keyingi].split(" —")[0] + ")"
    return matn


def xato_matni(xato):
    """Telegram xatolarini tushunarli qilib aytadi."""
    nom = type(xato).__name__
    if nom == "FloodWaitError":
        daqiqa = max(1, int(getattr(xato, "seconds", 60)) // 60)
        return f"Telegram ko'p urinish uchun vaqtincha to'xtatdi — {daqiqa} daqiqadan keyin qayta urinib ko'ring"
    return {
        "ApiIdInvalidError": "api_id yoki api_hash noto'g'ri — my.telegram.org dan qayta ko'chiring",
        "PhoneNumberInvalidError": "Telefon raqami noto'g'ri — +998901234567 ko'rinishida yozing",
        "PhoneNumberBannedError": "Bu raqam Telegram'da bloklangan",
        "PhoneCodeInvalidError": "Kod noto'g'ri — qaytadan yozing",
        "PhoneCodeExpiredError": "Kodning muddati o'tgan — yangi kod so'rang",
        "SendCodeUnavailableError": "Telegram hozir boshqa usulda kod yubora olmaydi — bir necha daqiqa kuting",
        "PasswordHashInvalidError": "Ikki bosqichli parol noto'g'ri",
        "ConnectionError": "Telegram serveriga ulanib bo'lmadi — internetni tekshiring",
        "TimeoutError": "Telegram javob bermadi — internetni tekshiring va qayta urinib ko'ring",
    }.get(nom, f"{nom}: {xato}")


class Akkaunt:
    def __init__(self, xabar_keldi, holat_xabari=print, sessiya=SESSIYA, nom="Telegram akkaunt"):
        self.sessiya, self.nom = sessiya, nom
        self.xabar_keldi = xabar_keldi        # (dict) -> None: {kim, matn, tur, chat_id, xabar_id}
        self.holat_xabari = holat_xabari
        self.dostlar = []                     # kuzatiladigan do'stlar: ism, @username yoki raqam
        self.hammasi = False                  # barcha shaxsiy xabarlar
        self.rasm_yukla = True                # kelgan rasmni yuklab olish (AI ko'rib aytishi uchun)
        self.mijoz = None
        self.loop = None
        self.telefon = ""
        self.kod_hash = None
        self.men = None                       # ulangan akkaunt nomi
        self.holat = "ulanmagan"              # ulanmagan / kod_kutilmoqda / qr_kutilmoqda / parol_kerak / ulangan / xato
        self.qr_url, self.qr_xato = None, ""
        self.premium = False
        self.bezak = False                    # True — Premium emoji/stikerlar yuklansin (kompaniya akkaunti)
        self.emojilar = {}                    # oddiy emoji -> [premium emoji id, ...]
        self.stikerlar = {}                   # emoji -> [stiker hujjati, ...]

    # --- ichki: alohida thread'dagi asyncio ---
    def _bajar(self, coro, timeout=40):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    def ishga_tushir(self, api_id, api_hash):
        from telethon import TelegramClient, events
        self.toxtat()
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

        async def yarat():                    # mijoz shu loop ichida yaratiladi — o'shanga bog'lanadi
            m = TelegramClient(self.sessiya, int(api_id), str(api_hash).strip())
            await m.connect()
            return m
        self.mijoz = self._bajar(yarat())

        @self.mijoz.on(events.NewMessage(incoming=True))
        async def _yangi(hodisa):
            try:
                await self._ishla(hodisa)
            except Exception as xato:
                print(f"(Telegram xabarini o'qishda xato: {xato})")

        if self._bajar(self.mijoz.is_user_authorized()):
            self._ulandi()
        return self.holat

    def _ulandi(self):
        self._bajar(self._ulandi_async())

    def toxtat(self):
        if self.mijoz is not None:
            try:
                self._bajar(self.mijoz.disconnect(), timeout=10)
            except Exception:
                pass
        if self.loop is not None:
            self.loop.call_soon_threadsafe(self.loop.stop)
        self.mijoz = self.loop = None

    # --- kirish (bir marta) ---
    def kod_yubor(self, telefon):
        """Kod so'raydi. Kod QAYERGA ketganini qaytaradi (odatda SMS emas — Telegram ilovasiga)."""
        self.telefon = telefon.strip().replace(" ", "")
        natija = self._bajar(self.mijoz.send_code_request(self.telefon))
        self.kod_hash = natija.phone_code_hash
        self.holat = "kod_kutilmoqda"
        return _qayerga(natija)

    def qr_boshla(self, daqiqa=3):
        """QR kod bilan kirish (kod kerak emas): telefondagi Telegram -> Sozlamalar -> Qurilmalar ->
        'Kompyuterni ulash' bilan skanerlanadi. QR har ~30 soniyada yangilanadi (self.qr_url)."""
        from telethon.errors import SessionPasswordNeededError
        self.qr_url, self.qr_xato = None, ""

        async def ish():
            try:
                qr = await self.mijoz.qr_login()
                self.qr_url, self.holat = qr.url, "qr_kutilmoqda"
                tugash = self.loop.time() + daqiqa * 60
                while True:
                    try:
                        await qr.wait(timeout=25)
                        break
                    except asyncio.TimeoutError:
                        if self.loop.time() > tugash:
                            self.holat, self.qr_url = "ulanmagan", None
                            self.qr_xato = "QR vaqti tugadi — qaytadan 'QR kod bilan kirish'ni bosing"
                            return
                        await qr.recreate()
                        self.qr_url = qr.url
            except SessionPasswordNeededError:
                self.holat, self.qr_url = "parol_kerak", None
                return
            except Exception as xato:
                self.holat, self.qr_url, self.qr_xato = "ulanmagan", None, xato_matni(xato)
                return
            self.qr_url = None
            await self._ulandi_async()

        asyncio.run_coroutine_threadsafe(ish(), self.loop)

    async def _ulandi_async(self):
        me = await self.mijoz.get_me()
        self.premium = bool(getattr(me, "premium", False))
        if self.bezak and self.premium:
            try:
                await self._bezak_yukla()
            except Exception as xato:
                print(f"(Premium emoji yuklanmadi: {xato})")
        self.men = " ".join(x for x in (me.first_name, me.last_name) if x) + (f" (@{me.username})" if me.username else "")
        self.holat = "ulangan"
        self.holat_xabari(f"✈️ {self.nom} ulandi: {self.men}")

    async def _bezak_yukla(self):
        """Akkauntdagi Premium emoji va stiker to'plamlarini o'qiydi (o'rnatilganlari, bo'lmasa — tavsiya etilganlari)."""
        from telethon.tl.functions.messages import (GetAllStickersRequest, GetEmojiStickersRequest,
                                                    GetFeaturedEmojiStickersRequest, GetStickerSetRequest)
        from telethon.tl.types import DocumentAttributeCustomEmoji, DocumentAttributeSticker, InputStickerSetID
        toplamlar = []
        for sorov, soni in ((GetEmojiStickersRequest(0), 10), (GetAllStickersRequest(0), 8)):
            try:
                toplamlar += list(getattr(await self.mijoz(sorov), "sets", []))[:soni]
            except Exception:
                pass
        if not any(getattr(t, "emojis", False) for t in toplamlar):
            try:
                toplamlar += [getattr(t, "set", t) for t in (await self.mijoz(GetFeaturedEmojiStickersRequest(0))).sets][:5]
            except Exception:
                pass
        emojilar, stikerlar = {}, {}
        for t in toplamlar:
            try:
                to = await self.mijoz(GetStickerSetRequest(InputStickerSetID(t.id, t.access_hash), 0))
            except Exception:
                continue
            for d in to.documents:
                for a in d.attributes:
                    if isinstance(a, DocumentAttributeCustomEmoji) and a.alt:
                        emojilar.setdefault(_toza(a.alt), []).append(d.id)
                    elif isinstance(a, DocumentAttributeSticker) and a.alt:
                        stikerlar.setdefault(_toza(a.alt), []).append(d)
        self.emojilar, self.stikerlar = emojilar, stikerlar
        print(f"(Premium: {len(emojilar)} xil emoji, {len(stikerlar)} xil stiker yuklandi)")

    def bezak_bormi(self):
        return self.premium and bool(self.emojilar or self.stikerlar)

    def yubor_bezakli(self, chat_id, matn):
        """Matnni Premium emoji bilan yuboradi; oxirida [STIKER:👋] bo'lsa — mos stikerni ham.
        Yuborilgan xabarlar ro'yxatini qaytaradi."""
        from telethon.tl.types import MessageEntityCustomEmoji
        stiker = None
        m = STIKER_BELGI.search(matn)
        if m:
            stiker = _toza(m.group(1))
            matn = (matn[:m.start()] + matn[m.end():]).strip()
        belgilar = []
        if self.premium and self.emojilar:
            for e in EMOJI.finditer(matn):
                idlar = self.emojilar.get(_toza(e.group()))
                if idlar:
                    belgilar.append(MessageEntityCustomEmoji(_u16(matn[:e.start()]), _u16(e.group()), random.choice(idlar)))
        yuborilgan = []
        if matn:
            try:
                yuborilgan.append(self._bajar(self.mijoz.send_message(chat_id, matn, formatting_entities=belgilar or None),
                                              timeout=30))
            except Exception as xato:
                if not belgilar:
                    raise
                print(f"(Premium emoji bilan yuborilmadi, oddiy yuboraman: {xato})")
                yuborilgan.append(self.yubor(chat_id, matn))
        if stiker and self.premium and self.stikerlar.get(stiker):
            try:
                yuborilgan.append(self._bajar(self.mijoz.send_file(chat_id, random.choice(self.stikerlar[stiker])),
                                              timeout=30))
            except Exception as xato:
                print(f"(Stiker yuborilmadi: {xato})")
        return yuborilgan

    def qayta_yubor(self):
        """Kodni boshqa usulda (odatda SMS) qayta yuborish."""
        from telethon.tl.functions.auth import ResendCodeRequest
        natija = self._bajar(self.mijoz(ResendCodeRequest(self.telefon, self.kod_hash)))
        self.kod_hash = natija.phone_code_hash
        return _qayerga(natija)

    def kirish(self, kod, parol=""):
        from telethon.errors import SessionPasswordNeededError
        try:
            if self.holat == "parol_kerak" or (parol and self.holat != "kod_kutilmoqda"):
                self._bajar(self.mijoz.sign_in(password=parol))
            else:
                self._bajar(self.mijoz.sign_in(self.telefon, str(kod).strip(), phone_code_hash=self.kod_hash))
        except SessionPasswordNeededError:
            if not parol:
                self.holat = "parol_kerak"
                return "parol_kerak"
            self._bajar(self.mijoz.sign_in(password=parol))
        self._ulandi()
        return "ulangan"

    def chiqish(self):
        try:
            self._bajar(self.mijoz.log_out())
        finally:
            self.holat, self.men = "ulanmagan", None
            for fayl in (self.sessiya + ".session", self.sessiya + ".session-journal"):
                try:
                    os.remove(fayl)
                except OSError:
                    pass

    # --- xabarlar ---
    def _kuzatiladimi(self, kim):
        if self.hammasi:
            return True
        ism = " ".join(x for x in (getattr(kim, "first_name", ""), getattr(kim, "last_name", "")) if x).lower()
        username = (getattr(kim, "username", "") or "").lower()
        telefon = (getattr(kim, "phone", "") or "").lstrip("+")
        for d in self.dostlar:
            d = d.strip().lower()
            if not d:
                continue
            if d.startswith("@") and d[1:] == username:
                return True
            if d.lstrip("+").isdigit() and telefon and telefon.endswith(d.lstrip("+")[-9:]):
                return True
            if d == username or (d and (d == ism or d in ism.split() or ism.startswith(d))):
                return True
        return False

    async def _ishla(self, hodisa):
        if not hodisa.is_private:                 # guruh va kanallar — yo'q
            return
        if hodisa.chat_id == TELEGRAM_XIZMAT:
            return
        kim = await hodisa.get_sender()
        if kim is None or getattr(kim, "bot", False) or not self._kuzatiladimi(kim):
            return
        xabar = hodisa.message
        tur = "matn"
        if xabar.voice:
            tur = "ovoz"
        elif xabar.video_note or xabar.video:
            tur = "video"
        elif xabar.photo:
            tur = "rasm"
        elif xabar.sticker:
            tur = "stiker"
        elif xabar.document:
            tur = "fayl"
        ism = " ".join(x for x in (kim.first_name, kim.last_name) if x) or (kim.username or "Noma'lum")
        rasm_yoli = None
        if tur == "rasm" and self.rasm_yukla:
            try:
                import tempfile
                rasm_yoli = await xabar.download_media(file=os.path.join(tempfile.gettempdir(), "jarvis_tg_rasm.jpg"))
            except Exception:
                rasm_yoli = None
        self.xabar_keldi({"kim": ism, "matn": xabar.message or "", "tur": tur, "chat_id": hodisa.chat_id,
                          "xabar_id": xabar.id, "rasm": rasm_yoli, "username": getattr(kim, "username", "") or "",
                          "emoji": getattr(getattr(xabar, "sticker", None), "alt", "") if tur == "stiker" else ""})

    def oqildi(self, chat_id, xabar_id):
        try:
            self._bajar(self.mijoz.send_read_acknowledge(chat_id, max_id=xabar_id), timeout=15)
        except Exception:
            pass

    def yubor(self, chat_id, matn):
        return self._bajar(self.mijoz.send_message(chat_id, matn), timeout=30)

    def oxirgi_xabarlar(self, chat_id, soni=12):
        """Suhbatning oxirgi xabarlari, eskisidan yangisiga: [(chiquvchimi, matn, vaqt, id), ...]"""
        xabarlar = self._bajar(self.mijoz.get_messages(chat_id, limit=soni), timeout=30)
        def matn(x):
            if x.message:
                return x.message
            if x.voice:
                return "[ovozli xabar yubordi]"
            if x.photo:
                return "[rasm yubordi]"
            return "[fayl/stiker yubordi]" if x.media else ""
        return [(bool(x.out), matn(x), x.date.timestamp(), x.id) for x in reversed(xabarlar)]
