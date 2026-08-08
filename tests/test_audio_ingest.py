from __future__ import annotations
import sys, tempfile, unittest
from pathlib import Path
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"engine"))
from audio_ingest import transcode_music_to_wav

class AudioIngestTests(unittest.TestCase):
    def test_wav_disguised_as_mp3_is_read_by_content(self):
        sr=22050
        t=np.arange(sr)/sr
        audio=(.2*np.sin(2*np.pi*440*t)).astype(np.float32)
        with tempfile.TemporaryDirectory() as td:
            td=Path(td)
            real=td/"a.wav"; fake=td/"a.mp3"
            sf.write(real,audio,sr); fake.write_bytes(real.read_bytes())
            result=transcode_music_to_wav(fake,td/"out",original_name="a.mp3")
            info=sf.info(result["path"])
            self.assertEqual(info.samplerate,44100)
            self.assertGreater(info.frames,1000)

    def test_html_saved_as_mp3_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); bad=td/"error.mp3"
            bad.write_text("<!doctype html><html>404</html>",encoding="utf-8")
            with self.assertRaises(RuntimeError) as ctx:
                transcode_music_to_wav(bad,td/"out")
            self.assertIn("no audio",str(ctx.exception).lower())

    def test_stereo_roundtrip(self):
        sr=44100
        t=np.arange(sr//2)/sr
        audio=np.stack([.1*np.sin(2*np.pi*330*t),.1*np.sin(2*np.pi*550*t)],axis=1).astype(np.float32)
        with tempfile.TemporaryDirectory() as td:
            td=Path(td); src=td/"s.wav"; sf.write(src,audio,sr)
            result=transcode_music_to_wav(src,td/"out")
            info=sf.info(result["path"])
            self.assertEqual(info.channels,2)
            self.assertEqual(info.samplerate,44100)

if __name__=="__main__":
    unittest.main()
