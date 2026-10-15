#!/data/data/com.termux/files/usr/bin/bash
# Start (or restart) the resident router. Keeps the DB/aliases warm so routing is ~ms.
set -euo pipefail
FB_HOME="${FASTBRAIN_HOME:-$HOME/.fastbrain}"
SOCK="${FASTBRAIN_ROUTER_SOCKET:-$FB_HOME/router/router.sock}"
PIDFILE="$FB_HOME/router/router.pid"
LOG="$FB_HOME/router/router.log"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE="$ROOT/scripts/fastbrain-router-service.py"
pick_python() {
  local c p
  for c in "$@"; do
    [ -n "$c" ] || continue
    p="$(command -v "$c" 2>/dev/null)" || continue
    "$p" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 13) else 1)' 2>/dev/null && { echo "$p"; return 0; }
  done
  return 1
}
PY="$(pick_python "${FASTBRAIN_PYTHON:-}" python3.13 python3.14 python3)" || { echo "ERROR: Python 3.13+ required" >&2; exit 2; }
mkdir -p "$FB_HOME/router"
if [ -f "$PIDFILE" ]; then
  old="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$old" ] && kill -0 "$old" 2>/dev/null; then
    kill "$old" 2>/dev/null || true
    for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do kill -0 "$old" 2>/dev/null || break; sleep 0.1; done
    kill -9 "$old" 2>/dev/null || true
  fi
fi
rm -f "$SOCK"
set -a
[ -f "$FB_HOME/fastbrain.env" ] && . "$FB_HOME/fastbrain.env"
set +a
export PYTHONPATH="$FB_HOME/app${PYTHONPATH:+:$PYTHONPATH}"
if command -v setsid >/dev/null 2>&1; then
  setsid nohup "$PY" "$SERVICE" --socket "$SOCK" >"$LOG" 2>&1 < /dev/null &
else
  nohup "$PY" "$SERVICE" --socket "$SOCK" >"$LOG" 2>&1 < /dev/null &
fi
pid=$!
echo "$pid" > "$PIDFILE"
for _ in $(seq 1 30); do
  if [ -S "$SOCK" ] && "$PY" - "$SOCK" <<'PYEOF' >/dev/null 2>&1
import socket, sys
s = socket.socket(socket.AF_UNIX); s.settimeout(1); s.connect(sys.argv[1])
s.sendall(b"GET /health HTTP/1.0\r\n\r\n"); raise SystemExit(0 if b" 200 " in s.recv(256) else 1)
PYEOF
  then
    # Loopback bridge for the Hermes Mobile app (key-protected; see fastbrain-router-tcp.py). Restarted with the router.
    TCP="$ROOT/scripts/fastbrain-router-tcp.py"; TPID="$FB_HOME/router/tcp.pid"
    if [ -f "$TCP" ]; then
      [ -f "$TPID" ] && kill "$(cat "$TPID" 2>/dev/null)" 2>/dev/null || true
      if command -v setsid >/dev/null 2>&1; then setsid nohup "$PY" "$TCP" --socket "$SOCK" >"$FB_HOME/router/tcp.log" 2>&1 < /dev/null &
      else nohup "$PY" "$TCP" --socket "$SOCK" >"$FB_HOME/router/tcp.log" 2>&1 < /dev/null & fi
      echo $! > "$TPID"
    fi
    # Natural voice (Piper) for the app, if setup-piper.sh was run once.
    PV="${PIPER_VOICES_DIR:-$HOME/.piper-voices}"
    if [ -f "$ROOT/scripts/piper-tts-server.py" ] && ls "$PV"/*.onnx >/dev/null 2>&1; then
      pkill -f piper-tts-server.py 2>/dev/null || true
      if command -v setsid >/dev/null 2>&1; then setsid nohup "$PY" "$ROOT/scripts/piper-tts-server.py" --voices-dir "$PV" >"$PV/server.log" 2>&1 < /dev/null &
      else nohup "$PY" "$ROOT/scripts/piper-tts-server.py" --voices-dir "$PV" >"$PV/server.log" 2>&1 < /dev/null & fi
    fi
    echo "FASTBRAIN_ROUTER_STARTED pid=$pid socket=$SOCK"
    exit 0
  fi
  kill -0 "$pid" 2>/dev/null || break
  sleep 0.1
done
echo "ERROR: router did not become ready"
tail -n 30 "$LOG" 2>/dev/null || true
exit 1
