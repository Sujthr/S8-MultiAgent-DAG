@echo off
setlocal EnableDelayedExpansion
set "HERE=%~dp0"
set "WORKSPACE=%HERE%workspace"
set "GATEWAY_DIR=%WORKSPACE%\gateway"
set "LOGS_DIR=%HERE%logs"

:: Copy .env to workspace
copy /Y "%HERE%.env" "%WORKSPACE%\.env" >nul 2>&1

:: Kill existing gateway on port 8108
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8108 " ^| findstr "LISTENING" 2^>nul') do (
    taskkill /F /PID %%p >nul 2>&1
)

:: Start fresh gateway
echo [gateway] Starting LLM Gateway V8...
start "llm_gateway_s8" /MIN cmd /c "cd /d "%GATEWAY_DIR%" && uv run main.py > "%LOGS_DIR%\gateway2.log" 2>&1"

:: Wait for ready
set /a wait=0
:WAIT_LOOP
timeout /t 2 /nobreak >nul
set /a wait+=2
curl -s http://localhost:8108/v1/routers >nul 2>&1
if not errorlevel 1 (
    echo [gateway] Ready at http://localhost:8108
    goto DONE
)
if %wait% geq 60 (
    echo [gateway] WARNING: Gateway did not start within 60s
    goto DONE
)
goto WAIT_LOOP
:DONE
endlocal
