from __future__ import annotations
import json, sqlite3, time
from pathlib import Path
from typing import Any

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS memory_hot (
  type TEXT NOT NULL, subject TEXT NOT NULL, value TEXT NOT NULL,
  scope TEXT NOT NULL DEFAULT '', confidence REAL NOT NULL DEFAULT 1.0,
  priority INTEGER NOT NULL DEFAULT 50, expires_at REAL,
  updated_at REAL NOT NULL, PRIMARY KEY(type,subject,scope)
);
CREATE TABLE IF NOT EXISTS working_memory (
  kind TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL,
  updated_at REAL NOT NULL, PRIMARY KEY(kind,key)
);
CREATE TABLE IF NOT EXISTS experience (
  skill TEXT PRIMARY KEY, uses INTEGER NOT NULL DEFAULT 0,
  successes INTEGER NOT NULL DEFAULT 0, total_latency_ms REAL NOT NULL DEFAULT 0,
  failures INTEGER NOT NULL DEFAULT 0, corrections INTEGER NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS corrections (
  id INTEGER PRIMARY KEY AUTOINCREMENT, input TEXT NOT NULL,
  wrong TEXT, corrected TEXT NOT NULL, metadata TEXT NOT NULL DEFAULT '{}',
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS learned_skills (
  id TEXT PRIMARY KEY, definition TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
  version INTEGER NOT NULL DEFAULT 1, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS route_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, input TEXT NOT NULL, domain TEXT,
  skill TEXT, confidence REAL, memory_source TEXT, latency_ms REAL,
  route TEXT, reason TEXT, created_at REAL NOT NULL
);
"""

class DB:
    def __init__(self, path: Path):
        self.path=Path(path); self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn=sqlite3.connect(self.path, timeout=2.0)
        self.conn.row_factory=sqlite3.Row
        self.conn.executescript(SCHEMA); self.conn.commit()

    def close(self): self.conn.close()

    def upsert_hot(self, m: dict[str, Any]):
        self.conn.execute("""INSERT INTO memory_hot(type,subject,value,scope,confidence,priority,expires_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(type,subject,scope) DO UPDATE SET value=excluded.value,
        confidence=excluded.confidence,priority=excluded.priority,expires_at=excluded.expires_at,updated_at=excluded.updated_at""",
        (m['type'],m['subject'].lower(),json.dumps(m['value']),m.get('scope',''),float(m.get('confidence',1)),int(m.get('priority',50)),m.get('expires_at'),time.time()))
        self.conn.commit()

    def hot_get(self, typ: str, subject: str, scope: str=''):
        now=time.time(); row=self.conn.execute("SELECT * FROM memory_hot WHERE type=? AND subject=? AND scope=? AND (expires_at IS NULL OR expires_at>?)",(typ,subject.lower(),scope,now)).fetchone()
        if not row and scope:
            row=self.conn.execute("SELECT * FROM memory_hot WHERE type=? AND subject=? AND scope='' AND (expires_at IS NULL OR expires_at>?)",(typ,subject.lower(),now)).fetchone()
        if not row: return None
        d=dict(row); d['value']=json.loads(d['value']); return d

    def hot_list(self, typ: str|None=None):
        q="SELECT * FROM memory_hot"; args=[]
        if typ: q+=" WHERE type=?"; args=[typ]
        rows=[]
        for r in self.conn.execute(q,args):
            d=dict(r); d['value']=json.loads(d['value']); rows.append(d)
        return rows

    def hot_delete(self, typ: str, subject: str, scope: str='') -> int:
        cur=self.conn.execute("DELETE FROM memory_hot WHERE type=? AND subject=? AND scope=?",(typ,subject.lower(),scope))
        self.conn.commit()
        return int(cur.rowcount or 0)

    def work_set(self, kind,key,value):
        self.conn.execute("INSERT INTO working_memory(kind,key,value,updated_at) VALUES(?,?,?,?) ON CONFLICT(kind,key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",(kind,key,json.dumps(value),time.time())); self.conn.commit()

    def work_recent(self,kind,limit=10):
        out=[]
        for r in self.conn.execute("SELECT * FROM working_memory WHERE kind=? ORDER BY updated_at DESC LIMIT ?",(kind,limit)):
            d=dict(r); d['value']=json.loads(d['value']); out.append(d)
        return out

    def record_route(self, text, result):
        self.conn.execute("INSERT INTO route_log(input,domain,skill,confidence,memory_source,latency_ms,route,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(text,result.domain,result.skill,result.confidence,result.context_source,result.latency_ms,result.route,result.reason,time.time())); self.conn.commit()
