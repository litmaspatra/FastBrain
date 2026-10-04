# Review of the Codex-generated code: what was wrong and what changed

Tested with CPython 3.13.13 and 3.14.4 on Linux x86-64 (54 tests, all passing on both).
NOT tested on a real Android/Termux device, with real Hermes helpers, Hindsight, or the MiniLM model.

## 1. Mixed-up files (repo would not run at all)
| File | Actually contained | Fixed |
|---|---|---|
| `fastbrain/config.py` | the FastBrain engine | now `Config` |
| `fastbrain/semantic.py` | `Config` | now `SemanticEngine` |
| `fastbrain/context.py` | `SemanticEngine` | now `ContextEngine` |
| `fastbrain/memory.py` | `ContextEngine` | now `MemoryBridge` (**rewritten**, see below) |
| `fastbrain/engine.py` | stale older copy of the engine | now the newer engine + the phrases only the old copy had |
| `README.md` | the update script | now the README |
| `docs/UPDATE.md` | the README | now a short update guide |
| `scripts/update-fastbrain.sh` | a 140-line copy of the installer | now the real updater |
| `fastbrain/patch_marker.py` | an empty "blocked tool path" placeholder | deleted |

**`MemoryBridge` did not exist anywhere in the zip.** It was rebuilt from `tests/test_memory.py` and every
call site (`app.py`, `cli.py`, `api.py`, `context.py`). If your phone still has the original at
`~/.fastbrain/app/fastbrain/memory.py`, diff it against the new file before replacing it.

## 2. Bugs fixed
- **Battery "charging" detection was inverted**: `DISCHARGING` / `NOT_CHARGING` contain "charging", so every
  "if battery < 20 and not charging ..." condition saw "charging". Negatives are now tested first.
- **Python pinned to exactly 3.13**: installer asserted `== (3, 13)`, `doctor` failed on 3.14, scripts hard-coded
  `python3.13` / `python3.14`. Now: any 3.13+, auto-detected (`python3.13` -> `python3.14` -> `python3`), overridable.
  MiniLM picks the interpreter that can really import numpy + onnxruntime.
- **Double execution**: if the router replied slowly, `fastbrain-fast.sh` fell back to the CLI and ran the action again
  (a message could be sent twice). It now only falls back when the request never reached the router.
- **Hermes wrapper routed twice** (dry route, then route again). Now one call; stdout stays clean when declined.
- **Pre-router regexes hijacked sentences**: "show me the weather" played music, "tell me a joke" tried to message "me".
  Removed the over-broad patterns. "send me the report" no longer targets a contact named "me". A whole sentence after
  "open" is no longer treated as an app name. Volume is clamped to 0-100.
- **MiniLM timeout was always 50 ms** (the "adaptive" flag ignored your 0.20 s setting). Unseen text now gets the slow budget.
- **Launcher froze the installer's `PYTHONPATH`** into `~/.fastbrain/fastbrain`. Now expanded at run time.
- **Updater could delete the working app** if the copy failed midway. Now build-then-swap.
- **API crashed on bad JSON**, shared one SQLite connection across threads, and accepted cross-site POSTs. Now single-threaded,
  returns 400, requires `application/json`, caps body size.
- **Unauthenticated skill registration = code execution**: a learned skill could be `bash`, could override built-in
  `call_contact`, and PATH was searched before the helper directories. Commands must now be bare helper names,
  shells/interpreters are refused, built-ins can't be replaced, helper dirs win over PATH.
- **Risk handling**: missing risk was "low" in the learner but "medium" in the registry, and `"risk":"critical"` skipped the
  high-risk check. Missing = medium, unknown = high.
- **Router service** could be frozen by one stalled client (10 s timeout added); MiniLM service likewise (2 s).
- Executor parsed JSON from stdout+stderr combined (any stderr noise broke the battery/wifi conditions).
- Trace table stored double-encoded JSON and `tracing.py` was never used; now wired in.
- `route_log` / `route_trace` grew forever; trimmed to 5000 rows.
- `benchmark-memory` left a fake alias in your real hot cache; `skill-add` crashed with a traceback on invalid input.
- Semantic scoring re-tokenized every example on every route; features are now cached.
- Home-directory assumptions (`~/.fastbrain`) now honour `FASTBRAIN_HOME`.

## 3. Left alone on purpose (your call)
- `models/semantic.onnx.b64` is never installed, and that is lucky: it has no `normal_hermes` class, so enabling it
  would force every sentence into one of 16 actions.
- Routing only reads the hot cache. Hindsight is consulted by `memory-warm` / `memory-probe` / `lookup()`, not mid-route
  (a 5 s adapter call on every unknown name would wreck latency).
- If a later step of a multi-step plan fails after an earlier one ran, the whole request returns failure and Hermes
  may redo the earlier step. Needs a design decision.
- Dry-runs are logged like real requests, so they count toward "most requested songs".
- "go to X" / "switch to X" still map to `open_app` (the helper just fails and Hermes takes over).
- MiniLM accepts a similarity of only 0.45 for local execution; consider raising it once you have logs.
