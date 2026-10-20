# Hermes integration

FastBrain is an optional sidecar pre-router, never a replacement for Hermes.

## Boundary

- Do **not** patch Hermes core, gateway code, Mobile, OmniRoute, Hindsight Lite, or `~/.hermes/config.yaml`.
- Do **not** install a persistent hook, service, or startup job.
- Do **not** start the native Termux bridge implicitly. Its lifecycle remains explicit:

  ```bash
  /root/FastBrain/bin/fastbrain native-bridge status|start|stop
  ```

## Sidecar protocol

Use the FastBrain-owned wrapper from an external caller that has a durable request identifier:

```bash
/root/FastBrain/scripts/hermes-fastbrain-wrapper.sh \
  --request-id "$REQUEST_ID" -- "$USER_TEXT"
```

The wrapper invokes `fastbrain preroute` exactly once and emits JSON. For command-line use, `scripts/hermes-with-fastbrain.sh` invokes this wrapper first and calls `hermes chat --query` only when the wrapper returns exit `64`; it is not a gateway hook or background service.

- Exit **64**: `decision=decline`; no FastBrain action was reserved or attempted. The caller may process the original request with Hermes.
- Exit **0**: `decision=handled`; consume the returned result. Do not also send that invocation to Hermes.
- Exit **75**: approval is required, work is in progress, the request conflicts, or a consequential result is indeterminate. Do not automatically fall through to Hermes or retry it.

For consequential local actions, the first call returns a one-time `approval_token`; the externally approved follow-up must reuse the same request ID and token:

```bash
/root/FastBrain/scripts/hermes-fastbrain-wrapper.sh \
  --request-id "$REQUEST_ID" \
  --approval-token "$APPROVAL_TOKEN" \
  -- "$USER_TEXT"
```

FastBrain records the request fingerprint and reserves execution atomically. A duplicate request ID returns the stored completion, `in_progress`, `indeterminate`, or `request_id_conflict`; it never performs the action a second time.

## Fallback and safety

- Unrecognized/non-local requests decline before execution and preserve normal Hermes processing.
- Battery status is the only automatic read-only Android candidate.
- App launch, flashlight, SMS, contact-dependent requests, media/volume controls, reminders, notes, and other local helpers require the pre-router approval handshake even if a legacy skill is labelled low risk.
- Existing native-bridge token authentication, HMAC confirmations, replay-nonce protection, fixed command/app allowlists, and battery-only Debian fallback stay in effect.
- A consequential timeout or failed execution is recorded as `indeterminate`; FastBrain will not retry it or request Hermes to duplicate it.

## Current status

This protocol is available for an external integration client, but it is **not connected to a Hermes gateway hook and is not auto-started**. Keep it that way until an integration caller can supply a stable request ID and display/return FastBrain’s structured result.
