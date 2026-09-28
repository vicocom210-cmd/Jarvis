"""
Jarvis sozlamalari: ovoz, til, rang, ism.
Kompyuterda saqlanadi (%APPDATA%\\Jarvis\\sozlamalar.json), qayta yoqilganda ham eslab qoladi.
"""
import json
import os

PAPKA = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "Jarvis")
FAYL = os.path.join(PAPKA, "sozlamalar.json")

# Har bir til uchun: Google tanish tili, ayol va erkak ovozi (edge-tts), Vikipediya
TILLAR = {
    "uz": {"nomi": "O'zbek", "google": "uz-UZ", "ayol": "uz-UZ-MadinaNeural",
           "erkak": "uz-UZ-SardorNeural"},
    "ru": {"nomi": "Русский", "google": "ru-RU", "ayol": "ru-RU-SvetlanaNeural",
           "erkak": "ru-RU-DmitryNeural"},
    "en": {"nomi": "English", "google": "en-US", "ayol": "en-US-JennyNeural",
           "erkak": "en-US-GuyNeural"},
    "de": {"nomi": "Deutsch", "google": "de-DE", "ayol": "de-DE-KatjaNeural",
           "erkak": "de-DE-ConradNeural"},
}

# Rang mavzulari: (kutish rangi, faol rang)
RANGLAR = {
    "kok":      {"nomi": "Ko'k",     "xira": (40, 95, 210),  "yorqin": (70, 205, 255)},
    "yashil":   {"nomi": "Yashil",   "xira": (30, 150, 90),  "yorqin": (80, 255, 170)},
    "qizil":    {"nomi": "Qizil",    "xira": (180, 40, 50),  "yorqin": (255, 90, 90)},
    "oltin":    {"nomi": "Oltin",    "xira": (190, 130, 30), "yorqin": (255, 200, 80)},
    "binafsha": {"nomi": "Binafsha", "xira": (110, 60, 200), "yorqin": (190, 130, 255)},
    "oq":       {"nomi": "Oq",       "xira": (130, 140, 160), "yorqin": (235, 245, 255)},
}

STANDART = {"ovoz": "ayol", "til": "uz", "rang": "kok", "ism": "Abdulloh",
            "telegram_token": "", "telegram_egasi": 0, "telefon_adres": "", "telefon_pin": "0000",
            "telefon_kanal": "", "shahar": "toshkent", "chat_avto": True,
            "groq_kalit": "", "mikrofon": "", "sezgirlik": 3,
            "claude_kalit": "", "claude_model": "claude-sonnet-5",
            "tga_api_id": "", "tga_api_hash": "", "tga_dostlar": [], "tga_hammasi": False,
            "ig_token": "", "ig_id": "", "ig_username": "", "ig_rejalar": [], "ig_korilgan": [], "ig_avto_ulash": False, "ig_brauzer_kirgan": False,
            "kameralar": [], "kamera_kuzatuv": False, "kamera_ovoz": False,
            "yuz_eshik": None, "yuz_eshik_och": True}      # None — hali tanlanmagan (o'zi yoqiladi)


def yukla():
    sozlama = dict(STANDART)
    try:
        with open(FAYL, encoding="utf-8") as f:
            sozlama.update(json.load(f))
    except (OSError, ValueError):
        pass
    # noto'g'ri qiymat bo'lsa, standartga qaytaramiz
    if sozlama["til"] not in TILLAR:
        sozlama["til"] = STANDART["til"]
    if sozlama["rang"] not in RANGLAR:
        sozlama["rang"] = STANDART["rang"]
    if sozlama["ovoz"] not in ("ayol", "erkak"):
        sozlama["ovoz"] = STANDART["ovoz"]
    return sozlama


def saqla(sozlama):
    try:
        os.makedirs(PAPKA, exist_ok=True)
        with open(FAYL, "w", encoding="utf-8") as f:
            json.dump(sozlama, f, ensure_ascii=False, indent=2)
    except OSError as xato:
        print(f"(Sozlamalar saqlanmadi: {xato})")
