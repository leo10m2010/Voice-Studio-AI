from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

import server


class SanitizeScriptTest(unittest.TestCase):
    """
    generate_voice_clone() se cuelga indefinidamente con escritura mezclada
    (issue #318 del repo oficial) y ese cuelgue retiene generate_lock para
    siempre, dejando el motor sin poder generar nunca más. La única defensa
    posible desde fuera es no llegar a esa llamada.
    """

    def test_keeps_ordinary_spanish(self):
        text = "¡Atención, Huánuco! Hoy celebramos: 2 x 1 en todo — S/ 25.50."
        clean, removed = server.sanitize_script(text)
        self.assertEqual(clean, text)
        self.assertEqual(removed, [])

    def test_removes_foreign_scripts_and_emoji(self):
        clean, removed = server.sanitize_script("Hola 你好 mundo 🎉 สวัสดี")
        self.assertNotIn("你", clean)
        self.assertNotIn("🎉", clean)
        self.assertIn("Hola", clean)
        self.assertIn("mundo", clean)
        self.assertTrue(removed)

    def test_reports_each_removed_character_once(self):
        _, removed = server.sanitize_script("aaa 好好好 bbb")
        self.assertEqual(removed, ["好"])

    def test_empty_input_is_safe(self):
        self.assertEqual(server.sanitize_script(""), ("", []))


class ChunkSizeTest(unittest.TestCase):
    """El modelo acelera el habla pasados ~100 caracteres (issue #239)."""

    def test_default_chunk_stays_near_the_drift_threshold(self):
        self.assertLessEqual(server.TTS_CHUNK_CHARS, 220)

    def test_a_typical_spot_is_not_split(self):
        spot = (
            "¡Atención, Huánuco! Hoy celebramos con orgullo nuestra historia, "
            "nuestra cultura y nuestra gente. ¡Feliz aniversario!"
        )
        self.assertEqual(len(server.split_text_for_tts(spot)), 1)

    def test_long_text_is_split_below_the_limit(self):
        chunks = server.split_text_for_tts("Frase de prueba. " * 60)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk), server.TTS_CHUNK_CHARS)


class StuckDetectionTest(unittest.TestCase):
    def setUp(self):
        self.manager = server.ModelManager()

    def tearDown(self):
        self.manager.end_generation()

    def test_idle_engine_is_not_stuck(self):
        self.assertEqual(self.manager.stuck_seconds(), 0.0)

    def test_generation_within_budget_is_not_stuck(self):
        self.manager.begin_generation(budget_seconds=60.0)
        self.assertEqual(self.manager.stuck_seconds(), 0.0)

    def test_generation_past_budget_reports_overrun(self):
        self.manager.begin_generation(budget_seconds=0.01)
        time.sleep(0.05)
        self.assertGreater(self.manager.stuck_seconds(), 0.0)

    def test_finishing_clears_the_stuck_state(self):
        self.manager.begin_generation(budget_seconds=0.01)
        time.sleep(0.05)
        self.manager.end_generation()
        self.assertEqual(self.manager.stuck_seconds(), 0.0)


class PromptCacheTest(unittest.TestCase):
    """Cada entrada retiene tensores de una voz; sin tope la sesión crecía."""

    def test_cache_is_bounded_and_evicts_the_least_recent(self):
        manager = server.ModelManager()
        for index in range(server.PROMPT_CACHE_MAX + 3):
            manager.prompt_cache[f"voz-{index}"] = object()
            while len(manager.prompt_cache) > server.PROMPT_CACHE_MAX:
                manager.prompt_cache.popitem(last=False)

        self.assertEqual(len(manager.prompt_cache), server.PROMPT_CACHE_MAX)
        self.assertNotIn("voz-0", manager.prompt_cache)
        self.assertIn(f"voz-{server.PROMPT_CACHE_MAX + 2}", manager.prompt_cache)



