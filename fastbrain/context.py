from __future__ import annotations
import hashlib,json,math,re,shlex,socket,subprocess
from collections import Counter
from .models import Decision

TOKEN_RE=re.compile(r"[\w']+", re.UNICODE)
def norm(s:str)->str: return ' '.join(TOKEN_RE.findall(s.lower()))
def features(s:str):
    t=norm(s); toks=t.split(); c=Counter(toks); compact=t.replace(' ','')
    for n in (3,4):
        for i in range(max(0,len(compact)-n+1)): c['#'+compact[i:i+n]] += .18
    return c
def cosine(a,b):
    if not a or not b:return 0.0
    dot=sum(v*b.get(k,0) for k,v in a.items()); na=math.sqrt(sum(v*v for v in a.values())); nb=math.sqrt(sum(v*v for v in b.values()))
    return dot/(na*nb) if na and nb else 0.0

class SemanticEngine:
    """Fast local scorer with persistent MiniLM for genuinely ambiguous text."""
    def __init__(self, registry, cfg=None):
        self.registry=registry; self.cfg=cfg; self.session=None; self.labels=[]; self.onnx_error=''
        self.helper=getattr(cfg,'semantic_helper','') if cfg is not None else ''
        self.minilm_socket=getattr(cfg,'minilm_socket',None) if cfg is not None else None
        requested=getattr(cfg,'semantic_backend','auto') if cfg is not None else 'auto'
        self.backend='ngram'
        if requested=='minilm':
            self.backend='minilm_socket'
        elif requested in {'auto','onnx'}:
            if requested=='auto' and self.minilm_socket and self.minilm_socket.exists():
                self.backend='minilm_socket'
            elif self.helper:
                self.backend='onnx_helper'
            else:
                self._try_onnx()

    def _threshold(self): return float(getattr(self.cfg,'semantic_min_confidence',0.75) or 0.75)
    def _local_first_threshold(self): return 0.90
    def _minilm_similarity(self): return float(getattr(self.cfg,'minilm_min_similarity',0.45) or 0.45)
    def _minilm_margin(self): return float(getattr(self.cfg,'minilm_min_margin',0.10) or 0.10)

    def _try_onnx(self):
        model=getattr(self.cfg,'semantic_model',None); labels=getattr(self.cfg,'semantic_labels',None)
        if not model or not labels or not model.is_file() or not labels.is_file():
            self.onnx_error='model_or_labels_missing'; return
        try:
            import onnxruntime as ort
            loaded=json.loads(labels.read_text(encoding='utf-8'))
            if isinstance(loaded,dict): loaded=loaded.get('labels',[])
            if not isinstance(loaded,list) or not all(isinstance(x,str) for x in loaded): raise ValueError('invalid labels file')
            self.session=ort.InferenceSession(str(model),providers=['CPUExecutionProvider'])
            self.labels=loaded; self.backend='onnx'
        except Exception as exc:
            self.onnx_error=f'{type(exc).__name__}: {exc}'; self.session=None; self.labels=[]; self.backend='ngram'

    def status(self):
        return {
            'backend':self.backend,
            'onnx_ready':bool(self.session is not None or self.helper),
            'minilm_ready':bool(self.minilm_socket and self.minilm_socket.exists()),
            'minilm_socket':str(self.minilm_socket) if self.minilm_socket else None,
            'minilm_min_similarity':self._minilm_similarity(),
            'minilm_min_margin':self._minilm_margin(),
            'labels':len(self.labels),'helper':self.helper or None,
            'min_confidence':self._threshold(),'local_first_threshold':self._local_first_threshold(),
            'error':self.onnx_error or None,
        }

    def _vector(self,text):
        import numpy as np
        dim=int(getattr(self.cfg,'semantic_dim',2048) or 2048); vec=np.zeros((1,dim),dtype='float32')
        for key,value in features(text).items():
            digest=hashlib.blake2b(key.encode('utf-8'),digest_size=8).digest(); idx=int.from_bytes(digest,'little')%dim
            vec[0,idx]+=float(value)
        n=float(np.linalg.norm(vec))
        if n: vec/=n
        return vec

    @staticmethod
    def _softmax(values):
        m=max(values); ex=[math.exp(float(x)-m) for x in values]; total=sum(ex) or 1.0
        return [x/total for x in ex]

    def _local_choice(self,text,options=None):
        candidates=[s for s in self.registry.all() if not options or s['id'] in options]
        q=features(text); scores={}
        for s in candidates:
            sims=[cosine(q,features(x)) for x in s.get('examples',[])]
            scores[s['id']]=max(sims or [0.0])
        if not scores:return Decision('normal_hermes',0,{})
        best=max(scores,key=scores.get); raw=scores[best]
        conf=max(0.0,min(0.99,0.48+0.55*raw))
        return Decision(best,conf,scores)

    def _minilm_choice(self,text,options=None):
        path=self.minilm_socket
        if not path or not path.exists(): return None
        try:
            req={'text':text}
            if options: req['options']=list(options)
            client=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            timeout = self.cfg.minilm_timeout_fast if getattr(self.cfg, "adaptive_minilm", True) else self.cfg.minilm_timeout
            client.settimeout(float(timeout))
            try:
                client.connect(str(path)); client.sendall((json.dumps(req)+'\n').encode('utf-8'))
                chunks=[]
                while True:
                    part=client.recv(65536)
                    if not part: break
                    chunks.append(part)
                    if b'\n' in part: break
            finally:
                client.close()
            data=json.loads(b''.join(chunks).split(b'\n',1)[0].decode('utf-8'))
            if not data.get('ok'): return None
            scores={k:float(v) for k,v in (data.get('scores') or {}).items() if self.registry.get(k) and (not options or k in options)}
            if not scores:return None
            ranked=sorted(scores.items(),key=lambda kv:kv[1],reverse=True)
            best,similarity=ranked[0]; second=ranked[1][1] if len(ranked)>1 else -1.0; margin=similarity-second
            if similarity < self._minilm_similarity() or margin < self._minilm_margin(): return None
            conf=min(.97,.91 + min(.04,max(0.0,similarity-self._minilm_similarity())*.10) + min(.02,margin*.05))
            return Decision(best,conf,scores)
        except Exception as exc:
            self.onnx_error=f'minilm {type(exc).__name__}: {exc}'; return None

    def _helper_choice(self,text,options=None):
        if not self.helper:return None
        try:
            proc=subprocess.run(shlex.split(self.helper)+[text],capture_output=True,text=True,timeout=float(getattr(self.cfg,'semantic_helper_timeout',0.35) or 0.35))
            if proc.returncode!=0:return None
            data=json.loads(proc.stdout or '{}')
            if not data.get('ok'):return None
            scores={k:float(v) for k,v in (data.get('scores') or {}).items() if self.registry.get(k) and (not options or k in options)}
            if not scores:return None
            best=max(scores,key=scores.get); confidence=float(scores[best])
            if confidence < self._threshold():return None
            return Decision(best,min(.99,max(0.0,confidence)),scores)
        except Exception as exc:
            self.onnx_error=f'helper {type(exc).__name__}: {exc}'; return None

    def _onnx_choice(self,text,options=None):
        if self.backend=='minilm_socket':
            return self._minilm_choice(text,options)
        helper=self._helper_choice(text,options)
        if helper is not None:return helper
        if self.session is None:return None
        try:
            inp=self.session.get_inputs()[0].name; out=self.session.run(None,{inp:self._vector(text)})[0]
            vals=out[0].tolist() if hasattr(out[0],'tolist') else list(out[0]); probs=self._softmax(vals)
            scores={label:float(probs[i]) for i,label in enumerate(self.labels[:len(probs)]) if (not options or label in options) and self.registry.get(label)}
            if not scores:return None
            best=max(scores,key=scores.get); confidence=float(scores[best])
            if confidence < self._threshold():return None
            return Decision(best,min(.99,max(0.0,confidence)),scores)
        except Exception as exc:
            self.onnx_error=f'{type(exc).__name__}: {exc}'; return None

    def route(self,text:str):
        q=features(text); domain_scores={}
        for domain in self.registry.domains():
            examples=[x for s in self.registry.all() if s.get('category')==domain for x in s.get('examples',[])]
            domain_scores[domain]=max([cosine(q,features(x)) for x in examples] or [0.0])
        domain=max(domain_scores,key=domain_scores.get) if domain_scores else 'unknown'
        opts=[s['id'] for s in self.registry.all() if s.get('category')==domain]
        local=self._local_choice(text,opts)
        if local.confidence >= self._local_first_threshold(): return domain,local,domain_scores
        semantic=self._onnx_choice(text)
        if semantic is not None:
            skill=self.registry.get(semantic.choice); sem_domain=skill.get('category','unknown') if skill else 'unknown'
            return sem_domain,semantic,{sem_domain:semantic.confidence}
        return domain,local,domain_scores

    def choice(self,text:str, options:list[str]|None=None)->Decision:
        local=self._local_choice(text,options)
        if local.confidence >= self._local_first_threshold():return local
        semantic=self._onnx_choice(text,options)
        return semantic if semantic is not None else local

    def boolean(self,text:str,positive:list[str],negative:list[str])->dict:
        q=features(text); p=max([cosine(q,features(x)) for x in positive] or [0]); n=max([cosine(q,features(x)) for x in negative] or [0]); den=p+n+1e-9
        yes=.5 if p==n==0 else p/den; return {'yes':yes,'no':1-yes}
    def score(self,value:float, low=0, high=4): return max(low,min(high,round(value)))
