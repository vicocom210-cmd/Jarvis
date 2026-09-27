"""
Bepul sun'iy intellekt bilan suhbat (ixtiyoriy).
Kalit bo'lsa ishlaydi, bo'lmasa — suhbat.py va Vikipediya yetarli.

Qo'llab-quvvatlanadi (biri bo'lsa yetadi, ustuvorlik tartibida):
  GROQ_API_KEY      — Groq (bepul, tez, karta shart emas): https://console.groq.com
  GEMINI_API_KEY    — Google Gemini (bepul ta'rif): https://aistudio.google.com/apikey
  ANTHROPIC_API_KEY — Claude (pullik)

Qo'shimcha kutubxona shart emas — urllib orqali ishlaydi.
Suhbat xotirasi: oxirgi bir necha gap eslab qolinadi (ketma-ket savol berish mumkin).
"""
import json
import os
import urllib.error
import urllib.request

# Groq bepul modellari — biri ishlamasa, keyingisi sinaladi (eskirganlari olib tashlangan)
GROQ_MODELLAR = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant",
                 "meta-llama/llama-4-scout-17b-16e-instruct", "openai/gpt-oss-20b"]

TIZIM = ("Sen Jarvis ismli aqlli shaxsiy yordamchisan (Iron Man'dagi Jarvis kabi). "
         "Foydalanuvchi ismi: {ism}. Hamisha {til_nomi} tilida, samimiy va aniq javob ber. "
         "Javobing ovoz chiqarib o'qiladi: odatda 1-3 gap, murakkab savolda 4-5 gapgacha, "
         "ro'yxat va markdown belgilarisiz. Savol noaniq bo'lsa — taxmin qilma, qisqa "
         "aniqlashtiruvchi savol ber. O'rinli bo'lsa, bitta foydali maslahat qo'sh. "
         "Sen kompyuterda dastur ochish, fayl qidirish va ko'chirish, musiqa qo'yish, Telegramga "
         "yozish, ob-havo, valyuta kursi, eslatma qo'yish kabi ishlarni bajara olasan — foydalanuvchi "
         "shunga o'xshash narsa so'rasa, uni qanday buyruq bilan aytishni maslahat ber.")
TIL_NOMLARI = {"uz": "o'zbek", "ru": "rus", "en": "ingliz", "de": "nemis"}
tarix = []                       # [(rol, matn), ...] — oxirgi suhbat


def _sorov(url, malumot, sarlavhalar, timeout=30):
    xom = json.dumps(malumot).encode("utf-8")
    # Cloudflare (xato 1010) oddiy so'rovni bloklaydi — brauzerdek ko'rsatamiz
    sarlavhalar = dict(sarlavhalar)
    sarlavhalar.setdefault("User-Agent",
                           "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")
    sarlavhalar.setdefault("Accept", "application/json")
    sorov = urllib.request.Request(url, data=xom, headers=sarlavhalar)
    try:
        with urllib.request.urlopen(sorov, timeout=timeout) as javob:
            return json.loads(javob.read().decode("utf-8"))
    except urllib.error.HTTPError as xato:
        tana = xato.read().decode("utf-8", "ignore")[:400]      # xato sababini o'qiymiz
        raise RuntimeError(f"HTTP {xato.code}: {tana}")


def bormi():
    return bool(os.environ.get("GROQ_API_KEY") or os.environ.get("GEMINI_API_KEY")
                or os.environ.get("ANTHROPIC_API_KEY"))


def _groq(savol, tizim, oldingi, harorat=0.7):
    xabarlar = [{"role": "system", "content": tizim}]
    for rol, matn in oldingi:
        xabarlar.append({"role": rol, "content": matn})
    xabarlar.append({"role": "user", "content": savol})
    sarlavhalar = {"Authorization": "Bearer " + os.environ["GROQ_API_KEY"].strip(),
                   "Content-Type": "application/json"}
    xatolar = []
    for model in GROQ_MODELLAR:                              # biri ishlamasa, keyingisi
        try:
            natija = _sorov("https://api.groq.com/openai/v1/chat/completions",
                            {"model": model, "messages": xabarlar, "max_tokens": 400,
                             "temperature": harorat}, sarlavhalar)
            return natija["choices"][0]["message"]["content"].strip()
        except RuntimeError as xato:
            xatolar.append(f"{model}: {xato}")
            if "HTTP 401" in str(xato) or "invalid_api_key" in str(xato):
                break                                       # kalit noto'g'ri — model almashtirish yordam bermaydi
    raise RuntimeError(" | ".join(xatolar))


