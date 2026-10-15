#!/usr/bin/env python3
"""Natural voice for the Hermes Mobile app: KittenTTS (open source, ~25 MB ONNX model, CPU only) on 127.0.0.1:8766.

Install (once, in the same Linux environment where Hermes/FastBrain run):
    pkg install espeak            # Termux; in Debian/Ubuntu proot: apt install espeak-ng
    pip install kittentts soundfile numpy onnxruntime
Run (the app starts using it as soon as it is up; without it the phone's own voice is used):
    python ~/FastBrain/scripts/kitten-tts-server.py
The first start downloads the model (needs internet once), later starts are offline.

POST /tts  (form: text, speed, voice) -> audio/wav, 16-bit mono.  GET /health.
Only callers that send X-Hermes-Mobile-Key (the app's key, ~/.hermes-mobile/key) are served.
The app cuts replies into short phrases and sets a pace and a pause for each; this server only speaks one phrase.
"""
from __future__ import annotations

import argparse
import hmac
import io
import threading
import urllib.parse
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VOICES = {"expr-voice-2-m", "expr-voice-2-f", "expr-voice-3-m", "expr-voice-3-f",
          "expr-voice-4-m", "expr-voice-4-f", "expr-voice-5-m", "expr-voice-5-f"}
RATE = 24000
_model = None
_ready = threading.Event()
_lock = threading.Lock()  # one synthesis at a time: the model isn't thread safe, the phone has few cores


def load_model():
    global _model
    from kittentts import KittenTTS
    try:
        _model = KittenTTS()
    except TypeError:
        _model = KittenTTS("KittenML/kitten-tts-nano-0.2")
    _ready.set()
    print("kitten tts model ready", flush=True)


def synth(text: str, voice: str, speed: float) -> bytes:
    import numpy as np
    with _lock:
        audio = _model.generate(text, voice=voice, speed=speed)
    a = np.asarray(audio, dtype="float32").reshape(-1)
    if a.size == 0:
        return b""
    loud = np.abs(a) > 0.01  # trim silence at both ends: the app adds its own pauses
    idx = np.flatnonzero(loud)
    if idx.size:
        a = a[max(0, idx[0] - 240): idx[-1] + 480]
    pcm = (np.clip(a, -1, 1) * 32767).astype("<i2").tobytes()
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    return out.getvalue()


def handler(key_path: Path):
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
            if self.path != "/health":
                return self._send(404, b"{}")
            if not self._ok():
                return self._send(403, b"{}")
            self._send(200 if _ready.is_set() else 503, b'{"ok":true}' if _ready.is_set() else b'{"ok":false,"status":"loading"}')

        def do_POST(self):
            if self.path != "/tts":
                return self._send(404, b"{}")
            if not self._ok():
                return self._send(403, b"{}")
            if not _ready.is_set():
                return self._send(503, b'{"error":"loading"}')
            try:
                n = int(self.headers.get("Content-Length", "0") or 0)
                if n <= 0 or n > 20000:
                    return self._send(413, b"{}")
                f = urllib.parse.parse_qs(self.rfile.read(n).decode("utf-8", "replace"))
                text = (f.get("text") or [""])[0].strip()[:600]
                voice = (f.get("voice") or ["expr-voice-2-f"])[0]
                speed = max(0.7, min(1.3, float((f.get("speed") or ["1.0"])[0])))
                if not text or voice not in VOICES:
                    return self._send(400, b"{}")
                self._send(200, synth(text, voice, speed), "audio/wav")
            except Exception as exc:
                self._send(500, ('{"error":"%s"}' % type(exc).__name__).encode())

    return H


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8766)
    p.add_argument("--key-file", default=str(Path.home() / ".hermes-mobile" / "key"))
    a = p.parse_args()
    threading.Thread(target=load_model, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), handler(Path(a.key_file)))
    srv.daemon_threads = True
    print(f"kitten tts server on 127.0.0.1:{a.port}", flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
