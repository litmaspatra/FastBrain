import json
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from fastbrain.app import build
from fastbrain.config import Config


class GoodAliasHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        n = int(self.headers["Content-Length"])
        query = json.loads(self.rfile.read(n))
        body = json.dumps(
            {
                "type": query["type"],
                "subject": query["subject"],
                "scope": query["scope"],
                "value": "butagorira",
                "confidence": 0.99,
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ProseAliasHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        n = int(self.headers["Content-Length"])
        query = json.loads(self.rfile.read(n))
        body = json.dumps(
            {
                "type": query["type"],
                "subject": query["subject"],
                "scope": query["scope"],
                "value": (
                    "I found several historical memories about Govind. One discusses "
                    "messaging etiquette and another unrelated event, but no verified alias "
                    "is explicitly stated here."
                ),
                "confidence": 0.92,
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def make_stack(handler):
    server = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name)
    skills = Path(__file__).parents[1] / "skills" / "builtin.json"
    cfg = Config(
        root,
        root / "db",
        skills,
        memory_mode="hybrid",
        hindsight_url=f"http://127.0.0.1:{server.server_port}",
        direct_timeout=1,
    )
    return server, temp, build(cfg)


def test_direct_and_hybrid_projection():
    server, temp, stack = make_stack(GoodAliasHandler)
    result = stack["memory"].lookup("alias", "govind", "communication")
    assert result["value"] == "butagorira"
    assert result["_source"] == "direct"
    assert result["_promoted"] is True
    hot = stack["memory"].lookup_hot("alias", "govind", "communication")
    assert hot["value"] == "butagorira"
    server.shutdown()
    temp.cleanup()


def test_prose_alias_is_not_promoted():
    server, temp, stack = make_stack(ProseAliasHandler)
    result = stack["memory"].lookup("alias", "govind", "communication")
    assert result["_source"] == "direct"
    assert result["_promoted"] is False
    assert result["_promotion_reason"] == "alias_not_structurally_resolved"
    assert stack["memory"].lookup_hot("alias", "govind", "communication") is None
    server.shutdown()
    temp.cleanup()


def test_alias_sentence_is_safely_extracted():
    server, temp, stack = make_stack(GoodAliasHandler)
    normalized = stack["memory"]._normalize_alias(
        "Govind", "Govind is also known as butagorira in messaging contexts."
    )
    assert normalized == "butagorira"
    server.shutdown()
    temp.cleanup()
