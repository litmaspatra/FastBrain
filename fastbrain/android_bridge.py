"""Allowlisted bridge from FastBrain's Debian runtime to Termux commands.

The bridge never invokes a shell. It can run only fixed Termux command names
with positional arguments assembled from validated FastBrain route data.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from .native_termux_client import NativeTermuxClient

_DEFAULT_TERMUX_BIN = "/data/data/com.termux/files/usr/bin"
_APP_PACKAGES = {
    "whatsapp": "com.whatsapp",
    "telegram": "org.telegram.messenger",
    "maps": "com.google.android.apps.maps",
    "settings": "com.android.settings",
}
_PHONE = re.compile(r"^\+?[0-9][0-9 .()\-]{2,40}$")


class AndroidBridge:
    def __init__(
        self,
        command_dir: str | Path | None = None,
        runner: Callable[..., Any] = subprocess.run,
        timeout: float = 3.0,
        native_client=None,
    ):
        self.command_dir = Path(command_dir or os.getenv("FASTBRAIN_TERMUX_BIN", _DEFAULT_TERMUX_BIN))
        self.runner = runner
        self.timeout = max(0.1, min(float(timeout), 8.0))
        self.native_client = native_client
        self.native_error = ""
        if native_client is None and os.getenv("FASTBRAIN_NATIVE_BRIDGE_ENABLED") == "1":
            try:
                self.native_client = NativeTermuxClient(
                    os.getenv("FASTBRAIN_NATIVE_BRIDGE_URL", "http://127.0.0.1:8988/v1/action"),
                    os.getenv("FASTBRAIN_NATIVE_BRIDGE_AUTH_TOKEN_FILE", "/data/data/com.termux/files/home/.fastbrain-native-bridge/auth.token"),
                    os.getenv("FASTBRAIN_NATIVE_BRIDGE_CONFIRMATION_KEY_FILE", "/data/data/com.termux/files/home/.fastbrain-native-bridge/confirmation.key"),
                    timeout=float(os.getenv("FASTBRAIN_NATIVE_BRIDGE_TIMEOUT", "1.5")),
                )
            except (OSError, ValueError) as exc:
                self.native_error = f"bridge_unavailable: {type(exc).__name__}"

    def _command(self, name: str) -> str | None:
        path = self.command_dir / name
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None

    @staticmethod
    def handles(skill: str) -> bool:
        return skill in {"battery_status", "torch_on", "torch_off", "open_app", "send_sms"}

    def unavailable_reason(self, skill: str, arguments: dict[str, Any]) -> str:
        if skill == "battery_status":
            return "android_command_unavailable: termux-battery-status"
        if skill in {"torch_on", "torch_off"}:
            return "android_command_unavailable: termux-torch"
        if skill == "send_sms":
            return "android_command_unavailable: termux-sms-send"
        if skill == "open_app":
            app = " ".join(str(arguments.get("app") or "").lower().split())
            if app not in _APP_PACKAGES:
                return f"android_app_not_allowlisted: {app or 'empty'}"
            return "android_command_unavailable: termux-open"
        return "android_command_unavailable"

    @staticmethod
    def _normalized_name(value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", value.lower()))

    def plan(self, skill: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        if skill == "battery_status":
            command = self._command("termux-battery-status")
            return {"operation": skill, "argv": [command]} if command else None
        if skill in {"torch_on", "torch_off"}:
            command = self._command("termux-torch")
            if not command:
                return None
            return {"operation": skill, "argv": [command, "on" if skill == "torch_on" else "off"]}
        if skill == "open_app":
            app = " ".join(str(arguments.get("app") or "").lower().split())
            package = _APP_PACKAGES.get(app)
            command = self._command("termux-open")
            if not command or not package:
                return None
            uri = f"intent:#Intent;package={package};end"
            return {"operation": skill, "argv": [command, uri], "app": app}
        if skill == "send_sms":
            contact = str(arguments.get("contact") or "").strip()
            message = str(arguments.get("message") or "")
            if not contact or not message or len(contact) > 100 or len(message) > 1600:
                return None
            if not self._command("termux-sms-send"):
                return None
            return {"operation": skill, "contact": contact, "message": message, "requires_confirmation": True}
        return None

    def _run(self, argv: list[str], operation: str) -> dict[str, Any]:
        try:
            proc = self.runner(argv, capture_output=True, text=True, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            return {"executed": True, "success": False, "error": "android_command_timeout", "operation": operation}
        except OSError as exc:
            return {"executed": True, "success": False, "error": f"android_command_unavailable: {exc}", "operation": operation}
        return {
            "executed": True,
            "success": proc.returncode == 0,
            "operation": operation,
            "command": argv,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[-1000:],
            "stderr": (proc.stderr or "")[-1000:],
        }

    def _resolve_phone(self, contact: str) -> tuple[str | None, str | None]:
        if _PHONE.fullmatch(contact):
            return contact, None
        command = self._command("termux-contact-list")
        if not command:
            return None, "contact_lookup_unavailable"
        result = self._run([command], "contact_lookup")
        if not result.get("success"):
            return None, result.get("error") or "contact_lookup_failed"
        try:
            records = json.loads(result.get("stdout") or "[]")
        except json.JSONDecodeError:
            return None, "contact_lookup_invalid_json"
        sought = self._normalized_name(contact)
        numbers: set[str] = set()
        for item in records if isinstance(records, list) else []:
            if not isinstance(item, dict) or self._normalized_name(str(item.get("name") or "")) != sought:
                continue
            values = [item.get("number"), item.get("phone_number")]
            phones = item.get("phones")
            if isinstance(phones, list):
                values.extend(phones)
            for value in values:
                number = str(value or "").strip()
                if _PHONE.fullmatch(number):
                    numbers.add(number)
        if not numbers:
            return None, "contact_not_found"
        if len(numbers) != 1:
            return None, "contact_ambiguous"
        return next(iter(numbers)), None

    @staticmethod
    def _native_request(plan: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
        operation = plan.get("operation")
        if operation == "battery_status":
            return "battery", {}
        if operation in {"torch_on", "torch_off"}:
            return "flashlight", {"state": "on" if operation == "torch_on" else "off"}
        if operation == "open_app":
            return "launch_app", {"app": plan.get("app", "")}
        if operation == "send_sms":
            return "sms", {"contact": plan.get("contact", ""), "message": plan.get("message", "")}
        return None

    @staticmethod
    def _bridge_unavailable(payload: dict[str, Any]) -> bool:
        return str(payload.get("error") or "").startswith("bridge_unavailable:")

    def _execute_debian(self, plan: dict[str, Any]) -> dict[str, Any]:
        operation = str(plan.get("operation") or "")
        if operation == "send_sms":
            number, error = self._resolve_phone(str(plan.get("contact") or ""))
            if error:
                return {"executed": False, "success": False, "error": error, "operation": operation}
            command = self._command("termux-sms-send")
            if not command:
                return {"executed": False, "success": False, "error": "android_command_unavailable", "operation": operation}
            return self._run([command, "-n", number, str(plan.get("message") or "")], operation)
        argv = plan.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
            return {"executed": False, "success": False, "error": "invalid_bridge_plan"}
        return self._run(argv, operation)

    def execute(self, plan: dict[str, Any] | None, confirmed: bool = False) -> dict[str, Any]:
        if not isinstance(plan, dict):
            return {"executed": False, "success": False, "error": "android_command_unavailable"}
        operation = str(plan.get("operation") or "")
        if plan.get("requires_confirmation") and not confirmed:
            return {"executed": False, "success": False, "error": "confirmation_required", "operation": operation, "requires_confirmation": True}
        native = self._native_request(plan)
        if native and (self.native_client is not None or self.native_error):
            native_operation, native_args = native
            payload = self.native_client.call(native_operation, native_args, confirmed=confirmed) if self.native_client else {"success": False, "error": self.native_error}
            if payload.get("success"):
                return {"executed": True, "success": True, "operation": operation, "executor_source": "native_bridge", **payload}
            if operation == "battery_status" and self._bridge_unavailable(payload):
                fallback = self._execute_debian(plan)
                fallback["fallback"] = "debian_subprocess"
                fallback["native_error"] = payload.get("error")
                return fallback
            return {"executed": False, "success": False, "error": payload.get("error", "native_bridge_failed"), "operation": operation, "executor_source": "native_bridge"}
        return self._execute_debian(plan)
