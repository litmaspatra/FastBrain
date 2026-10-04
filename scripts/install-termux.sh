#!/data/data/com.termux/files/usr/bin/bash
# Installs/updates FastBrain into ~/.fastbrain. Safe to re-run: env, DB, router and model
# files are never overwritten. No pip is run and nothing outside ~/.fastbrain is replaced.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# First interpreter that is Python >= 3.13 (3.13 and 3.14 both work; core is stdlib-only).
pick_python() {
  local c p
  for c in "$@"; do
    [ -n "$c" ] || continue
    p="$(command -v "$c" 2>/dev/null)" || continue
    "$p" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 13) else 1)' 2>/dev/null && { echo "$p"; return 0; }
  done
  return 1
}
PY="$(pick_python "${FASTBRAIN_PYTHON:-}" python3.13 python3.14 python3)" || {
  echo "ERROR: Python 3.13+ is required (tried python3.13, python3.14, python3). Nothing changed." >&2
  echo "       Termux: pkg install python   (or set FASTBRAIN_PYTHON=/path/to/python3.13)" >&2
  exit 2
}
echo "Python OK: $PY ($("$PY" -c 'import sys; print(sys.version.split()[0])'))"

HOME_DIR="${FASTBRAIN_HOME:-$HOME/.fastbrain}"
APP_DIR="$HOME_DIR/app"
BIN_DIR="$HOME_DIR/bin"
HELPER_DIR="$HOME_DIR/helpers"
mkdir -p "$HOME_DIR" "$BIN_DIR" "$HELPER_DIR" "$HOME_DIR/router" "$HOME_DIR/minilm" "$HOME_DIR/state"
chmod 700 "$HELPER_DIR"

# Build the new app dir first, then swap, so a failed copy never leaves you without an app.
rm -rf "$APP_DIR.new" "$APP_DIR.old"
mkdir -p "$APP_DIR.new"
cp -a "$ROOT/fastbrain" "$ROOT/skills" "$APP_DIR.new/"
find "$APP_DIR.new" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
[ -d "$APP_DIR" ] && mv "$APP_DIR" "$APP_DIR.old"
mv "$APP_DIR.new" "$APP_DIR"
rm -rf "$APP_DIR.old"

# FastBrain-owned adapters. Existing Hermes phone helpers are never modified.
install_bin() { cp "$ROOT/scripts/$1" "$BIN_DIR/$2"; chmod 700 "$BIN_DIR/$2"; }
install_bin hindsight-direct.py hindsight-direct.py
install_bin fast-media.sh fast-media
install_bin minilm-semantic-service.py minilm-semantic-service.py
install_bin start-minilm.sh start-minilm
install_bin stop-minilm.sh stop-minilm
rm -f "$BIN_DIR/fast-simpmusic"

cat > "$HOME_DIR/fastbrain.env.example" <<'ENV'
FASTBRAIN_MEMORY_MODE=hybrid
# Direct Hindsight may be configured as a command or HTTP endpoint.
# FASTBRAIN_HINDSIGHT_CMD="/path/to/hermes-python /path/to/hindsight-direct.py"
# FASTBRAIN_HINDSIGHT_URL=http://127.0.0.1:PORT
# FASTBRAIN_HINDSIGHT_PATH=/recall
FASTBRAIN_HINDSIGHT_TIMEOUT=5.0
FASTBRAIN_HINDSIGHT_LIMIT=3
# Pin the interpreters if auto-detection picks the wrong one:
# FASTBRAIN_PYTHON=/data/data/com.termux/files/usr/bin/python3.13
# FASTBRAIN_MINILM_PYTHON=/data/data/com.termux/files/usr/bin/python3.14
# Optional persistent MiniLM semantic service:
# FASTBRAIN_SEMANTIC_BACKEND=minilm
# FASTBRAIN_MINILM_SOCKET="$HOME/.fastbrain/minilm/minilm.sock"
# FASTBRAIN_MINILM_TIMEOUT=0.20
# FASTBRAIN_MINILM_MIN_SIMILARITY=0.45
# FASTBRAIN_MINILM_MIN_MARGIN=0.10
ENV

ENV_FILE="$HOME_DIR/fastbrain.env"
if [ ! -f "$ENV_FILE" ]; then
  HERMES_PY="$HOME/.hermes/hermes-agent/venv/bin/python"
  if [ -x "$HERMES_PY" ] && "$HERMES_PY" -c 'import hindsight_lite; from hindsight_lite.hermes import HermesMemoryBridge' >/dev/null 2>&1; then
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
  chmod 600 "$ENV_FILE"
fi

# Launcher. PYTHONPATH is expanded when it RUNS (\$), not frozen at install time.
cat > "$HOME_DIR/fastbrain.tmp" <<EOF2
#!/data/data/com.termux/files/usr/bin/bash
set -a
[ -f "$HOME_DIR/fastbrain.env" ] && . "$HOME_DIR/fastbrain.env"
set +a
export PYTHONPATH="$APP_DIR\${PYTHONPATH:+:\$PYTHONPATH}"
exec "$PY" -m fastbrain.cli "\$@"
EOF2
chmod +x "$HOME_DIR/fastbrain.tmp"
mv "$HOME_DIR/fastbrain.tmp" "$HOME_DIR/fastbrain"

# Hermes skill. Existing skills are not edited.
HERMES_SKILL_DIR="$HOME/.hermes/skills/fastbrain"
if [ -d "$HOME/.hermes" ] && [ -f "$ROOT/integrations/hermes-fastbrain/SKILL.md" ]; then
  mkdir -p "$HERMES_SKILL_DIR"
  cp "$ROOT/integrations/hermes-fastbrain/SKILL.md" "$HERMES_SKILL_DIR/SKILL.md"
  chmod 600 "$HERMES_SKILL_DIR/SKILL.md"
  echo "Installed Hermes FastBrain integration skill: $HERMES_SKILL_DIR/SKILL.md"
fi

# One bounded persistent note so Hermes knows how to bridge durable learning into FastBrain.
LEARNED="$HOME/hermes-phone/LEARNED.md"
if [ -f "$LEARNED" ] && ! grep -Fq '<!-- FASTBRAIN_BRIDGE_BEGIN -->' "$LEARNED"; then
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

echo "Installed in $HOME_DIR (existing DB/env/router/model data preserved)"
echo "Run: $HOME_DIR/fastbrain doctor"
