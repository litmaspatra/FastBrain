#!/usr/bin/env python3
"""Natural voice for the Hermes Mobile app: Piper TTS (open source, ONNX, CPU only, 20-65 MB per voice) on 127.0.0.1:8766.

Setup (once; see scripts/setup-piper.sh, which does all of this):
    pip install piper-tts
    python -m piper.download_voices --download-dir ~/.piper-voices en_US-lessac-medium
Run:
    python ~/FastBrain/scripts/piper-tts-server.py

POST /tts  (form: text, speed, voice) -> audio/wav, 16-bit mono.   GET /voices -> installed voice names, one per line.
GET /health.  Only callers that send X-Hermes-Mobile-Key (the app's key, Termux's ~/.hermes-mobile/key) are served.
The app cuts a reply into short phrases and sets a pace for each; this server speaks one phrase at a time.
"""
from __future__ import annotations

import argparse
import hmac
import io
import os
import re
import threading
import urllib.parse
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

def default_key_file() -> str:
    """The app writes its key to Termux's home; inside the Debian proot that is this absolute path (as the Hermes plugin uses)."""
    for c in (os.environ.get("HERMES_MOBILE_KEY_FILE", ""), "/data/data/com.termux/files/home/.hermes-mobile/key", str(Path.home() / ".hermes-mobile" / "key")):
        if c and Path(c).is_file():
            return c
    return "/data/data/com.termux/files/home/.hermes-mobile/key"


VOICE_RE = re.compile(r"^[a-z]{2,3}_[A-Za-z]{2,4}-[A-Za-z0-9_]+-(?:x_low|low|medium|high)$")
DEFAULT_VOICE = "en_US-lessac-medium"

_voices: dict = {}
_lock = threading.Lock()  # one synthesis at a time: a phone has few cores, and sessions are not shared


def default_dirs() -> list[Path]:
    home = Path.home()
    env = os.environ.get("PIPER_VOICES_DIR", "")
    return [Path(d) for d in ([env] if env else []) + [str(home / ".piper-voices"), str(home / "piper-voices"),
                                                       str(home / ".hermes" / "cache" / "piper-voices"), str(home / "FastBrain" / "piper-voices")]]


def catalog(dirs: list[Path]) -> dict[str, Path]:
    """name -> .onnx path for every usable voice (the .onnx.json next to it exists), looking in each folder and one level down."""
    found: dict[str, Path] = {}
    for d in dirs:
        for pat in ("*.onnx", "*/*.onnx"):
            for p in sorted(d.glob(pat)):
                if VOICE_RE.match(p.stem) and p.with_name(p.name + ".json").exists():
                    found.setdefault(p.stem, p)
    return found


def installed(dirs: list[Path]) -> list[str]:
    return sorted(catalog(dirs))


def get_voice(dirs: list[Path], name: str):
    cat = catalog(dirs)
    if name not in cat:
        name = DEFAULT_VOICE if DEFAULT_VOICE in cat else (sorted(cat)[0] if cat else "")
    if not name:
        return None, ""
    if name not in _voices:
        from piper import PiperVoice
        _voices[name] = PiperVoice.load(cat[name])
    return _voices[name], name


def synth(voice, text: str, speed: float) -> bytes:
    """One phrase as 16-bit mono WAV, silence trimmed at both ends (the app adds its own pauses)."""
    import numpy as np
    from piper import SynthesisConfig
    cfg = SynthesisConfig(length_scale=1.0 / max(0.5, min(1.6, speed)), noise_w_scale=0.9)
    parts, rate = [], 22050
    for chunk in voice.synthesize(text, cfg):
        rate = chunk.sample_rate
        parts.append(np.asarray(chunk.audio_float_array, dtype="float32").reshape(-1))
    a = np.concatenate(parts) if parts else np.zeros(0, dtype="float32")
    idx = np.flatnonzero(np.abs(a) > 0.01)
    if idx.size:
        a = a[max(0, idx[0] - int(rate * 0.01)): idx[-1] + int(rate * 0.02)]
    pcm = (np.clip(a, -1, 1) * 32767).astype("<i2").tobytes()
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return out.getvalue()


def make_handler(voices_dir: list[Path], key_path: Path):
    class H(BaseHTTPRequestHandler):
        timeout = 15

        def log_message(self, *a):
            return

        def _send(self, code, body, ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _ok(self):
            try:
                key = key_path.read_text().strip()
            except OSError:
                key = ""
            return bool(key) and hmac.compare_digest(key.encode(), self.headers.get("X-Hermes-Mobile-Key", "").encode())

        def do_GET(self):
            if self.path not in ("/health", "/voices"):
                return self._send(404, b"{}")
            if not self._ok():
                return self._send(403, b"{}")
            names = installed(voices_dir)
            if self.path == "/voices":
                return self._send(200, "\n".join(names).encode(), "text/plain")
            self._send(200 if names else 503, b'{"ok":true}' if names else b'{"ok":false,"error":"no_voice_installed"}')

        def do_POST(self):
            if self.path != "/tts":
                return self._send(404, b"{}")
            if not self._ok():
                return self._send(403, b"{}")
            try:
                n = int(self.headers.get("Content-Length", "0") or 0)
                if n <= 0 or n > 20000:
                    return self._send(413, b"{}")
                f = urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8", "replace"))
                text = (f.get("text") or [""])[0].strip()[:600]
                speed = float((f.get("speed") or ["1.0"])[0])
                if not text:
                    return self._send(400, b"{}")
                with _lock:
                    voice, _ = get_voice(voices_dir, (f.get("voice") or [DEFAULT_VOICE])[0])
                    if voice is None:
                        return self._send(503, b'{"error":"no_voice_installed"}')
                    wav = synth(voice, text, speed)
                self._send(200, wav, "audio/wav")
            except Exception as exc:
                self._send(500, ('{"error":"%s"}' % type(exc).__name__).encode())

    return H


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8766)
    p.add_argument("--voices-dir", action="append", help="folder with Piper voices (repeatable); by default ~/.piper-voices, ~/piper-voices, ~/.hermes/cache/piper-voices, ~/FastBrain/piper-voices")
    p.add_argument("--key-file", default=default_key_file())
    a = p.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler([Path(d) for d in a.voices_dir] if a.voices_dir else default_dirs(), Path(a.key_file)))
    srv.daemon_threads = True
    print(f"piper tts server on 127.0.0.1:{a.port}, voices: {installed([Path(d) for d in a.voices_dir] if a.voices_dir else default_dirs())}", flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
