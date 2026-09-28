@echo off
REM Jarvis.exe ni o'z kompyuteringizda yasash (GitHub'dan yuklab olish ham mumkin).
REM Ikki marta bosing. Tayyor fayl: dist\Jarvis.exe
cd /d "%~dp0"
set PY="C:\Program Files (x86)\Python311-32\python.exe"
%PY% -m pip install pyinstaller pillow pywebview anthropic telethon qrcode cryptography playwright
%PY% belgi_yasa.py
if not exist modellar mkdir modellar
curl -L -o modellar\face_detection_yunet_2023mar.onnx https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
curl -L -o modellar\face_recognition_sface_2021dec.onnx https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx
curl -L -o modellar\object_detection_nanodet_2022nov.onnx https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/object_detection_nanodet/object_detection_nanodet_2022nov.onnx
%PY% -m PyInstaller --noconfirm --onefile --windowed --name Jarvis --icon jarvis.ico ^
  --add-data "chat.html;." --add-data "jarvis.png;." --add-data "modellar;modellar" --collect-data speech_recognition --collect-all uiautomation ^
  --collect-submodules shazamio --collect-all webview --collect-submodules anthropic --collect-submodules telethon --hidden-import telegram_akkaunt --hidden-import qrcode --hidden-import instagram_brauzer --collect-all playwright --hidden-import clr --hidden-import pyaudio jarvis.py
echo.
echo Tayyor: dist\Jarvis.exe
echo O'rnatuvchi uchun: jarvis_setup.iss ni Inno Setup da oching va Compile bosing
pause
