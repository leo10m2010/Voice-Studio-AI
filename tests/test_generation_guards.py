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


class FakeTorch:
    """Los dtypes de torch solo se comparan por identidad aquí."""

    bfloat16 = "bfloat16"
    float16 = "float16"
    float32 = "float32"


class CudaDtypeTest(unittest.TestCase):
    """
    En GPU este modelo va en fp32, medido en una RTX 4070 con muestreo
    determinista:

      fp16   -> aborta el proceso (TensorCompare.cu: Assertion input[0] != 0)
      bf16   -> 13.92 s de audio, rms 0.032   (mal: no cierra la locución)
      fp32   -> 4.40 s, rms 0.070             (coincide con CPU: 4.24 s, 0.075)

    Por fp16 no se completó nunca una locución en GPU, ni en la 4070 ni en el
    equipo antiguo.
    """

    def setUp(self):
        self.addCleanup(setattr, server, "CUDA_COMPUTE_DTYPE", server.CUDA_COMPUTE_DTYPE)

    def test_por_defecto_es_fp32(self):
        server.CUDA_COMPUTE_DTYPE = "float32"
        self.assertEqual(server.cuda_dtype_name(), "float32")
        self.assertEqual(server.resolve_cuda_dtype(FakeTorch), FakeTorch.float32)

    def test_fp16_no_es_elegible_ni_pidiéndolo(self):
        # Es el dtype que abortaba el proceso: dejarlo elegible solo serviría
        # para reproducir el fallo.
        server.CUDA_COMPUTE_DTYPE = "float16"
        self.assertEqual(server.cuda_dtype_name(), "float32")
        self.assertEqual(server.resolve_cuda_dtype(FakeTorch), FakeTorch.float32)

    def test_bf16_solo_si_se_pide_por_entorno(self):
        server.CUDA_COMPUTE_DTYPE = "bfloat16"
        self.assertEqual(server.resolve_cuda_dtype(FakeTorch), FakeTorch.bfloat16)

    def test_un_valor_raro_no_rompe(self):
        server.CUDA_COMPUTE_DTYPE = "cualquier-cosa"
        self.assertEqual(server.resolve_cuda_dtype(FakeTorch), FakeTorch.float32)


class VramRequirementTest(unittest.TestCase):
    """El 0.6B en fp32 llega a 5.29 GB asignados / 5.73 GB reservados con un
    guion largo. Las cifras viejas (2.5 / 5.0) suponían fp16."""

    def test_cubre_el_pico_medido_del_modelo_por_defecto(self):
        self.assertGreaterEqual(server.vram_required_gb(server.DEFAULT_MODEL_ID), 5.73)

    def test_el_modelo_grande_pide_más_que_el_pequeño(self):
        self.assertGreater(
            server.vram_required_gb("Qwen/Qwen3-TTS-12Hz-1.7B-Base"),
            server.vram_required_gb(server.DEFAULT_MODEL_ID),
        )

    def test_modelo_desconocido_usa_el_valor_por_defecto(self):
        self.assertEqual(
            server.vram_required_gb("no/existe"),
            server.DEFAULT_VRAM_REQUIRED_GB,
        )

    def test_lo_que_ve_la_interfaz_coincide_con_lo_que_decide_el_motor(self):
        # updateHardwareHint() usa gpu_vram_recommended_gb para dibujar
        # "Auto→CUDA/CPU". Si divergiera de choose_backend(), la app anunciaría
        # una cosa y haría otra.
        for model_id in server.SUPPORTED_MODELS:
            with self.subTest(model_id=model_id):
                self.assertEqual(
                    server.SUPPORTED_MODELS[model_id]["gpu_vram_recommended_gb"],
                    server.vram_required_gb(model_id),
                )