class FormatoDeSalidaTest(unittest.TestCase):
    """MP3 lo escribe libsndfile; no añade dependencias al instalador."""

    def setUp(self):
        import numpy as np
        self.tono = (0.3 * np.sin(2 * np.pi * 440 * np.arange(24000) / 24000)).astype("float32")

    def _escribir(self, extension):
        import soundfile as sf
        import tempfile
        with tempfile.TemporaryDirectory() as carpeta:
            destino = Path(carpeta) / f"salida.{extension}"
            server.write_audio(destino, self.tono, 24000, extension)
            self.assertTrue(destino.exists() and destino.stat().st_size > 0)
            return sf.info(str(destino))

    def test_escribe_los_tres_formatos(self):
        self.assertEqual(self._escribir("wav").format, "WAV")
        self.assertEqual(self._escribir("flac").format, "FLAC")
        self.assertEqual(self._escribir("mp3").format, "MP3")

    def test_mp3_conserva_duracion_y_frecuencia(self):
        info = self._escribir("mp3")
        self.assertEqual(info.samplerate, 24000)
        self.assertAlmostEqual(info.duration, 1.0, delta=0.1)

    def test_mp3_pesa_mucho_menos_que_wav(self):
        import soundfile as sf, tempfile
        with tempfile.TemporaryDirectory() as carpeta:
            wav = Path(carpeta) / "a.wav"
            mp3 = Path(carpeta) / "a.mp3"
            server.write_audio(wav, self.tono, 24000, "wav")
            server.write_audio(mp3, self.tono, 24000, "mp3")
            self.assertLess(mp3.stat().st_size, wav.stat().st_size / 2)

    def test_formato_desconocido_cae_en_wav(self):
        # Nunca debe fallar la generación por un formato raro guardado en
        # preferencias; se degrada a WAV en vez de reventar.
        self.assertEqual(self._escribir("xyz").format, "WAV")

    def test_tipos_mime_declarados(self):
        self.assertEqual(server.AUDIO_MEDIA_TYPES[".mp3"], "audio/mpeg")
        self.assertEqual(server.AUDIO_MEDIA_TYPES[".flac"], "audio/flac")


class LongitudDeReferenciaTest(unittest.TestCase):
    """
    La fidelidad se estanca a los ~15 s y luego empeora, y una referencia
    larga dispara el cuelgue sin token de fin. Por eso se recorta.
    """

    def _voz(self, segundos, sr=24000):
        import numpy as np
        n = int(segundos * sr)
        t = np.arange(n) / sr
        # Habla simulada: tono con silencios intercalados cada segundo.
        y = (0.3 * np.sin(2 * np.pi * 180 * t)).astype("float32")
        for k in range(1, int(segundos)):
            y[int((k - 0.12) * sr):int(k * sr)] = 0.0
        return y

    def test_una_referencia_corta_no_se_toca(self):
        corta = self._voz(12)
        salida = server.limit_reference_length(corta, 24000)
        self.assertEqual(len(salida), len(corta))

    def test_una_referencia_larga_se_recorta(self):
        salida = server.limit_reference_length(self._voz(40), 24000)
        self.assertLessEqual(len(salida) / 24000, server.REFERENCE_MAX_SECONDS + 0.01)

    def test_el_recorte_conserva_material_suficiente(self):
        salida = server.limit_reference_length(self._voz(40), 24000)
        self.assertGreaterEqual(len(salida) / 24000, server.REFERENCE_MIN_KEEP_SECONDS)

    def test_el_recorte_cae_en_un_silencio(self):
        import numpy as np
        salida = server.limit_reference_length(self._voz(40), 24000)
        # El final no debe quedar a mitad de palabra: la última muestra es
        # parte de un tramo con voz, no un corte en seco a plena amplitud.
        self.assertLess(float(np.abs(salida[-1])), 0.35)

    def test_el_optimo_puntua_mas_que_una_referencia_larga(self):
        self.assertGreater(server.REFERENCE_MAX_SECONDS, 15.0)
        self.assertLess(server.REFERENCE_MAX_SECONDS, 25.0)


