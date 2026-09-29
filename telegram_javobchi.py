"""
Ikkinchi Telegram akkaunt (masalan, kompaniya — Gatework) uchun AVTOMATIK JAVOBCHI.

Kimdir shaxsiy xabar yozsa — Jarvis bir necha soniya kutadi (ketma-ket xabarlarni yig'adi), suhbatning
oxirgi xabarlarini o'qiydi va AI (Claude) kompaniya ma'lumotiga tayanib javob yozadi.

Himoya:
  - faqat shaxsiy chatlar (guruh/kanal/bot yo'q), Telegram'ning rasmiy chati (kodlar) — hech qachon;
  - operator (siz) o'zingiz shu chatda yozsangiz — Jarvis 30 daqiqa o'sha chatga aralashmaydi;
  - soatiga javoblar soni cheklangan (spam deb bloklanmaslik uchun), bitta chatga tez-tez yozmaydi.
"""
import collections
import json
import os
import queue
import threading
import time

import sozlamalar
import telegram_akkaunt

JAVOBLAR_FAYLI = os.path.join(sozlamalar.PAPKA, "telegram_biznes_javoblar.json")


class Javobchi:
    def __init__(self, akk, ai, malumot, xabar=print):
        self.akk = akk                    # telegram_akkaunt.Akkaunt (2-akkaunt)
        self.ai = ai                      # (tarix [(rol, matn)], malumot) -> javob matni yoki None
        self.malumot = malumot            # () -> kompaniya haqida matn
        self.xabar = xabar                # Jarvis chatiga qisqa yozuv
        self.yoniq = False
        self.kechikish = 6                # s — ketma-ket kelgan xabarlarni bittada javoblash uchun
        self.operator_pauza = 30 * 60     # s — siz o'zingiz yozgan chatga aralashmaslik
        self.soat_chegara = 60            # soatiga ko'pi bilan shuncha javob
        self.chat_oraligi = 8             # s — bitta chatga ikki javob orasida
        self.javoblar_soni = 0
        self.bezakli = True               # Premium bo'lsa — premium emoji va stikerlar bilan
        self.oxirgi_holat = "Hali xabar kelmadi"   # sozlamalarda ko'rinadi — nima bo'lganini bilish uchun
        self._aytilgan = {}
        self._kimlar = {}               # chat_id -> oxirgi aytilgan sabab (bir xil sababni takrorlamaslik)
        self._oxirgi = {}                 # chat_id -> oxirgi kelgan xabar vaqti
        self._chatga_javob = {}           # chat_id -> oxirgi javob vaqti
        self._soat = collections.deque()
        self._navbat = queue.Queue()
        self._bizniki = self._yukla()     # Jarvis yuborgan xabar id'lari (operatornikidan ajratish uchun)
        threading.Thread(target=self._ishchi, daemon=True).start()

    # --- Jarvis yuborgan xabarlar ro'yxati (qayta yonganda ham eslab qoladi) ---
    def _yukla(self):
        try:
            with open(JAVOBLAR_FAYLI, encoding="utf-8") as f:
                return {int(k): set(v) for k, v in json.load(f).items()}
        except (OSError, ValueError):
            return {}

    def _saqla(self):
        try:
            with open(JAVOBLAR_FAYLI, "w", encoding="utf-8") as f:
                json.dump({str(k): sorted(v)[-50:] for k, v in self._bizniki.items()}, f)
        except OSError:
            pass

    # --- Telegram loop'idan chaqiriladi (tez qaytishi kerak) ---
    def _sabab(self, chat_id, kim, matn):
        """Javob berilmadi — sababini Jarvis chatida va sozlamalarda ko'rsatadi."""
        self.oxirgi_holat = f"{time.strftime('%H:%M')} — {kim}: {matn}"
        if self._aytilgan.get(chat_id) != matn:
            self._aytilgan[chat_id] = matn
            self.xabar(f"💼 {kim}ga javob berilmadi: {matn}")

    def keldi(self, x):
        self.oxirgi_holat = f"{time.strftime('%H:%M')} — {x.get('kim')}dan xabar keldi"
        print(f"(Biznes Telegram: {x.get('kim')}dan xabar keldi, avto-javob {'yoniq' if self.yoniq else 'OCHIQ EMAS'})")
        if not self.yoniq:
            self._sabab(x["chat_id"], x.get("kim", "?"), "avtomatik javob o'chiq — sozlamalarda yoqing")
            return
        self._kimlar[x["chat_id"]] = x.get("kim", "?")
        self._oxirgi[x["chat_id"]] = time.time()
        self._navbat.put(x["chat_id"])

    def _ishchi(self):
        while True:
            chat_id = self._navbat.get()
            time.sleep(self.kechikish)
            if time.time() - self._oxirgi.get(chat_id, 0) < self.kechikish - 0.5:
                continue                  # yana xabar keldi — keyingi navbat javob beradi
            try:
                self.javob_ber(chat_id)
            except Exception as xato:
                print(f"(Biznes Telegram javob xatosi: {type(xato).__name__}: {xato})")
                self._sabab(chat_id, self._kimlar.get(chat_id, "Mijoz"), f"xato — {type(xato).__name__}: {str(xato)[:120]}")

    def javob_ber(self, chat_id):
        kim = self._kimlar.get(chat_id, "Mijoz")
        if not self.yoniq:
            return
        if self.akk.holat != "ulangan":
            return self._sabab(chat_id, kim, f"akkaunt holati: {self.akk.holat}")
        tarix = self.akk.oxirgi_xabarlar(chat_id, 14)
        if not tarix or tarix[-1][0]:
            return                        # oxirgi xabar bizniki — javob berilgan
        hozir = time.time()
        bizniki = self._bizniki.get(chat_id, set())
        for chiquvchi, _, vaqt, xid in tarix:
            if chiquvchi and xid not in bizniki and hozir - vaqt < self.operator_pauza:
                qoldi = int((self.operator_pauza - (hozir - vaqt)) // 60) + 1
                return self._sabab(chat_id, kim, "bu chatga Gatework akkauntidan o'zingiz yozgansiz — Jarvis "
                                   f"{qoldi} daqiqa aralashmaydi (sinash uchun boshqa akkauntdan yozing)")
        if hozir - self._chatga_javob.get(chat_id, 0) < self.chat_oraligi:
            return
        while self._soat and hozir - self._soat[0] > 3600:
            self._soat.popleft()
        if len(self._soat) >= self.soat_chegara:
            return self._sabab(chat_id, kim, "soatlik chegara (60 ta) — keyinroq")
        suhbat = []
        for chiquvchi, matn, _, _ in tarix:
            rol = "assistant" if chiquvchi else "user"
            if not matn:
                continue
            if suhbat and suhbat[-1][0] == rol:
                suhbat[-1] = (rol, suhbat[-1][1] + "\n" + matn)
            else:
                suhbat.append((rol, matn))
        while suhbat and suhbat[0][0] == "assistant":
            suhbat.pop(0)
        if not suhbat or suhbat[-1][0] != "user":
            return
        javob = self.ai(suhbat, self.malumot())
        if not javob:
            import sun_iy
            return self._sabab(chat_id, kim, "Claude javob bermadi — " + (sun_iy.biznes_xato or "AI kaliti ulanganmi?"))
        if self.bezakli and self.akk.bezak_bormi():
            yuborilganlar = self.akk.yubor_bezakli(chat_id, javob)
        else:
            yuborilganlar = [self.akk.yubor(chat_id, telegram_akkaunt.STIKER_BELGI.sub("", javob).strip())]
        for x in yuborilganlar:
            self._bizniki.setdefault(chat_id, set()).add(getattr(x, "id", 0))
        self._saqla()
        self._chatga_javob[chat_id] = time.time()
        self._soat.append(time.time())
        self.javoblar_soni += 1
        self.akk.oqildi(chat_id, tarix[-1][3])
        self._aytilgan.pop(chat_id, None)
        self.oxirgi_holat = f"{time.strftime('%H:%M')} — {kim}ga javob berildi ✅"
        self.xabar(f"💼 {kim}ga avtomatik javob berildi — «{suhbat[-1][1][:60]}»")
