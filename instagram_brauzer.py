"""
Instagram — ORQA FONDA joylash: Jarvis'ning alohida brauzeri (Microsoft Edge) ekrandan tashqarida
ishlaydi, sichqoncha va klaviaturangizni ishlatmaydi — shu paytda kompyuterdan bemalol foydalanasiz.

Kirish: bir marta "Instagram'ga kirish" tugmasi Instagram'ning O'Z sahifasini ochadi, u yerga o'zingiz
kirasiz. Jarvis parolni ko'rmaydi va saqlamaydi — brauzer profili faqat "kirilgan" holatni eslab qoladi
(%APPDATA%\\Jarvis\\instagram_brauzer). Uzish — profil papkasi o'chiriladi.

Kutubxona: pip install playwright   (brauzer yuklanmaydi — Windows'dagi Edge ishlatiladi)
"""
import os
import re
import shutil
import threading
import time

import sozlamalar

PROFIL = os.path.join(sozlamalar.PAPKA, "instagram_brauzer")
XATO_RASMI = os.path.join(sozlamalar.PAPKA, "instagram_xato.png")
ASOSIY = "https://www.instagram.com/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0")

# Sahifadagi tugmalar (ingliz / rus / o'zbek / turk)
YARAT = re.compile(r"^(New post|Create|Создать|Новая публикация|Yaratish|Yangi post|Oluştur|Yeni gönderi)$", re.I)
POST = re.compile(r"^(Post|Публикация|Post|Gönderi)$", re.I)
TANLA = re.compile(r"(Select from computer|Выбрать на компьютере|Kompyuterdan|Bilgisayardan seç)", re.I)
KEYINGI = re.compile(r"^(Next|Далее|Keyingi|İleri)$", re.I)
ULASH = re.compile(r"^(Share|Поделиться|Ulashish|Paylaş)$", re.I)
OK = re.compile(r"^(OK|ОК|Tamam)$", re.I)
KEYIN = re.compile(r"^(Not now|Не сейчас|Keyinroq|Şimdi değil)$", re.I)
TAVSIF = ('div[contenteditable="true"][aria-label]', 'div[role="textbox"][contenteditable="true"]',
          'textarea[aria-label]')
TAYYOR = re.compile(r"(has been shared|been shared|опубликован|опубликовано|paylaşıldı|ulashildi)", re.I)

_qulf = threading.Lock()                     # bir vaqtda bitta brauzer (profil bitta)


class InstaBrauzerXato(Exception):
    pass


def bormi():
    try:
        import importlib
        importlib.import_module("playwright.sync_api")
        return True
    except Exception:
        return False


def _ochish(p, korinsin, brauzer_yoli=None):
    """Jarvis profili bilan brauzer. korinsin=False — ekrandan tashqarida (sizga xalaqit bermaydi)."""
    os.makedirs(PROFIL, exist_ok=True)
    args = ["--disable-blink-features=AutomationControlled", "--no-first-run", "--no-default-browser-check"]
    if not korinsin:
        args += ["--window-position=-32000,-32000", "--window-size=1280,900"]
    sozlama = dict(user_data_dir=PROFIL, headless=False, args=args, viewport={"width": 1280, "height": 900},
                   user_agent=UA, locale="en-US")
    if brauzer_yoli:
        sozlama["executable_path"] = brauzer_yoli
    else:
        for kanal in ("msedge", "chrome"):                  # Windows'da Edge doim bor
            try:
                return p.chromium.launch_persistent_context(channel=kanal, **sozlama)
            except Exception as xato:
                oxirgi = xato
        raise InstaBrauzerXato(f"Edge yoki Chrome topilmadi: {oxirgi}")
    return p.chromium.launch_persistent_context(**sozlama)


def _kirganmi(kontekst):
    return any(c.get("name") == "sessionid" and c.get("value") for c in kontekst.cookies("https://www.instagram.com"))


def kirish_oynasi(daqiqa=5, brauzer_yoli=None):
    """Instagram'ning o'z kirish sahifasini ochadi — foydalanuvchi o'zi kiradi. Kirilsa True."""
    from playwright.sync_api import sync_playwright
    with _qulf, sync_playwright() as p:
        k = _ochish(p, korinsin=True, brauzer_yoli=brauzer_yoli)
        try:
            sahifa = k.pages[0] if k.pages else k.new_page()
            sahifa.goto(ASOSIY + "accounts/login/", wait_until="domcontentloaded")
            tugash = time.time() + daqiqa * 60
            while time.time() < tugash:
                if _kirganmi(k):
                    time.sleep(3)                                # "ma'lumotni saqlaymi" va h.k. yakunlansin
                    return True
                if not k.pages:                                  # foydalanuvchi oynani yopdi
                    return _kirganmi(k)
                time.sleep(1.5)
            return _kirganmi(k)
        finally:
            try:
                k.close()
            except Exception:
                pass


