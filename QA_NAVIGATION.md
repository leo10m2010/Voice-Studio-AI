# Voice Studio AI v0.6.5 — QA de navegación

Se reemplazaron los dos paneles superpuestos de Voice / Model por un único
`selectorSheet` con dos vistas internas mutuamente exclusivas:

- `voiceSheetView`
- `modelSheetView`

## Prueba ejecutada en Chromium

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
