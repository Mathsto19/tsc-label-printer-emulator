function Get-SimulatorPython {
    $pythonSimulador = Join-Path $PSScriptRoot 'runtime\python.exe'
    if (-not (Test-Path -LiteralPath $pythonSimulador -PathType Leaf)) {
        throw 'O Python do pacote esta ausente. Extraia o ZIP completo, incluindo a pasta runtime. Para gerar o pacote a partir do codigo-fonte, execute preparar_pacote.ps1.'
    }
    # Nao usa PATH, py.exe, Microsoft Store nem a .venv copiada de outro computador.
    # Executa o interpretador e importa inclusive as bibliotecas nativas antes de abrir o QZ.
    $diagnostico = & $pythonSimulador -c 'import sys; assert sys.version_info[:2] == (3, 12); import reportlab, PIL, qrcode, pymupdf; import simulador' 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "O Python incluido no pacote nao iniciou corretamente. Extraia novamente o ZIP completo em uma pasta local. Suporte: Windows 10/11 de 64 bits (Intel/AMD). Detalhes: $($diagnostico -join ' ')"
    }
    return $pythonSimulador
}