def kirganmi(brauzer_yoli=None):
    from playwright.sync_api import sync_playwright
    with _qulf, sync_playwright() as p:
        k = _ochish(p, korinsin=False, brauzer_yoli=brauzer_yoli)
        try:
            return _kirganmi(k)
        finally:
            k.close()


def chiqish():
    shutil.rmtree(PROFIL, ignore_errors=True)


def _bos(sahifa, rol_nom, kutish=15, majburiy=True):
    """Rol (button/link) va nom bo'yicha ko'rinib turgan elementni kutib bosadi."""
    tugash = time.time() + kutish
    while time.time() < tugash:
        for rol in ("button", "link", "menuitem"):
            el = sahifa.get_by_role(rol, name=rol_nom)
            for i in range(el.count()):
                try:
                    if el.nth(i).is_visible():
                        el.nth(i).click()
                        return True
                except Exception:
                    continue
        # ba'zi tugmalar faqat belgi (svg aria-label)
        svg = sahifa.locator("svg[aria-label]")
        for i in range(svg.count()):
            try:
                if rol_nom.search(svg.nth(i).get_attribute("aria-label") or "") and svg.nth(i).is_visible():
                    svg.nth(i).click()
                    return True
            except Exception:
                continue
        time.sleep(0.5)
    if majburiy:
        raise InstaBrauzerXato(f"Sahifada tugma topilmadi: {rol_nom.pattern[:40]}")
    return False


def joyla(fayl, tavsif, holat=print, brauzer_yoli=None, ulashilsin=True):
    """Videoni orqa fonda joylaydi. Muvaffaqiyatli bo'lsa True."""
    from playwright.sync_api import sync_playwright
    with _qulf, sync_playwright() as p:
        k = _ochish(p, korinsin=False, brauzer_yoli=brauzer_yoli)
        sahifa = k.pages[0] if k.pages else k.new_page()
        try:
            if not _kirganmi(k):
                raise InstaBrauzerXato("Instagram'ga kirilmagan — sozlamalarda 'Instagram'ga kirish'ni bosing")
            holat("Instagram'ni orqa fonda ochyapman...")
            sahifa.goto(ASOSIY, wait_until="domcontentloaded")
            sahifa.wait_for_timeout(3000)
            for _ in range(2):                                   # "Bildirishnomalar"/"saqlash" oynalari
                _bos(sahifa, KEYIN, kutish=2, majburiy=False)
            _bos(sahifa, YARAT)
            _bos(sahifa, POST, kutish=3, majburiy=False)          # yangi menyuda "Post" bandi
            holat("Videoni yuklayapman...")
            fayl_maydoni = sahifa.locator('input[type="file"]')
            fayl_maydoni.first.wait_for(state="attached", timeout=15000)
            fayl_maydoni.first.set_input_files(fayl)
            _bos(sahifa, OK, kutish=6, majburiy=False)            # "Videolar Reels bo'lib joylanadi"
            _bos(sahifa, KEYINGI, kutish=60)                     # video yuklanguncha kutadi
            sahifa.wait_for_timeout(1500)
            _bos(sahifa, KEYINGI, kutish=30)
            sahifa.wait_for_timeout(1500)
            if tavsif:
                for tanlov in TAVSIF:
                    maydon = sahifa.locator(tanlov)
                    if maydon.count() and maydon.first.is_visible():
                        maydon.first.click()
                        sahifa.keyboard.insert_text(tavsif)
                        break
                else:
                    raise InstaBrauzerXato("Tavsif maydoni topilmadi")
            if not ulashilsin:
                return True
            holat("Ulashyapman...")
            _bos(sahifa, ULASH, kutish=20)
            tugash = time.time() + 180                           # 3 daqiqagacha — "ulashildi" yozuvi
            while time.time() < tugash:
                try:
                    if sahifa.get_by_text(TAYYOR).count():
                        return True
                except Exception:
                    pass
                sahifa.wait_for_timeout(2000)
            raise InstaBrauzerXato("Ulashildi degan yozuv chiqmadi — Instagram'da tekshirib ko'ring")
        except Exception:
            try:
                sahifa.screenshot(path=XATO_RASMI)               # nosozlikni topish uchun
            except Exception:
                pass
            raise
        finally:
            try:
                k.close()
            except Exception:
                pass
