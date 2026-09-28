"""
Jarvis belgisini (ikonkasini) chizadi: to'q doira ichida nurli, zarrachali 3D shar —
xuddi dasturdagi shar kabi. Natija:
  jarvis.ico  — EXE va o'rnatuvchi (Inno Setup) uchun (16..256 px, hammasi bitta faylda)
  jarvis.png  — 512 px rasm (xohlagan joyda ishlatish uchun)
Kerak: pip install pillow
"""
import math

from PIL import Image, ImageDraw, ImageFilter

K = 1024                                     # katta chizib, keyin kichraytiramiz — silliq chiqadi


def _fibonacci(n):
    oltin = math.pi * (3 - math.sqrt(5))
    for i in range(n):
        y = 1 - 2 * (i + 0.5) / n
        r = math.sqrt(1 - y * y)
        yield math.cos(oltin * i) * r, y, math.sin(oltin * i) * r


def belgi(olcham=K):
    s = olcham / K
    rasm = Image.new("RGBA", (olcham, olcham), (0, 0, 0, 0))
    cx = cy = olcham / 2

    # 1) to'q ko'k doira (fon) — och ish stolida ham, to'q ish stolida ham aniq ko'rinadi
    fon = Image.new("RGBA", (olcham, olcham), (0, 0, 0, 0))
    d = ImageDraw.Draw(fon)
    R_fon = 470 * s
    for i in range(60):                      # markazdan chetga qarab to'qlashadi
        t = i / 59
        r = R_fon * (1 - t)
        rang = (int(8 + 16 * t), int(14 + 26 * t), int(34 + 44 * t), 255)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=rang)
    d.ellipse((cx - R_fon, cy - R_fon, cx + R_fon, cy + R_fon), outline=(75, 208, 255, 150),
              width=max(1, int(10 * s)))
    rasm.alpha_composite(fon)

    # 2) sharning ichki nuri
    nur = Image.new("RGBA", (olcham, olcham), (0, 0, 0, 0))
    ImageDraw.Draw(nur).ellipse((cx - 250 * s, cy - 250 * s, cx + 250 * s, cy + 250 * s),
                                fill=(40, 140, 255, 110))
    rasm.alpha_composite(nur.filter(ImageFilter.GaussianBlur(90 * s)))

    # 3) zarrachalar — aylantirilgan va egilgan 3D shar; oldidagilari yirik va yorqin
    zar = Image.new("RGBA", (olcham, olcham), (0, 0, 0, 0))
    d = ImageDraw.Draw(zar)
    R = 330 * s
    a, e = 0.6, 0.38
    ca, sa, ce, se = math.cos(a), math.sin(a), math.cos(e), math.sin(e)
    nuqtalar = []
    for x, y, z in _fibonacci(620):
        x2, z2 = x * ca + z * sa, z * ca - x * sa
        y2, z3 = y * ce - z2 * se, y * se + z2 * ce
        nuqtalar.append((z3, x2, y2))
    for z3, x2, y2 in sorted(nuqtalar):          # orqadagilari birinchi chiziladi
        chuq = (z3 + 1) / 2                      # 0 = orqa, 1 = old
        r = (4 + 9 * chuq) * s
        px, py = cx + x2 * R, cy + y2 * R
        yorug = 0.35 + 0.65 * chuq
        rang = (int(30 + 120 * chuq * yorug), int(120 + 110 * chuq * yorug), 255,
                int(90 + 165 * chuq))
        d.ellipse((px - r, py - r, px + r, py + r), fill=rang)
    # zarrachalar atrofida yumshoq porlash
    porlash = zar.filter(ImageFilter.GaussianBlur(14 * s))
    rasm.alpha_composite(porlash)
    rasm.alpha_composite(zar)

    # 4) yaltiroq nuqta (chap-yuqorida)
    yal = Image.new("RGBA", (olcham, olcham), (0, 0, 0, 0))
    ImageDraw.Draw(yal).ellipse((cx - 190 * s, cy - 200 * s, cx - 30 * s, cy - 60 * s),
                                fill=(210, 245, 255, 70))
    rasm.alpha_composite(yal.filter(ImageFilter.GaussianBlur(40 * s)))
    return rasm


if __name__ == "__main__":
    katta = belgi()
    katta.resize((512, 512), Image.LANCZOS).save("jarvis.png")
    olchamlar = [256, 128, 64, 48, 32, 24, 16]
    rasmlar = [katta.resize((o, o), Image.LANCZOS) for o in olchamlar]
    rasmlar[0].save("jarvis.ico", sizes=[(o, o) for o in olchamlar], append_images=rasmlar[1:])
    print("jarvis.ico va jarvis.png tayyor")
