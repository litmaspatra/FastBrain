---
name: fastbrain
description: Use FastBrain as Hermes' low-latency phone router for aliases, preferences, corrections, reusable helpers, and learned skills.
---

# FastBrain integration for Hermes

FastBrain is the phone's low-latency reflex/router layer. Use it for reusable device actions, aliases, preferences, corrections, and learned helpers while keeping Hermes as the full reasoning fallback.

## Mandatory bridge behavior

When the user explicitly teaches a durable alias, preference, default, routine, channel preference, constraint, or reusable FastBrain behavior:

1. Store or update the durable fact in Hindsight using `hmem_remember` or `hmem_update` when appropriate.
2. Project performance-critical facts into FastBrain immediately with `~/.fastbrain/fastbrain cache-put ...`.
3. Do not merely say FastBrain will know it. Verify the FastBrain write succeeded.

For contact aliases, always use type `alias`, scope `communication`, and lowercase the alias subject. Example:

```bash
~/.fastbrain/fastbrain cache-put alias ashu "Anshul Sharma" --scope communication
```

When useful, verify with:

```bash
~/.fastbrain/fastbrain route "call Ashu" --dry-run
```

The expected contact is `Anshul Sharma` with `context_source` equal to `hot`.

## Core rules

- Prefer FastBrain for simple, repeatable phone actions that can be represented as a typed skill.
- Do not bypass FastBrain safety/risk rules for high-risk actions.
- Do not modify existing Hermes helpers when a new FastBrain-only helper will work. Put new helpers in `~/.fastbrain/helpers/` and make them executable.
- Keep Hindsight as the durable source of truth and FastBrain hot memory as the speed layer.
- Avoid duplicate Hindsight memories. Update or merge an existing fact when appropriate.
- A missing FastBrain alias is not an error; literal contact names are passed to the Android contact resolver.

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
~/.fastbrain/fastbrain cache-put alias ashu "Anshul Sharma" --scope communication
~/.fastbrain/fastbrain cache-put alias anshul "Anshul Sharma" --scope communication
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

1. Create a helper under `~/.fastbrain/helpers/NAME`.
2. Make it executable with `chmod 700 ~/.fastbrain/helpers/NAME`.
3. Test it directly with harmless or dry-run inputs when possible.
4. Register a learned skill whose executor command is `NAME`.
5. Test routing with `~/.fastbrain/fastbrain route "example phrase" --dry-run`.

FastBrain searches `~/.fastbrain/helpers/` before Hermes helper directories for learned helper commands.

## Learning policy

A workflow is a good FastBrain candidate when it is repeated or likely to repeat, deterministic enough to validate, low or medium risk, and materially faster without full Hermes reasoning.

Do not create a skill after a one-off success unless the user asked for it or the workflow is clearly reusable.

When a user corrects FastBrain, preserve the correction in Hindsight when durable, update the hot cache if performance-critical, and revise or re-register the learned skill if the correction changes routing or execution.

## Testing

Use `--dry-run` before real execution for calls, messages, reminders, or any medium-risk newly learned skill.

Useful commands:

```bash
~/.fastbrain/fastbrain doctor
~/.fastbrain/fastbrain skills
~/.fastbrain/fastbrain stats
~/.fastbrain/fastbrain route "COMMAND" --dry-run
```
