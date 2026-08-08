$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..")

Write-Host ""
Write-Host "Voice Studio AI - Compilacion para Windows" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor DarkGray

function Need-Command($name, $message) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        Write-Host ""
        Write-Host "Falta: $name" -ForegroundColor Yellow
        Write-Host $message
        exit 1
    }
}

Need-Command "node" "Instala Node.js y vuelve a ejecutar."
Need-Command "npm" "Instala Node.js/NPM y vuelve a ejecutar."
Need-Command "cargo" "Instala Rust desde https://rustup.rs/ y vuelve a abrir PowerShell."
Need-Command "rustc" "Instala Rust desde https://rustup.rs/."

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host ""
    Write-Host "Preparando el motor Python..." -ForegroundColor Yellow
    powershell -ExecutionPolicy Bypass -File ".\scripts\setup-windows.ps1"
}

Write-Host ""
Write-Host "1/4 Instalando dependencias de interfaz..."
npm install

Write-Host ""
Write-Host "2/4 Actualizando dependencias del motor..."
.\.venv\Scripts\python.exe -m pip install -r .\engine\requirements.txt

Write-Host ""
Write-Host "3/4 Empaquetando motor Python/PyTorch..."
powershell -ExecutionPolicy Bypass -File ".\scripts\build-engine-windows.ps1"

Write-Host ""
Write-Host "4/4 Generando instalador NSIS..."
npm run tauri build -- --bundles nsis

$bundle = Resolve-Path ".\src-tauri\target\release\bundle\nsis" -ErrorAction SilentlyContinue
Write-Host ""
Write-Host "COMPILACION TERMINADA" -ForegroundColor Green
if ($bundle) {
    Write-Host "Instalador:" -ForegroundColor Green
    Write-Host "  $bundle"
    Get-ChildItem $bundle -Filter "*setup.exe" | ForEach-Object {
        Write-Host "  $($_.FullName)" -ForegroundColor Cyan
    }
}
Write-Host ""
Write-Host "Nota: el instalador puede ser grande porque el motor incluye PyTorch."
Write-Host "Los modelos Qwen no se incluyen: se descargan la primera vez y quedan en cache."
