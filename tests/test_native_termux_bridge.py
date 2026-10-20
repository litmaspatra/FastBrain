import importlib.util
import hmac
import os
import time
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path
from types import SimpleNamespace


SOURCE = Path(__file__).parents[1] / "scripts" / "termux_native_bridge.py"
spec = importlib.util.spec_from_file_location("termux_native_bridge", SOURCE)
bridge = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(bridge)


def _commands(tmp_path, *names):
    for name in names:
        path = tmp_path / name
        path.write_text("#!/bin/sh\n", encoding="utf-8")
        path.chmod(0o700)


def test_native_bridge_accepts_authenticated_battery_only(tmp_path):
    _commands(tmp_path, "termux-battery-status")
    calls = []

    def runner(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout='{"percentage":72}', stderr="")

    auth_token = "a" * 32
    core = bridge.BridgeCore(auth_token, "c" * 32, command_dir=tmp_path, runner=runner)

    status, payload = core.handle(auth_token, {"operation": "battery", "args": {}})
    assert status == 200
    assert payload["success"] is True
    assert calls == [([str(tmp_path / "termux-battery-status")], {"capture_output": True, "text": True, "timeout": 4.0})]

    status, payload = core.handle("wrong-token", {"operation": "battery", "args": {}})
    assert status == 401
    assert payload["error"] == "unauthorized"

    status, payload = core.handle(auth_token, {"operation": "shell", "args": {"command": "id"}})
    assert status == 400
    assert payload["error"] == "operation_not_allowed"


def test_sensitive_operation_requires_signed_one_time_confirmation(tmp_path):
    _commands(tmp_path, "termux-torch")
    token = "a" * 32
    key = "c" * 32
    core = bridge.BridgeCore(token, key, command_dir=tmp_path, runner=lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""))
    request = {"operation": "flashlight", "args": {"state": "on"}}

    status, payload = core.handle(token, {**request, "confirmation": {"confirmed": True}})
    assert status == 403
    assert payload["error"] == "confirmation_invalid"

    issued_at = int(time.time())
    nonce = "n" * 16
    mac = hmac.new(key.encode(), core._canonical("flashlight", {"state": "on"}, issued_at, nonce), "sha256").hexdigest()
    signed = {**request, "confirmation": {"issued_at": issued_at, "nonce": nonce, "mac": mac}}
    assert core.handle(token, signed)[0] == 200
    status, payload = core.handle(token, signed)
    assert status == 403
    assert payload["error"] == "confirmation_replayed"


def test_health_endpoint_requires_the_bridge_token(tmp_path):
    token = "a" * 32
    core = bridge.BridgeCore(token, "c" * 32, command_dir=tmp_path)
    server = HTTPServer(("127.0.0.1", 0), bridge.make_handler(core))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/health"
    try:
        with urllib.request.urlopen(url, timeout=2):
            raise AssertionError("unauthenticated health request unexpectedly succeeded")
    except urllib.error.HTTPError as exc:
        assert exc.code == 401
    request = urllib.request.Request(url, headers={"X-FastBrain-Token": token})
    with urllib.request.urlopen(request, timeout=2) as response:
        assert response.status == 200
        assert response.read() == b'{"ok": true}'
    server.shutdown()


def test_authenticated_shutdown_stops_native_bridge_server(tmp_path):
    token = "a" * 32
    core = bridge.BridgeCore(token, "c" * 32, command_dir=tmp_path)
    server = HTTPServer(("127.0.0.1", 0), bridge.make_handler(core))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}/shutdown",
        headers={"X-FastBrain-Token": token},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=2) as response:
        assert response.status == 200
        assert response.read() == b'{"ok": true, "status": "shutdown_requested"}'
    thread.join(timeout=2)
    assert not thread.is_alive()


def test_pid_claim_prevents_a_second_native_bridge_instance(tmp_path):
    pid_file = tmp_path / "bridge.pid"
    bridge._claim_pid(pid_file, os.getpid())
    try:
        bridge._claim_pid(pid_file, 5678)
        raise AssertionError("second bridge instance unexpectedly acquired pid file")
    except RuntimeError as exc:
        assert "already running" in str(exc)


def test_bounded_shutdown_timer_does_not_keep_bridge_process_alive():
    class Server:
        def shutdown(self):
            return None

    timer = bridge._shutdown_timer(Server(), 90)
    assert timer.daemon is True
    timer.cancel()
