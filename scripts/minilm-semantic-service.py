#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import socket
import time
from pathlib import Path

TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)


class WordPieceTokenizer:
    def __init__(self, vocab_path: Path, max_length: int = 128):
        self.vocab = {token: i for i, token in enumerate(vocab_path.read_text(encoding="utf-8").splitlines())}
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
        for token in TOKEN_RE.findall(text.lower()):
            ids.extend(self._wordpiece(token))
            if len(ids) >= self.max_length - 1:
                break
        ids.append(self.sep)
        mask = [1] * len(ids)
        while len(ids) < self.max_length:
            ids.append(self.pad)
            mask.append(0)
        return ids[: self.max_length], mask[: self.max_length]


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
        encoded = [self.tokenizer.encode(t) for t in texts]
        ids = np.asarray([x[0] for x in encoded], dtype=np.int64)
        mask = np.asarray([x[1] for x in encoded], dtype=np.int64)
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
        pooled /= np.clip(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-9, None)
        return pooled.astype(np.float32)


def load_examples(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for skill in data:
        sid = skill.get("id")
        if not sid or sid == "normal_hermes":
            continue
        for example in skill.get("examples", []):
            if isinstance(example, str) and example.strip():
                rows.append((sid, example.strip()))
    return rows


class SemanticIndex:
    def __init__(self, model: MiniLM, skills_path: Path):
        self.model = model
        self.skills_path = skills_path
        self.reload()

    def reload(self):
        self.examples = load_examples(self.skills_path)
        if not self.examples:
            raise RuntimeError("no skill examples found")
        self.vectors = self.model.embed([x[1] for x in self.examples])

    def query(self, text: str, options=None):
        started = time.perf_counter()
        q = self.model.embed([text])[0]
        raw = self.vectors @ q
        allowed = set(options or [])
        scores = {}
        matched = {}
        for i, (skill, example) in enumerate(self.examples):
            if allowed and skill not in allowed:
                continue
            score = float(raw[i])
            if score > scores.get(skill, -2.0):
                scores[skill] = score
                matched[skill] = example
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        if not ranked:
            return {"ok": False, "error": "no_candidates"}
        best_skill, best_score = ranked[0]
        second = ranked[1][1] if len(ranked) > 1 else -1.0
        return {
            "ok": True,
            "skill": best_skill,
            "similarity": best_score,
            "margin": best_score - second,
            "scores": scores,
            "matched_example": matched.get(best_skill),
            "latency_ms": (time.perf_counter() - started) * 1000,
        }


def recv_json(conn):
    chunks = []
    while True:
        part = conn.recv(65536)
        if not part:
            break
        chunks.append(part)
        if b"\n" in part:
            break
    raw = b"".join(chunks).split(b"\n", 1)[0]
    return json.loads(raw.decode("utf-8"))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--vocab", required=True)
    p.add_argument("--skills", required=True)
    p.add_argument("--socket", required=True)
    args = p.parse_args()

    model_path = Path(args.model).expanduser()
    vocab_path = Path(args.vocab).expanduser()
    skills_path = Path(args.skills).expanduser()
    socket_path = Path(args.socket).expanduser()
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        socket_path.unlink()
    except FileNotFoundError:
        pass

    started = time.perf_counter()
    model = MiniLM(model_path, vocab_path)
    index = SemanticIndex(model, skills_path)
    startup_ms = (time.perf_counter() - started) * 1000

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    os.chmod(socket_path, 0o600)
    server.listen(8)
    print(json.dumps({"ready": True, "startup_ms": startup_ms, "examples": len(index.examples), "socket": str(socket_path)}), flush=True)

    try:
        while True:
            conn, _ = server.accept()
            with conn:
                try:
                    req = recv_json(conn)
                    if req.get("op") == "ping":
                        out = {"ok": True, "status": "ready", "examples": len(index.examples)}
                    elif req.get("op") == "reload":
                        index.reload()
                        out = {"ok": True, "status": "reloaded", "examples": len(index.examples)}
                    else:
                        text = str(req.get("text") or "").strip()
                        if not text:
                            out = {"ok": False, "error": "empty_text"}
                        else:
                            options = req.get("options")
                            out = index.query(text, options if isinstance(options, list) else None)
                except Exception as exc:
                    out = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
                conn.sendall((json.dumps(out, ensure_ascii=False) + "\n").encode("utf-8"))
    finally:
        server.close()
        try:
            socket_path.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
