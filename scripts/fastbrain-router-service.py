#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
import socketserver
import urllib.parse
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from fastbrain.app import build


class UnixHTTPServer(socketserver.UnixStreamServer):
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    server_version = "FastBrainRouter/1"

    def log_message(self, fmt, *args):
        return

    def _send(self, code: int, payload: dict):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True, "status": "ready"})
        else:
            self._send(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        if self.path != "/route":
            self._send(404, {"ok": False, "error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or 0)
            body = self.rfile.read(length).decode("utf-8")
            form = urllib.parse.parse_qs(body, keep_blank_values=True)
            text = (form.get("text") or [""])[0].strip()
            if not text:
                self._send(400, {"ok": False, "error": "empty_text"})
                return
            dry_run = (form.get("dry_run") or ["0"])[0] in {"1", "true", "yes"}
            execute = (form.get("execute") or ["0"])[0] in {"1", "true", "yes"}
            stack = self.server.stack
            result = stack["engine"].route(text)
            payload = result.to_dict()
            if execute or dry_run:
                payload["execution"] = stack["executor"].execute(result, dry_run=dry_run)
            self._send(200, payload)
        except Exception as exc:
            self._send(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--socket", required=True)
    args = p.parse_args()
    sock = Path(args.socket).expanduser()
    sock.parent.mkdir(parents=True, exist_ok=True)
    try:
        sock.unlink()
    except FileNotFoundError:
        pass
    stack = build()
    server = UnixHTTPServer(str(sock), Handler)
    server.stack = stack
    os.chmod(sock, 0o600)
    print(json.dumps({"ready": True, "socket": str(sock)}), flush=True)
    try:
        server.serve_forever(poll_interval=0.1)
    finally:
        server.server_close()
        try:
            stack["db"].close()
        except Exception:
            pass
        try:
            sock.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
