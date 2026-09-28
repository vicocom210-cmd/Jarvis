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
import threading

import sozlamalar

SESSIYA = os.path.join(sozlamalar.PAPKA, "telegram_akkaunt")


class Akkaunt:
    def __init__(self, xabar_keldi, holat_xabari=print):
        self.xabar_keldi = xabar_keldi        # (dict) -> None: {kim, matn, tur, chat_id, xabar_id}
        self.holat_xabari = holat_xabari
        self.dostlar = []                     # kuzatiladigan do'stlar: ism, @username yoki raqam
        self.hammasi = False                  # barcha shaxsiy xabarlar
        self.mijoz = None
        self.loop = None
        self.telefon = ""
        self.kod_hash = None
        self.men = None                       # ulangan akkaunt nomi
        self.holat = "ulanmagan"              # ulanmagan / kod_kutilmoqda / parol_kerak / ulangan / xato

    # --- ichki: alohida thread'dagi asyncio ---
    def _bajar(self, coro, timeout=40):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    def ishga_tushir(self, api_id, api_hash):
        from telethon import TelegramClient, events
        self.toxtat()
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

        async def yarat():                    # mijoz shu loop ichida yaratiladi — o'shanga bog'lanadi
            m = TelegramClient(SESSIYA, int(api_id), str(api_hash).strip())
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
        me = self._bajar(self.mijoz.get_me())
        self.men = " ".join(x for x in (me.first_name, me.last_name) if x) + (f" (@{me.username})" if me.username else "")
        self.holat = "ulangan"
        self.holat_xabari(f"✈️ Telegram akkaunt ulandi: {self.men}")

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
        self.telefon = telefon.strip().replace(" ", "")
        natija = self._bajar(self.mijoz.send_code_request(self.telefon))
        self.kod_hash = natija.phone_code_hash
        self.holat = "kod_kutilmoqda"

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
            for fayl in (SESSIYA + ".session", SESSIYA + ".session-journal"):
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
        if tur == "rasm":
            try:
                import tempfile
                rasm_yoli = await xabar.download_media(file=os.path.join(tempfile.gettempdir(), "jarvis_tg_rasm.jpg"))
            except Exception:
                rasm_yoli = None
        self.xabar_keldi({"kim": ism, "matn": xabar.message or "", "tur": tur, "chat_id": hodisa.chat_id,
                          "xabar_id": xabar.id, "rasm": rasm_yoli,
                          "emoji": getattr(getattr(xabar, "sticker", None), "alt", "") if tur == "stiker" else ""})

    def oqildi(self, chat_id, xabar_id):
        try:
            self._bajar(self.mijoz.send_read_acknowledge(chat_id, max_id=xabar_id), timeout=15)
        except Exception:
            pass

    def yubor(self, chat_id, matn):
        self._bajar(self.mijoz.send_message(chat_id, matn), timeout=30)
