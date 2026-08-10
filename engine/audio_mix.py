from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np


def _as_mono_voice(wav) -> np.ndarray:
    y = np.asarray(wav, dtype=np.float32).squeeze()
    if y.ndim == 0:
        return np.zeros(1, dtype=np.float32)
    if y.ndim == 1:
        return y

    # Defensive handling for either channels-first or samples-first.
    if y.shape[0] <= 8:
        return np.mean(y, axis=0, dtype=np.float32)
    return np.mean(y, axis=1, dtype=np.float32)


_MUSIC_DECODE_CACHE: dict[tuple, np.ndarray] = {}
_MUSIC_DECODE_CACHE_MAX = 12


def _decode_stereo_music(path: Path, sample_rate: int) -> np.ndarray:
    try:
        music, _ = librosa.load(
            str(path),
            sr=sample_rate,
            mono=False,
            dtype=np.float32,
        )
    except Exception as exc:
        raise RuntimeError(
            f"No se pudo leer la música '{path.name}'. "
            "Prueba con WAV, MP3, FLAC u OGG."
        ) from exc

    music = np.asarray(music, dtype=np.float32)

    if music.ndim == 1:
        return np.stack([music, music], axis=0)

    if music.ndim != 2:
        music = np.asarray(music).squeeze()
        if music.ndim == 1:
            return np.stack([music, music], axis=0)
        raise RuntimeError("La música tiene un formato de canales no compatible.")

    # librosa returns channels-first. Keep first two channels for the final stereo mix.
    if music.shape[0] == 1:
        return np.repeat(music, 2, axis=0)
    return music[:2]


def _as_stereo_music(path: Path, sample_rate: int) -> np.ndarray:
    """
    Same track/sample-rate combos get mixed repeatedly (background music picker,
    re-mixing a result with a new volume, etc.), so cache the decoded+resampled
    result instead of re-running librosa.load on every call. Keyed on mtime/size
    so replacing a file (e.g. re-importing under the same name) invalidates it.
    """
    try:
        stat = path.stat()
        cache_key = (str(path.resolve()), stat.st_mtime_ns, stat.st_size, sample_rate)
    except OSError:
        cache_key = None

    if cache_key is not None and cache_key in _MUSIC_DECODE_CACHE:
        return _MUSIC_DECODE_CACHE[cache_key].copy()

    result = _decode_stereo_music(path, sample_rate)

    if cache_key is not None:
        if len(_MUSIC_DECODE_CACHE) >= _MUSIC_DECODE_CACHE_MAX:
            _MUSIC_DECODE_CACHE.pop(next(iter(_MUSIC_DECODE_CACHE)))
        _MUSIC_DECODE_CACHE[cache_key] = result

    return result.copy()


def _normalize_music(music: np.ndarray, target_dbfs: float = -18.0) -> np.ndarray:
    if not music.size:
        return music

    rms = float(np.sqrt(np.mean(np.square(music), dtype=np.float64) + 1e-12))
    if rms < 1e-7:
        return music

    target = 10 ** (target_dbfs / 20.0)
    # Avoid extreme amplification of very quiet/noisy files.
    gain = min(target / rms, 3.0)
    return (music * gain).astype(np.float32)


def _fade_envelope(length: int, sample_rate: int) -> np.ndarray:
    envelope = np.ones(length, dtype=np.float32)
    if length <= 1:
        return envelope

    fade_in = min(length // 3, max(1, int(sample_rate * 0.22)))
    fade_out = min(length // 3, max(1, int(sample_rate * 0.45)))

    if fade_in > 1:
        envelope[:fade_in] = np.linspace(0.0, 1.0, fade_in, dtype=np.float32)
    if fade_out > 1:
        envelope[-fade_out:] = np.linspace(1.0, 0.0, fade_out, dtype=np.float32)

    return envelope


def mix_voice_with_music(
    voice_wav,
    sample_rate: int,
    music_path: Path,
    music_volume: float = 0.18,
) -> np.ndarray:
    """
    Mix a generated mono voice with stereo background music.

    Properties:
    - output duration exactly matches the generated voice;
    - music is resampled to the voice sample rate;
    - short music loops automatically;
    - long music is trimmed;
    - music gets a short fade-in/out;
    - music level is normalized before applying the user volume;
    - voice is centered in stereo;
    - final mix is softly limited to prevent clipping.

    Returns samples-first stereo: shape (samples, 2), suitable for soundfile.write().
    """
    if sample_rate <= 0:
        raise ValueError("sample_rate debe ser mayor que cero.")

    voice = _as_mono_voice(voice_wav)
    if voice.size == 0:
        raise RuntimeError("La locución generada está vacía.")

    music = _as_stereo_music(Path(music_path), sample_rate)
    if music.shape[1] == 0:
        raise RuntimeError("La música seleccionada está vacía.")

    target_length = int(voice.shape[0])

    if music.shape[1] < target_length:
        repeats = int(np.ceil(target_length / music.shape[1]))
        music = np.tile(music, (1, repeats))

    music = music[:, :target_length]
    music = _normalize_music(music)

    volume = float(np.clip(music_volume, 0.0, 0.60))
    music *= volume
    music *= _fade_envelope(target_length, sample_rate)[None, :]

    voice_stereo = np.stack([voice, voice], axis=0)
    mixed = voice_stereo + music

    # Transparent peak protection first.
    peak = float(np.max(np.abs(mixed))) if mixed.size else 0.0
    if peak > 0.985:
        mixed *= 0.985 / peak

    # Very mild soft limiting for occasional coincident transients.
    mixed = np.tanh(mixed * 1.03) / np.tanh(1.03)
    peak = float(np.max(np.abs(mixed))) if mixed.size else 0.0
    if peak > 0.985:
        mixed *= 0.985 / peak

    return mixed.T.astype(np.float32)
