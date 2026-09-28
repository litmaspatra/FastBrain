#!/usr/bin/env python3
"""FastBrain -> Hindsight Lite command adapter.

Reads one JSON object from stdin and returns one normalized memory candidate.
Runs inside Hermes' own Python environment so FastBrain's Python 3.13 runtime
remains isolated from Hermes/Hindsight dependencies.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _first_result(raw):
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            raw = json.loads(text)
        except Exception:
            return {"content": text, "confidence": 0.8}

    if isinstance(raw, list):
        return raw[0] if raw else None

    if isinstance(raw, dict):
        for key in ("result", "memory", "item"):
            if isinstance(raw.get(key), dict):
                return raw[key]
        for key in ("results", "memories", "items"):
            value = raw.get(key)
            if isinstance(value, list) and value:
                return value[0]
        return raw

    return None


def normalize(raw, payload):
    item = _first_result(raw)
    if not isinstance(item, dict):
        return {}

    value = (
        item.get("value")
        or item.get("fact")
        or item.get("content")
        or item.get("text")
        or item.get("memory")
    )
    if value is None:
        return {"raw": raw}

    confidence = item.get("confidence")
    if confidence is None:
        # Hindsight's semantic score is ranking-oriented and can be numerically
        # small, so do not treat it as confidence. Use a conservative default.
        confidence = 0.8

    return {
        "type": payload.get("type", item.get("type", "memory")),
        "subject": payload.get("subject", item.get("subject", "")),
        "scope": payload.get("scope", item.get("scope", "")),
        "value": value,
        "confidence": confidence,
        "raw": item,
    }


def main() -> int:
    payload = json.load(sys.stdin)
    query = str(payload.get("query") or "").strip()
    if not query:
        print(json.dumps({}))
        return 2

    hermes_home = os.environ.get("HERMES_HOME", str(Path.home() / ".hermes"))
    session_id = os.environ.get("FASTBRAIN_HINDSIGHT_SESSION", "fastbrain-direct")
    limit = int(os.environ.get("FASTBRAIN_HINDSIGHT_LIMIT", "3"))
    limit = max(1, min(100, limit))

    from hindsight_lite.hermes import HermesMemoryBridge

    bridge = HermesMemoryBridge()
    try:
        bridge.initialize(session_id=session_id, hermes_home=hermes_home)
        raw = bridge.tool("hmem_recall", {"query": query, "limit": limit})
        print(json.dumps(normalize(raw, payload), ensure_ascii=False))
        return 0
    finally:
        try:
            bridge.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
