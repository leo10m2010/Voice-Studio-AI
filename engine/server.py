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
import uuid
from pathlib import Path
from typing import Literal, Optional
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.parse import quote

os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from audio_mix import mix_voice_with_music
from audio_ingest import transcode_music_to_wav, validate_canonical_music

DEFAULT_MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"

SUPPORTED_MODELS = {
    "Qwen/Qwen3-TTS-12Hz-0.6B-Base": {
        "name": "Qwen3-TTS 0.6B Base",
        "author": "Qwen",
        "family": "Qwen3-TTS",
        "engine": "qwen",
        "recommended": True,
        "disk_gb": 2.52,
        "gpu_vram_recommended_gb": 5.5,
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
        "gpu_vram_recommended_gb": 10.0,
        "description": "Más pesado. Puede mejorar calidad, pero requiere bastante más memoria.",
        "license": "apache-2.0",
        "spanish": True,
    },
}

CURATED_DISCOVERY_MODELS = [
    {
        "id": "ResembleAI/Chatterbox-Multilingual-es-mx-latam",
        "name": "Chatterbox Multilingual · Español LatAm",
        "author": "ResembleAI",
        "family": "Chatterbox V3",
        "engine": "chatterbox",
        "recommended": False,
        "description": "Modelo dedicado a español latinoamericano con voice cloning.",
        "license": "mit",
        "spanish": True,
        "compatible": False,
        "compatibility_note": "Requiere adaptador Chatterbox; no usa la API de Qwen.",
    },
    {
        "id": "myshell-ai/OpenVoiceV2",
        "name": "OpenVoice V2",
        "author": "myshell-ai",
        "family": "OpenVoice",
        "engine": "openvoice",
        "recommended": False,
        "description": "Clonación de timbre multilingüe con soporte nativo de español.",
        "license": "mit",
        "spanish": True,
        "compatible": False,
        "compatibility_note": "Requiere adaptador OpenVoice; no usa la API de Qwen.",
    },
]
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

ALLOWED_AUDIO = {".wav", ".mp3", ".flac", ".ogg"}
MAX_UPLOAD_MB = 80
FETCH_REMOTE_AVATARS = os.environ.get("QWEN_STUDIO_FETCH_AVATARS", "0").lower() in {
    "1",
    "true",
    "yes",
}

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


_HF_AVATAR_CACHE: dict[str, Optional[str]] = {}
_HF_SEARCH_CACHE: dict[str, tuple[float, list[dict]]] = {}


