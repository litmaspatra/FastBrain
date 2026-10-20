from __future__ import annotations

import threading
import os
import subprocess
from pathlib import Path

from fastbrain.db import DB
from fastbrain.models import RouteResult
from fastbrain.prerouter import PreRouter


class FakeEngine:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def route(self, _text):
        self.calls += 1
        return self.result


class FakeExecutor:
    def __init__(self, result=None):
        self.result = result or {"executed": True, "success": True, "operation": "battery_status"}
        self.calls = []

    def execute(self, route, confirmed=False):
        self.calls.append((route, confirmed))
        return dict(self.result)


def _router(tmp_path, route, result=None):
    return PreRouter(FakeEngine(route), FakeExecutor(result), DB(tmp_path / "fastbrain.db"))


def test_unrecognized_request_declines_without_executor(tmp_path):
    router = _router(tmp_path, RouteResult("hermes", skill="normal_hermes", reason="fallback"))

    result = router.handle("explain quantum computing", request_id="ws-1")

    assert result["decision"] == "decline"
    assert result["fallback_to_hermes"] is True
    assert result["exit_code"] == 64
    assert router.executor.calls == []


def test_read_only_request_replays_completed_result_without_second_execution(tmp_path):
    router = _router(tmp_path, RouteResult("local", skill="battery_status", confidence=1.0))

    first = router.handle("battery status", request_id="ws-2")
    second = router.handle("battery status", request_id="ws-2")

    assert first["decision"] == "handled"
    assert second["decision"] == "handled"
    assert second["replayed"] is True
    assert len(router.executor.calls) == 1


def test_consequential_request_requires_one_time_approval_before_execution(tmp_path):
    router = _router(tmp_path, RouteResult("local", skill="open_app", arguments={"app": "WhatsApp"}, confidence=1.0))

    pending = router.handle("open WhatsApp", request_id="ws-3")

    assert pending["decision"] == "approval_required"
    assert pending["fallback_to_hermes"] is False
    assert isinstance(pending["approval_token"], str)
    assert router.executor.calls == []

    handled = router.handle("open WhatsApp", request_id="ws-3", approval_token=pending["approval_token"])
    replay = router.handle("open WhatsApp", request_id="ws-3", approval_token=pending["approval_token"])

    assert handled["decision"] == "handled"
    assert replay["replayed"] is True
    assert len(router.executor.calls) == 1


def test_invalid_approval_token_never_executes_consequential_request(tmp_path):
    router = _router(tmp_path, RouteResult("local", skill="open_app", arguments={"app": "WhatsApp"}, confidence=1.0))
    router.handle("open WhatsApp", request_id="ws-invalid")

    rejected = router.handle("open WhatsApp", request_id="ws-invalid", approval_token="wrong-token")

    assert rejected["decision"] == "approval_required"
    assert rejected["error"] == "approval_token_invalid_or_already_used"
    assert router.executor.calls == []


def test_reused_request_id_with_different_operation_is_rejected(tmp_path):
    router = _router(tmp_path, RouteResult("local", skill="battery_status", confidence=1.0))
    assert router.handle("battery status", request_id="ws-4")["decision"] == "handled"

    conflict = router.handle("battery status again", request_id="ws-4")

    assert conflict == {
        "version": 1,
        "request_id": "ws-4",
        "decision": "request_id_conflict",
        "fallback_to_hermes": False,
        "consequential": False,
        "exit_code": 75,
    }
    assert len(router.executor.calls) == 1


def test_uncertain_consequential_failure_is_not_retried_or_fallen_through(tmp_path):
    route = RouteResult("local", skill="open_app", arguments={"app": "WhatsApp"}, confidence=1.0)
    router = _router(tmp_path, route, {"executed": True, "success": False, "error": "android_command_timeout"})
    pending = router.handle("open WhatsApp", request_id="ws-5")

    first = router.handle("open WhatsApp", request_id="ws-5", approval_token=pending["approval_token"])
    second = router.handle("open WhatsApp", request_id="ws-5", approval_token=pending["approval_token"])

    assert first["decision"] == "indeterminate"
    assert first["fallback_to_hermes"] is False
    assert second["decision"] == "indeterminate"
    assert len(router.executor.calls) == 1


def test_concurrent_approval_reserves_one_execution(tmp_path):
    route = RouteResult("local", skill="open_app", arguments={"app": "WhatsApp"}, confidence=1.0)
    router = _router(tmp_path, route)
    pending = router.handle("open WhatsApp", request_id="ws-6")
    started = threading.Event()
    release = threading.Event()

    def delayed_execute(route, confirmed=False):
        router.executor.calls.append((route, confirmed))
        started.set()
        release.wait(timeout=2)
        return {"executed": True, "success": True, "operation": "open_app"}

    router.executor.execute = delayed_execute
    first_result = []
    worker = threading.Thread(target=lambda: first_result.append(router.handle("open WhatsApp", request_id="ws-6", approval_token=pending["approval_token"])))
    worker.start()
    assert started.wait(timeout=2)
    duplicate = router.handle("open WhatsApp", request_id="ws-6", approval_token=pending["approval_token"])
    release.set()
    worker.join(timeout=2)

    assert duplicate["decision"] == "in_progress"
    assert first_result[0]["decision"] == "handled"
    assert len(router.executor.calls) == 1


