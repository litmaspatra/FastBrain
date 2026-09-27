from __future__ import annotations
import json

def export_jsonl(stack, output):
    rows=[]
    for s in stack["registry"].all():
        if s["id"]=="normal_hermes": continue
        for text in s.get("examples",[]): rows.append({"text":text,"domain":s.get("category","unknown"),"skill":s["id"],"source":"skill_example"})
    for r in stack["db"].conn.execute("SELECT input,wrong,corrected,metadata FROM corrections ORDER BY id"):
        rows.append({"text":r["input"],"corrected":r["corrected"],"wrong":r["wrong"],"metadata":json.loads(r["metadata"]),"source":"correction"})
    with open(output,"w",encoding="utf-8") as f:
        for row in rows:f.write(json.dumps(row,ensure_ascii=False)+"\n")
    return len(rows)