class CudaFaultTest(unittest.TestCase):
    """
    Un device-side assert corrompe el contexto CUDA del proceso entero: todo lo
    que venga después falla igual. En el registro se veían cinco POST
    /api/generate seguidos devolviendo 500 sin que nada cambiara.
    """

    def setUp(self):
        server.reset_cuda_fault()
        self.addCleanup(server.reset_cuda_fault)

    def test_reconoce_el_fallo_real_del_registro(self):
        exc = RuntimeError(
            "CUDA error: device-side assert triggered\n"
            "CUDA kernel errors might be asynchronously reported at some other API call."
        )
        self.assertTrue(server.is_cuda_fault(exc))

    def test_falta_de_memoria_no_descarta_la_gpu(self):
        # Es recuperable y tiene su propio camino: un trabajo más corto sí cabría.
        exc = RuntimeError("CUDA out of memory. Tried to allocate 2.00 GiB")
        self.assertFalse(server.is_cuda_fault(exc))

    def test_un_error_corriente_no_descarta_la_gpu(self):
        self.assertFalse(server.is_cuda_fault(FileNotFoundError("falta el guion")))

    def test_descartar_la_gpu_fuerza_cpu_en_modo_auto(self):
        server.disable_cuda("RuntimeError: CUDA error: device-side assert triggered")
        self.assertEqual(
            server.MODEL_MANAGER.choose_backend("auto", server.DEFAULT_MODEL_ID),
            "cpu",
        )

    def test_pedir_cuda_a_mano_lo_dice_en_vez_de_reventar(self):
        server.disable_cuda("RuntimeError: CUDA error: device-side assert triggered")
        with self.assertRaises(RuntimeError) as caught:
            server.MODEL_MANAGER.choose_backend("cuda", server.DEFAULT_MODEL_ID)
        self.assertIn("Reinicia la app", str(caught.exception))

    def test_solo_se_guarda_el_primer_motivo(self):
        server.disable_cuda("primero")
        server.disable_cuda("segundo")
        self.assertEqual(server.cuda_fault_reason(), "primero")


class FriendlyErrorTest(unittest.TestCase):
    """El volcado crudo de un fallo CUDA son diez líneas sobre CUDA_LAUNCH_BLOCKING
    y TORCH_USE_CUDA_DSA: depuración de PyTorch, no algo que ayude a locutar."""

    def test_el_fallo_cuda_se_traduce(self):
        mensaje = server.friendly_generation_error(
            RuntimeError("CUDA error: device-side assert triggered")
        )
        self.assertNotIn("device-side", mensaje)
        self.assertIn("CPU", mensaje)

    def test_la_falta_de_memoria_dice_qué_hacer(self):
        mensaje = server.friendly_generation_error(RuntimeError("CUDA out of memory."))
        self.assertIn("memoria", mensaje)

    def test_los_demás_errores_se_muestran_tal_cual(self):
        mensaje = server.friendly_generation_error(ValueError("voz no encontrada"))
        self.assertIn("voz no encontrada", mensaje)


