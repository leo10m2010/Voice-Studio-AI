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

# La URL del catálogo va compilada en el instalador. Si se fija a una Release
# versionada, una app antigua queda viendo para siempre el motor con el que
# salió y publicar una corrección nunca la alcanza. Tiene que ser el puntero
# estable 'engine-latest'.
$rust = Get-Content ".\src-tauri\src\lib.rs" -Raw
$manifestUrl = [regex]::Match(
    $rust,
    'ENGINE_MANIFEST_URL:\s*&str\s*=\s*"([^"]+)"'
).Groups[1].Value

if (-not $manifestUrl) {
    throw "No se pudo leer ENGINE_MANIFEST_URL de src-tauri\src\lib.rs."
}
if ($manifestUrl -match '/download/engine-v[0-9]') {
    throw "ENGINE_MANIFEST_URL está fijado a una Release versionada ($manifestUrl). Usa 'engine-latest' o las apps antiguas no recibirán motores nuevos."
}
if ($manifestUrl -notmatch '/download/engine-latest/engine-manifest\.json$') {
    throw "ENGINE_MANIFEST_URL no apunta al catálogo esperado: $manifestUrl"
}
Write-Host "Catálogo del motor sin fijar por versión: OK" -ForegroundColor Green

$frontendEngine = [regex]::Match(
    (Get-Content ".\src\main.js" -Raw),
    'REQUIRED_ENGINE_VERSION\s*=\s*"([^"]+)"'
).Groups[1].Value
if ($frontendEngine -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$') {
    throw "REQUIRED_ENGINE_VERSION no es una versión válida: '$frontendEngine'"
}
Write-Host "Motor mínimo exigido: $frontendEngine" -ForegroundColor Green

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