def fetch_json_url(url: str, timeout: float = 6.0):
    request = Request(
        url,
        headers={
            "User-Agent": "VoiceStudioAI/0.6",
            "Accept": "application/json",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def huggingface_author_avatar(author: str) -> Optional[str]:
    """
    Hugging Face exposes public user/org overview endpoints with avatarUrl.
    The lookup is best-effort so the app remains usable offline.
    """
    if not author:
        return None
    if author in _HF_AVATAR_CACHE:
        return _HF_AVATAR_CACHE[author]

    # Avatars are decorative. Do not make the local app wait on Hugging Face
    # during startup or every refresh when the user is offline. Set
    # QWEN_STUDIO_FETCH_AVATARS=1 to opt into the best-effort lookup.
    if not FETCH_REMOTE_AVATARS:
        _HF_AVATAR_CACHE[author] = None
        return None

    value = None
    encoded = quote(author, safe="")
    for endpoint in (
        f"https://huggingface.co/api/organizations/{encoded}/overview",
        f"https://huggingface.co/api/users/{encoded}/overview",
    ):
        try:
            data = fetch_json_url(endpoint)
            value = data.get("avatarUrl") or data.get("avatar_url")
            if value:
                break
        except Exception:
            continue

    _HF_AVATAR_CACHE[author] = value
    return value


def supported_model_payload(model_id: str) -> dict:
    info = dict(SUPPORTED_MODELS[model_id])
    info.update(
        {
            "id": model_id,
            "compatible": True,
            "compatibility_note": "Compatible con el motor Qwen integrado.",
            "avatar_url": huggingface_author_avatar(info.get("author", "")),
            "hub_url": f"https://huggingface.co/{model_id}",
        }
    )
    return info


def discover_engine_family(model_id: str, tags: list[str]) -> tuple[str, str]:
    text = (model_id + " " + " ".join(tags)).lower()
    if "qwen3-tts" in text:
        return "qwen", "Qwen3-TTS"
    if "chatterbox" in text:
        return "chatterbox", "Chatterbox"
    if "openvoice" in text:
        return "openvoice", "OpenVoice"
    if "xtts" in text:
        return "xtts", "XTTS"
    return "unknown", "TTS"


def search_huggingface_models(query: str, limit: int = 16) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []

    key = query.lower()
    cached = _HF_SEARCH_CACHE.get(key)
    if cached and time.time() - cached[0] < 120:
        return cached[1]

    try:
        from huggingface_hub import HfApi

        api = HfApi()
        models = api.list_models(
            search=query,
            filter="text-to-speech",
            sort="downloads",
            direction=-1,
            limit=max(limit * 2, 20),
            full=True,
        )

        results = []
        for model in models:
            model_id = getattr(model, "id", None) or getattr(model, "modelId", None)
            if not model_id:
                continue

            tags = list(getattr(model, "tags", None) or [])
            author = getattr(model, "author", None) or model_id.split("/", 1)[0]
            engine, family = discover_engine_family(model_id, tags)
            compatible = model_id in SUPPORTED_MODELS

            results.append(
                {
                    "id": model_id,
                    "name": model_id.split("/")[-1],
                    "author": author,
                    "family": family,
                    "engine": engine,
                    "recommended": bool(
                        SUPPORTED_MODELS.get(model_id, {}).get("recommended")
                    ),
                    "compatible": compatible,
                    "compatibility_note": (
                        "Compatible con el motor Qwen integrado."
                        if compatible
                        else f"Descubierto en Hugging Face. Requiere adaptador {family}."
                    ),
                    "description": "",
                    "license": None,
                    "spanish": ("es" in tags or "spanish" in tags),
                    "downloads": getattr(model, "downloads", None),
                    "likes": getattr(model, "likes", None),
                    "avatar_url": huggingface_author_avatar(author),
                    "hub_url": f"https://huggingface.co/{model_id}",
                }
            )
            if len(results) >= limit:
                break
    except Exception:
        results = []

    _HF_SEARCH_CACHE[key] = (time.time(), results)
    return results


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

    if sound_dir.exists():
        for source in sound_dir.iterdir():
            if not source.is_file() or source.suffix.lower() not in ALLOWED_AUDIO:
                continue

            # The bundled library is published as MP3, while the mixer and
            # validator expect canonical WAV files. Convert seeds once so the
            # built-in music is usable immediately after first launch.
            canonical = SOUNDS_DIR / f"{source.stem}.wav"
            if canonical.exists():
                continue
            try:
                transcode_music_to_wav(
                    source_path=source,
                    destination_dir=SOUNDS_DIR,
                    original_name=source.name,
                    target_sr=44100,
                )
            except Exception:
                # Keep the original available for the repair action if a
                # codec is unavailable in a reduced installation.
                try:
                    shutil.copy2(source, SOUNDS_DIR / source.name)
                except OSError:
                    pass


copy_seed_assets()


class EngineStatus:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data = {
            "stage": "idle",
            "title": "Motor listo",
            "message": "Esperando una generación.",
            "backend": None,
        }

    def set(
        self,
        stage: str,
        title: str,
        message: str,
        backend: Optional[str] = None,
    ) -> None:
        with self._lock:
            self._data = {
                "stage": stage,
                "title": title,
                "message": message,
                "backend": backend,
            }

    def get(self) -> dict:
        with self._lock:
            return dict(self._data)


STATUS = EngineStatus()


def torch_info() -> dict:
    try:
        import torch

        cuda = bool(torch.cuda.is_available())
        result = {
            "python_ready": True,
            "python_error": None,
            "torch_version": torch.__version__,
            "cuda_available": cuda,
            "cuda_version": getattr(torch.version, "cuda", None),
            "gpu_name": None,
            "vram_gb": None,
            "compute_capability": None,
            "recommended_mode": "cpu",
        }

        if cuda:
            properties = torch.cuda.get_device_properties(0)
            vram_gb = properties.total_memory / (1024**3)
            capability = torch.cuda.get_device_capability(0)
            result.update(
                {
                    "gpu_name": torch.cuda.get_device_name(0),
                    "vram_gb": round(vram_gb, 2),
                    "compute_capability": f"{capability[0]}.{capability[1]}",
                    # Conservative threshold for the official PyTorch model.
                    "recommended_mode": "cuda" if vram_gb >= 5.5 else "cpu",
                }
            )
        return result
    except Exception as exc:
        return {
            "python_ready": False,
            "python_error": f"{type(exc).__name__}: {exc}",
            "torch_version": None,
            "cuda_available": False,
            "cuda_version": None,
            "gpu_name": None,
            "vram_gb": None,
            "compute_capability": None,
            "recommended_mode": "cpu",
        }



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


def reference_cache_signature(audio_path: Path, transcript: str) -> str:
    stat = audio_path.stat()
    digest = hashlib.sha1(transcript.encode("utf-8")).hexdigest()[:12]
    return f"{stat.st_mtime_ns}:{stat.st_size}:{digest}"


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

        # Official capability starts around 3 s. Community workflows commonly
        # report practical success in roughly the 7–30 s range.
        if 8.0 <= duration <= 25.0:
            score += 30
        elif 5.0 <= duration < 8.0 or 25.0 < duration <= 35.0:
            score += 24
            notes.append("La duración es utilizable; 8–25 s suele ser un rango práctico.")
        elif 3.0 <= duration < 5.0:
            score += 15
            notes.append("Qwen puede clonar desde ~3 s, pero una referencia algo más larga suele ser más estable.")
        elif duration < 3.0:
            score += 5
            notes.append("Referencia muy corta: intenta usar al menos 3 s y preferiblemente más.")
        else:
            score += 14
            notes.append("Referencia larga: prioriza 8–25 s del estilo de voz que realmente quieres conservar.")

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

        if transcript.strip():
            score += 35
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
        }


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


def get_voice_reference_info(audio_path: Path) -> dict:
    try:
        _, metadata = prepare_reference_audio(audio_path, force=False)
        return metadata
    except Exception as exc:
        transcript = ""
        sidecar = transcript_path(audio_path)
        if sidecar.exists():
            transcript = sidecar.read_text(encoding="utf-8", errors="ignore").strip()
        analysis = analyze_reference_audio(audio_path, transcript)
        return {
            "quality_score": analysis["quality_score"],
            "quality_label": analysis["quality_label"],
            "notes": analysis["notes"],
            "original": analysis,
            "prepared_analysis": analysis,
            "has_transcript": bool(transcript),
            "transcript": transcript,
        }


def split_text_for_tts(text: str, max_chars: int = 460) -> list[str]:
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


def estimate_max_new_tokens(text: str) -> int:
    words = max(1, len(re.findall(r"\b\w+\b", text, flags=re.UNICODE)))
    # 12 Hz audio tokenizer. Rough margin based on normal Spanish speech rates.
    return int(clamp(words * 6 + 160, 384, 2048))


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


class ModelManager:
    def __init__(self) -> None:
        self.model = None
        self.backend: Optional[str] = None
        self.model_id: Optional[str] = None
        self.load_lock = threading.Lock()
        self.generate_lock = threading.Lock()
        self.prompt_cache: dict[str, object] = {}

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
        info = torch_info()
        if requested == "cpu":
            return "cpu"
        if requested == "cuda":
            if not info.get("cuda_available"):
                raise RuntimeError("CUDA no está disponible en este equipo.")
            return "cuda"

        model_info = SUPPORTED_MODELS.get(model_id) or {}
        required = float(model_info.get("gpu_vram_recommended_gb", 5.5))
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

            if target == "cuda":
                dtype = torch.float16
                device_map = "cuda:0"
            else:
                dtype = torch.float32
                device_map = "cpu"

            try:
                model = Qwen3TTSModel.from_pretrained(
                    model_id,
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
        transcript = ref_text or ""
        signature = metadata.get("signature", "")
        key = f"{self.model_id}|{backend}|{voice_path.stem}|{signature}"

        if key in self.prompt_cache:
            return self.prompt_cache[key], prepared_path

        prompt = model.create_voice_clone_prompt(
            ref_audio=str(prepared_path),
            ref_text=transcript or None,
            x_vector_only_mode=not bool(transcript),
        )
        self.prompt_cache[key] = prompt
        return prompt, prepared_path

    def generate(
        self,
        text: str,
        voice_path: Path,
        ref_text: Optional[str],
        language: str,
        requested_mode: str,
        generation: dict,
        model_id: str,
    ):
        with self.generate_lock:
            target = self.choose_backend(requested_mode, model_id)

            try:
                return self._generate_once(
                    text, voice_path, ref_text, language, target, generation, model_id
                )
            except Exception as first_error:
                is_auto_cuda = requested_mode == "auto" and target == "cuda"
                is_oom = "out of memory" in str(first_error).lower()

                if is_auto_cuda and is_oom:
                    STATUS.set(
                        "loading_model",
                        "Cambiando a CPU",
                        "La GPU se quedó sin memoria. Reintentando en modo compatible.",
                        "cpu",
                    )
                    self.unload()
                    return self._generate_once(
                        text, voice_path, ref_text, language, "cpu", generation, model_id
                    )

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

        prompt, prepared_path = self.get_clone_prompt(
            model=model,
            voice_path=voice_path,
            ref_text=ref_text,
            backend=actual_backend,
        )

        chunks = split_text_for_tts(text)
        outputs = []
        sample_rate = None

        for index, chunk in enumerate(chunks, start=1):
            STATUS.set(
                "generating",
                f"Generando locución {index}/{len(chunks)}",
                (
                    "Qwen está sintetizando la voz localmente."
                    if len(chunks) == 1
                    else "El texto largo se dividió por frases para reducir deriva."
                ),
                actual_backend,
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

        return combined, int(sample_rate or 24000), actual_backend


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
    output_format: Literal["wav", "flac"] = "wav"
    music_id: Optional[str] = None
    music_volume: float = 0.18


class TranscriptUpdate(BaseModel):
    transcript: str = ""


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
        items.append(item)
    return items


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "model": DEFAULT_MODEL_ID,
        "data_root": str(DATA_ROOT),
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
    direct = [supported_model_payload(model_id) for model_id in SUPPORTED_MODELS]
    discovery = []
    for item in CURATED_DISCOVERY_MODELS:
        row = dict(item)
        row["avatar_url"] = huggingface_author_avatar(row.get("author", ""))
        row["hub_url"] = f"https://huggingface.co/{row['id']}"
        discovery.append(row)
    return {
        "recommended_id": DEFAULT_MODEL_ID,
        "compatible": direct,
        "discovery": discovery,
    }


@app.get("/api/models/search")
def model_search(q: str = "", limit: int = 16):
    return {
        "query": q,
        "results": search_huggingface_models(q, max(1, min(limit, 24))),
    }


@app.get("/api/history")
def history():
    return load_history()


@app.delete("/api/history")
def clear_history():
    save_history([])
    return {"ok": True}


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
    media = "audio/flac" if path.suffix.lower() == ".flac" else "audio/wav"
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
        wav, sample_rate, backend = MODEL_MANAGER.generate(
            text=text,
            voice_path=voice_path,
            ref_text=ref_text,
            language=request.language,
            requested_mode=request.mode,
            generation=generation,
            model_id=request.model_id,
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

        import soundfile as sf

        extension = request.output_format
        filename = f"locucion_{int(time.time())}_{uuid.uuid4().hex[:5]}.{extension}"
        output_path = OUTPUTS_DIR / filename

        if extension == "flac":
            sf.write(str(output_path), wav, sample_rate, format="FLAC")
        else:
            sf.write(str(output_path), wav, sample_rate, format="WAV")

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
            "url": f"/api/outputs/{filename}",
            "used_transcript": bool(ref_text),
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
            "used_transcript": bool(ref_text),
            "history": history_item,
            "qwen_sampling": generation,
        }
    except Exception as exc:
        STATUS.set(
            "error",
            "Error del motor",
            f"{type(exc).__name__}: {exc}",
            MODEL_MANAGER.backend,
        )
        raise HTTPException(
            status_code=500,
            detail=f"{type(exc).__name__}: {exc}",
        ) from exc


def packaging_self_test() -> int:
    """
    Lightweight packaged-runtime test.
    It intentionally does NOT download a model. It verifies that the frozen
    engine can import the exact runtime stack needed before NSIS is attempted.
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
    check("torch", lambda: __import__("torch").__version__)
    check("transformers", lambda: __import__("transformers").__version__)
    check("accelerate", lambda: __import__("accelerate").__version__)
    check("huggingface_hub", lambda: __import__("huggingface_hub").__version__)

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


if __name__ == "__main__":
    if "--self-test-packaging" in sys.argv:
        raise SystemExit(packaging_self_test())

    import uvicorn

    print()
    print("Qwen Voice Studio - Local Engine")
    print(f"Data: {DATA_ROOT}")
    print(f"API:  http://127.0.0.1:{PORT}")
    print()

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=PORT,
        log_level="info",
    )
