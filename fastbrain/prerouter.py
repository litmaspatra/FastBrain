"""Sidecar-only, request-idempotent pre-router for FastBrain actions."""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from typing import Any


_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")
_READ_ONLY = {"battery_status"}


class PreRouter:
    """Reserve local work before execution so reconnects cannot duplicate it."""

    def __init__(self, engine: Any, executor: Any, db: Any, ttl_seconds: float = 86400.0):
        self.engine = engine
        self.executor = executor
        self.db = db
        self.ttl_seconds = float(ttl_seconds)

    @staticmethod
    def _fingerprint(text: str, route: Any) -> str:
        canonical = json.dumps(
            {
                "text": " ".join(str(text or "").split()),
                "route": route.route,
                "skill": route.skill,
                "arguments": route.arguments,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _summary(result: dict[str, Any]) -> dict[str, Any]:
        keys = ("executed", "success", "error", "operation", "executor_source", "fallback", "native_error", "latency_ms")
        return {key: result[key] for key in keys if key in result}

    @staticmethod
    def _response(request_id: str | None, decision: str, consequential: bool, *, execution: dict[str, Any] | None = None, replayed: bool = False, approval_token: str | None = None, error: str | None = None):
        fallback = decision == "decline"
        response = {
            "version": 1,
            "request_id": request_id,
            "decision": decision,
            "fallback_to_hermes": fallback,
            "consequential": consequential,
            "exit_code": 64 if fallback else (0 if decision == "handled" else 75),
        }
        if execution is not None:
            response["execution"] = execution
        if replayed:
            response["replayed"] = True
        if approval_token is not None:
            response["approval_token"] = approval_token
        if error is not None:
            response["error"] = error
        return response

    def _execute(self, route: Any, request_id: str | None, fingerprint: str | None, consequential: bool):
        try:
            result = self.executor.execute(route, confirmed=consequential)
        except Exception as exc:
            result = {"executed": False, "success": False, "error": f"prerouter_execution_error: {type(exc).__name__}"}
        summary = self._summary(result)
        indeterminate = consequential and not bool(result.get("success"))
        if request_id and fingerprint:
            self.db.preroute_finish(request_id, fingerprint, "indeterminate" if indeterminate else "completed", summary, self.ttl_seconds)
        return self._response(request_id, "indeterminate" if indeterminate else "handled", consequential, execution=summary)

    def handle(self, text: str, request_id: str | None = None, approval_token: str | None = None) -> dict[str, Any]:
        request_id = request_id or None
        if request_id is not None and not _REQUEST_ID.fullmatch(request_id):
            return self._response(request_id, "request_id_conflict", False, error="invalid_request_id")
        route = self.engine.route(text)
        if route.route != "local" or route.skill == "normal_hermes":
            return self._response(request_id, "decline", False)

        consequential = route.skill not in _READ_ONLY
        fingerprint = self._fingerprint(text, route)
        if not request_id:
            if consequential:
                return self._response(None, "approval_required", True, error="request_id_required")
            return self._execute(route, None, None, False)

        issued_token = secrets.token_urlsafe(24) if consequential and not approval_token else None
        token_hash = hashlib.sha256((approval_token or issued_token or "").encode("utf-8")).hexdigest() if consequential else None
        reservation = self.db.preroute_reserve(request_id, fingerprint, consequential, token_hash, self.ttl_seconds)
        status = reservation["status"]
        if status == "conflict":
            return self._response(request_id, "request_id_conflict", consequential)
        if status == "completed":
            return self._response(request_id, "handled", consequential, execution=reservation.get("result", {}), replayed=True)
        if status == "indeterminate":
            return self._response(request_id, "indeterminate", consequential)
        if status == "approval_required":
            return self._response(request_id, "approval_required", True, approval_token=issued_token, error=None if issued_token else "approval_token_invalid_or_already_used")
        if status == "executing" and not (reservation.get("created") or reservation.get("approved")):
            return self._response(request_id, "in_progress", consequential)
        return self._execute(route, request_id, fingerprint, consequential)
