@echo off
cd /d "%~dp0"
py -m pip install -r requirements.txt
if errorlevel 1 (
  pause
  exit /b 1
)
if exist .env for /f "usebackq tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"
start http://localhost:8000
py server.py
pause
