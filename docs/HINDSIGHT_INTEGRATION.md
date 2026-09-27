# Hindsight Lite integration

FastBrain supports both PRD scenarios.

## A: hot cache

Project selected structured memories into SQLite using `fastbrain cache-put` or `POST /v1/context`. Lookups are local and should be millisecond-scale.

## B: direct lookup

Configure either:

- `FASTBRAIN_HINDSIGHT_URL` + `FASTBRAIN_HINDSIGHT_PATH`, or
- `FASTBRAIN_HINDSIGHT_CMD` for a tiny adapter command that accepts JSON on stdin and returns JSON on stdout.

The direct adapter intentionally avoids assuming a private Hindsight Lite internal API. This makes FastBrain compatible with the installed plugin without modifying it first.

Accepted normalized response:

```json
{"type":"alias","subject":"govind","scope":"communication","value":"butagorira","confidence":0.99}
```

Also accepted: `{ "result": {...} }` and `{ "memories": [{...}] }`.

## Hybrid

Default mode is `hybrid`: hot cache first, direct lookup on miss, then project successful direct results into the hot cache.

## Benchmark rule

Run `fastbrain benchmark-memory`. Prefer direct when consistently below ~500 ms, hot when >=1 s, otherwise hybrid.
