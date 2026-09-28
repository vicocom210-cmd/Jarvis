"""
Yuzni tanish (OpenCV neyron tarmoqlari, internet shart emas):
  YuNet  — rasmda yuzni topadi
  SFace  — yuzning "barmoq izi"ni (128 ta son) chiqaradi va solishtiradi
Model fayllari birinchi marta avtomatik yuklab olinadi (%APPDATA%\\Jarvis\\modellar, ~39 MB).

Kimlar tanilishi: %APPDATA%\\Jarvis\\yuzlar.json — har bir odam uchun bir necha namuna.
Rasmlarning o'zi saqlanmaydi, faqat raqamli "barmoq izi".
"""
import json
import os
import sys
import threading
import time
import urllib.request

import sozlamalar

MODELLAR = {
    "aniqlash": ("face_detection_yunet_2023mar.onnx",
                 "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
                 "face_detection_yunet/face_detection_yunet_2023mar.onnx"),
    "tanish": ("face_recognition_sface_2021dec.onnx",
               "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
               "face_recognition_sface/face_recognition_sface_2021dec.onnx"),
}
MODEL_PAPKA = os.path.join(sozlamalar.PAPKA, "modellar")
BAZA_FAYL = os.path.join(sozlamalar.PAPKA, "yuzlar.json")

TANISH_CHEGARA = 0.363        # SFace tavsiyasi: shundan yuqori — o'sha odam
ESHIK_CHEGARA = 0.45          # eshik ochish uchun qattiqroq (xato ochilmasin)
KICHIK_YUZ = 60               # bundan kichik (uzoqdagi) yuzlar ishonchsiz — hisobga olinmaydi


def _model_yoli(kalit):
    nom, url = MODELLAR[kalit]
    for papka in (os.path.join(getattr(sys, "_MEIPASS", ""), "modellar"), MODEL_PAPKA):
        yol = os.path.join(papka, nom)
        if os.path.isfile(yol) and os.path.getsize(yol) > 100_000:
            return yol
    os.makedirs(MODEL_PAPKA, exist_ok=True)
    yol = os.path.join(MODEL_PAPKA, nom)
    print(f"(Yuz modeli yuklab olinyapti: {nom})")
    urllib.request.urlretrieve(url, yol + ".qism")
    os.replace(yol + ".qism", yol)
    return yol


class Tanuvchi:
    """Yuz topish va tanish. Bitta nusxa yetarli (modellar og'ir)."""
    _nusxa = None
    _qulf = threading.Lock()

    @classmethod
    def ol(cls):
        with cls._qulf:
            if cls._nusxa is None:
                cls._nusxa = cls()
            return cls._nusxa

    def __init__(self):
        import cv2
        self.cv2 = cv2
        self.aniqlagich = cv2.FaceDetectorYN.create(_model_yoli("aniqlash"), "", (320, 320), 0.8, 0.3, 5000)
        self.taniydigan = cv2.FaceRecognizerSF.create(_model_yoli("tanish"), "")
        self._ish_qulfi = threading.Lock()
        self.baza = self._yukla()

    # ----- baza -----
    def _yukla(self):
        try:
            with open(BAZA_FAYL, encoding="utf-8") as f:
                return {ism: [self._massiv(v) for v in namunalar] for ism, namunalar in json.load(f).items()}
        except (OSError, ValueError):
            return {}

    def _massiv(self, royxat):
        import numpy as np
        return np.array(royxat, dtype=np.float32).reshape(1, -1)

    def _saqla(self):
        os.makedirs(os.path.dirname(BAZA_FAYL), exist_ok=True)
        with open(BAZA_FAYL, "w", encoding="utf-8") as f:
            json.dump({ism: [v.flatten().round(6).tolist() for v in n] for ism, n in self.baza.items()}, f)

    def odamlar(self):
        return {ism: len(n) for ism, n in self.baza.items()}

    def ochir(self, ism):
        if self.baza.pop(ism, None) is not None:
            self._saqla()
            return True
        return False

    # ----- topish va tanish -----
    def yuzlar(self, rasm):
        """Rasmdagi yuzlar: [(quti(x,y,w,h), barmoq_izi, ishonch), ...] — kattasi birinchi."""
        cv2 = self.cv2
        bal = min(1.0, 960 / max(rasm.shape[:2]))            # katta kadrni kichraytirib qidiramiz
        kichik = cv2.resize(rasm, None, fx=bal, fy=bal) if bal < 1 else rasm
        with self._ish_qulfi:
            self.aniqlagich.setInputSize((kichik.shape[1], kichik.shape[0]))
            _, topilgan = self.aniqlagich.detect(kichik)
            natija = []
            for f in (topilgan if topilgan is not None else []):
                f = f.copy()
                f[:14] /= bal                                   # asl kadr koordinatalariga qaytaramiz
                x, y, w, h = (int(v) for v in f[:4])
                if min(w, h) < KICHIK_YUZ:
                    continue
                tekis = self.taniydigan.alignCrop(rasm, f)
                natija.append(((x, y, w, h), self.taniydigan.feature(tekis).copy(), float(f[14])))
        return sorted(natija, key=lambda n: -n[0][2] * n[0][3])

    def kim(self, barmoq_izi):
        """(ism, o'xshashlik 0..1) — eng o'xshashi. Baza bo'sh bo'lsa (None, 0)."""
        eng, ball = None, 0.0
        for ism, namunalar in self.baza.items():
            for n in namunalar:
                b = self.taniydigan.match(barmoq_izi, n, self.cv2.FaceRecognizerSF_FR_COSINE)
                if b > ball:
                    eng, ball = ism, b
        return eng, ball

    def qosh(self, ism, rasmlar):
        """Rasmlardan (har birida bitta asosiy yuz) odamni eslab qoladi. Qo'shilgan namunalar soni."""
        yangi = []
        for rasm in rasmlar:
            topilgan = self.yuzlar(rasm)
            if topilgan:
                iz = topilgan[0][1]
                # deyarli bir xil kadrlarni qayta qo'shmaymiz — turli burchaklar foydaliroq
                if all(self.taniydigan.match(iz, y, self.cv2.FaceRecognizerSF_FR_COSINE) < 0.93 for y in yangi):
                    yangi.append(iz)
        if yangi:
            self.baza.setdefault(ism, []).extend(yangi)
            self.baza[ism] = self.baza[ism][-30:]
            self._saqla()
        return len(yangi)


