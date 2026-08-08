param(
    [string]$PythonExe = ".venv\Scripts\python.exe",
    [string]$OutputDir = "engine-dist"
)

$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..")

if (-not (Test-Path $PythonExe)) {
    throw "No se encontró Python del entorno: $PythonExe"
}

$py = (Resolve-Path $PythonExe).Path
$output = Join-Path (Get-Location) $OutputDir
$engineFolder = Join-Path $output "qwen-engine"

Write-Host ""
Write-Host "Voice Studio AI - Motor Windows LEAN" -ForegroundColor Cyan
Write-Host "Python: $py" -ForegroundColor DarkGray
Write-Host "Salida: $engineFolder" -ForegroundColor DarkGray

& $py -m pip install --upgrade pyinstaller

if (Test-Path "engine\build") { Remove-Item "engine\build" -Recurse -Force }
if (Test-Path $engineFolder) { Remove-Item $engineFolder -Recurse -Force }
New-Item -ItemType Directory -Force -Path $output | Out-Null

powershell -ExecutionPolicy Bypass -File ".\scripts\prepare-qwen-vendor.ps1" -PythonExe $py | Out-Host
$vendorRoot = Join-Path (Resolve-Path ".\engine") "_vendor_slim"

$oldPythonPath = $env:PYTHONPATH
try {
    if ($oldPythonPath) { $env:PYTHONPATH = "$vendorRoot;$oldPythonPath" }
    else { $env:PYTHONPATH = "$vendorRoot" }

    & $py -m PyInstaller `
        --noconfirm `
        --clean `
        --onedir `
        --optimize 1 `
        --name qwen-engine `
        --distpath "$output" `
        --workpath engine\build `
        --specpath engine `
        --paths "$vendorRoot" `
        --collect-data qwen_tts `
        --hidden-import qwen_tts.inference.qwen3_tts_model `
        --hidden-import qwen_tts.inference.qwen3_tts_tokenizer `
        --hidden-import qwen_tts.core.models.configuration_qwen3_tts `
        --hidden-import qwen_tts.core.models.modeling_qwen3_tts `
        --hidden-import qwen_tts.core.models.processing_qwen3_tts `
        --hidden-import qwen_tts.core.tokenizer_12hz.configuration_qwen3_tts_tokenizer_v2 `
        --hidden-import qwen_tts.core.tokenizer_12hz.modeling_qwen3_tts_tokenizer_v2 `
        --exclude-module qwen_tts.cli `
        --exclude-module qwen_tts.core.tokenizer_25hz `
        --exclude-module onnxruntime `
        --exclude-module sox `
        --exclude-module gradio `
        --exclude-module pandas `
        --exclude-module sklearn `
        --exclude-module matplotlib `
        --exclude-module tensorflow `
        --exclude-module tensorboard `
        --exclude-module IPython `
        --exclude-module jupyter `
        --exclude-module notebook `
        --exclude-module cv2 `
        engine\server.py
}
finally {
    $env:PYTHONPATH = $oldPythonPath
}

$engineExe = Join-Path $engineFolder "qwen-engine.exe"
if (-not (Test-Path $engineExe)) { throw "PyInstaller no generó $engineExe" }

Write-Host ""
Write-Host "Self-test del motor..."
& $engineExe --self-test-packaging
if ($LASTEXITCODE -ne 0) { throw "El self-test del motor falló." }

$bytes = (Get-ChildItem $engineFolder -Recurse -File | Measure-Object Length -Sum).Sum
$gb = [math]::Round($bytes / 1GB, 2)
Write-Host "Motor creado: $gb GB" -ForegroundColor Green
