"""Explicit lifecycle control for the native Termux bridge.

This manager never starts the bridge implicitly. Callers must invoke ``start``
for a manually requested session; AndroidBridge only consumes an already-live
bridge endpoint.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any, Callable


class NativeBridgeManager:
    def __init__(
        self,
        client: Any,
        launcher: str | Path,
        scheduler: str = "termux-job-scheduler",
        job_id: int = 8903,
        runner: Callable[..., Any] = subprocess.run,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.launcher = Path(launcher)
        self.scheduler = scheduler
        self.job_id = int(job_id)
        self.runner = runner
        self.sleep = sleep

    def health(self) -> dict[str, Any]:
        result = self.client.health()
        return result if isinstance(result, dict) else {"ok": False, "error": "invalid_health_response"}

    def start(self, wait_seconds: float = 3.0) -> dict[str, Any]:
        """Schedule one bridge process, then require an authenticated health check."""
        current = self.health()
        if current.get("ok") is True:
            return {"ok": True, "status": "already_running"}
        if not self.launcher.is_file():
            return {"ok": False, "error": "native_bridge_launcher_missing"}
        command = [
            self.scheduler,
            "--script", str(self.launcher),
            "--job-id", str(self.job_id),
            "--battery-not-low", "false",
            "--storage-not-low", "false",
        ]
        try:
            proc = self.runner(command, capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "error": f"native_bridge_start_failed: {type(exc).__name__}"}
        if proc.returncode != 0:
            return {"ok": False, "error": "native_bridge_start_failed", "stderr": (proc.stderr or "")[-300:]}
        deadline = time.monotonic() + max(0.0, min(float(wait_seconds), 10.0))
        while time.monotonic() < deadline:
            self.sleep(0.1)
            if self.health().get("ok") is True:
                return {"ok": True, "status": "started"}
        return {"ok": False, "error": "native_bridge_health_timeout"}

    def shutdown(self) -> dict[str, Any]:
        """Stop the loopback server first, then cancel its bounded scheduler job."""
        try:
            self.client.shutdown()
        except (OSError, ValueError, AttributeError):
            pass
        try:
            proc = self.runner([self.scheduler, "--cancel", "--job-id", str(self.job_id)], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "error": f"native_bridge_shutdown_failed: {type(exc).__name__}"}
        if proc.returncode != 0:
            return {"ok": False, "error": "native_bridge_shutdown_failed", "stderr": (proc.stderr or "")[-300:]}
        return {"ok": True, "status": "shutdown_requested"}
