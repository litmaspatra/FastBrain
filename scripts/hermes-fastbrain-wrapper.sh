#!/data/data/com.termux/files/usr/bin/bash
# Non-invasive pre-router. It never replaces Hermes; on any miss/error it exits 64 so caller can run normal Hermes.
set -euo pipefail
FB="${FASTBRAIN_HOME:-$HOME/.fastbrain}/fastbrain"
TEXT="$*"
[ -x "$FB" ] || exit 64
JSON="$($FB route "$TEXT")" || exit 64
ROUTE=$(printf '%s' "$JSON" | "${FASTBRAIN_PYTHON:-python3.13}" -c 'import json,sys; print(json.load(sys.stdin).get("route","hermes"))')
if [ "$ROUTE" != local ]; then exit 64; fi
exec "$FB" route --execute "$TEXT"
