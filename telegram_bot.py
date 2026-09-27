"""
Telegram bot: telefondan (istalgan joydan) kompyuterdagi Jarvis'ni boshqarish.

Xavfsizlik:
  * Botni faqat BITTA odam — egasi boshqaradi. Egasi juftlash kodi bilan aniqlanadi:
    Jarvis ekranda 6 xonali kod ko'rsatadi, siz uni botga yuborasiz. Boshqa hech kim
    (kodni bilmasa) botga buyruq bera olmaydi.
  * Buyruqlar oddiy Jarvis buyruqlari kabi bajariladi — xavfli buyruqlar baribir
    "ha/yo'q" tasdig'ini so'raydi.

Qo'shimcha kutubxona shart emas: Telegram API bilan urllib orqali gaplashamiz.
"""
import json
import os
import random
import time
import urllib.parse
import urllib.request
import uuid

API = "https://api.telegram.org/bot{token}/{usul}"
FAYL_API = "https://api.telegram.org/file/bot{token}/{yol}"
MAX_FAYL = 49 * 1024 * 1024          # Telegram botlari 50 MB gacha fayl yubora oladi


def _multipart(maydonlar, fayl_maydoni, fayl_nomi, malumot):
    """Fayl yuborish uchun so'rov tanasi (multipart/form-data)."""
    chegara = uuid.uuid4().hex
    tana = bytearray()
    for kalit, qiymat in maydonlar.items():
        tana += (f"--{chegara}\r\nContent-Disposition: form-data; name=\"{kalit}\"\r\n\r\n"
                 f"{qiymat}\r\n").encode("utf-8")
    tana += (f"--{chegara}\r\nContent-Disposition: form-data; name=\"{fayl_maydoni}\"; "
             f"filename=\"{fayl_nomi}\"\r\nContent-Type: application/octet-stream\r\n\r\n"
             ).encode("utf-8")
    tana += malumot + b"\r\n" + f"--{chegara}--\r\n".encode("utf-8")
    return bytes(tana), f"multipart/form-data; boundary={chegara}"


