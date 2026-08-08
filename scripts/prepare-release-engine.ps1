$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..")

Write-Host ""
Write-Host "Voice Studio AI - Preparando motor para Release" -ForegroundColor Cyan
Write-Host "El runner no necesita GPU: se empaqueta el runtime CUDA para el usuario final." -ForegroundColor DarkGray

if (Test-Path ".venv") {
    Remove-Item ".venv" -Recurse -Force
}

python -m venv .venv
$py = Resolve-Path ".venv\Scripts\python.exe"

& $py -m pip install --upgrade pip setuptools wheel

Write-Host ""
Write-Host "Instalando PyTorch CUDA 12.6..."
& $py -m pip install `
    torch==2.10.0 `
    torchaudio==2.10.0 `
    --index-url https://download.pytorch.org/whl/cu126

Write-Host ""
Write-Host "Instalando dependencias del motor..."
& $py -m pip install -r engine\requirements.txt

Write-Host ""
Write-Host "Verificando runtime..."
& $py -c "import torch; import qwen_tts; print('Torch:', torch.__version__); print('CUDA runtime:', torch.version.cuda); print('qwen_tts: OK')"

Write-Host ""
Write-Host "Empaquetando sidecar Python LEAN..."
powershell -ExecutionPolicy Bypass -File ".\scripts\build-engine-windows.ps1"

$engineBytes = (
    Get-ChildItem ".\engine-dist\qwen-engine" -Recurse -File |
    Measure-Object -Property Length -Sum
).Sum

$engineGB = [math]::Round($engineBytes / 1GB, 2)

Write-Host ""
Write-Host "Motor empaquetado: $engineGB GB" -ForegroundColor Green

if ($engineBytes -gt 1.85GB) {
    Write-Warning "El motor sin comprimir supera 1.85 GB. GitHub Release limita cada asset a menos de 2 GiB; revisa el tamano final del NSIS."
}
