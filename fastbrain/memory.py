from __future__ import annotations

import json
import re
import shlex
import subprocess
import time
import urllib.request


class MemoryBridge:
    """Hindsight bridge supporting hot cache, direct lookup, and safe hybrid promotion."""

    PROMOTABLE_TYPES = {
        "alias", "preference", "default", "relationship", "routine",
        "skill_hint", "constraint", "channel_preference", "time_preference",
    }

    MIN_PROMOTE_CONFIDENCE = {
        "alias": 0.85, "preference": 0.75, "default": 0.80,
        "relationship": 0.80, "routine": 0.75, "skill_hint": 0.80,
        "constraint": 0.85, "channel_preference": 0.80,
        "time_preference": 0.75,
    }

    def __init__(self, db, cfg):
        self.db = db
        self.cfg = cfg

    def project(self, memory):
        self.db.upsert_hot(memory)

    def lookup_hot(self, typ, subject, scope=""):
        result = self.db.hot_get(typ, subject, scope)
        if result:
            result["_source"] = "hot"
        return result

    @staticmethod
    def _clean_text(value):
        if not isinstance(value, str):
            return value
        return " ".join(value.strip().split())

    def _build_query(self, typ, subject, scope=""):
        subject = str(subject).strip()
        scope = str(scope).strip()
        if typ == "alias":
            return f"What alias, nickname, alternate name, handle, or contact identity is associated with {subject}?"
        if typ == "preference":
            if scope:
                return f"What are the user's preferences for {scope} in the context of {subject}?"
            return f"What does the user prefer regarding {subject}?"
        if typ == "channel_preference":
            return f"What communication channel does the user prefer for {subject}?"
        if typ == "time_preference":
            return f"What time-related preference does the user have for {subject}?"
        if typ == "routine":
            return f"What routine does the user follow for {subject}?"
        if typ == "default":
            return f"What default should be used for {subject}{' in ' + scope if scope else ''}?"
        if typ == "constraint":
            return f"What constraint or rule applies to {subject}{' in ' + scope if scope else ''}?"
        if typ == "relationship":
            return f"What relationship or identity information is known about {subject}?"
        return f"What relevant memory is known about {subject}{' for ' + scope if scope else ''}?"

    def _normalize_alias(self, subject, value):
        value = self._clean_text(value)
        if not isinstance(value, str) or not value:
            return None
        if len(value) <= 64 and re.fullmatch(r"[@\w.+-]+", value, flags=re.UNICODE):
            return value
        esc = re.escape(subject)
        patterns = [
            rf"(?i)\b{esc}\b\s*(?:=|->|→|:|is\s+also\s+known\s+as|is\s+known\s+as|aka|alias(?:\s+is)?)\s*[`\"']?([@\w.+-]{{2,64}})",
            rf"(?i)([@\w.+-]{{2,64}})\s+(?:is\s+an?\s+alias\s+of|is\s+the\s+alias\s+for|refers\s+to)\s+{esc}\b",
        ]
        for pattern in patterns:
            match = re.search(pattern, value)
            if match:
                candidate = match.group(1).strip("`\"'")
                if candidate.lower() != subject.lower():
                    return candidate
        return None

    def _normalize_direct(self, typ, subject, scope, data):
        if not isinstance(data, dict) or "value" not in data:
            return data
        value = data.get("value")
        confidence = float(data.get("confidence", 0.8) or 0.8)
        if typ == "alias":
            alias = self._normalize_alias(subject, value)
            if not alias:
                data["_promotable"] = False
                data["_promotion_reason"] = "alias_not_structurally_resolved"
                return data
            data["value"] = alias
            data["confidence"] = max(confidence, 0.90)
        elif isinstance(value, str):
            compact = self._clean_text(value)
            if len(compact) > 240:
                data["_promotable"] = False
                data["_promotion_reason"] = "value_too_long"
                return data
            data["value"] = compact
        data.setdefault("type", typ)
        data.setdefault("subject", subject)
        data.setdefault("scope", scope)
        return data

    def should_promote(self, typ, data):
        if typ not in self.PROMOTABLE_TYPES:
            return False, "type_not_promotable"
        if not isinstance(data, dict) or "value" not in data:
            return False, "no_usable_value"
        if data.get("_promotable") is False:
            return False, data.get("_promotion_reason", "normalization_rejected")
        confidence = float(data.get("confidence", 0.0) or 0.0)
        minimum = self.MIN_PROMOTE_CONFIDENCE.get(typ, 0.80)
        if confidence < minimum:
            return False, f"confidence_below_{minimum:.2f}"
        return True, "eligible"

    def _run_direct_command(self, payload):
        started = time.perf_counter()
        proc = subprocess.run(
            shlex.split(self.cfg.hindsight_cmd),
            input=json.dumps(payload), text=True, capture_output=True,
            timeout=self.cfg.direct_timeout,
        )
        return proc, (time.perf_counter() - started) * 1000

    def debug_direct(self, typ, subject, scope=""):
        payload = {
            "type": typ, "subject": subject, "scope": scope,
            "query": self._build_query(typ, subject, scope), "fastbrain": True,
        }
        if self.cfg.hindsight_cmd:
            started = time.perf_counter()
            try:
                proc, latency = self._run_direct_command(payload)
                return {
                    "transport": "command", "query": payload["query"],
                    "command": shlex.split(self.cfg.hindsight_cmd),
                    "returncode": proc.returncode, "latency_ms": latency,
                    "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:],
                }
            except Exception as exc:
                return {
                    "transport": "command", "query": payload["query"],
                    "latency_ms": (time.perf_counter() - started) * 1000,
                    "error": repr(exc),
                }
        return {"transport": "http" if self.cfg.hindsight_url else "none", "query": payload["query"]}

    def lookup_direct(self, typ, subject, scope=""):
        payload = {
            "type": typ,
            "subject": subject,
            "scope": scope,
            "query": self._build_query(typ, subject, scope),
            "fastbrain": True,
        }
        started = time.perf_counter()
        try:
            if self.cfg.hindsight_cmd:
                proc, _ = self._run_direct_command(payload)
                if proc.returncode:
                    return None
                data = json.loads(proc.stdout or "{}")
            elif self.cfg.hindsight_url:
                request = urllib.request.Request(
                    self.cfg.hindsight_url + self.cfg.hindsight_path,
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"}, method="POST",
                )
                with urllib.request.urlopen(request, timeout=self.cfg.direct_timeout) as response:
                    data = json.loads(response.read().decode())
            else:
                return None

            if isinstance(data, dict) and "result" in data and isinstance(data["result"], dict):
                data = data["result"]
            elif isinstance(data, dict) and data.get("memories"):
                data = data["memories"][0]

            if not isinstance(data, dict):
                return None
            if "value" not in data:
                value = data.get("fact") or data.get("content")
                if value is None:
                    return None
                data = {
                    "type": typ, "subject": subject, "scope": scope,
                    "value": value, "confidence": data.get("confidence", 0.8),
                }

            data = self._normalize_direct(typ, subject, scope, data)
            data["_source"] = "direct"
            data["_latency_ms"] = (time.perf_counter() - started) * 1000
            promotable, reason = self.should_promote(typ, data)
            data["_promotable"] = promotable
            data["_promotion_reason"] = reason
            return data
        except Exception:
            return None

    def promote_direct_result(self, typ, subject, scope, result):
        promotable, reason = self.should_promote(typ, result)
        if not promotable:
            return False, reason
        memory = {
            "type": typ, "subject": subject,
            "scope": result.get("scope", scope), "value": result["value"],
            "confidence": result.get("confidence", 0.8),
            "priority": result.get("priority", 50),
        }
        self.project(memory)
        return True, "promoted"

    def lookup(self, typ, subject, scope=""):
        mode = self.cfg.memory_mode
        if mode in {"hot", "hybrid"}:
            result = self.lookup_hot(typ, subject, scope)
            if result:
                return result
        if mode in {"direct", "hybrid"}:
            result = self.lookup_direct(typ, subject, scope)
            if result and mode == "hybrid":
                promoted, reason = self.promote_direct_result(typ, subject, scope, result)
                result["_promoted"] = promoted
                result["_promotion_reason"] = reason
            return result
        return None
