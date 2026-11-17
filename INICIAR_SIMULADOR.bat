@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0iniciar_simulador.ps1" %*
set "resultado=%ERRORLEVEL%"
echo.
pause
exit /b %resultado%
