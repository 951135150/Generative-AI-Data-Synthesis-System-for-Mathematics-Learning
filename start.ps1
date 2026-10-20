param([int]$ApiPort = 8001, [int]$WebPort = 3000)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $projectPython)) { throw 'Run .\setup.ps1 first.' }
if (-not (Test-Path -LiteralPath 't2p-web\node_modules\next\dist\bin\next')) { throw 'Frontend dependencies are missing. Run .\setup.ps1.' }
foreach ($port in @($ApiPort, $WebPort)) {
    if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
        throw "Port $port is already in use. Select another port; no existing process was stopped."
    }
}
$env:AI_MODE = 'simulation'
$env:ALLOW_PAID_API = 'false'
$env:RAG_ALLOW_DOWNLOAD = 'false'
$env:FRONTEND_ORIGINS = "http://localhost:$WebPort,http://127.0.0.1:$WebPort"
$env:NEXT_PUBLIC_API_URL = "http://127.0.0.1:$ApiPort"
$env:HF_HOME = Join-Path $projectRoot '.runtime\rag\huggingface'
$env:npm_config_cache = Join-Path $projectRoot '.runtime\npm-cache'
$runtimeFolder = Join-Path $projectRoot '.runtime'
New-Item -ItemType Directory -Force -Path $runtimeFolder | Out-Null
& $projectPython scripts/backup_local.py
if ($LASTEXITCODE -ne 0) { throw 'Database backup failed; startup stopped.' }
$apiProcess = $null
$webProcess = $null
try {
    $apiProcess = Start-Process -FilePath $projectPython -ArgumentList @('-m', 'uvicorn', 'api_server:app', '--host', '127.0.0.1', '--port', "$ApiPort") -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeFolder 'api.stdout.log') -RedirectStandardError (Join-Path $runtimeFolder 'api.stderr.log')
    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if ($apiProcess.HasExited) { throw 'Backend exited. See .runtime/api.stderr.log.' }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/" -TimeoutSec 2
            if ($health.status) { $ready = $true; break }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $ready) { throw 'Backend did not become ready. See .runtime/api.stderr.log.' }
    # Launch Node directly so this script owns the server process rather than an npm shell.
    $webProcess = Start-Process -FilePath (Get-Command node).Source -ArgumentList @('node_modules/next/dist/bin/next', 'dev', '-H', '127.0.0.1', '-p', "$WebPort") -WorkingDirectory (Join-Path $projectRoot 't2p-web') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeFolder 'web.stdout.log') -RedirectStandardError (Join-Path $runtimeFolder 'web.stderr.log')
    Write-Host "Frontend: http://127.0.0.1:$WebPort"
    Write-Host "API: http://127.0.0.1:$ApiPort/docs"
    Write-Host 'Offline simulation active. CUDA preferred; CPU fallback automatic. Press Ctrl+C to stop both servers.'
    while (-not $apiProcess.HasExited -and -not $webProcess.HasExited) { Start-Sleep -Milliseconds 500 }
} finally {
    foreach ($ownedProcess in @($apiProcess, $webProcess)) {
        if ($null -ne $ownedProcess -and -not $ownedProcess.HasExited) { Stop-Process -Id $ownedProcess.Id }
    }
}
