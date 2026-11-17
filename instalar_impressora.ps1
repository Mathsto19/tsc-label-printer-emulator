#Requires -RunAsAdministrator
# Prepara o QZ Tray e cria a fila virtual. Nunca altera uma impressora existente.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ambiente_python.ps1')
$null = Get-SimulatorPython
. (Join-Path $PSScriptRoot 'qztray.ps1')

$nomeImpressora = 'TSC DA300'
$nomePorta = 'TSC_DA300_VIRTUAL_19100'
$driver = 'Generic / Text Only'
$hostIP = '127.0.0.1'
$portaTCP = 19100
$descricao = 'SIMULADOR TSPL PDF - 127.0.0.1:19100'

Import-Module PrintManagement -ErrorAction Stop

$existente = Get-Printer -Name $nomeImpressora -ErrorAction SilentlyContinue
if ($null -ne $existente) {
    if ($existente.PortName -eq $nomePorta -and $existente.Comment -eq $descricao) {
        Write-Host 'A impressora virtual ja esta instalada.' -ForegroundColor Green
    } else {
        throw "Ja existe uma impressora '$nomeImpressora' nao identificada como nossa. Nada foi alterado."
    }
}

$drv = Get-PrinterDriver -Name $driver -ErrorAction SilentlyContinue
if ($null -eq $drv) {
    try { Add-PrinterDriver -Name $driver -ErrorAction Stop } catch {
        throw "Driver '$driver' nao disponivel. Instale o driver nativo do Windows 'Generic / Text Only' e tente novamente. Detalhes: $($_.Exception.Message)"
    }
}

$existentePorta = Get-PrinterPort -Name $nomePorta -ErrorAction SilentlyContinue
if ($null -ne $existentePorta) {
    if ($existentePorta.PrinterHostAddress -ne $hostIP -or $existentePorta.PortNumber -ne $portaTCP) {
        throw "A porta '$nomePorta' ja existe com destino diferente. Nada foi alterado."
    }
} else {
    Add-PrinterPort -Name $nomePorta -PrinterHostAddress $hostIP -PortNumber $portaTCP -ErrorAction Stop
}

# Verifica o QZ mesmo ao executar novamente para uma fila ja instalada.
# Em caso de falha, nao anuncia que a preparacao esta completa.
Install-QzTray

if ($null -eq $existente) {
    Add-Printer -Name $nomeImpressora -DriverName $driver -PortName $nomePorta -Comment $descricao -ErrorAction Stop
}
Write-Host ''
Write-Host 'TSC DA300 VIRTUAL E QZ TRAY PREPARADOS COM SUCESSO' -ForegroundColor Green
Write-Host 'Nome no Windows: TSC DA300'
Write-Host 'Driver: Generic / Text Only (para TSPL bruto)'
Write-Host 'Destino: 127.0.0.1:19100'
Write-Host 'Execute INICIAR_SIMULADOR.bat normalmente antes de imprimir: ele abre o QZ Tray e o simulador.'
Write-Host 'Depois, atualize o site e permita a conexao dele no QZ Tray, se solicitado.'
Write-Host ''
Get-Printer -Name $nomeImpressora | Format-List Name,DriverName,PortName,Comment
