@echo off
echo.
echo [stop] Stopping LLM Gateway V8...

:: Kill by port 8108
set "KILLED=0"
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8108 " ^| findstr "LISTENING" 2^>nul') do (
    echo [stop] Killing PID %%p on port 8108
    taskkill /F /PID %%p >nul 2>&1
    set "KILLED=1"
)

:: Also try by window title
taskkill /F /FI "WINDOWTITLE eq llm_gateway_s8" >nul 2>&1

if "%KILLED%"=="1" (
    echo [stop] Gateway stopped.
) else (
    echo [stop] No gateway process found on port 8108.
)
echo.
