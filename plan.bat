@echo off
REM Планировщик визуальной новеллы - запуск в один клик (Windows)
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Окружение не найдено. Сначала запусти start.bat.
    pause
    exit /b 1
)

echo Открываю http://127.0.0.1:8420/plan.html
start "" http://127.0.0.1:8420/plan.html

".venv\Scripts\python.exe" run.py --no-browser
