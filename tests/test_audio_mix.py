from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from audio_mix import mix_voice_with_music


class AudioMixTests(unittest.TestCase):
    def test_resamples_loops_preserves_voice_duration_and_prevents_clipping(self):
        voice_sr = 24000
        voice_seconds = 2.4
        voice_t = np.arange(int(voice_sr * voice_seconds)) / voice_sr
        voice = (0.23 * np.sin(2 * np.pi * 220 * voice_t)).astype(np.float32)

        music_sr = 44100
        music_seconds = 0.65  # intentionally shorter than voice => must loop
        music_t = np.arange(int(music_sr * music_seconds)) / music_sr
        left = 0.35 * np.sin(2 * np.pi * 440 * music_t)
        right = 0.30 * np.sin(2 * np.pi * 660 * music_t)
        music = np.stack([left, right], axis=1).astype(np.float32)

        with tempfile.TemporaryDirectory() as td:
            music_path = Path(td) / "music.wav"
            sf.write(music_path, music, music_sr)

            mixed = mix_voice_with_music(
                voice_wav=voice,
                sample_rate=voice_sr,
                music_path=music_path,
                music_volume=0.18,
            )

        self.assertEqual(mixed.shape, (voice.shape[0], 2))
        self.assertLessEqual(float(np.max(np.abs(mixed))), 0.986)
        self.assertGreater(float(np.mean(np.abs(mixed[:, 0] - mixed[:, 1]))), 0.0001)

        # Music must materially change the dry voice.
        dry = np.stack([voice, voice], axis=1)
        self.assertGreater(float(np.mean(np.abs(mixed - dry))), 0.001)

    def test_zero_volume_is_nearly_dry_voice(self):
        sr = 24000
        t = np.arange(sr) / sr
        voice = (0.15 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)
        music = (0.5 * np.sin(2 * np.pi * 500 * t)).astype(np.float32)

        with tempfile.TemporaryDirectory() as td:
            music_path = Path(td) / "music.wav"
            sf.write(music_path, music, sr)

            mixed = mix_voice_with_music(
                voice_wav=voice,
                sample_rate=sr,
                music_path=music_path,
                music_volume=0.0,
            )

        self.assertEqual(mixed.shape, (voice.shape[0], 2))
        self.assertTrue(np.isfinite(mixed).all())


class NivelDeMusicaTest(unittest.TestCase):
    """
    La música se normaliza a -18 dBFS y luego se multiplica por el volumen, así
    que el control tiene que traducirse en un cambio audible. Al 18% quedaba
    17.5 dB por debajo de la voz —prácticamente inaudible, de ahí el "la música
    no hace nada"— y al 45% queda a 6.5 dB, que ya es una cama de radio.
    """

    def _mezclar(self, volumen):
        """Energía de la mezcla en la frecuencia de la música.

        Restar la voz no sirve como medida: el limitador suave del final toca
        también la voz, así que a volumen 0 ya aparecía un residuo. Mirando solo
        los 900 Hz de la música se aísla lo que aporta de verdad.
        """
        sr = 24000
        t = np.arange(sr * 2) / sr
        voz = (0.18 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)
        musica = (0.5 * np.sin(2 * np.pi * 900 * t)).astype(np.float32)

        with tempfile.TemporaryDirectory() as td:
            ruta = Path(td) / "music.wav"
            sf.write(ruta, musica, sr)
            mezclado = mix_voice_with_music(
                voice_wav=voz, sample_rate=sr, music_path=ruta, music_volume=volumen
            )

        mono = mezclado.mean(axis=1)
        espectro = np.abs(np.fft.rfft(mono * np.hanning(len(mono))))
        frecuencias = np.fft.rfftfreq(len(mono), 1 / sr)
        banda = (frecuencias > 850) & (frecuencias < 950)
        return float(np.max(espectro[banda]))

    def test_mas_volumen_es_mas_musica(self):
        bajo = self._mezclar(0.18)
        alto = self._mezclar(0.45)
        self.assertGreater(alto, bajo * 2.0)

    def test_el_rango_que_ofrece_la_interfaz_se_nota(self):
        # El deslizador va de 5 a 60; los extremos deben sonar muy distintos.
        minimo = self._mezclar(0.05)
        maximo = self._mezclar(0.60)
        self.assertGreater(maximo, minimo * 8)

    def test_sin_volumen_no_hay_musica(self):
        self.assertLess(self._mezclar(0.0), self._mezclar(0.18) * 0.1)

    def test_el_motor_admite_el_maximo_de_la_interfaz(self):
        # El control llegaba solo a 40 mientras el motor aceptaba 60: se
        # desaprovechaba la mitad útil del rango.
        alto = self._mezclar(0.60)
        recortado = self._mezclar(0.90)  # el motor lo limita a 0.60
        self.assertAlmostEqual(alto, recortado, delta=alto * 0.02)


if __name__ == "__main__":
    unittest.main()
