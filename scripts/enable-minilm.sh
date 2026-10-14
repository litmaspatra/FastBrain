#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FB_HOME="${FASTBRAIN_HOME:-$HOME/.fastbrain}"
TEST_DIR="$HOME/.fastbrain-minilm-test"
SRC_MODEL="$TEST_DIR/model_qint8_arm64.onnx"
SRC_VOCAB="$TEST_DIR/vocab.txt"
DST_DIR="$FB_HOME/minilm"
ENV_FILE="$FB_HOME/fastbrain.env"
START="$FB_HOME/bin/start-minilm"

[ -f "$SRC_MODEL" ] || { echo "MINILM_ENABLE_ERROR missing $SRC_MODEL; run bash scripts/test-minilm-isolated.sh first"; exit 2; }
[ -f "$SRC_VOCAB" ] || { echo "MINILM_ENABLE_ERROR missing $SRC_VOCAB; run bash scripts/test-minilm-isolated.sh first"; exit 2; }
[ -x "$START" ] || { echo "MINILM_ENABLE_ERROR missing $START; run bash scripts/install-termux.sh first"; exit 2; }

mkdir -p "$DST_DIR"
cp "$SRC_MODEL" "$DST_DIR/model_qint8_arm64.onnx"
cp "$SRC_VOCAB" "$DST_DIR/vocab.txt"
chmod 600 "$DST_DIR/model_qint8_arm64.onnx" "$DST_DIR/vocab.txt"

[ -f "$ENV_FILE" ] || touch "$ENV_FILE"
TMP="$ENV_FILE.tmp.$$"
awk '
  $0=="# FASTBRAIN_MINILM_BEGIN" {skip=1; next}
  $0=="# FASTBRAIN_MINILM_END" {skip=0; next}
  !skip {print}
' "$ENV_FILE" > "$TMP"
cat >> "$TMP" <<'EOF'
# FASTBRAIN_MINILM_BEGIN
FASTBRAIN_SEMANTIC_BACKEND=minilm
FASTBRAIN_MINILM_SOCKET="$HOME/.fastbrain/minilm/minilm.sock"
FASTBRAIN_MINILM_TIMEOUT=0.20
FASTBRAIN_MINILM_MIN_SIMILARITY=0.45
FASTBRAIN_MINILM_MIN_MARGIN=0.10
# Disable the old per-request tiny ONNX helper while MiniLM is active.
FASTBRAIN_SEMANTIC_HELPER=""
# FASTBRAIN_MINILM_END
EOF
mv "$TMP" "$ENV_FILE"
chmod 600 "$ENV_FILE"

"$START"
echo "MINILM_ENABLED"
echo "Model: $DST_DIR/model_qint8_arm64.onnx"
echo "Socket: $FB_HOME/minilm/minilm.sock"
