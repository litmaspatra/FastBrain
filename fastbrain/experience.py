from __future__ import annotations
import time


class ExperienceEngine:
    def __init__(self,db):self.db=db

    def record(self,skill,success,latency_ms,correction=False):
        self.db.conn.execute("""INSERT INTO experience(skill,uses,successes,total_latency_ms,failures,corrections,updated_at)
        VALUES(?,1,?,?,?, ?,?) ON CONFLICT(skill) DO UPDATE SET uses=uses+1,successes=successes+excluded.successes,total_latency_ms=total_latency_ms+excluded.total_latency_ms,failures=failures+excluded.failures,corrections=corrections+excluded.corrections,updated_at=excluded.updated_at""",
        (skill,1 if success else 0,float(latency_ms),0 if success else 1,1 if correction else 0,time.time())); self.db.conn.commit()

    def get(self,skill):
        row=self.db.conn.execute('SELECT * FROM experience WHERE skill=?',(skill,)).fetchone()
        if not row:return None
        d=dict(row); d['success_rate']=d['successes']/d['uses'] if d['uses'] else 0; d['avg_latency_ms']=d['total_latency_ms']/d['uses'] if d['uses'] else 0
        return d

    def local_trust(self,skill):
        """Return whether execution history still supports local learned-skill routing.

        New skills get a three-use grace period so they can accumulate evidence. After
        that, repeated failures/corrections make Hermes the safer fallback. Slow but
        otherwise successful skills stay local; latency is reported for later tuning.
        """
        d=self.get(skill)
        if not d or d['uses']<3:
            return {'trusted':True,'reason':'insufficient_history','stats':d}
        if d['failures']>=2 and d['success_rate']<0.75:
            return {'trusted':False,'reason':'repeated_failures','stats':d}
        if d['corrections']>=2 and d['success_rate']<0.9:
            return {'trusted':False,'reason':'repeated_corrections','stats':d}
        if d['success_rate']<0.6:
            return {'trusted':False,'reason':'low_success_rate','stats':d}
        return {'trusted':True,'reason':'history_ok','stats':d}

    def stats(self):
        out=[]
        for r in self.db.conn.execute('SELECT * FROM experience ORDER BY uses DESC'):
            d=dict(r); d['success_rate']=d['successes']/d['uses'] if d['uses'] else 0; d['avg_latency_ms']=d['total_latency_ms']/d['uses'] if d['uses'] else 0; out.append(d)
        return out