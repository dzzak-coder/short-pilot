@echo off
setlocal
cd /d "%~dp0"
docker info >nul 2>nul
if errorlevel 1 (
  echo Ouvrez Docker Desktop, attendez son demarrage, puis relancez ce fichier.
  pause
  exit /b 1
)
docker compose -p shortpilot-n8n -f "tools\n8n\compose.yaml" up -d
if errorlevel 1 (
  pause
  exit /b 1
)
start "" "http://localhost:5678"
