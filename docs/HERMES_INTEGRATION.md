# Hermes integration

FastBrain is intentionally a sidecar, not a replacement.

1. Install and validate FastBrain independently.
2. Keep normal Hermes routing unchanged.
3. Add `scripts/hermes-fastbrain-wrapper.sh` as a pre-router only after validation.
4. Exit code `64` means "not handled": invoke normal Hermes/OmniRoute.
5. If FastBrain is stopped, Hermes must continue normally.

Recommended flow:

`input -> wrapper -> FastBrain local action OR exit 64 -> Hermes`

Do not patch `~/.hermes`, OmniRoute, Hindsight, or the Android adapter until the standalone benchmark passes on the phone.
