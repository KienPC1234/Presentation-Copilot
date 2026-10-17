<#
.SYNOPSIS
    Remove build junk and stale generated files, and optionally reclaim Docker space.

.EXAMPLE
    .\scripts\cleanup.ps1
    .\scripts\cleanup.ps1 -Docker -Volumes
    $env:RETENTION_DAYS = 30; .\scripts\cleanup.ps1
#>
param(
    [switch]$Docker,
    [switch]$Volumes,
    [int]$RetentionDays = $(if ($env:RETENTION_DAYS) { [int]$env:RETENTION_DAYS } else { 14 })
)

$ErrorActionPreference = 'SilentlyContinue'
$Root = Split-Path -Parent $PSScriptRoot

Write-Host '==> Removing Python caches'
Get-ChildItem -Path $Root -Recurse -Directory -Force |
    Where-Object { $_.Name -in @('__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache') -and $_.FullName -notlike '*\.git\*' } |
    Remove-Item -Recurse -Force
Get-ChildItem -Path $Root -Recurse -File -Include *.pyc, *.pyo -ErrorAction SilentlyContinue | Remove-Item -Force

Write-Host '==> Removing .NET build output'
Get-ChildItem -Path (Join-Path $Root 'client') -Recurse -Directory -Force |
    Where-Object { $_.Name -in @('bin', 'obj') -and $_.FullName -notlike '*\.git\*' } |
    Remove-Item -Recurse -Force

Write-Host '==> Removing stray audio and log files'
foreach ($dir in @('server', 'client')) {
    $path = Join-Path $Root $dir
    if (Test-Path $path) {
        Get-ChildItem -Path $path -Recurse -File -Include *.wav, *.mp3, *.pcm, *.log | Remove-Item -Force
    }
}

Write-Host "==> Pruning generated exports older than $RetentionDays days"
$exports = Join-Path $Root 'server/data/exports'
if (Test-Path $exports) {
    Get-ChildItem -Path $exports -Directory |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$RetentionDays) } |
        Remove-Item -Recurse -Force
}

if ($Docker) {
    if (Get-Command docker -ErrorAction SilentlyContinue) {
        Write-Host '==> Pruning Docker build cache and dangling images'
        docker builder prune -f
        docker image prune -f
        if ($Volumes) {
            Write-Host '==> Pruning unused Docker volumes'
            docker volume prune -f
        }
        docker system df
    } else {
        Write-Warning 'docker not found; skipping Docker cleanup'
    }
}

Write-Host '==> Done'