# ---------- Eshik oldini kuzatish: tanish yuz — eshik ochiladi ----------
class EshikQorovuli:
    """Kamerani kuzatadi. Tanish odam ketma-ket bir necha kadrda aniq tanilsa — eshikni ochadi.
    Notanish odam turib qolsa — rasm bilan xabar beradi."""

    def __init__(self, k, kadr_manbai, tanildi, notanish, ochsin=True,
                 kerakli_kadr=3, oyna=4.0, tanaffus=20, notanish_tanaffus=90):
        self.k = k
        self.kadr_manbai = kadr_manbai            # () -> kadrlar generatori (numpy rasmlar)
        self.tanildi = tanildi                    # (k, ism, ball, rasm, ochildi_mi) -> None
        self.notanish = notanish                  # (k, rasm) -> None
        self.ochsin = ochsin
        self.kerakli_kadr, self.oyna = kerakli_kadr, oyna
        self.tanaffus, self.notanish_tanaffus = tanaffus, notanish_tanaffus
        self.ketdi_soniya = 15                    # shuncha vaqt ko'rinmasa — "ketdi" deb hisoblaymiz
        self.ishlasin = True
        threading.Thread(target=self._ishla, daemon=True).start()

    def toxtat(self):
        self.ishlasin = False

    def _ishla(self):
        try:
            t = Tanuvchi.ol()
        except Exception as xato:
            print(f"(Yuz tanish ishga tushmadi: {xato})")
            return
        oxirgi_ochish = oxirgi_notanish = 0.0
        ochilgan_ism, oxirgi_korildi = None, 0.0     # eshik kimga ochildi va u oxirgi marta qachon ko'rindi
        while self.ishlasin:
            dalillar = []                         # [(vaqt, ism)] — ketma-ket tanishlar
            notanish_kadr = 0
            try:
                for rasm in self.kadr_manbai(lambda: self.ishlasin):
                    hozir = time.time()
                    yuzlar = t.yuzlar(rasm)
                    if not yuzlar:
                        notanish_kadr = 0
                        continue
                    ism, ball = t.kim(yuzlar[0][1])
                    if ism and ball >= ESHIK_CHEGARA:
                        dalillar = [d for d in dalillar if hozir - d[0] < self.oyna and d[1] == ism]
                        dalillar.append((hozir, ism))
                        notanish_kadr = 0
                        # Eshik ochilgan odam hali eshik oldida turibdi — qayta-qayta ochmaymiz.
                        # U ketdi_soniya dan ko'p ko'rinmay qolib, qaytib kelsa — yana ochiladi.
                        if ism == ochilgan_ism:
                            if hozir - oxirgi_korildi >= self.ketdi_soniya:
                                ochilgan_ism = None               # ketib, qaytib keldi
                            oxirgi_korildi = hozir
                        hali_shu_yerda = ism == ochilgan_ism
                        if len(dalillar) >= self.kerakli_kadr and hozir - oxirgi_ochish > self.tanaffus \
                                and not hali_shu_yerda:
                            oxirgi_ochish = oxirgi_korildi = hozir
                            ochilgan_ism = ism
                            dalillar = []
                            self.tanildi(self.k, ism, ball, rasm, self.ochsin)
                    elif not ism or ball < TANISH_CHEGARA:
                        notanish_kadr += 1
                        if notanish_kadr >= 4 and hozir - oxirgi_notanish > self.notanish_tanaffus:
                            oxirgi_notanish = hozir
                            self.notanish(self.k, rasm)
            except Exception as xato:
                print(f"(Eshik qorovuli xatosi: {xato})")
            for _ in range(10):                   # kamera uzildi — biroz kutib qayta ulanamiz
                if not self.ishlasin:
                    return
                time.sleep(1)
