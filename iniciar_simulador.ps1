param(
    [ValidateSet(203, 300)][int]$Dpi = 203,
    [switch]$SemNavegador
)
$ErrorActionPreference = 'Stop'
try {
    . (Join-Path $PSScriptRoot 'ambiente_python.ps1')
    $pythonSimulador = Get-SimulatorPython
    Write-Host 'Verificando QZ Tray para impressao pelo site...'
    . (Join-Path $PSScriptRoot 'qztray.ps1')
    Start-QzTray
    $argumentos = @((Join-Path $PSScriptRoot 'simulador.py'), '--dpi', "$Dpi")
    if ($SemNavegador) { $argumentos += '--sem-navegador' }
    Write-Host 'Abrindo simulador com o Python incluido no pacote...'
    & $pythonSimulador @argumentos
    exit $LASTEXITCODE
} catch {
    Write-Host "ERRO: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
