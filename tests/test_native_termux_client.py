import hmac
import json
from types import SimpleNamespace

from fastbrain.native_termux_client import NativeTermuxClient


def test_native_client_signs_sensitive_request_only_after_fastbrain_confirmation(tmp_path):
    auth = tmp_path / "auth.token"
    confirm = tmp_path / "confirmation.key"
    auth.write_text("a" * 32, encoding="utf-8")
    confirm.write_text("c" * 32, encoding="utf-8")
    auth.chmod(0o600)
    confirm.chmod(0o600)
    observed = {}

    def opener(request, timeout):
        observed["headers"] = dict(request.header_items())
        observed["payload"] = json.loads(request.data)
        observed["timeout"] = timeout
        return SimpleNamespace(status=200, read=lambda: b'{"success":true}')

    client = NativeTermuxClient("http://127.0.0.1:8988/v1/action", auth, confirm, opener=opener, clock=lambda: 100)

    assert client.call("sms", {"contact": "Ravi", "message": "hello"}, confirmed=False) == {
        "success": False,
        "error": "confirmation_required",
    }
    result = client.call("sms", {"contact": "Ravi", "message": "hello"}, confirmed=True)

    assert result == {"success": True}
    proof = observed["payload"]["confirmation"]
    canonical = json.dumps(
        {"operation": "sms", "args": {"contact": "Ravi", "message": "hello"}, "issued_at": 100, "nonce": proof["nonce"]},
        separators=(",", ":"), sort_keys=True,
    ).encode()
    assert proof["mac"] == hmac.new(("c" * 32).encode(), canonical, "sha256").hexdigest()
    assert observed["timeout"] <= 8


def test_native_client_health_uses_authenticated_loopback_request(tmp_path):
    auth = tmp_path / "auth.token"
    confirm = tmp_path / "confirmation.key"
    auth.write_text("a" * 32, encoding="utf-8")
    confirm.write_text("c" * 32, encoding="utf-8")
    auth.chmod(0o600)
    confirm.chmod(0o600)
    observed = {}

    def opener(request, timeout):
        observed["url"] = request.full_url
        observed["headers"] = dict(request.header_items())
        return SimpleNamespace(status=200, read=lambda: b'{"ok": true}')

    client = NativeTermuxClient("http://127.0.0.1:8988/v1/action", auth, confirm, opener=opener)
    assert client.health() == {"ok": True}
    assert observed["url"] == "http://127.0.0.1:8988/health"


def test_native_client_shutdown_uses_authenticated_loopback_request(tmp_path):
    auth = tmp_path / "auth.token"
    confirm = tmp_path / "confirmation.key"
    auth.write_text("a" * 32, encoding="utf-8")
    confirm.write_text("c" * 32, encoding="utf-8")
    auth.chmod(0o600)
    confirm.chmod(0o600)
    observed = {}

    def opener(request, timeout):
        observed["url"] = request.full_url
        observed["method"] = request.get_method()
        return SimpleNamespace(status=200, read=lambda: b'{"ok": true, "status": "shutdown_requested"}')

    client = NativeTermuxClient("http://127.0.0.1:8988/v1/action", auth, confirm, opener=opener)
    assert client.shutdown() == {"ok": True, "status": "shutdown_requested"}
    assert observed == {"url": "http://127.0.0.1:8988/shutdown", "method": "POST"}
