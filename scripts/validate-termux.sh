#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
FB="${FASTBRAIN_HOME:-$HOME/.fastbrain}/fastbrain"
[ -x "$FB" ] || { echo "FastBrain not installed"; exit 2; }
"$FB" doctor
"$FB" cache-put alias govind butagorira --scope communication
"$FB" route --dry-run "call Govind"
"$FB" route "open WhatsApp"
"$FB" route "play something"
"$FB" route "explain quantum computing"
"$FB" benchmark-memory --iterations 30
