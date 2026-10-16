#!/usr/bin/env python3
"""Loopback TCP front for the FastBrain router, for the Hermes Mobile Android app.

The router listens on a Unix socket inside Termux's private folder, which other Android apps cannot open. This
exposes the same /route and /health on 127.0.0.1:8765, but ONLY to callers that send the app's key in the
X-Hermes-Mobile-Key header (the app writes the key to Termux's ~/.hermes-mobile/key). Any other app on the phone that
connects to the port gets 403, so it cannot make the phone call or message anyone.
"""
from __future__ import annotations

import argparse
import hmac
import os
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def default_key_file() -> str:
    """The app writes its key to Termux's home; inside the Debian proot that is this absolute path (as the Hermes plugin uses)."""
    for c in (os.environ.get("HERMES_MOBILE_KEY_FILE", ""), "/data/data/com.termux/files/home/.hermes-mobile/key", str(Path.home() / ".hermes-mobile" / "key")):
        if c and Path(c).is_file():
            return c
    return "/data/data/com.termux/files/home/.hermes-mobile/key"


def read_key(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def forward(sock_path: Path, raw: bytes, timeout: float) -> bytes:
    c = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    c.settimeout(timeout)
    try:
        c.connect(str(sock_path))
        c.sendall(raw)
        out = []
        while True:
            part = c.recv(65536)
            if not part:
                break
            out.append(part)
        return b"".join(out)
    finally:
        c.close()


def make_handler(sock_path: Path, key_path: Path, timeout: float):
    class H(BaseHTTPRequestHandler):
        server_version = "FastBrainTCP/1"
        timeout = 10

        def log_message(self, *a):
            return

        def _send(self, code: int, body: bytes, ctype="application/json; charset=utf-8"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorised(self) -> bool:
            key = read_key(key_path)  # re-read: the app may rewrite it
            got = self.headers.get("X-Hermes-Mobile-Key", "")
            return bool(key) and hmac.compare_digest(key.encode(), got.encode())

        def do_GET(self):
            if self.path != "/health":
                return self._send(404, b'{"ok":false,"error":"not_found"}')
            if not self._authorised():
                return self._send(403, b'{"ok":false,"error":"forbidden"}')
            self._send(200, b'{"ok":true,"status":"ready"}')

        def do_POST(self):
            if self.path != "/route":
                return self._send(404, b'{"ok":false,"error":"not_found"}')
            if not self._authorised():
                return self._send(403, b'{"ok":false,"error":"forbidden"}')
            try:
                n = int(self.headers.get("Content-Length", "0") or 0)
                if n < 0 or n > 65536:
                    return self._send(413, b'{"ok":false,"error":"too_large"}')
                body = self.rfile.read(n)
                req = (b"POST /route HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n"
                       b"Content-Type: application/x-www-form-urlencoded\r\n"
                       + f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
                raw = forward(sock_path, req, timeout)
                head, sep, payload = raw.partition(b"\r\n\r\n")
                if not sep:
                    return self._send(502, b'{"ok":false,"error":"bad_router_reply"}')
                code = int(head.split(b"\r\n", 1)[0].split()[1])
                self._send(code, payload)
            except OSError:
                self._send(503, b'{"ok":false,"error":"router_unavailable"}')
            except Exception as exc:  # never let one request stop the bridge
                self._send(500, ('{"ok":false,"error":"%s"}' % type(exc).__name__).encode())

    return H


def main() -> int:
    home = Path(os.environ.get("FASTBRAIN_HOME", Path.home() / ".fastbrain"))
    p = argparse.ArgumentParser()
    p.add_argument("--socket", default=os.environ.get("FASTBRAIN_ROUTER_SOCKET", str(home / "router" / "router.sock")))
    p.add_argument("--key-file", default=default_key_file())
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--timeout", type=float, default=24.0, help="seconds to wait for the router (actions can take a while)")
    a = p.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), make_handler(Path(a.socket).expanduser(), Path(a.key_file), a.timeout))
    srv.daemon_threads = True
    print(f"fastbrain tcp bridge on 127.0.0.1:{a.port}", flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
