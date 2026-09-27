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

TIZIM = ("Sen Jarvis ismli shaxsiy ovozli yordamchisan. Foydalanuvchi ismi: {ism}. "
         "Hamisha {til_nomi} tilida, samimiy, qisqa (1-3 gap) javob ber. "
         "Sen kompyuterda dastur ochish, fayl qidirish, musiqa qo'yish kabi ishlarni "
         "bajara olasan, lekin bu suhbatda faqat savolga javob berayapsan.")
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


def _groq(savol, tizim):
    xabarlar = [{"role": "system", "content": tizim}]
    for rol, matn in tarix[-6:]:
        xabarlar.append({"role": rol, "content": matn})
    xabarlar.append({"role": "user", "content": savol})
    sarlavhalar = {"Authorization": "Bearer " + os.environ["GROQ_API_KEY"].strip(),
                   "Content-Type": "application/json"}
    xatolar = []
    for model in GROQ_MODELLAR:                              # biri ishlamasa, keyingisi
        try:
            natija = _sorov("https://api.groq.com/openai/v1/chat/completions",
                            {"model": model, "messages": xabarlar, "max_tokens": 400,
                             "temperature": 0.7}, sarlavhalar)
            return natija["choices"][0]["message"]["content"].strip()
        except RuntimeError as xato:
            xatolar.append(f"{model}: {xato}")
            if "HTTP 401" in str(xato) or "invalid_api_key" in str(xato):
                break                                       # kalit noto'g'ri — model almashtirish yordam bermaydi
    raise RuntimeError(" | ".join(xatolar))


def _gemini(savol, tizim):
    tarkib = []
    for rol, matn in tarix[-6:]:
        tarkib.append({"role": "user" if rol == "user" else "model",
                       "parts": [{"text": matn}]})
    tarkib.append({"role": "user", "parts": [{"text": savol}]})
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           "gemini-2.0-flash:generateContent?key=" + os.environ["GEMINI_API_KEY"])
    natija = _sorov(url, {"system_instruction": {"parts": [{"text": tizim}]},
                          "contents": tarkib}, {"Content-Type": "application/json"})
    return natija["candidates"][0]["content"]["parts"][0]["text"].strip()


def _claude(savol, tizim):
    xabarlar = [{"role": rol, "content": matn} for rol, matn in tarix[-6:]]
    xabarlar.append({"role": "user", "content": savol})
    natija = _sorov(
        "https://api.anthropic.com/v1/messages",
        {"model": "claude-haiku-4-5-20251001", "max_tokens": 400,
         "system": tizim, "messages": xabarlar},
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
            j = ishlovchi(savol, tizim)
            if j:
                tarix.append(("user", savol))
                tarix.append(("assistant", j))
                del tarix[:-12]                  # faqat oxirgi 6 juftni saqlaymiz
                return j
        except Exception as xato:
            print(f"(AI xatosi [{kalit}]: {xato})")
    return None
