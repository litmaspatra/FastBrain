#!/usr/bin/env python3
from __future__ import annotations

import argparse,hashlib,json,os,re,socket,sqlite3,time
from collections import OrderedDict
from pathlib import Path

TOKEN_RE=re.compile(r"\w+|[^\w\s]",re.UNICODE)

class WordPieceTokenizer:
    def __init__(self,vocab_path:Path,max_length:int=128):
        self.vocab={t:i for i,t in enumerate(vocab_path.read_text(encoding='utf-8').splitlines())}
        self.unk=self.vocab.get('[UNK]',100);self.cls=self.vocab.get('[CLS]',101);self.sep=self.vocab.get('[SEP]',102);self.pad=self.vocab.get('[PAD]',0);self.max_length=max_length
    def _wordpiece(self,token:str):
        if token in self.vocab:return [self.vocab[token]]
        if len(token)>100:return [self.unk]
        out=[];start=0
        while start<len(token):
            end=len(token);found=None
            while start<end:
                piece=token[start:end];piece=('##'+piece) if start else piece
                if piece in self.vocab:found=self.vocab[piece];break
                end-=1
            if found is None:return [self.unk]
            out.append(found);start=end
        return out
    def encode(self,text:str):
        ids=[self.cls]
        for token in TOKEN_RE.findall(text.lower()):
            ids.extend(self._wordpiece(token))
            if len(ids)>=self.max_length-1:break
        ids.append(self.sep);mask=[1]*len(ids)
        while len(ids)<self.max_length:ids.append(self.pad);mask.append(0)
        return ids[:self.max_length],mask[:self.max_length]

class MiniLM:
    def __init__(self,model_path:Path,vocab_path:Path):
        import numpy as np,onnxruntime as ort
        self.np=np;self.tokenizer=WordPieceTokenizer(vocab_path);self.session=ort.InferenceSession(str(model_path),providers=['CPUExecutionProvider']);self.input_names={x.name for x in self.session.get_inputs()}
    def embed(self,texts):
        np=self.np;encoded=[self.tokenizer.encode(t) for t in texts]
        ids=np.asarray([x[0] for x in encoded],dtype=np.int64);mask=np.asarray([x[1] for x in encoded],dtype=np.int64);feeds={}
        if 'input_ids' in self.input_names:feeds['input_ids']=ids
        if 'attention_mask' in self.input_names:feeds['attention_mask']=mask
        if 'token_type_ids' in self.input_names:feeds['token_type_ids']=np.zeros_like(ids)
        output=self.session.run(None,feeds)[0];weights=mask[...,None].astype(np.float32);pooled=(output*weights).sum(axis=1)/np.clip(weights.sum(axis=1),1e-9,None);pooled/=np.clip(np.linalg.norm(pooled,axis=1,keepdims=True),1e-9,None);return pooled.astype(np.float32)

def _eligible_candidate(row):
    try:
        definition=json.loads(row['definition']);risk=definition.get('risk','low')
        return risk!='high' and row['successes']>=2 and row['score']>=0.8 and row['status'] in {'eligible','promoted'}
    except Exception:return False

def load_examples(skills_path:Path,db_path:Path):
    skills=json.loads(skills_path.read_text(encoding='utf-8')) if skills_path.exists() else []
    candidate_rows=[]
    if db_path.exists():
        try:
            con=sqlite3.connect(db_path);con.row_factory=sqlite3.Row
            for row in con.execute('SELECT definition FROM learned_skills WHERE enabled=1'):
                try:skills.append(json.loads(row['definition']))
                except Exception:pass
            candidate_rows=list(con.execute("SELECT id,phrase,definition,successes,score,status FROM learning_candidates WHERE status IN ('eligible','promoted')"))
            con.close()
        except Exception:pass
    rows=[];seen=set()
    for skill in skills:
        sid=skill.get('id')
        if not sid or sid=='normal_hermes':continue
        for ex in skill.get('examples',[]):
            if isinstance(ex,str) and ex.strip():
                key=(sid,ex.strip().lower())
                if key not in seen:rows.append((sid,ex.strip()));seen.add(key)
    for row in candidate_rows:
        if not _eligible_candidate(row):continue
        try:definition=json.loads(row['definition'])
        except Exception:continue
        sid=definition.get('id') or row['id'];phrase=str(row['phrase'] or '').strip()
        if not sid or sid=='normal_hermes' or not phrase:continue
        key=(sid,phrase.lower())
        if key not in seen:rows.append((sid,phrase));seen.add(key)
    return rows

def semantic_learning_fingerprint(db_path:Path):
    if not db_path.exists():return 'missing'
    try:
        con=sqlite3.connect(db_path);con.row_factory=sqlite3.Row
        learned=list(con.execute('SELECT enabled,definition FROM learned_skills ORDER BY rowid'))
        candidates=list(con.execute("SELECT id,phrase,definition,successes,score,status FROM learning_candidates WHERE status IN ('eligible','promoted') ORDER BY id"))
        con.close();h=hashlib.sha256()
        for row in learned:
            h.update(str(int(bool(row['enabled']))).encode('ascii'));h.update(b'\0');h.update(str(row['definition'] or '').encode('utf-8'));h.update(b'\0')
        for row in candidates:
            if not _eligible_candidate(row):continue
            for key in ('id','phrase','definition','successes','score','status'):
                h.update(str(row[key]).encode('utf-8'));h.update(b'\0')
        return h.hexdigest()
    except Exception as exc:return 'error:'+type(exc).__name__

