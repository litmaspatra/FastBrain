#!/data/data/com.termux/files/usr/bin/bash
set -u

ROOT="$HOME/.fastbrain-minilm-test"
MODEL="$ROOT/model_qint8_arm64.onnx"
VOCAB="$ROOT/vocab.txt"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS="$REPO/skills/builtin.json"
PY=""
for c in "${FASTBRAIN_MINILM_PYTHON:-}" python3.14 python3.13 python3; do
  [ -n "$c" ] || continue; p="$(command -v "$c" 2>/dev/null)" || continue
  "$p" -c 'import numpy, onnxruntime' >/dev/null 2>&1 && { PY="$p"; break; }
done

mkdir -p "$ROOT"

if [ -z "$PY" ]; then
  echo "MINILM_TEST_UNAVAILABLE"
  echo "No python3 can import both numpy and onnxruntime. Nothing outside $ROOT was changed."
  exit 0
fi

fetch() {
  url="$1"
  out="$2"
  if [ -s "$out" ]; then return 0; fi
  tmp="$out.part"
  rm -f "$tmp"
  if command -v curl >/dev/null 2>&1; then
    curl -L --fail --retry 2 --connect-timeout 15 -o "$tmp" "$url" || return 1
  elif command -v wget >/dev/null 2>&1; then
    wget -O "$tmp" "$url" || return 1
  else
    return 1
  fi
  mv "$tmp" "$out"
}

MODEL_URL="https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/onnx/model_qint8_arm64.onnx?download=true"
VOCAB_URL="https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/main/vocab.txt?download=true"

if ! fetch "$MODEL_URL" "$MODEL"; then
  echo "MINILM_TEST_UNAVAILABLE"
  echo "Could not download ARM64 MiniLM ONNX model. Nothing outside $ROOT was changed."
  exit 0
fi
if ! fetch "$VOCAB_URL" "$VOCAB"; then
  echo "MINILM_TEST_UNAVAILABLE"
  echo "Could not download MiniLM vocab.txt. Nothing outside $ROOT was changed."
  exit 0
fi

printf 'Model: '; ls -lh "$MODEL" | awk '{print $5, $9}'
printf 'Vocab: '; ls -lh "$VOCAB" | awk '{print $5, $9}'

echo "--- MiniLM semantic benchmark ---"
"$PY" "$REPO/scripts/minilm-semantic-test.py" \
  --model "$MODEL" \
  --vocab "$VOCAB" \
  --skills "$SKILLS"
status=$?

if [ "$status" -eq 0 ]; then
  echo "MINILM_TEST_OK"
  echo "Nothing outside $ROOT was modified by this test."
else
  echo "MINILM_TEST_FAILED"
  echo "Nothing outside $ROOT was modified by this test."
fi
exit "$status"
