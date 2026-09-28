"""
Kamerada ODAM borligini aniqlash (shunchaki harakat emas).
NanoDet-Plus neyron tarmog'i (~4 MB, OpenCV, internetsiz): rasmdagi odamlarni to'rtburchak bilan topadi.
Mushuk, shamolda barg, soya, yorug'lik o'zgarishi — odam emas, ogohlantirish bermaydi.

Qayta ishlash kodi OpenCV Zoo'dagi NanoDet namunasidan moslashtirilgan (Apache-2.0):
https://github.com/opencv/opencv_zoo/tree/main/models/object_detection_nanodet
"""
import threading

import numpy as np

import yuz

ODAM_SINFI = 0                               # COCO ro'yxatida 0 — "person"


class OdamAniqlagich:
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
        self.net = cv2.dnn.readNet(yuz._model_yoli("odam"))
        self.olcham = (416, 416)
        self.qadamlar = (8, 16, 32, 64)
        self.reg_max = 7
        self.loyiha = np.arange(self.reg_max + 1)
        self.orta = np.array([103.53, 116.28, 123.675], dtype=np.float32).reshape(1, 1, 3)
        self.og = np.array([57.375, 57.12, 58.395], dtype=np.float32).reshape(1, 1, 3)
        self.ish_qulfi = threading.Lock()
        self.langarlar = []
        for q in self.qadamlar:
            h, w = self.olcham[0] // q, self.olcham[1] // q
            xv, yv = np.meshgrid(np.arange(w) * q, np.arange(h) * q)
            self.langarlar.append(np.column_stack((xv.flatten() + 0.5 * (q - 1), yv.flatten() + 0.5 * (q - 1))))

    def _letterbox(self, rasm):
        cv2 = self.cv2
        th, tw = self.olcham
        h, w = rasm.shape[:2]
        if h > w:
            nh, nw = th, int(tw * w / h)
            img = cv2.resize(rasm, (nw, nh), interpolation=cv2.INTER_AREA)
            chap, tepa = (tw - nw) // 2, 0
            img = cv2.copyMakeBorder(img, 0, 0, chap, tw - nw - chap, cv2.BORDER_CONSTANT, value=0)
        else:
            nh, nw = int(th * h / w), tw
            img = cv2.resize(rasm, (nw, nh), interpolation=cv2.INTER_AREA)
            chap, tepa = 0, (th - nh) // 2
            img = cv2.copyMakeBorder(img, tepa, th - nh - tepa, 0, 0, cv2.BORDER_CONSTANT, value=0)
        return img, (tepa, chap, nh, nw)

    def odamlar(self, rasm, ishonch=0.5):
        """Rasmdagi odamlar: [(x1, y1, x2, y2, ishonch), ...] — asl rasm koordinatalarida."""
        cv2 = self.cv2
        img, (tepa, chap, nh, nw) = self._letterbox(rasm)
        blob = cv2.dnn.blobFromImage((img.astype(np.float32) - self.orta) / self.og)
        with self.ish_qulfi:
            self.net.setInput(blob)
            chiqish = self.net.forward(self.net.getUnconnectedOutLayersNames())
        # Chiqishlar tartibi OpenCV versiyasiga qarab farq qiladi — o'lchami bo'yicha juftlaymiz:
        # sinflar (N, 80) va qutilar (N, 32); N — langarlar soni (qadam 8 -> 2704, 16 -> 676, 32 -> 169)
        chiqish = [c.squeeze(0) if c.ndim == 3 else c for c in chiqish]
        sinflar = {c.shape[0]: c for c in chiqish if c.shape[1] != 4 * (self.reg_max + 1)}
        qutilar_ = {c.shape[0]: c for c in chiqish if c.shape[1] == 4 * (self.reg_max + 1)}
        qutilar, ballar = [], []
        for q, langar in zip(self.qadamlar, self.langarlar):
            n = langar.shape[0]
            if n not in sinflar or n not in qutilar_:
                continue
            sinf, quti = sinflar[n], qutilar_[n]
            e = np.exp(quti.reshape(-1, self.reg_max + 1))
            masofa = (e / e.sum(axis=1, keepdims=True)).dot(self.loyiha).reshape(-1, 4) * q
            odam_ball = sinf[:, ODAM_SINFI]
            kerak = odam_ball >= ishonch * 0.8                 # faqat odam sinfi — tez
            if not kerak.any():
                continue
            m, l = masofa[kerak], langar[kerak]
            qutilar.append(np.column_stack([l[:, 0] - m[:, 0], l[:, 1] - m[:, 1],
                                            l[:, 0] + m[:, 2], l[:, 1] + m[:, 3]]))
            ballar.append(odam_ball[kerak])
        if not qutilar:
            return []
        qutilar, ballar = np.concatenate(qutilar), np.concatenate(ballar)
        wh = qutilar.copy()
        wh[:, 2:] -= wh[:, :2]
        tanlangan = cv2.dnn.NMSBoxes(wh.tolist(), ballar.tolist(), ishonch, 0.6)
        h, w = rasm.shape[:2]
        natija = []
        for i in np.array(tanlangan).flatten():
            x1, y1, x2, y2 = qutilar[i]
            natija.append((int(max(0, (x1 - chap) * w / nw)), int(max(0, (y1 - tepa) * h / nh)),
                           int(min(w, (x2 - chap) * w / nw)), int(min(h, (y2 - tepa) * h / nh)),
                           float(ballar[i])))
        return sorted(natija, key=lambda n: -n[4])


def belgila(rasm, odamlar):
    """Topilgan odamlarni rasmda yashil to'rtburchak bilan belgilaydi (xabar uchun)."""
    import cv2
    rasm = rasm.copy()
    for x1, y1, x2, y2, b in odamlar:
        cv2.rectangle(rasm, (x1, y1), (x2, y2), (60, 220, 90), 3)
        cv2.putText(rasm, f"odam {int(b * 100)}%", (x1 + 4, max(20, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (60, 220, 90), 2)
    return rasm
