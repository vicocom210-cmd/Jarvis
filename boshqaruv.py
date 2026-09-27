"""
Ilova ichida ishlash: tugmani nomi bo'yicha bosish, matn yozish, klaviatura tugmalari.

Tugmani topishning ikki yo'li (ketma-ket sinaladi):
  1) Windows UI Automation — oddiy dasturlar tugmalarining nomini Windows'ga aytib turadi.
     ("uiautomation" kutubxonasi kerak: pip install uiautomation)
  2) Ekrandagi yozuvni o'qish (OCR) — o'yinlar va maxsus dizaynli dasturlar uchun.
     Ekran rasmi olinadi, Windows'ning o'z matn tanish vositasi (Windows.Media.Ocr)
     yozuvlarni o'qiydi, kerakli yozuv ustiga sichqoncha bilan bosiladi.
     Qo'shimcha dastur shart emas (Windows 10/11 da bor).
"""
import difflib
import os
import re
import subprocess
import tempfile
import time

KONSOLSIZ = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Nomi aytilsa, qidirmasdan klaviaturadan bosiladigan tugmalar
KLAVISHLAR = {"enter": "enter", "ентер": "enter", "entr": "enter", "esc": "esc", "escape": "esc",
              "probel": "space", "space": "space", "tab": "tab", "backspace": "backspace",
              "delete": "delete", "f5": "f5", "f11": "f11", "yuqori": "up", "pastki": "down",
              "chap": "left", "o'ng": "right"}

OCR_SKRIPT = r'''
param([string]$yol)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Kut($amal, $tur) {
    $vazifa = $asTask.MakeGenericMethod($tur).Invoke($null, @($amal))
    $vazifa.Wait(-1) | Out-Null
    $vazifa.Result
}
$fayl = Kut ([Windows.Storage.StorageFile]::GetFileFromPathAsync($yol)) ([Windows.Storage.StorageFile])
$oqim = Kut ($fayl.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$dekoder = Kut ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($oqim)) ([Windows.Graphics.Imaging.BitmapDecoder])
$rasm = Kut ($dekoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$motor = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
$natija = Kut ($motor.RecognizeAsync($rasm)) ([Windows.Media.Ocr.OcrResult])
$q = 0
foreach ($qator in $natija.Lines) {
    foreach ($s in $qator.Words) {
        $r = $s.BoundingRect
        "{0}`t{1}`t{2}`t{3}`t{4}`t{5}" -f $q, $s.Text, [int]$r.X, [int]$r.Y, [int]$r.Width, [int]$r.Height
    }
    $q++
}
'''


def _toza(matn):
    return re.sub(r"[^\w' ]", " ", matn.lower()).split()


def _oxshashlik(a, b):
    return difflib.SequenceMatcher(None, " ".join(_toza(a)), " ".join(_toza(b))).ratio()


# ---------- 1) Windows UI Automation ----------
def uia_bilan_bos(nom, vaqt_chegarasi=4):
    """Faol oynadan nomi mos tugmani topib bosadi. Bosilsa True."""
    try:
        import uiautomation as auto
    except ImportError:
        return False
    try:
        oyna = auto.GetForegroundControl()
        if oyna is None or oyna.Name == "Jarvis":
            return False
        tugash = time.time() + vaqt_chegarasi
        eng_yaxshi, eng_ball = None, 0.0
        for boshqaruv, _ in auto.WalkControl(oyna, maxDepth=15):
            if time.time() > tugash:
                break
            nomi = boshqaruv.Name or ""
            if not nomi or len(nomi) > 80:
                continue
            ball = _oxshashlik(nom, nomi)
            if ball > eng_ball:
                eng_yaxshi, eng_ball = boshqaruv, ball
            if ball > 0.95:
                break
        if eng_yaxshi is not None and eng_ball >= 0.75:
            eng_yaxshi.Click(simulateMove=False)
            return True
    except Exception as xato:
        print(f"(UI Automation xatosi: {xato})")
    return False


