#Requires -RunAsAdministrator
# Nao remove filas que nao pertencam ao simulador.
$ErrorActionPreference = 'Stop'
Import-Module PrintManagement -ErrorAction Stop
$nome = 'TSC DA300'
$porta = 'TSC_DA300_VIRTUAL_19100'
$descricao = 'SIMULADOR TSPL PDF - 127.0.0.1:19100'
$obj = Get-Printer -Name $nome -ErrorAction SilentlyContinue
if ($null -eq $obj) {
    Write-Host 'Fila virtual nao encontrada; nada a fazer.'
    exit 0
}
if ($obj.PortName -ne $porta -or $obj.Comment -ne $descricao) {
    throw 'A impressora existente nao pertence ao simulador. Nao sera removida.'
}
Remove-Printer -Name $nome -ErrorAction Stop
$emUso = @(Get-Printer | Where-Object { $_.PortName -eq $porta })
if ($emUso.Count -eq 0) {
    Remove-PrinterPort -Name $porta -ErrorAction SilentlyContinue
}
Write-Host 'Apenas a fila virtual do simulador foi removida.' -ForegroundColor Green
Write-Host 'Seus PDFs e arquivos PRN foram preservados.'
