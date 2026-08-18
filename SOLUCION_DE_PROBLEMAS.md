# Solución de problemas

Guía para cuando Voice Studio AI no genera audio, no deja agregar voces, o
simplemente "no hace nada" en una PC distinta a la de desarrollo.

## Lo primero: copiar el diagnóstico

La app trae un botón que recopila todo lo necesario en un solo texto:

- **Ajustes → Motor local → Gestionar → Copiar diagnóstico**
- o, si el motor no arrancó, el botón **Copiar diagnóstico** del aviso rojo
  que aparece sobre el editor.

Ese texto incluye la versión de la app, el motor instalado, el hardware
detectado, el estado de los modelos y **las últimas líneas del registro real
del motor**. Con eso se identifica la causa sin adivinar.

El registro también está en disco:

```text
%LOCALAPPDATA%\com.voicestudioai.desktop\engine\engine.log
```

y el del arranque anterior en `engine.prev.log`.

## Síntomas y causas

### "Le doy Generar y no pasa nada"

Ya no debería ocurrir: el botón Generar siempre responde y dice qué falta
(guion vacío, voz sin seleccionar, modelo sin instalar, motor caído) y abre
la pantalla correspondiente.

Si aún así no genera, el mensaje que muestre indica el paso siguiente.

### "No puedo agregar voces nuevas" / `No module named 'sklearn'`

Causa: un motor empaquetado sin `scikit-learn`.

`librosa` carga sus submódulos de forma diferida, así que un motor sin
`scikit-learn` **importa bien y arranca bien**, y solo falla en la primera
llamada real: preparar una referencia de voz o generar audio. El motor
`engine-v1.0.2` publicado tenía este defecto.

Solución: actualizar el motor a **1.0.3** o posterior. La app lo pide sola al
abrir. También se puede forzar desde
**Ajustes → Motor local → Gestionar → Reparar / actualizar**.

Esto no se puede repetir: `--self-test-packaging` ahora ejecuta el pipeline de
audio completo (`librosa.load`, `effects.trim`, `time_stretch`, `pitch_shift`,
`resample`, `decode_audio_file`) en vez de solo importar librosa, y Rust corre
ese self-test sobre el motor descargado **antes** de activarlo. Un motor con
este defecto se rechaza durante la instalación.

### "Error del motor" al generar, y en el registro `device-side assert`

Síntoma: la generación falla al instante y el aviso muestra un texto largo
sobre `CUDA error: device-side assert triggered`, `CUDA_LAUNCH_BLOCKING=1` y
`TORCH_USE_CUDA_DSA`. Reintentar da exactamente el mismo error. En el registro
aparece la línea que importa:

```text
TensorCompare.cu:109: Assertion `input[0] != 0` failed.
```

Causa: el motor cargaba el modelo en **fp16**. Los pesos tienen un rango que
fp16 no cubre —se corta en 65504—, así que las activaciones desbordaban a
infinito, el softmax devolvía NaN y `torch.multinomial` abortaba; ese `assert`
es su comprobación de "probability tensor contains either inf, nan or element
< 0".

No dependía de la tarjeta: fallaba igual en una RTX 4070 recién instalada y en
el equipo antiguo. **Ninguna locución en GPU llegó nunca a completarse.**

Solución: actualizar el motor a **1.0.4** o posterior, que carga en **fp32**.
La app pide la actualización sola al abrir.

Se probaron los tres dtypes en una RTX 4070 con muestreo determinista, misma
frase y misma voz:

| dtype | resultado | audio | tiempo |
|---|---|---|---|
| fp16 | aborta el proceso | — | — |
| bf16 | degrada: no cierra la locución | 13.92 s, rms 0.032 | 23.8 s |
| **fp32** | **correcto** | **4.40 s, rms 0.070** | **6.5 s** |
| CPU (fp32) | correcto, de referencia | 4.24 s, rms 0.075 | 16.0 s |

bf16 no revienta pero sobra: con 8 bits de mantisa el modelo deja de cerrar
bien la locución y devuelve el triple de audio. fp32 en GPU coincide con CPU y
sigue siendo 2.5x más rápido, así que es lo que se usa.

El coste es memoria: fp32 ocupa el doble que fp16 y el 0.6B llega a **5.29 GB
asignados / 5.73 GB reservados** con un guion largo. Por eso la VRAM exigida
para elegir GPU subió de 2.5 GB a **6 GB** (y de 5 a 11 GB en el modelo 1.7B).
Una tarjeta con menos irá a CPU: más lenta, pero correcta, que es mejor que el
error de antes.

`QWEN_ENGINE_CUDA_DTYPE=bfloat16` fuerza bf16 para comparar. fp16 se ignora
aunque se pida: es el dtype que abortaba el proceso.

Dos cosas más cambiaron a raíz de esto:

- Un fallo de kernel corrompe el contexto CUDA del **proceso entero**: a partir
  de ahí toda operación en GPU falla, por eso reintentar no servía de nada. Ahora
  el motor lo detecta, descarta la GPU para lo que queda de sesión y **termina
  el trabajo en CPU** en vez de devolver error. El diagnóstico dice
  `GPU descartada en esta sesión: …` y la línea de hardware muestra
  "GPU fuera de servicio". Reiniciar la app la devuelve al servicio.
- El aviso ya no vuelca la traza de PyTorch. El texto completo queda en el
  registro del motor, que es donde sirve.

### "Agregué una voz y no la clona: repite el mismo audio"

Síntoma: se genera un guion corto y sale una locución larguísima que no dice lo
escrito, sino algo parecido a la referencia.

