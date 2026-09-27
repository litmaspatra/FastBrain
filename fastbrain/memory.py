from __future__ import annotations
import json, shlex, subprocess, time, urllib.request

class MemoryBridge:
    """Hindsight bridge supporting hot cache, direct HTTP/command lookup, or hybrid."""
    def __init__(self, db, cfg): self.db=db; self.cfg=cfg
    def project(self,m): self.db.upsert_hot(m)
    def lookup_hot(self,typ,subject,scope=''):
        r=self.db.hot_get(typ,subject,scope)
        if r:r['_source']='hot'
        return r
    def lookup_direct(self,typ,subject,scope=''):
        payload={'type':typ,'subject':subject,'scope':scope,'query':f'{typ} {subject} {scope}'.strip(),'fastbrain':True}
        start=time.perf_counter()
        try:
            if self.cfg.hindsight_cmd:
                p=subprocess.run(shlex.split(self.cfg.hindsight_cmd),input=json.dumps(payload),text=True,capture_output=True,timeout=self.cfg.direct_timeout)
                if p.returncode: return None
                data=json.loads(p.stdout or '{}')
            elif self.cfg.hindsight_url:
                req=urllib.request.Request(self.cfg.hindsight_url+self.cfg.hindsight_path,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'},method='POST')
                with urllib.request.urlopen(req,timeout=self.cfg.direct_timeout) as r:data=json.loads(r.read().decode())
            else:return None
            if isinstance(data,dict) and 'result' in data and isinstance(data['result'],dict): data=data['result']
            elif isinstance(data,dict) and data.get('memories'): data=data['memories'][0]
            if not isinstance(data,dict):return None
            if 'value' not in data:
                value=data.get('fact') or data.get('content')
                if value is None:return None
                data={'type':typ,'subject':subject,'scope':scope,'value':value,'confidence':data.get('confidence',.8)}
            data['_source']='direct'; data['_latency_ms']=(time.perf_counter()-start)*1000
            return data
        except Exception:return None
    def lookup(self,typ,subject,scope=''):
        mode=self.cfg.memory_mode
        if mode in {'hot','hybrid'}:
            r=self.lookup_hot(typ,subject,scope)
            if r:return r
        if mode in {'direct','hybrid'}:
            r=self.lookup_direct(typ,subject,scope)
            if r and mode=='hybrid':
                try:self.project({k:r[k] for k in ('type','subject','value') if k in r}|{'scope':r.get('scope',scope),'confidence':r.get('confidence',.8),'priority':r.get('priority',50)})
                except Exception:pass
            return r
        return None
