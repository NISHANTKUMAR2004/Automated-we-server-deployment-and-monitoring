@echo off
setlocal
cd /d "%~dp0"
set "APP=%~1"
if "%APP%"=="" set "APP=portfolio"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\deployment\deploy-dummy-app.ps1" -Application "%APP%"
if errorlevel 1 (
    echo.
    echo Puppet-based deployment failed.
)
pause
