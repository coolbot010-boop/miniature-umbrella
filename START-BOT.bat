@echo off
title Tradebot
cd /d "%~dp0"
echo Tradebot start... Sluit dit venster om de bot te stoppen.
echo.
where python >nul 2>nul
if %errorlevel%==0 (
    python bot.py live --ja
) else (
    py bot.py live --ja
)
echo.
echo De bot is gestopt. Lees de melding hierboven.
pause
