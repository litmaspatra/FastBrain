"""Hot-cache memory with an optional direct Hindsight lookup.

Hindsight stays the durable source of truth. FastBrain keeps a small SQLite
"hot" cache of facts that are cheap to resolve, and can ask Hindsight directly
(HTTP endpoint or command adapter) on a miss.

Only structurally clear results are promoted into the hot cache. A prose answer
such as "I found several memories about Govind..." is returned to the caller but
never turned into an alias.
"""
from __future__ import annotations

import json
import re
import shlex
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

_NEGATIVE_MISS_TTL = 600.0   # direct lookup answered "nothing": don't ask again for 10 min
_NEGATIVE_ERROR_TTL = 30.0   # direct lookup failed/timed out: back off briefly
_PROMOTE_MIN_CONFIDENCE = 0.75

_ALIAS_PATTERN = re.compile(
    r"(?:also\s+known\s+as|a\.?k\.?a\.?|alias(?:ed)?\s+(?:is|as)|nickname\s+(?:is|:)|"
    r"saved\s+(?:in\s+contacts\s+)?as|contact\s+name\s+is|is\s+called)\s+"
    r"[\"'\u201c]?([^\"'\u201d.,;:!?\n]+?)[\"'\u201d]?"
    r"(?=\s+(?:in|on|for|when|while|within|across|and)\b|[.,;:!?]|$)",
    re.I,
)
_NEGATION = re.compile(r"\b(?:no|not|never|none|unknown|unclear|unrelated|unverified|cannot|can't|couldn't)\b", re.I)
_SENTENCE_PUNCT = re.compile(r"[.!?:;]")


