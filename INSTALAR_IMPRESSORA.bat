@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
echo Instalando TSC DA300 virtual e QZ Tray... (exige permissao de administrador)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar_impressora.ps1"
if errorlevel 1 goto falha
echo.
echo Instalacao completa. Execute INICIAR_SIMULADOR.bat normalmente para imprimir pelo site.
pause
exit /b 0

:falha
echo.
echo ERRO: a instalacao nao foi concluida. Confira a mensagem acima.
echo Execute este arquivo como administrador. Se a fila ja existe, pode executar novamente para instalar o QZ Tray.
pause
exit /b 1
