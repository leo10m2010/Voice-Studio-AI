# QA — Música de fondo

## Problemas corregidos

### 1. Mezcla dependiente del WebView
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

### 2. Historial incorrecto
Antes:
- historial apuntaba a la voz seca;
- el blob con música solo existía en la sesión actual.

Ahora:
- historial apunta al archivo final ya mezclado.

### 3. Selector se reiniciaba
Antes:
- `renderSounds()` reconstruía el `<select>`;
- no persistía el `soundId`.

Ahora:
- `selectedSoundId` vive en estado;
- se guarda en localStorage;
- se restaura después de refrescar;
- un audio recién importado queda seleccionado.

## Comportamiento del mixer

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

## Prueba automática

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
