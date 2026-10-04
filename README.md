# FastBrain

FastBrain is a lightweight, local-first **reflex + context + skill-routing layer for Hermes** on Android/Termux. It borrows the useful typed-decision idea from Laya while adding personal context, Hindsight memory, and a safe executor.

## What is implemented

- deterministic reflex router
- dependency-free local semantic decision engine (`choice`, probabilistic matching, confidence)
- MiniLM ONNX semantic layer with persistent Termux service
- hierarchical skill registry with dynamic learned skills
- working memory and alias/preference resolution
- MicroReasoner for context and bounded safe compositions
- Hindsight Lite bridge with **hot**, **direct**, and **hybrid** modes
- benchmark for hot-cache vs direct Hindsight latency
- skill learner (low/medium risk; high-risk rejected)
- experience/latency statistics
- local HTTP API
- safe executor using existing Hermes/Android helpers
- non-invasive Hermes pre-router wrapper
- Termux installer/validator
- CI tests on Python 3.13 and 3.14

## Safe update flow

FastBrain now supports in-place upgrades without resetting your local state.

```bash
git pull --ff-only
bash scripts/update-fastbrain.sh
```

The updater preserves the live environment in `~/.fastbrain`, including:

- `fastbrain.env`
- `fastbrain.db`
- `router/`
- `models/`
- `minilm/`
- cached Hindsight data and local aliases

This means you can update the repo and re-install without losing your working setup.

## Workflow engine

FastBrain now supports bounded local workflows without becoming an unrestricted agent:

- ordered local plans with at most a small number of explicit steps
- same-command app/media/contact context reuse
- communication pronoun reuse while preserving contact safety
- deferred `hermes_clause` nodes for unclear steps instead of losing the whole plan
- deferred clauses carry useful local context such as the current app/contact/media query
- battery percentage conditions (`below`, `above`, etc.)
- charging / not-charging conditions
- Wi-Fi connected / disconnected conditions
- `else` / `otherwise` branches
- compound low-risk conditional branches
- combined battery conditions such as `battery < 20 AND not charging`
- same battery read reused for percentage + charging evaluation
- all-or-defer safety for mixed conditional sequences: if any branch step is unresolved or not low-risk, the branch does not partially execute

Medium/high-risk secondary skills remain blocked by the executor. Unknown clauses are never converted into arbitrary shell commands.

## Safety / isolation

The installer creates `~/.fastbrain/app` using the first **Python 3.13+** it finds (`python3.13`, then `python3.14`, then `python3`; override with `FASTBRAIN_PYTHON`) and does not run pip. The core is standard-library only, so 3.13 and 3.14 both work. It does not alter system Python, `~/.hermes`, `~/.omniroute`, `~/hermes-phone`, Hindsight Lite, or the Android adapter during standalone installation.

## Termux install

```bash
git clone https://github.com/litmaspatra/FastBrain.git
cd FastBrain
bash scripts/install-termux.sh
~/.fastbrain/fastbrain doctor
bash scripts/validate-termux.sh
```

## Try routing safely

Use dry-run while validating device workflows:

```bash
~/.fastbrain/fastbrain cache-put alias govind butagorira --scope communication
~/.fastbrain/fastbrain route "call Govind" --dry-run
~/.fastbrain/fastbrain route "play something" --dry-run
~/.fastbrain/fastbrain route "check battery and if it's below 20 and not charging open battery settings otherwise do nothing" --dry-run
```

Complex/uncertain input returns `route: hermes` or an explicit deferred `hermes_clause` rather than forcing a local action.

Run the final roadmap regression set without executing device actions:

```bash
bash scripts/test-roadmap-final.sh
```

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

## Updating safely

Use the packaged updater instead of reinstalling everything by hand:

```bash
bash scripts/update-fastbrain.sh
```

This is intentionally idempotent and safe to re-run.

More detail: `docs/UPDATE.md`.
