@echo off
REM Jarvis.exe ni o'z kompyuteringizda yasash (GitHub'dan yuklab olish ham mumkin).
REM Ikki marta bosing. Tayyor fayl: dist\Jarvis.exe
cd /d "%~dp0"
set PY="C:\Program Files (x86)\Python311-32\python.exe"
%PY% -m pip install pyinstaller pillow pywebview
%PY% belgi_yasa.py
%PY% -m PyInstaller --noconfirm --onefile --windowed --name Jarvis --icon jarvis.ico ^
  --add-data "chat.html;." --add-data "jarvis.png;." --collect-data speech_recognition --collect-all uiautomation ^
  --collect-submodules shazamio --collect-all webview --hidden-import clr --hidden-import pyaudio jarvis.py
echo.
echo Tayyor: dist\Jarvis.exe
echo O'rnatuvchi uchun: jarvis_setup.iss ni Inno Setup da oching va Compile bosing
pause
