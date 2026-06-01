@echo off
setlocal EnableDelayedExpansion

echo.
echo ================================================================
echo   S8-Assignment  START
echo ================================================================
echo.

:: ── 0. Locate this script's directory ────────────────────────────────────────
set "HERE=%~dp0"
set "WORKSPACE=%HERE%workspace"
set "GATEWAY_DIR=%WORKSPACE%\gateway"
set "CODE_DIR=%WORKSPACE%\code"
set "LOGS_DIR=%HERE%logs"

:: ── 1. Key rotation: read GEMINI_KEY_SLOT from .env ──────────────────────────
set "KEY_SLOT=1"
for /f "tokens=1,2 delims==" %%A in ('findstr /i "GEMINI_KEY_SLOT" "%HERE%.env" 2^>nul') do (
    set "KEY_SLOT=%%B"
)
echo [start] Using Gemini key slot: %KEY_SLOT%

:: Build the actual GEMINI_API_KEY from the slot
set "GEMINI_API_KEY="
if "%KEY_SLOT%"=="1" (
    for /f "tokens=1,2 delims==" %%A in ('findstr /i "^GEMINI_API_KEY=" "%HERE%.env" 2^>nul') do set "GEMINI_API_KEY=%%B"
)
if "%KEY_SLOT%"=="2" (
    for /f "tokens=1,2 delims==" %%A in ('findstr /i "^GEMINI_API_KEY_2=" "%HERE%.env" 2^>nul') do set "GEMINI_API_KEY=%%B"
)
if "%KEY_SLOT%"=="3" (
    for /f "tokens=1,2 delims==" %%A in ('findstr /i "^GEMINI_API_KEY_3=" "%HERE%.env" 2^>nul') do set "GEMINI_API_KEY=%%B"
)
if "%KEY_SLOT%"=="4" (
    for /f "tokens=1,2 delims==" %%A in ('findstr /i "^GEMINI_API_KEY_4=" "%HERE%.env" 2^>nul') do set "GEMINI_API_KEY=%%B"
)
if "%KEY_SLOT%"=="5" (
    for /f "tokens=1,2 delims==" %%A in ('findstr /i "^GEMINI_API_KEY_5=" "%HERE%.env" 2^>nul') do set "GEMINI_API_KEY=%%B"
)

:: ── 2. Run setup if workspace not ready ──────────────────────────────────────
if not exist "%GATEWAY_DIR%\main.py" (
    echo [start] Running first-time setup...
    python "%HERE%setup.py"
    if errorlevel 1 (
        echo ERROR: setup.py failed. Check output above.
        pause
        exit /b 1
    )
)

:: ── 3. Update .env in workspace with the selected Gemini key ─────────────────
:: Copy base .env then inject the selected key as GEMINI_API_KEY
copy /Y "%HERE%.env" "%WORKSPACE%\.env" >nul 2>&1
if not "%GEMINI_API_KEY%"=="" (
    :: Use PowerShell to safely update the key in workspace\.env
    powershell -NoProfile -Command ^
        "(Get-Content '%WORKSPACE%\.env') -replace '^GEMINI_API_KEY=.*','GEMINI_API_KEY=%GEMINI_API_KEY%' | Set-Content '%WORKSPACE%\.env'"
    echo [start] GEMINI_API_KEY set from slot %KEY_SLOT%
) else (
    echo [start] WARNING: GEMINI_API_KEY_!KEY_SLOT! is empty in .env
)

:: ── 4. Check Ollama ───────────────────────────────────────────────────────────
echo [start] Checking Ollama...
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [start] WARNING: Ollama not running. Embeddings may fail.
    echo         Install Ollama from https://ollama.com and run:
    echo           ollama pull nomic-embed-text
) else (
    echo [start] Ollama OK
)

:: ── 5. Kill any existing gateway ─────────────────────────────────────────────
taskkill /F /IM python.exe /FI "WINDOWTITLE eq llm_gateway*" >nul 2>&1
:: Alternative: look for port 8108
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8108 " ^| findstr "LISTENING" 2^>nul') do (
    echo [start] Killing existing process on port 8108 ^(PID %%p^)
    taskkill /F /PID %%p >nul 2>&1
)

:: ── 6. Start gateway in background ───────────────────────────────────────────
echo [start] Starting LLM Gateway V8...
set "GATEWAY_LOG=%LOGS_DIR%\gateway.log"
start "llm_gateway_s8" /MIN cmd /c "cd /d "%GATEWAY_DIR%" && uv run main.py > "%GATEWAY_LOG%" 2>&1"

:: Wait for gateway to be ready (max 45 seconds)
set /a wait=0
:WAIT_LOOP
timeout /t 2 /nobreak >nul
set /a wait+=2
curl -s http://localhost:8108/v1/routers >nul 2>&1
if not errorlevel 1 (
    echo [start] Gateway ready at http://localhost:8108
    goto GATEWAY_READY
)
if %wait% geq 45 (
    echo ERROR: Gateway did not start within 45s.
    echo Check logs\gateway.log for errors.
    type "%GATEWAY_LOG%" 2>nul | findstr /i "error\|exception\|traceback" | head /c 20
    pause
    exit /b 1
)
echo [start] Waiting for gateway... %wait%s
goto WAIT_LOOP

:GATEWAY_READY
echo.
echo ================================================================
echo   Gateway is UP.  Starting query runner...
echo ================================================================
echo.

:: ── 7. Run all assignment parts ───────────────────────────────────────────────
set "PART=%~1"
if "%PART%"=="" (
    python "%HERE%run_all.py"
) else (
    python "%HERE%run_all.py" --part %PART%
)

echo.
echo ================================================================
echo   Done. Results in: logs\results\
echo ================================================================
echo.
pause
endlocal
