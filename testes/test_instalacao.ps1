# Testes isolados: nao baixam, instalam, abrem programas nem alteram impressoras.
$ErrorActionPreference = 'Stop'
$raiz = Split-Path -Parent $PSScriptRoot
. (Join-Path $raiz 'qztray.ps1')

function Assert-True($condicao, $mensagem) {
    if (-not $condicao) { throw "FALHOU: $mensagem" }
}

function Invoke-QzScenario {
    param(
        [bool]$Existente = $false, [bool]$Local = $false,
        [bool]$HashValido = $true, [bool]$FalhaDownload = $false,
        [int]$Codigo = 0, [bool]$EncontradoDepois = $true,
        [string]$Arquitetura = 'AMD64'
    )
    $estado = @{ Downloads = 0; Execucoes = 0; Remocoes = 0; Url = ''; Erro = '' }
    $archAnterior = $env:PROCESSOR_ARCHITECTURE
    $archWowAnterior = $env:PROCESSOR_ARCHITEW6432
    $tlsAnterior = [Net.ServicePointManager]::SecurityProtocol
    function Get-QzTrayPath {
        if ($Existente -or ($estado.Execucoes -gt 0 -and $EncontradoDepois)) { return 'C:\QZ Tray\qz-tray.exe' }
    }
    function Test-Path {
        param($LiteralPath, $PathType)
        if ($LiteralPath -like '*\instaladores\*') { return $Local }
        return ($estado.Downloads -gt 0)
    }
    function Invoke-WebRequest {
        param([switch]$UseBasicParsing, $Uri, $OutFile, $TimeoutSec, $ErrorAction)
        $estado.Downloads++
        $estado.Url = $Uri
        if ($FalhaDownload) { throw 'Sem internet (teste)' }
    }
    function Get-FileHash {
        param($LiteralPath, $Algorithm)
        Assert-True ($Algorithm -eq 'SHA256') 'verifica SHA-256'
        $hash = 'invalido'
        if ($HashValido) {
            $hash = '7a44a50f679f0a1dab6679e6c22158dd335511074f5fcc1b208b6f9caf711ba7'
            if ($Arquitetura -eq 'ARM64') { $hash = '10e308b91d84b637520eb36096cb6814b33a66f3cabc317ce776253e759babc8' }
        }
        return @{ Hash = $hash }
    }
    function Start-Process {
        param($FilePath, $ArgumentList, [switch]$Wait, [switch]$PassThru, $WindowStyle, $ErrorAction)
        Assert-True ($ArgumentList -eq '/S' -and $Wait -and $PassThru) 'aguarda instalacao silenciosa'
        $estado.Execucoes++
        return @{ ExitCode = $Codigo }
    }
    function Remove-Item {
        param($LiteralPath, [switch]$Force, $ErrorAction)
        Assert-True ($LiteralPath -like '*tsc-qz-*.exe') 'remove somente download temporario'
        $estado.Remocoes++
    }
    try {
        $env:PROCESSOR_ARCHITECTURE = $Arquitetura
        $env:PROCESSOR_ARCHITEW6432 = ''
        try { Install-QzTray } catch { $estado.Erro = $_.Exception.Message }
        Assert-True ([Net.ServicePointManager]::SecurityProtocol -eq $tlsAnterior) 'restaura TLS'
        return $estado
    } finally {
        $env:PROCESSOR_ARCHITECTURE = $archAnterior
        $env:PROCESSOR_ARCHITEW6432 = $archWowAnterior
    }
}

$r = Invoke-QzScenario -Existente $true
Assert-True ($r.Execucoes -eq 0 -and $r.Downloads -eq 0 -and -not $r.Erro) 'preserva QZ existente'
$r = Invoke-QzScenario
Assert-True ($r.Execucoes -eq 1 -and $r.Downloads -eq 1 -and $r.Remocoes -eq 1 -and -not $r.Erro) 'instala x64 e limpa temporario'
Assert-True ($r.Url -eq 'https://github.com/qzind/tray/releases/download/v2.3.0/qz-tray-2.3.0-x86_64.exe') 'download oficial x64'
$r = Invoke-QzScenario -Arquitetura ARM64
Assert-True ($r.Url -like '*-arm64.exe' -and $r.Execucoes -eq 1 -and -not $r.Erro) 'instala ARM64'
$r = Invoke-QzScenario -Local $true
Assert-True ($r.Downloads -eq 0 -and $r.Execucoes -eq 1 -and $r.Remocoes -eq 0 -and -not $r.Erro) 'usa e preserva instalador incluido'
$r = Invoke-QzScenario -HashValido $false
Assert-True ($r.Execucoes -eq 0 -and $r.Remocoes -eq 1 -and $r.Erro) 'bloqueia arquivo incorreto'
$r = Invoke-QzScenario -FalhaDownload $true
Assert-True ($r.Execucoes -eq 0 -and $r.Remocoes -eq 1 -and $r.Erro) 'falha de rede nao executa instalador'
$r = Invoke-QzScenario -Codigo 2
Assert-True ($r.Erro -like '*codigo 2*') 'propaga falha do instalador'
$r = Invoke-QzScenario -EncontradoDepois $false
Assert-True ($r.Erro -like '*nao foi encontrado*') 'confirma instalacao apos retorno zero'
$r = Invoke-QzScenario -Arquitetura x86
Assert-True ($r.Execucoes -eq 0 -and $r.Downloads -eq 0 -and $r.Erro) 'informa arquitetura sem suporte'

