from __future__ import annotations

import importlib.abc
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))


class BlockModule(importlib.abc.MetaPathFinder):
    """Makes one package look absent, the way a trimmed build makes it absent."""

    def __init__(self, blocked: str) -> None:
        self.blocked = blocked

    def find_spec(self, name, path=None, target=None):
        if name == self.blocked or name.startswith(f"{self.blocked}."):
            raise ModuleNotFoundError(f"No module named '{self.blocked}'")
        return None


class AudioPipelineProbeTest(unittest.TestCase):
    """
    Guards the check that decides whether a packaged engine may be activated.

    A build without scikit-learn still imports librosa cleanly (librosa attaches
    its submodules lazily) and only fails on the first real call — which is how
    an engine shipped that started fine but broke every voice import and every
    generation with "No module named 'sklearn'". The probe must exercise those
    calls, not just the imports.
    """

    def test_probe_passes_on_a_complete_runtime(self):
        from server import audio_pipeline_probe

        self.assertIn("OK", audio_pipeline_probe())

    def test_importing_librosa_alone_does_not_prove_it_works(self):
        blocker = BlockModule("sklearn")
        for name in [n for n in sys.modules if n == "sklearn" or n.startswith("sklearn.")]:
            del sys.modules[name]
        sys.meta_path.insert(0, blocker)
        try:
            import librosa

            # The weak check the self-test used to rely on: it passes.
            self.assertTrue(librosa.__version__)

            # The real pipeline does not.
            from server import audio_pipeline_probe

            with self.assertRaises(ModuleNotFoundError):
                audio_pipeline_probe()
        finally:
            sys.meta_path.remove(blocker)


if __name__ == "__main__":
    unittest.main()
