"""
Tarjima: Jarvis ichida hamma narsa o'zbekcha ishlaydi.
Boshqa til tanlansa:  siz aytgan gap -> o'zbekchaga,  Jarvis javobi -> tanlangan tilga.
Google Translate'ning bepul manzilidan foydalanadi (kalit shart emas).
Internet bo'lmasa yoki xato bo'lsa, matn o'zgarmasdan qaytadi.
"""
import json
import urllib.parse
import urllib.request

_xotira = {}


def tarjima(matn, dan, ga):
    if not matn or dan == ga:
        return matn
    kalit = (matn, dan, ga)
    if kalit in _xotira:
        return _xotira[kalit]
    url = ("https://translate.googleapis.com/translate_a/single?client=gtx&dt=t"
           f"&sl={dan}&tl={ga}&q=" + urllib.parse.quote(matn))
    try:
        sorov = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(sorov, timeout=6) as javob:
            malumot = json.loads(javob.read().decode("utf-8"))
        natija = "".join(qism[0] for qism in malumot[0] if qism and qism[0]).strip()
    except Exception as xato:
        print(f"(Tarjima xatosi: {xato})")
        return matn
    if natija:
        _xotira[kalit] = natija
        return natija
    return matn
