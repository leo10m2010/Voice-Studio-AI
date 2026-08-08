from __future__ import annotations

import json
import re
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf


def _clean_stem(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"[^A-Za-z0-9À-ÿ _.-]+", "", stem).strip()
    stem = re.sub(r"\s+", "_", stem)
    return stem or "audio"


def sniff_obvious_non_audio(path: Path) -> str | None:
    try:
        head = path.read_bytes()[:4096]
    except OSError:
        return "No se pudo leer el archivo."

    if not head:
        return "El archivo está vacío."

    lower = head.lstrip().lower()
    if (
        lower.startswith(b"<!doctype html")
        or lower.startswith(b"<html")
        or lower.startswith(b"<?xml")
        or lower.startswith(b"{")
        or lower.startswith(b"[")
    ):
        return "El archivo parece contener HTML/JSON/texto y no audio."

    return None


def decode_audio_file(path: Path, target_sr: int = 44100) -> tuple[np.ndarray, int]:
    path = Path(path)
    obvious = sniff_obvious_non_audio(path)
    if obvious:
        raise RuntimeError(obvious)

    # Read by actual container/header first, not by extension.
    try:
        data, sr = sf.read(str(path), dtype="float32", always_2d=True)
        if data.size and sr > 0:
            if sr != target_sr:
                channels = [
                    librosa.resample(
                        data[:, ch],
                        orig_sr=sr,
                        target_sr=target_sr,
                    )
                    for ch in range(data.shape[1])
                ]
                n = min(len(ch) for ch in channels)
                data = np.stack([ch[:n] for ch in channels], axis=1)
                sr = target_sr
            return np.asarray(data, dtype=np.float32), int(sr)
    except Exception:
        pass

    # Codec fallback.
    try:
        y, sr = librosa.load(
            str(path),
            sr=target_sr,
            mono=False,
            dtype=np.float32,
        )
    except Exception as exc:
        raise RuntimeError(
            "No se pudo decodificar como audio válido. "
            "Puede estar dañado, tener una extensión incorrecta "
            "o no ser realmente MP3/WAV/FLAC/OGG."
        ) from exc

    y = np.asarray(y, dtype=np.float32)
    if not y.size:
        raise RuntimeError("El archivo de audio está vacío.")

    if y.ndim == 1:
        data = y[:, None]
    elif y.ndim == 2:
        data = y.T
    else:
        raise RuntimeError("Distribución de canales no compatible.")

    return data.astype(np.float32), int(sr)


def _prepare_pcm(data: np.ndarray) -> np.ndarray:
    data = np.asarray(data, dtype=np.float32)
    data = np.nan_to_num(data, nan=0.0, posinf=0.0, neginf=0.0)

    if data.ndim == 1:
        data = data[:, None]

    if data.shape[1] > 2:
        data = data[:, :2]

    data = data - np.mean(data, axis=0, keepdims=True)

    peak = float(np.max(np.abs(data))) if data.size else 0.0
    if peak > 0.985:
        data *= 0.985 / peak

    return data.astype(np.float32)


def transcode_music_to_wav(
    source_path: Path,
    destination_dir: Path,
    original_name: str | None = None,
    target_sr: int = 44100,
) -> dict:
    source_path = Path(source_path)
    destination_dir = Path(destination_dir)
    destination_dir.mkdir(parents=True, exist_ok=True)

    data, sr = decode_audio_file(source_path, target_sr=target_sr)
    data = _prepare_pcm(data)

    if data.shape[0] < int(sr * 0.10):
        raise RuntimeError("La música es demasiado corta.")

    stem = _clean_stem(original_name or source_path.name)
    used_stems = {
        path.stem.casefold()
        for path in destination_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".wav", ".mp3", ".flac", ".ogg"}
    }
    candidate = stem
    i = 2
    while candidate.casefold() in used_stems:
        candidate = f"{stem}_{i}"
        i += 1
    target = destination_dir / f"{candidate}.wav"

    sf.write(str(target), data, sr, format="WAV", subtype="PCM_16")

    try:
        info = sf.info(str(target))
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise RuntimeError("Falló la validación del WAV interno.") from exc

    metadata = {
        "source_name": original_name or source_path.name,
        "canonical_filename": target.name,
        "duration": round(float(info.duration), 3),
        "sample_rate": int(info.samplerate),
        "channels": int(info.channels),
        "format": str(info.format),
        "subtype": str(info.subtype),
    }

    target.with_suffix(target.suffix + ".meta.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {"path": target, "metadata": metadata}


def validate_canonical_music(path: Path) -> tuple[bool, str | None, dict | None]:
    try:
        info = sf.info(str(path))
        if info.frames <= 0 or info.samplerate <= 0:
            return False, "No contiene muestras de audio válidas.", None
        return True, None, {
            "duration": float(info.duration),
            "sample_rate": int(info.samplerate),
            "channels": int(info.channels),
            "format": str(info.format),
            "subtype": str(info.subtype),
        }
    except Exception:
        return False, (
            "No se puede decodificar. El archivo puede estar dañado "
            "o su extensión no corresponde al contenido."
        ), None
