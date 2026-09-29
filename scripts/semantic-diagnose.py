#!/usr/bin/env python3
from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastbrain.app import build


def minilm_raw(stack, text):
    cfg = stack['config']
    path = cfg.minilm_socket
    if not path or not path.exists():
        return {'available': False, 'reason': 'socket_missing', 'socket': str(path) if path else None}
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(float(cfg.minilm_timeout))
    try:
        client.connect(str(path))
        client.sendall((json.dumps({'text': text}) + '\n').encode('utf-8'))
        chunks = []
        while True:
            part = client.recv(65536)
            if not part:
                break
            chunks.append(part)
            if b'\n' in part:
                break
        data = json.loads(b''.join(chunks).split(b'\n', 1)[0].decode('utf-8') or '{}')
        data['available'] = True
        return data
    except Exception as exc:
        return {'available': False, 'reason': f'{type(exc).__name__}: {exc}', 'socket': str(path)}
    finally:
        client.close()


def main():
    if len(sys.argv) < 2:
        print('usage: semantic-diagnose.py <phrase>', file=sys.stderr)
        return 2
    text = ' '.join(sys.argv[1:])
    stack = build()
    engine = stack['engine']
    semantic = stack['semantic']
    cfg = stack['config']

    det_skill, det_conf = engine._deterministic(text)
    local = semantic._local_choice(text)
    mini = minilm_raw(stack, text)
    final = engine.route(text)

    ranked_local = sorted(local.scores.items(), key=lambda kv: kv[1], reverse=True)[:5]
    payload = {
        'text': text,
        'deterministic': {'skill': det_skill, 'confidence': det_conf} if det_skill else None,
        'local_semantic': {
            'skill': local.choice,
            'confidence': local.confidence,
            'top5_raw_similarity': [{'skill': k, 'score': v} for k, v in ranked_local],
            'local_first_threshold': semantic._local_first_threshold(),
        },
        'minilm': mini,
        'minilm_policy': {
            'min_similarity': cfg.minilm_min_similarity,
            'min_margin': cfg.minilm_min_margin,
            'timeout_seconds': cfg.minilm_timeout,
        },
        'final_route': final.to_dict(),
        'backend_status': semantic.status(),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
