#!/data/data/com.termux/files/usr/bin/bash
# Explicit sidecar launcher: FastBrain first, Hermes only after exit 64.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PREROUTER="${FASTBRAIN_PREROUTER:-$ROOT/scripts/hermes-fastbrain-wrapper.sh}"
HERMES="${HERMES_BIN:-hermes}"

OUT="$($PREROUTER "$@")"
STATUS=$?
case "$STATUS" in
  0)
    printf '%s\n' "$OUT"
    exit 0
    ;;
  64)
    TEXT=""
    while [ "$#" -gt 0 ]; do
      [ "$1" = "--" ] && { shift; break; }
      case "$1" in
        --request-id|--approval-token) shift 2 ;;
        *) break ;;
      esac
    done
    TEXT="$*"
    [ -n "$TEXT" ] || exit 75
    exec "$HERMES" chat --query "$TEXT" --source fastbrain-fallback
    ;;
  *)
    [ -z "$OUT" ] || printf '%s\n' "$OUT"
    exit "$STATUS"
    ;;
esac
