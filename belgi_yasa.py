"""
Jarvis.exe uchun belgi (ikonka) yasaydi: jarvis.ico — nurli ko'k shar.
EXE qurishdan oldin avtomatik ishlaydi (kerak: pip install pillow).
"""
import math

from PIL import Image, ImageDraw, ImageFilter

OLCHAM = 256


def shar():
    rasm = Image.new("RGBA", (OLCHAM, OLCHAM), (0, 0, 0, 0))
    # tashqi nur
    nur = Image.new("RGBA", (OLCHAM, OLCHAM), (0, 0, 0, 0))
    ImageDraw.Draw(nur).ellipse((20, 20, 236, 236), fill=(75, 208, 255, 140))
    rasm.alpha_composite(nur.filter(ImageFilter.GaussianBlur(16)))
    # shar: markazdan chetga qarab rang o'zgaradi
    tana = Image.new("RGBA", (OLCHAM, OLCHAM), (0, 0, 0, 0))
    p = tana.load()
    cx, cy, r = 128, 128, 96
    yorug = (96, 104)                                   # yorug' nuqta (chap-tepa)
    for y in range(OLCHAM):
        for x in range(OLCHAM):
            d = math.hypot(x - cx, y - cy)
            if d > r:
                continue
            t = math.hypot(x - yorug[0], y - yorug[1]) / (r * 1.6)
            t = min(1.0, t)
            ranglar = [(200, 245, 255), (75, 208, 255), (30, 90, 210), (14, 22, 60)]
            i = min(2, int(t * 3))
            k = t * 3 - i
            a, b = ranglar[i], ranglar[i + 1]
            chet = 255 if d < r - 1.5 else int(255 * (r - d) / 1.5)
            p[x, y] = tuple(int(a[j] + (b[j] - a[j]) * k) for j in range(3)) + (max(0, chet),)
    rasm.alpha_composite(tana)
    # zarrachalar halqasi
    chiz = ImageDraw.Draw(rasm)
    for i in range(48):
        burchak = i / 48 * 2 * math.pi
        x = cx + math.cos(burchak) * (r + 14)
        y = cy + math.sin(burchak) * (r + 14) * 0.42
        chiz.ellipse((x - 2.2, y - 2.2, x + 2.2, y + 2.2), fill=(170, 235, 255, 230))
    return rasm


if __name__ == "__main__":
    shar().save("jarvis.ico", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("jarvis.ico tayyor")