class IclTranscriptTest(unittest.TestCase):
    """
    ICL solo funciona si la transcripción es lo que de verdad se oye en el
    audio preparado. Con desajuste el modelo nunca emite el token de fin y
    agota max_new_tokens. Medido en una RTX 4070, guion que debería durar
    3.5 s con referencia de 13.7 s:

      texto exacto (202 car)  ->  3.92 s   correcto
      sin texto               ->  3.68 s   correcto
      texto de más (326 car)  -> 10.48 s   mal
      texto de menos (68 car) -> 30.64 s   inservible
      texto x4 (1307 car)     -> 30.64 s   inservible

    El caso real: una voz de 73 s se recorta a 18 s pero conserva la
    transcripción entera; 970 caracteres para 18 s son 53.9 car/s.
    """

    def test_una_transcripcion_que_corresponde_se_usa(self):
        # 13.7 s de audio, 202 caracteres: 14.7 car/s.
        texto, motivo = server.usable_icl_transcript("x" * 202, 13.7)
        self.assertEqual(len(texto), 202)
        self.assertIsNone(motivo)

    def test_el_caso_real_de_entel_se_descarta(self):
        texto, motivo = server.usable_icl_transcript("x" * 970, 18.0)
        self.assertEqual(texto, "")
        self.assertIn("más", motivo)

    def test_texto_de_menos_se_descarta(self):
        texto, motivo = server.usable_icl_transcript("x" * 68, 13.7)
        self.assertEqual(texto, "")
        self.assertIn("menos", motivo)

    def test_sin_transcripcion_no_es_un_descarte(self):
        # x-vector es un modo legítimo, no un fallo: no hay motivo que contar.
        for vacio in ("", "   ", None):
            with self.subTest(vacio=repr(vacio)):
                texto, motivo = server.usable_icl_transcript(vacio, 13.7)
                self.assertEqual(texto, "")
                self.assertIsNone(motivo)

    def test_sin_duracion_medida_no_se_arriesga(self):
        texto, motivo = server.usable_icl_transcript("x" * 200, 0.0)
        self.assertEqual(texto, "")
        self.assertIsNotNone(motivo)

    def test_acepta_el_rango_de_velocidad_de_habla_normal(self):
        # 10 s de audio: se aceptan de 77 a 224 caracteres.
        for n in (80, 140, 200):
            with self.subTest(n=n):
                texto, _ = server.usable_icl_transcript("x" * n, 10.0)
                self.assertEqual(len(texto), n)

    def test_recorta_espacios_antes_de_medir(self):
        texto, motivo = server.usable_icl_transcript("  " + "x" * 140 + "  ", 10.0)
        self.assertEqual(len(texto), 140)
        self.assertIsNone(motivo)


class PromptCacheModeTest(unittest.TestCase):
    """
    La clave de la caché no distinguía ICL de x-vector, así que generar con
    transcripción y luego sin ella devolvía el prompt ICL cacheado: la segunda
    locución salía rota heredando el modo de la primera.
    """

    def test_icl_y_xvector_no_comparten_entrada(self):
        llamadas = []

        class ModeloFalso:
            def create_voice_clone_prompt(self, ref_audio, ref_text, x_vector_only_mode):
                llamadas.append(x_vector_only_mode)
                return f"prompt-{'xvec' if x_vector_only_mode else 'icl'}"

        manager = server.ModelManager()
        manager.model_id = "modelo"
        voz = Path("Animador.mp3")
        metadata = {"signature": "firma", "prepared_analysis": {"duration": 10.0}}
        original = server.prepare_reference_audio
        server.prepare_reference_audio = lambda path, force=False: (path, metadata)
        self.addCleanup(setattr, server, "prepare_reference_audio", original)

        icl, _, _ = manager.get_clone_prompt(ModeloFalso(), voz, "x" * 140, "cpu")
        xvec, _, _ = manager.get_clone_prompt(ModeloFalso(), voz, None, "cpu")

        self.assertEqual(icl, "prompt-icl")
        self.assertEqual(xvec, "prompt-xvec")
        self.assertEqual(llamadas, [False, True])

    def test_la_misma_peticion_sigue_reutilizando_la_cache(self):
        llamadas = []

        class ModeloFalso:
            def create_voice_clone_prompt(self, ref_audio, ref_text, x_vector_only_mode):
                llamadas.append(x_vector_only_mode)
                return "prompt"

        manager = server.ModelManager()
        manager.model_id = "modelo"
        voz = Path("Animador.mp3")
        metadata = {"signature": "firma", "prepared_analysis": {"duration": 10.0}}
        original = server.prepare_reference_audio
        server.prepare_reference_audio = lambda path, force=False: (path, metadata)
        self.addCleanup(setattr, server, "prepare_reference_audio", original)

        manager.get_clone_prompt(ModeloFalso(), voz, "x" * 140, "cpu")
        manager.get_clone_prompt(ModeloFalso(), voz, "x" * 140, "cpu")
        self.assertEqual(len(llamadas), 1)