function Invoke-PrinterScenario {
    param([string]$Fila, [bool]$FalhaQz = $false)
    $estado = @{ Qz = 0; FilasNovas = 0; PortasNovas = 0; Erro = '' }
    function Import-Module { param($Name, $ErrorAction) }
    function Get-SimulatorPython { return 'C:\pacote\runtime\python.exe' }
    function Get-Printer {
        param($Name, $ErrorAction)
        if ($Fila -eq 'nossa') { return @{ PortName = 'TSC_DA300_VIRTUAL_19100'; Comment = 'SIMULADOR TSPL PDF - 127.0.0.1:19100' } }
        if ($Fila -eq 'outra') { return @{ PortName = 'USB001'; Comment = '' } }
    }
    function Get-PrinterDriver { param($Name, $ErrorAction) return @{ Name = $Name } }
    function Get-PrinterPort {
        param($Name, $ErrorAction)
        return @{ PrinterHostAddress = '127.0.0.1'; PortNumber = 19100 }
    }
    function Add-Printer { param($Name, $DriverName, $PortName, $Comment, $ErrorAction) $estado.FilasNovas++ }
    function Add-PrinterPort { param($Name, $PrinterHostAddress, $PortNumber, $ErrorAction) $estado.PortasNovas++ }
    function Install-QzTray {
        $estado.Qz++
        if ($FalhaQz) { throw 'Falha QZ (teste)' }
    }
    # Retira apenas o requisito de elevacao e o carregamento das funcoes reais para usar mocks.
    $codigoTeste = [IO.File]::ReadAllText((Join-Path $raiz 'instalar_impressora.ps1'))
    $codigoTeste = $codigoTeste.Replace('#Requires -RunAsAdministrator', '')
    $codigoTeste = $codigoTeste.Replace('. (Join-Path $PSScriptRoot ''qztray.ps1'')', '')
    $codigoTeste = $codigoTeste.Replace('. (Join-Path $PSScriptRoot ''ambiente_python.ps1'')', '')
    try { & ([scriptblock]::Create($codigoTeste)) | Out-Null } catch { $estado.Erro = $_.Exception.Message }
    return $estado
}

$r = Invoke-PrinterScenario -Fila nossa
Assert-True ($r.Qz -eq 1 -and $r.FilasNovas -eq 0 -and -not $r.Erro) 'reexecucao prepara QZ sem recriar fila'
$r = Invoke-PrinterScenario -Fila ausente
Assert-True ($r.Qz -eq 1 -and $r.FilasNovas -eq 1 -and -not $r.Erro) 'instalacao nova prepara QZ e fila'
$r = Invoke-PrinterScenario -Fila outra
Assert-True ($r.Qz -eq 0 -and $r.FilasNovas -eq 0 -and $r.PortasNovas -eq 0 -and $r.Erro) 'protege impressora alheia'
$r = Invoke-PrinterScenario -Fila ausente -FalhaQz $true
Assert-True ($r.FilasNovas -eq 0 -and $r.Erro) 'nao conclui instalacao sem QZ'

& {
    function Get-QzTrayPath { return $null }
    function Start-Process { throw 'Nao deveria abrir nada sem QZ instalado.' }
    $erroQz = ''
    try { Start-QzTray } catch { $erroQz = $_.Exception.Message }
    Assert-True ($erroQz -like '*INSTALAR_IMPRESSORA.bat*') 'orienta reparo quando falta QZ'
}
Write-Host 'OK: 14 cenarios de instalacao/abertura, sem alterar o Windows.' -ForegroundColor Green
