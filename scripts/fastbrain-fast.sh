#!/data/data/com.termux/files/usr/bin/bash
# Fast path: ask the resident router over its unix socket; fall back to the CLI.
# Never falls back after an --execute request that may already have run (no double actions).
set -euo pipefail
FB_HOME="${FASTBRAIN_HOME:-$HOME/.fastbrain}"
SOCK="${FASTBRAIN_ROUTER_SOCKET:-$FB_HOME/router/router.sock}"
FALLBACK="$FB_HOME/fastbrain"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLIENT="$ROOT/scripts/fastbrain-router-client.py"
pick_python() {
  local c p
  for c in "$@"; do
    [ -n "$c" ] || continue
    p="$(command -v "$c" 2>/dev/null)" || continue
    "$p" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 13) else 1)' 2>/dev/null && { echo "$p"; return 0; }
  done
  return 1
}
PY="$(pick_python "${FASTBRAIN_PYTHON:-}" python3.13 python3.14 python3 || true)"

if [ "${1:-}" != "route" ]; then
  exec "$FALLBACK" "$@"
fi
shift
text_parts=()
dry=0
execute=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) dry=1 ;;
    --execute) execute=1 ;;
    *) text_parts+=("$1") ;;
  esac
  shift
done
text="${text_parts[*]:-}"
if [ -z "$text" ]; then
  echo "usage: fastbrain-fast route <text> [--dry-run|--execute]" >&2
  exit 2
fi

if [ -S "$SOCK" ] && [ -f "$CLIENT" ] && [ -n "$PY" ]; then
  args=("$PY" "$CLIENT" --socket "$SOCK")
  [ "$dry" = 1 ] && args+=(--dry-run)
  [ "$execute" = 1 ] && args+=(--execute)
  args+=("$text")
  rc=0
  "${args[@]}" || rc=$?
  if [ "$rc" -eq 0 ]; then
    exit 0
  fi
  # rc 3 = never reached the router (safe to retry). rc 4 = request was sent but the reply
  # was lost/late: with --execute the action may have happened, so do NOT run it again.
  if [ "$rc" -eq 4 ] && [ "$execute" = 1 ]; then
    echo "FASTBRAIN_ROUTER_NO_REPLY: not retrying an --execute request" >&2
    exit 64
  fi
fi

fallback=("$FALLBACK" route "$text")
[ "$dry" = 1 ] && fallback+=(--dry-run)
[ "$execute" = 1 ] && fallback+=(--execute)
exec "${fallback[@]}"
