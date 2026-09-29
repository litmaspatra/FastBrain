#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
FB_HOME="${FASTBRAIN_HOME:-$HOME/.fastbrain}"
SOCK="${FASTBRAIN_ROUTER_SOCKET:-$FB_HOME/router/router.sock}"
FALLBACK="$FB_HOME/fastbrain"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLIENT="$ROOT/scripts/fastbrain-router-client.py"
PY="${FASTBRAIN_PYTHON:-python3.13}"

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

if [ -S "$SOCK" ] && [ -f "$CLIENT" ] && command -v "$PY" >/dev/null 2>&1; then
  args=("$PY" "$CLIENT" --socket "$SOCK")
  [ "$dry" = 1 ] && args+=(--dry-run)
  [ "$execute" = 1 ] && args+=(--execute)
  args+=("$text")
  if "${args[@]}"; then
    exit 0
  fi
fi

fallback=("$FALLBACK" route "$text")
[ "$dry" = 1 ] && fallback+=(--dry-run)
[ "$execute" = 1 ] && fallback+=(--execute)
exec "${fallback[@]}"
