param(
    [string]$Tag = "voices-latest",
    [string]$VoiceDir = "assets/voice",
    # Sin esto sube todas las de la carpeta, que ya viajan en el instalador.
    # Normalmente solo interesan las publicadas despues del ultimo instalador.
    [string[]]$Only = @()
)

# Publica las voces de assets/voice como catálogo descargable.
#
# Las voces incluidas en el instalador solo llegan a un equipo cuando instala
# esa versión de la app. Este catálogo es una Release fija cuyo JSON se
# sobrescribe, así que una voz nueva llega a todos los equipos sin sacar
# instalador: el motor la ve al arrancar, o al pulsar "Buscar voces nuevas".
#
# Igual que engine-latest, NO se versiona el tag: si apuntara a una Release por
# versión, una app antigua se quedaría viendo el catálogo con el que salió.

$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..")

$repo = (gh repo view --json nameWithOwner --jq .nameWithOwner)
if (-not $repo) { throw "No se pudo determinar el repositorio con gh." }

$carpeta = Resolve-Path $VoiceDir
$audios = Get-ChildItem $carpeta -File | Where-Object { $_.Extension -in ".mp3", ".wav", ".flac" }
# Invocado con -File, PowerShell pasa "a.mp3,b.mp3" como UNA cadena en vez de
# como array, asi que se separa a mano y se aceptan las dos formas.
$pedidas = @()
foreach ($item in $Only) {
    $pedidas += ($item -split ",") | ForEach-Object { $_.Trim() } | Where-Object { $_ }
}

if ($pedidas.Count -gt 0) {
    $audios = @($audios | Where-Object { $pedidas -contains $_.Name -or $pedidas -contains $_.BaseName })
    $faltan = @($pedidas | Where-Object { $nombre = $_; -not ($audios | Where-Object { $_.Name -eq $nombre -or $_.BaseName -eq $nombre }) })
    if ($faltan.Count -gt 0) {
        throw "No estan en $carpeta : $($faltan -join ', ')"
    }
}
if ($audios.Count -eq 0) { throw "No hay voces en $carpeta." }

Write-Host "Repositorio: $repo" -ForegroundColor Cyan
Write-Host "Voces encontradas: $($audios.Count)" -ForegroundColor Cyan

# gh escribe en stderr cuando la Release no existe y, con ErrorActionPreference
# en Stop, PowerShell 5.1 lo convierte en excepcion aunque sea el caso normal.
$previo = $ErrorActionPreference
$ErrorActionPreference = "Continue"
gh release view $Tag --repo $repo | Out-Null
$existe = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $previo

if (-not $existe) {
    gh release create $Tag --repo $repo --title "Catalogo de voces" `
        --notes "Voces descargables de Voice Studio AI. El motor consulta este catalogo al arrancar."
    if ($LASTEXITCODE -ne 0) { throw "No se pudo crear la Release $Tag." }
    Write-Host "Release $Tag creada." -ForegroundColor Green
}

$entradas = @()
foreach ($audio in $audios) {
    gh release upload $Tag $audio.FullName --repo $repo --clobber
    if ($LASTEXITCODE -ne 0) { throw "No se pudo subir $($audio.Name)." }

    # La transcripción viaja dentro del JSON, no como archivo suelto: así el
    # motor la escribe junto a la voz sin una segunda descarga que pueda fallar.
    $texto = ""
    $sidecar = "$($audio.FullName).txt"
    if (Test-Path $sidecar) { $texto = (Get-Content $sidecar -Raw -Encoding UTF8).Trim() }

    $entradas += [ordered]@{
        name       = $audio.Name
        url        = "https://github.com/$repo/releases/download/$Tag/$($audio.Name)"
        sha256     = (Get-FileHash $audio.FullName -Algorithm SHA256).Hash.ToLower()
        bytes      = $audio.Length
        transcript = $texto
    }
    Write-Host "  subida $($audio.Name) ($([math]::Round($audio.Length/1KB)) KB)" -ForegroundColor Green
}

$manifiesto = [ordered]@{
    schema       = 1
    published_at = (Get-Date).ToUniversalTime().ToString("o")
    voices       = $entradas
}

$destino = Join-Path $env:TEMP "voices-manifest.json"
# Out-File -Encoding utf8 escribe BOM en PowerShell 5.1 y eso rompe a cualquier
# lector estricto de JSON. Se escribe UTF-8 sin BOM a proposito.
$json = $manifiesto | ConvertTo-Json -Depth 6
[System.IO.File]::WriteAllText($destino, $json, (New-Object System.Text.UTF8Encoding $false))
gh release upload $Tag $destino --repo $repo --clobber
if ($LASTEXITCODE -ne 0) { throw "No se pudo subir el manifiesto." }

Write-Host ""
Write-Host "Catálogo publicado con $($entradas.Count) voces." -ForegroundColor Green
Write-Host "Los equipos las verán al abrir la app, o con 'Buscar voces nuevas'." -ForegroundColor Cyan
