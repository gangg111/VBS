@echo off
cd /d "%~dp0"
where pythonw >nul 2>&1 && (
    start "" pythonw vbs_gui.py
) || (
    where python >nul 2>&1 && (
        start "" pythonw vbs_gui.py 2>nul || python vbs_gui.py
    ) || (
        echo Nie znaleziono Pythona. Zainstaluj Python 3 i dodaj go do PATH.
        pause
    )
)
