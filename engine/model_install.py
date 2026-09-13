from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Optional


Downloader = Callable[..., str]


def snapshot_problems(snapshot_path: Path) -> list[str]:
    """Validate local loading dependencies and safetensors lengths, without loading tensors."""
    snapshot = Path(snapshot_path)
    problems: set[str] = set()

    def check_file(relative: str) -> Optional[dict]:
        path = snapshot / relative
        try:
            if path.stat().st_size == 0:
                raise ValueError("empty file")
            if path.suffix == ".json":
                data = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("expected JSON object")
                return data
        except (OSError, ValueError, TypeError):
            problems.add(relative)
        return None

    config = check_file("config.json") or {}
    directories = [snapshot]
    if config.get("model_type") == "qwen3_tts":
        for relative in (
            "generation_config.json", "preprocessor_config.json", "tokenizer_config.json",
            "vocab.json", "merges.txt", "speech_tokenizer/config.json",
            "speech_tokenizer/configuration.json", "speech_tokenizer/preprocessor_config.json",
        ):
            check_file(relative)
        directories.append(snapshot / "speech_tokenizer")

    for directory in directories:
        weights = set(directory.glob("*.safetensors")) | set(directory.glob("pytorch_model*.bin"))
        for index in directory.glob("*.index.json"):
            data = check_file(index.relative_to(snapshot).as_posix()) or {}
            mapping = data.get("weight_map")
            if not isinstance(mapping, dict) or not mapping:
                problems.add(index.relative_to(snapshot).as_posix())
                continue
            for filename in mapping.values():
                if not isinstance(filename, str) or Path(filename).name != filename:
                    problems.add(index.relative_to(snapshot).as_posix())
                    continue
                weights.add(directory / filename)
        if not weights:
            problems.add((directory / "model.safetensors").relative_to(snapshot).as_posix())
        for path in weights:
            relative = path.relative_to(snapshot).as_posix()
            check_file(relative)
            if path.suffix != ".safetensors" or relative in problems:
                continue
            try:
                with path.open("rb") as stream:
                    prefix = stream.read(8)
                    header_size = int.from_bytes(prefix, "little")
                    if len(prefix) != 8 or not 0 < header_size <= 100_000_000:
                        raise ValueError("invalid safetensors header")
                    header = json.loads(stream.read(header_size))
                offsets = [value["data_offsets"] for key, value in header.items() if key != "__metadata__"]
                if not offsets or any(
                    len(pair) != 2 or any(type(n) is not int for n in pair)
                    or not 0 <= pair[0] <= pair[1] for pair in offsets
                ):
                    raise ValueError("invalid tensor offsets")
                if path.stat().st_size != 8 + header_size + max(pair[1] for pair in offsets):
                    raise ValueError("truncated tensor data")
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                problems.add(relative)
    return sorted(problems)


def model_snapshot_complete(snapshot_path: Path) -> bool:
    return not snapshot_problems(snapshot_path)