# ---------- 2) Ekrandagi yozuvni o'qish (OCR) ----------
def ekran_sozlari(rasm_yoli):
    """Ekran rasmidagi so'zlar: [(qator_raqami, soz, x, y, eni, boyi), ...]"""
    skript = os.path.join(tempfile.gettempdir(), "jarvis_ocr.ps1")
    with open(skript, "w", encoding="utf-8-sig") as f:
        f.write(OCR_SKRIPT)
    natija = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", skript, "-yol", rasm_yoli],
        capture_output=True, timeout=40, creationflags=KONSOLSIZ)
    sozlar = []
    for qator in natija.stdout.decode("utf-8", "ignore").splitlines():
        qismlar = qator.split("\t")
        if len(qismlar) == 6:
            try:
                sozlar.append((int(qismlar[0]), qismlar[1], *map(int, qismlar[2:])))
            except ValueError:
                pass
    if not sozlar and natija.stderr:
        print("(OCR xatosi:", natija.stderr.decode("utf-8", "ignore")[:300], ")")
    return sozlar


def yozuvni_top(nom, sozlar):
    """Ekrandagi so'zlar ichidan nomga eng mos ketma-ketlikni topadi -> (x, y) markazi."""
    kerak = _toza(nom)
    if not kerak:
        return None
    qatorlar = {}
    for q, soz, x, y, e, b in sozlar:
        qatorlar.setdefault(q, []).append((soz, x, y, e, b))
    eng_yaxshi, eng_ball = None, 0.0
    for sozlar_ in qatorlar.values():
        for uzunlik in {len(kerak), len(kerak) - 1, len(kerak) + 1} - {0}:
            for i in range(0, max(1, len(sozlar_) - uzunlik + 1)):
                bolak = sozlar_[i:i + uzunlik]
                if not bolak:
                    continue
                ball = _oxshashlik(nom, " ".join(s[0] for s in bolak))
                if ball > eng_ball:
                    x1 = min(s[1] for s in bolak)
                    y1 = min(s[2] for s in bolak)
                    x2 = max(s[1] + s[3] for s in bolak)
                    y2 = max(s[2] + s[4] for s in bolak)
                    eng_yaxshi, eng_ball = ((x1 + x2) // 2, (y1 + y2) // 2), ball
    return eng_yaxshi if eng_ball >= 0.75 else None


def ocr_bilan_bos(nom):
    import pyautogui
    rasm = os.path.join(tempfile.gettempdir(), "jarvis_ocr.png")
    pyautogui.screenshot(rasm)
    joy = yozuvni_top(nom, ekran_sozlari(rasm))
    if joy:
        pyautogui.click(*joy)
        return True
    return False


# ---------- umumiy ----------
def tugmani_bos(nom):
    """'enter the game' tugmasini bosadi. Natija: 'klavish', 'uia', 'ocr' yoki None."""
    import pyautogui
    kalit = nom.lower().strip()
    if kalit in KLAVISHLAR:
        pyautogui.press(KLAVISHLAR[kalit])
        return "klavish"
    if uia_bilan_bos(nom):
        return "uia"
    try:
        if ocr_bilan_bos(nom):
            return "ocr"
    except Exception as xato:
        print(f"(OCR bilan bosib bo'lmadi: {xato})")
    return None


def kalitlardan_bos(kalitlar, rasm_yoli=None):
    """Ekrandagi yozuvlar ichidan berilgan kalit so'zlardan birini topib bosadi.
    Bir marta ekran o'qiladi (tez). Bosilsa True."""
    import pyautogui
    if rasm_yoli is None:
        rasm_yoli = os.path.join(tempfile.gettempdir(), "jarvis_ocr.png")
        pyautogui.screenshot(rasm_yoli)
    sozlar = ekran_sozlari(rasm_yoli)
    for kalit in kalitlar:
        joy = yozuvni_top(kalit, sozlar)
        if joy:
            pyautogui.click(*joy)
            return True
    return False


def faol_oyna_nomi():
    """Hozir oldinda turgan oynaning sarlavhasi."""
    if os.name != "nt":
        return ""
    import ctypes
    u32 = ctypes.windll.user32
    hwnd = u32.GetForegroundWindow()
    uzunlik = u32.GetWindowTextLengthW(hwnd)
    joy = ctypes.create_unicode_buffer(uzunlik + 1)
    u32.GetWindowTextW(hwnd, joy, uzunlik + 1)
    return joy.value


def matn_yoz(matn):
    """Faol maydonga matn yozadi (o'zbekcha va kirill harflari ham to'g'ri chiqadi)."""
    import pyautogui
    import pyperclip
    pyperclip.copy(matn)
    pyautogui.hotkey("ctrl", "v")
