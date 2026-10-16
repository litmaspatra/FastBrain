#!/usr/bin/env bash
# Starts what the Hermes Mobile app talks to, only if it isn't already running: the router (if down), its key-protected
# loopback bridge (fastbrain-router-tcp.py, port 8765) and the Piper voice server (port 8766, if a voice is installed).
# The app runs this by itself the first time a voice command finds the bridge down; you can also run it by hand.
FB_HOME="${FASTBRAIN_HOME:-$HOME/.fastbrain}"
SOCK="${FASTBRAIN_ROUTER_SOCKET:-$FB_HOME/router/router.sock}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"
mkdir -p "$FB_HOME/router"
bg() { if command -v setsid >/dev/null 2>&1; then setsid nohup "$@" < /dev/null & else nohup "$@" < /dev/null & fi; }
[ -S "$SOCK" ] || bash "$ROOT/scripts/start-fastbrain-router.sh" >"$FB_HOME/router/start.log" 2>&1 || true
pgrep -f fastbrain-router-tcp.py >/dev/null 2>&1 || bg "$PY" "$ROOT/scripts/fastbrain-router-tcp.py" --socket "$SOCK" >"$FB_HOME/router/tcp.log" 2>&1
if ! pgrep -f piper-tts-server.py >/dev/null 2>&1; then
  bg "$PY" "$ROOT/scripts/piper-tts-server.py" >"$FB_HOME/router/piper.log" 2>&1
fi
sleep 1
echo started
