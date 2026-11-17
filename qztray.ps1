# Funcoes compartilhadas pelo instalador e pela abertura do simulador (Windows PowerShell 5.1).
function Get-QzTrayPath {
    $locais = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\QZ Tray',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\QZ Tray',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\QZ Tray'
    )
    foreach ($chave in $locais) {
        $registro = Get-ItemProperty -LiteralPath $chave -ErrorAction SilentlyContinue
        if ($registro.InstallLocation) {
            $exe = Join-Path $registro.InstallLocation 'qz-tray.exe'
            if (Test-Path -LiteralPath $exe -PathType Leaf) { return $exe }
        }
    }
    foreach ($pasta in @($env:ProgramW6432, $env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        if ($pasta) {
            $exe = Join-Path $pasta 'QZ Tray\qz-tray.exe'
            if (Test-Path -LiteralPath $exe -PathType Leaf) { return $exe }
        }
    }
    return $null
}

function Install-QzTray {
    if (Get-QzTrayPath) {
        Write-Host 'QZ Tray ja instalado; mantendo a instalacao existente.' -ForegroundColor Green
        return
    }

    # Versao fixada e hashes publicados na release oficial. Ao atualizar, troque ambos.
    # https://github.com/qzind/tray/releases/tag/v2.3.0
    $versao = '2.3.0'
    $arquitetura = $env:PROCESSOR_ARCHITEW6432
    if (-not $arquitetura) { $arquitetura = $env:PROCESSOR_ARCHITECTURE }
    switch ($arquitetura) {
        'ARM64' {
            $sufixo = 'arm64'
            $hashEsperado = '10e308b91d84b637520eb36096cb6814b33a66f3cabc317ce776253e759babc8'
        }
        'AMD64' {
            $sufixo = 'x86_64'
            $hashEsperado = '7a44a50f679f0a1dab6679e6c22158dd335511074f5fcc1b208b6f9caf711ba7'
        }
        default { throw 'Instalacao automatica do QZ Tray requer Windows de 64 bits (Intel/AMD ou ARM64). Consulte https://qz.io/download/.' }
    }
    $arquivo = "qz-tray-$versao-$sufixo.exe"
    $url = "https://github.com/qzind/tray/releases/download/v$versao/$arquivo"
    # Permite distribuir o instalador oficial junto do pacote para uso sem internet.
    $instalador = Join-Path $PSScriptRoot "instaladores\$arquivo"
    $temporario = $null
    $protocoloAnterior = [Net.ServicePointManager]::SecurityProtocol
    try {
        if (-not (Test-Path -LiteralPath $instalador -PathType Leaf)) {
            $temporario = Join-Path ([IO.Path]::GetTempPath()) ("tsc-qz-" + [guid]::NewGuid().ToString('N') + '.exe')
            $instalador = $temporario
            Write-Host "Baixando QZ Tray $versao do fornecedor (cerca de 140 MB)..."
            [Net.ServicePointManager]::SecurityProtocol = $protocoloAnterior -bor [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $instalador -TimeoutSec 600 -ErrorAction Stop
        }
        if ((Get-FileHash -LiteralPath $instalador -Algorithm SHA256).Hash -ne $hashEsperado) {
            throw 'O arquivo do QZ Tray nao corresponde ao instalador oficial esperado. Ele nao sera executado.'
        }
        Write-Host 'Instalando QZ Tray. Aguarde...'
        $processo = Start-Process -FilePath $instalador -ArgumentList '/S' -Wait -PassThru -WindowStyle Hidden -ErrorAction Stop
        if ($processo.ExitCode -ne 0) { throw "Instalador do QZ Tray retornou codigo $($processo.ExitCode)." }
        if (-not (Get-QzTrayPath)) { throw 'O instalador terminou, mas o executavel do QZ Tray nao foi encontrado.' }
        Write-Host 'QZ Tray instalado com sucesso.' -ForegroundColor Green
    } catch {
        throw "Nao foi possivel preparar o QZ Tray: $($_.Exception.Message) Verifique a internet ou instale por https://qz.io/download/ e execute INSTALAR_IMPRESSORA.bat novamente."
    } finally {
        [Net.ServicePointManager]::SecurityProtocol = $protocoloAnterior
        if ($temporario -and (Test-Path -LiteralPath $temporario)) {
            Remove-Item -LiteralPath $temporario -Force -ErrorAction SilentlyContinue
        }
    }
}

function Start-QzTray {
    $exe = Get-QzTrayPath
    if (-not $exe) {
        throw 'QZ Tray nao encontrado. Execute INSTALAR_IMPRESSORA.bat como administrador para completar a instalacao.'
    }
    # O proprio QZ impede instancias duplicadas. Executado pela abertura normal do simulador.
    Start-Process -FilePath $exe -WorkingDirectory (Split-Path -Parent $exe) -WindowStyle Hidden -ErrorAction Stop | Out-Null
    Write-Host 'QZ Tray: abertura solicitada. Confira o icone ao lado do relogio.'
}
