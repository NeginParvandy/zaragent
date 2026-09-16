@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "VENV_PY=.venv\Scripts\python.exe"
set "PYTHON_CMD="

if exist "%VENV_PY%" (
  "%VENV_PY%" -c "import sys,struct; raise SystemExit(0 if sys.version_info[:2] == (3,13) and struct.calcsize('P')*8 == 64 else 1)" >nul 2>nul
  if errorlevel 1 (
    echo Existing .venv is not Python 3.13 64-bit. Recreating it...
    rmdir /s /q ".venv"
  ) else (
    for /f "delims=" %%V in ('"%VENV_PY%" -c "import platform; print(platform.python_version())"') do echo Using existing Python %%V 64-bit virtual environment.
    goto install_dependencies
  )
)

where py >nul 2>nul
if not errorlevel 1 (
  py -3.13 -c "import sys,struct; raise SystemExit(0 if sys.version_info[:2] == (3,13) and struct.calcsize('P')*8 == 64 else 1)" >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=py -3.13"
)

if not defined PYTHON_CMD (
  where python >nul 2>nul
  if not errorlevel 1 (
    python -c "import sys,struct; raise SystemExit(0 if sys.version_info[:2] == (3,13) and struct.calcsize('P')*8 == 64 else 1)" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"
  )
)

if not defined PYTHON_CMD (
  echo ERROR: Python 3.13 64-bit was not found.
  echo Install Python 3.13 x64, then run this file again.
  exit /b 1
)

for /f "delims=" %%V in ('%PYTHON_CMD% -c "import platform; print(platform.python_version())"') do echo Selected Python %%V 64-bit
%PYTHON_CMD% -m venv ".venv"
if errorlevel 1 exit /b 1

:install_dependencies
set "PYTHONUTF8=1"
echo Installing dependencies from local wheelhouse only...
"%VENV_PY%" -m pip install --no-index --find-links="%CD%\wheelhouse" -r requirements.windows-py313.lock.txt
if errorlevel 1 exit /b 1

"%VENV_PY%" -m pip check
if errorlevel 1 exit /b 1

"%VENV_PY%" -m compileall -q app scripts
if errorlevel 1 exit /b 1

"%VENV_PY%" scripts\verify_install.py
if errorlevel 1 exit /b 1

echo.
echo Offline installation completed successfully.
echo Next steps:
echo   1. copy .env.example .env
echo   2. configure .env
echo   3. run_prod.bat
endlocal
