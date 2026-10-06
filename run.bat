@echo off
title Media-Downloader-Bot
cd /d "%~dp0"

echo ==============================================
echo      TELEGRAM SOCIAL MEDIA DOWNLOADER BOT
echo ==============================================
echo.

if not exist .env (
    if exist .env.example (
        copy .env.example .env
        echo Created .env template. Please configure your TELEGRAM_BOT_TOKEN!
    )
)

:: Create dedicated named executable so Task Manager displays 'media-downloader.exe' instead of generic 'python.exe'
for /f "delims=" %%i in ('where python') do set PYTHON_BIN=%%i & goto :found_py
:found_py

if not exist media-downloader.exe (
    copy "%PYTHON_BIN%" media-downloader.exe >nul
)

echo Starting Media Downloader Bot as [media-downloader.exe]...
media-downloader.exe bot.py
pause