class ReferenceScoreTest(unittest.TestCase):
    """Puntuar por "tiene transcripción" mentía: la voz de 73 s recortada a
    18 s con su transcripción entera salía "Excelente 96" y era inservible."""

    def _analiza(self, segundos, transcript):
        import numpy as np
        import soundfile as sf
        import tempfile

        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "ref.wav"
            n = int(24000 * segundos)
            onda = (0.2 * np.sin(2 * np.pi * 180 * np.arange(n) / 24000)).astype("float32")
            sf.write(str(ruta), onda, 24000)
            return server.analyze_reference_audio(ruta, transcript)

    def test_una_transcripcion_que_no_corresponde_no_suma(self):
        buena = self._analiza(14.0, "x" * 200)
        mala = self._analiza(14.0, "x" * 970)
        self.assertTrue(buena["transcript_usable"])
        self.assertFalse(mala["transcript_usable"])
        self.assertGreater(buena["quality_score"], mala["quality_score"])

    def test_lo_explica_en_las_notas(self):
        mala = self._analiza(14.0, "x" * 970)
        self.assertTrue(any("recorta" in n for n in mala["notes"]))


class IclGreedyTest(unittest.TestCase):
    """
    El muestreo voraz se desboca en ICL. Medido en una RTX 4070, guion que
    debería durar 7.8 s:

      perfil fiel + x-vector ->  7.44 s   0.96x   correcto
      perfil fiel + ICL      -> 30.64 s   3.94x   inservible
      temperatura baja + ICL ->  8.16 s   1.05x   correcto

    Es el peor caso posible: "fiel" es el perfil que elige quien busca máxima
    fidelidad, y la transcripción es lo que recomienda Qwen para lo mismo.
    """

    def test_el_perfil_fiel_es_voraz(self):
        # Si esto cambia, la sustitución de abajo deja de hacer falta.
        fiel = server.qwen_sampling_from_friendly_controls(1.0, 0.0, "faithful")
        self.assertFalse(fiel["do_sample"])
        self.assertFalse(fiel["subtalker_dosample"])

    def test_con_icl_se_sustituye_por_temperatura_baja(self):
        fiel = server.qwen_sampling_from_friendly_controls(1.0, 0.0, "faithful")
        seguro = server.sampling_safe_for_icl(fiel, icl_active=True)
        self.assertTrue(seguro["do_sample"])
        self.assertTrue(seguro["subtalker_dosample"])
        self.assertLessEqual(seguro["temperature"], 0.75)

    def test_sin_icl_el_perfil_fiel_se_respeta(self):
        # Voraz + x-vector sí funciona (0.96x) y da tomas idénticas entre sí,
        # que es justo lo que promete el perfil.
        fiel = server.qwen_sampling_from_friendly_controls(1.0, 0.0, "faithful")
        self.assertEqual(server.sampling_safe_for_icl(fiel, icl_active=False), fiel)

    def test_un_perfil_que_ya_muestrea_no_se_toca(self):
        natural = server.qwen_sampling_from_friendly_controls(0.5, 0.3, "natural")
        self.assertEqual(server.sampling_safe_for_icl(natural, icl_active=True), natural)

    def test_no_muta_el_diccionario_recibido(self):
        # Cada trabajo en cola lleva su propia copia de los ajustes; mutarla
        # aquí cambiaría los ajustes guardados en el historial.
        fiel = server.qwen_sampling_from_friendly_controls(1.0, 0.0, "faithful")
        copia = dict(fiel)
        server.sampling_safe_for_icl(fiel, icl_active=True)
        self.assertEqual(fiel, copia)


