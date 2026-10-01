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
HELPER_DIR="$HOME_DIR/helpers"
ROUTER_DIR="$HOME_DIR/router"
MODEL_DIR="$HOME_DIR/models"
MINILM_DIR="$HOME_DIR/minilm"
DB_PATH="${FASTBRAIN_DB:-$HOME_DIR/fastbrain.db}"
ENV_FILE="$HOME_DIR/fastbrain.env"
mkdir -p "$HOME_DIR" "$BIN_DIR" "$HELPER_DIR" "$ROUTER_DIR" "$MODEL_DIR" "$MINILM_DIR"
chmod 700 "$HELPER_DIR"

# Preserve runtime state between upgrades: router sockets, DB, env, and model files.
# We intentionally do not wipe prior DB or config. Re-running install should be safe.
backup_dir=""
if [ -d "$APP_DIR" ]; then
  backup_dir="$HOME_DIR/app.previous.$RANDOM"
  mv "$APP_DIR" "$backup_dir"
fi

rm -rf "$APP_DIR.new"
mkdir -p "$APP_DIR.new"
cp -a "$ROOT/fastbrain" "$ROOT/skills" "$APP_DIR.new/"
if [ -n "${backup_dir:-}" ] && [ -d "$backup_dir" ]; then
  # Keep old runtime state alive across an update; only the app package gets replaced.
  rm -rf "$backup_dir"
fi
mv "$APP_DIR.new" "$APP_DIR"

# Preserve existing environment and DB when updating, but install new CLI helpers.
# Never replace custom user configuration blindly.
cp "$ROOT/scripts/hindsight-direct.py" "$BIN_DIR/hindsight-direct.py"
cp "$ROOT/scripts/fast-media.sh" "$BIN_DIR/fast-media"
cp "$ROOT/scripts/minilm-semantic-service.py" "$BIN_DIR/minilm-semantic-service.py"
cp "$ROOT/scripts/start-minilm.sh" "$BIN_DIR/start-minilm"
cp "$ROOT/scripts/stop-minilm.sh" "$BIN_DIR/stop-minilm"
chmod 700 "$BIN_DIR/hindsight-direct.py" "$BIN_DIR/fast-media" "$BIN_DIR/minilm-semantic-service.py" "$BIN_DIR/start-minilm" "$BIN_DIR/stop-minilm"
rm -f "$BIN_DIR/fast-simpmusic"

cat > "$HOME_DIR/fastbrain.env.example" <<'ENV'
FASTBRAIN_MEMORY_MODE=hybrid
# Direct Hindsight may be configured as a command or HTTP endpoint.
# FASTBRAIN_HINDSIGHT_CMD="/path/to/hermes-python /path/to/hindsight-direct.py"
# FASTBRAIN_HINDSIGHT_URL=http://127.0.0.1:PORT
# FASTBRAIN_HINDSIGHT_PATH=/recall
FASTBRAIN_HINDSIGHT_TIMEOUT=5.0
FASTBRAIN_HINDSIGHT_LIMIT=3
# Optional persistent MiniLM semantic service:
# FASTBRAIN_SEMANTIC_BACKEND=minilm
# FASTBRAIN_MINILM_SOCKET="$HOME/.fastbrain/minilm/minilm.sock"
# FASTBRAIN_MINILM_TIMEOUT=0.20
# FASTBRAIN_MINILM_MIN_SIMILARITY=0.45
# FASTBRAIN_MINILM_MIN_MARGIN=0.10
ENV

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
FASTBRAIN_MINILM_TIMEOUT=0.20
ENV
    echo "Configured isolated direct Hindsight Lite adapter."
  else
    cat > "$ENV_FILE" <<'ENV'
FASTBRAIN_MEMORY_MODE=hybrid
FASTBRAIN_HINDSIGHT_TIMEOUT=5.0
FASTBRAIN_HINDSIGHT_LIMIT=3
FASTBRAIN_MINILM_TIMEOUT=0.20
ENV
    echo "Hindsight direct adapter not auto-configured; hot cache remains available."
  fi
fi

# Do not overwrite an existing DB or live router state during an update.
if [ ! -f "$DB_PATH" ]; then
  touch "$DB_PATH"
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

# Install FastBrain's Hermes skill. Existing skills are not edited.
HERMES_SKILL_DIR="$HOME/.hermes/skills/fastbrain"
if [ -d "$HOME/.hermes" ] && [ -f "$ROOT/integrations/hermes-fastbrain/SKILL.md" ]; then
  mkdir -p "$HERMES_SKILL_DIR"
  cp "$ROOT/integrations/hermes-fastbrain/SKILL.md" "$HERMES_SKILL_DIR/SKILL.md"
  chmod 600 "$HERMES_SKILL_DIR/SKILL.md"
  echo "Installed Hermes FastBrain integration skill: $HERMES_SKILL_DIR/SKILL.md"
fi

# Add one bounded persistent note so Hermes knows how to bridge durable learning
# into FastBrain even if skill discovery changes. Preserve all existing content.
LEARNED="$HOME/hermes-phone/LEARNED.md"
MARKER_BEGIN='<!-- FASTBRAIN_BRIDGE_BEGIN -->'
MARKER_END='<!-- FASTBRAIN_BRIDGE_END -->'
if [ -f "$LEARNED" ] && ! grep -Fq "$MARKER_BEGIN" "$LEARNED"; then
  cat >> "$LEARNED" <<'EOF3'

<!-- FASTBRAIN_BRIDGE_BEGIN -->
## FastBrain bridge
- FastBrain is the low-latency router at `~/.fastbrain/fastbrain`; Hermes remains the full reasoning fallback.
- For a durable alias/preference/default/routine/correction that should be fast, update Hindsight as source of truth and also project it into FastBrain hot cache.
- Contact aliases use: `~/.fastbrain/fastbrain cache-put alias <lowercase-alias> "<resolved contact>" --scope communication`.
- Verify FastBrain writes instead of only claiming they were stored.
- Reusable low/medium-risk workflows may become FastBrain helpers under `~/.fastbrain/helpers/` plus a registered FastBrain skill.
- Do not overwrite existing Hermes phone helpers merely to teach FastBrain a new workflow.
<!-- FASTBRAIN_BRIDGE_END -->
EOF3
  echo "Added bounded FastBrain bridge note to $LEARNED"
fi

echo "Installed safely in $HOME_DIR"
echo "Existing DB/env/router/model data were preserved for in-place updates."
echo "Run: $HOME_DIR/fastbrain doctor"