def test_cli_preroute_emits_json_and_uses_decline_exit_code(monkeypatch, capsys):
    from fastbrain import cli

    class Router:
        def handle(self, text, request_id=None, approval_token=None):
            assert (text, request_id, approval_token) == ("explain quantum computing", "ws-7", None)
            return {"decision": "decline", "exit_code": 64}

    monkeypatch.setattr(cli, "build", lambda: {"engine": object(), "executor": object(), "db": object()})
    monkeypatch.setattr(cli, "PreRouter", lambda **kwargs: Router())
    monkeypatch.setattr("sys.argv", ["fastbrain", "preroute", "--text", "explain quantum computing", "--request-id", "ws-7"])

    assert cli.main() == 64
    assert '"decision": "decline"' in capsys.readouterr().out


def test_hermes_wrapper_forwards_request_id_to_prerouter(tmp_path):
    fake = tmp_path / "fastbrain"
    capture = tmp_path / "argv.json"
    fake.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" > \"$CAPTURE\"\nexit 64\n", encoding="utf-8")
    fake.chmod(0o700)
    wrapper = Path(__file__).parents[1] / "scripts" / "hermes-fastbrain-wrapper.sh"
    env = {**os.environ, "FASTBRAIN_BIN": str(fake), "CAPTURE": str(capture)}

    proc = subprocess.run([str(wrapper), "--request-id", "ws-8", "--", "explain quantum computing"], env=env, text=True, capture_output=True)

    assert proc.returncode == 64
    assert capture.read_text(encoding="utf-8").strip() == "preroute --text explain quantum computing --request-id ws-8"


def test_hermes_wrapper_forwards_approval_token(tmp_path):
    fake = tmp_path / "fastbrain"
    capture = tmp_path / "argv.json"
    fake.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" > \"$CAPTURE\"\nexit 0\n", encoding="utf-8")
    fake.chmod(0o700)
    wrapper = Path(__file__).parents[1] / "scripts" / "hermes-fastbrain-wrapper.sh"
    env = {**os.environ, "FASTBRAIN_BIN": str(fake), "CAPTURE": str(capture)}

    proc = subprocess.run([str(wrapper), "--request-id", "ws-9", "--approval-token", "token", "--", "open WhatsApp"], env=env, text=True, capture_output=True)

    assert proc.returncode == 0
    assert capture.read_text(encoding="utf-8").strip() == "preroute --text open WhatsApp --request-id ws-9 --approval-token token"


def test_hermes_launcher_falls_through_only_after_clean_decline(tmp_path):
    prerouter = tmp_path / "prerouter"
    hermes = tmp_path / "hermes"
    capture = tmp_path / "argv.txt"
    prerouter.write_text("#!/bin/sh\nexit 64\n", encoding="utf-8")
    hermes.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" > \"$CAPTURE\"\n", encoding="utf-8")
    prerouter.chmod(0o700)
    hermes.chmod(0o700)
    launcher = Path(__file__).parents[1] / "scripts" / "hermes-with-fastbrain.sh"
    env = {**os.environ, "FASTBRAIN_PREROUTER": str(prerouter), "HERMES_BIN": str(hermes), "CAPTURE": str(capture)}

    proc = subprocess.run([str(launcher), "--request-id", "ws-10", "--", "explain quantum computing"], env=env, text=True, capture_output=True)

    assert proc.returncode == 0
    assert capture.read_text(encoding="utf-8").strip() == "chat --query explain quantum computing --source fastbrain-fallback"


def test_hermes_launcher_does_not_fall_through_after_prerouter_indeterminate(tmp_path):
    prerouter = tmp_path / "prerouter"
    hermes = tmp_path / "hermes"
    prerouter.write_text("#!/bin/sh\nprintf '%s\\n' '{\"decision\":\"indeterminate\"}'\nexit 75\n", encoding="utf-8")
    hermes.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
    prerouter.chmod(0o700)
    hermes.chmod(0o700)
    launcher = Path(__file__).parents[1] / "scripts" / "hermes-with-fastbrain.sh"
    env = {**os.environ, "FASTBRAIN_PREROUTER": str(prerouter), "HERMES_BIN": str(hermes)}

    proc = subprocess.run([str(launcher), "--request-id", "ws-11", "--", "open WhatsApp"], env=env, text=True, capture_output=True)

    assert proc.returncode == 75
    assert '"decision":"indeterminate"' in proc.stdout
