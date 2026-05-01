@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ============================================
echo  Kompilacja VBS GUI
echo ============================================
echo.

:: Sprawdź Pythona
python --version >nul 2>&1
if errorlevel 1 (
    echo [BLAD] Python nie jest zainstalowany lub nie jest w PATH.
    pause
    exit /b 1
)

:: Zainstaluj PyInstaller jeśli brakuje
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Instalacja PyInstaller...
    pip install pyinstaller
)

:: Zainstaluj Pillow jeśli brakuje (potrzebne do konwersji ikony)
python -c "import PIL" >nul 2>&1
if errorlevel 1 (
    echo [INFO] Instalacja Pillow...
    pip install pillow
)

:: Konwertuj ikona.png -> ikona.ico
echo [INFO] Konwersja ikony...
python -c "from PIL import Image; img = Image.open('ikona.png'); img.save('ikona.ico', format='ICO', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"
if errorlevel 1 (
    echo [BLAD] Nie udalo sie skonwertowac ikony.
    pause
    exit /b 1
)

:: Kompilacja
echo.
echo [INFO] Kompilacja...
echo.
pyinstaller --onedir --windowed --icon=ikona.ico --name=VBS --clean vbs_gui.py

if errorlevel 1 (
    echo.
    echo [BLAD] Kompilacja nieudana.
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Gotowe! Plik: dist\VBS_GUI.exe
echo ============================================
echo.

:: Otwórz folder dist
explorer dist

pause
