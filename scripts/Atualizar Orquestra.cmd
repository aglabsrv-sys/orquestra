@echo off
setlocal
set "ORQUESTRA_RECUPERADOR=%~f0"
powershell -NoLogo -NoProfile -Command "$texto = Get-Content -LiteralPath $env:ORQUESTRA_RECUPERADOR -Raw -Encoding UTF8; & ([scriptblock]::Create(($texto -split '(?m)^# INICIO POWERSHELL\r?$')[1]))"
pause
exit /b

# INICIO POWERSHELL
$ErrorActionPreference = 'Stop'
$temporario = $null
try {
    Add-Type -AssemblyName System.Windows.Forms
    $origem = Split-Path -Parent $env:ORQUESTRA_RECUPERADOR
    $aplicativo = Split-Path -Parent $origem
    if (-not (Test-Path -LiteralPath (Join-Path $aplicativo 'pyproject.toml'))) {
        $seletor = New-Object System.Windows.Forms.FolderBrowserDialog
        $seletor.Description = 'Selecione a pasta do aplicativo Orquestra (onde estao pyproject.toml e uv.lock), e nao o vault.'
        $seletor.ShowNewFolderButton = $false
        if ($seletor.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) { exit }
        $aplicativo = $seletor.SelectedPath
        $seletor.Dispose()
    }
    $confirmacao = [System.Windows.Forms.MessageBox]::Show(
        "Sincronizar e atualizar o Orquestra?`n`n$aplicativo`n`nA atualizacao substitui alteracoes locais nos arquivos do aplicativo e nao cria backup em ZIP. Para preservar personalizacoes, cancele e confira uma copia fora da pasta do aplicativo e do vault antes de continuar.",
        'Atualizar Orquestra', 'OKCancel', 'Information')
    if ($confirmacao -ne [System.Windows.Forms.DialogResult]::OK) { exit }
    $uv = (Get-Command uv -ErrorAction Stop).Source
    $temporario = Join-Path ([System.IO.Path]::GetTempPath()) ("orquestra-atualizar-" + [guid]::NewGuid().ToString('N') + '.py')
    Write-Host 'Preparando a atualizacao oficial...'
    Invoke-WebRequest -UseBasicParsing -Uri 'https://raw.githubusercontent.com/aglabsrv-sys/orquestra/main/src/orquestra/atualizacao_git.py' -OutFile $temporario
    & $uv run --no-project --python '>=3.11' $temporario --aplicativo $aplicativo --confirmar
    if ($LASTEXITCODE -ne 0) { throw 'A atualizacao nao terminou. Confira a mensagem acima e tente novamente.' }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
} finally {
    if ($temporario -and (Test-Path -LiteralPath $temporario)) { Remove-Item -LiteralPath $temporario -Force }
}
