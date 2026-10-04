"""Regression tests for bugs found while reviewing the Codex-written code."""
import json
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import HTTPServer
from pathlib import Path

import pytest

from fastbrain.api import Handler
from fastbrain.app import build
from fastbrain.config import Config
from fastbrain.executor import Executor

SKILLS = Path(__file__).parents[1] / "skills" / "builtin.json"


def make_stack(**kw):
    td = tempfile.TemporaryDirectory()
    root = Path(td.name)
    kw.setdefault("memory_mode", "hot")
    s = build(Config(root, root / "db.sqlite", SKILLS, **kw))
    s["_td"] = td
    return s


# --- executor: 'DISCHARGING' contains 'charging' and used to read as charging -----------------
@pytest.mark.parametrize("payload,expected", [
    ('{"percentage":15,"plugged":"UNPLUGGED","status":"DISCHARGING"}', False),
    ('{"percentage":15,"plugged":"UNPLUGGED","status":"NOT_CHARGING"}', False),
    ('{"percentage":50,"plugged":"PLUGGED_AC","status":"CHARGING"}', True),
    ('{"status":"FULL","plugged":"PLUGGED_USB"}', True),
    ("Battery 40% (not charging)", False),
    ("Battery 40% charging", True),
    ("no idea", None),
])
def test_charging_detection(payload, expected):
    assert Executor._extract_charging(payload) is expected


# --- routing: ordinary sentences must not be hijacked ---------------------------------------
@pytest.mark.parametrize("text", ["show me the weather", "tell me a joke", "watch out for that",
                                  "explain quantum computing", "what time is it"])
def test_ordinary_sentences_go_to_hermes(text):
    assert make_stack()["engine"].route(text).route == "hermes"


def test_send_me_is_not_a_contact():
    r = make_stack()["engine"].route("send me the report")
    assert r.route == "hermes" and r.arguments.get("contact") == ""


def test_long_open_sentence_is_not_an_app():
    r = make_stack()["engine"].route("open a new issue on github and write a long description of the bug")
    assert r.route == "hermes"


def test_volume_is_clamped():
    r = make_stack()["engine"].route("set volume to 250")
    assert r.route == "local" and r.arguments["level"] == 100


def test_trace_is_stored_as_json_list_not_double_encoded():
    s = make_stack()
    s["engine"].route("open maps")
    stages = s["db"].conn.execute("SELECT stages FROM route_trace ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert isinstance(json.loads(stages), list)


# --- skills: learned skills must not become arbitrary code execution --------------------------
def _skill(**over):
    d = {"id": "my_helper", "category": "files", "risk": "low", "examples": ["do my thing"],
         "executor": {"command": "my-helper"}}
    d.update(over)
    return d


@pytest.mark.parametrize("bad", [
    _skill(id="call_contact"),                              # override a built-in
    _skill(executor={"command": "bash"}),                   # shell
    _skill(executor={"command": "/bin/sh"}),                # path
    _skill(executor={"command": "rm -rf x"}),               # spaces
    _skill(risk="high"),
    _skill(risk="critical"),                                # unknown risk must not slip past the 'high' check
])
def test_register_rejects_dangerous_skills(bad):
    with pytest.raises(ValueError):
        make_stack()["learner"].learn(bad)


def test_register_accepts_normal_helper():
    s = make_stack()
    s["learner"].learn(_skill())
    assert s["registry"].get("my_helper")


def test_observed_skill_without_risk_is_not_auto_eligible():
    s = make_stack()
    d = {"id": "norisk_helper", "category": "files", "examples": ["do it"], "executor": {"command": "norisk-helper"}}
    for _ in range(3):
        out = s["learner"].observe("do it", d)
    assert out.get("status") != "eligible"


# --- memory ------------------------------------------------------------------------------------
def test_project_validates_input():
    m = make_stack()["memory"]
    with pytest.raises(ValueError):
        m.project({"type": "alias", "subject": "", "value": "x"})
    with pytest.raises(ValueError):
        m.project({"type": "alias", "subject": "x"})


@pytest.mark.parametrize("text", [
    "I found no verified alias for Govind, only unrelated memories.",
    "Govind's alias is not stated anywhere.",
    "Someone else is also known as butagorira.",   # not about the requested subject
    "a b c d e",
])
def test_alias_normalizer_rejects_unclear_text(text):
    assert make_stack()["memory"]._normalize_alias("Govind", text) is None


def test_direct_miss_is_negatively_cached_and_does_not_poison_aliases():
    s = make_stack(memory_mode="hybrid", hindsight_cmd="false", direct_timeout=1)  # adapter always fails
    m = s["memory"]
    assert m.lookup("alias", "nobody", "communication") is None
    hot = m.lookup_hot("alias", "nobody", "communication")
    assert hot and hot["_negative"] is True
    assert s["context"].resolve_alias("nobody") == ("nobody", "none")   # falls back to the literal name
    assert all(r["subject"] != "nobody" for r in s["db"].hot_list())      # markers hidden from listings
    m.project({"type": "alias", "subject": "nobody", "value": "somebody", "scope": "communication"})
    assert m.lookup_hot("alias", "nobody", "communication")["value"] == "somebody"


# --- API -----------------------------------------------------------------------------------------
@pytest.fixture()
def api():
    Handler.stack = make_stack()
    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def _post(url, body, ctype="application/json"):
    req = urllib.request.Request(url, data=body, headers={"Content-Type": ctype}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_api_routes(api):
    code, out = _post(api + "/v1/route", b'{"text":"open maps"}')
    assert code == 200 and out["skill"] == "open_app"


def test_api_bad_json_is_400_not_a_crash(api):
    assert _post(api + "/v1/route", b"{not json")[0] == 400
    assert _post(api + "/v1/route", b"[1,2]")[0] == 400


def test_api_rejects_cross_site_style_content_type(api):
    assert _post(api + "/v1/skills", b"{}", ctype="text/plain")[0] == 400
