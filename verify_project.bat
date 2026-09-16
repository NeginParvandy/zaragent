@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: .venv was not found. Run install.bat first.
  exit /b 1
)

if not exist ".env" (
  copy /Y ".env.example" ".env" >nul
  echo Created .env from .env.example.
)

".venv\Scripts\python.exe" -m compileall -q app scripts
if errorlevel 1 exit /b 1

".venv\Scripts\python.exe" scripts\verify_install.py
if errorlevel 1 exit /b 1

".venv\Scripts\python.exe" -m pip check
if errorlevel 1 exit /b 1

echo Project verification completed successfully.
endlocal
