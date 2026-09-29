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
        return [
            home / ".fastbrain" / "helpers" / name,
            home / "hermes-phone" / "bin" / name,
            home / ".hermes" / "bin" / name,
            home / "bin" / name,
        ]

    @staticmethod
    def _is_executable(path: Path) -> bool:
        return path.is_file() and os.access(path, os.X_OK)

    @staticmethod
    def _norm_contact(value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", str(value).lower()))

    @classmethod
    def _contact_similarity(cls, a: str, b: str) -> float:
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

        ranked = sorted(
            ((self._contact_similarity(contact, name), name) for name in names),
            key=lambda x: x[0],
            reverse=True,
        )
        suggestions = []
        for score, name in ranked:
            if score < 0.45:
                continue
            suggestions.append({"name": name, "score": round(score, 3)})
            if len(suggestions) == 3:
                break

        if suggestions and self.context is not None:
            self.context.set_pending_confirmation({
                "skill": result.skill,
                "arguments": dict(result.arguments),
                "heard": contact,
                "suggestion": suggestions[0]["name"],
            })

        return {
            "ok": False,
            "status": "contact_uncertain",
            "heard": contact,
            "suggestions": suggestions,
            "needs_confirmation": bool(suggestions),
        }

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
                source = "fastbrain_helper" if "/.fastbrain/helpers/" in str(candidate) else "hermes_helper"
                return [str(candidate), *argv[1:]], source

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
            query = result.arguments.get("query") or (rest[-1] if rest else "music")
            return [str(dispatcher), "play", "music", str(query)], "phone_dispatcher"
        if skill == "play_video":
            query = result.arguments.get("query") or (rest[-1] if rest else "video")
            return [str(dispatcher), "play", "video", str(query)], "phone_dispatcher"
        if skill == "create_reminder":
            return [str(dispatcher), "remind", *rest], "phone_dispatcher"
        if skill == "create_obsidian_note":
            text = result.arguments.get("text") or (rest[0] if rest else "")
            return [str(dispatcher), "note", "create", "FastBrain", str(text)], "phone_dispatcher"
        return None, None

    def _prepare_followups(self, result):
        """Resolve explicit low-risk secondary skills and expose deferred planner steps."""
        out=[]
        for step in result.plan or []:
            if step.get('op')=='hermes_clause':
                out.append({
                    'op':'hermes_clause',
                    'text':step.get('text',''),
                    'context':dict(step.get('context') or {}),
                    'allowed':False,
                    'route':'hermes',
                    'deferred':True,
                    'reason':'unresolved_compound_clause',
                })
                continue
            if step.get('op')=='conditional':
                then_step=dict(step.get('then') or {})
                visible_then={k:v for k,v in then_step.items() if k not in {'result','timeout'}}
                out.append({
                    'op':'conditional',
                    'source_result':step.get('source_result'),
                    'operator':step.get('operator'),
                    'threshold':step.get('threshold'),
                    'then':visible_then,
                    'allowed':False,
                    'deferred':True,
                    'reason':'result_required_before_condition',
                })
                continue
            sid=step.get('skill')
            if not sid:
                continue
            skill=self.registry.get(sid)
            if not skill or skill.get('risk','low')!='low':
                out.append({'skill':sid,'allowed':False,'reason':'secondary_skill_not_low_risk'})
                continue
            args=dict(step.get('arguments') or {})
            required=[k for k,v in (skill.get('arguments') or {}).items() if v.get('required')]
            missing=[k for k in required if not args.get(k)]
            if missing:
                out.append({'skill':sid,'allowed':False,'reason':'missing_arguments:'+','.join(missing)})
                continue
            rr=RouteResult('local',skill.get('category','unknown'),sid,args,.995,'compound_followup',step.get('source','microreasoner'),[])
            argv=self.registry.render_command(skill,args)
            resolved,source=self._resolve_command(rr,argv or []) if argv else (None,None)
            out.append({'skill':sid,'allowed':bool(resolved),'arguments':args,'command':resolved,'executor_source':source,'result':rr,'timeout':float(skill.get('timeout',8))})
        return out

    def execute(self, result, dry_run=False):
        if result.route != "local":
            return {"executed": False, "route": result.route, "reason": result.reason}

        contact_guard = self._contact_guard(result)
        if not contact_guard.get("ok"):
            return {
                "executed": False,
                "success": False,
                "error": "contact_uncertain",
                "contact_guard": contact_guard,
            }

        skill = self.registry.get(result.skill)
        argv = self.registry.render_command(skill, result.arguments)
        if not argv:
            return {"executed": False, "error": "no_executor"}

        resolved, source = self._resolve_command(result, argv)
        if not resolved:
            return {
                "executed": False,
                "error": "helper_not_found",
                "command": argv[0],
                "searched": [str(p) for p in self._helper_candidates(argv[0])],
                "dispatcher": str(Path.home() / "hermes-phone" / "bin" / "phone"),
            }

        followups=self._prepare_followups(result)
        visible_followups=[{k:v for k,v in f.items() if k not in {'result','timeout'}} for f in followups]

        if dry_run:
            return {
                "executed": False,
                "dry_run": True,
                "command": resolved,
                "executor_source": source,
                "contact_guard": contact_guard,
                "followups": visible_followups,
            }

        started = time.perf_counter()
        try:
            proc = subprocess.run(resolved, timeout=float(skill.get("timeout", 8)), capture_output=True, text=True)
            latency_ms = (time.perf_counter() - started) * 1000
            ok = proc.returncode == 0
            self.experience.record(result.skill, ok, latency_ms)
            followup_results=[]
            if ok:
                for item in followups:
                    if not item.get('allowed') or not item.get('command'):
                        followup_results.append({k:v for k,v in item.items() if k not in {'result','timeout'}})
                        continue
                    fstart=time.perf_counter()
                    try:
                        fp=subprocess.run(item['command'],timeout=item['timeout'],capture_output=True,text=True)
                        flatency=(time.perf_counter()-fstart)*1000
                        fok=fp.returncode==0
                        self.experience.record(item['skill'],fok,flatency)
                        followup_results.append({'skill':item['skill'],'executed':True,'success':fok,'returncode':fp.returncode,'latency_ms':flatency,'command':item['command'],'executor_source':item['executor_source'],'stdout':fp.stdout[-500:],'stderr':fp.stderr[-500:]})
                        if not fok:
                            ok=False
                            break
                    except Exception as fexc:
                        flatency=(time.perf_counter()-fstart)*1000
                        self.experience.record(item['skill'],False,flatency)
                        followup_results.append({'skill':item['skill'],'executed':True,'success':False,'latency_ms':flatency,'command':item.get('command'),'error':str(fexc)})
                        ok=False
                        break
            if ok and self.context is not None:
                self.context.clear_pending_confirmation()
                self.context.remember_action(result.skill, result.arguments)
                for item in followups:
                    if item.get('allowed') and item.get('result'):
                        self.context.remember_action(item['skill'], item['result'].arguments)
            return {
                "executed": True,
                "success": ok,
                "returncode": proc.returncode,
                "latency_ms": latency_ms,
                "executor_source": source,
                "command": resolved,
                "stdout": proc.stdout[-1000:],
                "stderr": proc.stderr[-1000:],
                "contact_guard": contact_guard,
                "followups": followup_results,
            }
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            self.experience.record(result.skill, False, latency_ms)
            return {
                "executed": True,
                "success": False,
                "latency_ms": latency_ms,
                "executor_source": source,
                "command": resolved,
                "error": str(exc),
                "contact_guard": contact_guard,
                "followups": [],
            }
