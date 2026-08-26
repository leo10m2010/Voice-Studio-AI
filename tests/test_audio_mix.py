from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from audio_mix import (
    _INTRO_SECONDS,
    _OUTRO_SECONDS,
    mix_voice_with_music,
)


class AudioMixTests(unittest.TestCase):
    def test_resamples_loops_keeps_the_whole_voice_and_prevents_clipping(self):
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

        intro = int(voice_sr * _INTRO_SECONDS)
        outro = int(voice_sr * _OUTRO_SECONDS)
        self.assertEqual(mixed.shape, (intro + voice.shape[0] + outro, 2))
        self.assertLessEqual(float(np.max(np.abs(mixed))), 0.986)
        self.assertGreater(float(np.mean(np.abs(mixed[:, 0] - mixed[:, 1]))), 0.0001)

        # Music must materially change the dry voice.
        dry = np.stack([voice, voice], axis=1)
        self.assertGreater(
            float(np.mean(np.abs(mixed[intro:intro + voice.shape[0]] - dry))), 0.001
        )

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

        # Sin música audible no se añade ni entrada ni cola: serían silencio.
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

        # El deslizador fija la cama bajo la voz, así que se mide ahí y no en
        # la entrada/cola del spot, que van por encima a propósito.
        cama = mezclado[-voz.shape[0] :] if len(mezclado) == len(voz) else mezclado[
            int(sr * _INTRO_SECONDS) : int(sr * _INTRO_SECONDS) + voz.shape[0]
        ]
        mono = cama.mean(axis=1)
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


class EstructuraDeSpotTest(unittest.TestCase):
    """
    La música plana de principio a fin sonaba a "pista de fondo", no a spot.
    Ahora entra sola unos segundos, se agacha bajo la voz y vuelve a subir al
    final para cerrar con un fundido.
    """

    SR = 24000

    def _mezclar(self, segundos_de_voz=4.0, volumen=0.30):
        t = np.arange(int(self.SR * segundos_de_voz)) / self.SR
        voz = (0.20 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)

        tm = np.arange(self.SR * 2) / self.SR
        musica = (0.4 * np.sin(2 * np.pi * 900 * tm)).astype(np.float32)

        with tempfile.TemporaryDirectory() as td:
            ruta = Path(td) / "music.wav"
            sf.write(ruta, musica, self.SR)
            mezclado = mix_voice_with_music(
                voice_wav=voz,
                sample_rate=self.SR,
                music_path=ruta,
                music_volume=volumen,
            )
        return voz, mezclado

    @staticmethod
    def _nivel(bloque):
        return float(np.sqrt(np.mean(np.square(bloque.mean(axis=1)))))

    def test_la_musica_entra_sola_antes_de_la_voz(self):
        voz, mezclado = self._mezclar()
        intro = int(self.SR * _INTRO_SECONDS)

        # Hay sonido antes de que empiece la voz…
        self.assertGreater(self._nivel(mezclado[:intro]), 0.01)
        # …y la voz sigue entera, desplazada por la entrada.
        recorte = mezclado[intro:intro + voz.shape[0]].mean(axis=1)
        self.assertGreater(float(np.corrcoef(recorte, voz)[0, 1]), 0.9)

    def test_la_musica_se_baja_cuando_habla_la_voz(self):
        _, mezclado = self._mezclar()
        intro = int(self.SR * _INTRO_SECONDS)

        # Medio segundo de música expuesta contra medio segundo ya bajo la voz.
        expuesta = self._musica_en(mezclado[int(self.SR * 0.8):int(self.SR * 1.3)])
        cama = self._musica_en(
            mezclado[intro + int(self.SR * 0.5):intro + int(self.SR * 1.0)]
        )
        self.assertGreater(expuesta, cama * 1.8)

    def test_queda_musica_al_final_y_cierra_con_fundido(self):
        voz, mezclado = self._mezclar()
        intro = int(self.SR * _INTRO_SECONDS)
        fin_de_voz = intro + voz.shape[0]

        cola = mezclado[fin_de_voz:]
        self.assertGreaterEqual(len(cola), int(self.SR * (_OUTRO_SECONDS - 0.05)))

        # Sube tras la voz…
        self.assertGreater(self._nivel(cola[int(self.SR * 0.8):int(self.SR * 1.3)]), 0.01)
        # …y termina en silencio, no cortado de golpe.
        self.assertLess(float(np.max(np.abs(cola[-int(self.SR * 0.05):]))), 0.02)

    def test_una_voz_corta_tambien_recibe_entrada_y_cola(self):
        voz, mezclado = self._mezclar(segundos_de_voz=0.6)
        esperado = int(self.SR * _INTRO_SECONDS) + voz.shape[0] + int(
            self.SR * _OUTRO_SECONDS
        )
        self.assertEqual(mezclado.shape[0], esperado)
        self.assertLessEqual(float(np.max(np.abs(mezclado))), 0.986)

    @staticmethod
    def _musica_en(bloque):
        """Energía a 900 Hz: aísla la música de la voz, que está en 200 Hz."""
        mono = bloque.mean(axis=1)
        espectro = np.abs(np.fft.rfft(mono * np.hanning(len(mono))))
        frecuencias = np.fft.rfftfreq(len(mono), 1 / EstructuraDeSpotTest.SR)
        banda = (frecuencias > 850) & (frecuencias < 950)
        return float(np.max(espectro[banda]))


if __name__ == "__main__":
    unittest.main()
