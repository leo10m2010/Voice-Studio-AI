$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..")

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Primero ejecuta scripts\setup-windows.ps1" -ForegroundColor Yellow
    exit 1
}

$py = Resolve-Path ".venv\Scripts\python.exe"

Write-Host ""
Write-Host "Construyendo motor Python para Windows..." -ForegroundColor Cyan
Write-Host "Este paso es pesado porque incluye PyTorch y Qwen." -ForegroundColor DarkGray

& $py -m pip install --upgrade pyinstaller

if (Test-Path "engine\build") { Remove-Item "engine\build" -Recurse -Force }
if (Test-Path "engine\dist") { Remove-Item "engine\dist" -Recurse -Force }
if (Test-Path "engine-dist\qwen-engine") { Remove-Item "engine-dist\qwen-engine" -Recurse -Force }

& $py -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --name qwen-engine `
    --distpath engine-dist `
    --workpath engine\build `
    --specpath engine `
    --collect-all qwen_tts `
    --collect-all transformers `
    --collect-all librosa `
    --collect-all soundfile `
    --collect-all torchaudio `
    --collect-all torch `
    engine\server.py

Write-Host ""
Write-Host "Motor creado en engine-dist\qwen-engine" -ForegroundColor Green
Write-Host "Ahora puedes ejecutar: npm run tauri build"
Write-Host ""
