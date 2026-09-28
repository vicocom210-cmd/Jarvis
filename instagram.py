"""
Instagram — RASMIY API orqali (parol emas, akkaunt bloklanmaydi):
  • Reels / video joylash (fayl kompyuterdan to'g'ridan-to'g'ri yuklanadi — internetga
    oldindan qo'yish shart emas: "resumable upload")
  • oxirgi postlar, izohlarni o'qish va javob yozish
  • statistika (ko'rishlar, layklar, obunachilar)

Ikki xil kalit (token) bilan ishlaydi — Jarvis o'zi aniqlaydi:
  "IG..."  — Instagram API with Instagram Login (Facebook sahifasi shart emas)   -> graph.instagram.com
  "EAA..." — Instagram API with Facebook Login (Facebook sahifasiga bog'langan)   -> graph.facebook.com
Instagram akkaunti Professional (Creator yoki Business) bo'lishi kerak.
Qo'shimcha kutubxona shart emas — urllib.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

VIDEO_TURLARI = (".mp4", ".mov", ".m4v")
RASM_TURLARI = (".jpg", ".jpeg", ".png")


class InstagramXato(Exception):
    pass


def _xato_matni(tana):
    """Meta xatosini tushunarli qilib beradi."""
    try:
        x = json.loads(tana).get("error", {})
    except (ValueError, AttributeError):
        return tana[:200]
    kod, xabar = x.get("code"), x.get("message", "")
    if kod == 190:
        return "Instagram kaliti (token) eskirgan yoki noto'g'ri — sozlamalarda yangisini qo'ying"
    if kod in (10, 200) or "permission" in xabar.lower():
        return "Ruxsat yetarli emas — token yaratishda kerakli ruxsatlarni belgilang (content_publish, comments, insights)"
    if kod == 9 or "limit" in xabar.lower():
        return "Instagram cheklovi: bugun juda ko'p joylandi — keyinroq urinib ko'ring"
    return f"Instagram: {xabar or tana[:200]}"


class Instagram:
    def __init__(self, token):
        self.token = (token or "").strip()
        self.ig_login = self.token.startswith("IG")         # Instagram Login tokeni (Facebook sahifasiz)
        self.asos = "https://graph.instagram.com" if self.ig_login else "https://graph.facebook.com"
        self.id = None
        self.username = None

    # --- ichki ---
    def _sorov(self, usul, yol, param=None, timeout=40):
        param = dict(param or {})
        param["access_token"] = self.token
        url = yol if yol.startswith("http") else f"{self.asos}/{yol.lstrip('/')}"
        malumot = None
        if usul == "GET":
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(param)
        else:
            malumot = urllib.parse.urlencode(param).encode()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=malumot, method=usul), timeout=timeout) as j:
                return json.loads(j.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as xato:
            raise InstagramXato(_xato_matni(xato.read().decode("utf-8", "ignore"))) from None
        except OSError as xato:
            raise InstagramXato(f"Instagram'ga ulanib bo'lmadi: {xato}") from None

    # --- ulanish ---
    def ulan(self):
        """Akkauntni topadi. (id, username) qaytaradi."""
        if self.ig_login:
            me = self._sorov("GET", "me", {"fields": "user_id,username"})
            self.id, self.username = str(me.get("user_id") or me.get("id")), me.get("username")
        else:
            sahifalar = self._sorov("GET", "me/accounts",
                                    {"fields": "name,instagram_business_account{id,username}"}).get("data", [])
            for s in sahifalar:
                ig = s.get("instagram_business_account")
                if ig:
                    self.id, self.username = ig["id"], ig.get("username")
                    break
            if not self.id:
                raise InstagramXato("Facebook sahifangizga Professional Instagram akkaunti bog'lanmagan")
        return self.id, self.username

    def akkaunt(self):
        return self._sorov("GET", self.id, {"fields": "username,followers_count,media_count"})

    # --- joylash ---
    def joyla(self, fayl, tavsif, holat=print):
        """Video (Reels) ni joylaydi. Media id qaytaradi."""
        if not fayl.lower().endswith(VIDEO_TURLARI):
            raise InstagramXato("Hozircha faqat video (Reels) joylanadi: .mp4 yoki .mov")
        hajm = os.path.getsize(fayl)
        idish = self._sorov("POST", f"{self.id}/media",
                            {"media_type": "REELS", "upload_type": "resumable", "caption": tavsif})
        cid = idish["id"]
        uri = idish.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{cid}"
        holat(f"Videoni yuklayapman ({hajm // (1024 * 1024)} MB)...")
        with open(fayl, "rb") as f:
            sorov = urllib.request.Request(uri, data=f.read(), method="POST", headers={
                "Authorization": f"OAuth {self.token}", "offset": "0", "file_size": str(hajm)})
        try:
            with urllib.request.urlopen(sorov, timeout=600) as j:
                javob = json.loads(j.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as xato:
            raise InstagramXato(_xato_matni(xato.read().decode("utf-8", "ignore"))) from None
        if javob.get("success") is False:
            raise InstagramXato(f"Video yuklanmadi: {javob}")
        holat("Instagram videoni tayyorlayapti...")
        for _ in range(60):                                   # 5 daqiqagacha kutamiz
            time.sleep(5)
            h = self._sorov("GET", cid, {"fields": "status_code,status"})
            if h.get("status_code") == "FINISHED":
                break
            if h.get("status_code") in ("ERROR", "EXPIRED"):
                raise InstagramXato(f"Instagram videoni qabul qilmadi: {h.get('status', '')} "
                                    "(format: MP4, H.264, 3 soniyadan 15 daqiqagacha, vertikal 9:16 tavsiya)")
        else:
            raise InstagramXato("Instagram videoni juda uzoq tayyorlayapti — keyinroq tekshiring")
        natija = self._sorov("POST", f"{self.id}/media_publish", {"creation_id": cid})
        return natija.get("id")

    # --- o'qish ---
    def postlar(self, soni=5):
        return self._sorov("GET", f"{self.id}/media", {
            "fields": "id,caption,media_type,timestamp,like_count,comments_count,permalink",
            "limit": soni}).get("data", [])

    def statistika(self, media_id):
        """Ko'rishlar va boshqalar. Metrika nomlari vaqti-vaqti bilan o'zgaradi — birma-bir sinaymiz."""
        natija = {}
        for metrika in ("views", "reach", "likes", "comments", "shares", "saved"):
            try:
                d = self._sorov("GET", f"{media_id}/insights", {"metric": metrika}).get("data", [])
                if d:
                    natija[metrika] = d[0].get("values", [{}])[0].get("value", d[0].get("total_value", {}).get("value"))
            except InstagramXato:
                continue
        return natija

    def izohlar(self, media_id, soni=10):
        return self._sorov("GET", f"{media_id}/comments",
                           {"fields": "id,text,username,timestamp", "limit": soni}).get("data", [])

    def javob_yoz(self, izoh_id, matn):
        return self._sorov("POST", f"{izoh_id}/replies", {"message": matn}).get("id")


def video_top(sozlar, papkalar):
    """Papkalardan video fayl topadi: nomida so'zlar bo'lsa — o'sha, bo'lmasa eng yangisi."""
    topilgan = []
    for papka in papkalar:
        try:
            for nom in os.listdir(papka):
                if nom.lower().endswith(VIDEO_TURLARI):
                    yol = os.path.join(papka, nom)
                    topilgan.append((os.path.getmtime(yol), yol))
        except OSError:
            continue
    if not topilgan:
        return None
    topilgan.sort(reverse=True)
    sozlar = [s for s in sozlar if len(s) > 2]
    for _, yol in topilgan:
        nom = os.path.basename(yol).lower()
        if sozlar and any(s in nom for s in sozlar):
            return yol
    return topilgan[0][1]
