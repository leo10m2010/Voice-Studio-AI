$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..")

Write-Host ""
Write-Host "Qwen Voice Studio - Preparacion de Windows" -ForegroundColor Cyan
Write-Host "------------------------------------------------" -ForegroundColor DarkGray

function Find-Python312 {
    try {
        & py -3.12 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return "py -3.12"
        }
    } catch {}

    try {
        $version = & python --version 2>&1
        if ($version -match "Python 3\.12") {
            return "python"
        }
    } catch {}

    return $null
}

$pythonCommand = Find-Python312

if (-not $pythonCommand) {
    Write-Host ""
    Write-Host "Falta Python 3.12." -ForegroundColor Yellow
    Write-Host "Instalalo y vuelve a ejecutar este archivo."
    Write-Host ""
    Write-Host "Con winget:" -ForegroundColor Gray
    Write-Host "winget install -e --id Python.Python.3.12"
    exit 1
}

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creando entorno virtual .venv..."
    if ($pythonCommand -eq "py -3.12") {
        & py -3.12 -m venv .venv
    } else {
        & python -m venv .venv
    }
}

$py = Resolve-Path ".venv\Scripts\python.exe"
$pipArgs = @("-m", "pip")

Write-Host "Actualizando pip..."
& $py @pipArgs install --upgrade pip setuptools wheel

$hasNvidia = $false
try {
    $null = Get-Command nvidia-smi -ErrorAction Stop
    $hasNvidia = $true
} catch {}

if ($hasNvidia) {
    Write-Host ""
    Write-Host "NVIDIA detectada. Instalando PyTorch CUDA 12.6..." -ForegroundColor Green
    Write-Host "CUDA 12.6 se usa para conservar compatibilidad con GTX 10-series y RTX modernas." -ForegroundColor DarkGray
    & $py @pipArgs install --upgrade --force-reinstall `
        torch==2.10.0 torchaudio==2.10.0 `
        --index-url https://download.pytorch.org/whl/cu126
} else {
    Write-Host ""
    Write-Host "No se detecto NVIDIA. Instalando PyTorch CPU..." -ForegroundColor Yellow
    & $py @pipArgs install --upgrade --force-reinstall `
        torch==2.10.0 torchaudio==2.10.0 `
        --index-url https://download.pytorch.org/whl/cpu
}

Write-Host ""
Write-Host "Instalando Qwen3-TTS y servidor local..."
& $py @pipArgs install -r engine\requirements.txt

Write-Host ""
Write-Host "Comprobando PyTorch..."
& $py -c "import torch; print('Torch:', torch.__version__); print('CUDA:', torch.cuda.is_available()); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"

if (-not (Test-Path "node_modules")) {
    Write-Host ""
    Write-Host "Instalando dependencias de la interfaz..."
    npm install
}

Write-Host ""
Write-Host "Preparacion terminada." -ForegroundColor Green
Write-Host ""
Write-Host "PRUEBA SIN TAURI:"
Write-Host "  npm run local" -ForegroundColor Cyan
Write-Host ""
Write-Host "Luego abre:"
Write-Host "  http://127.0.0.1:5173" -ForegroundColor Cyan
Write-Host ""
Write-Host "La primera generacion descargara Qwen3-TTS 0.6B (~2.5 GB)." -ForegroundColor DarkGray
Write-Host ""
