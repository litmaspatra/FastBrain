#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOME_DIR="${FASTBRAIN_HOME:-$HOME/.fastbrain}"
PY="${FASTBRAIN_PYTHON:-python3.13}"
ROUTER_SOCKET="${FASTBRAIN_ROUTER_SOCKET:-$HOME_DIR/router/router.sock}"

if [ ! -d "$ROOT/.git" ]; then
  echo "This repo is not a git checkout. Run the installer from the repo root." >&2
  exit 2
fi

cd "$ROOT"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Updating repository from git..."
  git pull --ff-only || { echo "git pull failed; leaving local runtime state intact." >&2; exit 3; }
else
  echo "No git metadata found; continuing with local files only." >&2
fi

bash "$ROOT/scripts/install-termux.sh"

# Keep the live router running if it was already started. This avoids a full setup reset.
if [ -f "$HOME_DIR/router/router.pid" ] && kill -0 "$(cat "$HOME_DIR/router/router.pid" 2>/dev/null || true)" 2>/dev/null; then
  echo "Restarting FastBrain router service..."
  bash "$ROOT/scripts/start-fastbrain-router.sh" || true
else
  echo "No active FastBrain router found; start it later with: bash $ROOT/scripts/start-fastbrain-router.sh"
fi

printf '\nFastBrain update complete.\n'
printf 'Environment preserved: %s\n' "$HOME_DIR"
printf 'DB preserved: %s\n' "${FASTBRAIN_DB:-$HOME_DIR/fastbrain.db}"
printf 'Run: %s/fastbrain doctor\n' "$HOME_DIR"
