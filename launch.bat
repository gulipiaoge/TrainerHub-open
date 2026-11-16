@echo off
cd /d "%~dp0"
title TrainerHub
echo.
echo   TrainerHub is starting...
echo   All data stays in this folder under data\
echo.
"%~dp0.venv\Scripts\pythonw.exe" "%~dp0app.py"
if errorlevel 1 (
  echo.
  echo [ERROR] App did not start. Please check that the WebView2 Runtime is installed.
  echo         Run: .venv\Scripts\pip install -r requirements.txt
  pause
)
exit
