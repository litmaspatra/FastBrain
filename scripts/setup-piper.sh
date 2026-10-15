#!/usr/bin/env bash
# One-time setup of the natural voice (Piper) for the Hermes Mobile app, then starts it. Safe to run again.
# Run it in the same Linux environment where Hermes / FastBrain run (Termux, or the Debian/Ubuntu proot).
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
DIR="${PIPER_VOICES_DIR:-$HOME/.piper-voices}"
PY="${PYTHON:-python3}"
mkdir -p "$DIR"
"$PY" -m pip install --upgrade piper-tts numpy 2>&1 | tail -2 || "$PY" -m pip install --break-system-packages --upgrade piper-tts numpy
# A clear female voice and a male one, medium quality (about 60 MB each). Add any other Piper voice name here.
for v in ${PIPER_VOICES:-en_US-lessac-medium en_US-ryan-medium}; do
  [ -f "$DIR/$v.onnx" ] || "$PY" -m piper.download_voices --download-dir "$DIR" "$v"
done
pkill -f piper-tts-server.py 2>/dev/null || true
if command -v setsid >/dev/null 2>&1; then setsid nohup "$PY" "$HERE/piper-tts-server.py" --voices-dir "$DIR" > "$DIR/server.log" 2>&1 < /dev/null &
else nohup "$PY" "$HERE/piper-tts-server.py" --voices-dir "$DIR" > "$DIR/server.log" 2>&1 < /dev/null & fi
sleep 2
echo "Piper voice server started (log: $DIR/server.log). In the app: Settings → Voice → Natural voice → Test voice."
