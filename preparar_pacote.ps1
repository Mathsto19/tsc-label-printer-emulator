# Ferramenta de empacotamento. O computador de destino NAO precisa ter Python/pip.
param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
Set-Location -LiteralPath $PSScriptRoot

function Get-OfficialFile($Url, $Path, $HashEsperado) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Write-Host "Baixando $Url"
        $tlsAnterior = [Net.ServicePointManager]::SecurityProtocol
        try {
            [Net.ServicePointManager]::SecurityProtocol = $tlsAnterior -bor [Net.SecurityProtocolType]::Tls12
            Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Path -TimeoutSec 600
        } finally {
            [Net.ServicePointManager]::SecurityProtocol = $tlsAnterior
        }
    }
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash -ne $HashEsperado) {
        throw "SHA-256 incorreto: $Path. O arquivo nao sera usado."
    }
}

& $Python -c 'import sys; assert sys.version_info[:2] == (3, 12) and sys.maxsize > 2**32'
if ($LASTEXITCODE -ne 0) { throw 'Para gerar o pacote, informe -Python com o caminho de um Python 3.12 x64 funcional.' }

$cache = Join-Path $PSScriptRoot '.pacote-cache'
$runtime = Join-Path $PSScriptRoot 'runtime'
$instaladores = Join-Path $PSScriptRoot 'instaladores'
New-Item -ItemType Directory -Path $cache, $instaladores -Force | Out-Null
$arquivoPython = Join-Path $cache 'python-3.12.10-embed-amd64.zip'
Get-OfficialFile 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip' $arquivoPython '4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3'

if (-not (Test-Path -LiteralPath $runtime)) {
    $preparo = Join-Path $PSScriptRoot ('.runtime-preparo-' + [guid]::NewGuid().ToString('N'))
    Expand-Archive -LiteralPath $arquivoPython -DestinationPath $preparo
    # _pth isola o interpretador do Python/PYTHONPATH da maquina e usa caminhos relativos.
    @('python312.zip', '.', 'Lib\site-packages', '..', 'import site') | Set-Content -LiteralPath (Join-Path $preparo 'python312._pth') -Encoding ASCII
    & $Python -m pip install --isolated --disable-pip-version-check --only-binary=:all: --no-compile --target (Join-Path $preparo 'Lib\site-packages') -r (Join-Path $PSScriptRoot 'requirements-portatil.txt')
    if ($LASTEXITCODE -ne 0) { throw "Falha preparando bibliotecas. Pasta de diagnostico preservada: $preparo" }
    & (Join-Path $preparo 'python.exe') -c 'import reportlab, PIL, qrcode, pymupdf; import simulador'
    if ($LASTEXITCODE -ne 0) { throw "Falha validando runtime. Pasta preservada: $preparo" }
    # Confere ambos os caminhos absolutos antes de mover uma pasta.
    $limite = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\') + '\'
    foreach ($alvo in @($preparo, $runtime)) {
        if (-not [IO.Path]::GetFullPath($alvo).StartsWith($limite, [StringComparison]::OrdinalIgnoreCase)) { throw 'Destino fora do projeto.' }
    }
    Move-Item -LiteralPath $preparo -Destination $runtime
}
. (Join-Path $PSScriptRoot 'ambiente_python.ps1')
$null = Get-SimulatorPython

# Inclui tambem o instalador do QZ: instalacao no destino pode ser feita sem internet.
$qz = Join-Path $instaladores 'qz-tray-2.3.0-x86_64.exe'
Get-OfficialFile 'https://github.com/qzind/tray/releases/download/v2.3.0/qz-tray-2.3.0-x86_64.exe' $qz '7a44a50f679f0a1dab6679e6c22158dd335511074f5fcc1b208b6f9caf711ba7'

$pacotes = Join-Path $PSScriptRoot 'Pacotes'
$destino = Join-Path $pacotes ('TSC_DA300_Virtual_Windows_x64_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
New-Item -ItemType Directory -Path $destino | Out-Null
# Lista explicita: nao inclui .venv, capturas, dados pessoais, logs nem caches da maquina.
$arquivos = @(
    'INSTALAR_IMPRESSORA.bat', 'instalar_impressora.ps1', 'desinstalar_impressora.ps1',
    'INICIAR_SIMULADOR.bat', 'iniciar_simulador.ps1', 'ambiente_python.ps1',
    'qztray.ps1', 'iniciar_qztray.ps1', 'simulador.py', 'tspl_pdf.py', 'perfil.py', 'previas.py',
    'painel.html', 'previa.html', 'exemplo_teste.prn', 'LEIA-ME.md', 'requirements.txt',
    'requirements-portatil.txt', 'preparar_pacote.ps1', 'runtime', 'instaladores'
)
foreach ($arquivo in $arquivos) { Copy-Item -LiteralPath (Join-Path $PSScriptRoot $arquivo) -Destination $destino -Recurse }
Write-Host 'Compactando pacote completo...'
Compress-Archive -LiteralPath $destino -DestinationPath ($destino + '.zip') -CompressionLevel Optimal
Write-Host "PACOTE PRONTO: $destino.zip" -ForegroundColor Green
