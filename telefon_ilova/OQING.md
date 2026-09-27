# Jarvis telefon ilovasi (Android APK)

Bu — telefon uchun Jarvis. U:
- **O'zi suhbatlashadi** (Groq bepul kaliti bilan) — savol berasiz, javob beradi.
- **Kompyuterni boshqaradi** (💻 Kompyuter bo'limi) — bir Wi-Fi'dagi kompyuterdagi Jarvis'ga buyruq yuboradi.

## APK'ni qanday olish (Android Studio kerak emas)

1. Loyihani GitHub'ga yuklang (allaqachon yuklangan).
2. GitHub'da loyiha sahifasini oching → yuqoridagi **Actions** bo'limi.
3. **"Jarvis telefon APK"** ni tanlang → o'ngdagi **Run workflow** tugmasini bosing (yoki
   `telefon_ilova` papkasi o'zgarsa, avtomatik ishlaydi).
4. Yashil ✓ chiqqach, o'sha ishni bosing → pastdagi **Artifacts** bo'limidan **Jarvis-APK** ni yuklab oling.
5. ZIP ichidan `app-debug.apk` ni telefonga o'tkazing va o'rnating
   (telefonда "Noma'lum manbalardan o'rnatish"ga ruxsat bering).

## Sozlash (birinchi marta)

Ilovani ochib, o'ng yuqoridagi ⚙ tugmasini bosing:
- **Kompyuter IP** — kompyuterda Jarvis ishga tushganда konsolда ko'rsatiladi
  (masalan `192.168.1.5`). Telefon va kompyuter bir Wi-Fi'da bo'lsin.
- **PIN** — kompyuterdagi sozlamada belgilangan PIN (standart `0000`).
- **Groq kaliti** — telefon o'zi javob berishi uchun (ixtiyoriy, bepul).

## Ishlatish
- **💬 Suhbat** — savol yozing yoki 🎤 bosib gapiring, telefon o'zi javob beradi.
- **💻 Kompyuter** — tugmalarni bosing yoki buyruq yozing, kompyuter bajaradi.
