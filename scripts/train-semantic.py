#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from collections import Counter

TOKEN_RE = re.compile(r"[\w']+", re.UNICODE)


def norm(s: str) -> str:
    return " ".join(TOKEN_RE.findall(s.lower()))


def features(s: str):
    t = norm(s)
    toks = t.split()
    c = Counter(toks)
    compact = t.replace(" ", "")
    for n in (3, 4):
        for i in range(max(0, len(compact) - n + 1)):
            c["#" + compact[i : i + n]] += 0.18
    return c


def vector(text: str, dim: int):
    import numpy as np

    v = np.zeros(dim, dtype="float32")
    for key, value in features(text).items():
        digest = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(digest, "little") % dim
        v[idx] += float(value)
    n = float(np.linalg.norm(v))
    if n:
        v /= n
    return v


def load_rows(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            text = str(row.get("text") or "").strip()
            skill = str(row.get("skill") or "").strip()
            if not text or not skill:
                continue
            weight = float(row.get("weight", 1.0) or 1.0)
            rows.append((text, skill, max(0.05, min(weight, 5.0))))
    if not rows:
        raise SystemExit("No labelled training examples found.")
    return rows


def train(rows, dim: int, epochs: int, lr: float, l2: float, seed: int):
    import numpy as np

    labels = sorted({skill for _, skill, _ in rows})
    label_to_idx = {label: i for i, label in enumerate(labels)}
    x = np.stack([vector(text, dim) for text, _, _ in rows]).astype("float32")
    y = np.array([label_to_idx[skill] for _, skill, _ in rows], dtype="int64")
    sample_w = np.array([weight for _, _, weight in rows], dtype="float32")

    rng = np.random.default_rng(seed)
    w = rng.normal(0, 0.01, size=(dim, len(labels))).astype("float32")
    b = np.zeros(len(labels), dtype="float32")

    for epoch in range(epochs):
        logits = x @ w + b
        logits -= logits.max(axis=1, keepdims=True)
        exp = np.exp(logits)
        probs = exp / exp.sum(axis=1, keepdims=True)
        probs[np.arange(len(y)), y] -= 1.0
        probs *= sample_w[:, None]
        denom = float(sample_w.sum()) or 1.0
        grad_w = (x.T @ probs) / denom + l2 * w
        grad_b = probs.sum(axis=0) / denom
        w -= lr * grad_w
        b -= lr * grad_b

    logits = x @ w + b
    pred = logits.argmax(axis=1)
    acc = float((pred == y).mean())
    return labels, w, b, acc


def export_onnx(model_path: Path, weights, bias, dim: int):
    try:
        import onnx
        from onnx import TensorProto, helper, numpy_helper
    except Exception as exc:
        raise RuntimeError("onnx package is required only for export") from exc

    inp = helper.make_tensor_value_info("input", TensorProto.FLOAT, [None, dim])
    out = helper.make_tensor_value_info("logits", TensorProto.FLOAT, [None, int(bias.shape[0])])
    w_init = numpy_helper.from_array(weights.astype("float32"), name="W")
    b_init = numpy_helper.from_array(bias.astype("float32"), name="B")
    nodes = [
        helper.make_node("MatMul", ["input", "W"], ["mm"]),
        helper.make_node("Add", ["mm", "B"], ["logits"]),
    ]
    graph = helper.make_graph(nodes, "FastBrainSemantic", [inp], [out], [w_init, b_init])
    model = helper.make_model(graph, producer_name="fastbrain", opset_imports=[helper.make_opsetid("", 13)])
    onnx.checker.check_model(model)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, model_path)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("training_jsonl")
    p.add_argument("--output-dir", default="semantic-model")
    p.add_argument("--dim", type=int, default=2048)
    p.add_argument("--epochs", type=int, default=400)
    p.add_argument("--lr", type=float, default=0.35)
    p.add_argument("--l2", type=float, default=0.0005)
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()

    src = Path(args.training_jsonl).expanduser()
    out = Path(args.output_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    rows = load_rows(src)
    labels, weights, bias, train_acc = train(rows, args.dim, args.epochs, args.lr, args.l2, args.seed)

    labels_path = out / "labels.json"
    labels_path.write_text(json.dumps({"labels": labels}, indent=2), encoding="utf-8")
    meta = {
        "examples": len(rows),
        "labels": len(labels),
        "dim": args.dim,
        "epochs": args.epochs,
        "train_accuracy": train_acc,
        "feature_hash": "blake2b-64-mod-dim",
    }
    (out / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    model_path = out / "semantic.onnx"
    try:
        export_onnx(model_path, weights, bias, args.dim)
        exported = True
        error = None
    except Exception as exc:
        exported = False
        error = str(exc)

    print(json.dumps({
        "ok": exported,
        "training": meta,
        "model": str(model_path) if exported else None,
        "labels": str(labels_path),
        "export_error": error,
    }, indent=2))
    return 0 if exported else 3


if __name__ == "__main__":
    raise SystemExit(main())
