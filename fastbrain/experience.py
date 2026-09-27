from __future__ import annotations
import time
class ExperienceEngine:
    def __init__(self,db):self.db=db
    def record(self,skill,success,latency_ms,correction=False):
        self.db.conn.execute("""INSERT INTO experience(skill,uses,successes,total_latency_ms,failures,corrections,updated_at)
        VALUES(?,1,?,?,?, ?,?) ON CONFLICT(skill) DO UPDATE SET uses=uses+1,successes=successes+excluded.successes,total_latency_ms=total_latency_ms+excluded.total_latency_ms,failures=failures+excluded.failures,corrections=corrections+excluded.corrections,updated_at=excluded.updated_at""",
        (skill,1 if success else 0,float(latency_ms),0 if success else 1,1 if correction else 0,time.time())); self.db.conn.commit()
    def stats(self):
        out=[]
        for r in self.db.conn.execute('SELECT * FROM experience ORDER BY uses DESC'):
            d=dict(r); d['success_rate']=d['successes']/d['uses'] if d['uses'] else 0; d['avg_latency_ms']=d['total_latency_ms']/d['uses'] if d['uses'] else 0; out.append(d)
        return out
