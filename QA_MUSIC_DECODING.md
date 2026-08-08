# QA — Música v0.6.8

Error corregido:

`mpg123: Giving up searching valid MPEG header after 65536 bytes of junk`

La extensión ya no se considera prueba de que el contenido sea MP3.

## Nueva importación

- archivo temporal;
- inspección de contenido;
- decode real;
- resample a 44.1 kHz;
- WAV PCM16 interno;
- lectura de verificación.

El mixer ya trabaja sobre el WAV interno.

## Biblioteca antigua

Botón: `Reparar biblioteca de música`

- WAV válidos: permanecen;
- MP3/FLAC/OGG válidos: se convierten a WAV;
- archivos corruptos/HTML/etc.: se mueven a
  `%LOCALAPPDATA%\QwenVoiceStudio\sounds_invalid`.

## Tests

- WAV con extensión `.mp3`: PASS.
- HTML con extensión `.mp3`: rechazado: PASS.
- estéreo WAV: PASS.
- mixer loop/resample/clipping: PASS.
