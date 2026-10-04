# FastBrain PRD v0.2 — implementation contract

FastBrain is Hermes' lightweight local cognitive reflex layer for Android/Termux. It follows these phases:

1. Foundation: API, SQLite, skill registry, deterministic router, logging, benchmark framework.
2. Context Engine: aliases, recent entities, working memory, preferences, selective context.
3. Hindsight Bridge: hot-cache and direct-lookup modes, plus measured hybrid mode.
4. Semantic Engine: compact local typed decision engine, replaceable by ONNX later without API change.
5. MicroReasoner: context-aware decisions and safe 2–4 step plans.
6. Hermes Integration: non-invasive pre-router with normal-Hermes fallback.
7. Skill Learning: verified low/medium-risk workflow definitions can be registered without retraining.
8. Experience Engine: success, failure, latency, and correction statistics.
9. Training Pipeline: usage/correction data is retained for later external training/export; phone runtime remains independent of training dependencies.
10. Expansion: skill/API architecture supports Google Workspace, social media, notifications, and further Android actions.

## Requirements

- Android/Termux/aarch64, Python 3.13+ (tested on 3.13 and 3.14).
- No Torch requirement; stdlib-only core.
- Target simple-action end-to-end latency <10 s, usually <5 s.
- Preferred total install <300 MB; hard ceiling 500 MB.
- No modification of system Python, Hermes, OmniRoute, Hindsight Lite, or Android adapter during standalone installation.
- Confidence gating and safe fallback are mandatory.
- Hindsight direct vs hot cache must be benchmarked on the actual phone before final memory-mode choice.

## Typed decisions

FastBrain exposes internal choice/boolean/score primitives through its semantic engine and structured route output. Unknown/complex work escalates to Hermes.

## Memory tiers

HOT: SQLite projection. WARM: direct Hindsight structured lookup. COLD: full Hermes + Hindsight semantic/reflection path.

## Skill learning

Immediate skill registration uses definitions/examples; no phone-side neural retraining is required. High-risk skills are rejected by the automatic learner.
