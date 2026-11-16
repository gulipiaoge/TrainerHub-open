@echo off
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\pythonw.exe" goto missing
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0app.py"
exit /b 0

:missing
echo [ERROR] Python runtime not found.
echo         Run: .venv\Scripts\pip install -r requirements.txt
pause
exit /b 1
