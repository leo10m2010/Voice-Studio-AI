$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..")

Write-Host "Voice Studio AI - comprobación antes de crear tag" -ForegroundColor Cyan
Write-Host ""

$package = Get-Content ".\package.json" -Raw | ConvertFrom-Json
$version = [string]$package.version
$expectedTag = "v$version"

# Comprobaciones reales en vez de buscar cadenas concretas en el código: esos
# greps se rompían en cada refactor y no probaban que nada funcionara.
Write-Host "Compilando Rust en modo release..."
Push-Location ".\src-tauri"
try {
    cargo check --release --quiet
    if ($LASTEXITCODE -ne 0) { throw "cargo check --release falló." }
    cargo test --quiet
    if ($LASTEXITCODE -ne 0) { throw "cargo test falló." }
}
finally { Pop-Location }

Write-Host "Ejecutando pruebas del motor..."
& ".\.venv\Scripts\python.exe" -m unittest discover -s tests -p "test_*.py"
if ($LASTEXITCODE -ne 0) { throw "Las pruebas del motor fallaron." }

# La versión del motor tiene que coincidir entre el frontend y el catálogo que
# Rust descarga; si no, la app pide actualizar a una versión que no existe.
$frontendEngine = [regex]::Match(
    (Get-Content ".\src\main.js" -Raw),
    'REQUIRED_ENGINE_VERSION\s*=\s*"([^"]+)"'
).Groups[1].Value
$manifestEngine = [regex]::Match(
    (Get-Content ".\src-tauri\src\lib.rs" -Raw),
    'engine-v([0-9]+\.[0-9]+\.[0-9]+)/engine-manifest\.json'
).Groups[1].Value

if (-not $frontendEngine -or -not $manifestEngine) {
    throw "No se pudo leer la versión del motor del frontend o del catálogo."
}
if ($frontendEngine -ne $manifestEngine) {
    throw "REQUIRED_ENGINE_VERSION ($frontendEngine) no coincide con el catálogo publicado ($manifestEngine)."
}
Write-Host "Motor requerido y catálogo coinciden: $frontendEngine" -ForegroundColor Green

$dirty = git status --porcelain
if ($dirty) {
    Write-Host "Hay cambios sin commit:" -ForegroundColor Yellow
    git status --short
    throw "Haz commit de TODOS los cambios antes de crear el tag."
}

Write-Host "HEAD:"
git log -1 --decorate --oneline

Write-Host ""
Write-Host "Rust y pruebas del motor en verde." -ForegroundColor Green
Write-Host "Árbol Git limpio." -ForegroundColor Green
Write-Host ""
Write-Host "Tag que debes crear DESPUÉS de este commit: $expectedTag" -ForegroundColor Cyan
