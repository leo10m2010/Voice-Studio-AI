from __future__ import annotations

import gc
import json
import os
import math
import hashlib
import re
import shutil
import sys
import threading
import time
import traceback
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Literal, Optional
from datetime import datetime, timezone

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from audio_mix import mix_voice_with_music
from audio_ingest import (
    decode_audio_file,
    transcode_music_to_wav,
    validate_canonical_music,
)
from text_normalize import normalize_spanish
from model_install import ModelInstallRegistry

DEFAULT_MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"

# En GPU este modelo va en fp32. Ni fp16 ni bf16 sirven, y ninguna de las dos
# cosas depende de la tarjeta.
#
# fp16 revienta. Los pesos tienen un rango que fp16 no cubre —se corta en
# 65504—, así que las activaciones desbordan a inf, el softmax devuelve NaN y
# torch.multinomial aborta el proceso:
#
#   TensorCompare.cu:109: Assertion `input[0] != 0` failed
#
# que es su comprobación de "probability tensor contains either inf, nan or
# element < 0". Fallaba en el primer muestreo, siempre, tanto en una RTX 4070
# como en un equipo antiguo: nunca llegó a completarse una locución en GPU.
#
# bf16 no revienta, pero degrada. Tiene el rango de fp32 con 8 bits de mantisa,
# y con ese margen el modelo deja de cerrar bien la locución: medido en una
# 4070 con muestreo determinista, la misma frase daba 13.92 s de audio (rms
# 0.032) frente a 4.40 s (rms 0.070) en fp32. fp32 en GPU sí coincide con CPU
# (4.24 s, rms 0.075), que es la referencia buena.
#
# fp32 en GPU sigue mereciendo la pena: 6.5 s para esa frase contra 16.0 s en
# CPU, 2.5x más rápido.
CUDA_COMPUTE_DTYPE = (os.environ.get("QWEN_ENGINE_CUDA_DTYPE") or "float32").lower()

# VRAM mínima para elegir GPU, con margen para el tokenizer 12Hz, la caché KV y
# las activaciones. Medido, no estimado: el 0.6B en fp32 con un guion largo
# llega a 5.29 GB asignados y 5.73 GB reservados en una RTX 4070. Las cifras
# anteriores (2.5 / 5.0) venían de suponer fp16 y se quedaban cortas.
# Quedarse corto tampoco rompe: choose_backend() reintenta en CPU al detectar
# falta de memoria.
VRAM_REQUIRED_GB = {
    "Qwen/Qwen3-TTS-12Hz-0.6B-Base": 6.0,
    "Qwen/Qwen3-TTS-12Hz-1.7B-Base": 11.0,
}
DEFAULT_VRAM_REQUIRED_GB = 6.0

SUPPORTED_MODELS = {
    "Qwen/Qwen3-TTS-12Hz-0.6B-Base": {
        "name": "Qwen3-TTS 0.6B Base",
        "author": "Qwen",
        "family": "Qwen3-TTS",
        "engine": "qwen",
        "recommended": True,
        "disk_gb": 2.52,
        "gpu_vram_recommended_gb": 6.0,
        "description": "Recomendado. Mejor equilibrio para este equipo y clonación local.",
        "license": "apache-2.0",
        "spanish": True,
    },
    "Qwen/Qwen3-TTS-12Hz-1.7B-Base": {
        "name": "Qwen3-TTS 1.7B Base",
        "author": "Qwen",
        "family": "Qwen3-TTS",
        "engine": "qwen",
        "recommended": False,
        "disk_gb": 4.54,
        "gpu_vram_recommended_gb": 11.0,
        "description": "Más pesado. Puede mejorar calidad, pero requiere bastante más memoria.",
        "license": "apache-2.0",
        "spanish": True,
    },
}

PORT = int(os.environ.get("QWEN_ENGINE_PORT", "8765"))

PROJECT_ROOT = Path(
    os.environ.get("QWEN_STUDIO_ROOT") or Path(__file__).resolve().parents[1]
).resolve()

if os.name == "nt":
    local_appdata = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    DATA_ROOT = Path(
        os.environ.get("QWEN_STUDIO_DATA") or local_appdata / "QwenVoiceStudio"
    )
else:
    DATA_ROOT = Path(
        os.environ.get("QWEN_STUDIO_DATA") or Path.home() / ".qwen-voice-studio"
    )

VOICES_DIR = DATA_ROOT / "voices"
SOUNDS_DIR = DATA_ROOT / "sounds"
INVALID_SOUNDS_DIR = DATA_ROOT / "sounds_invalid"
OUTPUTS_DIR = DATA_ROOT / "outputs"
PREPARED_DIR = DATA_ROOT / "prepared_voices"
VOICE_META_DIR = DATA_ROOT / "voice_meta"
HF_HOME = DATA_ROOT / "huggingface"
HISTORY_PATH = DATA_ROOT / "history.json"
SEEDED_SOUNDS_PATH = DATA_ROOT / "seeded_sounds.json"

for directory in (
    VOICES_DIR,
    SOUNDS_DIR,
    INVALID_SOUNDS_DIR,
    OUTPUTS_DIR,
    PREPARED_DIR,
    VOICE_META_DIR,
    HF_HOME,
):
    directory.mkdir(parents=True, exist_ok=True)

os.environ["HF_HOME"] = str(HF_HOME)
os.environ["HUGGINGFACE_HUB_CACHE"] = str(HF_HOME / "hub")

MODEL_INSTALLER = ModelInstallRegistry(HF_HOME, SUPPORTED_MODELS)

ALLOWED_AUDIO = {".wav", ".mp3", ".flac", ".ogg"}
MAX_UPLOAD_MB = 80

# La fidelidad del clon sube casi linealmente de 3 a 15 s, luego se estanca y
# empeora. Pasarse además dispara el cuelgue en el que el modelo no emite el
# token de fin, así que las referencias más largas se recortan.
REFERENCE_MAX_SECONDS = 18.0
REFERENCE_MIN_KEEP_SECONDS = 8.0

# Por encima de ~100 caracteres la velocidad de habla se va acelerando hacia el
# final del fragmento (issue #239 del repo oficial de Qwen3-TTS). Fragmentar a
# 460 dejaba casi cualquier locución dentro de esa zona. 200 mantiene un spot
# típico en un solo fragmento y parte los textos largos antes de que derive.
TTS_CHUNK_CHARS = 200

# Cada entrada retiene los tensores del prompt de una voz. Con una biblioteca
# grande no tiene sentido conservarlas todas.
PROMPT_CACHE_MAX = 8

# Cuánto puede tardar una generación antes de considerarla colgada. Medido a
# ~1.3 s por carácter en el peor CPU probado; este margen es varias veces eso,
# así que solo se dispara cuando de verdad dejó de progresar.
STUCK_SECONDS_PER_CHAR = 8.0
STUCK_MINIMUM_SECONDS = 600.0

