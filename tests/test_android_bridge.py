from pathlib import Path
from types import SimpleNamespace

from fastbrain.android_bridge import AndroidBridge
from fastbrain.app import build
from fastbrain.config import Config
from fastbrain.executor import Executor
from fastbrain.models import RouteResult


SKILLS = Path(__file__).parents[1] / "skills" / "builtin.json"


def _commands(tmp_path, *names):
    for name in names:
        path = tmp_path / name
        path.write_text("#!/bin/sh\n", encoding="utf-8")
        path.chmod(0o700)


def test_battery_bridge_uses_only_allowlisted_native_command(tmp_path):
    _commands(tmp_path, "termux-battery-status")
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout='{"percentage": 72}', stderr="")

    bridge = AndroidBridge(command_dir=tmp_path, runner=runner, timeout=1.5)
    plan = bridge.plan("battery_status", {})

    assert plan and plan["operation"] == "battery_status"
    result = bridge.execute(plan)
    assert result["success"] is True
    assert result["stdout"] == '{"percentage": 72}'
    assert calls == [([str(tmp_path / "termux-battery-status")], {"capture_output": True, "text": True, "timeout": 1.5})]


def test_app_bridge_only_accepts_known_apps(tmp_path):
    _commands(tmp_path, "termux-open")
    bridge = AndroidBridge(command_dir=tmp_path)

    assert bridge.plan("open_app", {"app": "rm -rf /"}) is None
    plan = bridge.plan("open_app", {"app": "WhatsApp"})
    assert plan == {
        "operation": "open_app",
        "argv": [str(tmp_path / "termux-open"), "intent:#Intent;package=com.whatsapp;end"],
        "app": "whatsapp",
    }


def test_sms_bridge_requires_confirmation_before_reading_contacts(tmp_path):
    _commands(tmp_path, "termux-contact-list", "termux-sms-send")
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        if argv[0].endswith("termux-contact-list"):
            return SimpleNamespace(returncode=0, stdout='[{"name":"Ravi","number":"+15551234567"}]', stderr="")
        return SimpleNamespace(returncode=0, stdout="sent", stderr="")

    bridge = AndroidBridge(command_dir=tmp_path, runner=runner)
    plan = bridge.plan("send_sms", {"contact": "Ravi", "message": "hello"})

    assert bridge.execute(plan, confirmed=False)["error"] == "confirmation_required"
    assert calls == []
    result = bridge.execute(plan, confirmed=True)
    assert result["success"] is True
    assert calls[0][0] == [str(tmp_path / "termux-contact-list")]
    assert calls[1][0] == [str(tmp_path / "termux-sms-send"), "-n", "+15551234567", "hello"]


def test_executor_requires_confirmation_before_sms_bridge_access(tmp_path):
    _commands(tmp_path, "termux-contact-list", "termux-sms-send")
    calls = []

    def runner(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout='[{"name":"Ravi","number":"+15551234567"}]', stderr="")

    stack = build(Config(tmp_path / "state", tmp_path / "state" / "db.sqlite", SKILLS, memory_mode="hot"))
    bridge = AndroidBridge(command_dir=tmp_path, runner=runner)
    executor = Executor(stack["registry"], stack["experience"], stack["context"], android_bridge=bridge)
    route = stack["engine"].route("sms Ravi hello")

    result = executor.execute(route)
    assert result["error"] == "confirmation_required"
    assert calls == []


def test_cli_requires_explicit_confirm_flag_for_execution(monkeypatch):
    from fastbrain import cli

    captured = {}

    class Engine:
        @staticmethod
        def route(_text):
            return RouteResult("local", "communication", "send_sms", {"contact": "Ravi", "message": "hello"}, 1.0, "test", "none", [])

    class ExecutorStub:
        @staticmethod
        def execute(_result, dry_run=False, confirmed=False):
            captured.update(dry_run=dry_run, confirmed=confirmed)
            return {"executed": False, "success": False, "error": "confirmation_required"}

    monkeypatch.setattr(cli, "build", lambda: {"engine": Engine(), "executor": ExecutorStub()})
    monkeypatch.setattr("sys.argv", ["fastbrain", "route", "sms", "Ravi", "hello", "--execute", "--confirm"])

    assert cli.main() == 64
    assert captured == {"dry_run": False, "confirmed": True}


def test_executor_reports_unavailable_android_command(tmp_path):
    stack = build(Config(tmp_path / "state", tmp_path / "state" / "db.sqlite", SKILLS, memory_mode="hot"))
    executor = Executor(stack["registry"], stack["experience"], stack["context"], android_bridge=AndroidBridge(command_dir=tmp_path))

    result = executor.execute(stack["engine"].route("battery status"))

    assert result == {
        "executed": False,
        "success": False,
        "error": "android_command_unavailable: termux-battery-status",
        "operation": "battery_status",
    }


def test_medium_risk_message_requires_confirmation_before_helper_lookup(tmp_path):
    stack = build(Config(tmp_path / "state", tmp_path / "state" / "db.sqlite", SKILLS, memory_mode="hot"))
    route = stack["engine"].route("message Ravi hello")

    result = stack["executor"].execute(route)

    assert result == {
        "executed": False,
        "success": False,
        "error": "confirmation_required",
        "operation": "send_whatsapp",
        "requires_confirmation": True,
    }


def test_native_bridge_is_preferred_for_battery(tmp_path):
    _commands(tmp_path, "termux-battery-status")
    direct_calls = []

    class Native:
        def call(self, operation, args, confirmed=False):
            assert (operation, args, confirmed) == ("battery", {}, False)
            return {"success": True, "stdout": '{"percentage":72}'}

    bridge = AndroidBridge(
        command_dir=tmp_path,
        runner=lambda *args, **kwargs: direct_calls.append(args),
        native_client=Native(),
    )
    result = bridge.execute(bridge.plan("battery_status", {}))

    assert result["success"] is True
    assert result["executor_source"] == "native_bridge"
    assert direct_calls == []


def test_only_battery_falls_back_after_native_bridge_unavailable(tmp_path):
    _commands(tmp_path, "termux-battery-status", "termux-contact-list", "termux-sms-send")
    direct_calls = []

    class Native:
        def call(self, operation, args, confirmed=False):
            return {"success": False, "error": "bridge_unavailable: URLError"}

    def runner(argv, **kwargs):
        direct_calls.append(argv)
        return SimpleNamespace(returncode=0, stdout='{"percentage":72}', stderr="")

    bridge = AndroidBridge(command_dir=tmp_path, runner=runner, native_client=Native())
    battery = bridge.execute(bridge.plan("battery_status", {}))
    sms = bridge.execute(bridge.plan("send_sms", {"contact": "+15551234567", "message": "hello"}), confirmed=True)

    assert battery["success"] is True
    assert battery["fallback"] == "debian_subprocess"
    assert direct_calls == [[str(tmp_path / "termux-battery-status")]]
    assert sms == {"executed": False, "success": False, "error": "bridge_unavailable: URLError", "operation": "send_sms", "executor_source": "native_bridge"}
