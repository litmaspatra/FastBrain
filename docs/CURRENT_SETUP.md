# Current Hermes/Termux Setup

This document describes the FastBrain installation currently running on Kartik's Android/Termux setup. It is an operational description, not a generic installation guide.

## Components and locations

| Component | Current location | Role |
|---|---|---|
| FastBrain source checkout | `~/FastBrain` | GitHub repository and router scripts |
| Installed FastBrain application | `~/.fastbrain/app` | Python 3.13 FastBrain package used by the CLI and router service |
| FastBrain command | `~/.fastbrain/fastbrain` | Loads `~/.fastbrain/fastbrain.env`, then runs `python3.13 -m fastbrain.cli` |
| Hot database | `~/.fastbrain/fastbrain.db` | SQLite hot cache, skills, context, and experience data |
| Hindsight adapter | `~/.fastbrain/bin/hindsight-direct.py` | Direct lookup adapter used by the hybrid memory mode |
| Persistent semantic service | `~/.fastbrain/bin/minilm-semantic-service.py` | MiniLM ONNX service over a Unix socket |
| Persistent route service | `~/FastBrain/scripts/fastbrain-router-service.py` | Long-lived FastBrain engine over a Unix socket |
| Hermes pre-router | `~/.hermes/hermes-agent/agent/fastbrain_prerouter.py` | Runs FastBrain before an LLM-backed Hermes turn |

The installed package is intentionally separate from the checkout. `scripts/install-termux.sh` copies the repository package into `~/.fastbrain/app`; it does not import the checkout at runtime for normal CLI requests.

## Request path

```text
CLI / TUI / dashboard / gateway / relay voice turn
                    |
                    v
Hermes AIAgent turn facade
                    |
                    v
~/.hermes/hermes-agent/agent/fastbrain_prerouter.py
                    |
                    v
~/FastBrain/scripts/fastbrain-fast.sh route ... --execute
                    |
          +---------+---------+
          |                   |
          v                   v
persistent Unix socket       ~/.fastbrain/fastbrain
(router service)              (CLI fallback)
          |
          v
FastBrain local route + existing Hermes/Android helper

If the route is not local, execution fails, or the call times out:
FastBrain returns control to normal Hermes/OmniRoute processing.
```

The Hermes boundary is fail-open. A successful FastBrain route is consumed before Hermes creates an LLM-backed turn. A non-local or failed route does not block normal Hermes processing.

## Persistent router

The current router socket is:

```text
~/.fastbrain/router/router.sock
```

The service is started with:

```bash
~/FastBrain/scripts/start-fastbrain-router.sh
```

The service exposes a small HTTP-like Unix-socket interface:

- `GET /health` reports readiness.
- `POST /route` accepts `text`, `dry_run`, and `execute` form fields.

`fastbrain-fast.sh` uses the persistent socket for low-latency routing and falls back to the normal FastBrain CLI if the socket/client is unavailable. Non-executing socket requests use a short client timeout; executing requests allow up to 8 seconds because an Android helper may run for several seconds.

Verified command for the current service:

```bash
curl --unix-socket ~/.fastbrain/router/router.sock http://localhost/health
```

Expected response:

```json
{"ok": true, "status": "ready"}
```

## Semantic routing

The active environment uses the persistent MiniLM backend:

```text
FASTBRAIN_SEMANTIC_BACKEND=minilm
FASTBRAIN_MINILM_SOCKET=~/.fastbrain/minilm/minilm.sock
FASTBRAIN_MINILM_TIMEOUT=0.20
FASTBRAIN_MINILM_MIN_SIMILARITY=0.45
FASTBRAIN_MINILM_MIN_MARGIN=0.10
```

The MiniLM service currently runs with Python 3.14 and its own ONNX model/vocabulary files under `~/.fastbrain/minilm`. The core FastBrain CLI and installed application use Python 3.13. The old per-request ONNX helper is disabled while MiniLM is active.

## Memory and Hindsight

The CLI is configured for hybrid memory:

```text
FASTBRAIN_MEMORY_MODE=hybrid
FASTBRAIN_HINDSIGHT_TIMEOUT=5.0
FASTBRAIN_HINDSIGHT_LIMIT=3
```

The direct Hindsight command is the Hermes Agent virtual-environment Python invoking `~/.fastbrain/bin/hindsight-direct.py`. FastBrain uses the hot SQLite cache first and can consult the direct adapter on a miss, then project successful results back into the hot layer.

Durable facts remain in Hindsight. FastBrain's SQLite data is the performance layer, not the durable source of truth.

## Hermes integration behavior

`fastbrain_prerouter.py` deliberately normalizes only the known WhatsApp preparation speech variants. It does not perform broad fuzzy matching. It invokes:

```text
~/FastBrain/scripts/fastbrain-fast.sh route <text> --execute
```

A route is accepted by Hermes only when all of these are true:

1. the command exits successfully;
2. the response is valid JSON;
3. `route` is `local`;
4. the execution object reports `success: true`.

The Hermes integration timeout is 8 seconds. Timeout, launch errors, invalid output, non-local routes, and failed executions all fall back to normal Hermes processing. Successful local routes are logged with the selected FastBrain skill.

FastBrain executes existing Hermes/Android helpers rather than replacing them. Examples include device controls, app opening, media playback, contact actions, and messaging, subject to FastBrain's risk and contact-safety checks.

## Verification commands

```bash
~/.fastbrain/fastbrain doctor
~/.fastbrain/fastbrain stats
curl --unix-socket ~/.fastbrain/router/router.sock http://localhost/health
~/.fastbrain/fastbrain route 'turn the flashlight on' --dry-run
~/FastBrain/scripts/fastbrain-fast.sh route 'battery' --dry-run
bash ~/FastBrain/scripts/test-roadmap-final.sh
```

The dry-run commands must not perform device actions. The final roadmap script is the repository's regression set for bounded workflow behavior.

## Operational boundaries

- FastBrain is a pre-router and sidecar; Hermes remains the full reasoning fallback.
- Do not modify Hermes helpers merely to add a FastBrain route.
- Keep aliases and durable preferences in Hindsight, then project performance-critical values into FastBrain hot memory.
- Keep uncertain and high-risk workflows out of automatic local execution.
- Do not commit `~/.fastbrain/fastbrain.db`, runtime sockets, PID files, model binaries, or environment files containing local paths/configuration.