app = FastAPI(title="Qwen Voice Studio Local Engine", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "tauri://localhost",
        "http://tauri.localhost",
        "https://tauri.localhost",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def supported_model_payload(model_id: str) -> dict:
    info = dict(SUPPORTED_MODELS[model_id])
    install = MODEL_INSTALLER.get_state(model_id)
    info.update(
        {
            "id": model_id,
            "compatible": True,
            "compatibility_note": "Compatible con el motor Qwen integrado.",
            "hub_url": f"https://huggingface.co/{model_id}",
            "installed": install["installed"],
            "install_state": install["state"],
            "install_message": install["message"],
            "downloaded_bytes": install["downloaded_bytes"],
            "expected_bytes": install["expected_bytes"],
            "install_error": install["error"],
        }
    )
    return info


def safe_filename(name: str) -> str:
    raw = Path(name).name
    stem = re.sub(r"[^A-Za-z0-9À-ÿ _.-]+", "", raw).strip()
    stem = re.sub(r"\s+", "_", stem)
    return stem or f"audio_{uuid.uuid4().hex[:8]}.wav"


def pretty_name(filename: str) -> str:
    return Path(filename).stem.replace("_", " ").replace("-", " ").strip()


def transcript_path(audio_path: Path) -> Path:
    return audio_path.with_suffix(audio_path.suffix + ".txt")


def copy_seed_assets() -> None:
    """
    Seeds the user library from the bundled assets.

    Transcoding the bundled MP3 music is expensive (tens of MB through
    librosa). This MUST NOT run on the import path: until it finishes the
    HTTP port is not open, the desktop shell's health check times out, and
    the user gets an app that loads with no voices, no models and a dead
    Generate button. It is started in the background once uvicorn is
    already accepting requests. See warm_up_library().
    """
    voice_dir = PROJECT_ROOT / "assets" / "voice"
    sound_dir = PROJECT_ROOT / "assets" / "sonidos"

    if voice_dir.exists():
        for source in voice_dir.iterdir():
            if not source.is_file() or source.suffix.lower() not in ALLOWED_AUDIO:
                continue
            target = VOICES_DIR / source.name
            if target.exists():
                continue
            try:
                shutil.copy2(source, target)
                sidecar = transcript_path(source)
                if sidecar.exists():
                    shutil.copy2(sidecar, transcript_path(target))
            except OSError:
                pass

    if not sound_dir.exists():
        return

    # The bundled library ships as MP3 while the mixer and validator expect
    # canonical WAV, so each seed is transcoded once. Which seeds are already
    # done is recorded explicitly instead of being guessed from the resulting
    # file name: transcode_music_to_wav() renames on collision, so a seed could
    # land as "Alegria_2_2.wav" while the guard kept looking for "Alegria_2.wav"
    # — and re-transcoded the same track on every single launch, growing the
    # library (and startup time) without bound.
    seeded = set()
    if SEEDED_SOUNDS_PATH.exists():
        try:
            seeded = set(json.loads(SEEDED_SOUNDS_PATH.read_text(encoding="utf-8")))
        except Exception:
            seeded = set()
    else:
        # First run after the fix: a library seeded by an older build has no
        # marker yet. Recover it from the sidecars each import already writes,
        # so existing users do not get one final round of duplicates.
        for sidecar in SOUNDS_DIR.glob("*.meta.json"):
            try:
                name = json.loads(sidecar.read_text(encoding="utf-8")).get("source_name")
            except Exception:
                continue
            if name:
                seeded.add(name)

    changed = False
    for source in sorted(sound_dir.iterdir()):
        if not source.is_file() or source.suffix.lower() not in ALLOWED_AUDIO:
            continue
        if source.name in seeded:
            continue
        try:
            transcode_music_to_wav(
                source_path=source,
                destination_dir=SOUNDS_DIR,
                original_name=source.name,
                target_sr=44100,
            )
        except Exception as exc:
            # Copying the undecodable original into the library would only add
            # a track the mixer rejects. Skip it and say why.
            print(f"[seed] no se pudo preparar {source.name}: {exc}")
            continue
        seeded.add(source.name)
        changed = True

    if changed:
        SEEDED_SOUNDS_PATH.write_text(
            json.dumps(sorted(seeded), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


class LibraryWarmUp:
    """
    Tracks the one-time background preparation of the local library.

    Reference preparation (resample + trim + analysis) costs a librosa decode
    per voice. Doing it inline inside GET /api/voices made the very first
    refresh block for as long as it took to process every seeded voice. The
    listing now serves whatever is already cached and reports `analyzing`
    for the rest, while this warm-up fills the cache in the background.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: set[str] = set()
        self._seeding = True
        self._started = False

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
        threading.Thread(target=self._run, name="library-warm-up", daemon=True).start()

    def _run(self) -> None:
        try:
            copy_seed_assets()
        except Exception as exc:
            print(f"[warm-up] no se pudieron copiar los recursos incluidos: {exc}")
        finally:
            with self._lock:
                self._seeding = False

        try:
            removed = prune_orphan_outputs()
            if removed:
                print(f"[warm-up] {removed} audio(s) sin referencia eliminados")
        except Exception as exc:
            print(f"[warm-up] no se pudo limpiar outputs: {exc}")

        for path in sorted(VOICES_DIR.iterdir()):
            if not path.is_file() or path.suffix.lower() not in ALLOWED_AUDIO:
                continue
            if self._claim(path):
                self._prepare(path)

        preload_model_if_affordable()

    def _claim(self, audio_path: Path) -> bool:
        """Reserve a voice so two threads never analyze the same file."""
        with self._lock:
            if audio_path.stem in self._pending:
                return False
            self._pending.add(audio_path.stem)
            return True

    def _prepare(self, audio_path: Path) -> None:
        try:
            prepare_reference_audio(audio_path, force=False)
        except Exception as exc:
            print(f"[warm-up] no se pudo preparar {audio_path.name}: {exc}")
        finally:
            with self._lock:
                self._pending.discard(audio_path.stem)

    def schedule(self, audio_path: Path) -> None:
        if not self._claim(audio_path):
            return
        threading.Thread(
            target=self._prepare,
            args=(audio_path,),
            name=f"prepare-{audio_path.stem[:16]}",
            daemon=True,
        ).start()

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._seeding or bool(self._pending)


WARM_UP = LibraryWarmUp()

# Loading the model costs ~34 s on a slow CPU and the clone prompt another ~9 s.
# Paid on the first Generate, that is 43 s of the user staring at a spinner.
# Paid right after startup, it lands while they are still writing the script.
PRELOAD_ENABLED = os.environ.get("QWEN_STUDIO_PRELOAD", "1").lower() not in {
    "0",
    "false",
    "no",
}
# The model needs ~2.5 GB resident. Holding that on a machine that is already
# short on memory would trade a faster first render for a slower everything,
# so the preload only happens when there is comfortable headroom.
PRELOAD_MIN_FREE_GB = 4.0


def available_memory_gb() -> Optional[float]:
    if os.name != "nt":
        try:
            return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 1024**3
        except (ValueError, OSError, AttributeError):
            return None
    import ctypes

    class MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatusEx()
    status.dwLength = ctypes.sizeof(MemoryStatusEx)
    try:
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
    except Exception:
        return None
    return status.ullAvailPhys / 1024**3


def preload_model_if_affordable() -> None:
    """Warms the model so the first generation does not pay for loading it."""
    if not PRELOAD_ENABLED:
        return
    if MODEL_INSTALLER.cached_snapshot(DEFAULT_MODEL_ID) is None:
        return

    free = available_memory_gb()
    if free is not None and free < PRELOAD_MIN_FREE_GB:
        print(f"[preload] omitido: solo {free:.1f} GB de RAM libre")
        return

    try:
        started = time.perf_counter()
        MODEL_MANAGER.load("auto", DEFAULT_MODEL_ID)
        print(f"[preload] modelo listo en {time.perf_counter() - started:.1f} s")
    except Exception as exc:
        # Preloading is an optimization. A failure here must not stop the
        # engine; the real load happens again on the first generation.
        print(f"[preload] no se pudo precargar el modelo: {exc}")


class EngineStatus:
    """
    What the engine is doing right now.

    Generation runs ~11x slower than real time on a CPU, so a 10-second spot is
    a 100-second wait. Reporting only "generando" for that long reads as a
    frozen app. This also carries which chunk is in flight and how long the
    request has been running, so the UI can show honest progress.
    """

    IDLE = {
        "stage": "idle",
        "title": "Motor listo",
        "message": "Esperando una generación.",
        "backend": None,
        "chunk_index": 0,
        "chunk_count": 0,
        "elapsed_seconds": 0.0,
    }

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data = dict(self.IDLE)
        self._started_at: Optional[float] = None

    def start_request(self) -> None:
        with self._lock:
            self._started_at = time.perf_counter()

    def end_request(self) -> None:
        with self._lock:
            self._started_at = None

    def set(
        self,
        stage: str,
        title: str,
        message: str,
        backend: Optional[str] = None,
        chunk_index: int = 0,
        chunk_count: int = 0,
    ) -> None:
        with self._lock:
            self._data = {
                "stage": stage,
                "title": title,
                "message": message,
                "backend": backend,
                "chunk_index": chunk_index,
                "chunk_count": chunk_count,
            }

    def get(self) -> dict:
        with self._lock:
            data = dict(self._data)
            data["elapsed_seconds"] = (
                round(time.perf_counter() - self._started_at, 1)
                if self._started_at is not None
                else 0.0
            )
            return data


STATUS = EngineStatus()


class GenerationCancelled(RuntimeError):
    pass


_CANCEL_LOCK = threading.Lock()
_CANCELLED_REQUESTS: set[str] = set()


def mark_generation_cancelled(request_id: str) -> None:
    with _CANCEL_LOCK:
        _CANCELLED_REQUESTS.add(request_id)


def is_generation_cancelled(request_id: str) -> bool:
    with _CANCEL_LOCK:
        return request_id in _CANCELLED_REQUESTS


def clear_generation_cancelled(request_id: str) -> None:
    with _CANCEL_LOCK:
        _CANCELLED_REQUESTS.discard(request_id)


_CUDA_FAULT_LOCK = threading.Lock()
_CUDA_FAULT_REASON: Optional[str] = None


def cuda_fault_reason() -> Optional[str]:
    with _CUDA_FAULT_LOCK:
        return _CUDA_FAULT_REASON


def disable_cuda(reason: str) -> None:
    """
    Retira la GPU de lo que queda de sesión.

    Un fallo de kernel (device-side assert) no se limita a la llamada que lo
    provocó: corrompe el contexto CUDA del proceso entero, así que a partir de
    ahí *cualquier* operación en GPU falla igual. Reintentar en CUDA no puede
    salir bien, y en el registro se veía exactamente eso: cinco POST
    /api/generate seguidos devolviendo 500 sin que nada cambiara.

    Solo lo cura reemplazar el proceso. Mientras tanto, marcarlo permite seguir
    generando en CPU en vez de dejar la app inservible hasta reiniciarla.
    """
    global _CUDA_FAULT_REASON
    with _CUDA_FAULT_LOCK:
        if _CUDA_FAULT_REASON is None:
            _CUDA_FAULT_REASON = reason
            print(f"[cuda] GPU desactivada para esta sesión: {reason}")


def reset_cuda_fault() -> None:
    global _CUDA_FAULT_REASON
    with _CUDA_FAULT_LOCK:
        _CUDA_FAULT_REASON = None


def is_cuda_fault(exc: BaseException) -> bool:
    """
    Distingue un contexto CUDA roto de una GPU que solo se quedó sin memoria.

    Falta de memoria es recuperable y ya tiene su propio camino: se reintenta en
    CPU sin descartar la GPU, porque un trabajo más corto sí cabría después.
    """
    text = f"{type(exc).__name__}: {exc}".lower()
    if "out of memory" in text:
        return False
    return any(
        marker in text
        for marker in (
            "device-side assert",
            "cuda error",
            "acceleratorerror",
            "cuda kernel errors",
            "cublas",
            "cudnn_status",
            "no kernel image is available",
            "illegal memory access",
        )
    )


def friendly_generation_error(exc: BaseException) -> str:
    """
    Lo que ve el usuario cuando la generación falla.

    El volcado crudo de un fallo CUDA son diez líneas sobre cudaErrorAssert,
    CUDA_LAUNCH_BLOCKING y TORCH_USE_CUDA_DSA: instrucciones para depurar
    PyTorch, no para locutar un spot. Se resume y se dice qué hacer, dejando el
    texto completo en el registro, que es donde sirve.
    """
    raw = f"{type(exc).__name__}: {exc}"
    if is_cuda_fault(exc):
        return (
            "La tarjeta gráfica falló durante la síntesis y quedó inutilizable "
            "hasta reiniciar la app. Vuelve a intentarlo: se generará en CPU, "
            "más lento pero fiable. El detalle técnico está en el registro del "
            "motor."
        )
    if "out of memory" in raw.lower():
        return (
            "La GPU se quedó sin memoria. Cierra otros programas que la usen, "
            "o cambia el modo a CPU en Ajustes."
        )
    return raw


def describe_cuda_fault(exc: BaseException) -> str:
    first_line = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    return f"{type(exc).__name__}: {first_line}" if first_line else type(exc).__name__


def cuda_dtype_name() -> str:
    """
    Nombre del dtype de GPU. fp16 se ignora aunque lo pidan por entorno: es el
    que abortaba el proceso, y dejarlo elegible solo serviría para reproducir
    el fallo. Ver el comentario de CUDA_COMPUTE_DTYPE.
    """
    if CUDA_COMPUTE_DTYPE == "bfloat16":
        return "bfloat16"
    return "float32"


def resolve_cuda_dtype(torch):
    return torch.bfloat16 if cuda_dtype_name() == "bfloat16" else torch.float32


def vram_required_gb(model_id: str) -> float:
    model_info = SUPPORTED_MODELS.get(model_id) or {}
    return float(
        model_info.get("gpu_vram_recommended_gb")
        or VRAM_REQUIRED_GB.get(model_id, DEFAULT_VRAM_REQUIRED_GB)
    )


_GPU_PROBE: Optional[dict] = None


def probe_gpu(torch) -> Optional[dict]:
    """
    Lee nombre, VRAM y capacidad de cómputo una sola vez.

    Se cachea porque no cambian durante la sesión y porque, tras un fallo de
    kernel, volver a preguntárselo a CUDA lanza excepción: sin la copia, el
    diagnóstico pasaría a decir "sin NVIDIA detectada" justo cuando más falta
    hace saber qué tarjeta es.
    """
    global _GPU_PROBE
    if _GPU_PROBE is not None:
        return _GPU_PROBE
    try:
        properties = torch.cuda.get_device_properties(0)
        major, minor = torch.cuda.get_device_capability(0)
        _GPU_PROBE = {
            "gpu_name": torch.cuda.get_device_name(0),
            "vram_gb": round(properties.total_memory / (1024**3), 2),
            "capability": (int(major), int(minor)),
        }
    except Exception:
        return None
    return _GPU_PROBE


def torch_info() -> dict:
    try:
        import torch

        fault = cuda_fault_reason()
        present = bool(torch.cuda.is_available())
        result = {
            "python_ready": True,
            "python_error": None,
            "torch_version": torch.__version__,
            "cuda_available": present,
            # La GPU existe pero está descartada tras un fallo de kernel.
            "cuda_usable": present and fault is None,
            "cuda_disabled_reason": fault,
            "cuda_version": getattr(torch.version, "cuda", None),
            "gpu_name": None,
            "vram_gb": None,
            "compute_capability": None,
            "compute_dtype": None,
            "recommended_mode": "cpu",
        }

        probe = probe_gpu(torch) if present else None
        if probe:
            capability = probe["capability"]
            fits = probe["vram_gb"] >= vram_required_gb(DEFAULT_MODEL_ID)
            result.update(
                {
                    "gpu_name": probe["gpu_name"],
                    "vram_gb": probe["vram_gb"],
                    "compute_capability": f"{capability[0]}.{capability[1]}",
                    "compute_dtype": cuda_dtype_name(),
                    "recommended_mode": (
                        "cuda" if fits and fault is None else "cpu"
                    ),
                }
            )
        return result
    except Exception as exc:
        return {
            "python_ready": False,
            "python_error": f"{type(exc).__name__}: {exc}",
            "torch_version": None,
            "cuda_available": False,
            "cuda_usable": False,
            "cuda_disabled_reason": None,
            "cuda_version": None,
            "gpu_name": None,
            "vram_gb": None,
            "compute_capability": None,
            "compute_dtype": None,
            "recommended_mode": "cpu",
        }



_THREADS_TUNED = False


def tune_cpu_threads() -> None:
    """
    Pins torch to physical cores.

    Transformer decode is memory-bandwidth bound, so the extra logical cores of
    hyperthreading mostly add contention. Frozen builds can also misdetect the
    topology entirely, which is worse. Setting it once, explicitly, avoids both.
    """
    global _THREADS_TUNED
    if _THREADS_TUNED:
        return
    _THREADS_TUNED = True

    try:
        import torch

        physical = os.cpu_count() or 1
        if os.name == "nt":
            try:
                import subprocess

                output = subprocess.run(
                    ["wmic", "cpu", "get", "NumberOfCores"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                cores = [
                    int(line)
                    for line in output.stdout.split()
                    if line.strip().isdigit()
                ]
                if cores:
                    physical = sum(cores)
            except Exception:
                pass

        threads = max(1, min(physical, os.cpu_count() or 1))
        torch.set_num_threads(threads)
        print(f"[torch] hilos fijados a {threads} (núcleos físicos detectados)")
    except Exception as exc:
        print(f"[torch] no se pudo ajustar los hilos: {exc}")


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def qwen_sampling_from_friendly_controls(
    stability: float,
    style_exaggeration: float,
    profile: str,
) -> dict:
    """
    Qwen Base exposes sampling controls, not ElevenLabs-style similarity/style
    controls. We keep a familiar UI but map only what Qwen actually supports.

    Research-informed profiles:
    - faithful: deterministic cloning for consistency (do_sample=False)
    - natural: close to Qwen/ElevenLabs neutral defaults
    - spot: modestly more variable delivery, not extreme style exaggeration
    """
    s = clamp(stability, 0.0, 1.0)
    style = clamp(style_exaggeration, 0.0, 1.0)

    if profile == "faithful":
        return {
            "do_sample": False,
            "subtalker_dosample": False,
            "temperature": 0.70,
            "top_p": 0.92,
            "top_k": 40,
            "repetition_penalty": 1.08,
            "subtalker_temperature": 0.70,
            "subtalker_top_p": 0.92,
            "subtalker_top_k": 40,
        }

    # Higher stability = lower randomness.
    temperature = 1.12 - 0.42 * s
    subtalker_temperature = 1.10 - 0.40 * s
    top_p = 1.00 - 0.08 * s
    top_k = round(64 - 22 * s)

    # Style stays deliberately conservative. ElevenLabs itself recommends
    # style=0 for many cloned-voice use cases because high style can destabilize.
    temperature += 0.16 * style
    subtalker_temperature += 0.15 * style
    top_k += round(10 * style)
    top_p += 0.02 * style

    if profile == "spot":
        temperature += 0.05
        subtalker_temperature += 0.05

    return {
        "do_sample": True,
        "subtalker_dosample": True,
        "temperature": round(clamp(temperature, 0.50, 1.15), 3),
        "top_p": round(clamp(top_p, 0.82, 1.0), 3),
        "top_k": int(clamp(top_k, 25, 80)),
        "repetition_penalty": round(1.05 + 0.035 * s, 3),
        "subtalker_temperature": round(
            clamp(subtalker_temperature, 0.50, 1.15), 3
        ),
        "subtalker_top_p": round(clamp(top_p, 0.82, 1.0), 3),
        "subtalker_top_k": int(clamp(top_k, 25, 80)),
    }


def apply_audio_postprocessing(
    wav,
    sample_rate: int,
    speed: float,
    pitch_semitones: float,
    speaker_boost: bool,
):
    """
    Speed/pitch are not native low-level controls of generate_voice_clone().
    We apply them locally after synthesis.

    librosa time_stretch changes tempo while approximately preserving pitch.
    librosa pitch_shift changes pitch while approximately preserving duration.
    """
    import numpy as np
    import librosa

    y = np.asarray(wav, dtype=np.float32).squeeze()

    if y.ndim != 1:
        y = np.mean(y, axis=-1).astype(np.float32)

    rate = clamp(speed, 0.70, 1.35)
    if abs(rate - 1.0) > 0.015:
        y = librosa.effects.time_stretch(y, rate=rate).astype(np.float32)

    semitones = clamp(pitch_semitones, -4.0, 4.0)
    if abs(semitones) > 0.05:
        y = librosa.effects.pitch_shift(
            y=y,
            sr=sample_rate,
            n_steps=semitones,
        ).astype(np.float32)

    if speaker_boost and y.size:
        # Mild local presence boost: RMS normalization + soft limiting.
        rms = float(np.sqrt(np.mean(np.square(y)) + 1e-9))
        target_rms = 10 ** (-18.0 / 20.0)
        if rms > 1e-6:
            gain = min(target_rms / rms, 2.0)
            y = y * gain

        y = np.tanh(y * 1.12) / np.tanh(1.12)

    if y.size:
        peak = float(np.max(np.abs(y)))
        if peak > 0.98:
            y = y * (0.98 / peak)

    return y.astype(np.float32)



def voice_meta_path(audio_path: Path) -> Path:
    return VOICE_META_DIR / f"{audio_path.stem}.json"


def prepared_voice_path(audio_path: Path) -> Path:
    return PREPARED_DIR / f"{audio_path.stem}.wav"


# Se sube cuando cambia cómo se analiza o se prepara una referencia, para que
# las voces ya importadas se vuelvan a medir en vez de servir un veredicto
# obsoleto. La 2 corrige la puntuación que daba "Excelente" a transcripciones
# que no corresponden al audio usado.
REFERENCE_ANALYSIS_VERSION = 2


def reference_cache_signature(audio_path: Path, transcript: str) -> str:
    stat = audio_path.stat()
    digest = hashlib.sha1(transcript.encode("utf-8")).hexdigest()[:12]
    return f"v{REFERENCE_ANALYSIS_VERSION}:{stat.st_mtime_ns}:{stat.st_size}:{digest}"


def analyze_reference_audio(audio_path: Path, transcript: str = "") -> dict:
    """
    Practical reference-quality analysis. This is NOT a speaker-similarity score.
    It reports properties known to matter for cloning: duration, level, clipping,
    and whether exact transcript/ICL conditioning is available.
    """
    import numpy as np
    import soundfile as sf

    try:
        info = sf.info(str(audio_path))
        duration = float(info.duration)
        sample_rate = int(info.samplerate)
        channels = int(info.channels)

        # Read enough data to evaluate level/clipping. References are expected
        # to be short; always_float avoids integer-format ambiguity.
        y, sr = sf.read(str(audio_path), always_2d=True, dtype="float32")
        mono = np.mean(y, axis=1) if y.size else np.zeros(1, dtype=np.float32)

        rms = float(np.sqrt(np.mean(np.square(mono)) + 1e-12))
        peak = float(np.max(np.abs(mono))) if mono.size else 0.0
        rms_dbfs = 20.0 * math.log10(max(rms, 1e-8))
        peak_dbfs = 20.0 * math.log10(max(peak, 1e-8))
        clipping_ratio = float(np.mean(np.abs(mono) >= 0.995)) if mono.size else 0.0

        score = 0
        notes = []

        # La calidad sube de forma casi lineal de 3 a 15 s, ahí se estanca y
        # después empeora; además una referencia larga es uno de los
        # disparadores del cuelgue sin token de fin. Por eso el óptimo es
        # 10–15 s y no "cuanto más, mejor".
        if 10.0 <= duration <= 15.0:
            score += 30
        elif 8.0 <= duration < 10.0 or 15.0 < duration <= 20.0:
            score += 26
        elif 5.0 <= duration < 8.0 or 20.0 < duration <= REFERENCE_MAX_SECONDS:
            score += 20
            notes.append("Duración utilizable; 10–15 s es donde el clon sale mejor.")
        elif 3.0 <= duration < 5.0:
            score += 12
            notes.append("Qwen clona desde ~3 s, pero con 10–15 s el resultado es bastante más estable.")
        elif duration < 3.0:
            score += 5
            notes.append("Referencia muy corta: usa al menos 3 s, idealmente 10–15 s.")
        else:
            score += 10
            notes.append(
                f"Referencia larga: se recortará a {REFERENCE_MAX_SECONDS:.0f} s. "
                "Pasados los 15 s la calidad deja de subir y puede empeorar."
            )

        if -28.0 <= rms_dbfs <= -12.0:
            score += 20
        elif -34.0 <= rms_dbfs <= -8.0:
            score += 13
            notes.append("El nivel es aceptable, pero puede normalizarse mejor.")
        else:
            score += 5
            notes.append("El audio está demasiado bajo o demasiado fuerte.")

        if clipping_ratio < 0.001:
            score += 15
        elif clipping_ratio < 0.01:
            score += 7
            notes.append("Hay algo de saturación/clipping.")
        else:
            notes.append("Hay clipping notable; usa una grabación más limpia.")

        # Puntuar por "tiene transcripción" mentía: una que no corresponde al
        # audio no suma fidelidad, la destruye. La voz de 73 s recortada a 18 s
        # con su transcripción entera salía "Excelente 96" y era inservible.
        usable, motivo = usable_icl_transcript(transcript, duration)
        if usable:
            score += 35
        elif transcript.strip():
            notes.append(
                f"{motivo} Para usar ICL, recorta el audio a {REFERENCE_MAX_SECONDS:.0f} s "
                "o menos y pega la transcripción de ese tramo."
            )
        else:
            notes.append("Falta transcripción exacta: se usará X-vector y la fidelidad puede bajar.")

        score = int(clamp(score, 0, 100))
        if score >= 88:
            label = "Excelente"
        elif score >= 72:
            label = "Buena"
        elif score >= 55:
            label = "Mejorable"
        else:
            label = "Baja"

        return {
            "duration": round(duration, 2),
            "sample_rate": sample_rate,
            "channels": channels,
            "rms_dbfs": round(rms_dbfs, 1),
            "peak_dbfs": round(peak_dbfs, 1),
            "clipping_ratio": round(clipping_ratio, 5),
            "quality_score": score,
            "quality_label": label,
            "notes": notes,
            "has_transcript": bool(transcript.strip()),
            "transcript_usable": bool(usable),
        }
    except Exception as exc:
        return {
            "duration": None,
            "sample_rate": None,
            "channels": None,
            "rms_dbfs": None,
            "peak_dbfs": None,
            "clipping_ratio": None,
            "quality_score": 0,
            "quality_label": "Sin analizar",
            "notes": [f"No se pudo analizar: {type(exc).__name__}"],
            "has_transcript": bool(transcript.strip()),
            "transcript_usable": False,
        }


def reference_offset_path(audio_path: Path) -> Path:
    return VOICE_META_DIR / f"{audio_path.stem}.offset"


def read_reference_offset(audio_path: Path) -> float:
    """Segundo desde el que empieza el tramo elegido por el usuario."""
    ruta = reference_offset_path(audio_path)
    if not ruta.exists():
        return 0.0
    try:
        return max(0.0, float(ruta.read_text(encoding="utf-8").strip()))
    except (OSError, ValueError):
        return 0.0


def write_reference_offset(audio_path: Path, seconds: float) -> None:
    ruta = reference_offset_path(audio_path)
    if seconds and seconds > 0:
        ruta.write_text(f"{float(seconds):.3f}", encoding="utf-8")
    else:
        ruta.unlink(missing_ok=True)


def limit_reference_length(y, sample_rate: int, offset_seconds: float = 0.0):
    """
    Acorta una referencia demasiado larga cortando en un silencio.

    La fidelidad del clon sube casi linealmente hasta ~15 s, ahí se estanca y
    después empeora; y una referencia larga es además uno de los disparadores
    del cuelgue en el que el modelo nunca emite el token de fin. Cortar en
    seco a mitad de palabra dejaría un final abrupto que el clon imita, así
    que se busca el último silencio antes del límite.
    """
    import librosa
    import numpy as np

    # Tramo elegido a mano: se descarta lo anterior y se recorta desde ahí.
    inicio = int(max(0.0, offset_seconds) * sample_rate)
    if inicio and inicio < y.size - int(REFERENCE_MIN_KEEP_SECONDS * sample_rate):
        y = np.ascontiguousarray(y[inicio:])

    limite = int(REFERENCE_MAX_SECONDS * sample_rate)
    if y.size <= limite:
        return y

    minimo = int(REFERENCE_MIN_KEEP_SECONDS * sample_rate)
    try:
        tramos = librosa.effects.split(y[:limite], top_db=35)
    except Exception:
        tramos = []

    for inicio, fin in reversed(list(tramos)):
        if fin >= minimo:
            return np.ascontiguousarray(y[:fin])

    return np.ascontiguousarray(y[:limite])


def prepare_reference_audio(audio_path: Path, force: bool = False) -> tuple[Path, dict]:
    """
    Creates a conservative 24 kHz mono reference:
    - resample to 24 kHz
    - trim only leading/trailing silence
    - remove DC offset
    - normalize RMS toward -20 dBFS with limited gain
    - gentle peak protection

    No denoising/EQ is applied because aggressive processing can change timbre.
    """
    import numpy as np
    import librosa
    import soundfile as sf

    transcript = ""
    sidecar = transcript_path(audio_path)
    if sidecar.exists():
        transcript = sidecar.read_text(encoding="utf-8", errors="ignore").strip()

    out = prepared_voice_path(audio_path)
    meta_file = voice_meta_path(audio_path)
    signature = reference_cache_signature(audio_path, transcript)

    if not force and out.exists() and meta_file.exists():
        try:
            cached = json.loads(meta_file.read_text(encoding="utf-8"))
            if cached.get("signature") == signature:
                return out, cached
        except Exception:
            pass

    y, _ = librosa.load(str(audio_path), sr=24000, mono=True)
    y = y.astype(np.float32)

    if y.size:
        y, _ = librosa.effects.trim(y, top_db=35)
    if not y.size:
        y = np.zeros(2400, dtype=np.float32)

    y = limit_reference_length(y, 24000, read_reference_offset(audio_path))

    y = y - float(np.mean(y))
    rms = float(np.sqrt(np.mean(np.square(y)) + 1e-12))
    target_rms = 10 ** (-20.0 / 20.0)
    if rms > 1e-6:
        gain = min(target_rms / rms, 10 ** (12.0 / 20.0))
        y = y * gain

    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak > 0.98:
        y = y * (0.98 / peak)

    sf.write(str(out), y, 24000, subtype="PCM_16")

    original = analyze_reference_audio(audio_path, transcript)
    prepared = analyze_reference_audio(out, transcript)
    metadata = {
        "signature": signature,
        "source": str(audio_path),
        "prepared": str(out),
        "original": original,
        "prepared_analysis": prepared,
        "quality_score": prepared["quality_score"],
        "quality_label": prepared["quality_label"],
        "notes": prepared["notes"],
        "has_transcript": bool(transcript),
        "transcript": transcript,
        "recommended_seconds": "8–25",
        "official_minimum_note": "Qwen anuncia clonación rápida desde ~3 segundos.",
    }
    meta_file.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out, metadata


def cached_reference_info(audio_path: Path) -> Optional[dict]:
    """Return the stored analysis only when it is still valid — never decode."""
    transcript = ""
    sidecar = transcript_path(audio_path)
    if sidecar.exists():
        transcript = sidecar.read_text(encoding="utf-8", errors="ignore").strip()

    meta_file = voice_meta_path(audio_path)
    if not meta_file.exists() or not prepared_voice_path(audio_path).exists():
        return None

    try:
        cached = json.loads(meta_file.read_text(encoding="utf-8"))
        if cached.get("signature") == reference_cache_signature(audio_path, transcript):
            return cached
    except Exception:
        pass
    return None


def get_voice_reference_info(audio_path: Path) -> dict:
    """
    Listing-safe reference info.

    Only cached results are returned. A cache miss schedules the analysis in
    the background and reports it as pending, so listing the library never
    costs a librosa decode per voice.
    """
    cached = cached_reference_info(audio_path)
    if cached is not None:
        return cached

    WARM_UP.schedule(audio_path)
    transcript = ""
    sidecar = transcript_path(audio_path)
    if sidecar.exists():
        transcript = sidecar.read_text(encoding="utf-8", errors="ignore").strip()

    return {
        "analyzing": True,
        "quality_score": 0,
        "quality_label": "Analizando…",
        "notes": ["Analizando la referencia en segundo plano."],
        "original": {},
        "prepared_analysis": {},
        "has_transcript": bool(transcript),
        "transcript": transcript,
    }


_SPEAKABLE = re.compile(
    r"[0-9A-Za-zÀ-ÿĀ-ſ"          # latino, con acentos y extendido
    r"\s"
    r".,;:!?¡¿'\"()\[\]{}«»…\-–—/%+&@#*°º ª$€£]"
)


def sanitize_script(text: str) -> tuple[str, list[str]]:
    """
    Deja solo caracteres que el modelo puede pronunciar en español.

    generate_voice_clone() se cuelga indefinidamente con entradas de escritura
    mezclada (issue #318 del repo oficial), y un emoji o un ideograma pegado
    por accidente basta para provocarlo. Como retener el lock para siempre
    inutiliza el motor entero, es mejor no llegar a esa llamada: se retiran
    esos caracteres y se informa de cuáles eran.
    """
    kept = []
    removed: list[str] = []
    for char in text:
        if _SPEAKABLE.match(char):
            kept.append(char)
        elif char.isspace():
            kept.append(" ")
        elif char not in removed:
            removed.append(char)
    return "".join(kept), removed


def split_text_for_tts(text: str, max_chars: int = TTS_CHUNK_CHARS) -> list[str]:
    text = re.sub(r"\s+", " ", text.strip())
    if max_chars < 1:
        raise ValueError("max_chars debe ser mayor que cero.")
    if len(text) <= max_chars:
        return [text]

    sentences = re.split(r"(?<=[.!?¡¿;:])\s+", text)
    chunks = []
    current = ""

    def split_long_sentence(sentence: str) -> list[str]:
        words = sentence.split()
        parts = []
        part = ""
        for word in words:
            # A URL or an unusually long token must not make the generated
            # request exceed the model's chunk limit.
            if len(word) > max_chars:
                if part:
                    parts.append(part)
                    part = ""
                parts.extend(
                    word[start : start + max_chars]
                    for start in range(0, len(word), max_chars)
                )
                continue

            candidate = f"{part} {word}".strip()
            if part and len(candidate) > max_chars:
                parts.append(part)
                part = word
            else:
                part = candidate
        if part:
            parts.append(part)
        return parts or [sentence[:max_chars]]

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if len(sentence) > max_chars:
            parts = split_long_sentence(sentence)
        else:
            parts = [sentence]

        for part in parts:
            candidate = f"{current} {part}".strip()
            if current and len(candidate) > max_chars:
                chunks.append(current)
                current = part
            else:
                current = candidate

    if current:
        chunks.append(current)
    return chunks or [text]


# ICL (usar la transcripción de la referencia) solo funciona si ese texto es lo
# que de verdad se oye en el audio preparado. Con cualquier desajuste el modelo
# deja de emitir el token de fin y agota max_new_tokens: devuelve una locución
# larguísima que no dice el guion. Medido en una RTX 4070, guion de 48
# caracteres que debería durar 3.5 s, referencia de 13.7 s:
#
#   texto exacto (202 car, 14.7 car/s) ->  3.92 s   1.12x   correcto
#   sin texto (x-vector)               ->  3.68 s   1.05x   correcto
#   texto de más (326 car, 23.8 car/s) -> 10.48 s   2.99x   mal
#   texto de menos (68 car, 5.0 car/s) -> 30.64 s   8.75x   inservible
#   texto x4 (1307 car, 95.4 car/s)    -> 30.64 s   8.75x   inservible
#
# Una transcripción equivocada es mucho peor que ninguna, así que ante la duda
# se descarta y se clona solo con la huella de voz.
#
# El disparador real en producción: una referencia larga se recorta a 18 s pero
# la transcripción pegada describe el audio entero. Una voz de 73 s con su
# transcripción completa da 53.9 car/s y cae de lleno en el último caso.
ICL_CHARS_PER_SECOND = 14.0
ICL_RATIO_MIN = 0.55
ICL_RATIO_MAX = 1.60


def usable_icl_transcript(
    transcript: Optional[str], prepared_seconds: float
) -> tuple[str, Optional[str]]:
    """
    Decide si la transcripción describe el audio que se va a usar.

    Devuelve (texto_a_usar, motivo_del_descarte). El texto vacío significa
    clonar solo con la huella de voz, que siempre funciona.
    """
    texto = (transcript or "").strip()
    if not texto:
        return "", None
    if prepared_seconds <= 0:
        return "", "No se pudo medir la referencia."

    esperados = prepared_seconds * ICL_CHARS_PER_SECOND
    proporcion = len(texto) / esperados

    if proporcion > ICL_RATIO_MAX:
        return "", (
            f"La transcripción ({len(texto)} caracteres) describe mucho más de "
            f"lo que dura la referencia usada ({prepared_seconds:.0f} s). "
            "Se clonó solo con la huella de voz."
        )
    if proporcion < ICL_RATIO_MIN:
        return "", (
            f"La transcripción ({len(texto)} caracteres) describe mucho menos "
            f"de lo que dura la referencia usada ({prepared_seconds:.0f} s). "
            "Se clonó solo con la huella de voz."
        )
    return texto, None


def estimate_max_new_tokens(text: str) -> int:
    words = max(1, len(re.findall(r"\b\w+\b", text, flags=re.UNICODE)))
    # 12 Hz audio tokenizer. Rough margin based on normal Spanish speech rates.
    return int(clamp(words * 6 + 160, 384, 2048))


AUDIO_MEDIA_TYPES = {
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".mp3": "audio/mpeg",
}

# MP3 lo escribe libsndfile desde la 1.1, así que no añade dependencias ni
# engorda el instalador. Es el formato que piden las emisoras y el que cabe en
# WhatsApp: un spot de 10 s pasa de ~470 KB en WAV a ~40 KB.
_SOUNDFILE_FORMATS = {"wav": "WAV", "flac": "FLAC", "mp3": "MP3"}


def resample_output(samples, sample_rate: int, target_rate: int):
    """
    Lleva el resultado a otra frecuencia de muestreo.

    El modelo entrega 24 kHz, pero las emisoras suelen pedir 44.1 kHz. Subir
    la frecuencia no añade información; solo evita que el archivo se rechace
    o lo reconvierta un equipo peor.
    """
    if not target_rate or target_rate == sample_rate:
        return samples, sample_rate

    import librosa
    import numpy as np

    audio = np.asarray(samples, dtype=np.float32)
    if audio.ndim == 1:
        convertido = librosa.resample(audio, orig_sr=sample_rate, target_sr=target_rate)
    else:
        canales = [
            librosa.resample(
                np.ascontiguousarray(audio[:, canal]),
                orig_sr=sample_rate,
                target_sr=target_rate,
            )
            for canal in range(audio.shape[1])
        ]
        minimo = min(len(canal) for canal in canales)
        convertido = np.stack([canal[:minimo] for canal in canales], axis=1)

    return convertido.astype(np.float32), target_rate


def write_audio(path: Path, samples, sample_rate: int, extension: str) -> None:
    """Escribe el resultado en el formato pedido, con WAV como respaldo."""
    import soundfile as sf

    fmt = _SOUNDFILE_FORMATS.get(extension.lower())
    if fmt is None or fmt not in sf.available_formats():
        fmt = "WAV"
    sf.write(str(path), samples, sample_rate, format=fmt)


def load_history() -> list[dict]:
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_history(items: list[dict]) -> None:
    HISTORY_PATH.write_text(
        json.dumps(items[:150], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def add_history_item(item: dict) -> None:
    items = load_history()
    items.insert(0, item)
    save_history(items)
    # save_history() keeps only the newest 150 entries, so older renders stop
    # being reachable at that point. Drop their files too.
    prune_orphan_outputs(items[:150])


def prune_orphan_outputs(items: Optional[list[dict]] = None) -> int:
    """
    Deletes renders no history entry points at any more.

    Every generation and every music change writes a new file, and clearing the
    history used to leave all of them behind, so `outputs/` grew forever.
    """
    if items is None:
        items = load_history()

    referenced = set()
    for item in items:
        for key in ("filename", "dry_filename"):
            name = item.get(key)
            if name:
                referenced.add(str(name))

    removed = 0
    for path in OUTPUTS_DIR.iterdir():
        if not path.is_file() or path.name in referenced:
            continue
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


class ModelManager:
    def __init__(self) -> None:
        self.model = None
        self.backend: Optional[str] = None
        self.model_id: Optional[str] = None
        self.load_lock = threading.Lock()
        self.generate_lock = threading.Lock()
        # LRU acotada: cada entrada retiene tensores de una voz y antes solo se
        # vaciaba al descargar el modelo, así que con una biblioteca grande la
        # memoria crecía sin techo a lo largo de la sesión.
        self.prompt_cache: OrderedDict[str, object] = OrderedDict()
        # Instante en que empezó la generación en curso, para poder distinguir
        # "va lenta" de "se colgó" (ver stuck_seconds).
        self._active_since: Optional[float] = None
        self._active_budget: float = 0.0
        self._active_lock = threading.Lock()

    def begin_generation(self, budget_seconds: float) -> None:
        with self._active_lock:
            self._active_since = time.monotonic()
            self._active_budget = budget_seconds

    def end_generation(self) -> None:
        with self._active_lock:
            self._active_since = None
            self._active_budget = 0.0

    def stuck_seconds(self) -> float:
        """
        Segundos que la generación en curso lleva pasada de su presupuesto.

        generate_voice_clone() puede quedarse colgado con ciertas entradas
        (issue #318 del repo oficial). Cuando eso pasa retiene generate_lock
        para siempre: el motor sigue respondiendo /api/health pero ninguna
        generación posterior vuelve a completarse nunca. No se puede abortar
        esa llamada desde Python, pero sí detectarla y decirlo.
        """
        with self._active_lock:
            if self._active_since is None or self._active_budget <= 0:
                return 0.0
            over = time.monotonic() - self._active_since - self._active_budget
            return max(0.0, over)

    def unload(self) -> None:
        self.model = None
        self.backend = None
        self.model_id = None
        self.prompt_cache.clear()
        gc.collect()
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

    def choose_backend(self, requested: str, model_id: str) -> str:
        if requested == "cpu":
            return "cpu"

        fault = cuda_fault_reason()
        if fault:
            if requested == "cuda":
                raise RuntimeError(
                    "La GPU quedó fuera de servicio en esta sesión "
                    f"({fault}). Reinicia la app para volver a usarla, o "
                    "genera en modo CPU."
                )
            return "cpu"

        info = torch_info()
        if requested == "cuda":
            if not info.get("cuda_available"):
                raise RuntimeError("CUDA no está disponible en este equipo.")
            return "cuda"

        required = vram_required_gb(model_id)
        available = float(info.get("vram_gb") or 0.0)
        if info.get("cuda_available") and available >= required:
            return "cuda"
        return "cpu"

    def load(self, requested: str, model_id: str):
        if model_id not in SUPPORTED_MODELS:
            raise RuntimeError(
                "Este modelo aparece en Hugging Face, pero todavía no tiene "
                "un adaptador ejecutable en Voice Studio AI."
            )

        snapshot = MODEL_INSTALLER.cached_snapshot(model_id)
        if snapshot is None:
            raise RuntimeError(
                "El modelo seleccionado no está instalado. Abre Modelos y pulsa "
                "'Instalar modelo' antes de generar."
            )

        with self.load_lock:
            target = self.choose_backend(requested, model_id)

            if (
                self.model is not None
                and self.backend == target
                and self.model_id == model_id
            ):
                return self.model, target

            self.unload()
            info = SUPPORTED_MODELS[model_id]
            STATUS.set(
                "loading_model",
                f"Cargando {info['name']}",
                (
                    f"La primera vez descargará aproximadamente {info['disk_gb']} GB. "
                    "Después el modelo queda guardado en este equipo."
                ),
                target,
            )

            import torch
            from qwen_tts import Qwen3TTSModel

            tune_cpu_threads()

            if target == "cuda":
                dtype = resolve_cuda_dtype(torch)
                device_map = "cuda:0"
                print(f"[torch] GPU en {cuda_dtype_name()}")
            else:
                dtype = torch.float32
                device_map = "cpu"

            try:
                model = Qwen3TTSModel.from_pretrained(
                    str(snapshot),
                    device_map=device_map,
                    dtype=dtype,
                    attn_implementation="sdpa",
                    low_cpu_mem_usage=True,
                )
            except Exception:
                self.unload()
                raise

            self.model = model
            self.backend = target
            self.model_id = model_id
            return model, target

    def invalidate_voice(self, voice_id: str) -> None:
        for key in list(self.prompt_cache):
            if f"|{voice_id}|" in key:
                self.prompt_cache.pop(key, None)

    def get_clone_prompt(
        self,
        model,
        voice_path: Path,
        ref_text: Optional[str],
        backend: str,
    ):
        prepared_path, metadata = prepare_reference_audio(voice_path)
        duracion = float(
            (metadata.get("prepared_analysis") or {}).get("duration") or 0.0
        )
        transcript, icl_rechazo = usable_icl_transcript(ref_text, duracion)

        signature = metadata.get("signature", "")
        # El modo va en la clave: dos prompts del mismo audio, uno ICL y otro
        # solo x-vector, son objetos distintos. Sin esto, generar con
        # transcripción y luego sin ella devolvía el prompt ICL cacheado.
        modo = f"icl:{hashlib.sha1(transcript.encode()).hexdigest()[:12]}" if transcript else "xvec"
        key = f"{self.model_id}|{backend}|{voice_path.stem}|{signature}|{modo}"

        if key in self.prompt_cache:
            self.prompt_cache.move_to_end(key)
            return self.prompt_cache[key], prepared_path, icl_rechazo

        prompt = model.create_voice_clone_prompt(
            ref_audio=str(prepared_path),
            ref_text=transcript or None,
            x_vector_only_mode=not bool(transcript),
        )
        self.prompt_cache[key] = prompt
        while len(self.prompt_cache) > PROMPT_CACHE_MAX:
            self.prompt_cache.popitem(last=False)
        return prompt, prepared_path, icl_rechazo

    def generate(
        self,
        text: str,
        voice_path: Path,
        ref_text: Optional[str],
        language: str,
        requested_mode: str,
        generation: dict,
        model_id: str,
        request_id: str = "",
    ):
        with self.generate_lock:
            target = self.choose_backend(requested_mode, model_id)

            try:
                return self._generate_once(
                    text, voice_path, ref_text, language, target, generation, model_id, request_id
                )
            except GenerationCancelled:
                raise
            except Exception as first_error:
                is_auto_cuda = requested_mode == "auto" and target == "cuda"
                is_oom = "out of memory" in str(first_error).lower()

                if target == "cuda" and is_cuda_fault(first_error):
                    # El contexto CUDA ya no sirve para nada en este proceso
                    # (ver disable_cuda), así que se descarta la GPU y se
                    # termina el trabajo en CPU en vez de devolver un 500 que
                    # se repetiría idéntico en cada reintento del usuario.
                    disable_cuda(describe_cuda_fault(first_error))
                    STATUS.set(
                        "loading_model",
                        "Cambiando a CPU",
                        "La GPU falló durante la síntesis. Terminando en modo compatible.",
                        "cpu",
                    )
                    self.unload()
                    return self._generate_once(
                        text, voice_path, ref_text, language, "cpu", generation, model_id, request_id
                    )

                if is_auto_cuda and is_oom:
                    STATUS.set(
                        "loading_model",
                        "Cambiando a CPU",
                        "La GPU se quedó sin memoria. Reintentando en modo compatible.",
                        "cpu",
                    )
                    self.unload()
                    return self._generate_once(
                        text, voice_path, ref_text, language, "cpu", generation, model_id, request_id
                    )

                # Cualquier otro fallo pudo dejar el modelo a medias. Se
                # descarta para que la petición siguiente parta de una carga
                # limpia en vez de reutilizar un modelo dudoso y fallar igual
                # para siempre.
                self.unload()
                raise

    def _generate_once(
        self,
        text: str,
        voice_path: Path,
        ref_text: Optional[str],
        language: str,
        backend: str,
        generation: dict,
        model_id: str,
        request_id: str = "",
    ):
        model, actual_backend = self.load(backend, model_id)

        STATUS.set(
            "preparing_voice",
            "Preparando referencia",
            (
                "Usando transcripción para máxima fidelidad."
                if ref_text
                else "Usando huella de voz sin transcripción."
            ),
            actual_backend,
        )

        effective_language = None if language == "Auto" else language

        prompt, prepared_path, icl_rechazo = self.get_clone_prompt(
            model=model,
            voice_path=voice_path,
            ref_text=ref_text,
            backend=actual_backend,
        )
        if icl_rechazo:
            print(f"[icl] transcripción descartada: {icl_rechazo}")

        chunks = split_text_for_tts(text)
        outputs = []
        sample_rate = None

        for index, chunk in enumerate(chunks, start=1):
            if request_id and is_generation_cancelled(request_id):
                raise GenerationCancelled("Generación cancelada por el usuario.")

            STATUS.set(
                "generating",
                f"Generando locución {index}/{len(chunks)}",
                (
                    "Qwen está sintetizando la voz localmente."
                    if len(chunks) == 1
                    else "El texto largo se dividió por frases para reducir deriva."
                ),
                actual_backend,
                chunk_index=index,
                chunk_count=len(chunks),
            )

            kwargs = {
                "text": chunk,
                "language": effective_language,
                "voice_clone_prompt": prompt,
                "max_new_tokens": estimate_max_new_tokens(chunk),
                "non_streaming_mode": True,
                "do_sample": bool(generation["do_sample"]),
                "temperature": float(generation["temperature"]),
                "top_p": float(generation["top_p"]),
                "top_k": int(generation["top_k"]),
                "repetition_penalty": float(generation["repetition_penalty"]),
                "subtalker_dosample": bool(generation["subtalker_dosample"]),
                "subtalker_temperature": float(generation["subtalker_temperature"]),
                "subtalker_top_p": float(generation["subtalker_top_p"]),
                "subtalker_top_k": int(generation["subtalker_top_k"]),
            }

            wavs, sr = model.generate_voice_clone(**kwargs)
            sample_rate = int(sr)
            outputs.append(wavs[0])

        import numpy as np

        if len(outputs) == 1:
            combined = outputs[0]
        else:
            pause = np.zeros(int((sample_rate or 24000) * 0.16), dtype=np.float32)
            combined_parts = []
            for i, wav in enumerate(outputs):
                if i:
                    combined_parts.append(pause)
                combined_parts.append(np.asarray(wav, dtype=np.float32))
            combined = np.concatenate(combined_parts)

        return combined, int(sample_rate or 24000), actual_backend, icl_rechazo


MODEL_MANAGER = ModelManager()


class GenerateRequest(BaseModel):
    text: str
    voice_id: str
    model_id: str = DEFAULT_MODEL_ID
    language: str = "Spanish"
    mode: Literal["auto", "cuda", "cpu"] = "auto"
    profile: Literal["faithful", "natural", "spot", "custom"] = "natural"

    speed: float = 1.0
    stability: float = 0.55
    style_exaggeration: float = 0.0
    pitch_semitones: float = 0.0
    speaker_boost: bool = True
    output_format: Literal["wav", "flac", "mp3"] = "wav"
    output_sample_rate: Literal[0, 44100] = 0
    music_id: Optional[str] = None
    music_volume: float = 0.18
    request_id: str = ""


class NormalizeRequest(BaseModel):
    text: str = ""


class CancelGenerateRequest(BaseModel):
    request_id: str


class ModelInstallRequest(BaseModel):
    model_id: str


class TranscriptUpdate(BaseModel):
    transcript: str = ""


class HistoryMusicRequest(BaseModel):
    sound_id: Optional[str] = None
    music_volume: float = 0.18


def find_audio(directory: Path, audio_id: str) -> Path:
    for path in directory.iterdir():
        if path.is_file() and path.suffix.lower() in ALLOWED_AUDIO:
            if path.stem == audio_id:
                return path
    raise HTTPException(status_code=404, detail="Audio no encontrado.")


def list_audio(directory: Path, include_transcript: bool = False) -> list[dict]:
    items = []
    for path in sorted(directory.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_file() or path.suffix.lower() not in ALLOWED_AUDIO:
            continue
        item = {
            "id": path.stem,
            "name": pretty_name(path.name),
            "filename": path.name,
        }
        if include_transcript:
            sidecar = transcript_path(path)
            transcript = ""
            if sidecar.exists():
                transcript = sidecar.read_text(
                    encoding="utf-8", errors="ignore"
                ).strip()
            item["has_transcript"] = bool(transcript)
            item["transcript"] = transcript

            ref_info = get_voice_reference_info(path)
            prepared = ref_info.get("prepared_analysis") or ref_info.get("original") or {}
            item["duration"] = prepared.get("duration")
            item["quality_score"] = ref_info.get("quality_score", 0)
            item["quality_label"] = ref_info.get("quality_label", "Sin analizar")
            item["reference_notes"] = ref_info.get("notes", [])
            item["sample_rate"] = prepared.get("sample_rate")
            item["channels"] = prepared.get("channels")
            item["rms_dbfs"] = prepared.get("rms_dbfs")
            item["prepared"] = bool(ref_info.get("prepared"))
            item["analyzing"] = bool(ref_info.get("analyzing"))
            item["offset_seconds"] = read_reference_offset(path)
            item["source_duration"] = (ref_info.get("original") or {}).get("duration")
        items.append(item)
    return items


@app.get("/api/health")
def health():
    # `engine` identifies *this* server. The desktop shell checks it so a
    # stranger already listening on the port cannot be mistaken for us.
    return {
        "ok": True,
        "engine": "voice-studio-ai",
        "model": DEFAULT_MODEL_ID,
        "data_root": str(DATA_ROOT),
        "library_warming_up": WARM_UP.busy,
        "generation_stuck_seconds": round(MODEL_MANAGER.stuck_seconds(), 1),
    }


@app.get("/api/system")
def system():
    info = torch_info()
    info.update(
        {
            "model_id": DEFAULT_MODEL_ID,
            "model_loaded": MODEL_MANAGER.model is not None,
            "loaded_model_id": MODEL_MANAGER.model_id,
            "loaded_backend": MODEL_MANAGER.backend,
            "data_root": str(DATA_ROOT),
        }
    )
    return info


@app.get("/api/status")
def status():
    return STATUS.get()


@app.get("/api/models")
def models():
    return {
        "recommended_id": DEFAULT_MODEL_ID,
        "compatible": [supported_model_payload(mid) for mid in SUPPORTED_MODELS],
    }


@app.post("/api/models/install", status_code=202)
def install_model(request: ModelInstallRequest):
    if request.model_id not in SUPPORTED_MODELS:
        raise HTTPException(
            status_code=400,
            detail="Este modelo todavía no tiene un adaptador instalable en Voice Studio AI.",
        )
    try:
        return MODEL_INSTALLER.start(request.model_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/models/install/status")
def model_install_status(model_id: str):
    if model_id not in SUPPORTED_MODELS:
        raise HTTPException(status_code=404, detail="Modelo compatible no encontrado.")
    return MODEL_INSTALLER.get_state(model_id)


@app.get("/api/history")
def history():
    return load_history()


@app.delete("/api/history")
def clear_history():
    save_history([])
    return {"ok": True, "removed_files": prune_orphan_outputs([])}


@app.get("/api/voices")
def voices():
    return list_audio(VOICES_DIR, include_transcript=True)


@app.get("/api/sounds")
def sounds():
    items = []
    for item in list_audio(SOUNDS_DIR, include_transcript=False):
        path = find_audio(SOUNDS_DIR, item["id"])
        valid, error, info = validate_canonical_music(path)
        item["valid"] = valid
        item["error"] = error
        if info:
            item["duration"] = round(info["duration"], 2)
            item["sample_rate"] = info["sample_rate"]
            item["channels"] = info["channels"]
            item["audio_format"] = info["format"]
        items.append(item)
    return items


@app.get("/api/voices/{voice_id}/audio")
def voice_audio(voice_id: str):
    path = find_audio(VOICES_DIR, voice_id)
    return FileResponse(path)


@app.post("/api/voices/{voice_id}/transcript")
def update_voice_transcript(voice_id: str, request: TranscriptUpdate):
    path = find_audio(VOICES_DIR, voice_id)
    sidecar = transcript_path(path)
    text = request.transcript.strip()

    if text:
        sidecar.write_text(text, encoding="utf-8")
    else:
        sidecar.unlink(missing_ok=True)

    MODEL_MANAGER.invalidate_voice(voice_id)
    try:
        _, metadata = prepare_reference_audio(path, force=True)
    except Exception:
        metadata = get_voice_reference_info(path)

    return {
        "ok": True,
        "voice_id": voice_id,
        "has_transcript": bool(text),
        "transcript": text,
        "quality_score": metadata.get("quality_score", 0),
        "quality_label": metadata.get("quality_label", "Sin analizar"),
    }


class ReferenceOffsetRequest(BaseModel):
    offset_seconds: float = 0.0


@app.post("/api/voices/{voice_id}/offset")
def set_reference_offset(voice_id: str, request: ReferenceOffsetRequest):
    """
    Elige desde qué segundo se toma la referencia.

    El recorte automático se queda con el principio, que no siempre es el
    mejor tramo: puede haber una respiración, ruido o una frase poco
    representativa. Esto permite mover ese punto sin editar el archivo fuera.
    """
    path = find_audio(VOICES_DIR, voice_id)
    write_reference_offset(path, request.offset_seconds)
    MODEL_MANAGER.invalidate_voice(voice_id)
    _, metadata = prepare_reference_audio(path, force=True)
    return {
        "ok": True,
        "voice_id": voice_id,
        "offset_seconds": read_reference_offset(path),
        "duration": (metadata.get("prepared_analysis") or {}).get("duration"),
        "quality_score": metadata.get("quality_score", 0),
        "quality_label": metadata.get("quality_label", "Sin analizar"),
    }


@app.post("/api/voices/{voice_id}/prime", status_code=202)
def prime_voice(voice_id: str):
    """
    Precomputes the clone prompt for a voice the user just selected.

    Building it costs ~9 s and is cached per voice, so doing it now — while
    they are still writing the script — takes that time off the first
    generation. Fire-and-forget: failures surface later on the real request.
    """
    path = find_audio(VOICES_DIR, voice_id)

    def worker() -> None:
        try:
            model, backend = MODEL_MANAGER.load("auto", DEFAULT_MODEL_ID)
            sidecar = transcript_path(path)
            ref_text = (
                sidecar.read_text(encoding="utf-8", errors="ignore").strip()
                if sidecar.exists()
                else None
            )
            MODEL_MANAGER.get_clone_prompt(model, path, ref_text or None, backend)
        except Exception as exc:
            print(f"[prime] no se pudo preparar la voz {voice_id}: {exc}")

    threading.Thread(target=worker, name=f"prime-{voice_id[:16]}", daemon=True).start()
    return {"ok": True, "voice_id": voice_id}


@app.get("/api/sounds/{sound_id}/audio")
def sound_audio(sound_id: str):
    path = find_audio(SOUNDS_DIR, sound_id)
    return FileResponse(path)


@app.get("/api/outputs/{filename}")
def output_audio(filename: str):
    safe = Path(filename).name
    path = OUTPUTS_DIR / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail="Resultado no encontrado.")
    media = AUDIO_MEDIA_TYPES.get(path.suffix.lower(), "audio/wav")
    return FileResponse(path, media_type=media)


async def save_upload(file: UploadFile, destination_dir: Path) -> Path:
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_AUDIO:
        raise HTTPException(
            status_code=400,
            detail="Formato no compatible. Usa WAV, MP3, FLAC u OGG.",
        )

    filename = safe_filename(file.filename or f"audio{suffix}")
    target = destination_dir / filename

    # IDs are derived from Path.stem. Keep stems unique as well as full file
    # names unique; otherwise foo.mp3 and foo.wav become indistinguishable to
    # find_audio(), prepared-reference caches, and the frontend.
    stem_taken = any(
        path.is_file()
        and path.suffix.lower() in ALLOWED_AUDIO
        and path.stem.casefold() == target.stem.casefold()
        for path in destination_dir.iterdir()
    )
    if target.exists() or stem_taken:
        target = destination_dir / f"{target.stem}_{uuid.uuid4().hex[:5]}{target.suffix}"

    size = 0
    with target.open("wb") as handle:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_MB * 1024 * 1024:
                handle.close()
                target.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=400,
                    detail=f"El archivo supera {MAX_UPLOAD_MB} MB.",
                )
            handle.write(chunk)

    return target


@app.post("/api/voices/import")
async def import_voice(
    file: UploadFile = File(...),
    transcript: str = Form(""),
):
    target = await save_upload(file, VOICES_DIR)

    clean_transcript = transcript.strip()
    if clean_transcript:
        transcript_path(target).write_text(clean_transcript, encoding="utf-8")

    try:
        prepared_path, metadata = prepare_reference_audio(target, force=True)
        if not prepared_path.exists() or not metadata.get("prepared_analysis", {}).get(
            "duration"
        ):
            raise RuntimeError("El archivo no contiene audio decodificable.")
    except Exception as exc:
        target.unlink(missing_ok=True)
        transcript_path(target).unlink(missing_ok=True)
        prepared_voice_path(target).unlink(missing_ok=True)
        voice_meta_path(target).unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail=f"No se pudo preparar '{file.filename or target.name}'. {exc}",
        ) from exc

    return {
        "id": target.stem,
        "name": pretty_name(target.name),
        "filename": target.name,
        "has_transcript": bool(clean_transcript),
        "duration": (metadata.get("prepared_analysis") or {}).get("duration"),
        "quality_score": metadata.get("quality_score", 0),
        "quality_label": metadata.get("quality_label", "Sin analizar"),
        "reference_notes": metadata.get("notes", []),
    }


@app.post("/api/sounds/import")
async def import_sound(file: UploadFile = File(...)):
    temp_dir = DATA_ROOT / "upload_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = await save_upload(file, temp_dir)

    try:
        result = transcode_music_to_wav(
            source_path=temp_path,
            destination_dir=SOUNDS_DIR,
            original_name=file.filename or temp_path.name,
            target_sr=44100,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"No se pudo importar '{file.filename or temp_path.name}'. {exc}",
        ) from exc
    finally:
        temp_path.unlink(missing_ok=True)

    target = result["path"]
    metadata = result["metadata"]

    return {
        "id": target.stem,
        "name": pretty_name(Path(metadata["source_name"]).name),
        "filename": target.name,
        "source_name": metadata["source_name"],
        "duration": metadata["duration"],
        "sample_rate": metadata["sample_rate"],
        "channels": metadata["channels"],
        "valid": True,
    }


@app.post("/api/sounds/repair")
def repair_sounds():
    repaired = []
    quarantined = []
    already_valid = []

    for path in list(SOUNDS_DIR.iterdir()):
        if not path.is_file() or path.suffix.lower() not in ALLOWED_AUDIO:
            continue

        if path.suffix.lower() == ".wav":
            valid, _, _ = validate_canonical_music(path)
            if valid:
                already_valid.append(path.name)
                continue

        try:
            result = transcode_music_to_wav(
                source_path=path,
                destination_dir=SOUNDS_DIR,
                original_name=path.name,
                target_sr=44100,
            )
            repaired.append({"from": path.name, "to": result["path"].name})
            path.unlink(missing_ok=True)
            path.with_suffix(path.suffix + ".meta.json").unlink(missing_ok=True)
        except Exception as exc:
            destination = INVALID_SOUNDS_DIR / path.name
            i = 2
            while destination.exists():
                destination = INVALID_SOUNDS_DIR / f"{path.stem}_{i}{path.suffix}"
                i += 1
            shutil.move(str(path), str(destination))
            quarantined.append({
                "file": path.name,
                "reason": str(exc),
                "moved_to": str(destination),
            })

    return {
        "ok": True,
        "repaired": repaired,
        "quarantined": quarantined,
        "already_valid": already_valid,
    }


@app.post("/api/generate")
def generate(request: GenerateRequest):
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Escribe un guion.")
    if len(text) > 3000:
        raise HTTPException(
            status_code=400,
            detail="Esta versión limita cada guion a 3000 caracteres.",
        )

    # Una generación colgada retiene generate_lock para siempre. Sin esto, la
    # siguiente petición se quedaría esperando indefinidamente y el usuario
    # vería otra vez "le doy generar y no pasa nada"; con esto recibe el motivo
    # y la app puede ofrecer reiniciar el motor.
    stuck = MODEL_MANAGER.stuck_seconds()
    if stuck > 0:
        raise HTTPException(
            status_code=503,
            detail=(
                "La generación anterior lleva "
                f"{int(stuck / 60) + 1} min pasada de su tiempo previsto y dejó "
                "el motor bloqueado. Reinicia Voice Studio AI para recuperarlo."
            ),
        )

    text, removed = sanitize_script(text)
    text = text.strip()
    if not text:
        raise HTTPException(
            status_code=400,
            detail="El guion no contiene texto que se pueda pronunciar.",
        )

    # El modelo lee mal precios, horas y fechas (issue #328): "S/ 25.50" o
    # "3:30 pm" salen deletreados o en otro idioma. Se reescriben a palabras
    # antes de fragmentar, porque expandirlos alarga el texto y eso cambia
    # dónde caen los cortes.
    spoken_text = normalize_spanish(text)

    if request.model_id not in SUPPORTED_MODELS:
        raise HTTPException(
            status_code=400,
            detail=(
                "Ese modelo fue descubierto en Hugging Face, pero necesita "
                "un adaptador distinto. Selecciona un modelo marcado como Compatible."
            ),
        )

    music_path_prechecked = None
    if request.music_id:
        music_path_prechecked = find_audio(SOUNDS_DIR, request.music_id)
        valid_music, music_error, _ = validate_canonical_music(music_path_prechecked)
        if not valid_music:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"La música '{music_path_prechecked.name}' no es un audio válido. "
                    f"{music_error or ''} "
                    "Pulsa 'Reparar biblioteca de música' o vuelve a importarla."
                ).strip(),
            )

    voice_path = find_audio(VOICES_DIR, request.voice_id)
    sidecar = transcript_path(voice_path)
    ref_text = None

    if sidecar.exists():
        candidate = sidecar.read_text(encoding="utf-8", errors="ignore").strip()
        ref_text = candidate or None

    STATUS.start_request()
    MODEL_MANAGER.begin_generation(
        max(STUCK_MINIMUM_SECONDS, len(spoken_text) * STUCK_SECONDS_PER_CHAR)
    )
    STATUS.set(
        "checking",
        "Comprobando hardware",
        "Seleccionando el mejor modo para este equipo.",
        request.mode,
    )

    generation = qwen_sampling_from_friendly_controls(
        stability=request.stability,
        style_exaggeration=request.style_exaggeration,
        profile=request.profile,
    )

    try:
        wav, sample_rate, backend, icl_rechazo = MODEL_MANAGER.generate(
            text=spoken_text,
            voice_path=voice_path,
            ref_text=ref_text,
            language=request.language,
            requested_mode=request.mode,
            generation=generation,
            model_id=request.model_id,
            request_id=request.request_id,
        )

        STATUS.set(
            "postprocessing",
            "Ajustando la voz",
            "Aplicando velocidad, tono y presencia localmente.",
            backend,
        )

        wav = apply_audio_postprocessing(
            wav=wav,
            sample_rate=sample_rate,
            speed=request.speed,
            pitch_semitones=request.pitch_semitones,
            speaker_boost=request.speaker_boost,
        )

        music_path = None
        music_name = None
        if request.music_id:
            STATUS.set(
                "mixing",
                "Mezclando música",
                "Aplicando el fondo seleccionado al archivo final.",
                backend,
            )
            music_path = music_path_prechecked or find_audio(SOUNDS_DIR, request.music_id)
            music_name = pretty_name(music_path.name)
            wav = mix_voice_with_music(
                voice_wav=wav,
                sample_rate=sample_rate,
                music_path=music_path,
                music_volume=clamp(request.music_volume, 0.0, 0.60),
            )

        STATUS.set(
            "saving",
            "Guardando resultado",
            "Escribiendo el archivo final con la mezcla aplicada.",
            backend,
        )

        extension = request.output_format
        filename = f"locucion_{int(time.time())}_{uuid.uuid4().hex[:5]}.{extension}"
        output_path = OUTPUTS_DIR / filename

        wav, sample_rate = resample_output(
            wav, sample_rate, request.output_sample_rate
        )
        write_audio(output_path, wav, sample_rate, extension)

        history_item = {
            "id": uuid.uuid4().hex,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "text": text,
            "title": text[:88] + ("…" if len(text) > 88 else ""),
            "voice_id": request.voice_id,
            "voice_name": pretty_name(voice_path.name),
            "backend": backend,
            "model_id": request.model_id,
            "model_name": SUPPORTED_MODELS[request.model_id]["name"],
            "music_id": request.music_id,
            "music_name": music_name,
            "filename": filename,
            # The dry (voice-only) render, kept so background music can be
            # added, swapped, or removed later without regenerating the TTS.
            "dry_filename": filename if not request.music_id else None,
            "url": f"/api/outputs/{filename}",
            "used_transcript": bool(ref_text) and not icl_rechazo,
            "settings": {
                "speed": round(clamp(request.speed, 0.70, 1.35), 2),
                "profile": request.profile,
                "stability": round(clamp(request.stability, 0.0, 1.0), 2),
                "style_exaggeration": round(
                    clamp(request.style_exaggeration, 0.0, 1.0), 2
                ),
                "pitch_semitones": round(
                    clamp(request.pitch_semitones, -4.0, 4.0), 2
                ),
                "speaker_boost": bool(request.speaker_boost),
                "language": request.language,
                "model_id": request.model_id,
                "output_format": extension,
                "music_id": request.music_id,
                "music_name": music_name,
                "music_volume": round(clamp(request.music_volume, 0.0, 0.60), 2),
                "qwen_sampling": generation,
            },
        }
        add_history_item(history_item)

        STATUS.set(
            "done",
            "Locución terminada",
            "El audio está listo.",
            backend,
        )

        return {
            "ok": True,
            "backend": backend,
            "model_id": request.model_id,
            "model_name": SUPPORTED_MODELS[request.model_id]["name"],
            "music_id": request.music_id,
            "music_name": music_name,
            "music_volume": round(clamp(request.music_volume, 0.0, 0.60), 2),
            "sample_rate": sample_rate,
            "filename": filename,
            "url": f"/api/outputs/{filename}",
            "used_transcript": bool(ref_text) and not icl_rechazo,
            "history": history_item,
            "qwen_sampling": generation,
            "removed_characters": removed,
            "spoken_text": spoken_text if spoken_text != text else None,
            "transcript_ignored": icl_rechazo,
        }
    except GenerationCancelled as exc:
        STATUS.set("idle", "Motor listo", "Generación cancelada por el usuario.", MODEL_MANAGER.backend)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        # Se responde un resumen, así que el volcado completo solo sobrevive si
        # se escribe aquí: HTTPException es un error "manejado" y uvicorn no lo
        # registra. Sin esto, el registro del motor —lo que pide el botón
        # Copiar diagnóstico— se quedaría sin la causa real.
        print("[generate] fallo:\n" + traceback.format_exc(), file=sys.stderr)
        detail = friendly_generation_error(exc)
        STATUS.set(
            "error",
            "Error del motor",
            detail,
            MODEL_MANAGER.backend,
        )
        raise HTTPException(status_code=500, detail=detail) from exc
    finally:
        STATUS.end_request()
        MODEL_MANAGER.end_generation()
        if request.request_id:
            clear_generation_cancelled(request.request_id)


@app.post("/api/normalize")
def normalize_preview(request: NormalizeRequest):
    """
    Cómo se leerá el guion, sin generar nada.

    Una locución cuesta minutos en CPU: descubrir ahí que un precio se leyó
    mal significa tirar toda esa espera. Esto responde al instante.
    """
    clean, removed = sanitize_script(request.text.strip())
    spoken = normalize_spanish(clean)
    return {
        "spoken": spoken,
        "changed": spoken != clean,
        "removed_characters": removed,
        "characters": len(spoken),
    }


@app.post("/api/generate/cancel")
def cancel_generate(request: CancelGenerateRequest):
    if request.request_id:
        mark_generation_cancelled(request.request_id)
    return {"ok": True}


@app.post("/api/history/{history_id}/music")
def set_history_music(history_id: str, request: HistoryMusicRequest):
    """
    Post-production step: add, swap, or remove background music on an
    already-generated result without re-running the TTS model. Always mixes
    from the untouched dry (voice-only) render, so this can be called
    repeatedly with different tracks/volumes.
    """
    items = load_history()
    item = next((it for it in items if it.get("id") == history_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="No se encontró ese resultado en el historial.")

    dry_filename = item.get("dry_filename")
    if not dry_filename:
        raise HTTPException(
            status_code=400,
            detail="Este resultado no tiene una locución sin música guardada para remezclar.",
        )

    dry_path = OUTPUTS_DIR / dry_filename
    if not dry_path.exists():
        raise HTTPException(status_code=404, detail="El audio original ya no está disponible.")

    extension = Path(item.get("filename", dry_filename)).suffix.lstrip(".") or "wav"
    settings = item.setdefault("settings", {})

    if not request.sound_id:
        item["filename"] = dry_filename
        item["url"] = f"/api/outputs/{dry_filename}"
        item["music_id"] = None
        item["music_name"] = None
        settings["music_id"] = None
        settings["music_name"] = None
        save_history(items)
        prune_orphan_outputs(items)
        return item

    music_path = find_audio(SOUNDS_DIR, request.sound_id)
    valid_music, music_error, _ = validate_canonical_music(music_path)
    if not valid_music:
        raise HTTPException(
            status_code=400,
            detail=(
                f"La música '{music_path.name}' no es un audio válido. "
                f"{music_error or ''} "
                "Pulsa 'Reparar biblioteca de música' o vuelve a importarla."
            ).strip(),
        )

    import soundfile as sf

    voice_wav, sample_rate = sf.read(str(dry_path), dtype="float32", always_2d=False)
    music_volume = clamp(request.music_volume, 0.0, 0.60)
    mixed = mix_voice_with_music(
        voice_wav=voice_wav,
        sample_rate=sample_rate,
        music_path=music_path,
        music_volume=music_volume,
    )

    music_name = pretty_name(music_path.name)
    filename = f"locucion_{int(time.time())}_{uuid.uuid4().hex[:5]}.{extension}"
    output_path = OUTPUTS_DIR / filename
    write_audio(output_path, mixed, sample_rate, extension)

    item["filename"] = filename
    item["url"] = f"/api/outputs/{filename}"
    item["music_id"] = request.sound_id
    item["music_name"] = music_name
    settings["music_id"] = request.sound_id
    settings["music_name"] = music_name
    settings["music_volume"] = round(music_volume, 2)
    save_history(items)
    # The previous mix is no longer referenced by anything.
    prune_orphan_outputs(items)
    return item


def audio_pipeline_probe() -> str:
    """
    Runs every librosa/soundfile call the engine makes at runtime.

    `import librosa` is not proof that librosa works: librosa attaches its
    submodules through lazy_loader, so a runtime built without scikit-learn
    imports cleanly and only explodes on the first real call. That is exactly
    how a packaged engine shipped that started fine yet failed with "No module
    named 'sklearn'" on every voice import and every generation. Touching the
    real calls is the only check that catches it.
    """
    import tempfile

    import librosa
    import numpy as np
    import soundfile as sf

    tone = (0.25 * np.sin(2 * np.pi * 220.0 * np.arange(24000) / 24000.0)).astype(
        np.float32
    )

    with tempfile.TemporaryDirectory() as workspace:
        source = Path(workspace) / "self_test.wav"
        sf.write(str(source), tone, 24000, subtype="PCM_16")

        # prepare_reference_audio()
        loaded, _ = librosa.load(str(source), sr=24000, mono=True)
        trimmed, _ = librosa.effects.trim(loaded, top_db=35)

        # apply_audio_postprocessing()
        stretched = librosa.effects.time_stretch(trimmed, rate=1.05)
        librosa.effects.pitch_shift(y=stretched, sr=24000, n_steps=1.0)

        # audio_ingest.decode_audio_file()
        librosa.resample(tone, orig_sr=24000, target_sr=44100)
        decoded, rate = decode_audio_file(source, target_sr=44100)

    if not decoded.size or rate != 44100:
        raise RuntimeError("La decodificación de audio devolvió un resultado vacío.")
    return f"librosa+soundfile OK ({decoded.shape[0]} muestras @ {rate} Hz)"


def packaging_self_test() -> int:
    """
    Packaged-runtime test.

    It intentionally does NOT download a model, but it does EXERCISE the audio
    pipeline (see audio_pipeline_probe) instead of only importing it.
    """
    checks = []

    def check(label, fn):
        try:
            value = fn()
            checks.append((label, True, str(value or "OK")))
        except Exception as exc:
            checks.append((label, False, f"{type(exc).__name__}: {exc}"))

    check("numpy", lambda: __import__("numpy").__version__)
    check("soundfile", lambda: __import__("soundfile").__version__)
    check("librosa", lambda: __import__("librosa").__version__)
    check("scikit-learn", lambda: __import__("sklearn").__version__)
    check("torch", lambda: __import__("torch").__version__)
    check("transformers", lambda: __import__("transformers").__version__)
    check("accelerate", lambda: __import__("accelerate").__version__)
    check("huggingface_hub", lambda: __import__("huggingface_hub").__version__)

    check("pipeline de audio", audio_pipeline_probe)

    def normalizacion_check():
        # Módulo local: si PyInstaller no lo empaqueta, el motor arranca y
        # falla al generar. Se comprueba ejecutándolo, no solo importándolo.
        salida = normalize_spanish("S/ 25.50 a las 3:30 pm del 15/08/2026")
        if "veinticinco soles" not in salida or "de la tarde" not in salida:
            raise RuntimeError(f"Normalización inesperada: {salida!r}")
        return "normalize_spanish OK"

    check("normalización de texto", normalizacion_check)

    def qwen_check():
        from importlib.util import find_spec

        from qwen_tts import Qwen3TTSModel
        from qwen_tts.core.tokenizer_12hz.configuration_qwen3_tts_tokenizer_v2 import (
            Qwen3TTSTokenizerV2Config,
        )
        from qwen_tts.core.tokenizer_12hz.modeling_qwen3_tts_tokenizer_v2 import (
            Qwen3TTSTokenizerV2Model,
        )

        if find_spec("qwen_tts.core.tokenizer_25hz") is not None:
            raise RuntimeError("El runtime todavía contiene tokenizer_25hz.")

        return (
            f"{Qwen3TTSModel.__name__}, "
            f"{Qwen3TTSTokenizerV2Config.__name__}, "
            f"{Qwen3TTSTokenizerV2Model.__name__}, 12Hz-only"
        )

    check("qwen_tts.Qwen3TTSModel", qwen_check)

    print("VOICE_STUDIO_ENGINE_SELF_TEST")
    failed = False
    for label, ok, detail in checks:
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {label}: {detail}")
        failed = failed or not ok

    if failed:
        print("SELF_TEST_RESULT=FAIL")
        return 2

    print("SELF_TEST_RESULT=PASS")
    return 0


def port_conflict() -> Optional[str]:
    """
    Bind the port before uvicorn does so a conflict produces a readable
    message in engine.log instead of an opaque WinError traceback.
    """
    import socket

    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind(("127.0.0.1", PORT))
    except OSError as exc:
        return (
            f"El puerto {PORT} ya está ocupado por otro programa ({exc}). "
            "Cierra la otra copia de Voice Studio AI o el programa que lo usa, "
            f"o define QWEN_ENGINE_PORT con un puerto libre."
        )
    finally:
        probe.close()
    return None


if __name__ == "__main__":
    if "--self-test-packaging" in sys.argv:
        raise SystemExit(packaging_self_test())

    import uvicorn

    print()
    print("Qwen Voice Studio - Local Engine")
    print(f"Data: {DATA_ROOT}")
    print(f"API:  http://127.0.0.1:{PORT}")
    print()

    conflict = port_conflict()
    if conflict:
        print(f"ENGINE_START_FAILED: {conflict}", flush=True)
        raise SystemExit(3)

    # Seeding and reference analysis run here, alongside a port that is
    # already accepting requests, instead of delaying startup.
    WARM_UP.start()

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=PORT,
        log_level="info",
    )
