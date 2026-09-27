@echo off
REM Jarvis.exe ni o'z kompyuteringizda yasash (GitHub'dan yuklab olish ham mumkin).
REM Ikki marta bosing. Tayyor fayl: dist\Jarvis.exe
cd /d "%~dp0"
set PY="C:\Program Files (x86)\Python311-32\python.exe"
%PY% -m pip install pyinstaller pillow
%PY% belgi_yasa.py
%PY% -m PyInstaller --noconfirm --onefile --windowed --name Jarvis --icon jarvis.ico ^
  --add-data "chat.html;." --collect-data speech_recognition --collect-all uiautomation ^
  --collect-submodules shazamio --hidden-import pyaudio jarvis.py
echo.
echo Tayyor: dist\Jarvis.exe
pause
