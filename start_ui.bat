@echo off
setlocal
set "HERE=%~dp0"
echo.
echo ================================================================
echo   S8-Assignment  — Web UI
echo ================================================================
echo.
echo [ui] Installing Flask if needed...
python -m pip install flask --quiet
echo [ui] Starting UI at http://localhost:5000
echo [ui] Press Ctrl+C to stop
echo.
python "%HERE%ui.py"
endlocal
