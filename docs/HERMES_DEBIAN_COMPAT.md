# Hermes Debian proot compatibility (staged, not activated)

Hermes v0.21.6 can run inside Debian proot with a standalone Python 3.14 runtime, while FastBrain remains in Termux with its own Python 3.13 runtime.

## Boundaries

- Do **not** pip-install, create venvs, or modify `/root/.hermes` or the standalone Python runtime.
- Do not change OmniRoute, Hindsight memory data, Android adapter, model services, existing ports, or startup order.
- FastBrain stays a Termux sidecar; no Python imports across Termux and Debian.
- The existing pre-router returns exit code 64 when unhandled or unavailable. Treat that as fallthrough to Hermes.
- Hindsight direct integration should use a documented localhost HTTP/JSON adapter or an explicit stdin/stdout subprocess contract, not import a package from the other environment.
- Bind HTTP services to 127.0.0.1 only; use strict timeout and input validation. Proot and Termux share the device networking stack but endpoints still require real connectivity tests.
- Preserve existing `FASTBRAIN_HINDSIGHT_URL`, `FASTBRAIN_HINDSIGHT_PATH`, and `FASTBRAIN_HINDSIGHT_CMD` integration settings.

## Read-only verification on the phone

From Termux:
```sh
~/.fastbrain/fastbrain doctor
~/.fastbrain/fastbrain route "check battery" --dry-run
proot-distro login debian -- bash -lc 'hermes --version; hermes config get memory.provider'
```

No activation or environment changes are part of this staging document. Before wiring Hindsight, verify an end-to-end read against a throwaway test memory and confirm no Hermes startup regression. Do not use production memories for the bridge smoke test.