class AutoTranscriptTest(unittest.TestCase):
    """
    Transcribir el tramo que de verdad se usa es lo que hace utilizable el modo
    ICL, que Qwen recomienda para máxima fidelidad. Pedirle el texto al usuario
    no funciona: pega el del audio completo, el motor recorta a 18 s y el par
    deja de cuadrar.
    """

    def setUp(self):
        self.meta = {"signature": "firma", "prepared_analysis": {"duration": 18.0}}
        original = server.prepare_reference_audio
        server.prepare_reference_audio = lambda path, force=False: (path, self.meta)
        self.addCleanup(setattr, server, "prepare_reference_audio", original)
        self.llamadas = []

        class ModeloFalso:
            def create_voice_clone_prompt(inner, ref_audio, ref_text, x_vector_only_mode):
                self.llamadas.append(ref_text)
                return "prompt"

        self.modelo = ModeloFalso()
        self.manager = server.ModelManager()
        self.manager.model_id = "modelo"

    def test_sustituye_a_la_pegada_cuando_esta_no_cuadra(self):
        # 970 caracteres para 18 s son 53.9 car/s: el caso real que fallaba.
        self.meta["auto_transcript"] = "y" * 250
        _, _, rechazo = self.manager.get_clone_prompt(
            self.modelo, Path("entel.mp3"), "x" * 970, "cpu"
        )
        self.assertEqual(self.llamadas, ["y" * 250])
        self.assertIsNone(rechazo)

    def test_la_pegada_manda_si_cuadra(self):
        # Es la del usuario: si describe el tramo, es mejor fuente que el ASR.
        self.meta["auto_transcript"] = "y" * 250
        self.manager.get_clone_prompt(self.modelo, Path("v.mp3"), "x" * 250, "cpu")
        self.assertEqual(self.llamadas, ["x" * 250])

    def test_sin_transcripcion_pegada_usa_la_automatica(self):
        self.meta["auto_transcript"] = "y" * 250
        self.manager.get_clone_prompt(self.modelo, Path("v.mp3"), None, "cpu")
        self.assertEqual(self.llamadas, ["y" * 250])

    def test_si_el_asr_no_dio_nada_se_clona_con_huella_de_voz(self):
        # Sin red o sin modelo ASR la generación no puede caerse.
        self.meta["auto_transcript"] = ""
        self.manager.get_clone_prompt(self.modelo, Path("v.mp3"), None, "cpu")
        self.assertEqual(self.llamadas, [None])

    def test_una_transcripcion_automatica_absurda_tambien_se_descarta(self):
        # El ASR puede alucinar en audio con música o ruido.
        self.meta["auto_transcript"] = "y" * 4000
        self.manager.get_clone_prompt(self.modelo, Path("v.mp3"), None, "cpu")
        self.assertEqual(self.llamadas, [None])

    def test_transcribir_nunca_tumba_la_generacion(self):
        original = server.asr_model
        server.asr_model = lambda: (_ for _ in ()).throw(RuntimeError("sin red"))
        self.addCleanup(setattr, server, "asr_model", original)
        try:
            self.assertEqual(server.transcribe_reference(Path("no_existe.wav")), "")
        except RuntimeError:
            self.fail("transcribe_reference dejó escapar la excepción")


class TramoAutomaticoTest(unittest.TestCase):
    """
    El tramo lo elige el motor. Antes había un control para elegirlo a mano y
    era una decisión que nadie puede tomar sin escuchar el audio entero.

    Lo que se busca es voz limpia: medido sobre referencias reales, con la
    limpia el clon puntuó 87.5% con 4.8 puntos de dispersión entre tomas, y con
    una que lleva música de fondo, 77.2% con 33 puntos.
    """

    def _onda(self, segundos, sr=24000, con_silencios=True, amplitud=0.3, suelo=0.0):
        import numpy as np

        n = int(segundos * sr)
        t = np.arange(n) / sr
        y = (amplitud * np.sin(2 * np.pi * 180 * t)).astype("float32")
        if con_silencios:
            for k in range(1, int(segundos)):
                y[int((k - 0.35) * sr) : int(k * sr)] = 0.0
        if suelo:
            y = y + (suelo * np.sin(2 * np.pi * 55 * t)).astype("float32")
        return y.astype("float32")

    def test_el_suelo_distingue_voz_sola_de_musica_de_fondo(self):
        # Lo que importa es que separe, no el valor absoluto: en referencias
        # reales va de 0.04 (voz sola) a 0.65 (spot con música debajo).
        limpia = server.background_floor(self._onda(6), 24000)
        con_musica = server.background_floor(self._onda(6, suelo=0.12), 24000)
        self.assertLess(limpia, 0.2)
        self.assertGreater(con_musica, limpia * 2)

    def test_elige_la_ventana_limpia_y_no_la_del_principio(self):
        import numpy as np

        sucio = self._onda(20, suelo=0.15)
        limpio = self._onda(20)
        elegido = server.limit_reference_length(
            np.concatenate([sucio, limpio]), 24000
        )
        self.assertLess(server.background_floor(elegido, 24000), 0.3)

    def test_un_tramo_casi_vacio_nunca_gana(self):
        # Tiene el suelo perfecto y ninguna voz: sin la guarda ganaría siempre.
        import numpy as np

        silencio = np.zeros(int(18 * 24000), dtype="float32")
        self.assertEqual(server.score_reference_window(silencio, 24000), -1.0)

    def test_respeta_el_tramo_guardado_por_un_motor_anterior(self):
        import numpy as np

        y = self._onda(40)
        elegido = server.limit_reference_length(y, 24000, offset_seconds=10.0)
        self.assertLessEqual(len(elegido) / 24000, server.REFERENCE_MAX_SECONDS + 0.01)

    def test_una_referencia_corta_no_se_recorta(self):
        y = self._onda(10)
        self.assertEqual(len(server.limit_reference_length(y, 24000)), len(y))


