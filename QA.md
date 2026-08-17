# QA — historial de defectos corregidos

Notas consolidadas de los ocho archivos `QA_*.md` que antes vivían sueltos en
la raíz. Se conservan por el porqué de cada decisión; para diagnosticar un
problema actual usa `SOLUCION_DE_PROBLEMAS.md`.

---

## QA — Lean Windows Packaging v0.6.13

### Problema observado

El build anterior generó:

- `engine-dist\qwen-engine`: 4.29 GB
- PyInstaller analizaba cientos de submódulos de Transformers/Torch
- NSIS terminó fallando al crear el `setup.exe`

### Causa principal

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

### Nuevo empaquetado

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

### qwen_tts 12Hz-only

Durante el build se crea temporalmente:

`engine\_vendor_slim\qwen_tts`

a partir de la instalación oficial de qwen-tts.

No se modifica permanentemente el paquete de `.venv`.

Se elimina del vendor empaquetado:
- `qwen_tts/cli`
- `qwen_tts/core/tokenizer_25hz`

y el wrapper de tokenizer registra únicamente Tokenizer V2 / 12Hz.

### Nota: `scikit-learn` NO se puede excluir (y el self-test no lo detectaba)

`librosa` importa `sklearn` (`decompose`/`segment`) en su `__init__.py`, así
que es una dependencia dura, no opcional. Excluirla con
`--exclude-module sklearn` rompía `import librosa` en el motor empaquetado y
causaba `No se pudo preparar '<archivo>'. No module named 'sklearn'` al subir
cualquier voz nueva. Se eliminó ese exclude-module.

