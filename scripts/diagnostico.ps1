$ErrorActionPreference = "Continue"
Set-Location (Resolve-Path "$PSScriptRoot\..")

Write-Host ""
Write-Host "Qwen Voice Studio - Diagnostico" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor DarkGray

Write-Host ""
Write-Host "Node:"
node --version

Write-Host ""
Write-Host "NPM:"
npm --version

Write-Host ""
Write-Host "Python:"
if (Test-Path ".venv\Scripts\python.exe") {
    $venvPy = (Resolve-Path ".venv\Scripts\python.exe").Path
    & $venvPy --version
    if ($LASTEXITCODE -ne 0) {
        Write-Host ".venv existe, pero no puede iniciar. Ejecuta setup-windows.ps1 para recrearlo." -ForegroundColor Yellow
    } else {
        & $venvPy -c "import torch; print('Torch:', torch.__version__); print('CUDA:', torch.cuda.is_available()); print('CUDA runtime:', torch.version.cuda); print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'); print('VRAM GB:', round(torch.cuda.get_device_properties(0).total_memory/1024**3,2) if torch.cuda.is_available() else '-')"
        & $venvPy -c "from qwen_tts import Qwen3TTSModel; print('qwen_tts import: OK')"
    }
} else {
    Write-Host ".venv no existe." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "NVIDIA:"
try {
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
} catch {
    Write-Host "nvidia-smi no disponible."
}

Write-Host ""