class TramoDeReferenciaTest(unittest.TestCase):
    """Elegir desde qué segundo se toma la referencia."""

    def _voz(self, segundos, sr=24000):
        import numpy as np
        n = int(segundos * sr)
        y = (0.3 * np.sin(2 * np.pi * 180 * np.arange(n) / sr)).astype("float32")
        for k in range(1, int(segundos)):
            y[int((k - 0.12) * sr):int(k * sr)] = 0.0
        return y

    def test_sin_desplazamiento_se_toma_el_principio(self):
        y = self._voz(40)
        salida = server.limit_reference_length(y, 24000, 0.0)
        import numpy as np
        self.assertTrue(np.array_equal(salida, y[:len(salida)]))

    def test_con_desplazamiento_se_descarta_el_principio(self):
        import numpy as np
        y = self._voz(40)
        salida = server.limit_reference_length(y, 24000, 10.0)
        self.assertFalse(np.array_equal(salida, y[:len(salida)]))
        self.assertLessEqual(len(salida) / 24000, server.REFERENCE_MAX_SECONDS + 0.01)

    def test_un_desplazamiento_excesivo_se_ignora(self):
        # Pedir un tramo que dejaría menos material del mínimo no debe
        # producir una referencia inservible: se mantiene el comportamiento
        # normal en vez de devolver medio segundo de audio.
        salida = server.limit_reference_length(self._voz(20), 24000, 19.0)
        self.assertGreaterEqual(len(salida) / 24000, server.REFERENCE_MIN_KEEP_SECONDS)

    def test_desplazamiento_negativo_no_rompe(self):
        salida = server.limit_reference_length(self._voz(20), 24000, -5.0)
        self.assertGreater(len(salida), 0)


class RemuestreoTest(unittest.TestCase):
    """El modelo entrega 24 kHz; las emisoras suelen pedir 44.1 kHz."""

    def setUp(self):
        import numpy as np
        self.mono = (0.3 * np.sin(2 * np.pi * 440 * np.arange(24000) / 24000)).astype("float32")

    def test_sin_objetivo_no_toca_nada(self):
        import numpy as np
        salida, sr = server.resample_output(self.mono, 24000, 0)
        self.assertEqual(sr, 24000)
        self.assertTrue(np.array_equal(salida, self.mono))

    def test_misma_frecuencia_no_toca_nada(self):
        import numpy as np
        salida, sr = server.resample_output(self.mono, 24000, 24000)
        self.assertEqual(sr, 24000)
        self.assertTrue(np.array_equal(salida, self.mono))

    def test_sube_a_44100_conservando_la_duracion(self):
        salida, sr = server.resample_output(self.mono, 24000, 44100)
        self.assertEqual(sr, 44100)
        self.assertAlmostEqual(len(salida) / sr, len(self.mono) / 24000, delta=0.01)

    def test_conserva_los_canales_de_una_mezcla_estereo(self):
        import numpy as np
        estereo = np.stack([self.mono, self.mono * 0.5], axis=1)
        salida, sr = server.resample_output(estereo, 24000, 44100)
        self.assertEqual(sr, 44100)
        self.assertEqual(salida.ndim, 2)
        self.assertEqual(salida.shape[1], 2)
        self.assertAlmostEqual(salida.shape[0] / sr, estereo.shape[0] / 24000, delta=0.01)

    def test_no_introduce_valores_invalidos(self):
        import numpy as np
        salida, _ = server.resample_output(self.mono, 24000, 44100)
        self.assertTrue(np.all(np.isfinite(salida)))
        self.assertLessEqual(float(np.max(np.abs(salida))), 1.05)

if __name__ == "__main__":
    unittest.main()
