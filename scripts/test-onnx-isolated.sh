#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY=""
for c in "${FASTBRAIN_PYTHON:-}" python3.13 python3.14 python3; do
  [ -n "$c" ] || continue; p="$(command -v "$c" 2>/dev/null)" || continue
  "$p" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 13) else 1)' 2>/dev/null && { PY="$p"; break; }
done
VENV="${FASTBRAIN_ONNX_TEST_HOME:-$HOME/.fastbrain-onnx-test}"
TRAINING="${1:-$HOME/.fastbrain/fastbrain-training.jsonl}"
OUT="$VENV/model"

[ -n "$PY" ] || { echo "ERROR: Python 3.13+ is required"; exit 2; }
[ -f "$TRAINING" ] || { echo "ERROR: training file not found: $TRAINING"; exit 2; }

# We deliberately reuse Termux's already-working packaged NumPy via
# --system-site-packages. The venv itself remains isolated under ~/.fastbrain-onnx-test.
# Nothing is installed into system Python.
mkdir -p "$VENV"
if [ -d "$VENV/venv" ]; then
  rm -rf "$VENV/venv"
fi
"$PY" -m venv --system-site-packages "$VENV/venv"

PIP="$VENV/venv/bin/pip"
VPY="$VENV/venv/bin/python"

if ! "$VPY" - <<'PY' >/dev/null 2>&1
import numpy
print(numpy.__version__)
PY
then
  cat <<EOF
ONNX_TEST_UNAVAILABLE
The isolated Python venv could not see the existing Termux NumPy package.
Nothing outside $VENV was changed.
EOF
  exit 4
fi

# Install only the ONNX-specific pieces in the isolated venv. Do not ask pip for
# NumPy, because PyPI does not provide an Android/Bionic wheel for this platform.
"$PIP" install --upgrade pip >/dev/null
set +e
"$PIP" install --only-binary=:all: onnx onnxruntime
INSTALL_RC=$?
set -e
if [ "$INSTALL_RC" -ne 0 ]; then
  cat <<EOF
ONNX_TEST_UNAVAILABLE
Termux NumPy is visible, but pip could not install a binary onnx/onnxruntime stack for Android/Bionic.
This is now an ONNX platform-availability result rather than a NumPy failure.
Nothing outside $VENV was changed.
EOF
  exit 4
fi

rm -rf "$OUT"
mkdir -p "$OUT"
"$VPY" "$ROOT/scripts/train-semantic.py" "$TRAINING" --output-dir "$OUT"

"$VPY" - "$OUT/semantic.onnx" "$OUT/labels.json" "$TRAINING" <<'PY'
import hashlib,json,re,sys,time
from collections import Counter
from pathlib import Path
import numpy as np
import onnxruntime as ort

model=Path(sys.argv[1]); labels_path=Path(sys.argv[2]); data_path=Path(sys.argv[3])
labels=json.loads(labels_path.read_text())['labels']
TOKEN_RE=re.compile(r"[\w']+",re.UNICODE)
def norm(s): return ' '.join(TOKEN_RE.findall(s.lower()))
def feats(s):
    t=norm(s); c=Counter(t.split()); compact=t.replace(' ','')
    for n in (3,4):
        for i in range(max(0,len(compact)-n+1)): c['#'+compact[i:i+n]] += .18
    return c
def vec(text,dim=2048):
    v=np.zeros((1,dim),dtype='float32')
    for k,val in feats(text).items():
        idx=int.from_bytes(hashlib.blake2b(k.encode(),digest_size=8).digest(),'little')%dim
        v[0,idx]+=float(val)
    n=float(np.linalg.norm(v))
    if n: v/=n
    return v
rows=[]
for line in data_path.read_text(encoding='utf-8').splitlines():
    if not line.strip(): continue
    r=json.loads(line)
    if r.get('text') and r.get('skill'): rows.append((r['text'],r['skill']))
sess=ort.InferenceSession(str(model),providers=['CPUExecutionProvider'])
inp=sess.get_inputs()[0].name
ok=0; times=[]
for text,skill in rows:
    st=time.perf_counter(); out=sess.run(None,{inp:vec(text)})[0][0]; times.append((time.perf_counter()-st)*1000)
    pred=labels[int(np.argmax(out))]
    ok += pred==skill
acc=ok/len(rows) if rows else 0
print(json.dumps({
  'ok': True,
  'backend': 'onnxruntime',
  'examples': len(rows),
  'accuracy_on_export_set': acc,
  'median_inference_ms': float(np.median(times)) if times else None,
  'p95_inference_ms': float(np.percentile(times,95)) if times else None,
  'model': str(model),
  'labels': str(labels_path),
},indent=2))
PY

cat <<EOF
ONNX_TEST_OK
Isolated test home: $VENV
Model: $OUT/semantic.onnx
Labels: $OUT/labels.json
Nothing has been enabled in working FastBrain yet.
EOF
