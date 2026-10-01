#!/usr/bin/env python3
from __future__ import annotations

import argparse
import socket
import sys
import urllib.parse
from pathlib import Path


def request(sock_path: Path, text: str, dry_run: bool, execute: bool, timeout: float = 0.5) -> str:
    body = urllib.parse.urlencode({
        "text": text,
        "dry_run": "1" if dry_run else "0",
        "execute": "1" if execute else "0",
    }).encode("utf-8")
    req = (
        b"POST /route HTTP/1.1\r\n"
        b"Host: localhost\r\n"
        b"Connection: close\r\n"
        b"Content-Type: application/x-www-form-urlencoded\r\n"
        + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        + body
    )
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    try:
        client.connect(str(sock_path))
        client.sendall(req)
        chunks = []
        while True:
            part = client.recv(65536)
            if not part:
                break
            chunks.append(part)
    finally:
        client.close()
    raw = b"".join(chunks)
    head, sep, body_raw = raw.partition(b"\r\n\r\n")
    if not sep:
        raise RuntimeError("invalid router HTTP response")
    status_line = head.split(b"\r\n", 1)[0].decode("ascii", "replace")
    try:
        status = int(status_line.split()[1])
    except Exception as exc:
        raise RuntimeError(f"invalid router status: {status_line}") from exc
    payload = body_raw.decode("utf-8", "replace")
    if status < 200 or status >= 300:
        raise RuntimeError(payload or status_line)
    return payload


def main() -> int:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--socket", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--execute", action="store_true")
    p.add_argument("text", nargs="+")
    args = p.parse_args()
    text = " ".join(args.text).strip()
    if not text:
        return 2
    try:
        # Routing should be nearly instant, but --execute may run a real
        # Android helper for several seconds.
        timeout = 8.0 if args.execute else 0.5
        payload = request(
            Path(args.socket).expanduser(),
            text,
            args.dry_run,
            args.execute,
            timeout=timeout,
        )
    except Exception as exc:
        print(f"FASTBRAIN_ROUTER_CLIENT_ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3
    sys.stdout.write(payload)
    if not payload.endswith("\n"):
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
