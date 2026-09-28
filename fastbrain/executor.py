from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path


class Executor:
    """Execute FastBrain skills while reusing the working Hermes Android layer."""

    def __init__(self, registry, experience, context=None):
        self.registry = registry
        self.experience = experience
        self.context = context

    @staticmethod
    def _helper_candidates(name: str):
        home = Path.home()
        return [
            home / "hermes-phone" / "bin" / name,
            home / ".hermes" / "bin" / name,
            home / "bin" / name,
        ]

    @staticmethod
    def _is_executable(path: Path) -> bool:
        return path.is_file() and os.access(path, os.X_OK)

    def _resolve_command(self, result, argv):
        if result.skill in {"play_music", "choose_music_from_context", "play_video"}:
            fast_media = Path.home() / ".fastbrain" / "bin" / "fast-media"
            if self._is_executable(fast_media):
                query = str(result.arguments.get("query") or "popular songs")
                if result.skill == "play_video":
                    mode = "youtube-latest" if result.arguments.get("latest") else "youtube"
                else:
                    mode = str(result.arguments.get("player") or "simpmusic")
                    if mode not in {"simpmusic", "ytmusic"}:
                        mode = "simpmusic"
                return [str(fast_media), mode, query], "fastbrain_media"

        path = shutil.which(argv[0])
        if path:
            return [path, *argv[1:]], "path"

        for candidate in self._helper_candidates(argv[0]):
            if self._is_executable(candidate):
                return [str(candidate), *argv[1:]], "hermes_helper"

        dispatcher = Path.home() / "hermes-phone" / "bin" / "phone"
        if not self._is_executable(dispatcher):
            return None, None

        rest = list(argv[1:])
        skill = result.skill
        if skill == "call_contact":
            return [str(dispatcher), "call", *rest], "phone_dispatcher"
        if skill == "send_whatsapp":
            return [str(dispatcher), "whatsapp", *rest], "phone_dispatcher"
        if skill == "send_sms":
            return [str(dispatcher), "sms", *rest], "phone_dispatcher"
        if skill == "open_app":
            return [str(dispatcher), "open", *rest], "phone_dispatcher"
        if skill in {"torch_on", "torch_off", "battery_status", "wifi_status", "set_volume"}:
            return [str(dispatcher), "device", *rest], "phone_dispatcher"
        if skill in {"play_music", "choose_music_from_context"}:
            query = result.arguments.get("query") or (rest[-1] if rest else "music")
            return [str(dispatcher), "play", "music", str(query)], "phone_dispatcher"
        if skill == "play_video":
            query = result.arguments.get("query") or (rest[-1] if rest else "video")
            return [str(dispatcher), "play", "video", str(query)], "phone_dispatcher"
        if skill == "create_reminder":
            return [str(dispatcher), "remind", *rest], "phone_dispatcher"
        if skill == "create_obsidian_note":
            text = result.arguments.get("text") or (rest[0] if rest else "")
            return [str(dispatcher), "note", "create", "FastBrain", str(text)], "phone_dispatcher"
        return None, None

    def execute(self, result, dry_run=False):
        if result.route != "local":
            return {"executed": False, "route": result.route, "reason": result.reason}

        skill = self.registry.get(result.skill)
        argv = self.registry.render_command(skill, result.arguments)
        if not argv:
            return {"executed": False, "error": "no_executor"}

        resolved, source = self._resolve_command(result, argv)
        if not resolved:
            return {
                "executed": False,
                "error": "helper_not_found",
                "command": argv[0],
                "searched": [str(p) for p in self._helper_candidates(argv[0])],
                "dispatcher": str(Path.home() / "hermes-phone" / "bin" / "phone"),
            }

        if dry_run:
            return {"executed": False, "dry_run": True, "command": resolved, "executor_source": source}

        started = time.perf_counter()
        try:
            proc = subprocess.run(resolved, timeout=float(skill.get("timeout", 8)), capture_output=True, text=True)
            latency_ms = (time.perf_counter() - started) * 1000
            ok = proc.returncode == 0
            self.experience.record(result.skill, ok, latency_ms)
            if ok and self.context is not None:
                self.context.remember_action(result.skill, result.arguments)
            return {
                "executed": True,
                "success": ok,
                "returncode": proc.returncode,
                "latency_ms": latency_ms,
                "executor_source": source,
                "command": resolved,
                "stdout": proc.stdout[-1000:],
                "stderr": proc.stderr[-1000:],
            }
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            self.experience.record(result.skill, False, latency_ms)
            return {
                "executed": True,
                "success": False,
                "latency_ms": latency_ms,
                "executor_source": source,
                "command": resolved,
                "error": str(exc),
            }
