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


_INTRO_SECONDS = 2.8
"""Music alone before the voice comes in (the classic radio-spot opener)."""

_OUTRO_SECONDS = 3.4
"""Music alone after the voice ends, fade-out included."""

_INTRO_FADE_SECONDS = 0.35
_DUCK_SECONDS = 0.50
_LIFT_SECONDS = 0.60
_OUTRO_FADE_SECONDS = 1.80

_LEAD_OVER_BED = 3.2
"""
How much louder the exposed intro/outro is than the bed under the voice
(~10 dB, the usual ducking depth on radio). The user's volume stays the
level they hear under the voice, which is the one they actually tune;
below 2.5x the opener came out clearly quieter than the voice and did not
read as a spot opener at all.
"""

_LEAD_CEILING = 1.30


def _ramp(start: float, end: float, length: int) -> np.ndarray:
    if length <= 0:
        return np.zeros(0, dtype=np.float32)
    if length == 1:
        return np.full(1, end, dtype=np.float32)

    # Raised cosine: no audible corner at either end of the move.
    t = np.linspace(0.0, 1.0, length, dtype=np.float32)
    shape = (1.0 - np.cos(np.pi * t)) / 2.0
    return (start + (end - start) * shape).astype(np.float32)


def _spot_envelope(
    intro_samples: int,
    voice_samples: int,
    outro_samples: int,
    sample_rate: int,
    bed_level: float,
    lead_level: float,
) -> np.ndarray:
    """
    Spot shape: music on its own, duck under the voice, come back up and
    fade out at the end.
    """
    total = intro_samples + voice_samples + outro_samples
    envelope = np.full(total, bed_level, dtype=np.float32)

    duck = min(int(sample_rate * _DUCK_SECONDS), intro_samples)
    lift = min(int(sample_rate * _LIFT_SECONDS), outro_samples)
    fade_in = min(int(sample_rate * _INTRO_FADE_SECONDS), intro_samples - duck)
    fade_out = min(int(sample_rate * _OUTRO_FADE_SECONDS), outro_samples - lift)

    duck_start = intro_samples - duck
    envelope[:duck_start] = lead_level
    if fade_in > 1:
        envelope[:fade_in] = _ramp(0.0, lead_level, fade_in)
    if duck > 0:
        envelope[duck_start:intro_samples] = _ramp(lead_level, bed_level, duck)

    voice_end = intro_samples + voice_samples
    envelope[intro_samples:voice_end] = bed_level

    if lift > 0:
        envelope[voice_end:voice_end + lift] = _ramp(bed_level, lead_level, lift)
    envelope[voice_end + lift:] = lead_level
    if fade_out > 1:
        envelope[total - fade_out:] = _ramp(lead_level, 0.0, fade_out)

    return envelope


def mix_voice_with_music(
    voice_wav,
    sample_rate: int,
    music_path: Path,
    music_volume: float = 0.18,
) -> np.ndarray:
    """
    Mix a generated mono voice with stereo background music, arranged as a
    radio spot: the music opens on its own for a couple of seconds, ducks
    under the voice, and comes back up for a few seconds at the end before
    fading out.

    Properties:
    - output = intro + voice + outro, so it is longer than the voice;
    - music is resampled to the voice sample rate;
    - short music loops automatically;
    - long music is trimmed;
    - music level is normalized before applying the user volume;
    - the user volume is the bed level under the voice; intro/outro sit above it;
    - with volume 0 there is nothing to expose, so no intro/outro is added;
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

    bed_level = float(np.clip(music_volume, 0.0, 0.60))
    lead_level = min(bed_level * _LEAD_OVER_BED, _LEAD_CEILING)

    voice_length = int(voice.shape[0])
    if bed_level <= 0.0:
        # Sin música audible, el intro y la cola serían solo silencio pegado.
        intro_samples = outro_samples = 0
    else:
        intro_samples = int(sample_rate * _INTRO_SECONDS)
        outro_samples = int(sample_rate * _OUTRO_SECONDS)

    target_length = intro_samples + voice_length + outro_samples

    if music.shape[1] < target_length:
        repeats = int(np.ceil(target_length / music.shape[1]))
        music = np.tile(music, (1, repeats))

    music = music[:, :target_length]
    music = _normalize_music(music)

    music *= _spot_envelope(
        intro_samples=intro_samples,
        voice_samples=voice_length,
        outro_samples=outro_samples,
        sample_rate=sample_rate,
        bed_level=bed_level,
        lead_level=lead_level,
    )[None, :]

    if intro_samples or outro_samples:
        voice = np.concatenate(
            [
                np.zeros(intro_samples, dtype=np.float32),
                voice,
                np.zeros(outro_samples, dtype=np.float32),
            ]
        )

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
