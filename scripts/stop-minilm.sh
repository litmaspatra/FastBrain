#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
FB_HOME="${FASTBRAIN_HOME:-$HOME/.fastbrain}"
PIDFILE="$FB_HOME/minilm/minilm.pid"
SOCK="$FB_HOME/minilm/minilm.sock"
if [ -f "$PIDFILE" ]; then
  pid="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 20); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.1
    done
  fi
fi
rm -f "$PIDFILE" "$SOCK"
echo "MINILM_STOPPED"
