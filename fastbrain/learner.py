from __future__ import annotations
import json,time,re

class SkillLearner:
    def __init__(self,registry,db):self.registry=registry;self.db=db

    def learn(self,definition):
        required={'id','category','examples','executor'}
        missing=required-set(definition)
        if missing:raise ValueError('missing: '+','.join(sorted(missing)))
        if definition.get('risk')=='high':raise ValueError('high-risk skills require manual integration')
        self.registry.register(definition); return definition

    def correction(self,text,wrong,corrected,metadata=None):
        self.db.conn.execute('INSERT INTO corrections(input,wrong,corrected,metadata,created_at) VALUES(?,?,?,?,?)',(text,wrong,corrected,json.dumps(metadata or {}),time.time())); self.db.conn.commit()

    @staticmethod
    def _candidate_id(phrase,definition):
        base=definition.get('id') or re.sub(r'[^a-z0-9]+','_',phrase.lower()).strip('_') or 'workflow'
        return base[:64]

    @staticmethod
    def _score(definition,successful=True):
        risk=definition.get('risk','low')
        if risk=='high': return 0.0,'high_risk_rejected'
        score=0.0
        if successful: score+=0.45
        if definition.get('executor',{}).get('command'): score+=0.2
        if definition.get('examples'): score+=0.15
        if definition.get('category'): score+=0.1
        if risk=='low': score+=0.1
        elif risk=='medium': score-=0.1
        return max(0.0,min(1.0,score)),'ok'

    def observe(self,phrase,definition,successful=True):
        cid=self._candidate_id(phrase,definition)
        score,reason=self._score(definition,successful)
        if reason=='high_risk_rejected':
            return {'ok':False,'candidate_id':cid,'status':'rejected','score':score,'reason':reason}
        now=time.time(); payload=json.dumps(definition,ensure_ascii=False)
        row=self.db.conn.execute('SELECT observations,successes FROM learning_candidates WHERE id=?',(cid,)).fetchone()
        observations=(row['observations'] if row else 0)+1
        successes=(row['successes'] if row else 0)+(1 if successful else 0)
        risk=definition.get('risk','low')
        eligible=(risk=='low' and observations>=2 and successes>=2 and score>=0.8)
        status='eligible' if eligible else 'candidate'
        why='repeated_success' if eligible else ('medium_risk_manual_promotion' if risk=='medium' else 'needs_more_success')
        self.db.conn.execute('''INSERT INTO learning_candidates(id,phrase,definition,observations,successes,score,status,reason,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET phrase=excluded.phrase,definition=excluded.definition,
        observations=excluded.observations,successes=excluded.successes,score=excluded.score,status=excluded.status,reason=excluded.reason,updated_at=excluded.updated_at''',
        (cid,phrase,payload,observations,successes,score,status,why,now,now))
        self.db.conn.commit()
        return {'ok':True,'candidate_id':cid,'status':status,'score':score,'observations':observations,'successes':successes,'reason':why}

    def candidates(self):
        out=[]
        for r in self.db.conn.execute('SELECT * FROM learning_candidates ORDER BY updated_at DESC'):
            d=dict(r); d['definition']=json.loads(d['definition']); out.append(d)
        return out

    def promote(self,candidate_id,force=False):
        row=self.db.conn.execute('SELECT * FROM learning_candidates WHERE id=?',(candidate_id,)).fetchone()
        if not row: raise ValueError('candidate not found')
        d=dict(row); definition=json.loads(d['definition']); risk=definition.get('risk','low')
        if risk=='high': raise ValueError('high-risk skills require manual integration')
        if not force and d['status']!='eligible': raise ValueError('candidate is not eligible yet')
        learned=self.learn(definition)
        self.db.conn.execute("UPDATE learning_candidates SET status='promoted',reason='promoted',updated_at=? WHERE id=?",(time.time(),candidate_id)); self.db.conn.commit()
        return learned
