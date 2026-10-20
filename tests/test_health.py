from fastbrain.app import build
from fastbrain.config import Config
from fastbrain.health import API, health_payload


def test_health_has_version_and_capabilities(tmp_path, monkeypatch):
    monkeypatch.setenv("FASTBRAIN_HOME", str(tmp_path))
    h = health_payload(build(Config.from_env()))
    assert h["ok"] and h["version"] and h["api"] == API
    assert h["capabilities"]["llm"] is False
    assert isinstance(h["capabilities"]["skills"], int)
