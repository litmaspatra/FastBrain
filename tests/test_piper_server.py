import importlib.util
import io
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
spec = importlib.util.spec_from_file_location("piper_tts_server", Path(__file__).resolve().parents[1] / "scripts" / "piper-tts-server.py")
srv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(srv)


class FakePiper:
    def __init__(self):
        sys.modules["piper"] = SimpleNamespace(SynthesisConfig=lambda **kw: SimpleNamespace(**kw), PiperVoice=SimpleNamespace(load=lambda p: FakeVoice()))


class FakeVoice:
    def synthesize(self, text, cfg):
        import numpy as np
        self.cfg = cfg
        tone = (np.sin(np.linspace(0, 200, 2200)) * 0.5).astype("float32")
        yield SimpleNamespace(sample_rate=22050, audio_float_array=np.concatenate([np.zeros(500, "float32"), tone, np.zeros(500, "float32")]))


class T(unittest.TestCase):
    def test_voice_names_and_listing(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for n in ("en_US-lessac-medium", "bad name", "en_GB-alba-low"):
                (d / f"{n}.onnx").write_text("x")
                (d / f"{n}.onnx.json").write_text("{}")
            (d / "en_US-ryan-medium.onnx").write_text("x")  # no .json: not usable
            self.assertEqual(srv.installed(d), ["en_GB-alba-low", "en_US-lessac-medium"])

    def test_synth_trims_and_scales_speed(self):
        FakePiper()
        v = FakeVoice()
        wav = srv.synth(v, "hello", 1.25)
        self.assertAlmostEqual(v.cfg.length_scale, 0.8)
        with wave.open(io.BytesIO(wav)) as w:
            self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate()), (1, 2, 22050))
            self.assertLess(w.getnframes(), 3000)  # 3200 samples in; the silences were trimmed down to a short pad
            self.assertGreater(w.getnframes(), 2000)

    def test_unknown_voice_falls_back(self):
        FakePiper()
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "en_GB-alba-low.onnx").write_text("x")
            (d / "en_GB-alba-low.onnx.json").write_text("{}")
            srv._voices.clear()
            voice, name = srv.get_voice(d, "en_US-nobody-medium")
            self.assertEqual(name, "en_GB-alba-low")
            self.assertIsNotNone(voice)
            self.assertEqual(srv.get_voice(Path(tempfile.mkdtemp()), "x")[0], None)


if __name__ == "__main__":
    unittest.main()
