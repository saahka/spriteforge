@echo off
REM SpriteForge - запуск в один клик (Windows)
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo [1/2] Создаю виртуальное окружение...
    py -3.13 -m venv .venv
    if errorlevel 1 (
        echo Не удалось создать окружение. Установите Python 3.11+ и повторите.
        pause
        exit /b 1
    )
    echo.
    echo [2/2] Ставлю зависимости, это займёт несколько минут...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Не удалось поставить зависимости.
        pause
        exit /b 1
    )
)

echo.
echo Запускаю SpriteForge на http://127.0.0.1:8420
echo Закрой это окно чтобы остановить сервер.
echo.
".venv\Scripts\python.exe" run.py %*
