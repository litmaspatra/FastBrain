# FastBrain integration for Hermes

FastBrain is the phone's low-latency reflex/router layer. Use it for reusable device actions, aliases, preferences, corrections, and learned helpers while keeping Hermes as the full reasoning fallback.

## Core rules

- Prefer FastBrain for simple, repeatable phone actions that can be represented as a typed skill.
- Do not bypass FastBrain safety/risk rules for high-risk actions.
- Do not modify existing Hermes helpers when a new FastBrain-only helper will work. Put new helpers in `~/.fastbrain/helpers/` and make them executable.
- When the user teaches or corrects an alias, preference, default, routine, channel preference, or other durable fact, keep Hindsight as the durable source of truth using the available `hmem_remember` / `hmem_update` tools, and also project the performance-critical value into FastBrain's hot cache.
- Avoid duplicate Hindsight memories. Update/merge an existing fact when appropriate.

## FastBrain command

Use:

```bash
~/.fastbrain/fastbrain
```

### Add/update a hot memory

```bash
~/.fastbrain/fastbrain cache-put TYPE SUBJECT VALUE --scope SCOPE
```

Important examples:

```bash
~/.fastbrain/fastbrain cache-put alias anshul "Anshul Sharma" --scope communication
~/.fastbrain/fastbrain cache-put alias govind butagorira --scope communication
~/.fastbrain/fastbrain cache-put preference evening "upbeat hindi" --scope music
```

For contact aliases, always use type `alias` and scope `communication`. FastBrain checks this cache before the Android contact resolver. If there is no alias, literal contact names are passed directly to the phone contact resolver.

### Remove a wrong hot value

```bash
~/.fastbrain/fastbrain cache-delete TYPE SUBJECT --scope SCOPE
```

Also correct/update the corresponding Hindsight fact when one exists.

### Register a learned skill

Write a JSON definition to a temporary file and register it:

```bash
~/.fastbrain/fastbrain skill-add /path/to/skill.json
```

Required fields: `id`, `category`, `examples`, `executor`.

Recommended definition:

```json
{
  "id": "example_action",
  "category": "device",
  "description": "Example learned action",
  "risk": "low",
  "arguments": {
    "target": {"required": true}
  },
  "examples": ["do example for kitchen", "run example kitchen"],
  "executor": {
    "command": "example-action",
    "args": ["target"]
  },
  "timeout": 8
}
```

High-risk skills require manual integration and must not be auto-registered.

### Create a FastBrain helper

For a reusable workflow that Hermes successfully solved and that is safe to automate:

1. Create a small helper under `~/.fastbrain/helpers/NAME`.
2. Make it executable with `chmod 700 ~/.fastbrain/helpers/NAME`.
3. Test the helper directly using harmless/dry-run inputs when possible.
4. Register a learned skill whose executor command is `NAME`.
5. Test routing with:

```bash
~/.fastbrain/fastbrain route "example phrase" --dry-run
```

FastBrain searches `~/.fastbrain/helpers/` before Hermes helper directories for learned helper commands.

## Learning policy

A workflow is a good FastBrain candidate when it is:

- repeated or likely to repeat;
- deterministic enough to validate;
- low or medium risk;
- materially faster without full Hermes reasoning.

Do not create a skill after a one-off success unless the user asked for it or the workflow is clearly reusable.

When a user corrects FastBrain, preserve the correction in Hindsight when durable, update the hot cache if performance-critical, and revise/register the learned skill if the correction changes routing or execution.

## Testing

Use `--dry-run` before real execution for calls, messages, reminders, or any medium-risk newly learned skill.

Useful commands:

```bash
~/.fastbrain/fastbrain doctor
~/.fastbrain/fastbrain skills
~/.fastbrain/fastbrain stats
~/.fastbrain/fastbrain route "COMMAND" --dry-run
```
