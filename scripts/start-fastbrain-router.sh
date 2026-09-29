#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
FB_HOME="${FASTBRAIN_HOME:-$HOME/.fastbrain}"
SOCK="${FASTBRAIN_ROUTER_SOCKET:-$FB_HOME/router/router.sock}"
PIDFILE="$FB_HOME/router/router.pid"
LOG="$FB_HOME/router/router.log"
PY="${FASTBRAIN_PYTHON:-python3.13}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE="$ROOT/scripts/fastbrain-router-service.py"
mkdir -p "$FB_HOME/router"
if [ -f "$PIDFILE" ]; then
  old="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$old" ] && kill -0 "$old" 2>/dev/null; then kill "$old" 2>/dev/null || true; sleep 0.2; fi
fi
rm -f "$SOCK"
set -a
[ -f "$FB_HOME/fastbrain.env" ] && . "$FB_HOME/fastbrain.env"
set +a
export PYTHONPATH="$FB_HOME/app:${PYTHONPATH:-}"
nohup "$PY" "$SERVICE" --socket "$SOCK" >"$LOG" 2>&1 &
pid=$!
echo "$pid" > "$PIDFILE"
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if [ -S "$SOCK" ] && curl -fsS --unix-socket "$SOCK" http://localhost/health >/dev/null 2>&1; then
    echo "FASTBRAIN_ROUTER_STARTED pid=$pid socket=$SOCK"
    exit 0
  fi
  sleep 0.1
done
echo "ERROR: router did not become ready"
tail -n 30 "$LOG" 2>/dev/null || true
exit 1
