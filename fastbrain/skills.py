from __future__ import annotations
import json, re, shutil
from pathlib import Path
from typing import Any
from .db import DB

class SkillRegistry:
    def __init__(self, path: Path, db: DB):
        self.db=db; self.skills={}
        if path.exists():
            for s in json.loads(path.read_text()): self.skills[s['id']]=s
        for r in db.conn.execute("SELECT definition FROM learned_skills WHERE enabled=1"):
            s=json.loads(r['definition']); self.skills[s['id']]=s

    def get(self, skill): return self.skills.get(skill)
    def all(self): return list(self.skills.values())
    def domains(self): return sorted({s.get('category','unknown') for s in self.skills.values()})

    def register(self, skill: dict[str,Any]):
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,64}",skill.get('id','')): raise ValueError('invalid skill id')
        skill.setdefault('category','learned'); skill.setdefault('examples',[]); skill.setdefault('risk','medium')
        self.db.conn.execute("INSERT INTO learned_skills(id,definition,enabled,version,updated_at) VALUES(?,?,1,1,strftime('%s','now')) ON CONFLICT(id) DO UPDATE SET definition=excluded.definition,version=learned_skills.version+1,updated_at=excluded.updated_at",(skill['id'],json.dumps(skill)))
        self.db.conn.commit(); self.skills[skill['id']]=skill

    @staticmethod
    def render_command(skill: dict[str,Any], arguments: dict[str,Any]):
        ex=skill.get('executor',{}); command=ex.get('command')
        if not command: return None
        argv=[command]+[str(x) for x in ex.get('fixed_args',[])]
        for name in ex.get('args',[]):
            if name in arguments: argv.append(str(arguments[name]))
        return argv
