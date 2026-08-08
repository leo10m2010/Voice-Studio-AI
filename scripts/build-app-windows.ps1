$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..")

Write-Host ""
Write-Host "Voice Studio AI - Instalador ligero v0.7+" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor DarkGray
Write-Host "El Setup.exe ya NO contiene Python/PyTorch/Qwen." -ForegroundColor DarkGray
Write-Host "El motor se instala visualmente en el primer inicio." -ForegroundColor DarkGray

function Need-Command($name, $message) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) {
        Write-Host ""
        Write-Host "Falta: $name" -ForegroundColor Yellow
        Write-Host $message
        exit 1
    }
}

Need-Command "node" "Instala Node.js."
Need-Command "npm" "Instala Node.js/NPM."
Need-Command "cargo" "Instala Rust desde rustup.rs."
Need-Command "rustc" "Instala Rust desde rustup.rs."

Write-Host ""
Write-Host "1/3 Dependencias frontend..."
npm install

Write-Host ""
Write-Host "2/3 Cargo check..."
cargo check --manifest-path .\src-tauri\Cargo.toml

Write-Host ""
Write-Host "3/3 Tauri + NSIS..."
npm run tauri build -- --bundles nsis
if ($LASTEXITCODE -ne 0) {
    throw "Tauri/NSIS no pudo generar el instalador."
}

$bundlePath = ".\src-tauri\target\release\bundle\nsis"
$setups = @(Get-ChildItem $bundlePath -Filter "*setup.exe" -ErrorAction SilentlyContinue)
if ($setups.Count -eq 0) {
    throw "No se encontró ningún setup.exe."
}

Write-Host ""
Write-Host "INSTALADOR LISTO" -ForegroundColor Green
foreach ($setup in $setups) {
    $sizeMB = [math]::Round($setup.Length / 1MB, 1)
    Write-Host "  $($setup.FullName)" -ForegroundColor Cyan
    Write-Host "  Tamaño: $sizeMB MB" -ForegroundColor Green
}
Write-Host ""
Write-Host "En el primer inicio la app ofrecerá instalar el motor CPU/NVIDIA." -ForegroundColor DarkGray