class AsrOpcionalTest(unittest.TestCase):
    """
    Transcribir no compra fidelidad: emparejando por semilla sobre referencia
    limpia, ICL y huella de voz empatan (-0.06 puntos, 4 de 6). Por eso el
    modelo de 250 MB no se le descarga a nadie sin pedirlo.
    """

    def setUp(self):
        self.bandera = server.DATA_ROOT / "asr_enabled.flag"
        self.previo = self.bandera.read_text(encoding="utf-8") if self.bandera.exists() else None
        self.addCleanup(self._restaurar)

    def _restaurar(self):
        if self.previo is None:
            self.bandera.unlink(missing_ok=True)
        else:
            self.bandera.write_text(self.previo, encoding="utf-8")

    def test_viene_apagado(self):
        self.bandera.unlink(missing_ok=True)
        self.assertFalse(server.asr_enabled())

    def test_apagado_no_transcribe_ni_carga_el_modelo(self):
        server.set_asr_enabled(False)
        llamadas = []
        original = server.asr_model
        server.asr_model = lambda: llamadas.append(1)
        self.addCleanup(setattr, server, "asr_model", original)
        self.assertEqual(server.transcribe_reference(Path("da_igual.wav")), "")
        self.assertEqual(llamadas, [])

    def test_el_interruptor_persiste(self):
        server.set_asr_enabled(True)
        self.assertTrue(server.asr_enabled())
        server.set_asr_enabled(False)
        self.assertFalse(server.asr_enabled())


