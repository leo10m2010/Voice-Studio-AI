param(
    [ValidateSet("cpu","nvidia")]
    [string]$Flavor = "nvidia",
    [string]$EngineVersion = "1.0.3"
)

$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..")

$buildRoot = ".engine-build\$Flavor"
$venv = "$buildRoot\.venv"
$python = "$venv\Scripts\python.exe"
$output = "$buildRoot\dist"

$bootstrapPython = $null
try {
    $version = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
    if ($LASTEXITCODE -eq 0 -and $version.Trim() -eq "3.12") {
        $bootstrapPython = "python"
    }
} catch {}

if (-not $bootstrapPython) {
    try {
        & py -3.12 -c "import sys; print(sys.executable)" 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $bootstrapPython = "py"
        }
    } catch {}
}

if (-not $bootstrapPython) {
    throw "Se necesita Python 3.12 solo para CREAR el paquete del motor. Los usuarios finales no lo necesitarán."
}

if (-not (Test-Path $python)) {
    New-Item -ItemType Directory -Force -Path $buildRoot | Out-Null
    if ($bootstrapPython -eq "py") {
        & py -3.12 -m venv $venv
    } else {
        & python -m venv $venv
    }
}

& $python -m pip install --upgrade pip setuptools wheel
if ($LASTEXITCODE -ne 0) { throw "No se pudo actualizar pip para el motor $Flavor." }

if ($Flavor -eq "nvidia") {
    Write-Host "Instalando PyTorch CUDA 12.6..." -ForegroundColor Cyan
    & $python -m pip install --upgrade --force-reinstall torch==2.10.0 torchaudio==2.10.0 --index-url https://download.pytorch.org/whl/cu126
} else {
    Write-Host "Instalando PyTorch CPU..." -ForegroundColor Cyan
    & $python -m pip install --upgrade --force-reinstall torch==2.10.0 torchaudio==2.10.0 --index-url https://download.pytorch.org/whl/cpu
}
if ($LASTEXITCODE -ne 0) { throw "No se pudo instalar PyTorch para el motor $Flavor." }

& $python -m pip install -r .\engine\requirements.txt
if ($LASTEXITCODE -ne 0) { throw "No se pudieron instalar las dependencias del motor $Flavor." }

powershell -ExecutionPolicy Bypass -File .\scripts\build-engine-windows.ps1 `
    -PythonExe "$python" `
    -OutputDir "$output"
if ($LASTEXITCODE -ne 0) { throw "Fallo la compilacion del motor $Flavor." }

powershell -ExecutionPolicy Bypass -File .\scripts\package-engine-assets.ps1 `
    -Flavor "$Flavor" `
    -EngineDir "$output\qwen-engine" `
    -Version "$EngineVersion" `
    -OutputDir "engine-release"
if ($LASTEXITCODE -ne 0) { throw "Fallo el empaquetado del motor $Flavor v$EngineVersion." }
