@echo off
setlocal
title ShortPilot Studio
cd /d "%~dp0"

rem setx saves keys for future Windows sessions. Load those user variables now
rem so a double-click launch works immediately without exposing their values.

set "PYTHON_EXE="
set "PYTHON_ARGS="
where py >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_EXE=py"
  set "PYTHON_ARGS=-3"
)
if not defined PYTHON_EXE (
  where python >nul 2>nul
  if not errorlevel 1 set "PYTHON_EXE=python"
)
if not defined PYTHON_EXE if exist "%USERPROFILE%\miniconda3\python.exe" set "PYTHON_EXE=%USERPROFILE%\miniconda3\python.exe"

if not defined PYTHON_EXE (
  echo Python is not available. Install Python or Miniconda, then run this file again.
  pause
  exit /b 1
)

echo Starting ShortPilot...
"%PYTHON_EXE%" %PYTHON_ARGS% --version
if errorlevel 1 (
  echo Python could not start.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating the local environment. This is only needed once.
  "%PYTHON_EXE%" %PYTHON_ARGS% -m venv .venv
  if errorlevel 1 (
    echo Could not create the local environment.
    pause
    exit /b 1
  )
)

if not exist ".venv\deps_ok.txt" goto :install
for %%F in (requirements.txt) do set "REQ_DATE=%%~tF"
findstr /L /C:"%REQ_DATE%" ".venv\deps_ok.txt" >nul 2>nul
if errorlevel 1 goto :install
goto :launch

:install
echo Installing project dependencies. Please wait...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo Dependency installation failed. Check your Internet connection and run again.
  pause
  exit /b 1
)
for %%F in (requirements.txt) do echo %%~tF> ".venv\deps_ok.txt"

:launch
rem The helper resolves the portable Ollama location.  Call it unconditionally
rem so a moved runtime never makes the automatic startup silently disappear.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start_ollama.ps1"
if not exist "studio3d\dist\index.html" (
  echo Preparing the integrated 3D studio. This is only needed once.
  where npm.cmd >nul 2>nul
  if errorlevel 1 (
    echo Node.js is needed to build the 3D studio. Install Node.js and relaunch.
    pause
    exit /b 1
  )
  pushd "studio3d"
  call npm.cmd ci --no-audit --no-fund
  if errorlevel 1 (
    popd
    pause
    exit /b 1
  )
  call npm.cmd run build
  if errorlevel 1 (
    popd
    pause
    exit /b 1
  )
  popd
)
start "" /min powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "%~dp0tools\open_shortpilot_when_ready.ps1"
echo ShortPilot is starting at http://localhost:8000
echo Leave this window open while using ShortPilot.
".venv\Scripts\python.exe" app.py

echo ShortPilot stopped.
pause
