from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
import uuid
from pathlib import Path

from .api import serve
from .app import build


def _summary(values):
    if not values:
        return None
    ordered = sorted(values)
    return {
        "median_ms": statistics.median(values),
        "p95_ms": ordered[max(0, int(len(values) * 0.95) - 1)],
        "mean_ms": statistics.mean(values),
    }


def _load_definition(file_arg=None, inline_json=None):
    if inline_json:
        try:
            value = json.loads(inline_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid inline JSON: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ValueError("definition JSON must be an object")
        return value
    if not file_arg:
        raise ValueError("provide a JSON file or --json '<object>'")
    path = Path(file_arg).expanduser()
    if not path.is_file():
        raise ValueError(f"definition file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as f:
            value = json.load(f)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise ValueError("definition JSON must be an object")
    return value


def main():
    parser = argparse.ArgumentParser(prog="fastbrain")
    sub = parser.add_subparsers(dest="cmd", required=True)

    route = sub.add_parser("route")
    route.add_argument("text", nargs="+")
    route.add_argument("--execute", action="store_true")
    route.add_argument("--dry-run", action="store_true")

    sub.add_parser("doctor")

    benchmark = sub.add_parser("benchmark-memory")
    benchmark.add_argument("--iterations", type=int, default=20)
    benchmark.add_argument("--subject", default="")

    probe = sub.add_parser("memory-probe")
    probe.add_argument("type")
    probe.add_argument("subject")
    probe.add_argument("--scope", default="")
    probe.add_argument("--promote", action="store_true")

    warm = sub.add_parser("memory-warm")
    warm.add_argument("type")
    warm.add_argument("subject")
    warm.add_argument("--scope", default="")

    debug = sub.add_parser("memory-debug")
    debug.add_argument("type")
    debug.add_argument("subject")
    debug.add_argument("--scope", default="")

    server = sub.add_parser("serve")
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--port", type=int, default=8766)

    cache = sub.add_parser("cache-put")
    cache.add_argument("type")
    cache.add_argument("subject")
    cache.add_argument("value")
    cache.add_argument("--scope", default="")

    cache_delete = sub.add_parser("cache-delete")
    cache_delete.add_argument("type")
    cache_delete.add_argument("subject")
    cache_delete.add_argument("--scope", default="")

    alias_set = sub.add_parser("alias-set")
    alias_set.add_argument("canonical")
    alias_set.add_argument("aliases", nargs="+")

    skill_add = sub.add_parser("skill-add")
    skill_add.add_argument("json_file")

    observe = sub.add_parser("learn-observe")
    observe.add_argument("phrase")
    observe.add_argument("json_file", nargs="?")
    observe.add_argument("--json", dest="inline_json")
    observe.add_argument("--failed", action="store_true")

    sub.add_parser("learn-candidates")

    promote = sub.add_parser("learn-promote")
    promote.add_argument("candidate_id")
    promote.add_argument("--force", action="store_true")

    correct = sub.add_parser("learn-correct")
    correct.add_argument("candidate_id")
    correct.add_argument("phrase")
    correct.add_argument("json_file", nargs="?")
    correct.add_argument("--json", dest="inline_json")
    correct.add_argument("--wrong", default="")

    sub.add_parser("skills")
    sub.add_parser("stats")

    export = sub.add_parser("export-training")
    export.add_argument("--output", default="fastbrain-training.jsonl")

    args = parser.parse_args()
    stack = build()

    if args.cmd == "doctor":
        cfg = stack["config"]
        checks = {
            "python": sys.version.split()[0],
            "python_ok": sys.version_info[:2] == (3, 13),
            "platform": sys.platform,
            "machine": platform.machine(),
            "db": str(cfg.db_path),
            "memory_mode": cfg.memory_mode,
            "hindsight_direct_configured": bool(cfg.hindsight_url or cfg.hindsight_cmd),
            "skills": len(stack["registry"].all()),
        }
        print(json.dumps(checks, indent=2)); return 0 if checks["python_ok"] else 2

    if args.cmd == "route":
        result = stack["engine"].route(" ".join(args.text)); payload = result.to_dict()
        if args.execute or args.dry_run: payload["execution"] = stack["executor"].execute(result, dry_run=args.dry_run)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        if args.execute and not payload.get("execution", {}).get("success", False): return 64
        return 0

    if args.cmd == "cache-put":
        stack["memory"].project({"type":args.type,"subject":args.subject,"value":args.value,"scope":args.scope,"confidence":1,"priority":90}); print("OK"); return 0

    if args.cmd == "cache-delete":
        deleted=stack["db"].hot_delete(args.type,args.subject,args.scope); print(json.dumps({"deleted":deleted,"type":args.type,"subject":args.subject,"scope":args.scope},indent=2)); return 0

    if args.cmd == "alias-set":
        canonical=args.canonical.strip(); aliases=[]; seen=set()
        for raw in args.aliases:
            alias=" ".join(raw.strip().split()); key=alias.lower()
            if not alias or key in seen: continue
            seen.add(key); aliases.append(alias)
            stack["memory"].project({"type":"alias","subject":alias,"value":canonical,"scope":"communication","confidence":1,"priority":95})
        verified=[]
        for alias in aliases:
            hit=stack["memory"].lookup_hot("alias",alias,"communication")
            verified.append({"alias":alias,"canonical":hit.get("value") if hit else None,"ok":bool(hit and hit.get("value")==canonical),"source":hit.get("_source") if hit else None})
        ok=bool(verified) and all(x["ok"] for x in verified); print(json.dumps({"ok":ok,"canonical":canonical,"aliases":verified},indent=2,ensure_ascii=False)); return 0 if ok else 5

    if args.cmd == "skill-add":
        try: definition=_load_definition(args.json_file)
        except ValueError as exc:
            print(json.dumps({"ok":False,"error":str(exc)},indent=2,ensure_ascii=False)); return 6
        learned=stack["learner"].learn(definition); print(json.dumps({"ok":True,"skill":learned},indent=2,ensure_ascii=False)); return 0

    if args.cmd == "learn-observe":
        try: definition=_load_definition(args.json_file,args.inline_json)
        except ValueError as exc:
            print(json.dumps({"ok":False,"error":str(exc)},indent=2,ensure_ascii=False)); return 6
        payload=stack["learner"].observe(args.phrase,definition,successful=not args.failed); print(json.dumps(payload,indent=2,ensure_ascii=False)); return 0 if payload.get("ok") else 6

    if args.cmd == "learn-candidates":
        print(json.dumps(stack["learner"].candidates(),indent=2,ensure_ascii=False)); return 0

    if args.cmd == "learn-promote":
        try: learned=stack["learner"].promote(args.candidate_id,force=args.force)
        except ValueError as exc:
            print(json.dumps({"ok":False,"error":str(exc)},indent=2,ensure_ascii=False)); return 6
        print(json.dumps({"ok":True,"skill":learned},indent=2,ensure_ascii=False)); return 0

    if args.cmd == "learn-correct":
        try:
            definition=_load_definition(args.json_file,args.inline_json)
            payload=stack["learner"].correct_candidate(args.candidate_id,args.phrase,definition,wrong=args.wrong)
        except ValueError as exc:
            print(json.dumps({"ok":False,"error":str(exc)},indent=2,ensure_ascii=False)); return 6
        print(json.dumps(payload,indent=2,ensure_ascii=False)); return 0

    if args.cmd == "memory-debug":
        print(json.dumps(stack["memory"].debug_direct(args.type,args.subject,args.scope),indent=2,ensure_ascii=False)); return 0

    if args.cmd == "memory-warm":
        payload=stack["memory"].warm(args.type,args.subject,args.scope)
        print(json.dumps(payload,indent=2,ensure_ascii=False)); return 0 if payload.get("ok") else 3

    if args.cmd == "memory-probe":
        memory=stack["memory"]; direct=memory.lookup_direct(args.type,args.subject,args.scope)
        payload={"type":args.type,"subject":args.subject,"scope":args.scope,"direct":direct,"promoted":False}
        if args.promote and direct:
            promoted,reason=memory.promote_direct_result(args.type,args.subject,args.scope,direct); payload["promoted"]=promoted; payload["promotion_reason"]=reason
            if promoted: payload["hot_after"]=memory.lookup_hot(args.type,args.subject,args.scope)
        print(json.dumps(payload,indent=2,ensure_ascii=False)); return 0 if direct else 3

    if args.cmd == "benchmark-memory":
        memory=stack["memory"]; raw=args.subject.strip() if args.subject else uuid.uuid4().hex[:12]; subject="__fastbrain_benchmark__"+raw
        memory.project({"type":"alias","subject":subject,"value":"benchmark-value","scope":"benchmark","confidence":1})
        hot_times=[]; direct_times=[]; direct_configured=bool(stack["config"].hindsight_url or stack["config"].hindsight_cmd)
        for _ in range(args.iterations):
            started=time.perf_counter(); memory.lookup_hot("alias",subject,"benchmark"); hot_times.append((time.perf_counter()-started)*1000)
            if direct_configured:
                started=time.perf_counter(); memory.lookup_direct("alias",subject,"benchmark"); direct_times.append((time.perf_counter()-started)*1000)
        payload={"subject":subject,"hot":_summary(hot_times),"direct":_summary(direct_times),"direct_configured":direct_configured}
        if not direct_configured: payload["recommendation"]="configure direct Hindsight before comparing"
        elif statistics.median(direct_times)>=1000: payload["recommendation"]="hybrid: hot cache first, Hindsight on miss"
        elif statistics.median(direct_times)<500: payload["recommendation"]="direct is fast enough; hybrid still reduces repeated work"
        else: payload["recommendation"]="hybrid recommended"
        print(json.dumps(payload,indent=2)); return 0

    if args.cmd == "serve": serve(args.host,args.port); return 0
    if args.cmd == "skills": print(json.dumps(stack["registry"].all(),indent=2)); return 0
    if args.cmd == "stats": print(json.dumps(stack["experience"].stats(),indent=2)); return 0
    if args.cmd == "export-training":
        from .training import export_jsonl
        count=export_jsonl(stack,args.output); print(json.dumps({"output":args.output,"examples":count},indent=2)); return 0
    return 2

if __name__ == "__main__": raise SystemExit(main())
