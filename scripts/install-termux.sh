#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${FASTBRAIN_PYTHON:-python3.13}"
command -v "$PY" >/dev/null || { echo "ERROR: python3.13 is required. Nothing changed."; exit 2; }
"$PY" - <<'PY'
import sys
assert sys.version_info[:2]==(3,13), sys.version
print('Python 3.13 OK:',sys.version.split()[0])
PY

HOME_DIR="${FASTBRAIN_HOME:-$HOME/.fastbrain}"
APP_DIR="$HOME_DIR/app"
BIN_DIR="$HOME_DIR/bin"
mkdir -p "$HOME_DIR" "$BIN_DIR"

rm -rf "$APP_DIR.new"
mkdir -p "$APP_DIR.new"
cp -a "$ROOT/fastbrain" "$ROOT/skills" "$APP_DIR.new/"
rm -rf "$APP_DIR"
mv "$APP_DIR.new" "$APP_DIR"

# Install FastBrain-owned adapters only. Nothing is written into ~/.hermes.
cp "$ROOT/scripts/hindsight-direct.py" "$BIN_DIR/hindsight-direct.py"
cp "$ROOT/scripts/fast-music.py" "$BIN_DIR/fast-music.py"
chmod 700 "$BIN_DIR/hindsight-direct.py" "$BIN_DIR/fast-music.py"

cat > "$HOME_DIR/fastbrain.env.example" <<'ENV'
FASTBRAIN_MEMORY_MODE=hybrid
# Direct Hindsight may be configured as a command or HTTP endpoint.
# FASTBRAIN_HINDSIGHT_CMD="/path/to/hermes-python /path/to/hindsight-direct.py"
# FASTBRAIN_HINDSIGHT_URL=http://127.0.0.1:PORT
# FASTBRAIN_HINDSIGHT_PATH=/recall
FASTBRAIN_HINDSIGHT_TIMEOUT=5.0
FASTBRAIN_HINDSIGHT_LIMIT=3
ENV

# Preserve user configuration. Only create a default env if one does not exist.
ENV_FILE="$HOME_DIR/fastbrain.env"
if [ ! -f "$ENV_FILE" ]; then
  HERMES_PY="$HOME/.hermes/hermes-agent/venv/bin/python"
  if [ -x "$HERMES_PY" ] && "$HERMES_PY" - <<'PY' >/dev/null 2>&1
import hindsight_lite
from hindsight_lite.hermes import HermesMemoryBridge
PY
  then
    cat > "$ENV_FILE" <<ENV
FASTBRAIN_MEMORY_MODE=hybrid
FASTBRAIN_HINDSIGHT_CMD="$HERMES_PY $BIN_DIR/hindsight-direct.py"
FASTBRAIN_HINDSIGHT_TIMEOUT=5.0
FASTBRAIN_HINDSIGHT_LIMIT=3
ENV
    echo "Configured isolated direct Hindsight Lite adapter."
  else
    cat > "$ENV_FILE" <<'ENV'
FASTBRAIN_MEMORY_MODE=hybrid
FASTBRAIN_HINDSIGHT_TIMEOUT=5.0
FASTBRAIN_HINDSIGHT_LIMIT=3
ENV
    echo "Hindsight direct adapter not auto-configured; hot cache remains available."
  fi
fi

cat > "$HOME_DIR/fastbrain" <<EOF2
#!/data/data/com.termux/files/usr/bin/bash
set -a
[ -f "$HOME_DIR/fastbrain.env" ] && . "$HOME_DIR/fastbrain.env"
set +a
export PYTHONPATH="$APP_DIR:${PYTHONPATH:-}"
exec "$PY" -m fastbrain.cli "\$@"
EOF2
chmod +x "$HOME_DIR/fastbrain"

echo "Installed safely in $HOME_DIR"
echo "No pip install was run; no Hermes/OmniRoute/Hindsight/system Python files were modified."
echo "Run: $HOME_DIR/fastbrain doctor"
