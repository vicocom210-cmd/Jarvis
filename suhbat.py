"""
API'siz suhbat: Jarvis oddiy gaplarga sun'iy intellektdek javob beradi.
Internet ham, pul ham, API kalit ham kerak emas.

Ishlashi: gapdagi kalit so'zlarга qarab mavzuni topadi va tayyor javoblardan
birini tasodifiy tanlaydi (shuning uchun har safar bir xil gapirmaydi).
Mos mavzu topilmasa, javob=None qaytadi — u holda boshqa yo'l (Vikipediya yoki
bepul API) sinaladi.
"""
import datetime
import random

ISM_JOY = "{ism}"          # javoblarda foydalanuvchi ismiga almashtiriladi

# Har bir mavzu: (kalit so'zlar, javoblar ro'yxati)
MAVZULAR = [
    (("rahmat", "raxmat", "tashakkur", "minnatdor", "spasibo"),
     ["Arzimaydi, {ism}! Xizmatingizdaman.",
      "Doim tayyorman, {ism}.",
      "Sizga yordam berish menga zavq beradi."]),

    (("qalaysan", "yaxshimisan", "ishlaring qalay", "naxotasan", "kayfiyating", "ahvoling",
      "yaxshimisiz", "tinchmisan"),
     ["Rahmat, {ism}, men doim shaymanman! O'zingiz qalaysiz?",
      "Zo'r, ishlashga tayyorman. Sizda nima gaplar?",
      "A'lo! Siz bilan gaplashish yoqadi. O'zingiz-chi?"]),

    (("kim yaratgan", "kim yasagan", "kim yozgan", "kim qilgan", "dasturching", "seni kim"),
     ["Meni {ism} o'zining yordamchisi bo'lishim uchun yaratdi.",
      "Men {ism} uchun yozilgan shaxsiy yordamchiman."]),

    (("isming nima", "kimsan", "sen kimsan", "o'zingni tanishtir", "sen nimasan"),
     ["Men Alisaman — {ism}ning ovozli yordamchisiman.",
      "Ismim Jarvis. Kompyuterda sizga yordam berish uchun shu yerdaman, {ism}."]),

    (("charchadim", "charcha", "toliqdim", "uxlagim", "uyqum", "horidim"),
     ["Biroz dam oling, {ism}. Men sizni kutaman.",
      "Charchagan bo'lsangiz, bir piyola choy yordam beradi. Yoki musiqa qo'yaymi?",
      "Dam olish ham ish. O'zingizni ayang, {ism}."]),

    (("zerikdim", "zerikyapman", "ich pusti", "nima qilsam"),
     ["Keling, kayfiyatingizni ko'taraman — kulgili video qo'yaymi?",
      "Zerikdingizmi? Menga bir savol bering, suhbatlashamiz. Yoki musiqa qo'yay?"]),

    (("sevaman", "yaxshi ko'raman", "zo'rsan", "ajoyibsan", "yaxshisan", "klass", "zo'r ekansan"),
     ["Rahmat, {ism}! Bu menga juda yoqdi.",
      "Siz ham zo'rsiz, {ism}!",
      "Xursand qildingiz. Yana nima qilay?"]),

    (("hazil", "latifa", "kuldir", "prikol", "anekdot"),
     ["Dasturchi kofe ichmasa nima bo'ladi? — Kod ishlamay qoladi!",
      "Kompyuter nega sovqotdi? — Chunki u derazasini (Windows) yopmadi!",
      "Bir bayt ikkinchisiga: charchagan ko'rinasan. — Ha, biroz bitli bo'lib qoldim!"]),

    (("qanday yordam", "nima qila olasan", "nimalarni bilasan", "yordaming", "imkoniyating"),
     ["Men dastur va saytlarni ochaman, fayl qidiraman, musiqa qo'yaman, "
      "Telegram va Instagramga xabar yozaman, kameradan surat olaman va savollarga javob beraman. "
      "Yordam desangiz, to'liq ro'yxatni aytaman."]),

    (("seni o'chirsam", "kerakmassan", "yomonsan", "ahmoq", "jinnisan"),
     ["Kechirasiz, agar xato qilgan bo'lsam. Yaxshiroq bo'lishga harakat qilaman.",
      "Sizni xafa qilgan bo'lsam, uzr, {ism}. Qanday yordam bera olaman?"]),

    (("sog' bo'l", "salomat bo'l", "yaxshi qol"),
     ["Siz ham sog' bo'ling, {ism}!", "Rahmat, o'zingiz ham salomat bo'ling!"]),

    (("qandaysan bugun", "bugun qanday", "kuning qalay"),
     ["Bugun kunim zo'r — siz bilan ishlayapman-ku! O'zingizning kuningiz qalay?"]),

    (("aqllimisan", "aqling bormi", "sun'iy intellekt", "ai misan", "robotmisan"),
     ["Men oddiy yordamchiman, {ism}. Sun'iy intellektga ulansam, yanada aqlliroq bo'laman.",
      "Hozircha oddiy dastur bo'lsam ham, sizga yordam berishga tayyorman."]),

    (("sog'indim", "yoningdaman", "zerikdim sensiz"),
     ["Men ham shu yerdaman, {ism}. Har doim chaqiring."]),
]

# Foydalanuvchining kayfiyatini bilish (his-tuyg'u)
XAFA_SOZLAR = ("xafaman", "yig'la", "yomon", "tushkun", "ruhim", "gam", "qayg'u", "yolg'iz")
XURSAND_SOZLAR = ("xursand", "baxtli", "zo'r kun", "yutdim", "muvaffaqiyat", "sevinib")


def salom_vaqt():
    soat = datetime.datetime.now().hour
    if soat < 6:
        return "Tun yarmi bo'ldi"
    if soat < 12:
        return "Xayrli tong"
    if soat < 18:
        return "Xayrli kun"
    return "Xayrli kech"


def javob(gap, ism="xo'jayin"):
    """Gapga mos suhbat javobini qaytaradi yoki None (mos mavzu topilmasa)."""
    g = " " + gap.lower() + " "
    sozlar = set(gap.lower().replace(",", " ").split())
    salomlar = {"salom", "assalom", "assalomu", "hello", "hi", "privet", "hayrli", "xayrli"}
    if sozlar & salomlar or "assalom" in g:
        j = f"{salom_vaqt()}, {ism}! Sizga qanday yordam bera olaman?"
        return j
    if any(s in g for s in XAFA_SOZLAR):
        return random.choice([
            f"Xafa bo'lmang, {ism}. Har qanday qiyinchilik o'tib ketadi.",
            f"Men yoningizdaman, {ism}. Kayfiyatingizni ko'tarish uchun biror narsa qo'yaymi?",
            "Chuqur nafas oling. Hammasi yaxshi bo'ladi."])
    if any(s in g for s in XURSAND_SOZLAR):
        return random.choice([
            f"Zo'r-ku, {ism}! Sizning xursandchiligingiz menga ham yuqdi.",
            f"Tabriklayman, {ism}! Shunday davom eting."])
    for kalitlar, javoblar in MAVZULAR:
        if any(k in g for k in kalitlar):
            return random.choice(javoblar).replace(ISM_JOY, ism).format(ism=ism)
    return None
