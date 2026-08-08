param(
    [Parameter(Mandatory=$true)]
    [string]$PythonExe
)

$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..")

$vendorRoot = Join-Path (Resolve-Path ".\engine") "_vendor_slim"
$qwenTarget = Join-Path $vendorRoot "qwen_tts"

if (Test-Path $vendorRoot) {
    Remove-Item $vendorRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $vendorRoot | Out-Null

$qwenSource = & $PythonExe -c "import pathlib, qwen_tts; print(pathlib.Path(qwen_tts.__file__).resolve().parent)"
if (-not $qwenSource) {
    throw "No se pudo localizar qwen_tts en el entorno Python."
}

$qwenSource = $qwenSource.Trim()
if (-not (Test-Path $qwenSource)) {
    throw "No existe la carpeta qwen_tts detectada: $qwenSource"
}

Write-Host "Preparando qwen_tts 12Hz-only para PyInstaller..." -ForegroundColor Cyan
Write-Host "Origen: $qwenSource" -ForegroundColor DarkGray

Copy-Item $qwenSource $qwenTarget -Recurse -Force

# La app solo usa la familia Qwen3-TTS Tokenizer 12Hz.
$removePaths = @(
    (Join-Path $qwenTarget "cli"),
    (Join-Path $qwenTarget "core\tokenizer_25hz")
)
foreach ($path in $removePaths) {
    if (Test-Path $path) {
        Remove-Item $path -Recurse -Force
    }
}

# qwen_tts.__init__ upstream también importa el wrapper genérico del tokenizer.
# Lo conservamos, pero su implementación se parchea abajo para registrar solo V2/12Hz.
$tokenizerFile = Join-Path $qwenTarget "inference\qwen3_tts_tokenizer.py"
$tokenizer = Get-Content $tokenizerFile -Raw

# Regex tolera tanto LF como CRLF del wheel de Python.
$importPattern = '(?ms)^from \.\.core import \(\s*Qwen3TTSTokenizerV1Config,\s*Qwen3TTSTokenizerV1Model,\s*Qwen3TTSTokenizerV2Config,\s*Qwen3TTSTokenizerV2Model,\s*\)\s*'
$newImport = @'
from ..core.tokenizer_12hz.configuration_qwen3_tts_tokenizer_v2 import Qwen3TTSTokenizerV2Config
from ..core.tokenizer_12hz.modeling_qwen3_tts_tokenizer_v2 import Qwen3TTSTokenizerV2Model

'@

$patched = [regex]::Replace($tokenizer, $importPattern, $newImport, 1)
if ($patched -eq $tokenizer) {
    throw "No se encontró el bloque de imports V1/V2 esperado en qwen3_tts_tokenizer.py"
}
$tokenizer = $patched

$registerPattern = '(?ms)^\s*AutoConfig\.register\("qwen3_tts_tokenizer_25hz",\s*Qwen3TTSTokenizerV1Config\)\s*\r?\n\s*AutoModel\.register\(Qwen3TTSTokenizerV1Config,\s*Qwen3TTSTokenizerV1Model\)\s*\r?\n'
$patched = [regex]::Replace($tokenizer, $registerPattern, '', 1)
if ($patched -eq $tokenizer) {
    throw "No se encontró el registro del tokenizer 25Hz esperado."
}
$tokenizer = $patched

if ($tokenizer.Contains("Qwen3TTSTokenizerV1Config") -or $tokenizer.Contains("Qwen3TTSTokenizerV1Model")) {
    throw "El wrapper de tokenizer todavía contiene referencias V1/25Hz después del parche."
}

Set-Content -Path $tokenizerFile -Value $tokenizer -Encoding UTF8

# Evita que importar qwen_tts.core vuelva a exigir tokenizer_25hz.
$coreInit = Join-Path $qwenTarget "core\__init__.py"
@'
# Voice Studio AI packaged runtime: Qwen3-TTS 12Hz only.
from .tokenizer_12hz.configuration_qwen3_tts_tokenizer_v2 import Qwen3TTSTokenizerV2Config
from .tokenizer_12hz.modeling_qwen3_tts_tokenizer_v2 import Qwen3TTSTokenizerV2Model

__all__ = [
    "Qwen3TTSTokenizerV2Config",
    "Qwen3TTSTokenizerV2Model",
]
'@ | Set-Content -Path $coreInit -Encoding UTF8

Write-Host "Vendor 12Hz listo: $vendorRoot" -ForegroundColor Green
Write-Output $vendorRoot
