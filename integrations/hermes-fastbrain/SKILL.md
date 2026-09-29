---
name: fastbrain
description: Use FastBrain as Hermes' low-latency phone router for aliases, preferences, corrections, reusable helpers, and learned skills.
---

# FastBrain integration for Hermes

FastBrain is the phone's low-latency reflex/router layer. Use it for reusable device actions, aliases, preferences, corrections, and learned helpers while keeping Hermes as the full reasoning fallback.

## Mandatory bridge behavior

When the user explicitly teaches a durable alias, preference, default, routine, channel preference, constraint, or reusable FastBrain behavior:

1. Store or update the durable fact in Hindsight using `hmem_remember` or `hmem_update` when appropriate.
2. Project performance-critical facts into FastBrain immediately.
3. Verify the FastBrain write succeeded before claiming the bridge is updated.

For contact aliases, use type `alias`, scope `communication`, and lowercase matching is handled by FastBrain internally.

### One alias

```bash
~/.fastbrain/fastbrain cache-put alias govind butagorira --scope communication
```

### Several aliases for one canonical contact

Prefer the atomic helper command:

```bash
~/.fastbrain/fastbrain alias-set butagorira govind Gobimaru Devesh "DD Rao"
```

The command writes each alias to the hot cache and returns per-alias verification. It does not write Hindsight; Hermes must save/update the durable relationship with Hindsight first.

When the user says that several names refer to the same person, choose a canonical contact value that the existing Android contact resolver can actually resolve. Do not invent a canonical contact. If a known existing FastBrain alias already maps a trusted name to the real device contact, reuse that target.

After projecting aliases, verify at least one representative route with `--dry-run` when practical:

```bash
~/.fastbrain/fastbrain route "call Gobimaru" --dry-run
```

The expected result is a local `call_contact` route whose contact is the canonical contact and whose context source is `hot`.

## Core rules

- Prefer FastBrain for simple, repeatable phone actions that can be represented as a typed skill.
- Do not bypass FastBrain safety/risk rules for high-risk actions.
- Do not modify existing Hermes helpers when a new FastBrain-only helper will work. Put new helpers in `~/.fastbrain/helpers/` and make them executable.
- Keep Hindsight as the durable source of truth and FastBrain hot memory as the speed layer.
- Avoid duplicate Hindsight memories. Update or merge an existing fact when appropriate.
- A missing FastBrain alias is not an error; literal contact names are passed to the Android contact resolver.
- Microphone misrecognitions and fuzzy contact suggestions are short-lived working context only. Never convert them into durable aliases unless the user explicitly teaches that mapping.

## FastBrain command

Use:

```bash
~/.fastbrain/fastbrain
```

### Add or update a hot memory

```bash
~/.fastbrain/fastbrain cache-put TYPE SUBJECT VALUE --scope SCOPE
```

Examples:

```bash
~/.fastbrain/fastbrain cache-put alias govind butagorira --scope communication
~/.fastbrain/fastbrain cache-put preference evening "upbeat hindi" --scope music
```

### Remove a wrong hot value

```bash
~/.fastbrain/fastbrain cache-delete TYPE SUBJECT --scope SCOPE
```

Also correct or update the corresponding Hindsight fact when one exists.

### Register a learned skill

Write a JSON definition to a temporary file and register it:

```bash
~/.fastbrain/fastbrain skill-add /path/to/skill.json
```

Required fields: `id`, `category`, `examples`, `executor`.

High-risk skills require manual integration and must not be auto-registered.

### Create a FastBrain helper

For a reusable workflow that Hermes successfully solved and that is safe to automate:

1. Inspect the already-working phone helper or dispatcher commands for every action in the workflow. Never guess an Android command when an existing helper can be inspected.
2. Create a new helper only under `~/.fastbrain/helpers/NAME`. Do not edit `~/hermes-phone`, `~/.hermes/bin`, OmniRoute, Hindsight, or system packages.
3. Keep the helper minimal: compose existing verified helpers/dispatcher actions rather than reimplementing them.
4. Make it executable with `chmod 700 ~/.fastbrain/helpers/NAME`.
5. Test the helper directly. For workflows that cause side effects, use harmless checks first and only perform the real action when the user asked for it.
6. Register a learned skill whose `executor.command` is `NAME` and whose examples contain the user's natural trigger phrase.
7. Verify registration with `~/.fastbrain/fastbrain skills` and verify routing with `~/.fastbrain/fastbrain route "TRIGGER" --dry-run`.
8. Only report success when the dry-run resolves `route: local`, the expected learned skill id, and `executor_source: fastbrain_helper`.

FastBrain searches `~/.fastbrain/helpers/` before Hermes helper directories for learned helper commands.

## Automatic candidate learning

After Hermes successfully completes a workflow, automatically evaluate whether it is a reusable FastBrain candidate. Do not wait for the user to say "create a skill".

Observe it only when all are true:

- the workflow actually succeeded;
- the steps are deterministic and reproducible;
- a small FastBrain helper or existing helper composition can represent it;
- risk is low or medium;
- the workflow is likely to recur, has been repeated, or the user has corrected it.

Do not observe one-off research, open-ended reasoning, destructive actions, payments, account/security changes, deletes, publishing, or other high-risk workflows.

Prefer inline JSON:

```bash
~/.fastbrain/fastbrain learn-observe "USER TRIGGER PHRASE" --json '{"id":"candidate_id","category":"apps","examples":["USER TRIGGER PHRASE"],"risk":"low","executor":{"command":"helper-name"}}'
```

Low-risk candidates become `eligible` only after at least two successful observations. Medium-risk candidates remain manual-promotion candidates. High-risk candidates are rejected.

When a low-risk observation returns `status: eligible`, Hermes may promote it automatically with:

```bash
~/.fastbrain/fastbrain learn-promote CANDIDATE_ID
```

Then verify:

```bash
~/.fastbrain/fastbrain route "USER TRIGGER PHRASE" --dry-run
```

Do not claim learning succeeded until promotion and local route verification both succeed.

## Correction-aware learning

When the user explicitly corrects how a FastBrain candidate or learned workflow should behave, update that same candidate/skill instead of creating a duplicate.

Use:

```bash
~/.fastbrain/fastbrain learn-correct CANDIDATE_ID "USER TRIGGER PHRASE" --wrong "what was wrong" --json '{"id":"CANDIDATE_ID","category":"apps","examples":["USER TRIGGER PHRASE"],"risk":"low","executor":{"command":"correct-helper"}}'
```

Rules:

- The corrected definition must retain the same candidate id.
- High-risk corrections are rejected and require manual integration.
- If the candidate was already promoted, FastBrain updates the learned skill in place.
- Record durable user preferences/meaning changes in Hindsight as well when appropriate.
- If the correction changes a FastBrain-owned helper, update that helper first, test it, then call `learn-correct` with the corrected definition.
- After correction, verify the trigger with `route ... --dry-run` before claiming it is fixed.
- A microphone misrecognition confirmation is not a durable correction and must not call `learn-correct` unless the user explicitly teaches the mapping/behavior.

## Learning policy

A workflow is a good FastBrain candidate when it is repeated or likely to repeat, deterministic enough to validate, low or medium risk, and materially faster without full Hermes reasoning.

Do not create a skill after a one-off success unless the user asked for it or the workflow is clearly reusable.

## Testing

Use `--dry-run` before real execution for calls, messages, reminders, or any medium-risk newly learned skill.

Useful commands:

```bash
~/.fastbrain/fastbrain doctor
~/.fastbrain/fastbrain skills
~/.fastbrain/fastbrain stats
~/.fastbrain/fastbrain learn-candidates
~/.fastbrain/fastbrain route "COMMAND" --dry-run
```
