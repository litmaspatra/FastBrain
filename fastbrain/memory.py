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
        "alias",
        "preference",
        "default",
        "relationship",
        "routine",
        "skill_hint",
        "constraint",
        "channel_preference",
        "time_preference",
    }

    MIN_PROMOTE_CONFIDENCE = {
        "alias": 0.85,
        "preference": 0.75,
        "default": 0.80,
        "relationship": 0.80,
        "routine": 0.75,
        "skill_hint": 0.80,
        "constraint": 0.85,
        "channel_preference": 0.80,
        "time_preference": 0.75,
    }

    TIME_BUCKETS = {"morning", "afternoon", "evening", "night"}
    NEGATIVE_TTL_SECONDS = 3600
    NEGATIVE_SENTINEL = "__fastbrain_negative__"

    def __init__(self, db, cfg):
        self.db = db
        self.cfg = cfg

    def project(self, memory):
        self.db.upsert_hot(memory)

    def lookup_hot(self, typ, subject, scope=""):
        result = self.db.hot_get(typ, subject, scope)
        if result:
            result["_source"] = "hot"
            if isinstance(result.get("value"), dict) and result["value"].get(self.NEGATIVE_SENTINEL):
                result["_negative"] = True
        return result

    def _cache_negative(self, typ, subject, scope, reason="no_relevant_direct_memory"):
        self.project(
            {
                "type": typ,
                "subject": subject,
                "scope": scope,
                "value": {self.NEGATIVE_SENTINEL: True, "reason": reason},
                "confidence": 1.0,
                "priority": 1,
                "expires_at": time.time() + self.NEGATIVE_TTL_SECONDS,
            }
        )

    @staticmethod
    def _clean_text(value):
        if not isinstance(value, str):
            return value
        return " ".join(value.strip().split())

    @staticmethod
    def _raw_content(data):
        raw = data.get("raw") if isinstance(data, dict) else None
        if isinstance(raw, dict):
            return str(raw.get("content") or raw.get("text") or "")
        return str(raw or "")

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

    def _normalize_preference(self, subject, scope, value):
        value = self._clean_text(value)
        if not isinstance(value, str) or not value:
            return None

        if len(value) <= 80 and not re.search(r"(?i)\b(user|preference|prefers|likes|favorite|favourite)\b", value):
            return value.rstrip(".")

        patterns = [
            r"(?i)\bpreference\s+is\s+(.+?)(?:\.|$)",
            r"(?i)\bprefers?\s+(.+?)(?:\.|$)",
            r"(?i)\blikes?\s+(.+?)(?:\.|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, value)
            if match:
                candidate = match.group(1).strip(" `\"'.")
                if scope and subject:
                    candidate = re.sub(
                        rf"(?i)\s+(?:in|during|for)\s+(?:the\s+)?{re.escape(subject)}\b.*$",
                        "",
                        candidate,
                    ).strip()
                if candidate and len(candidate) <= 120:
                    return candidate
        return None

    def _query_for(self, typ, subject, scope):
        if typ == "alias":
            return f"What alias, nickname, alternate name, handle, or contact identity is associated with {subject}?"
        if typ == "preference":
            context = f" in the context of {subject}" if subject else ""
            topic = f" for {scope}" if scope else ""
            return f"What are the user's preferences{topic}{context}?"
        if typ == "default":
            return f"What default should be used for {subject} in {scope or 'this context'}?"
        if typ == "channel_preference":
            return f"What communication channel does the user prefer for {subject}?"
        if typ == "time_preference":
            return f"What time preference does the user have for {subject} in {scope or 'this context'}?"
        if typ == "routine":
            return f"What routine does the user follow for {subject} in {scope or 'this context'}?"
        if typ == "constraint":
            return f"What important constraint applies to {subject} in {scope or 'this context'}?"
        return f"What should FastBrain remember about {subject} for {typ} in {scope or 'this context'}?"

    def _context_matches(self, typ, subject, data):
        """Reject semantically-near but contextually-wrong memories.

        Hindsight may return the closest music preference even when the requested
        time bucket differs. For time-bucket preferences we require explicit
        evidence for the requested bucket in the recalled memory.
        """
        if typ not in {"preference", "time_preference"}:
            return True, "context_not_required"
        wanted = str(subject or "").lower().strip()
        if wanted not in self.TIME_BUCKETS:
            return True, "non_time_subject"

        text = self._raw_content(data).lower()
        mentioned = {bucket for bucket in self.TIME_BUCKETS if re.search(rf"\b{bucket}\b", text)}
        if wanted in mentioned:
            return True, "time_context_match"
        if mentioned:
            return False, "time_context_mismatch"
        return False, "time_context_not_explicit"

    def _normalize_direct(self, typ, subject, scope, data):
        if not isinstance(data, dict) or "value" not in data:
            return data

        context_ok, context_reason = self._context_matches(typ, subject, data)
        if not context_ok:
            data["_promotable"] = False
            data["_promotion_reason"] = context_reason
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

        elif typ == "preference":
            pref = self._normalize_preference(subject, scope, value)
            if not pref:
                data["_promotable"] = False
                data["_promotion_reason"] = "preference_not_structurally_resolved"
                return data
            data["value"] = pref

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

    def _run_direct_transport(self, payload):
        if self.cfg.hindsight_cmd:
            proc = subprocess.run(
                shlex.split(self.cfg.hindsight_cmd),
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                timeout=self.cfg.direct_timeout,
            )
            return {
                "transport": "command",
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        if self.cfg.hindsight_url:
            request = urllib.request.Request(
                self.cfg.hindsight_url + self.cfg.hindsight_path,
                data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=self.cfg.direct_timeout) as response:
                return {
                    "transport": "http",
                    "status": getattr(response, "status", 200),
                    "stdout": response.read().decode(),
                    "stderr": "",
                }
        return {"transport": "none", "stdout": "", "stderr": "not configured"}

    def debug_direct(self, typ, subject, scope=""):
        payload = {
            "type": typ,
            "subject": subject,
            "scope": scope,
            "query": self._query_for(typ, subject, scope),
            "fastbrain": True,
        }
        started = time.perf_counter()
        try:
            result = self._run_direct_transport(payload)
            result["query"] = payload["query"]
            result["latency_ms"] = (time.perf_counter() - started) * 1000
            if self.cfg.hindsight_cmd:
                result["command"] = shlex.split(self.cfg.hindsight_cmd)
            return result
        except Exception as exc:
            return {
                "query": payload["query"],
                "latency_ms": (time.perf_counter() - started) * 1000,
                "error": repr(exc),
            }

    def lookup_direct(self, typ, subject, scope=""):
        payload = {
            "type": typ,
            "subject": subject,
            "scope": scope,
            "query": self._query_for(typ, subject, scope),
            "fastbrain": True,
        }
        started = time.perf_counter()
        try:
            transport = self._run_direct_transport(payload)
            if transport.get("transport") == "command" and transport.get("returncode"):
                return None
            data = json.loads(transport.get("stdout") or "{}")

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
                    "type": typ,
                    "subject": subject,
                    "scope": scope,
                    "value": value,
                    "confidence": data.get("confidence", 0.8),
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
            "type": typ,
            "subject": subject,
            "scope": result.get("scope", scope),
            "value": result["value"],
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
                if result.get("_negative"):
                    return None
                return result

        if mode in {"direct", "hybrid"}:
            result = self.lookup_direct(typ, subject, scope)
            if not result:
                if mode == "hybrid":
                    self._cache_negative(typ, subject, scope, "direct_empty")
                return None

            promotable, reason = self.should_promote(typ, result)
            if not promotable:
                if mode == "hybrid":
                    self._cache_negative(typ, subject, scope, reason)
                return None

            if mode == "hybrid":
                promoted, reason = self.promote_direct_result(typ, subject, scope, result)
                result["_promoted"] = promoted
                result["_promotion_reason"] = reason
            return result

        return None
