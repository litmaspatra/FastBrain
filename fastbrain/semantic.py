from __future__ import annotations
import math, re
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
    """Small dependency-free semantic scorer. Replaceable by an ONNX backend later."""
    def __init__(self, registry): self.registry=registry
    def route(self,text:str):
        q=features(text); domain_scores={}
        for domain in self.registry.domains():
            examples=[x for s in self.registry.all() if s.get('category')==domain for x in s.get('examples',[])]
            domain_scores[domain]=max([cosine(q,features(x)) for x in examples] or [0.0])
        domain=max(domain_scores,key=domain_scores.get) if domain_scores else 'unknown'
        opts=[s['id'] for s in self.registry.all() if s.get('category')==domain]
        return domain,self.choice(text,opts),domain_scores
    def choice(self,text:str, options:list[str]|None=None)->Decision:
        candidates=[s for s in self.registry.all() if not options or s['id'] in options]
        q=features(text); scores={}
        for s in candidates:
            sims=[cosine(q,features(x)) for x in s.get('examples',[])]
            scores[s['id']]=max(sims or [0.0])
        if not scores:return Decision('normal_hermes',0,{})
        best=max(scores,key=scores.get); raw=scores[best]
        conf=max(0.0,min(0.99,0.48+0.55*raw))
        return Decision(best,conf,scores)
    def boolean(self,text:str,positive:list[str],negative:list[str])->dict:
        q=features(text); p=max([cosine(q,features(x)) for x in positive] or [0]); n=max([cosine(q,features(x)) for x in negative] or [0]); den=p+n+1e-9
        yes=.5 if p==n==0 else p/den; return {'yes':yes,'no':1-yes}
    def score(self,value:float, low=0, high=4): return max(low,min(high,round(value)))
