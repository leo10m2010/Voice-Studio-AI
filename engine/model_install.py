from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Optional


Downloader = Callable[..., str]


def model_snapshot_complete(snapshot_path: Path) -> bool:
    """Return True only for a local snapshot that contains config and weights."""
    snapshot = Path(snapshot_path)
    if not snapshot.is_dir() or not (snapshot / "config.json").is_file():
        return False

    weight_patterns = ("*.safetensors", "pytorch_model*.bin")
    return any(
        path.is_file()
        for pattern in weight_patterns
        for path in snapshot.rglob(pattern)
    )


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
        if record.get("model_id") != model_id:
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

    def _snapshot_download(self, model_id: str, *, local_files_only: bool) -> Path:
        downloader = self._downloader
        if downloader is None:
            from huggingface_hub import snapshot_download

            downloader = snapshot_download
        result = downloader(
            repo_id=model_id,
            cache_dir=str(self.cache_dir),
            local_files_only=local_files_only,
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

        repo_cache = self._repo_cache_dir(model_id)
        if repo_cache.exists() and any(repo_cache.rglob("*.incomplete")):
            return None

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

    def _downloaded_bytes(self, model_id: str) -> int:
        root = self._repo_cache_dir(model_id)
        if not root.exists():
            return 0
        total = 0
        for path in root.rglob("*"):
            try:
                if path.is_file():
                    total += path.stat().st_size
            except OSError:
                continue
        return total

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
            current["downloaded_bytes"] = self._downloaded_bytes(model_id)
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
                "downloaded_bytes": self._downloaded_bytes(model_id),
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
            record = self._write_record(model_id, snapshot)
            state = self._installed_state(model_id, snapshot)
            state["installed_at"] = record["installed_at"]
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}".strip()
            state = {
                "model_id": model_id,
                "state": "error",
                "installed": False,
                "message": "No se pudo completar la descarga. Revisa tu conexión y vuelve a intentarlo.",
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
