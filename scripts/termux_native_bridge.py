#!/usr/bin/env python3
"""Native Termux HTTP bridge for FastBrain.

This service is intentionally tiny: it binds only loopback, authenticates each
request, verifies cryptographic confirmation proofs for sensitive actions, and
runs a fixed Termux:API allowlist with subprocess argument arrays.
"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import stat
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable


TERMUX_BIN = Path("/data/data/com.termux/files/usr/bin")
APP_PACKAGES = {
    "whatsapp": "com.whatsapp",
    "telegram": "org.telegram.messenger",
    "maps": "com.google.android.apps.maps",
    "settings": "com.android.settings",
}
SENSITIVE = {"flashlight", "launch_app", "contacts", "sms"}
TIMEOUTS = {"battery": 4.0, "flashlight": 2.5, "launch_app": 3.0, "contacts": 4.0, "sms": 6.0}
PHONE = re.compile(r"^\+?[0-9][0-9 .()\-]{2,40}$")


class BridgeCore:
    def __init__(
        self,
        auth_token: str,
        confirmation_key: str,
        command_dir: str | Path = TERMUX_BIN,
        runner: Callable[..., Any] = subprocess.run,
        clock: Callable[[], float] = time.time,
    ):
        if len(auth_token) < 24 or len(confirmation_key) < 24:
            raise ValueError("bridge secrets must be at least 24 characters")
        self.auth_token = auth_token
        self.confirmation_key = confirmation_key
        self.command_dir = Path(command_dir)
        self.runner = runner
        self.clock = clock
        self.used_nonces: dict[str, float] = {}

    def _command(self, name: str) -> str | None:
        path = self.command_dir / name
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None

    def authenticated(self, supplied_token: str | None) -> bool:
        return isinstance(supplied_token, str) and hmac.compare_digest(self.auth_token, supplied_token)

    @staticmethod
    def _norm_name(value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", value.lower()))

    @staticmethod
    def _canonical(operation: str, args: dict[str, Any], issued_at: int, nonce: str) -> bytes:
        return json.dumps(
            {"operation": operation, "args": args, "issued_at": issued_at, "nonce": nonce},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    def _verify_confirmation(self, operation: str, args: dict[str, Any], proof: Any) -> str | None:
        if not isinstance(proof, dict):
            return "confirmation_required"
        issued_at = proof.get("issued_at")
        nonce = proof.get("nonce")
        mac = proof.get("mac")
        if not isinstance(issued_at, int) or not isinstance(nonce, str) or not isinstance(mac, str) or len(nonce) < 16:
            return "confirmation_invalid"
        now = self.clock()
        if abs(now - issued_at) > 60:
            return "confirmation_expired"
        self.used_nonces = {key: expiry for key, expiry in self.used_nonces.items() if expiry > now}
        if nonce in self.used_nonces:
            return "confirmation_replayed"
        expected = hmac.new(
            self.confirmation_key.encode("utf-8"),
            self._canonical(operation, args, issued_at, nonce),
            "sha256",
        ).hexdigest()
        if not hmac.compare_digest(expected, mac):
            return "confirmation_invalid"
        self.used_nonces[nonce] = now + 60
        return None

    def _validate(self, operation: Any, raw_args: Any) -> tuple[dict[str, Any] | None, str | None]:
        if operation not in TIMEOUTS:
            return None, "operation_not_allowed"
        if not isinstance(raw_args, dict):
            return None, "invalid_arguments"
        if operation in {"battery", "contacts"}:
            return ({}, None) if not raw_args else (None, "invalid_arguments")
        if operation == "flashlight":
            state = raw_args.get("state")
            return ({"state": state}, None) if set(raw_args) == {"state"} and state in {"on", "off"} else (None, "invalid_arguments")
        if operation == "launch_app":
            app = " ".join(str(raw_args.get("app") or "").lower().split())
            return ({"app": app}, None) if set(raw_args) == {"app"} and app in APP_PACKAGES else (None, "invalid_arguments")
        contact = str(raw_args.get("contact") or "").strip()
        message = str(raw_args.get("message") or "")
        if set(raw_args) != {"contact", "message"} or not contact or not message or len(contact) > 100 or len(message) > 1600:
            return None, "invalid_arguments"
        return {"contact": contact, "message": message}, None

    def _run(self, argv: list[str], operation: str) -> tuple[int, dict[str, Any]]:
        try:
            proc = self.runner(argv, capture_output=True, text=True, timeout=TIMEOUTS[operation])
        except subprocess.TimeoutExpired:
            return 504, {"success": False, "error": "operation_timeout", "operation": operation}
        except OSError as exc:
            return 503, {"success": False, "error": f"command_unavailable: {exc}", "operation": operation}
        payload = {
            "success": proc.returncode == 0,
            "operation": operation,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[-1000:],
            "stderr": (proc.stderr or "")[-1000:],
        }
        return (200 if proc.returncode == 0 else 502), payload

    def _phone_for_contact(self, contact: str) -> tuple[str | None, str | None]:
        if PHONE.fullmatch(contact):
            return contact, None
        command = self._command("termux-contact-list")
        if not command:
            return None, "contact_lookup_unavailable"
        code, result = self._run([command], "contacts")
        if code != 200:
            return None, result.get("error", "contact_lookup_failed")
        try:
            entries = json.loads(result.get("stdout") or "[]")
        except json.JSONDecodeError:
            return None, "contact_lookup_invalid_json"
        wanted = self._norm_name(contact)
        numbers: set[str] = set()
        for item in entries if isinstance(entries, list) else []:
            if not isinstance(item, dict) or self._norm_name(str(item.get("name") or "")) != wanted:
                continue
            values = [item.get("number"), item.get("phone_number")]
            if isinstance(item.get("phones"), list):
                values.extend(item["phones"])
            for value in values:
                number = str(value or "").strip()
                if PHONE.fullmatch(number):
                    numbers.add(number)
        if not numbers:
            return None, "contact_not_found"
        if len(numbers) != 1:
            return None, "contact_ambiguous"
        return next(iter(numbers)), None

    def handle(self, supplied_token: str | None, request: Any) -> tuple[int, dict[str, Any]]:
        if not self.authenticated(supplied_token):
            return 401, {"success": False, "error": "unauthorized"}
        if not isinstance(request, dict) or set(request) - {"operation", "args", "confirmation"}:
            return 400, {"success": False, "error": "invalid_request"}
        operation = request.get("operation")
        args, error = self._validate(operation, request.get("args"))
        if error:
            return 400, {"success": False, "error": error}
        if operation in SENSITIVE:
            error = self._verify_confirmation(operation, args, request.get("confirmation"))
            if error:
                return 403, {"success": False, "error": error, "operation": operation}
        if operation == "battery":
            command = self._command("termux-battery-status")
            return self._run([command], operation) if command else (503, {"success": False, "error": "command_unavailable: termux-battery-status", "operation": operation})
        if operation == "flashlight":
            command = self._command("termux-torch")
            return self._run([command, args["state"]], operation) if command else (503, {"success": False, "error": "command_unavailable: termux-torch", "operation": operation})
        if operation == "launch_app":
            command = self._command("termux-open")
            if not command:
                return 503, {"success": False, "error": "command_unavailable: termux-open", "operation": operation}
            return self._run([command, f"intent:#Intent;package={APP_PACKAGES[args['app']]};end"], operation)
        if operation == "contacts":
            command = self._command("termux-contact-list")
            return self._run([command], operation) if command else (503, {"success": False, "error": "command_unavailable: termux-contact-list", "operation": operation})
        number, error = self._phone_for_contact(args["contact"])
        if error:
            return 422, {"success": False, "error": error, "operation": operation}
        command = self._command("termux-sms-send")
        return self._run([command, "-n", number, args["message"]], operation) if command else (503, {"success": False, "error": "command_unavailable: termux-sms-send", "operation": operation})


def _secret(path: str) -> str:
    file = Path(path)
    mode = stat.S_IMODE(file.stat().st_mode)
    if mode & 0o077:
        raise ValueError(f"secret file permissions must be 0600 or stricter: {file}")
    value = file.read_text(encoding="utf-8").strip()
    if len(value) < 24:
        raise ValueError(f"secret file is too short: {file}")
    return value


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _claim_pid(path: str | Path, pid: int) -> Path:
    file = Path(path)
    file.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        try:
            existing = int(file.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            existing = 0
        if existing and _pid_alive(existing):
            raise RuntimeError(f"native bridge already running with pid {existing}")
        file.unlink(missing_ok=True)
        fd = os.open(file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(f"{pid}\n")
    return file


def _shutdown_timer(server: Any, seconds: float) -> threading.Timer:
    timer = threading.Timer(seconds, server.shutdown)
    timer.daemon = True
    timer.start()
    return timer


def make_handler(core: BridgeCore):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *_args: Any) -> None:
            return

        def _reply(self, code: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path != "/health":
                self.send_error(404)
                return
            if not core.authenticated(self.headers.get("X-FastBrain-Token")):
                self._reply(401, {"success": False, "error": "unauthorized"})
                return
            self._reply(200, {"ok": True})

        def do_POST(self) -> None:
            if self.path == "/shutdown":
                if not core.authenticated(self.headers.get("X-FastBrain-Token")):
                    self._reply(401, {"success": False, "error": "unauthorized"})
                    return
                self._reply(200, {"ok": True, "status": "shutdown_requested"})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if self.path != "/v1/action":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 8192:
                    raise ValueError("invalid request size")
                request = json.loads(self.rfile.read(length))
            except Exception:
                code, payload = 400, {"success": False, "error": "invalid_json"}
            else:
                code, payload = core.handle(self.headers.get("X-FastBrain-Token"), request)
            self._reply(code, payload)
    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="FastBrain native Termux allowlist bridge")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--auth-token-file", required=True)
    parser.add_argument("--confirmation-key-file", required=True)
    parser.add_argument("--pid-file", default="/data/data/com.termux/files/home/.fastbrain-native-bridge/bridge.pid")
    parser.add_argument("--run-seconds", type=float, default=0.0, help="bounded test-only lifetime; 0 runs until stopped")
    args = parser.parse_args()
    if args.host != "127.0.0.1" or not 1 <= args.port <= 65535:
        parser.error("bridge binds only to 127.0.0.1 with a valid port")
    if not 0.0 <= args.run_seconds <= 120.0:
        parser.error("run-seconds must be between 0 and 120")
    core = BridgeCore(_secret(args.auth_token_file), _secret(args.confirmation_key_file))
    try:
        pid_file = _claim_pid(args.pid_file, os.getpid())
    except RuntimeError as exc:
        parser.error(str(exc))
    server = ThreadingHTTPServer((args.host, args.port), make_handler(core))
    try:
        if args.run_seconds:
            _shutdown_timer(server, args.run_seconds)
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
        try:
            if pid_file.read_text(encoding="utf-8").strip() == str(os.getpid()):
                pid_file.unlink(missing_ok=True)
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
