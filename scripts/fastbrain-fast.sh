#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
FB_HOME="${FASTBRAIN_HOME:-$HOME/.fastbrain}"
SOCK="${FASTBRAIN_ROUTER_SOCKET:-$FB_HOME/router/router.sock}"
FALLBACK="$FB_HOME/fastbrain"

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
if [ -S "$SOCK" ]; then
  if curl -fsS --max-time 1 --unix-socket "$SOCK" \
      -X POST \
      --data-urlencode "text=$text" \
      --data "dry_run=$dry" \
      --data "execute=$execute" \
      http://localhost/route; then
    printf '\n'
    exit 0
  fi
fi
exec "$FALLBACK" route "$text" $([ "$dry" = 1 ] && printf '%s' '--dry-run') $([ "$execute" = 1 ] && printf '%s' '--execute')
