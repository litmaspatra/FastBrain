from __future__ import annotations
import json, re, shutil
from pathlib import Path
from typing import Any
from .db import DB

class SkillRegistry:
    # Interpreters/shells would turn a 'skill' into arbitrary code execution.
    _FORBIDDEN_COMMANDS=frozenset({'sh','bash','dash','zsh','ash','su','sudo','python','python3','perl','ruby','node','eval','exec','env','xargs','busybox','nc','ncat','curl','wget','rm','dd','mkfs','chmod','chown'})

    def __init__(self, path: Path, db: DB):
        self.db=db; self.skills={}; self.learned_ids=set()
        if path.exists():
            for s in json.loads(path.read_text(encoding='utf-8')): self.skills[s['id']]=s
        self.builtin_ids=frozenset(self.skills)
        for r in db.conn.execute("SELECT id,definition FROM learned_skills WHERE enabled=1"):
            try: s=json.loads(r['definition'])
            except ValueError: continue
            if s.get('id') in self.builtin_ids or not s.get('id'): continue  # learned skills never replace built-ins
            self.skills[s['id']]=s; self.learned_ids.add(s['id'])

    def _learned_trusted(self, skill):
        if skill not in self.learned_ids:return True
        row=self.db.conn.execute('SELECT * FROM experience WHERE skill=?',(skill,)).fetchone()
        if not row or row['uses']<3:return True
        uses=int(row['uses'] or 0); successes=int(row['successes'] or 0); failures=int(row['failures'] or 0); corrections=int(row['corrections'] or 0)
        rate=successes/uses if uses else 0
        if failures>=2 and rate<0.75:return False
        if corrections>=2 and rate<0.9:return False
        if rate<0.6:return False
        return True

    def get(self, skill):
        if skill and not self._learned_trusted(skill):return None
        return self.skills.get(skill)
    def all(self): return list(self.skills.values())
    def domains(self): return sorted({s.get('category','unknown') for s in self.skills.values()})
    def is_learned(self, skill): return skill in self.learned_ids

    def register(self, skill: dict[str,Any]):
        if not re.fullmatch(r"[a-z][a-z0-9_]{2,64}",skill.get('id','')): raise ValueError('invalid skill id')
        if skill['id'] in self.builtin_ids: raise ValueError('cannot override a built-in skill')
        command=(skill.get('executor') or {}).get('command')
        if not isinstance(command,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}",command):
            raise ValueError('executor.command must be a bare helper name (no path, no spaces)')
        if command in self._FORBIDDEN_COMMANDS: raise ValueError(f'executor.command {command!r} is not allowed')
        skill.setdefault('category','learned'); skill.setdefault('examples',[]); skill.setdefault('risk','medium')
        if skill['risk'] not in {'low','medium'}: raise ValueError('risk must be low or medium (high-risk skills need manual integration)')
        self.db.conn.execute("INSERT INTO learned_skills(id,definition,enabled,version,updated_at) VALUES(?,?,1,1,strftime('%s','now')) ON CONFLICT(id) DO UPDATE SET definition=excluded.definition,version=learned_skills.version+1,updated_at=excluded.updated_at",(skill['id'],json.dumps(skill)))
        self.db.conn.commit(); self.skills[skill['id']]=skill; self.learned_ids.add(skill['id'])

    @staticmethod
    def render_command(skill: dict[str,Any], arguments: dict[str,Any]):
        ex=skill.get('executor',{}); command=ex.get('command')
        if not command: return None
        argv=[command]+[str(x) for x in ex.get('fixed_args',[])]
        for name in ex.get('args',[]):
            if name in arguments: argv.append(str(arguments[name]))
        return argv