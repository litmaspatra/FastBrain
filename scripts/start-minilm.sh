#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
FB_HOME="${FASTBRAIN_HOME:-$HOME/.fastbrain}"
MODEL="${FASTBRAIN_MINILM_MODEL:-$FB_HOME/minilm/model_qint8_arm64.onnx}"
VOCAB="${FASTBRAIN_MINILM_VOCAB:-$FB_HOME/minilm/vocab.txt}"
SKILLS="$FB_HOME/app/skills/builtin.json"
DB="${FASTBRAIN_DB:-$FB_HOME/fastbrain.db}"
SOCK="${FASTBRAIN_MINILM_SOCKET:-$FB_HOME/minilm/minilm.sock}"
PIDFILE="$FB_HOME/minilm/minilm.pid"
LOG="$FB_HOME/minilm/minilm.log"
PY="${FASTBRAIN_MINILM_PYTHON:-python3.14}"
SERVICE="$FB_HOME/bin/minilm-semantic-service.py"
mkdir -p "$FB_HOME/minilm"

for f in "$MODEL" "$VOCAB" "$SKILLS" "$SERVICE"; do
  [ -e "$f" ] || { echo "MINILM_START_ERROR missing $f"; exit 2; }
done
command -v "$PY" >/dev/null || { echo "MINILM_START_ERROR missing $PY"; exit 2; }

if [ -f "$PIDFILE" ]; then
  pid="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    echo "MINILM_ALREADY_RUNNING pid=$pid socket=$SOCK"
    exit 0
  fi
  rm -f "$PIDFILE"
fi
rm -f "$SOCK"
nohup "$PY" "$SERVICE" --model "$MODEL" --vocab "$VOCAB" --skills "$SKILLS" --db "$DB" --socket "$SOCK" >"$LOG" 2>&1 &
pid=$!
echo "$pid" > "$PIDFILE"

for _ in $(seq 1 50); do
  if [ -S "$SOCK" ]; then
    echo "MINILM_STARTED pid=$pid socket=$SOCK"
    exit 0
  fi
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "MINILM_START_ERROR process_exited"
    tail -n 20 "$LOG" 2>/dev/null || true
    exit 3
  fi
  sleep 0.1
done

echo "MINILM_START_ERROR socket_timeout"
tail -n 20 "$LOG" 2>/dev/null || true
exit 4
