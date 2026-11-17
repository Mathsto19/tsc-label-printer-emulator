$ErrorActionPreference = 'Stop'
try {
    . (Join-Path $PSScriptRoot 'qztray.ps1')
    Start-QzTray
    exit 0
} catch {
    Write-Host "ERRO: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
