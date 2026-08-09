# Qwen Voice Studio

Aplicación local para Windows basada en Qwen3-TTS 12Hz 0.6B Base.

Objetivo:
- importar una voz propia o autorizada;
- escribir un guion;
- generar la locución localmente;
- agregar música de fondo;
- guardar WAV;
- después convertir la misma interfaz en un instalador Tauri.

## Qué versión es esta

Esta entrega incluye dos formas de probar exactamente el mismo programa:

### A. Prueba local sencilla, recomendada primero

No requiere Rust ni Visual Studio Build Tools.

Después de preparar dependencias:

```powershell
npm run local
```

Abre:

```text
http://127.0.0.1:5173
```

Esto ya prueba el motor real Qwen3-TTS de tu PC.

### B. Tauri

Cuando el motor ya funcione:

```powershell
npm run desktop
```

Esto abre la misma interfaz como aplicación Tauri.

Para Tauri necesitas además Rust y las herramientas de compilación de Windows.

---

# Instalación inicial en Windows

## 1. Requisitos

Necesitas:

- Windows 10/11
- Node.js
- Python 3.12
- conexión a internet durante instalación y primera descarga del modelo

Si no tienes Python 3.12:

```powershell
winget install -e --id Python.Python.3.12
```

## 2. Instalar todo lo necesario para Qwen

Desde PowerShell, dentro de esta carpeta:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup-windows.ps1
```

El script:

1. crea `.venv`;
2. detecta si hay NVIDIA;
3. instala PyTorch CUDA 12.6 cuando existe NVIDIA;
4. instala Qwen3-TTS;
5. instala el servidor local;
6. instala las dependencias web si hace falta;
7. comprueba CUDA.

Se usa la rama CUDA 12.6 por compatibilidad con GPU Pascal como GTX 1050 y también con GPU RTX modernas.

## 3. Probar

```powershell
npm run local
```

O haz doble clic en:

```text
INICIAR_PRUEBA.bat
```

Abre:

```text
http://127.0.0.1:5173
```

---

# GTX 1050 y RTX 4060

La aplicación detecta VRAM.

## RTX 4060

En modo Automático debería elegir:

```text
CUDA
```

Es la máquina adecuada para trabajar normalmente.

## GTX 1050

La GTX 1050 normalmente tiene poca VRAM para cargar cómodamente la implementación oficial de Qwen3-TTS 0.6B.

Por eso `Automático` usa esta regla:

```text
>= 5.5 GB VRAM  -> CUDA
<  5.5 GB VRAM  -> CPU
```

En la GTX 1050 podrás hacer una prueba real, pero en CPU puede tardar bastante.

Existe la opción:

```text
GPU experimental
```

para forzar CUDA. Si la GPU se queda sin memoria, aparecerá el error correspondiente.

En modo Automático, si una GPU inicialmente elegida se queda sin memoria, el motor intenta volver a CPU.

---

# Primera generación

Qwen descarga el modelo oficial:

```text
Qwen/Qwen3-TTS-12Hz-0.6B-Base
```

El modelo queda guardado en:

```text
%LOCALAPPDATA%\QwenVoiceStudio\huggingface
```

No vuelve a descargarlo cada vez.

Los archivos del usuario quedan en:

```text
%LOCALAPPDATA%\QwenVoiceStudio\
├── voices
├── sounds
├── outputs
└── huggingface
```

---

# Clonación de voz

Qwen tiene dos modos que este programa maneja automáticamente.

## Con transcripción

Si proporcionas la transcripción exacta del audio:

```text
audio de referencia + texto exacto hablado
```

el programa usa el modo ICL de Qwen.

Es la opción recomendada para mejor similitud.

## Sin transcripción

Si no escribes la transcripción, activa automáticamente:

```text
x_vector_only_mode = true
```

Así el usuario puede simplemente seleccionar un audio y generar.

Es más sencillo, aunque la calidad de clonación puede ser inferior.

---

# Música

Los fondos se guardan localmente.

Qwen solo genera la voz.

La mezcla final:

```text
voz + música
```

se hace en el motor Python local antes de guardar el WAV/FLAC. El navegador
solo reproduce el archivo definitivo.

La música no se envía a ningún servicio externo.

---

# Diagnóstico

Si algo falla:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\diagnostico.ps1
```

Copia la salida si necesitas revisar:

