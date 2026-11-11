@echo off
setlocal
cd /d "%~dp0"

if not exist .venv (
    py -3 -m venv .venv
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r requirements-build.txt

python -m PyInstaller --noconfirm --clean --windowed ^
  --name KEGE_Station ^
  --icon "assets\app_icon.ico" ^
  --add-data "assets;assets" ^
  --add-data "examples;examples" ^
  run.py

echo.
echo Готовая программа: dist\KEGE_Station\KEGE_Station.exe
if /I not "%~1"=="ci" pause
