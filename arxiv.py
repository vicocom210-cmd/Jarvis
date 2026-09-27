"""
Suhbat arxivi: siz va Jarvis o'rtasidagi har bir gap saqlanadi (ovoz, chat, telefon, Telegram).
Har kun alohida faylda: %APPDATA%\\Jarvis\\arxiv\\2026-09-27.jsonl
Chat oynasi (server.py -> /chat) shu yerdan o'qiydi.
"""
import collections
import datetime
import json
import os
import threading
import time

import sozlamalar

PAPKA = os.path.join(sozlamalar.PAPKA, "arxiv")
_qulf = threading.Lock()
_songgi = collections.deque(maxlen=500)     # jonli chat uchun oxirgi yozuvlar (xotirada)
_oxirgi_id = 0


def _fayl(sana):
    return os.path.join(PAPKA, f"{sana}.jsonl")


def yoz(kim, matn, manba=""):
    """kim: 'siz' yoki 'jarvis'. manba: ovoz, chat, telefon, telegram, yozuv."""
    global _oxirgi_id
    matn = (matn or "").strip()
    if not matn:
        return None
    with _qulf:
        _oxirgi_id = max(_oxirgi_id + 1, time.time_ns() // 1000)
        yozuv = {"id": _oxirgi_id, "vaqt": time.time(), "kim": kim, "matn": matn, "manba": manba}
        _songgi.append(yozuv)
        try:
            os.makedirs(PAPKA, exist_ok=True)
            with open(_fayl(datetime.date.today().isoformat()), "a", encoding="utf-8") as f:
                f.write(json.dumps(yozuv, ensure_ascii=False) + "\n")
        except OSError as xato:
            print(f"(Arxivga yozilmadi: {xato})")
    return yozuv


def keyin(oxirgi_id):
    """Jonli chat: shu id'dan keyingi yangi yozuvlar."""
    with _qulf:
        return [y for y in _songgi if y["id"] > oxirgi_id]


def kun(sana):
    """Bir kunning butun suhbati."""
    yozuvlar = []
    try:
        with open(_fayl(sana), encoding="utf-8") as f:
            for qator in f:
                try:
                    yozuvlar.append(json.loads(qator))
                except ValueError:
                    pass
    except OSError:
        pass
    return yozuvlar


def kunlar():
    """Arxivdagi kunlar (eng yangisi birinchi): [{sana, sarlavha, soni}, ...]"""
    try:
        fayllar = sorted((f[:-6] for f in os.listdir(PAPKA) if f.endswith(".jsonl")), reverse=True)
    except OSError:
        return []
    natija = []
    for sana in fayllar[:120]:
        yozuvlar = kun(sana)
        birinchi = next((y["matn"] for y in yozuvlar if y.get("kim") == "siz"), "")
        natija.append({"sana": sana, "sarlavha": birinchi[:48] or "Suhbat",
                       "soni": len(yozuvlar)})
    return natija


def qidir(soz, chegara=80):
    """Butun arxivdan so'z bo'yicha qidirish."""
    soz = (soz or "").lower().strip()
    if not soz:
        return []
    topildi = []
    for k in kunlar():
        for y in kun(k["sana"]):
            if soz in y.get("matn", "").lower():
                topildi.append(dict(y, sana=k["sana"]))
                if len(topildi) >= chegara:
                    return topildi
    return topildi


def ochir(sana):
    """Bir kunning arxivini o'chiradi."""
    try:
        os.remove(_fayl(sana))
        return True
    except OSError:
        return False
