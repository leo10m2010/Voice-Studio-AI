param(
    [ValidateSet("cpu","nvidia")]
    [string]$Flavor = "nvidia",
    [string]$EngineDir = "engine-dist\qwen-engine",
    [string]$Version = "1.0.1",
    [string]$OutputDir = "engine-release"
)

$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..")

$baseUrl = "https://github.com/leo10m2010/Voice-Studio-AI/releases/download/engine-v$Version"

python .\scripts\package_engine_assets.py `
    --engine-dir "$EngineDir" `
    --flavor "$Flavor" `
    --version "$Version" `
    --out "$OutputDir" `
    --base-url "$baseUrl"
if ($LASTEXITCODE -ne 0) {
    throw "No se pudieron crear los assets del motor $Flavor v$Version."
}

Write-Host ""
Write-Host "Assets listos en $OutputDir" -ForegroundColor Green
Write-Host "Sube engine-manifest.json y todos los voice-engine-*.zip a la Release engine-v$Version." -ForegroundColor Cyan
