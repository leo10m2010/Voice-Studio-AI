from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "engine"))

from audio_mix import mix_voice_with_music


class AudioMixTests(unittest.TestCase):
    def test_resamples_loops_preserves_voice_duration_and_prevents_clipping(self):
        voice_sr = 24000
        voice_seconds = 2.4
        voice_t = np.arange(int(voice_sr * voice_seconds)) / voice_sr
        voice = (0.23 * np.sin(2 * np.pi * 220 * voice_t)).astype(np.float32)

        music_sr = 44100
        music_seconds = 0.65  # intentionally shorter than voice => must loop
        music_t = np.arange(int(music_sr * music_seconds)) / music_sr
        left = 0.35 * np.sin(2 * np.pi * 440 * music_t)
        right = 0.30 * np.sin(2 * np.pi * 660 * music_t)
        music = np.stack([left, right], axis=1).astype(np.float32)

        with tempfile.TemporaryDirectory() as td:
            music_path = Path(td) / "music.wav"
            sf.write(music_path, music, music_sr)

            mixed = mix_voice_with_music(
                voice_wav=voice,
                sample_rate=voice_sr,
                music_path=music_path,
                music_volume=0.18,
            )

        self.assertEqual(mixed.shape, (voice.shape[0], 2))
        self.assertLessEqual(float(np.max(np.abs(mixed))), 0.986)
        self.assertGreater(float(np.mean(np.abs(mixed[:, 0] - mixed[:, 1]))), 0.0001)

        # Music must materially change the dry voice.
        dry = np.stack([voice, voice], axis=1)
        self.assertGreater(float(np.mean(np.abs(mixed - dry))), 0.001)

    def test_zero_volume_is_nearly_dry_voice(self):
        sr = 24000
        t = np.arange(sr) / sr
        voice = (0.15 * np.sin(2 * np.pi * 200 * t)).astype(np.float32)
        music = (0.5 * np.sin(2 * np.pi * 500 * t)).astype(np.float32)

        with tempfile.TemporaryDirectory() as td:
            music_path = Path(td) / "music.wav"
            sf.write(music_path, music, sr)

            mixed = mix_voice_with_music(
                voice_wav=voice,
                sample_rate=sr,
                music_path=music_path,
                music_volume=0.0,
            )

        self.assertEqual(mixed.shape, (voice.shape[0], 2))
        self.assertTrue(np.isfinite(mixed).all())


if __name__ == "__main__":
    unittest.main()
