#!/data/data/com.termux/files/usr/bin/bash
# Non-invasive pre-router. It never replaces Hermes: exit 64 means "not handled, run normal Hermes".
# One call only: the router decides AND executes. (The old version routed twice, which recorded
# the request twice and could double-trigger followups.) Output is printed only on success so a
# declined request leaves stdout clean for Hermes.
set -u
FB="${FASTBRAIN_HOME:-$HOME/.fastbrain}/fastbrain"
TEXT="$*"
[ -x "$FB" ] && [ -n "$TEXT" ] || exit 64
if OUT="$("$FB" route --execute "$TEXT" 2>/dev/null)"; then
  printf '%s\n' "$OUT"
  exit 0
fi
exit 64
