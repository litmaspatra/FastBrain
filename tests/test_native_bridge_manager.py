from types import SimpleNamespace

from fastbrain.native_bridge_manager import NativeBridgeManager


def test_manager_starts_once_and_waits_for_authenticated_health(tmp_path):
    launcher = tmp_path / "run-native-bridge.sh"
    launcher.write_text("#!/bin/sh\n", encoding="utf-8")
    launcher.chmod(0o700)
    calls = []

    class Client:
        def __init__(self):
            self.responses = [{"ok": False}, {"ok": True}]

        def health(self):
            return self.responses.pop(0) if self.responses else {"ok": True}

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="scheduled", stderr="")

    manager = NativeBridgeManager(Client(), launcher=launcher, scheduler="termux-job-scheduler", job_id=8903, runner=runner, sleep=lambda _: None)
    result = manager.start(wait_seconds=1)

    assert result == {"ok": True, "status": "started"}
    assert calls[0][0] == ["termux-job-scheduler", "--script", str(launcher), "--job-id", "8903", "--battery-not-low", "false", "--storage-not-low", "false"]


def test_manager_shutdown_stops_bridge_then_cancels_its_job(tmp_path):
    launcher = tmp_path / "run-native-bridge.sh"
    calls = []

    class Client:
        def shutdown(self):
            calls.append("bridge_shutdown")
            return {"ok": True, "status": "shutdown_requested"}

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    manager = NativeBridgeManager(Client(), launcher=launcher, job_id=8903, runner=runner)
    assert manager.shutdown() == {"ok": True, "status": "shutdown_requested"}
    assert calls == ["bridge_shutdown", (["termux-job-scheduler", "--cancel", "--job-id", "8903"], {"capture_output": True, "text": True, "timeout": 5})]


def test_cli_native_bridge_status_never_starts_bridge(monkeypatch):
    from fastbrain import cli

    calls = []

    class Manager:
        def health(self):
            calls.append("health")
            return {"ok": False}

        def start(self):
            calls.append("start")
            return {"ok": True}

        def shutdown(self):
            calls.append("shutdown")
            return {"ok": True}

    monkeypatch.setattr(cli, "_native_manager", lambda: Manager())
    monkeypatch.setattr("sys.argv", ["fastbrain", "native-bridge", "status"])
    assert cli.main() == 3
    assert calls == ["health"]
