@echo off
setlocal EnableDelayedExpansion
title Blaidd Drwg - Form Filler - Installer
cd /d "%~dp0"

echo ==================================================
echo    BLAIDD DRWG - FORM FILLER : one-time setup
echo ==================================================
echo.
echo This installs everything the bot needs.
echo It can take a few minutes. Please do not close this window.
echo.

REM ---------- 1. Python 3.10+ (installed automatically if missing) ----------
call :find_python
if defined PY goto :python_ok

echo [1/5] Python was not found - installing it automatically...
call :install_python
call :find_python
if defined PY goto :python_ok

echo.
echo [X] Automatic Python install did not work.
echo     Please install it by hand:
echo       1. Download Python from https://www.python.org/downloads/
echo       2. Run the installer and TICK "Add python.exe to PATH" at the bottom.
echo       3. Double-click install.bat again.
echo.
start "" "https://www.python.org/downloads/"
pause
exit /b 1

:python_ok
echo [1/5] Python is ready.

REM ---------- 2. Private environment ----------
if not exist "venv\Scripts\activate.bat" (
    echo [2/5] Creating a private Python environment...
    %PY% -m venv venv
    if errorlevel 1 (
        echo [X] Could not create the environment.
        pause
        exit /b 1
    )
) else (
    echo [2/5] Environment already exists - reusing it.
)
call venv\Scripts\activate.bat

REM ---------- 3. Python packages ----------
echo [3/5] Installing packages...
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [X] Package install failed. Check your internet connection and try again.
    pause
    exit /b 1
)

REM ---------- 4. Chrome for the automation ----------
echo [4/5] Installing the browser component...
playwright install chrome
if errorlevel 1 (
    echo.
    echo [!] Could not install Chrome automatically.
    echo     Install Google Chrome normally from https://www.google.com/chrome/
    echo     or right-click install.bat and choose "Run as administrator".
    echo     Setup will continue.
    echo.
)

REM ---------- 5. Bot token + who may use the bot ----------
echo [5/5] Bot settings
echo.
if exist "token.txt" goto :have_token

echo Create your bot first if you have not:
echo   - Open Telegram, search for @BotFather, send /newbot, follow the steps.
echo   - BotFather gives you a token that looks like 123456789:ABCdef...
echo.
:ask_token
set "TOKEN="
set /p "TOKEN=Paste your bot token here and press Enter: "
if not defined TOKEN goto :ask_token
echo !TOKEN!| find ":" >nul
if errorlevel 1 (
    echo That does not look like a token. It must contain a colon. Try again.
    goto :ask_token
)
>token.txt echo !TOKEN!
echo Token saved to token.txt
:have_token

if exist "allowed_ids.txt" (
    echo.
    echo Access settings already exist in allowed_ids.txt - keeping them.
    echo To change them, delete allowed_ids.txt and run install.bat again.
    goto :finish
)

echo.
echo Who should be allowed to use the bot?
echo.
echo    [1] Only me  (recommended - safest)
echo    [2] Everyone (anyone who finds the bot can use it)
echo.
:ask_access
set "CHOICE="
set /p "CHOICE=Type 1 or 2 and press Enter: "
if "!CHOICE!"=="1" goto :only_me
if "!CHOICE!"=="2" goto :everyone
goto :ask_access

:everyone
>allowed_ids.txt echo all
echo.
echo [!] Everyone can use the bot. Remember that sign-in windows and form filling
echo     run on THIS computer, so only choose this if you trust your users.
goto :finish

:only_me
echo.
echo To find your numeric Telegram ID: open Telegram, message @userinfobot, copy the number.
echo You can enter several IDs separated by commas, for example 123456789,987654321
echo.
:ask_id
set "TGID="
set /p "TGID=Your Telegram ID: "
if not defined TGID goto :ask_id
echo !TGID!| findstr /r "^[0-9,][0-9, ]*$" >nul
if errorlevel 1 (
    echo IDs contain only numbers and commas. Try again.
    goto :ask_id
)
>allowed_ids.txt echo !TGID!
echo Saved. Only that ID can use the bot.

:finish
echo.
echo ==================================================
echo    Setup finished!
echo    Now double-click  run.bat  to start the bot.
echo ==================================================
echo.
pause
exit /b 0


REM =====================================================================
REM  Subroutines
REM =====================================================================

:find_python
REM Sets PY if a Python 3.10+ is available, otherwise leaves it empty.
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "PY=py -3"
    goto :eof
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "PY=python"
    goto :eof
)
REM Freshly installed Python is not on PATH until a new window is opened,
REM so also look in the default install folders.
for %%V in (313 312 311 310) do (
    if exist "%LocalAppData%\Programs\Python\Python%%V\python.exe" (
        "%LocalAppData%\Programs\Python\Python%%V\python.exe" -c "import sys" >nul 2>&1
        if not errorlevel 1 (
            set PY="%LocalAppData%\Programs\Python\Python%%V\python.exe"
            goto :eof
        )
    )
)
goto :eof

:install_python
REM Try 1: winget (built into Windows 10/11)
where winget >nul 2>&1
if errorlevel 1 goto :download_python
echo     Installing Python with winget...
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
call :find_python
if defined PY goto :eof

:download_python
REM Try 2: download the official installer from python.org
echo     Downloading Python from python.org...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile '%TEMP%\python-installer.exe'"
if errorlevel 1 goto :eof
echo     Installing Python (this can take a minute)...
start /wait "" "%TEMP%\python-installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0
del "%TEMP%\python-installer.exe" >nul 2>&1
goto :eof
