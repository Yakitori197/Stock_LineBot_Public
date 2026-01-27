@echo off
title Stock LINE Bot

echo ==================================================
echo   Stock LINE Bot - Starting...
echo ==================================================
echo.

REM ====================================
REM IMPORTANT: Modify these paths!
REM ====================================
set PROJECT_PATH=%~dp0
set NGROK_PATH=%~dp0ngrok.exe

cd /d %PROJECT_PATH%

echo [1/3] Activating virtual environment...
call venv\Scripts\activate

echo [2/3] Starting ngrok...
start "ngrok" "%NGROK_PATH%" http 5000

timeout /t 3 /nobreak >nul

echo [3/3] Starting LINE Bot...
echo.
echo ==================================================
echo   Bot is running!
echo   Press Ctrl+C to stop
echo ==================================================
echo.

python src/app.py

echo.
echo Closing ngrok...
taskkill /FI "WINDOWTITLE eq ngrok" /F >nul 2>&1

echo.
echo Bot stopped. Press any key to close...
pause >nul
