$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..")

Write-Host "Voice Studio AI - comprobación antes de crear tag" -ForegroundColor Cyan
Write-Host ""

$package = Get-Content ".\package.json" -Raw | ConvertFrom-Json
$version = [string]$package.version
$expectedTag = "v$version"

$rust = Get-Content ".\src-tauri\src\lib.rs" -Raw

if ($rust.Contains("if let Ok(mut guard) = state.0.lock()")) {
    throw "Tu src-tauri\src\lib.rs todavía contiene el código viejo que provoca E0597."
}

if (-not $rust.Contains("terminate_engine(state.inner(), expected_stop.inner())")) {
    throw "No se encontró el fix Rust esperado."
}

$dirty = git status --porcelain
if ($dirty) {
    Write-Host "Hay cambios sin commit:" -ForegroundColor Yellow
    git status --short
    throw "Haz commit de TODOS los cambios antes de crear el tag."
}

Write-Host "HEAD:"
git log -1 --decorate --oneline

Write-Host ""
Write-Host "Código Rust correcto." -ForegroundColor Green
Write-Host "Árbol Git limpio." -ForegroundColor Green
Write-Host ""
Write-Host "Tag que debes crear DESPUÉS de este commit: $expectedTag" -ForegroundColor Cyan
