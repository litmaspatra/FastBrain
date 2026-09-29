from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from difflib import SequenceMatcher
from pathlib import Path

from .models import RouteResult


class Executor:
    """Execute FastBrain skills while reusing the working Hermes Android layer."""

    def __init__(self, registry, experience, context=None):
        self.registry = registry
        self.experience = experience
        self.context = context

    @staticmethod
    def _helper_candidates(name: str):
        home = Path.home()
        return [home / ".fastbrain" / "helpers" / name, home / "hermes-phone" / "bin" / name, home / ".hermes" / "bin" / name, home / "bin" / name]

    @staticmethod
    def _is_executable(path: Path) -> bool:
        return path.is_file() and os.access(path, os.X_OK)

    @staticmethod
    def _norm_contact(value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", str(value).lower()))

    @classmethod
    def _contact_similarity(cls, a, b):
        na, nb = cls._norm_contact(a), cls._norm_contact(b)
        ca, cb = na.replace(" ", ""), nb.replace(" ", "")
        return max(SequenceMatcher(None, na, nb).ratio(), SequenceMatcher(None, ca, cb).ratio())

    def _contact_guard(self, result):
        if result.skill not in {"call_contact", "send_whatsapp", "send_sms"}:
            return {"ok": True, "status": "not_applicable"}
        contact = str(result.arguments.get("contact") or "").strip()
        if not contact:
            return {"ok": False, "status": "missing_contact"}
        if result.context_source in {"hot", "working_memory", "plan_context"}:
            return {"ok": True, "status": "trusted_context", "contact": contact}
        tool = shutil.which("termux-contact-list")
        if not tool:
            return {"ok": False, "status": "contact_verification_unavailable", "contact": contact}
        try:
            proc = subprocess.run([tool], timeout=4, capture_output=True, text=True)
            if proc.returncode != 0 or not proc.stdout.strip():
                return {"ok": False, "status": "contact_verification_failed", "contact": contact}
            contacts = json.loads(proc.stdout)
        except Exception as exc:
            return {"ok": False, "status": "contact_verification_failed", "contact": contact, "error": str(exc)}
        unique = {}
        for item in contacts if isinstance(contacts, list) else []:
            name = str(item.get("name", "")).strip() if isinstance(item, dict) else ""
            key = self._norm_contact(name)
            if name and key and key not in unique:
                unique[key] = name
        names = list(unique.values())
        q = self._norm_contact(contact)
        exact = [name for name in names if self._norm_contact(name) == q]
        if exact:
            result.arguments["contact"] = exact[0]
            if self.context is not None:
                self.context.clear_pending_confirmation()
            return {"ok": True, "status": "exact_contact", "contact": exact[0]}
        ranked = sorted(((self._contact_similarity(contact, name), name) for name in names), key=lambda x: x[0], reverse=True)
        suggestions = []
        for score, name in ranked:
            if score < 0.45:
                continue
            suggestions.append({"name": name, "score": round(score, 3)})
            if len(suggestions) == 3:
                break
        if suggestions and self.context is not None:
            self.context.set_pending_confirmation({"skill": result.skill, "arguments": dict(result.arguments), "heard": contact, "suggestion": suggestions[0]["name"]})
        return {"ok": False, "status": "contact_uncertain", "heard": contact, "suggestions": suggestions, "needs_confirmation": bool(suggestions)}

    def _resolve_command(self, result, argv):
        if result.skill in {"play_music", "choose_music_from_context", "play_video"}:
            fast_media = Path.home() / ".fastbrain" / "bin" / "fast-media"
            if self._is_executable(fast_media):
                query = str(result.arguments.get("query") or "popular songs")
                if result.skill == "play_video":
                    mode = "youtube-latest" if result.arguments.get("latest") else "youtube"
                else:
                    mode = str(result.arguments.get("player") or "simpmusic")
                    if mode not in {"simpmusic", "ytmusic"}:
                        mode = "simpmusic"
                command = [str(fast_media), mode, query]
                if result.arguments.get("avoid"):
                    command.append("--another")
                return command, "fastbrain_media"
        if result.skill in {"send_whatsapp", "send_sms"}:
            helper_name = "whatsapp-message" if result.skill == "send_whatsapp" else "send-message"
            contact = str(result.arguments.get("contact") or "")
            message = str(result.arguments.get("message") or "")
            for candidate in self._helper_candidates(helper_name):
                if self._is_executable(candidate):
                    return [str(candidate), contact, message], "hermes_helper"
        path = shutil.which(argv[0])
        if path:
            return [path, *argv[1:]], "path"
        for candidate in self._helper_candidates(argv[0]):
            if self._is_executable(candidate):
                return [str(candidate), *argv[1:]], ("fastbrain_helper" if "/.fastbrain/helpers/" in str(candidate) else "hermes_helper")
        dispatcher = Path.home() / "hermes-phone" / "bin" / "phone"
        if not self._is_executable(dispatcher):
            return None, None
        rest = list(argv[1:])
        skill = result.skill
        if skill == "call_contact":
            return [str(dispatcher), "call", *rest], "phone_dispatcher"
        if skill == "send_whatsapp":
            return [str(dispatcher), "whatsapp", result.arguments.get("contact", ""), result.arguments.get("message", "")], "phone_dispatcher"
        if skill == "send_sms":
            return [str(dispatcher), "sms", result.arguments.get("contact", ""), result.arguments.get("message", "")], "phone_dispatcher"
        if skill == "open_app":
            return [str(dispatcher), "open", *rest], "phone_dispatcher"
        if skill in {"torch_on", "torch_off", "battery_status", "wifi_status", "set_volume"}:
            return [str(dispatcher), "device", *rest], "phone_dispatcher"
        if skill in {"play_music", "choose_music_from_context"}:
            return [str(dispatcher), "play", "music", str(result.arguments.get("query") or (rest[-1] if rest else "music"))], "phone_dispatcher"
        if skill == "play_video":
            return [str(dispatcher), "play", "video", str(result.arguments.get("query") or (rest[-1] if rest else "video"))], "phone_dispatcher"
        if skill == "create_reminder":
            return [str(dispatcher), "remind", *rest], "phone_dispatcher"
        if skill == "create_obsidian_note":
            return [str(dispatcher), "note", "create", "FastBrain", str(result.arguments.get("text") or (rest[0] if rest else ""))], "phone_dispatcher"
        return None, None

    def _prepare_skill_step(self, step):
        if step.get("op") == "noop":
            return {"op": "noop", "allowed": True, "reason": "no_action"}
        if step.get("op") == "hermes_clause":
            return {"op": "hermes_clause", "text": step.get("text", ""), "context": dict(step.get("context") or {}), "allowed": False, "route": "hermes", "deferred": True, "reason": "unresolved_compound_clause"}
        if step.get("op") == "sequence":
            prepared = [self._prepare_skill_step(s) for s in (step.get("steps") or [])[:3]]
            allowed = bool(prepared) and all(bool(s.get("allowed")) for s in prepared)
            return {"op": "sequence", "steps": prepared, "allowed": allowed, "deferred": not allowed, "reason": "bounded_low_risk_sequence" if allowed else "sequence_contains_deferred_or_blocked_step"}
        sid = step.get("skill")
        if not sid:
            return {"allowed": False, "reason": "invalid_step"}
        skill = self.registry.get(sid)
        if not skill or skill.get("risk", "low") != "low":
            return {"skill": sid, "allowed": False, "reason": "secondary_skill_not_low_risk"}
        args = dict(step.get("arguments") or {})
        required = [k for k, v in (skill.get("arguments") or {}).items() if v.get("required")]
        missing = [k for k in required if not args.get(k)]
        if missing:
            return {"skill": sid, "allowed": False, "reason": "missing_arguments:" + ",".join(missing)}
        rr = RouteResult("local", skill.get("category", "unknown"), sid, args, .995, "compound_followup", step.get("source", "microreasoner"), [])
        argv = self.registry.render_command(skill, args)
        resolved, source = self._resolve_command(rr, argv or []) if argv else (None, None)
        return {"skill": sid, "allowed": bool(resolved), "arguments": args, "command": resolved, "executor_source": source, "result": rr, "timeout": float(skill.get("timeout", 8))}

    @staticmethod
    def _extract_battery_percent(text):
        s = str(text or "")
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                for key in ("percentage", "percent", "level", "battery"):
                    if key in obj:
                        v = int(obj[key])
                        if 0 <= v <= 100:
                            return v
        except Exception:
            pass
        for pattern in [r"(?i)(?:battery|level|percentage|percent)\D{0,20}(100|[1-9]?\d)\s*%?", r"\b(100|[1-9]?\d)\s*%\b"]:
            m = re.search(pattern, s)
            if m:
                return int(m.group(1))
        return None

    @staticmethod
    def _extract_charging(text):
        s = str(text or "")
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                status = str(obj.get("status") or obj.get("plugged") or "").strip().lower()
                if status:
                    if any(x in status for x in ("charging", "full", "ac", "usb", "wireless")):
                        return True
                    if any(x in status for x in ("discharging", "not charging", "unplugged")):
                        return False
        except Exception:
            pass
        low = s.lower()
        if re.search(r"\b(?:not charging|discharging|unplugged)\b", low):
            return False
        if re.search(r"\b(?:charging|full)\b", low):
            return True
        return None

    @staticmethod
    def _extract_wifi_connected(text):
        s = str(text or "")
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                state = str(obj.get("supplicant_state") or obj.get("state") or obj.get("status") or "").strip().lower()
                ssid = str(obj.get("ssid") or "").strip()
                if state:
                    if state in {"completed", "connected", "enabled"}:
                        return True
                    if state in {"disconnected", "inactive", "disabled", "uninitialized"}:
                        return False
                if ssid and ssid.lower() not in {"<unknown ssid>", "unknown", "null", "none"}:
                    return True
        except Exception:
            pass
        low = s.lower()
        if re.search(r"\b(?:disconnected|not connected|disabled|inactive)\b", low):
            return False
        if re.search(r"\b(?:connected|completed)\b", low):
            return True
        return None

    @staticmethod
    def _condition_matches(value, operator, threshold):
        if operator == "lt":
            return value < threshold
        if operator == "gt":
            return value > threshold
        if operator == "eq":
            return value == threshold
        return False

    def _prepare_followups(self, result):
        out = []
        for step in result.plan or []:
            if step.get("op") == "conditional":
                conditions = list(step.get("conditions") or [])
                if not conditions and step.get("source_result"):
                    conditions = [{"source_result": step.get("source_result"), "operator": step.get("operator"), "threshold": step.get("threshold")}]
                out.append({"op": "conditional", "conditions": conditions, "source_result": step.get("source_result"), "operator": step.get("operator"), "threshold": step.get("threshold"), "then": dict(step.get("then") or {}), "else": dict(step.get("else") or {}) if step.get("else") else None, "allowed": False, "deferred": True, "reason": "result_required_before_condition"})
                continue
            out.append(self._prepare_skill_step(step))
        return out

    def _execute_prepared_step(self, item):
        if item.get("op") == "noop":
            return {"op": "noop", "executed": False, "success": True, "reason": "no_action"}
        if item.get("op") == "sequence":
            if not item.get("allowed"):
                return {"op": "sequence", "executed": False, "success": False, "deferred": True, "reason": item.get("reason", "sequence_not_fully_local"), "steps": [{k: v for k, v in s.items() if k not in {"result", "timeout"}} for s in item.get("steps") or []]}
            results = []
            ok = True
            for step in item.get("steps") or []:
                r = self._execute_prepared_step(step)
                results.append(r)
                if r.get("success") is False:
                    ok = False
                    break
            return {"op": "sequence", "executed": any(bool(r.get("executed")) for r in results), "success": ok, "steps": results}
        if not item.get("allowed") or not item.get("command"):
            return {k: v for k, v in item.items() if k not in {"result", "timeout"}}
        fstart = time.perf_counter()
        try:
            fp = subprocess.run(item["command"], timeout=item["timeout"], capture_output=True, text=True)
            flatency = (time.perf_counter() - fstart) * 1000
            fok = fp.returncode == 0
            self.experience.record(item["skill"], fok, flatency)
            return {"skill": item["skill"], "executed": True, "success": fok, "returncode": fp.returncode, "latency_ms": flatency, "command": item["command"], "executor_source": item["executor_source"], "stdout": fp.stdout[-500:], "stderr": fp.stderr[-500:]}
        except Exception as exc:
            flatency = (time.perf_counter() - fstart) * 1000
            self.experience.record(item.get("skill", "unknown"), False, flatency)
            return {"skill": item.get("skill"), "executed": True, "success": False, "latency_ms": flatency, "command": item.get("command"), "error": str(exc)}

    def _condition_value(self, source_result, primary_output):
        if source_result == "battery_status":
            return self._extract_battery_percent(primary_output)
        if source_result == "battery_charging":
            return self._extract_charging(primary_output)
        if source_result == "wifi_connected":
            return self._extract_wifi_connected(primary_output)
        return None

    def _evaluate_conditions(self, conditions, primary_output):
        values = {}
        evaluated = []
        for cond in conditions:
            source = cond.get("source_result")
            if source not in values:
                values[source] = self._condition_value(source, primary_output)
            value = values[source]
            if value is None:
                return None, evaluated, source
            matched = self._condition_matches(value, cond.get("operator"), cond.get("threshold"))
            evaluated.append({"source_result": source, "operator": cond.get("operator"), "threshold": cond.get("threshold"), "value": value, "matched": matched})
            if not matched:
                return False, evaluated, None
        return True, evaluated, None

    def execute(self, result, dry_run=False):
        if result.route != "local":
            return {"executed": False, "route": result.route, "reason": result.reason}
        contact_guard = self._contact_guard(result)
        if not contact_guard.get("ok"):
            return {"executed": False, "success": False, "error": "contact_uncertain", "contact_guard": contact_guard}
        skill = self.registry.get(result.skill)
        argv = self.registry.render_command(skill, result.arguments)
        if not argv:
            return {"executed": False, "error": "no_executor"}
        resolved, source = self._resolve_command(result, argv)
        if not resolved:
            return {"executed": False, "error": "helper_not_found", "command": argv[0], "searched": [str(p) for p in self._helper_candidates(argv[0])], "dispatcher": str(Path.home() / "hermes-phone" / "bin" / "phone")}
        followups = self._prepare_followups(result)
        visible_followups = [{k: v for k, v in f.items() if k not in {"result", "timeout"}} for f in followups]
        if dry_run:
            return {"executed": False, "dry_run": True, "command": resolved, "executor_source": source, "contact_guard": contact_guard, "followups": visible_followups}
        started = time.perf_counter()
        try:
            proc = subprocess.run(resolved, timeout=float(skill.get("timeout", 8)), capture_output=True, text=True)
            latency_ms = (time.perf_counter() - started) * 1000
            ok = proc.returncode == 0
            self.experience.record(result.skill, ok, latency_ms)
            followup_results = []
            if ok:
                primary_output = (proc.stdout or "") + "\n" + (proc.stderr or "")
                for item in followups:
                    if item.get("op") == "conditional":
                        conditions = list(item.get("conditions") or [])
                        matched, evaluated, missing_source = self._evaluate_conditions(conditions, primary_output)
                        if matched is None:
                            followup_results.append({"op": "conditional", "evaluated": False, "success": False, "reason": "source_result_unparseable", "source_result": missing_source, "conditions": evaluated})
                            ok = False
                            break
                        branch_name = "then" if matched else "else"
                        branch = item.get(branch_name)
                        if not branch:
                            followup_results.append({"op": "conditional", "evaluated": True, "conditions": evaluated, "matched": matched, "selected": branch_name, "executed": False, "success": True, "reason": "no_branch_action"})
                            continue
                        prepared = self._prepare_skill_step(branch)
                        branch_result = self._execute_prepared_step(prepared)
                        entry = {"op": "conditional", "evaluated": True, "conditions": evaluated, "matched": matched, "selected": branch_name, "branch": branch_result}
                        followup_results.append(entry)
                        if branch_result.get("success") is False:
                            ok = False
                            break
                        continue
                    r = self._execute_prepared_step(item)
                    followup_results.append(r)
                    if r.get("success") is False:
                        ok = False
                        break
            if ok and self.context is not None:
                self.context.clear_pending_confirmation()
                self.context.remember_action(result.skill, result.arguments)
                for item in followups:
                    if item.get("allowed") and item.get("result"):
                        self.context.remember_action(item["skill"], item["result"].arguments)
            return {"executed": True, "success": ok, "returncode": proc.returncode, "latency_ms": latency_ms, "executor_source": source, "command": resolved, "stdout": proc.stdout[-1000:], "stderr": proc.stderr[-1000:], "contact_guard": contact_guard, "followups": followup_results}
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            self.experience.record(result.skill, False, latency_ms)
            return {"executed": True, "success": False, "latency_ms": latency_ms, "executor_source": source, "command": resolved, "error": str(exc), "contact_guard": contact_guard, "followups": []}
