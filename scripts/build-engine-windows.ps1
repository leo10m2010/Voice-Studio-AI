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

& $py -m pip install --upgrade pyinstaller==6.22.0 pyinstaller-hooks-contrib==2026.6
if ($LASTEXITCODE -ne 0) { throw "No se pudo instalar PyInstaller." }

if (Test-Path "engine\build") { Remove-Item "engine\build" -Recurse -Force }
if (Test-Path $engineFolder) { Remove-Item $engineFolder -Recurse -Force }
New-Item -ItemType Directory -Force -Path $output | Out-Null

powershell -ExecutionPolicy Bypass -File ".\scripts\prepare-qwen-vendor.ps1" -PythonExe $py | Out-Host
if ($LASTEXITCODE -ne 0) { throw "No se pudo preparar el vendor de Qwen3-TTS 12Hz." }
$vendorRoot = Join-Path (Resolve-Path ".\engine") "_vendor_slim"

$oldPythonPath = $env:PYTHONPATH
try {
    if ($oldPythonPath) { $env:PYTHONPATH = "$vendorRoot;$oldPythonPath" }
    else { $env:PYTHONPATH = "$vendorRoot" }

    Write-Host "Validando import de Qwen3-TTS 12Hz antes de PyInstaller..."
    & $py -c "from qwen_tts import Qwen3TTSModel; from qwen_tts.core.tokenizer_12hz.configuration_qwen3_tts_tokenizer_v2 import Qwen3TTSTokenizerV2Config; from qwen_tts.core.tokenizer_12hz.modeling_qwen3_tts_tokenizer_v2 import Qwen3TTSTokenizerV2Model; print('Qwen3-TTS 12Hz import: OK')"
    if ($LASTEXITCODE -ne 0) {
        throw "El vendor de Qwen3-TTS 12Hz no se puede importar. Se cancela el empaquetado."
    }

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
        --exclude-module matplotlib `
        --exclude-module tensorflow `
        --exclude-module tensorboard `
        --exclude-module IPython `
        --exclude-module jupyter `
        --exclude-module notebook `
        --exclude-module cv2 `
        engine\server.py
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller no pudo compilar qwen-engine.exe."
    }
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
