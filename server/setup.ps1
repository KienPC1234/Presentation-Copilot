Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   PRESENTATION COPILOT SERVER - SETUP (PowerShell)          " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

Set-Location $PSScriptRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python not found in PATH! Please install Python 3.10+."
    exit 1
}

if (-not (Test-Path ".venv")) {
    Write-Host "[*] Creating virtual environment .venv ..." -ForegroundColor Yellow
    python -m venv .venv
}

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$venvPip = Join-Path $PSScriptRoot ".venv\Scripts\pip.exe"

Write-Host "[*] Installing Python dependencies from requirements.txt ..." -ForegroundColor Yellow
& $venvPip install --upgrade pip
& $venvPip install -r requirements.txt

if (-not (Test-Path ".env")) {
    Write-Host "[*] Copying .env.example -> .env ..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
}

if (Get-Command ollama -ErrorAction SilentlyContinue) {
    Write-Host "[*] Pulling Ollama models: qwen2.5:7b, nomic-embed-text ..." -ForegroundColor Yellow
    ollama pull qwen2.5:7b
    ollama pull nomic-embed-text
} else {
    Write-Warning "Ollama is not in PATH. Please ensure Ollama is installed and running."
}

Write-Host "`n[OK] Setup complete! Run .\start.ps1 to start the server." -ForegroundColor Green

