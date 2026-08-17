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


if __name__ == "__main__":
    unittest.main()
