#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
skills=json.loads((ROOT/'skills'/'builtin.json').read_text(encoding='utf-8'))
out=ROOT/'training'/'repo-training.jsonl'
out.parent.mkdir(parents=True,exist_ok=True)
rows=[]
for s in skills:
    if s.get('id')=='normal_hermes':
        continue
    for text in s.get('examples',[]):
        rows.append({'text':text,'domain':s.get('category','unknown'),'skill':s['id'],'source':'repo_skill_example','weight':1.0})
with out.open('w',encoding='utf-8') as f:
    for row in rows:
        f.write(json.dumps(row,ensure_ascii=False)+'\n')
print(json.dumps({'output':str(out),'examples':len(rows)},indent=2))
