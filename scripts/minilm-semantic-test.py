#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import time
from pathlib import Path

TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


class WordPieceTokenizer:
    def __init__(self, vocab_path: Path, max_length: int = 128):
        self.vocab = {}
        for i, token in enumerate(vocab_path.read_text(encoding="utf-8").splitlines()):
            self.vocab[token] = i
        self.unk = self.vocab.get("[UNK]", 100)
        self.cls = self.vocab.get("[CLS]", 101)
        self.sep = self.vocab.get("[SEP]", 102)
        self.pad = self.vocab.get("[PAD]", 0)
        self.max_length = max_length

    def _wordpiece(self, token: str):
        if token in self.vocab:
            return [self.vocab[token]]
        if len(token) > 100:
            return [self.unk]
        pieces = []
        start = 0
        while start < len(token):
            end = len(token)
            found = None
            while start < end:
                piece = token[start:end]
                if start:
                    piece = "##" + piece
                if piece in self.vocab:
                    found = self.vocab[piece]
                    break
                end -= 1
            if found is None:
                return [self.unk]
            pieces.append(found)
            start = end
        return pieces

    def encode(self, text: str):
        ids = [self.cls]
        for tok in TOKEN_RE.findall(text.lower()):
            ids.extend(self._wordpiece(tok))
            if len(ids) >= self.max_length - 1:
                break
        ids.append(self.sep)
        mask = [1] * len(ids)
        while len(ids) < self.max_length:
            ids.append(self.pad)
            mask.append(0)
        return ids[: self.max_length], mask[: self.max_length]


def load_skills(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for skill in data:
        sid = skill.get("id")
        if not sid or sid == "normal_hermes":
            continue
        for ex in skill.get("examples", []):
            if isinstance(ex, str) and ex.strip():
                rows.append((sid, ex.strip()))
    return rows


class MiniLM:
    def __init__(self, model_path: Path, vocab_path: Path):
        import numpy as np
        import onnxruntime as ort

        self.np = np
        self.tokenizer = WordPieceTokenizer(vocab_path)
        self.session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        self.input_names = {x.name for x in self.session.get_inputs()}

    def embed(self, texts):
        np = self.np
        enc = [self.tokenizer.encode(t) for t in texts]
        ids = np.asarray([x[0] for x in enc], dtype=np.int64)
        mask = np.asarray([x[1] for x in enc], dtype=np.int64)
        feeds = {}
        if "input_ids" in self.input_names:
            feeds["input_ids"] = ids
        if "attention_mask" in self.input_names:
            feeds["attention_mask"] = mask
        if "token_type_ids" in self.input_names:
            feeds["token_type_ids"] = np.zeros_like(ids)
        output = self.session.run(None, feeds)[0]
        weights = mask[..., None].astype(np.float32)
        pooled = (output * weights).sum(axis=1) / np.clip(weights.sum(axis=1), 1e-9, None)
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        pooled = pooled / np.clip(norms, 1e-9, None)
        return pooled.astype(np.float32)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--vocab", required=True)
    p.add_argument("--skills", required=True)
    p.add_argument("texts", nargs="*")
    args = p.parse_args()

    model_path = Path(args.model).expanduser()
    vocab_path = Path(args.vocab).expanduser()
    skills_path = Path(args.skills).expanduser()
    examples = load_skills(skills_path)
    if not examples:
        raise SystemExit("No skill examples found")

    started = time.perf_counter()
    model = MiniLM(model_path, vocab_path)
    load_ms = (time.perf_counter() - started) * 1000

    ex_texts = [x[1] for x in examples]
    started = time.perf_counter()
    ex_vecs = model.embed(ex_texts)
    index_ms = (time.perf_counter() - started) * 1000

    tests = args.texts or [
        "show me my power situation",
        "how much juice does my phone have",
        "get me into telegram somehow",
        "take me to whatsapp",
        "put on something that suits this moment",
        "continue what was playing",
    ]

    print(json.dumps({"model_load_ms": load_ms, "index_build_ms": index_ms, "examples": len(examples)}, indent=2))
    for text in tests:
        started = time.perf_counter()
        q = model.embed([text])[0]
        scores = ex_vecs @ q
        best_by_skill = {}
        best_example = {}
        for i, (skill, example) in enumerate(examples):
            score = float(scores[i])
            if score > best_by_skill.get(skill, -1.0):
                best_by_skill[skill] = score
                best_example[skill] = example
        ranked = sorted(best_by_skill.items(), key=lambda kv: kv[1], reverse=True)
        latency = (time.perf_counter() - started) * 1000
        best_skill, best_score = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else -1.0
        print(json.dumps({
            "text": text,
            "skill": best_skill,
            "similarity": best_score,
            "margin": best_score - second,
            "matched_example": best_example[best_skill],
            "latency_ms": latency,
            "top3": [{"skill": s, "score": sc} for s, sc in ranked[:3]],
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