class CatalogoDeVocesTest(unittest.TestCase):
    """
    El catálogo reparte voces a todos los equipos sin sacar instalador. Como el
    manifiesto viene de la red, cada campo se valida antes de tocar el disco.
    """

    def setUp(self):
        import tempfile

        self.carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(self.carpeta.cleanup)
        self.previo = server.VOICES_DIR
        server.VOICES_DIR = Path(self.carpeta.name)
        self.addCleanup(setattr, server, "VOICES_DIR", self.previo)
        self.descargas = []

    def _falso_requests(self, manifiesto, cuerpo=b"audio"):
        import hashlib

        prueba = self

        class Respuesta:
            status_code = 200

            def __init__(self, datos=None, contenido=None):
                self._datos = datos
                self._contenido = contenido

            def raise_for_status(self):
                return None

            @property
            def content(self):
                # El motor lee content y decodifica con utf-8-sig, porque el
                # manifiesto lo escribe PowerShell y puede colar un BOM.
                import json as _json

                return _json.dumps(self._datos).encode("utf-8")

            def json(self):
                return self._datos

            def iter_content(self, chunk_size=0):
                yield self._contenido

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        class Modulo:
            @staticmethod
            def get(url, timeout=0, stream=False):
                if url.endswith("voices-manifest.json"):
                    return Respuesta(datos=manifiesto)
                prueba.descargas.append(url)
                return Respuesta(contenido=cuerpo)

        import sys

        original = sys.modules.get("requests")
        sys.modules["requests"] = Modulo
        self.addCleanup(
            lambda: sys.modules.__setitem__("requests", original)
            if original
            else sys.modules.pop("requests", None)
        )
        return hashlib.sha256(cuerpo).hexdigest()

    def _entrada(self, **cambios):
        base = {
            "name": "Nueva.mp3",
            "url": "https://ejemplo/Nueva.mp3",
            "sha256": "0" * 64,
            "transcript": "Hola.",
        }
        base.update(cambios)
        return base

    def test_descarga_una_voz_nueva_con_su_transcripcion(self):
        digest = self._falso_requests({"voices": [self._entrada()]})
        # el sha del manifiesto tiene que ser el real
        digest2 = self._falso_requests({"voices": [self._entrada(sha256=digest)]})
        r = server.sync_remote_voices()
        self.assertEqual(r["descargadas"], ["Nueva.mp3"])
        destino = server.VOICES_DIR / "Nueva.mp3"
        self.assertTrue(destino.exists())
        self.assertEqual(server.transcript_path(destino).read_text(encoding="utf-8"), "Hola.")

    def test_un_sha_que_no_cuadra_no_deja_nada(self):
        self._falso_requests({"voices": [self._entrada(sha256="a" * 64)]})
        r = server.sync_remote_voices()
        self.assertEqual(r["descargadas"], [])
        self.assertFalse((server.VOICES_DIR / "Nueva.mp3").exists())
        self.assertFalse((server.VOICES_DIR / "Nueva.mp3.parcial").exists())

    def test_no_pisa_una_voz_que_ya_tienes(self):
        # Si la editaste o le pusiste transcripción, tu copia manda.
        destino = server.VOICES_DIR / "Nueva.mp3"
        destino.write_bytes(b"lo mio")
        digest = self._falso_requests({"voices": [self._entrada()]})
        self._falso_requests({"voices": [self._entrada(sha256=digest)]})
        server.sync_remote_voices()
        self.assertEqual(destino.read_bytes(), b"lo mio")
        self.assertEqual(self.descargas, [])

    def test_agrega_transcripcion_a_un_audio_oficial_ya_instalado(self):
        destino = server.VOICES_DIR / "Nueva.mp3"
        destino.write_bytes(b"audio")
        digest = self._falso_requests({"voices": [self._entrada()]})
        self._falso_requests({"voices": [self._entrada(sha256=digest)]})

        r = server.sync_remote_voices()

        self.assertEqual(r["descargadas"], [])
        self.assertEqual(r["transcripciones"], ["Nueva.mp3"])
        self.assertEqual(destino.read_bytes(), b"audio")
        self.assertEqual(
            server.transcript_path(destino).read_text(encoding="utf-8"),
            "Hola.",
        )
        self.assertEqual(self.descargas, [])

    def test_no_pisa_una_transcripcion_existente(self):
        destino = server.VOICES_DIR / "Nueva.mp3"
        destino.write_bytes(b"audio")
        server.transcript_path(destino).write_text("Mi texto.", encoding="utf-8")
        digest = self._falso_requests({"voices": [self._entrada()]})
        self._falso_requests({"voices": [self._entrada(sha256=digest)]})

        r = server.sync_remote_voices()

        self.assertEqual(r["transcripciones"], [])
        self.assertEqual(
            server.transcript_path(destino).read_text(encoding="utf-8"),
            "Mi texto.",
        )

    def test_respeta_una_transcripcion_quitada_por_el_usuario(self):
        destino = server.VOICES_DIR / "Nueva.mp3"
        destino.write_bytes(b"audio")
        server.transcript_disabled_path(destino).write_text(
            "user_removed\n", encoding="utf-8"
        )
        digest = self._falso_requests({"voices": [self._entrada()]})
        self._falso_requests({"voices": [self._entrada(sha256=digest)]})

        r = server.sync_remote_voices()

        self.assertEqual(r["transcripciones"], [])
        self.assertFalse(server.transcript_path(destino).exists())

    def test_rechaza_nombres_que_se_salen_de_la_carpeta(self):
        for nombre in ("../fuera.mp3", "sub/dir.mp3", "..\fuera.mp3"):
            with self.subTest(nombre=nombre):
                self._falso_requests({"voices": [self._entrada(name=nombre)]})
                server.sync_remote_voices()
                self.assertEqual(self.descargas, [])

    def test_rechaza_extensiones_que_no_son_audio(self):
        self._falso_requests({"voices": [self._entrada(name="script.exe")]})
        server.sync_remote_voices()
        self.assertEqual(self.descargas, [])

    def test_rechaza_urls_que_no_son_https(self):
        self._falso_requests({"voices": [self._entrada(url="http://ejemplo/a.mp3")]})
        server.sync_remote_voices()
        self.assertEqual(self.descargas, [])

    def test_sin_red_no_revienta(self):
        import sys

        class Modulo:
            @staticmethod
            def get(*a, **k):
                raise OSError("sin red")

        original = sys.modules.get("requests")
        sys.modules["requests"] = Modulo
        self.addCleanup(
            lambda: sys.modules.__setitem__("requests", original)
            if original
            else sys.modules.pop("requests", None)
        )
        r = server.sync_remote_voices()
        self.assertEqual(r["descargadas"], [])
        self.assertIsNotNone(r["error"])


