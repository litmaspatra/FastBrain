#!/data/data/com.termux/files/usr/bin/bash
# git pull + reinstall + restart whatever services were already running.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOME_DIR="${FASTBRAIN_HOME:-$HOME/.fastbrain}"

running() { [ -f "$1" ] && kill -0 "$(cat "$1" 2>/dev/null || true)" 2>/dev/null; }

cd "$ROOT"
if [ -d "$ROOT/.git" ]; then
  echo "Updating repository from git..."
  git pull --ff-only || { echo "git pull failed; installed copy left untouched." >&2; exit 3; }
else
  echo "Not a git checkout; installing the files that are here." >&2
fi

bash "$ROOT/scripts/install-termux.sh"

# Services keep running the old code until restarted, so restart the ones that were up.
if running "$HOME_DIR/router/router.pid"; then
  echo "Restarting FastBrain router..."
  bash "$ROOT/scripts/start-fastbrain-router.sh" || true
else
  echo "Router not running; start it with: bash $ROOT/scripts/start-fastbrain-router.sh"
fi
if running "$HOME_DIR/minilm/minilm.pid"; then
  echo "Restarting MiniLM service..."
  "$HOME_DIR/bin/stop-minilm" || true
  "$HOME_DIR/bin/start-minilm" || true
fi

printf '\nFastBrain update complete.\nEnv/DB/models preserved in %s\nRun: %s/fastbrain doctor\n' "$HOME_DIR" "$HOME_DIR"
