@echo off
chcp 65001 >nul
title ZHS Fucker
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] venv not found. Please check the folder.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" main.py %*

echo.
echo ============================================
echo  Finished. Press any key to close.
echo ============================================
pause >nul
