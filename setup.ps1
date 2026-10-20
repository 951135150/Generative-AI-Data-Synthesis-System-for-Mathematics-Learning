param([switch]$DownloadModel)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$env:AI_MODE = 'simulation'
$env:ALLOW_PAID_API = 'false'
$env:HF_HOME = Join-Path $projectRoot '.runtime\rag\huggingface'
$env:PIP_CACHE_DIR = Join-Path $projectRoot '.runtime\pip-cache'
$env:npm_config_cache = Join-Path $projectRoot '.runtime\npm-cache'

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $Executable (exit $LASTEXITCODE)" }
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw 'Install Node.js 20.9 or newer, then reopen PowerShell.' }
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    if (-not (Get-Command py -ErrorAction SilentlyContinue)) { throw 'Install Python 3.11 or 3.12 with the Python launcher.' }
    Invoke-Checked -Executable 'py' -Arguments @('-3', '-m', 'venv', '.venv')
}
$projectPython = Join-Path $projectRoot '.venv\Scripts\python.exe'
Invoke-Checked -Executable $projectPython -Arguments @('-c', 'import sys; assert (3,10) <= sys.version_info[:2] <= (3,12), "Use Python 3.10-3.12 for the tested CUDA wheel."')
& $projectPython -c 'import torch; assert torch.cuda.is_available()'
$cudaReady = $LASTEXITCODE -eq 0
if (-not $cudaReady) {
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) {
        try {
            Invoke-Checked -Executable $projectPython -Arguments @('-m', 'pip', 'install', 'torch==2.7.1', '--index-url', 'https://download.pytorch.org/whl/cu118')
        } catch {
            Write-Warning 'CUDA wheel installation failed. Trying the CPU wheel.'
            Invoke-Checked -Executable $projectPython -Arguments @('-m', 'pip', 'install', 'torch==2.7.1', '--index-url', 'https://download.pytorch.org/whl/cpu')
        }
    } else {
        Invoke-Checked -Executable $projectPython -Arguments @('-m', 'pip', 'install', 'torch==2.7.1', '--index-url', 'https://download.pytorch.org/whl/cpu')
    }
}
Invoke-Checked -Executable $projectPython -Arguments @('-m', 'pip', 'install', '-r', 'requirements.txt', '-c', 'constraints-windows.txt')
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
Push-Location -LiteralPath (Join-Path $projectRoot 't2p-web')
try { Invoke-Checked -Executable 'npm.cmd' -Arguments @('ci') } finally { Pop-Location }
if ($DownloadModel) { Invoke-Checked -Executable $projectPython -Arguments @('scripts/prepare_rag.py', '--download') }
Invoke-Checked -Executable $projectPython -Arguments @('scripts/check_environment.py')
Write-Host 'Ready. Run .\start.ps1. Offline simulation never needs an API key.'
