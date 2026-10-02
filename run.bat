@echo off
setlocal
chcp 65001 >nul
set PYTHONUTF8=1
title Blaidd Drwg - Form Filler
cd /d "%~dp0"

echo Blaidd Drwg - Form Filler
echo Use only on forms and accounts you are allowed to use. See README - Disclaimer.
echo.

if not exist "venv\Scripts\activate.bat" (
    echo First-time setup is not done yet.
    echo Please double-click install.bat first.
    echo.
    pause
    exit /b 1
)

REM --- Read the bot token from token.txt (first line) ---
if not exist "token.txt" (
    echo.
    echo token.txt not found in this folder.
    echo Run install.bat, or create token.txt and paste ONLY your BotFather token inside it.
    echo.
    pause
    exit /b 1
)
set /p BOT_TOKEN=<token.txt

echo %BOT_TOKEN%| find ":" >nul
if errorlevel 1 (
    echo.
    echo token.txt does not contain a valid token. It should look like 123456789:ABCdef...
    echo.
    pause
    exit /b 1
)

REM --- Only these Telegram IDs may use the bot (created by install.bat) ---
if exist "allowed_ids.txt" set /p ALLOWED_IDS=<allowed_ids.txt

call venv\Scripts\activate.bat

echo Starting bot... (close this window to stop it)
python bot.py

echo.
echo Bot stopped.
pause