class Bot:
    def __init__(self, token, egasi, xabar_keldi, egasi_ozgardi, holat_ozgardi, saqlash_papkasi):
        """xabar_keldi(matn)          — egasidan kelgan buyruq (Jarvis'ga beriladi)
        egasi_ozgardi(id)          — juftlash muvaffaqiyatli bo'ldi (saqlash uchun)
        holat_ozgardi(holat, kod)  — oynada ko'rsatish uchun
        saqlash_papkasi()          — telefondan kelgan fayllar shu yerga saqlanadi"""
        self.token = token.strip()
        self.egasi = int(egasi or 0)
        self.xabar_keldi = xabar_keldi
        self.egasi_ozgardi = egasi_ozgardi
        self.holat_ozgardi = holat_ozgardi
        self.saqlash_papkasi = saqlash_papkasi
        self.kod = f"{random.randint(0, 999999):06d}"
        self.ishlasin = True
        self.begonalarga_aytildi = set()
        self.urinishlar = {}          # kim necha marta noto'g'ri kod yubordi

    # ----- Telegram API -----
    def sorov(self, usul, vaqt=15, **qiymatlar):
        malumot = urllib.parse.urlencode(qiymatlar).encode("utf-8")
        url = API.format(token=self.token, usul=usul)
        with urllib.request.urlopen(url, data=malumot, timeout=vaqt) as javob:
            natija = json.loads(javob.read().decode("utf-8"))
        if not natija.get("ok"):
            raise RuntimeError(natija.get("description", "Telegram xatosi"))
        return natija["result"]

    def yoz(self, matn, chat=None):
        chat = chat or self.egasi
        if not chat or not matn:
            return
        try:
            self.sorov("sendMessage", chat_id=chat, text=matn[:4000])
        except Exception as xato:
            print(f"(Telegram: xabar yuborilmadi: {xato})")

    def fayl_yubor(self, yol, izoh=""):
        """Faylni egasiga yuboradi. Muvaffaqiyatli bo'lsa True."""
        if not self.egasi:
            return False
        try:
            if os.path.getsize(yol) > MAX_FAYL:
                self.yoz(f"{os.path.basename(yol)} — 50 MB dan katta, Telegram orqali yuborib bo'lmaydi.")
                return False
            with open(yol, "rb") as f:
                malumot = f.read()
            tana, tur = _multipart({"chat_id": self.egasi, "caption": izoh[:1000]}, "document",
                                   os.path.basename(yol), malumot)
            sorov = urllib.request.Request(API.format(token=self.token, usul="sendDocument"),
                                           data=tana, headers={"Content-Type": tur})
            with urllib.request.urlopen(sorov, timeout=120) as javob:
                return json.loads(javob.read().decode("utf-8")).get("ok", False)
        except Exception as xato:
            print(f"(Telegram: fayl yuborilmadi: {xato})")
            return False

    def yuklab_ol(self, file_id, nom):
        """Telefondan kelgan faylni kompyuterga saqlaydi. Saqlangan yo'lni qaytaradi."""
        malumot = self.sorov("getFile", file_id=file_id)
        url = FAYL_API.format(token=self.token, yol=malumot["file_path"])
        papka = self.saqlash_papkasi()
        os.makedirs(papka, exist_ok=True)
        nom = "".join(h for h in nom if h not in '\\/:*?"<>|') or "fayl"
        yol = os.path.join(papka, nom)
        asos, kengaytma = os.path.splitext(yol)
        i = 1
        while os.path.exists(yol):                      # bir xil nomli fayl bo'lsa — (1), (2)...
            yol = f"{asos} ({i}){kengaytma}"
            i += 1
        with urllib.request.urlopen(url, timeout=120) as javob, open(yol, "wb") as f:
            f.write(javob.read())
        return yol

    # ----- asosiy sikl -----
    def ishla(self):
        try:
            nom = self.sorov("getMe")["username"]
        except Exception as xato:
            print(f"(Telegram bot ulanmadi: {xato})")
            self.holat_ozgardi("xato", "")
            return
        print(f"📱 Telegram bot ishga tushdi: @{nom}")
        if self.egasi:
            self.holat_ozgardi("ulangan", nom)
        else:
            print(f"📱 Juftlash kodi: {self.kod} — uni @{nom} botiga yuboring.")
            self.holat_ozgardi("kod", self.kod)
        oxirgi = 0
        while self.ishlasin:
            try:
                yangilar = self.sorov("getUpdates", vaqt=40, offset=oxirgi + 1, timeout=25)
            except Exception as xato:
                print(f"(Telegram: {xato})")
                time.sleep(5)
                continue
            for yangi in yangilar:
                oxirgi = max(oxirgi, yangi["update_id"])
                xabar = yangi.get("message")
                if xabar and self.ishlasin:
                    try:
                        self.xabarni_ishla(xabar)
                    except Exception as xato:
                        print(f"(Telegram xabarida xato: {xato})")

    def xabarni_ishla(self, xabar):
        kimdan = xabar.get("from", {}).get("id")
        chat = xabar["chat"]["id"]
        matn = (xabar.get("text") or xabar.get("caption") or "").strip()

        if not self.egasi:                              # hali egasi yo'q — faqat kod qabul qilinadi
            if self.urinishlar.get(kimdan, 0) >= 5:
                return                                  # kodni taxmin qilmoqchi — e'tibor bermaymiz
            if matn == self.kod:
                self.egasi = kimdan
                self.egasi_ozgardi(kimdan)
                self.holat_ozgardi("ulangan", "")
                self.yoz("✅ Ulandi! Endi men sizning Jarvis'ingizman.\n"
                         "Buyruq yozing, masalan: soat necha, yuklamalardagi rasmlarni tashla, "
                         "ekran rasmini yubor. Rasm yoki fayl yuborsangiz, kompyuterga saqlayman.", chat)
            else:
                if matn.isdigit():
                    self.urinishlar[kimdan] = self.urinishlar.get(kimdan, 0) + 1
                self.yoz("Salom! Ulanish uchun kompyuterdagi Jarvis oynasida ko'rsatilgan "
                         "6 xonali kodni yuboring.", chat)
            return

        if kimdan != self.egasi:                        # begona odam
            if kimdan not in self.begonalarga_aytildi:
                self.begonalarga_aytildi.add(kimdan)
                self.yoz("Kechirasiz, bu shaxsiy bot.", chat)
            return

        # telefondan fayl yoki rasm keldi — kompyuterga saqlaymiz
        fayl = None
        if xabar.get("document"):
            d = xabar["document"]
            fayl = (d["file_id"], d.get("file_name") or "fayl")
        elif xabar.get("photo"):
            eng_katta = xabar["photo"][-1]
            fayl = (eng_katta["file_id"], time.strftime("rasm_%Y-%m-%d_%H-%M-%S.jpg"))
        elif xabar.get("video"):
            v = xabar["video"]
            fayl = (v["file_id"], v.get("file_name") or time.strftime("video_%Y-%m-%d_%H-%M-%S.mp4"))
        elif xabar.get("audio"):
            a = xabar["audio"]
            fayl = (a["file_id"], a.get("file_name") or time.strftime("audio_%Y-%m-%d_%H-%M-%S.mp3"))
        if fayl:
            try:
                yol = self.yuklab_ol(*fayl)
                self.yoz(f"💾 Kompyuterga saqlandi:\n{yol}")
                print(f"📱 Telefondan fayl keldi: {yol}")
            except Exception as xato:
                self.yoz(f"Faylni saqlab bo'lmadi: {xato}")
            if not matn:
                return

        if matn in ("/start", "/help", "/yordam"):
            self.yoz("Men kompyuteringizdagi Jarvis'man. Oddiy so'z bilan yozing, masalan:\n"
                     "• soat necha\n• youtubedan musiqa qo'y\n• yuklamalardagi rasmlarni tashla\n"
                     "• ish stolidagi hujjatlarni yubor\n• hisobot faylini yubor\n"
                     "• ekran rasmini yubor\n• yordam\n"
                     "Rasm, video yoki fayl yuborsangiz — kompyuterga saqlayman.")
            return
        if matn:
            self.xabar_keldi(matn)
