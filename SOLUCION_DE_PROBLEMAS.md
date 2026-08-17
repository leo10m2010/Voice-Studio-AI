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
