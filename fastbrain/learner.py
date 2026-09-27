from __future__ import annotations
import json,time
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