class MemoryBridge:
    def __init__(self, db, cfg):
        self.db = db
        self.cfg = cfg
        self.last_direct_error = ""

    # ------------------------------------------------------------------ hot cache
    def project(self, m: dict[str, Any]) -> None:
        """Write one fact into the hot cache."""
        typ = str(m.get("type") or "").strip()
        subject = str(m.get("subject") or "").strip()
        if not typ or not subject:
            raise ValueError("memory needs non-empty 'type' and 'subject'")
        if m.get("value") is None:
            raise ValueError("memory needs a 'value'")
        self.db.upsert_hot({
            "type": typ,
            "subject": subject,
            "value": m["value"],
            "scope": str(m.get("scope") or ""),
            "confidence": m.get("confidence", 1),
            "priority": m.get("priority", 50),
            "expires_at": m.get("expires_at"),
        })

    def lookup_hot(self, typ: str, subject: str, scope: str = ""):
        row = self.db.hot_get(typ, subject, scope)
        if not row:
            return None
        if row["value"] is None:  # negative-cache marker
            return {**row, "_source": "hot", "_negative": True}
        return {**row, "_source": "hot"}

    def _remember_miss(self, typ: str, subject: str, scope: str, ttl: float) -> None:
        # Never overwrite a real value with a miss marker.
        existing = self.db.hot_get(typ, subject, scope)
        if existing and existing["value"] is not None:
            return
        self.db.upsert_hot({
            "type": typ, "subject": subject, "value": None, "scope": scope,
            "confidence": 0, "priority": 0, "expires_at": time.time() + ttl,
        })

    # --------------------------------------------------------------- direct lookup
    @property
    def direct_configured(self) -> bool:
        return bool(self.cfg.hindsight_cmd or self.cfg.hindsight_url)

    @staticmethod
    def _payload(typ: str, subject: str, scope: str) -> dict[str, Any]:
        return {
            "query": " ".join(x for x in (typ, subject, scope) if x),
            "type": typ,
            "subject": subject,
            "scope": scope,
        }

    @staticmethod
    def _first_item(raw: Any):
        if isinstance(raw, list):
            raw = next((x for x in raw if isinstance(x, dict)), None)
        if isinstance(raw, dict):
            for key in ("result", "memory", "item"):
                if isinstance(raw.get(key), dict):
                    return raw[key]
            for key in ("results", "memories", "items"):
                value = raw.get(key)
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    return value[0]
        return raw if isinstance(raw, dict) else None

    def _direct_raw(self, payload: dict[str, Any]) -> Any:
        timeout = max(0.05, float(self.cfg.direct_timeout))
        if self.cfg.hindsight_cmd:
            proc = subprocess.run(
                shlex.split(self.cfg.hindsight_cmd),
                input=json.dumps(payload), capture_output=True, text=True, timeout=timeout,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"adapter exit {proc.returncode}: {(proc.stderr or '').strip()[:200]}")
            # Libraries sometimes print noise first; the JSON object is the last line.
            lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
            for line in reversed(lines):
                if line.lstrip().startswith(("{", "[")):
                    return json.loads(line)
            raise RuntimeError("adapter produced no JSON")
        base = self.cfg.hindsight_url
        if urlparse(base).scheme not in {"http", "https"}:
            raise RuntimeError("FASTBRAIN_HINDSIGHT_URL must be http(s)")
        req = urllib.request.Request(
            base + (self.cfg.hindsight_path or ""),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def _normalize_direct(self, raw: Any, typ: str, subject: str, scope: str):
        item = self._first_item(raw)
        if not item:
            return None
        value = None
        for key in ("value", "fact", "content", "text", "memory"):
            if item.get(key) not in (None, ""):
                value = item[key]
                break
        if value is None:
            return None
        try:
            confidence = float(item.get("confidence", 0.8))
        except (TypeError, ValueError):
            confidence = 0.0
        return {"type": typ, "subject": subject, "scope": scope, "value": value, "confidence": confidence}

    def lookup_direct(self, typ: str, subject: str, scope: str = ""):
        """Ask Hindsight directly. Returns a normalized dict or None (never raises)."""
        self.last_direct_error = ""
        if not self.direct_configured:
            self.last_direct_error = "not_configured"
            return None
        try:
            raw = self._direct_raw(self._payload(typ, subject, scope))
            return self._normalize_direct(raw, typ, subject, scope)
        except Exception as exc:  # timeout, adapter crash, bad JSON, connection refused...
            self.last_direct_error = f"{type(exc).__name__}: {exc}"
            return None

    def debug_direct(self, typ: str, subject: str, scope: str = ""):
        payload = self._payload(typ, subject, scope)
        out: dict[str, Any] = {
            "configured": self.direct_configured,
            "mode": self.cfg.memory_mode,
            "transport": "command" if self.cfg.hindsight_cmd else ("http" if self.cfg.hindsight_url else None),
            "timeout": self.cfg.direct_timeout,
            "request": payload,
        }
        if not self.direct_configured:
            out.update(ok=False, error="not_configured")
            return out
        started = time.perf_counter()
        try:
            raw = self._direct_raw(payload)
            out.update(ok=True, raw=raw, normalized=self._normalize_direct(raw, typ, subject, scope))
        except Exception as exc:
            out.update(ok=False, error=f"{type(exc).__name__}: {exc}")
        out["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        return out

    # ------------------------------------------------------------------ promotion
    @staticmethod
    def _normalize_alias(subject: str, value: Any):
        """Return a clean alias target or None when the text is not structurally clear."""
        if not isinstance(value, str):
            return None
        text = " ".join(value.split())
        if not text or _NEGATION.search(text):
            return None
        found = _ALIAS_PATTERN.search(text)
        if found:
            candidate = found.group(1).strip()
            # The sentence must actually be about the subject we asked for.
            if subject.strip().lower() not in text.lower()[: found.start()]:
                return None
        elif not _SENTENCE_PUNCT.search(text):
            candidate = text
        else:
            return None
        if not candidate or len(candidate.split()) > 3 or len(candidate) > 60:
            return None
        return candidate

    def promote_direct_result(self, typ: str, subject: str, scope: str, direct: dict[str, Any]):
        """Copy a trustworthy direct result into the hot cache. Returns (promoted, reason)."""
        if not isinstance(direct, dict) or direct.get("value") in (None, ""):
            return False, "empty_result"
        try:
            confidence = float(direct.get("confidence", 0) or 0)
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < _PROMOTE_MIN_CONFIDENCE:
            return False, "low_confidence"
        value = direct["value"]
        if typ == "alias":
            value = self._normalize_alias(subject, value)
            if value is None:
                return False, "alias_not_structurally_resolved"
        elif isinstance(value, str) and (len(value) > 120 or _SENTENCE_PUNCT.search(value.rstrip(". "))):
            return False, "value_not_structured"
        self.project({
            "type": typ, "subject": subject, "value": value, "scope": scope,
            "confidence": confidence, "priority": 60,
        })
        direct["value"] = value
        return True, "promoted"

    # --------------------------------------------------------------------- lookup
    def lookup(self, typ: str, subject: str, scope: str = ""):
        """Mode-aware lookup: hot first, then Hindsight on a miss (hybrid)."""
        mode = (self.cfg.memory_mode or "hybrid").lower()
        if mode != "direct":
            hot = self.lookup_hot(typ, subject, scope)
            if hot:
                return None if hot.get("_negative") else hot
        if mode == "hot" or not self.direct_configured:
            return None
        direct = self.lookup_direct(typ, subject, scope)
        if direct is None:
            if mode == "hybrid":
                ttl = _NEGATIVE_ERROR_TTL if self.last_direct_error else _NEGATIVE_MISS_TTL
                self._remember_miss(typ, subject, scope, ttl)
            return None
        result = dict(direct)
        result["_source"] = "direct"
        result["_promoted"] = False
        if mode == "hybrid":
            promoted, reason = self.promote_direct_result(typ, subject, scope, result)
            result["_promoted"] = promoted
            result["_promotion_reason"] = reason
        return result

    def warm(self, typ: str, subject: str, scope: str = ""):
        """Fetch from Hindsight now and promote, so the next lookup is a hot hit."""
        direct = self.lookup_direct(typ, subject, scope)
        if direct is None:
            return {"ok": False, "error": self.last_direct_error or "no_result",
                    "type": typ, "subject": subject, "scope": scope}
        promoted, reason = self.promote_direct_result(typ, subject, scope, direct)
        return {"ok": promoted, "promoted": promoted, "promotion_reason": reason, "direct": direct,
                "hot": self.lookup_hot(typ, subject, scope) if promoted else None}