class SemanticIndex:
    def __init__(self,model:MiniLM,skills_path:Path,db_path:Path,cache_size:int=256,check_interval:float=1.0):
        self.model=model;self.skills_path=skills_path;self.db_path=db_path;self.stamp=None
        self.cache=OrderedDict();self.cache_size=max(16,int(cache_size));self.check_interval=max(.1,float(check_interval));self.last_check=0.0
        self.reload()
    def _stamp(self):return (self.skills_path.stat().st_mtime_ns if self.skills_path.exists() else 0,semantic_learning_fingerprint(self.db_path))
    def reload(self):
        self.examples=load_examples(self.skills_path,self.db_path)
        if not self.examples:raise RuntimeError('no skill examples found')
        self.vectors=self.model.embed([x[1] for x in self.examples]);self.stamp=self._stamp();self.cache.clear();self.last_check=time.monotonic()
    def maybe_reload(self):
        now=time.monotonic()
        if now-self.last_check<self.check_interval:return False
        self.last_check=now
        if self._stamp()!=self.stamp:self.reload();return True
        return False
    @staticmethod
    def _cache_key(text,options):
        normalized=' '.join(str(text).lower().split());opts=tuple(sorted(str(x) for x in (options or [])))
        return normalized,opts
    def _cache_get(self,key):
        value=self.cache.get(key)
        if value is None:return None
        self.cache.move_to_end(key);return dict(value)
    def _cache_put(self,key,value):
        self.cache[key]=dict(value);self.cache.move_to_end(key)
        while len(self.cache)>self.cache_size:self.cache.popitem(last=False)
    def query(self,text:str,options=None):
        self.maybe_reload();key=self._cache_key(text,options);cached=self._cache_get(key)
        if cached is not None:
            cached['cache_hit']=True;cached['latency_ms']=0.0;return cached
        started=time.perf_counter();q=self.model.embed([text])[0];raw=self.vectors@q;allowed=set(options or []);scores={};matched={}
        for i,(skill,example) in enumerate(self.examples):
            if allowed and skill not in allowed:continue
            score=float(raw[i])
            if score>scores.get(skill,-2.0):scores[skill]=score;matched[skill]=example
        ranked=sorted(scores.items(),key=lambda kv:kv[1],reverse=True)
        if not ranked:return {'ok':False,'error':'no_candidates'}
        best_skill,best_score=ranked[0];second=ranked[1][1] if len(ranked)>1 else -1.0
        out={'ok':True,'skill':best_skill,'similarity':best_score,'margin':best_score-second,'scores':scores,'matched_example':matched.get(best_skill),'latency_ms':(time.perf_counter()-started)*1000,'cache_hit':False}
        self._cache_put(key,out);return out

def recv_json(conn):
    data=b''
    while b'\n' not in data and len(data)<131072:
        part=conn.recv(65536)
        if not part:break
        data+=part
    return json.loads(data.split(b'\n',1)[0].decode('utf-8') or '{}')

def main():
    p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--vocab',required=True);p.add_argument('--skills',required=True);p.add_argument('--db',required=True);p.add_argument('--socket',required=True);p.add_argument('--cache-size',type=int,default=256);p.add_argument('--check-interval',type=float,default=1.0);a=p.parse_args()
    socket_path=Path(a.socket).expanduser();socket_path.parent.mkdir(parents=True,exist_ok=True)
    try:socket_path.unlink()
    except FileNotFoundError:pass
    started=time.perf_counter();model=MiniLM(Path(a.model).expanduser(),Path(a.vocab).expanduser());index=SemanticIndex(model,Path(a.skills).expanduser(),Path(a.db).expanduser(),a.cache_size,a.check_interval);startup_ms=(time.perf_counter()-started)*1000
    server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);server.bind(str(socket_path));os.chmod(socket_path,0o600);server.listen(8);print(json.dumps({'ready':True,'startup_ms':startup_ms,'examples':len(index.examples),'socket':str(socket_path),'cache_size':index.cache_size,'check_interval':index.check_interval}),flush=True)
    try:
        while True:
            conn,_=server.accept()
            with conn:
                conn.settimeout(2.0)  # a client that connects and goes quiet must not hang the service
                try:
                    req=recv_json(conn)
                    if req.get('op')=='ping':out={'ok':True,'status':'ready','examples':len(index.examples),'cache_entries':len(index.cache)}
                    elif req.get('op')=='reload':index.reload();out={'ok':True,'status':'reloaded','examples':len(index.examples),'cache_entries':0}
                    elif req.get('op')=='clear_cache':index.cache.clear();out={'ok':True,'status':'cache_cleared','cache_entries':0}
                    else:
                        text=str(req.get('text') or '').strip();opts=req.get('options');out=index.query(text,opts if isinstance(opts,list) else None) if text else {'ok':False,'error':'empty_text'}
                except Exception as exc:out={'ok':False,'error':f'{type(exc).__name__}: {exc}'}
                conn.sendall((json.dumps(out,ensure_ascii=False)+'\n').encode('utf-8'))
    finally:
        server.close()
        try:socket_path.unlink()
        except FileNotFoundError:pass
if __name__=='__main__':raise SystemExit(main())