class ModelInstallRegistry:
    """Detects cached Hugging Face models and manages one background install."""

    def __init__(
        self,
        hf_home: Path,
        supported_models: Mapping[str, Mapping[str, object]],
        downloader: Optional[Downloader] = None,
    ) -> None:
        self.hf_home = Path(hf_home)
        self.cache_dir = self.hf_home / "hub"
        self.records_dir = self.hf_home / "installed_models"
        self.supported_models = supported_models
        self._downloader = downloader
        self._lock = threading.Lock()
        self._states: dict[str, dict] = {}
        self._size_cache: dict[str, int] = {}
        self._active_model_id: Optional[str] = None
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.records_dir.mkdir(parents=True, exist_ok=True)

    def _record_path(self, model_id: str) -> Path:
        digest = hashlib.sha256(model_id.encode("utf-8")).hexdigest()
        return self.records_dir / f"{digest}.json"

    def _repo_cache_dir(self, model_id: str) -> Path:
        return self.cache_dir / f"models--{model_id.replace('/', '--')}"

    def _within_cache(self, path: Path) -> bool:
        try:
            Path(path).resolve().relative_to(self.cache_dir.resolve())
            return True
        except (OSError, ValueError):
            return False

    def _load_record(self, model_id: str) -> Optional[dict]:
        try:
            record = json.loads(self._record_path(model_id).read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            return None
        if not isinstance(record, dict) or record.get("model_id") != model_id:
            return None
        return record

    def _write_record(self, model_id: str, snapshot_path: Path) -> dict:
        snapshot = Path(snapshot_path).resolve()
        if not self._within_cache(snapshot) or not model_snapshot_complete(snapshot):
            raise RuntimeError("La descarga terminó, pero la caché local del modelo está incompleta.")

        installed_at = datetime.now(timezone.utc).isoformat()
        record = {
            "model_id": model_id,
            "snapshot_path": str(snapshot),
            "installed_at": installed_at,
        }
        destination = self._record_path(model_id)
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, destination)
        return record

    def _snapshot_download(self, model_id: str, *, local_files_only: bool, **options) -> Path:
        downloader = self._downloader
        if downloader is None:
            from huggingface_hub import snapshot_download

            downloader = snapshot_download
        result = downloader(
            repo_id=model_id,
            cache_dir=str(self.cache_dir),
            local_files_only=local_files_only,
            **options,
        )
        return Path(result)

    def cached_snapshot(self, model_id: str) -> Optional[Path]:
        if model_id not in self.supported_models:
            return None

        record = self._load_record(model_id)
        if record:
            snapshot = Path(str(record.get("snapshot_path") or ""))
            if self._within_cache(snapshot) and model_snapshot_complete(snapshot):
                return snapshot

        try:
            snapshot = self._snapshot_download(model_id, local_files_only=True)
        except Exception:
            return None

        if not self._within_cache(snapshot) or not model_snapshot_complete(snapshot):
            return None
        try:
            self._write_record(model_id, snapshot)
        except (OSError, RuntimeError):
            pass
        return snapshot

    def _expected_bytes(self, model_id: str) -> int:
        try:
            return int(float(self.supported_models[model_id].get("disk_gb", 0)) * (1024**3))
        except (TypeError, ValueError):
            return 0

    def _downloaded_bytes(self, model_id: str, *, live: bool = False) -> int:
        """
        Total bytes on disk for a model.

        Walking a finished 2.3 GB snapshot takes hundreds of milliseconds, and
        /api/models is hit on every refresh and polled once a second during an
        install. Once a model is installed its size no longer changes, so the
        result is memoized; `live=True` forces a fresh walk while downloading.
        """
        root = self._repo_cache_dir(model_id)
        if not root.exists():
            return 0

        if not live:
            with self._lock:
                cached = self._size_cache.get(model_id)
            if cached is not None:
                return cached

        total = 0
        seen: set[Path] = set()
        for path in root.rglob("*"):
            try:
                resolved = path.resolve()
                if path.is_file() and resolved not in seen:
                    seen.add(resolved)
                    total += path.stat().st_size
            except OSError:
                continue

        if not live:
            with self._lock:
                self._size_cache[model_id] = total
        return total

    def _invalidate_size(self, model_id: str) -> None:
        with self._lock:
            self._size_cache.pop(model_id, None)

    def _installed_state(self, model_id: str, snapshot: Path) -> dict:
        record = self._load_record(model_id) or {}
        return {
            "model_id": model_id,
            "state": "installed",
            "installed": True,
            "message": "Modelo instalado y disponible sin volver a descargarlo.",
            "snapshot_path": str(snapshot),
            "installed_at": record.get("installed_at"),
            "downloaded_bytes": self._downloaded_bytes(model_id),
            "expected_bytes": self._expected_bytes(model_id),
            "error": None,
        }

    def get_state(self, model_id: str) -> dict:
        if model_id not in self.supported_models:
            raise KeyError(model_id)

        with self._lock:
            current = dict(self._states.get(model_id) or {})

        if current.get("state") == "downloading":
            current["downloaded_bytes"] = self._downloaded_bytes(model_id, live=True)
            return current

        snapshot = self.cached_snapshot(model_id)
        if snapshot:
            installed = self._installed_state(model_id, snapshot)
            with self._lock:
                self._states[model_id] = installed
            return dict(installed)

        if current.get("state") == "error":
            return current

        return {
            "model_id": model_id,
            "state": "not_installed",
            "installed": False,
            "message": "Descárgalo una vez para usarlo localmente.",
            "snapshot_path": None,
            "installed_at": None,
            "downloaded_bytes": self._downloaded_bytes(model_id),
            "expected_bytes": self._expected_bytes(model_id),
            "error": None,
        }

    def start(self, model_id: str) -> dict:
        if model_id not in self.supported_models:
            raise KeyError(model_id)

        snapshot = self.cached_snapshot(model_id)
        if snapshot:
            installed = self._installed_state(model_id, snapshot)
            with self._lock:
                self._states[model_id] = installed
            return installed

        # Walking the cache acquires _lock internally: do it before the state lock.
        downloaded_bytes = self._downloaded_bytes(model_id, live=True)
        with self._lock:
            current = self._states.get(model_id)
            if current and current.get("state") == "downloading":
                return dict(current)
            if self._active_model_id and self._active_model_id != model_id:
                raise RuntimeError(
                    "Ya hay otro modelo descargándose. Espera a que termine antes de iniciar uno nuevo."
                )

            state = {
                "model_id": model_id,
                "state": "downloading",
                "installed": False,
                "message": "Descargando archivos desde Hugging Face. Puedes seguir usando la aplicación.",
                "snapshot_path": None,
                "installed_at": None,
                "downloaded_bytes": downloaded_bytes,
                "expected_bytes": self._expected_bytes(model_id),
                "error": None,
            }
            self._states[model_id] = state
            self._active_model_id = model_id

        thread = threading.Thread(
            target=self._install_worker,
            args=(model_id,),
            name=f"model-install-{hashlib.sha256(model_id.encode()).hexdigest()[:8]}",
            daemon=True,
        )
        thread.start()
        return dict(state)

    def _install_worker(self, model_id: str) -> None:
        try:
            snapshot = self._snapshot_download(model_id, local_files_only=False)
            problems = snapshot_problems(snapshot)
            if problems:
                # Hub trusts existing final files. Explicitly replace only the bad
                # dependencies, at the same revision; keep valid GB-sized weights.
                snapshot = self._snapshot_download(
                    model_id, local_files_only=False, revision=snapshot.name,
                    allow_patterns=problems, force_download=True,
                )
                problems = snapshot_problems(snapshot)
                if problems:
                    raise RuntimeError("Archivos incompletos o inválidos: " + ", ".join(problems))
            record = self._write_record(model_id, snapshot)
            # The download just changed what is on disk; drop the memoized size
            # so the finished state reports the real total.
            self._invalidate_size(model_id)
            state = self._installed_state(model_id, snapshot)
            state["installed_at"] = record["installed_at"]
        except Exception as exc:
            self._invalidate_size(model_id)
            detail = f"{type(exc).__name__}: {exc}".strip()
            state = {
                "model_id": model_id,
                "state": "error",
                "installed": False,
                "message": "No se pudo completar o validar la descarga. Revisa la conexión y el espacio libre; pulsa Reintentar para reanudarla.",
                "snapshot_path": None,
                "installed_at": None,
                "downloaded_bytes": self._downloaded_bytes(model_id),
                "expected_bytes": self._expected_bytes(model_id),
                "error": detail[:700],
            }

        with self._lock:
            self._states[model_id] = state
            if self._active_model_id == model_id:
                self._active_model_id = None
