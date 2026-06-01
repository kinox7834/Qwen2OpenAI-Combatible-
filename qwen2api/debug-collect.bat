@echo off
chcp 65001 >nul
echo ========================================
echo  Qwen2OpenAI Debug Info Collector
echo ========================================
echo.
echo Timestamp: %DATE% %TIME%
echo System: %COMPUTERNAME%
echo OS: %OS%
echo.
echo ===== Python =====
python --version 2>&1
pip --version 2>&1
echo.
echo ===== Project State =====
if exist .env (
    for /f "tokens=1,* delims==" %%a in (.env) do (
        if /i "%%a"=="QWEN_TOKENS" (
            echo QWEN_TOKENS=***redacted*** (len:%%~zb)
        ) else if /i "%%a"=="API_KEY" (
            echo API_KEY=***redacted*** (len:%%~zb)
        ) else (
            echo %%a=%%b
        )
    )
) else (
    echo .env: NOT FOUND
)
echo.
echo ===== Port Check =====
netstat -ano | findstr ":8000 "
echo.
echo ===== Server Health =====
curl -s http://127.0.0.1:8000/health 2>&1
echo.
echo ===== Models Endpoint =====
curl -s http://127.0.0.1:8000/v1/models 2>&1
echo.
echo ===== Debug Endpoint =====
curl -s http://127.0.0.1:8000/debug 2>&1
echo.
echo ===== Requirements =====
type requirements.txt 2>&1
echo.
echo ========================================
echo  Done.
echo ========================================
pause
