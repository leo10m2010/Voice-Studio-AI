from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from model_install import ModelInstallRegistry, model_snapshot_complete


MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
SUPPORTED = {MODEL_ID: {"disk_gb": 2.52}}


def make_snapshot(hf_home: Path, model_id: str = MODEL_ID) -> Path:
    snapshot = (
        hf_home
        / "hub"
        / f"models--{model_id.replace('/', '--')}"
        / "snapshots"
        / "abc123"
    )
    snapshot.mkdir(parents=True, exist_ok=True)
    (snapshot / "config.json").write_text("{}", encoding="utf-8")
    (snapshot / "model.safetensors").write_bytes(b"weights")
    return snapshot


class ModelInstallTests(unittest.TestCase):
    def test_snapshot_requires_config_and_weights(self):
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = Path(temporary)
            self.assertFalse(model_snapshot_complete(snapshot))
            (snapshot / "config.json").write_text("{}", encoding="utf-8")
            self.assertFalse(model_snapshot_complete(snapshot))
            (snapshot / "model.safetensors").write_bytes(b"weights")
            self.assertTrue(model_snapshot_complete(snapshot))

    def test_existing_hugging_face_cache_is_detected_and_recorded(self):
        with tempfile.TemporaryDirectory() as temporary:
            hf_home = Path(temporary)
            snapshot = make_snapshot(hf_home)

            def downloader(**kwargs):
                self.assertTrue(kwargs["local_files_only"])
                return str(snapshot)

            registry = ModelInstallRegistry(hf_home, SUPPORTED, downloader=downloader)
            state = registry.get_state(MODEL_ID)

            self.assertTrue(state["installed"])
            self.assertEqual(state["state"], "installed")
            self.assertEqual(Path(state["snapshot_path"]), snapshot)
            self.assertEqual(len(list((hf_home / "installed_models").glob("*.json"))), 1)

    def test_background_install_moves_from_downloading_to_installed(self):
        with tempfile.TemporaryDirectory() as temporary:
            hf_home = Path(temporary)

            def downloader(**kwargs):
                if kwargs["local_files_only"]:
                    raise FileNotFoundError("not cached")
                return str(make_snapshot(hf_home))

            registry = ModelInstallRegistry(hf_home, SUPPORTED, downloader=downloader)
            initial = registry.start(MODEL_ID)
            self.assertEqual(initial["state"], "downloading")

            final = initial
            for _ in range(100):
                final = registry.get_state(MODEL_ID)
                if final["state"] != "downloading":
                    break
                time.sleep(0.01)

            self.assertEqual(final["state"], "installed")
            self.assertTrue(final["installed"])

    def test_failed_download_has_recoverable_error_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            hf_home = Path(temporary)

            def downloader(**kwargs):
                if kwargs["local_files_only"]:
                    raise FileNotFoundError("not cached")
                raise ConnectionError("offline")

            registry = ModelInstallRegistry(hf_home, SUPPORTED, downloader=downloader)
            registry.start(MODEL_ID)

            final = {}
            for _ in range(100):
                final = registry.get_state(MODEL_ID)
                if final.get("state") == "error":
                    break
                time.sleep(0.01)

            self.assertEqual(final["state"], "error")
            self.assertFalse(final["installed"])
            self.assertIn("ConnectionError", final["error"])


if __name__ == "__main__":
    unittest.main()
