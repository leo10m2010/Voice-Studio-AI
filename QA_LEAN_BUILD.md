# QA — Lean Windows Packaging v0.6.13

## Problema observado

El build anterior generó:

- `engine-dist\qwen-engine`: 4.29 GB
- PyInstaller analizaba cientos de submódulos de Transformers/Torch
- NSIS terminó fallando al crear el `setup.exe`

## Causa principal

El script usaba:

```text
--collect-all qwen_tts
--collect-all transformers
--collect-all librosa
--collect-all soundfile
--collect-all torchaudio
--collect-all torch
```

`--collect-all` obliga a PyInstaller a arrastrar submódulos y datos que
Voice Studio AI nunca ejecuta.

## Nuevo empaquetado

Se eliminan todos esos `collect-all` grandes.

Se incluyen explícitamente:
- runtime normal detectado por PyInstaller;
- datos de qwen_tts;
- Qwen3TTSModel;
- modelos/config/procesador Qwen3-TTS;
- tokenizer 12Hz.

Se excluyen:
- qwen_tts CLI;
- tokenizer Qwen 25Hz;
- onnxruntime/sox de la ruta 25Hz;
- Gradio;
- pandas;
- matplotlib;
- TensorFlow;
- TensorBoard;
- IPython/Jupyter/notebook;
- OpenCV.

## qwen_tts 12Hz-only

Durante el build se crea temporalmente:

`engine\_vendor_slim\qwen_tts`

a partir de la instalación oficial de qwen-tts.

No se modifica permanentemente el paquete de `.venv`.

Se elimina del vendor empaquetado:
- `qwen_tts/cli`
- `qwen_tts/core/tokenizer_25hz`

y el wrapper de tokenizer registra únicamente Tokenizer V2 / 12Hz.

## Nota: `scikit-learn` NO se puede excluir

`librosa` importa `sklearn` (`decompose`/`segment`) en su `__init__.py`, así
que es una dependencia dura, no opcional. Excluirla con
`--exclude-module sklearn` rompía `import librosa` en el motor empaquetado y
causaba `No se pudo preparar '<archivo>'. No module named 'sklearn'` al subir
cualquier voz nueva. Se eliminó ese exclude-module.

## Self-test obligatorio

Después de PyInstaller y ANTES de NSIS:

```powershell
engine-dist\qwen-engine\qwen-engine.exe --self-test-packaging
```

Debe comprobar:
- numpy
- soundfile
- librosa
- torch
- transformers
- accelerate
- huggingface_hub
- qwen_tts.Qwen3TTSModel

Si cualquiera falla, el build se detiene.

## Build local

```powershell
npm run build:windows
```

Resultado esperado:

`src-tauri\target\release\bundle\nsis\*setup.exe`

El script muestra:
- tamaño total del engine;
- 20 archivos más pesados;
- tamaño final del instalador;
- si el setup queda por debajo de 2 GiB.

El parche del vendor usa regex compatible con archivos LF y CRLF.