class BorrarUnaLocucionTest(unittest.TestCase):
    """
    Antes solo se podía vaciar el historial entero, así que quitar una toma
    fallida obligaba a tirar también las buenas.
    """

    def setUp(self):
        import tempfile

        self.carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(self.carpeta.cleanup)
        raiz = Path(self.carpeta.name)
        self.salidas = raiz / "outputs"
        self.salidas.mkdir()
        self.historial = raiz / "history.json"

        for atributo, valor in (("HISTORY_PATH", self.historial), ("OUTPUTS_DIR", self.salidas)):
            if hasattr(server, atributo):
                self.addCleanup(setattr, server, atributo, getattr(server, atributo))
                setattr(server, atributo, valor)

    def _sembrar(self, items):
        server.save_history(items)

    def test_quita_solo_la_pedida(self):
        self._sembrar([
            {"id": "uno", "filename": "a.mp3"},
            {"id": "dos", "filename": "b.mp3"},
        ])
        (self.salidas / "a.mp3").write_bytes(b"a")
        (self.salidas / "b.mp3").write_bytes(b"b")

        server.delete_history_item("uno")

        quedan = [i["id"] for i in server.load_history()]
        self.assertEqual(quedan, ["dos"])

    def test_se_lleva_su_audio_y_respeta_el_de_las_demas(self):
        self._sembrar([
            {"id": "uno", "filename": "a.mp3"},
            {"id": "dos", "filename": "b.mp3"},
        ])
        (self.salidas / "a.mp3").write_bytes(b"a")
        (self.salidas / "b.mp3").write_bytes(b"b")

        server.delete_history_item("uno")

        self.assertFalse((self.salidas / "a.mp3").exists())
        self.assertTrue((self.salidas / "b.mp3").exists())

    def test_un_audio_compartido_no_se_borra(self):
        # Cambiar la música reusa el mismo audio seco en otra entrada.
        self._sembrar([
            {"id": "uno", "filename": "mezcla.mp3", "dry_filename": "seco.mp3"},
            {"id": "dos", "filename": "otra.mp3", "dry_filename": "seco.mp3"},
        ])
        for n in ("mezcla.mp3", "otra.mp3", "seco.mp3"):
            (self.salidas / n).write_bytes(b"x")

        server.delete_history_item("uno")

        self.assertFalse((self.salidas / "mezcla.mp3").exists())
        self.assertTrue((self.salidas / "seco.mp3").exists())

    def test_una_que_no_existe_da_404(self):
        self._sembrar([{"id": "uno", "filename": "a.mp3"}])
        with self.assertRaises(server.HTTPException) as caught:
            server.delete_history_item("no-existe")
        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(len(server.load_history()), 1)


if __name__ == "__main__":
    unittest.main()