- versión de Torch;
- CUDA;
- GPU;
- VRAM;
- importación de qwen_tts.

---

# Probar en Tauri

Primero asegúrate de que:

```powershell
npm run local
```

genera voz correctamente.

Después instala los requisitos de Tauri para Windows y ejecuta:

```powershell
npm run desktop
```

Tauri inicia automáticamente el motor Python desde `.venv`.

---

# Crear un instalador en el futuro

El proyecto ya incluye una ruta experimental para empaquetar el motor Python:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-engine-windows.ps1
```

Esto usa PyInstaller en modo `onedir`, porque PyTorch/Qwen son grandes y un único EXE comprimido tendría un arranque muy lento.

Después:

```powershell
npm run tauri build
```

La carpeta `engine-dist` está declarada como recurso de Tauri.

Conviene validar primero la generación en las dos GPUs antes de producir el instalador definitivo, porque el motor empaquetado será grande.

---

# Seguridad y uso

Usa únicamente voces propias o voces para las que tengas autorización de clonación y utilización.


---

# V0.2 — Fidelidad y listas largas

Esta versión agrega:

- scroll independiente en la biblioteca de voces;
- edición de la transcripción de cualquier voz ya importada;
- modo ICL visible en la biblioteca;
- presets `Más fiel`, `Natural` y `Más expresivo`;
- controles avanzados reales de Qwen:
  - `temperature`;
  - `top_p`;
  - `top_k`;
  - `repetition_penalty`;
  - `subtalker_temperature`.

Importante: Qwen3-TTS Base no ofrece un parámetro oficial equivalente a `Similarity Boost` de ElevenLabs. Los controles anteriores son parámetros de muestreo. Para clonación, la mejora principal suele venir de usar una referencia limpia y su transcripción exacta.


---

# V0.3 — Eleven-style Settings + Tone controls + AI motion

The interface was redesigned around a familiar TTS workflow:

- large script editor;
- right-side `Settings / History`;
- voice picker with search and independent scroll;
- model card;
- Speed;
- Stability;
- Similarity (experimental mapping);
- Style Exaggeration;
- Tone / Pitch;
- Language Override;
- WAV/FLAC output;
- Speaker boost;
- processing mode in Advanced;
- local generation history.

## Important mapping

Qwen3-TTS Base voice cloning does **not** expose native controls named Stability,
Similarity, Style Exaggeration, Speed, Pitch or Speaker Boost.

This app maps the familiar controls as follows:

- **Stability** → official Qwen sampling controls:
  `temperature`, `top_p`, `top_k`, `repetition_penalty`,
  `subtalker_temperature`, `subtalker_top_p`, `subtalker_top_k`.
- **Similarity** → experimental conservative-sampling adjustment.
  It is NOT a real speaker-embedding similarity weight.
- **Style Exaggeration** → increases controlled sampling variation.
- **Speed** → local `librosa` time-stretch after Qwen generation.
- **Tone / Pitch** → local pitch-shift after Qwen generation.
- **Speaker boost** → local RMS normalization + soft limiting.
- **Highest clone fidelity** → clean reference audio + exact reference transcript
  so Qwen uses ICL rather than x-vector-only mode.

## Motion system

The UI uses lightweight CSS/JS motion inspired by production interaction patterns:

- sliding tab indicator;
- side-panel reveal for voice selection;
- modal scale/reveal;
- staggered list reveal;
- spinner → success check;
- toast blur/reveal;
- animated AI orb during generation;
- animated border beam around Generate while Qwen is working.

No animation package is required at runtime.
`prefers-reduced-motion` is respected.


---

# V0.4 — Cleaner status, Spanish default and spot workflow

Changes:

- the large persistent green `Ready` orb was removed;
- the orb now appears only in a thin transient generation strip while Qwen is working;
- after success, the strip collapses automatically and the result remains in the bottom player;
- Spanish is now the default synthesis language;
- the language selector is always visible instead of being hidden behind an override toggle;
- the hardware chip now shows the GPU and what Automatic mode will actually use (`Auto→CPU` or `Auto→CUDA`);
- right-side Settings are larger and easier to read;
- the Generate button uses the app accent instead of becoming a large white button in dark mode;
- added quick profiles:
  - Fiel
  - Natural
  - Spot
- added estimated speech duration next to the character count; 9–11 seconds is highlighted for 10-second spots;
- settings are persisted in localStorage between sessions;
- `Ctrl+Enter` / `Cmd+Enter` generates the voice;
- Settings and voice UI labels are now mostly Spanish;
- Settings panel returns to the top when opened.

The generation orb is now a state indicator, not a persistent content element.


---

# V0.5 — Reference Lab

See `RESEARCH.md` for the research basis and `DESIGN.md` for the UI audit.

Main changes:

- reference audio analysis and quality score;
- automatic conservative 24 kHz mono preparation;
- exact-transcript / ICL workflow emphasized;
- fake Similarity slider removed;
- official reusable Qwen clone prompt cached in memory;
- long-text sentence chunking;
- dynamic max_new_tokens;
- Fiel profile uses deterministic generation;
- Spanish-only primary workflow;
- large-screen editor max-width;
- settings rail scales up to a controlled maximum.


---

# V0.6 — Voice Studio AI

Novedades:
- selector de modelos;
- Qwen3-TTS 0.6B recomendado;
- Qwen3-TTS 1.7B compatible como opción pesada;
- búsqueda real de modelos Text-to-Speech en Hugging Face;
- avatar de autor/organización cuando el Hub lo proporciona;
- modelos de otra arquitectura marcados como `Adaptador`, sin prometer compatibilidad falsa;
- reproductor propio con waveform, seek, tiempo, volumen y descarga;
- transición Generar → Procesando → Player;
- material/translucencia y feedback de interacción inspirados en Apple Design;
- soporte de reduced motion / reduced transparency / high contrast;
- compilación final con `npm run build:windows`.

## Exportar a Windows

Primero instala los prerrequisitos de Tauri:
- Rust;
- Microsoft C++ Build Tools con `Desktop development with C++`;
- WebView2 si tu Windows no lo trae.

Después:

```powershell
npm run build:windows
```

El instalador final aparecerá dentro de:

```text
src-tauri\target\release\bundle\nsis\
```

y tendrá formato `*-setup.exe`.

El instalador contiene el motor local, pero no los pesos de Qwen.
Los modelos se descargan en la primera ejecución y quedan guardados en la caché local.


---

# V0.6.1 — Navigation fix

Fixed a side-sheet navigation bug where Voice and Model selectors could remain
logically active at the same time.

Changes:
- only one side sheet can exist in the active state;
- opening Models always closes Voices first, and vice versa;
- closed sheets are `inert`, `aria-hidden`, `visibility:hidden` and
  `pointer-events:none`;
- Back always returns to Settings and restores focus to the originating control;
- Escape closes the active sheet;
- changing Settings / History closes any open selector;
- preview audio stops when leaving a selector;
- background settings cannot receive pointer events while a selector is open.

This removes the possibility of an invisible sheet intercepting clicks.


---

# V0.6.2 — Single selector sheet

The Voice and Model selectors no longer use two overlapping side sheets.

There is now one physical selector panel (`selectorSheet`) with two mutually
exclusive internal views (`voiceSheetView`, `modelSheetView`). The inactive
view uses the native `hidden` attribute and cannot cover or intercept the
active view.

Tested navigation target:
Voice → Back → Model → Back → Voice → Back.


---

# V0.6.6 — GitHub Actions + one-click installer

The project now includes:

- `.github/workflows/validate.yml`
- `.github/workflows/release-windows.yml`
- `scripts/prepare-release-engine.ps1`
- `scripts/check-release-version.ps1`
- `GITHUB_RELEASES.md`

A Windows Release build packages the Python/Qwen/PyTorch runtime into the
application engine. End users do not install Python, Node, Rust or CUDA Toolkit.

Create a release by pushing a tag matching the application version:

```powershell
git tag v0.6.6
git push origin v0.6.6
```

GitHub Actions builds the NSIS setup executable and publishes it automatically.


---

# V0.6.7 — Music mixing fix

La música ya no se mezcla en el navegador/WebView.

Ahora `/api/generate` recibe:
- `music_id`;
- `music_volume`.

El motor Python:
1. carga y remuestrea la música al sample rate de la voz;
2. conserva estéreo cuando existe;
3. repite el fondo si es más corto que la locución;
4. recorta si es más largo;
5. normaliza el nivel del fondo;
6. aplica el volumen elegido;
7. aplica fade-in/fade-out;
8. centra la voz;
9. protege contra clipping;
10. guarda el archivo final real en `outputs`.

Ventajas:
- el reproductor usa el archivo definitivo;
- el Historial conserva exactamente la versión con música;
- la descarga no depende de un `blob:` temporal;
- WAV/FLAC funcionan por la misma ruta;
- la selección de música persiste entre refrescos y reinicios;
- una música recién importada queda seleccionada automáticamente.

Prueba local del mezclador:

```powershell
.\.venv\Scripts\python.exe .\tests\test_audio_mix.py
```


---

# V0.6.8 — Music decoder fix

Las músicas importadas se validan y convierten a WAV PCM16 44.1 kHz. Usa `Reparar biblioteca de música` una vez después de actualizar desde v0.6.7.


---

# V0.6.9 — GitHub Release workflow fix

GitHub Actions now clearly separates validation from publishing:

- `01 · Validar código (no publica Release)`
- `02 · Crear instalador Windows y publicar Release`

The release workflow can run from a `v*` tag or manually from Actions.
It derives the release tag from `package.json`, publishes the NSIS setup
through `tauri-apps/tauri-action@v1`, uploads a workflow artifact, and finally
verifies the GitHub Release with `gh release view`.

Official GitHub actions were updated to Node 24-compatible majors:
checkout v6, setup-node v6 and setup-python v6.


---

# V0.6.10 — Tauri Rust lifetime fix

Fixed the Windows release compilation error:

`error[E0597]: state does not live long enough`

Engine shutdown now extracts the `Child` from the mutex before killing/waiting
for it, so no `MutexGuard` outlives the local Tauri `State`.

GitHub Actions now runs `cargo check` before the expensive Python/PyTorch
packaging step.


---

# V0.6.11 — stale-tag guard

The repeated E0597 log proved GitHub was compiling an older Rust source.
Both workflows now inspect the exact checked-out commit and abort if the
old `state.0.lock()` window-event implementation is present.

Before creating a release tag run:

```powershell
npm run release:pretag
```

Create a fresh tag only after the fixed commit is already pushed.


---

# V0.6.12 - GitHub Actions YAML fix

Both workflows were rewritten and syntax-validated as YAML.

Expected entries in GitHub Actions after pushing to the default branch:

- `01 - Validar codigo`
- `02 - Crear instalador Windows y publicar Release`

The second workflow supports both manual `workflow_dispatch` and automatic
execution on `v*` tags.


---

# V0.6.13 — Lean Windows packaging

The PyInstaller build no longer uses `--collect-all` for Torch, Transformers,
Librosa, SoundFile or Torchaudio.

A temporary 12Hz-only Qwen runtime is prepared for packaging, unused heavy
optional modules are excluded, and the frozen engine must pass:

```powershell
engine-dist\qwen-engine\qwen-engine.exe --self-test-packaging
```

before Tauri/NSIS runs.

Build locally:

```powershell
npm run build:windows
```

The build prints the engine size, the largest bundled files and the final
`setup.exe` size.


---

# v0.7.0 — Engine Manager

Voice Studio AI now ships as a lightweight Windows application. Python,
PyTorch and qwen-tts are installed as a private downloadable runtime during
the visual first-run setup.

See `ENGINE_MANAGER.md`.


---

# v0.7.1 — Rust ownership fix

Fixes `E0505` in the Engine Manager catalog by making
`recommended_flavor` an owned `String` before moving the manifest.


---

# v0.7.3 — Installer and release recovery

- publishes a rebuilt `engine-v1.0.1` with the Qwen3-TTS 12 Hz tokenizer;
- rejects a packaged engine before publication when its exact Qwen imports fail;
- keeps large engine downloads resumable without a short total timeout;
- validates manifest paths, sizes, hashes and partial download ranges;
- records the last installation failure in `engine/last-install-error.log`;
- uses `npm ci` and `cargo --locked` in validation/release workflows;
- supports reproducible engine releases from `engine-v*` tags;
- moves the application to `v0.7.3` because the stale `v0.7.2` tag points to
  an older `0.7.1` manifest.


---

# v0.7.4 — Silent Windows launch and model installer

- builds the release executable with the Windows GUI subsystem so no terminal
  opens beside the application;
- detects compatible models already present in the private Hugging Face cache;
- installs model snapshots explicitly in the background with retryable state;
- shows `Sin instalar`, `Instalando`, `Instalado` and recovery states in the UI;
- requires engine `1.0.2` and guides older installations through the visual
  engine updater before opening the workspace.
