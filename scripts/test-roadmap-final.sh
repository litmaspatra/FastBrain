#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
FB="${HOME}/.fastbrain/fastbrain"

if [ ! -x "$FB" ]; then
  echo "FastBrain binary not found at $FB" >&2
  exit 1
fi

run() {
  echo
  echo ">>> $1"
  "$FB" route "$1" --dry-run
}

run "message Govind I am late, then call him, then open Maps"
run "open Maps, do something clever there, then set volume to 25"
run "check battery and if it's below 20 open battery settings otherwise do nothing"
run "check battery and if it's charging set volume to 30 otherwise set volume to 20"
run "check wifi and if wifi is connected open Maps otherwise do nothing"
run "check battery and if it's below 20 open battery settings and set volume to 20"
run "check battery and if it's below 20 and not charging open battery settings otherwise do nothing"
run "check battery and if it's below 20 open Maps and do something clever there"

echo
echo "FINAL_DRY_RUNS_COMPLETE"
