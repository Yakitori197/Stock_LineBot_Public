@echo off
title Stop Stock LINE Bot

echo ==================================================
echo   Stopping Stock LINE Bot...
echo ==================================================
echo.

echo Closing ngrok...
taskkill /IM ngrok.exe /F >nul 2>&1

echo Closing Python...
taskkill /IM python.exe /F >nul 2>&1

echo.
echo All services stopped.
echo.
pause
