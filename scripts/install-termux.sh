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
mkdir -p "$HOME_DIR"
rm -rf "$APP_DIR.new"
mkdir -p "$APP_DIR.new"
cp -a "$ROOT/fastbrain" "$ROOT/skills" "$APP_DIR.new/"
rm -rf "$APP_DIR"
mv "$APP_DIR.new" "$APP_DIR"
cat > "$HOME_DIR/fastbrain.env.example" <<'ENV'
# Copy to ~/.fastbrain/fastbrain.env and edit if needed.
FASTBRAIN_MEMORY_MODE=hybrid
# Configure ONE direct adapter only after validating your Hindsight interface.
# FASTBRAIN_HINDSIGHT_URL=http://127.0.0.1:PORT
# FASTBRAIN_HINDSIGHT_PATH=/recall
# FASTBRAIN_HINDSIGHT_CMD=/path/to/adapter-command
FASTBRAIN_HINDSIGHT_TIMEOUT=0.8
ENV
cat > "$HOME_DIR/fastbrain" <<EOF2
#!/data/data/com.termux/files/usr/bin/bash
set -a
[ -f "$HOME_DIR/fastbrain.env" ] && . "$HOME_DIR/fastbrain.env"
set +a
export PYTHONPATH="$APP_DIR:${PYTHONPATH:-}"
exec "$PY" -m fastbrain.cli "$@"
EOF2
chmod +x "$HOME_DIR/fastbrain"
echo "Installed safely in $HOME_DIR"
echo "No pip install was run; no Hermes/OmniRoute/Hindsight/system Python files were modified."
echo "Run: $HOME_DIR/fastbrain doctor"
