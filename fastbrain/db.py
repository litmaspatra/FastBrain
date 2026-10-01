from __future__ import annotations
import json, re, sqlite3, time
from collections import defaultdict
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
CREATE TABLE IF NOT EXISTS learning_candidates (
  id TEXT PRIMARY KEY, phrase TEXT NOT NULL, definition TEXT NOT NULL,
  observations INTEGER NOT NULL DEFAULT 1, successes INTEGER NOT NULL DEFAULT 1,
  score REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'candidate',
  reason TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS route_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT, input TEXT NOT NULL, domain TEXT,
  skill TEXT, confidence REAL, memory_source TEXT, latency_ms REAL,
  route TEXT, reason TEXT, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS route_trace (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  input TEXT NOT NULL,
  skill TEXT,
  route TEXT,
  total_ms REAL,
  stages TEXT,
  created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS music_history (
  query TEXT NOT NULL,
  player TEXT NOT NULL DEFAULT 'simpmusic',
  plays INTEGER NOT NULL DEFAULT 0,
  successes INTEGER NOT NULL DEFAULT 0,
  failures INTEGER NOT NULL DEFAULT 0,
  last_played_at REAL,
  updated_at REAL NOT NULL,
  PRIMARY KEY(query,player)
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
        self.conn.execute("INSERT INTO working_memory(kind,key,value,updated_at) VALUES(?,?,?,?) ON CONFLICT(kind,key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",(kind,key,json.dumps(value),time.time()))
        self.conn.commit()

    def work_recent(self,kind,limit=10):
        out=[]
        for r in self.conn.execute("SELECT * FROM working_memory WHERE kind=? ORDER BY updated_at DESC LIMIT ?",(kind,limit)):
            d=dict(r); d['value']=json.loads(d['value']); out.append(d)
        return out

    def work_delete(self,kind,key=None):
        if key is None:
            cur=self.conn.execute("DELETE FROM working_memory WHERE kind=?",(kind,))
        else:
            cur=self.conn.execute("DELETE FROM working_memory WHERE kind=? AND key=?",(kind,key))
        self.conn.commit(); return int(cur.rowcount or 0)

    def music_history_record(self, query, player='simpmusic', success=True):
        query=' '.join(str(query or '').strip().split())
        player=str(player or 'simpmusic').strip() or 'simpmusic'
        if not query:
            return
        now=time.time()
        self.conn.execute("""INSERT INTO music_history(query,player,plays,successes,failures,last_played_at,updated_at)
        VALUES(?,?,?,?,?,?,?) ON CONFLICT(query,player) DO UPDATE SET
        plays=music_history.plays+1,
        successes=music_history.successes+excluded.successes,
        failures=music_history.failures+excluded.failures,
        last_played_at=CASE WHEN excluded.successes>0 THEN excluded.last_played_at ELSE music_history.last_played_at END,
        updated_at=excluded.updated_at""",
        (query,player,1,1 if success else 0,0 if success else 1,now if success else None,now))
        self.conn.commit()

    def music_history(self, limit=20):
        rows=[]
        q="""SELECT *,
        CASE WHEN plays>0 THEN CAST(successes AS REAL)/plays ELSE 0 END AS success_rate
        FROM music_history WHERE successes>0
        ORDER BY successes DESC, COALESCE(last_played_at,0) DESC LIMIT ?"""
        for r in self.conn.execute(q,(int(limit),)):
            rows.append(dict(r))
        return rows

    @staticmethod
    def _explicit_music_query(text):
        text=' '.join(str(text or '').strip().split())
        m=re.match(r'^play\s+(.+)$', text, re.I)
        if not m:
            return None, 'simpmusic'
        query=m.group(1).strip()
        player='simpmusic'

        compound_patterns=[
            r'\s*,\s*(?:after\s+that\s+|next\s+)?(?=(?:open|launch|play|set\s+volume|volume|turn\s+torch|torch\s+(?:on|off)|flashlight\s+(?:on|off))\b)',
            r'\s+(?:and\s+then|then|after\s+that|next)\s+(?=(?:open|launch|play|set\s+volume|volume|turn\s+torch|torch\s+(?:on|off)|flashlight\s+(?:on|off))\b)',
            r'\s+and\s+(?=(?:open|launch|set\s+volume|volume|turn\s+torch|torch\s+(?:on|off)|flashlight\s+(?:on|off))\b)',
        ]
        for pattern in compound_patterns:
            parts=re.split(pattern,query,maxsplit=1,flags=re.I)
            if len(parts)>1:
                query=parts[0].strip()
                break

        pm=re.search(r'\s+on\s+(?:yt music|youtube music)\s*$', query, re.I)
        if pm:
            query=query[:pm.start()].strip(); player='ytmusic'
        else:
            pm=re.search(r'\s+on\s+simpmusic\s*$', query, re.I)
            if pm: query=query[:pm.start()].strip()
        query=re.sub(r'\s+(?:and\s+)?(?:then\s+)?(?:set\s+)?volume(?:\s+to)?\s+\d{1,3}\s*$', '', query, flags=re.I).strip()
        vague={
            'music','some music','something','something nice','something good',
            'something i would like','something suitable','another','another one',
            'another song','something else','popular songs'
        }
        if not query or query.lower() in vague:
            return None, player
        return query, player

    def music_request_history(self, limit=20, scan_limit=500):
        agg=defaultdict(lambda:{'requests':0,'last_requested_at':0.0,'query':None,'player':'simpmusic'})
        rows=self.conn.execute("""SELECT input,created_at FROM route_log
            WHERE skill IN ('play_music','choose_music_from_context')
            ORDER BY id DESC LIMIT ?""",(int(scan_limit),)).fetchall()
        for row in rows:
            query,player=self._explicit_music_query(row['input'])
            if not query:
                continue
            key=(query.lower(),player)
            item=agg[key]
            item['requests']+=1
            if float(row['created_at'] or 0)>item['last_requested_at']:
                item['last_requested_at']=float(row['created_at'] or 0)
                item['query']=query
                item['player']=player
        out=list(agg.values())
        out.sort(key=lambda x:(x['requests'],x['last_requested_at']),reverse=True)
        return out[:int(limit)]

    def record_route(self, text, result):
        self.conn.execute("INSERT INTO route_log(input,domain,skill,confidence,memory_source,latency_ms,route,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)",(text,result.domain,result.skill,result.confidence,result.context_source,result.latency_ms,result.route,result.reason,time.time()))
        self.conn.commit()

    def record_trace(self, text, skill, route, total_ms, stages):
        self.conn.execute(
            "INSERT INTO route_trace(input,skill,route,total_ms,stages,created_at) VALUES(?,?,?,?,?,?)",
            (text, skill, route, total_ms, json.dumps(stages), time.time()),
        )
        self.conn.commit()