**Reincidencia (motor 1.0.2).** El exclude volvió a colarse porque el `.spec`
generado en `engine\` sobrevivía entre builds con el exclude viejo, y porque
el self-test comprobaba `import librosa` — que **pasa** sin scikit-learn, ya
que librosa engancha sus submódulos con `lazy_loader`. El motor publicado
arrancaba bien y fallaba solo en la primera llamada real.

Correcciones aplicadas:

- `build-engine-windows.ps1` borra cualquier `engine\*.spec` antes de compilar;
- `scikit-learn` se declara en `engine/requirements.txt` en vez de depender de
  que librosa lo arrastre;
- se añaden `--collect-submodules sklearn.{decomposition,cluster,
  feature_extraction,neighbors}` y `--hidden-import sklearn`;
- `audio_pipeline_probe()` ejecuta el pipeline real (`librosa.load`,
  `effects.trim`, `time_stretch`, `pitch_shift`, `resample`,
  `decode_audio_file`) y el self-test lo llama;
- `tests/test_packaging_probe.py` fija la regresión: comprueba que
  `import librosa` pasa sin sklearn y que la sonda falla.

### Self-test obligatorio

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

### Build local

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

---

## QA — Música de fondo

### Problemas corregidos

#### 1. Mezcla dependiente del WebView
Antes:
- fetch del WAV/FLAC generado;
- fetch de la música;
- Web Audio API;
- blob temporal.

Problema:
- compatibilidad de codecs dependiente del navegador/WebView;
- resultado no persistente.

Ahora:
- mezcla 100% en el engine Python;
- resultado persistente en `outputs`.

#### 2. Historial incorrecto
Antes:
- historial apuntaba a la voz seca;
- el blob con música solo existía en la sesión actual.

Ahora:
- historial apunta al archivo final ya mezclado.

#### 3. Selector se reiniciaba
Antes:
- `renderSounds()` reconstruía el `<select>`;
- no persistía el `soundId`.

Ahora:
- `selectedSoundId` vive en estado;
- se guarda en localStorage;
- se restaura después de refrescar;
- un audio recién importado queda seleccionado.

### Comportamiento del mixer

- entrada de voz: mono o multicanal defensivo;
- salida: estéreo;
- sample rate final: sample rate de Qwen;
- música corta: loop;
- música larga: trim;
- duración final: exactamente la duración de la locución;
- fade-in: ~220 ms;
- fade-out: ~450 ms;
- music normalization: moderada;
- volumen: 0–60 % internamente;
- peak protection: <= ~0.985.

### Prueba automática

`tests/test_audio_mix.py`

Casos:
1. voz 24 kHz / 2.4 s + música estéreo 44.1 kHz / 0.65 s:
   - resample;
   - loop;
   - duración exacta;
   - estéreo;
   - sin clipping.
2. volumen de música 0:
   - salida válida;
   - sin NaN/Inf.

---

## QA — Música v0.6.8

Error corregido:

`mpg123: Giving up searching valid MPEG header after 65536 bytes of junk`

La extensión ya no se considera prueba de que el contenido sea MP3.

### Nueva importación

- archivo temporal;
- inspección de contenido;
- decode real;
- resample a 44.1 kHz;
- WAV PCM16 interno;
- lectura de verificación.

El mixer ya trabaja sobre el WAV interno.

### Biblioteca antigua

Botón: `Reparar biblioteca de música`

- WAV válidos: permanecen;
- MP3/FLAC/OGG válidos: se convierten a WAV;
- archivos corruptos/HTML/etc.: se mueven a
  `%LOCALAPPDATA%\QwenVoiceStudio\sounds_invalid`.

### Tests

- WAV con extensión `.mp3`: PASS.
- HTML con extensión `.mp3`: rechazado: PASS.
- estéreo WAV: PASS.
- mixer loop/resample/clipping: PASS.

---

## Voice Studio AI v0.6.5 — QA de navegación

Se reemplazaron los dos paneles superpuestos de Voice / Model por un único
`selectorSheet` con dos vistas internas mutuamente exclusivas:

- `voiceSheetView`
- `modelSheetView`

### Prueba ejecutada en Chromium

Datos simulados:
- 2 voces
- Qwen3-TTS 0.6B Base
- Qwen3-TTS 1.7B Base

Secuencia validada:

1. Estado inicial: selector cerrado.
2. Pulsar Voz:
   - selector visible;
   - título `Seleccionar voz`;
   - lista de voces visible;
   - vista de modelos oculta.
3. Pulsar Atrás:
   - selector cerrado;
   - regreso a Ajustes.
4. Pulsar Modelo:
   - selector visible;
   - título `Seleccionar modelo`;
   - Qwen 0.6B y 1.7B visibles;
   - vista de voces oculta.
5. Pulsar Atrás:
   - selector cerrado.
6. Abrir Voz y seleccionar `Animador`:
   - la selección se aplica;
   - el selector se cierra.
7. Abrir Modelo y seleccionar `Qwen3-TTS 1.7B Base`:
   - la selección se aplica;
   - el selector se cierra.
8. Abrir selector y pulsar Escape:
   - vuelve a Ajustes.

Resultado: PASS.

También se verificaron visualmente ambos estados del selector mediante captura
de Chromium.

---

## QA — Rust/Tauri build v0.6.10

### Error corregido

```text
error[E0597]: `state` does not live long enough
src/lib.rs:121
```

La causa era un `MutexGuard` temporal creado dentro de `on_window_event`.
Rust podía mantener vivo el temporal del `Result<MutexGuard<...>>` hasta el
final del bloque, mientras el `State` local ya estaba siendo destruido.

### Cambio

Antes:

```rust
let state = window.state::<EngineProcess>();
if let Ok(mut guard) = state.0.lock() {
    if let Some(child) = guard.as_mut() {
        let _ = child.kill();
        let _ = child.wait();
    }
    *guard = None;
}
```

Ahora:

```rust
fn take_engine_child(state: &EngineProcess) -> Result<Option<Child>, String> {
    let mut guard = state.0.lock().map_err(...)?;
    Ok(guard.take())
}