def _gemini(savol, tizim, oldingi, harorat=0.7):
    tarkib = []
    for rol, matn in oldingi:
        tarkib.append({"role": "user" if rol == "user" else "model",
                       "parts": [{"text": matn}]})
    tarkib.append({"role": "user", "parts": [{"text": savol}]})
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           "gemini-2.0-flash:generateContent?key=" + os.environ["GEMINI_API_KEY"])
    natija = _sorov(url, {"system_instruction": {"parts": [{"text": tizim}]},
                          "contents": tarkib,
                          "generationConfig": {"temperature": harorat}}, {"Content-Type": "application/json"})
    return natija["candidates"][0]["content"]["parts"][0]["text"].strip()


def _claude(savol, tizim, oldingi, harorat=0.7):
    xabarlar = [{"role": rol, "content": matn} for rol, matn in oldingi]
    xabarlar.append({"role": "user", "content": savol})
    natija = _sorov(
        "https://api.anthropic.com/v1/messages",
        {"model": "claude-haiku-4-5-20251001", "max_tokens": 400,
         "system": tizim, "messages": xabarlar, "temperature": harorat},
        {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
         "Content-Type": "application/json"})
    return natija["content"][0]["text"].strip()


def javob(savol, ism="xo'jayin", til="uz"):
    """Bepul/pullik AI bilan javob. Kalit bo'lmasa yoki xato bo'lsa — None."""
    tizim = TIZIM.format(ism=ism, til_nomi=TIL_NOMLARI.get(til, "o'zbek"))
    for kalit, ishlovchi in (("GROQ_API_KEY", _groq), ("GEMINI_API_KEY", _gemini),
                             ("ANTHROPIC_API_KEY", _claude)):
        if not os.environ.get(kalit):
            continue
        try:
            j = ishlovchi(savol, tizim, tarix[-6:])
            if j:
                tarix.append(("user", savol))
                tarix.append(("assistant", j))
                del tarix[:-12]                  # faqat oxirgi 6 juftni saqlaymiz
                return j
        except Exception as xato:
            print(f"(AI xatosi [{kalit}]: {xato})")
    return None


# ---------- Xabar muharriri (Telegram/Instagram xabarlari uchun) ----------
TAHRIR_TIZIM = (
    "Sen xabar muharririsan. Foydalanuvchi do'stiga yubormoqchi bo'lgan xabarni beradi. "
    "Uni {til_nomi} tilida imlo, tinish belgilari va katta-kichik harf xatolarisiz qayta yoz "
    "(o'zbekcha bo'lsa — lotin yozuvida, tutuq belgisi bilan: sun'iy, ma'lumot). "
    "Ma'nosini, ohangini va kim gapirayotganini O'ZGARTIRMA, yangi gap qo'shma, "
    "xabarga javob berma. Oxiriga mazmuniga mos 1-2 ta emoji qo'sh. "
    "Faqat tayyor xabarning o'zini qaytar: izohsiz, qo'shtirnoqsiz.")


def tahrir(matn, til="uz"):
    """Xabarni imlo xatosiz va emoji bilan qaytaradi. AI bo'lmasa yoki xato bo'lsa — None.
    Suhbat tarixiga aralashmaydi."""
    tizim = TAHRIR_TIZIM.format(til_nomi=TIL_NOMLARI.get(til, "o'zbek"))
    for kalit, ishlovchi in (("GROQ_API_KEY", _groq), ("GEMINI_API_KEY", _gemini),
                             ("ANTHROPIC_API_KEY", _claude)):
        if not os.environ.get(kalit):
            continue
        try:
            j = (ishlovchi(matn, tizim, [], harorat=0.2) or "").strip().strip('"“”«»').strip()
        except Exception as xato:
            print(f"(Tahrir xatosi [{kalit}]: {xato})")
            continue
        # AI xabarni "javob" qilib yubormasin: juda uzun yoki bo'sh bo'lsa — rad etamiz
        if j and len(j) <= len(matn) * 2 + 40:
            return j
    return None
