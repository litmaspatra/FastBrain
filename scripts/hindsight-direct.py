#!/usr/bin/env python3
"""FastBrain -> Hindsight Lite command adapter.

Reads one JSON object from stdin:
  {"query":"...", "type":"alias", "subject":"govind", "scope":"communication"}

Runs inside Hermes' own Python environment, initializes HermesMemoryBridge, calls
hmem_recall, and prints normalized JSON for FastBrain. This file deliberately has
no FastBrain imports so the two Python environments stay isolated.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def normalize(raw, payload):
    """Normalize common Hindsight recall shapes to a FastBrain-compatible dict."""
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            raw = json.loads(text)
        except Exception:
            return {
                "type": payload.get("type", "memory"),
                "subject": payload.get("subject", ""),
                "scope": payload.get("scope", ""),
                "value": text,
                "confidence": 0.8,
                "raw": text,
            }

    if isinstance(raw, list):
        if not raw:
            return {}
        raw = raw[0]

    if isinstance(raw, dict):
        for key in ("result", "memory", "item"):
            if isinstance(raw.get(key), dict):
                raw = raw[key]
                break
        memories = raw.get("memories") if isinstance(raw, dict) else None
        if isinstance(memories, list) and memories:
            raw = memories[0]

    if not isinstance(raw, dict):
        return {}

    value = (
        raw.get("value")
        or raw.get("fact")
        or raw.get("content")
        or raw.get("text")
        or raw.get("memory")
    )
    if value is None:
        # Preserve the object for debugging, but don't claim a usable memory.
        return {"raw": raw}

    return {
        "type": payload.get("type", raw.get("type", "memory")),
        "subject": payload.get("subject", raw.get("subject", "")),
        "scope": payload.get("scope", raw.get("scope", "")),
        "value": value,
        "confidence": raw.get("confidence", raw.get("score", 0.8)),
        "raw": raw,
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
