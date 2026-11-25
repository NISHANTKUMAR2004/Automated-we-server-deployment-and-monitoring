@echo off
setlocal
cd /d "%~dp0"

set "API_URL=http://127.0.0.1:8001"
set "WEB_URL=http://localhost:3000"
set "EC2_HOST=15.135.200.112"
set "EC2_USER=ubuntu"
set "SSH_KEY_PATH=D:\aws-keys\automated-server-monitoring-key.pem"

if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python virtual environment is missing.
    echo Create it and install backend\requirements.txt first.
    pause
    exit /b 1
)

if not exist "frontend\node_modules" (
    echo ERROR: Frontend packages are missing.
    echo Run "cd frontend ^&^& npm install" first.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\deployment\prepare-demo.ps1"
if errorlevel 1 (
    echo.
    echo Could not prepare the API port. See the error above.
    pause
    exit /b 1
)

curl.exe -fsS "%API_URL%/openapi.json" | findstr /C:"/api/dashboard" >nul
if errorlevel 1 (
    echo Starting FastAPI on port 8001...
    start "Monitoring API - port 8001" /D "%~dp0" "%~dp0.venv\Scripts\python.exe" -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8001
) else (
    echo FastAPI is already serving the live dashboard; reusing it.
)

curl.exe -fsS "%WEB_URL%" >nul 2>&1
if errorlevel 1 (
    powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }"
    if errorlevel 1 (
        echo ERROR: Port 3000 is occupied by another service.
        echo Close that service or use its current dashboard URL.
        pause
        exit /b 1
    )
    echo Starting React dashboard on port 3000...
    start "Monitoring Dashboard - port 3000" /D "%~dp0frontend" cmd /k npm run dev
) else (
    echo Dashboard is already running on port 3000; reusing it.
)

powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8081 -State Listen -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }"
if errorlevel 1 (
    echo Application SSH tunnel is already listening on port 8081.
) else (
    echo Starting application SSH tunnel on port 8081...
    start "Application Tunnel - port 8081" /D "%~dp0" ssh -i "%SSH_KEY_PATH%" -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -N -L 127.0.0.1:8081:127.0.0.1:8080 %EC2_USER%@%EC2_HOST%
)

timeout /t 3 /nobreak >nul
start "" "%WEB_URL%"
echo.
echo Demo ready:
echo   Dashboard: %WEB_URL%
echo   API docs:  %API_URL%/docs
echo   App demo:  deploy an app, then open its displayed URL through an SSH tunnel.
