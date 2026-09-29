#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,math,re,sys,time
from collections import Counter
from pathlib import Path

TOKEN_RE=re.compile(r"[\w']+",re.UNICODE)

def features(s):
    t=' '.join(TOKEN_RE.findall(s.lower())); c=Counter(t.split()); compact=t.replace(' ','')
    for n in (3,4):
        for i in range(max(0,len(compact)-n+1)):
            c['#'+compact[i:i+n]] += .18
    return c

def vector(text,dim):
    import numpy as np
    v=np.zeros((1,dim),dtype='float32')
    for key,val in features(text).items():
        idx=int.from_bytes(hashlib.blake2b(key.encode('utf-8'),digest_size=8).digest(),'little')%dim
        v[0,idx]+=float(val)
    n=float(np.linalg.norm(v))
    if n:v/=n
    return v

def softmax(vals):
    m=max(vals); ex=[math.exp(float(x)-m) for x in vals]; total=sum(ex) or 1.0
    return [x/total for x in ex]

def main():
    if len(sys.argv)<4:
        print(json.dumps({'ok':False,'error':'usage: helper MODEL LABELS TEXT'})); return 2
    model=Path(sys.argv[1]); labels_path=Path(sys.argv[2]); text=' '.join(sys.argv[3:])
    try:
        import onnxruntime as ort
        labels_obj=json.loads(labels_path.read_text(encoding='utf-8'))
        labels=labels_obj.get('labels',labels_obj) if isinstance(labels_obj,dict) else labels_obj
        dim=2048
        sess=ort.InferenceSession(str(model),providers=['CPUExecutionProvider'])
        inp=sess.get_inputs()[0]
        if len(inp.shape)>=2 and isinstance(inp.shape[1],int):dim=int(inp.shape[1])
        started=time.perf_counter(); out=sess.run(None,{inp.name:vector(text,dim)})[0][0]
        probs=softmax(out.tolist() if hasattr(out,'tolist') else list(out))
        scores={labels[i]:float(probs[i]) for i in range(min(len(labels),len(probs)))}
        best=max(scores,key=scores.get)
        print(json.dumps({'ok':True,'skill':best,'confidence':scores[best],'scores':scores,'latency_ms':(time.perf_counter()-started)*1000}))
        return 0
    except Exception as exc:
        print(json.dumps({'ok':False,'error':f'{type(exc).__name__}: {exc}'})); return 3

if __name__=='__main__': raise SystemExit(main())
