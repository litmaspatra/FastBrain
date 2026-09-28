from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
import uuid

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

    skill_add = sub.add_parser("skill-add")
    skill_add.add_argument("json_file")

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
        print(json.dumps(checks, indent=2))
        return 0 if checks["python_ok"] else 2

    if args.cmd == "route":
        result = stack["engine"].route(" ".join(args.text))
        payload = result.to_dict()
        if args.execute or args.dry_run:
            payload["execution"] = stack["executor"].execute(result, dry_run=args.dry_run)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        if args.execute and not payload.get("execution", {}).get("success", False):
            return 64
        return 0

    if args.cmd == "cache-put":
        stack["memory"].project(
            {
                "type": args.type,
                "subject": args.subject,
                "value": args.value,
                "scope": args.scope,
                "confidence": 1,
                "priority": 90,
            }
        )
        print("OK")
        return 0

    if args.cmd == "cache-delete":
        deleted = stack["db"].hot_delete(args.type, args.subject, args.scope)
        print(json.dumps({"deleted": deleted, "type": args.type, "subject": args.subject, "scope": args.scope}, indent=2))
        return 0

    if args.cmd == "skill-add":
        with open(args.json_file, "r", encoding="utf-8") as f:
            definition = json.load(f)
        learned = stack["learner"].learn(definition)
        print(json.dumps({"ok": True, "skill": learned}, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "memory-debug":
        payload = stack["memory"].debug_direct(args.type, args.subject, args.scope)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "memory-probe":
        memory = stack["memory"]
        direct = memory.lookup_direct(args.type, args.subject, args.scope)
        payload = {"type": args.type,"subject": args.subject,"scope": args.scope,"direct": direct,"promoted": False}
        if args.promote and direct:
            promoted, reason = memory.promote_direct_result(args.type, args.subject, args.scope, direct)
            payload["promoted"] = promoted
            payload["promotion_reason"] = reason
            if promoted:
                payload["hot_after"] = memory.lookup_hot(args.type, args.subject, args.scope)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0 if direct else 3

    if args.cmd == "benchmark-memory":
        memory = stack["memory"]
        raw = args.subject.strip() if args.subject else uuid.uuid4().hex[:12]
        subject = "__fastbrain_benchmark__" + raw
        memory.project({"type":"alias","subject":subject,"value":"benchmark-value","scope":"benchmark","confidence":1})
        hot_times=[];direct_times=[]
        direct_configured=bool(stack["config"].hindsight_url or stack["config"].hindsight_cmd)
        for _ in range(args.iterations):
            started=time.perf_counter();memory.lookup_hot("alias",subject,"benchmark");hot_times.append((time.perf_counter()-started)*1000)
            if direct_configured:
                started=time.perf_counter();memory.lookup_direct("alias",subject,"benchmark");direct_times.append((time.perf_counter()-started)*1000)
        payload={"subject":subject,"hot":_summary(hot_times),"direct":_summary(direct_times),"direct_configured":direct_configured}
        if not direct_configured:payload["recommendation"]="configure direct Hindsight before comparing"
        elif statistics.median(direct_times)>=1000:payload["recommendation"]="hybrid: hot cache first, Hindsight on miss"
        elif statistics.median(direct_times)<500:payload["recommendation"]="direct is fast enough; hybrid still reduces repeated work"
        else:payload["recommendation"]="hybrid recommended"
        print(json.dumps(payload,indent=2));return 0

    if args.cmd == "serve":
        serve(args.host, args.port);return 0
    if args.cmd == "skills":
        print(json.dumps(stack["registry"].all(), indent=2));return 0
    if args.cmd == "stats":
        print(json.dumps(stack["experience"].stats(), indent=2));return 0
    if args.cmd == "export-training":
        from .training import export_jsonl
        count=export_jsonl(stack,args.output);print(json.dumps({"output":args.output,"examples":count},indent=2));return 0
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