fn terminate_engine(state: &EngineProcess) -> Result<(), String> {
    if let Some(mut child) = take_engine_child(state)? {
        let _ = child.kill();
        let _ = child.wait();
    }
    Ok(())
}
```

Y el evento llama:

```rust
let state = window.state::<EngineProcess>();
terminate_engine(state.inner())
```

Ventajas:
- el `MutexGuard` se destruye dentro de `take_engine_child`;
- el lock ya está liberado antes de `kill()` / `wait()`;
- no existe el temporal que provocaba E0597;
- `stop_engine` y el cierre de ventana usan la misma ruta.

### GitHub Actions

Ahora ambos workflows ejecutan:

```powershell
cargo check --manifest-path .\src-tauri\Cargo.toml
```

El workflow de Release lo ejecuta **antes** de instalar/empaquetar PyTorch,
para detectar errores Rust rápidamente.

---

## QA Rust ownership fix v0.7.1

### Error

`E0505: cannot move out of manifest because it is borrowed`

`preferred` era un `&str`. En el fallback podía provenir de:

```rust
manifest.engines.first().map(|item| item.flavor.as_str())
```

Eso dejaba `manifest.engines` prestado. Después se intentaba mover `manifest`
completo a `EngineCatalog`, mientras el borrow seguía vivo para
`preferred.into()`.

### Fix

Ahora se crea un `String` propio antes de mover `manifest`:

```rust
let recommended_flavor = if hardware.recommended_flavor == "nvidia"
    && manifest.engines.iter().any(|item| item.flavor == "nvidia")
{
    "nvidia".to_string()
} else if manifest.engines.iter().any(|item| item.flavor == "cpu") {
    "cpu".to_string()
} else {
    manifest
        .engines
        .first()
        .map(|item| item.flavor.clone())
        .unwrap_or_else(|| "cpu".to_string())
};
```

Y después:

```rust
Ok(EngineCatalog {
    manifest,
    hardware,
    status,
    recommended_flavor,
})
```

No queda ningún borrow activo de `manifest` al moverlo.

Los parámetros `app` que solo se usan en builds `release` se marcaron como
`_app` para evitar warnings durante `cargo check` de debug.

---

## QA — stale tag / stale commit v0.6.11

El error reportado seguía mostrando este código:

```rust
let state = window.state::<EngineProcess>();
if let Ok(mut guard) = state.0.lock() {
```

Ese código **no existe** en la fuente corregida.

La fuente v0.6.11 contiene:

```rust
let state = window.state::<EngineProcess>();

if let Err(error) = terminate_engine(state.inner()) {
    eprintln!("No se pudo cerrar el motor local: {error}");
}
```

Por tanto, si GitHub muestra otra vez `if let Ok(mut guard)`, está compilando
un tag/commit anterior.

### Protección añadida

Ambos workflows ahora:

1. imprimen `git rev-parse HEAD`;
2. imprimen el último commit;
3. inspeccionan `src-tauri/src/lib.rs`;
4. buscan explícitamente el patrón viejo;
5. abortan inmediatamente si lo encuentran;
6. exigen `terminate_engine(state.inner())`;
7. luego ejecutan `cargo check`.

### Antes de taggear

Ejecuta:

```powershell
npm run release:pretag
```

Solo si pasa:

```powershell
git tag v0.6.11
git push origin v0.6.11
```

Nunca reutilices un tag antiguo para una nueva compilación.

---

## QA GitHub Actions v0.6.12

Problema de v0.6.11:
- bloques PowerShell con lineas sin sangria dentro de `run: |`;
- `Comprobar referencia de ejecucion` quedo fuera de `jobs.*.steps`;
- GitHub no podia registrar correctamente los workflows.

Sintoma:
- Actions mostraba `.github/workflows/validate.yml` en vez del nombre;
- no aparecia el workflow de Release.

v0.6.12:
- validate.yml reescrito;
- release-windows.yml reescrito;
- sin here-string PowerShell multilinea;
- todos los steps tienen 6 espacios de sangria;
- ambos archivos pasan parsing YAML local;
- Release conserva `workflow_dispatch` y trigger por tag `v*`;
- tauri-action publica NSIS en GitHub Release;
- el Release se verifica al final con `gh release view`.

---

## Defensas ante defectos conocidos de Qwen3-TTS

Contrastado contra los issues del repo oficial `QwenLM/Qwen3-TTS`.

| Issue | Qué reporta | Nuestra situación |
|---|---|---|
| #350 | Inferencia concurrente no soportada | Ya serializado con `generate_lock` |
| #333 | Logits NaN con flash attention | Usamos `attn_implementation="sdpa"` |
| #318 | `generate_voice_clone()` se cuelga con escritura mezclada | `sanitize_script()` retira lo no pronunciable; `stuck_seconds()` lo detecta; `restart_engine` lo recupera |
| #239 | La velocidad de habla se acelera pasados ~100 caracteres | `TTS_CHUNK_CHARS` bajado de 460 a 200 |
| #328 | Cadenas de tiempo y cifras mal pronunciadas | `text_normalize.normalize_spanish()` |
| #341 | ICL repite la cola del audio de referencia antes del texto | Sin arreglo limpio desde fuera; se mitiga con referencias recortadas de 8–25 s |

### Por qué el cuelgue era grave

Una llamada colgada retiene `generate_lock` para siempre. El motor seguía
respondiendo `/api/health` —parecía sano— pero ninguna generación posterior
volvía a completarse. No hay forma de abortar esa llamada desde Python, así
que la defensa es en tres capas: no llegar a ella, detectarla cuando ocurre,
y poder reemplazar el proceso sin cerrar la aplicación.

### Fuga de memoria corregida (hallazgo propio, no de los issues)

`prompt_cache` no tenía tope y solo se vaciaba al descargar el modelo. Cada
entrada retiene los tensores del prompt de una voz, así que en una biblioteca
grande la memoria crecía durante toda la sesión. Ahora es una `OrderedDict`
acotada por `PROMPT_CACHE_MAX` con desalojo del menos usado.
