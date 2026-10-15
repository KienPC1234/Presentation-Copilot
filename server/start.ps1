Set-Location $PSScriptRoot

$venvUvicorn = Join-Path $PSScriptRoot ".venv\Scripts\uvicorn.exe"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   STARTING PRESENTATION COPILOT SERVER                     " -ForegroundColor Cyan
Write-Host "   Web Dashboard : http://localhost:8765                   " -ForegroundColor Green
Write-Host "   WebSocket     : ws://localhost:8765/ws                  " -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan

if (Test-Path $venvUvicorn) {
    & $venvUvicorn main:app --host 127.0.0.1 --port 8765 --reload
} else {
    uvicorn main:app --host 127.0.0.1 --port 8765 --reload
}

