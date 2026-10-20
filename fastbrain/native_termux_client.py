"""Authenticated client for FastBrain's native Termux allowlist bridge."""
from __future__ import annotations

import hmac
import json
import secrets
import stat
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable


_ALLOWED = {"battery", "flashlight", "launch_app", "contacts", "sms"}
_SENSITIVE = {"flashlight", "launch_app", "contacts", "sms"}


class NativeTermuxClient:
    def __init__(
        self,
        url: str,
        auth_token_file: str | Path,
        confirmation_key_file: str | Path,
        opener: Callable[..., Any] = urllib.request.urlopen,
        clock: Callable[[], float] = time.time,
        timeout: float = 6.0,
    ):
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.path != "/v1/action":
            raise ValueError("native bridge URL must be http://127.0.0.1/.../v1/action")
        self.url = url
        self.auth_token = self._secret(auth_token_file)
        self.confirmation_key = self._secret(confirmation_key_file)
        self.opener = opener
        self.clock = clock
        self.timeout = max(0.1, min(float(timeout), 8.0))
        self.health_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "/health", "", "", ""))
        self.shutdown_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, "/shutdown", "", "", ""))

    @staticmethod
    def _secret(path: str | Path) -> str:
        file = Path(path)
        if stat.S_IMODE(file.stat().st_mode) & 0o077:
            raise ValueError(f"secret file permissions must be 0600 or stricter: {file}")
        value = file.read_text(encoding="utf-8").strip()
        if len(value) < 24:
            raise ValueError(f"secret file is too short: {file}")
        return value

    @staticmethod
    def _canonical(operation: str, args: dict[str, Any], issued_at: int, nonce: str) -> bytes:
        return json.dumps(
            {"operation": operation, "args": args, "issued_at": issued_at, "nonce": nonce},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    def call(self, operation: str, args: dict[str, Any], confirmed: bool = False) -> dict[str, Any]:
        if operation not in _ALLOWED or not isinstance(args, dict):
            return {"success": False, "error": "operation_not_allowed"}
        if operation in _SENSITIVE and not confirmed:
            return {"success": False, "error": "confirmation_required"}
        payload: dict[str, Any] = {"operation": operation, "args": args}
        if operation in _SENSITIVE:
            issued_at = int(self.clock())
            nonce = secrets.token_urlsafe(18)
            mac = hmac.new(self.confirmation_key.encode("utf-8"), self._canonical(operation, args, issued_at, nonce), "sha256").hexdigest()
            payload["confirmation"] = {"issued_at": issued_at, "nonce": nonce, "mac": mac}
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            headers={"Content-Type": "application/json", "X-FastBrain-Token": self.auth_token},
            method="POST",
        )
        try:
            response = self.opener(request, timeout=self.timeout)
            return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                return json.loads(exc.read().decode("utf-8"))
            except Exception:
                return {"success": False, "error": f"bridge_http_{exc.code}"}
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return {"success": False, "error": f"bridge_unavailable: {type(exc).__name__}"}

    def health(self) -> dict[str, Any]:
        request = urllib.request.Request(self.health_url, headers={"X-FastBrain-Token": self.auth_token}, method="GET")
        try:
            response = self.opener(request, timeout=self.timeout)
            return json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError, OSError, ValueError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": f"bridge_unavailable: {type(exc).__name__}"}

    def shutdown(self) -> dict[str, Any]:
        request = urllib.request.Request(self.shutdown_url, headers={"X-FastBrain-Token": self.auth_token}, method="POST")
        try:
            response = self.opener(request, timeout=self.timeout)
            return json.loads(response.read().decode("utf-8"))
        except (urllib.error.HTTPError, OSError, ValueError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": f"bridge_unavailable: {type(exc).__name__}"}