Causa: la transcripción pegada no corresponde al audio que el motor usa de
verdad. Una referencia larga **se recorta a 18 s**, pero la transcripción se
guardaba entera. En modo ICL el modelo condiciona sobre "este audio dice este
texto"; si no cuadra, deja de emitir el token de fin y agota el máximo de
tokens.

Medido en una RTX 4070, guion de 48 caracteres que debería durar 3,5 s, con una
referencia de 13,7 s:

| Transcripción | Velocidad implícita | Resultado |
|---|---|---|
| Exacta (202 car.) | 14,7 car/s | 3,92 s — correcto |
| Ninguna (X-vector) | — | 3,68 s — correcto |
| De más (326 car.) | 23,8 car/s | 10,48 s — mal |
| De menos (68 car.) | 5,0 car/s | 30,64 s — inservible |
| Cuádruple (1307 car.) | 95,4 car/s | 30,64 s — inservible |

Una transcripción equivocada es mucho peor que ninguna. Desde el motor
**1.0.5**, si el texto no encaja con la duración de la referencia usada, se
descarta y se clona solo con la huella de voz; la app dice por qué al terminar.

Para aprovechar ICL, que sí mejora la fidelidad:

- usa una referencia de **18 s o menos** (lo ideal, 10–15 s);
- pega la transcripción **de ese tramo**, no la del audio completo.

La puntuación de la voz ahora refleja esto: antes se sumaban 35 puntos por
"tener transcripción" sin comprobar nada, y una voz inservible salía
"Excelente 96". Ahora sale "Mejorable" con la nota que explica qué corregir.

Efecto secundario del mismo fallo: la caché de referencias no distinguía ICL de
X-vector, así que generar con transcripción y luego sin ella devolvía el prompt
equivocado. Ya no.

### El motor no responde al abrir la app

Aparece el aviso "El motor local no se pudo iniciar" con Reintentar y
Copiar diagnóstico. Causas frecuentes, en orden:

1. **Puerto 8765 ocupado** por otro programa. El registro lo dice
   explícitamente (`ENGINE_START_FAILED: El puerto 8765 ya está ocupado...`).
   Se puede mover con la variable de entorno `QWEN_ENGINE_PORT`.
2. **Antivirus corporativo** bloqueando `qwen-engine.exe`. Se ve como un
   proceso que arranca y muere sin escribir nada en el registro.
3. **Motor a medio instalar**. Reparar / actualizar lo resuelve.

### El modelo no se instala

La descarga viene de Hugging Face. En una red corporativa suele estar
bloqueada. El diagnóstico muestra `Modelo <id>: error` con el detalle.

## "El motor quedó bloqueado"

`generate_voice_clone()` de Qwen3-TTS puede colgarse indefinidamente con
ciertas entradas ([issue #318](https://github.com/QwenLM/Qwen3-TTS/issues)).
Cuando pasa, retiene el cerrojo de generación: el motor sigue respondiendo a
las comprobaciones de salud —parece vivo— pero ninguna locución posterior se
completa nunca.

Esa llamada no se puede abortar desde fuera. Lo que sí hace la app:

- **Evitarlo**: retira del guion los caracteres que el modelo no puede
  pronunciar (emoji, escrituras no latinas), que son los que disparan el
  cuelgue. Si se quitó algo, te lo dice tras generar.
- **Detectarlo**: si una generación pasa varias veces del tiempo previsto, se
  marca como bloqueada y la siguiente petición falla al instante con el motivo
  en vez de esperar para siempre.
- **Recuperarlo**: el botón **Reintentar** del aviso reemplaza el proceso del
  motor. Es la única cura real; cerrar y abrir la app hace lo mismo.

## Avisos de versión

Al abrir, la app consulta si hay una Release más reciente y muestra una franja
con enlace. **No descarga ni instala nada**: la actualización se hace bajando
el instalador. Si estás sin conexión o detrás de un proxy, la consulta falla en
silencio y no molesta. Ocultar el aviso lo silencia solo para esa versión.

El motor local es distinto: ese sí se actualiza solo, y la app consulta siempre
`engine-latest`, así que una app antigua también recibe el motor corregido.

## Qué NO es problema

- Que las voces aparezcan al principio como "Analizando…": el motor sirve la
  biblioteca de inmediato y analiza las referencias en segundo plano, a
  propósito. La puntuación de calidad aparece sola en unos segundos.
- Que la app tarde algo más la primera vez: la música incluida se convierte a
  WAV una sola vez, ya sin bloquear el arranque.

## Funciones que ahorran tiempo

Una locución cuesta minutos en CPU. Estas existen para no desperdiciarlos:

- **Vista previa de lectura.** Al escribir aparece *"ASÍ SE LEERÁ"* con el
  texto ya normalizado, si difiere de lo escrito. Sirve para detectar un
  precio o una hora mal interpretados **antes** de gastar la generación.
- **Cola.** El botón `+` junto a Generar encola el guion y limpia el editor.
  Se procesan uno tras otro sin vigilar la pantalla. Cada trabajo lleva su
  propia copia de los ajustes, así que seguir editando no altera lo encolado.
- **Reutilizar del historial.** El icono de recarga en cada entrada devuelve
  guion, voz y ajustes de esa locución para hacer una variación.
- **Tramo de la referencia.** Con audios de más de 19 s aparece un control
  para elegir desde qué segundo se toman los 18 s que se usan; el recorte
  automático se queda con el principio, que no siempre es el mejor tramo.
- **Formato y frecuencia.** MP3 para enviar (un spot de 10 s pesa ~40 KB en
  vez de ~470 KB) y 44.1 kHz cuando la emisora lo pide.
