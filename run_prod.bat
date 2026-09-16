@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run install.bat first.
  exit /b 1
)
if not exist ".env" (
  echo .env was not found. Copy .env.example to .env and configure it.
  exit /b 1
)
".venv\Scripts\python.exe" scripts\run_server.py --mode production
endlocal
