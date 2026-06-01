@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"

title Qwen2OpenAI

echo.
echo  ╔═══════════════════════════════════════════════╗
echo  ║           Qwen2OpenAI v0.1.0                  ║
echo  ║     Qwen Studio ^> OpenAI-Compatible API      ║
echo  ╚═══════════════════════════════════════════════╝
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.10+ and try again.
    pause
    exit /b 1
)

if not exist "%~dp0.env" (
    echo [INFO] No .env file found. Setup wizard will start on first run.
)

echo [INFO] Checking dependencies...
python -m pip install -r "%~dp0requirements.txt" -q

REM Detect port from .env or default to 8000
set PORT=8000
if exist "%~dp0.env" (
    for /f "tokens=2 delims==" %%a in ('findstr /b "PORT=" "%~dp0.env"') do set PORT=%%a
)

REM Kill existing process on the port
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT%"') do (
    taskkill /F /PID %%a >nul 2>&1 && echo [OK] Killed old process on port %PORT%
)

echo.
python -m qwen2openai %*
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Qwen2OpenAI exited with code %errorlevel%
    pause
)
