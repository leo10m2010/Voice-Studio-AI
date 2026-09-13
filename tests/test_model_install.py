from __future__ import annotations

import sys
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from model_install import ModelInstallRegistry, model_snapshot_complete


MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"
SUPPORTED = {MODEL_ID: {"disk_gb": 2.52}}


def write_weights(path: Path):
    header = json.dumps({"weight": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}}).encode()
    path.write_bytes(len(header).to_bytes(8, "little") + header + b"\0" * 4)


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
    write_weights(snapshot / "model.safetensors")
    return snapshot


class ModelInstallTests(unittest.TestCase):
    def test_snapshot_requires_config_and_weights(self):
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = Path(temporary)
            self.assertFalse(model_snapshot_complete(snapshot))
            (snapshot / "config.json").write_text("{}", encoding="utf-8")
            self.assertFalse(model_snapshot_complete(snapshot))
            write_weights(snapshot / "model.safetensors")
            self.assertTrue(model_snapshot_complete(snapshot))

    def test_nested_weights_do_not_replace_main_weights(self):
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = make_snapshot(Path(temporary))
            (snapshot / "speech_tokenizer").mkdir()
            (snapshot / "model.safetensors").rename(snapshot / "speech_tokenizer/model.safetensors")
            self.assertFalse(model_snapshot_complete(snapshot))

    def test_truncated_weights_and_missing_shards_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = make_snapshot(Path(temporary))
            weights = snapshot / "model.safetensors"
            weights.write_bytes(weights.read_bytes()[:-1])
            self.assertFalse(model_snapshot_complete(snapshot))
            write_weights(weights)
            (snapshot / "model.safetensors.index.json").write_text(json.dumps({
                "weight_map": {"a": "model.safetensors", "b": "missing.safetensors"}
            }))
            self.assertFalse(model_snapshot_complete(snapshot))

    def test_qwen_requires_text_and_speech_tokenizers(self):
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = make_snapshot(Path(temporary))
            (snapshot / "config.json").write_text('{"model_type": "qwen3_tts"}')
            self.assertFalse(model_snapshot_complete(snapshot))
            for name in ("generation_config.json", "preprocessor_config.json",
                         "tokenizer_config.json", "vocab.json"):
                (snapshot / name).write_text("{}")
            (snapshot / "merges.txt").write_text("#version: 0.2")
            speech = snapshot / "speech_tokenizer"
            speech.mkdir()
            for name in ("config.json", "configuration.json", "preprocessor_config.json"):
                (speech / name).write_text("{}")
            write_weights(speech / "model.safetensors")
            self.assertTrue(model_snapshot_complete(snapshot))
            (speech / "config.json").write_text("{")
            self.assertFalse(model_snapshot_complete(snapshot))

    def test_partial_cache_can_start_and_repairs_only_invalid_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            snapshot = make_snapshot(home)
            (snapshot / "model.safetensors").write_bytes(b"truncated")
            calls = []

            def downloader(**kwargs):
                calls.append(kwargs)
                if kwargs.get("force_download"):
                    self.assertEqual(kwargs["allow_patterns"], ["model.safetensors"])
                    self.assertEqual(kwargs["revision"], snapshot.name)
                    write_weights(snapshot / "model.safetensors")
                return str(snapshot)

            registry = ModelInstallRegistry(home, SUPPORTED, downloader=downloader)
            # A timeout makes the former recursive-lock deadlock fail, not hang CI.
            starter = threading.Thread(target=registry.start, args=(MODEL_ID,), daemon=True)
            starter.start()
            starter.join(2)
            self.assertFalse(starter.is_alive(), "start deadlocked on existing cache")
            for _ in range(200):
                final = registry.get_state(MODEL_ID)
                if final["state"] != "downloading":
                    break
                time.sleep(0.01)
            self.assertEqual(final["state"], "installed", final)
            self.assertEqual(sum(bool(call.get("force_download")) for call in calls), 1)

    def test_record_does_not_hide_later_truncation(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            snapshot = make_snapshot(home)
            registry = ModelInstallRegistry(home, SUPPORTED, downloader=lambda **kw: str(snapshot))
            self.assertTrue(registry.get_state(MODEL_ID)["installed"])
            (snapshot / "model.safetensors").write_bytes(b"broken")
            self.assertFalse(registry.get_state(MODEL_ID)["installed"])

    def test_unsuccessful_repair_never_marks_snapshot_installed(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            snapshot = make_snapshot(home)
            (snapshot / "model.safetensors").write_bytes(b"broken")
            registry = ModelInstallRegistry(home, SUPPORTED, downloader=lambda **kw: str(snapshot))
            registry.start(MODEL_ID)
            for _ in range(200):
                final = registry.get_state(MODEL_ID)
                if final["state"] != "downloading":
                    break
                time.sleep(0.01)
            self.assertEqual(final["state"], "error", final)
            self.assertIn("model.safetensors", final["error"])
            self.assertFalse(list(registry.records_dir.glob("*.json")))

    def test_unrelated_incomplete_blob_does_not_block_valid_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            snapshot = make_snapshot(home)
            (snapshot.parent.parent / "old.incomplete").write_bytes(b"partial")
            registry = ModelInstallRegistry(home, SUPPORTED, downloader=lambda **kw: str(snapshot))
            self.assertTrue(registry.get_state(MODEL_ID)["installed"])

    def test_symlink_bytes_are_not_counted_twice(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            snapshot = make_snapshot(home)
            try:
                (snapshot / "duplicate").symlink_to(snapshot / "model.safetensors")
            except OSError:
                self.skipTest("Symlink creation requires Windows developer mode or privileges")
            registry = ModelInstallRegistry(home, SUPPORTED)
            self.assertEqual(registry._downloaded_bytes(MODEL_ID),
                             (snapshot / "config.json").stat().st_size +
                             (snapshot / "model.safetensors").stat().st_size)

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
