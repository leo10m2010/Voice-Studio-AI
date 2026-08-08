$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..")

$package = Get-Content "package.json" -Raw | ConvertFrom-Json
$tauri = Get-Content "src-tauri\tauri.conf.json" -Raw | ConvertFrom-Json

$cargoText = Get-Content "src-tauri\Cargo.toml" -Raw
$cargoMatch = [regex]::Match(
    $cargoText,
    '(?ms)^\[package\]\s*.*?^version\s*=\s*"([^"]+)"'
)

if (-not $cargoMatch.Success) {
    throw "No se pudo leer la version de src-tauri\Cargo.toml"
}

$packageVersion = [string]$package.version
$tauriVersion = [string]$tauri.version
$cargoVersion = [string]$cargoMatch.Groups[1].Value

Write-Host "package.json:          $packageVersion"
Write-Host "tauri.conf.json:       $tauriVersion"
Write-Host "src-tauri/Cargo.toml:  $cargoVersion"

if (
    $packageVersion -ne $tauriVersion -or
    $packageVersion -ne $cargoVersion
) {
    throw "Las versiones no coinciden. Sincronizalas antes de publicar."
}

if ($env:GITHUB_REF_TYPE -eq "tag") {
    $expectedTag = "v$packageVersion"
    if ($env:GITHUB_REF_NAME -ne $expectedTag) {
        throw "El tag '$($env:GITHUB_REF_NAME)' no coincide con '$expectedTag'."
    }
}

Write-Host ""
Write-Host "Version correcta: v$packageVersion" -ForegroundColor Green
