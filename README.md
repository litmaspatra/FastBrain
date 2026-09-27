# FastBrain

FastBrain is a lightweight, local-first **reflex + context + skill-routing layer for Hermes** on Android/Termux. It borrows the useful typed-decision idea from Laya while adding personal context, Hindsight integration, skill execution, experience tracking, and learnable workflows.

## What is implemented

- deterministic reflex router
- dependency-free local semantic decision engine (`choice`, probabilistic matching, confidence)
- hierarchical skill registry with dynamic learned skills
- working memory and alias/preference resolution
- MicroReasoner for context and small safe compositions
- Hindsight Lite bridge with **hot**, **direct**, and **hybrid** modes
- benchmark for hot-cache vs direct Hindsight latency
- skill learner (low/medium risk; high-risk rejected)
- experience/latency statistics
- local HTTP API
- safe executor using existing Hermes/Android helpers
- non-invasive Hermes pre-router wrapper
- Termux installer/validator
- Python 3.13 CI tests

## Safety / isolation

The installer creates `~/.fastbrain/app` using **Python 3.13** and does not run pip. It does not alter system Python, `~/.hermes`, `~/.omniroute`, `~/hermes-phone`, Hindsight Lite, or the Android adapter.

## Termux install

```bash
git clone https://github.com/litmaspatra/FastBrain.git
cd FastBrain
bash scripts/install-termux.sh
~/.fastbrain/fastbrain doctor
bash scripts/validate-termux.sh
```

## Try routing safely

```bash
~/.fastbrain/fastbrain cache-put alias govind butagorira --scope communication
~/.fastbrain/fastbrain route --dry-run "call Govind"
~/.fastbrain/fastbrain route "play something"
~/.fastbrain/fastbrain route "explain quantum computing"
```

Complex/uncertain input returns `route: hermes` rather than forcing a local action.

## Hindsight scenarios

FastBrain deliberately supports both PRD scenarios:

1. **Hot cache** — selected Hindsight memories projected to SQLite.
2. **Direct** — structured lookup through a configurable HTTP or command adapter.
3. **Hybrid** — hot first, direct on miss, project successful result back into hot cache.

```bash
~/.fastbrain/fastbrain benchmark-memory --iterations 30
```

See `docs/HINDSIGHT_INTEGRATION.md` before wiring the direct adapter to your installed Hindsight Lite.

## Local API

```bash
~/.fastbrain/fastbrain serve --host 127.0.0.1 --port 8766
```

Endpoints include `/health`, `/v1/route`, `/v1/skills`, `/v1/context`, `/v1/learn`, `/v1/correction`, and `/v1/stats`.

## Hermes integration

Do not integrate until standalone validation passes. `scripts/hermes-fastbrain-wrapper.sh` exits `64` on any non-local request so normal Hermes remains the fallback.

See `docs/PRD.md` and `docs/HERMES_INTEGRATION.md`.
