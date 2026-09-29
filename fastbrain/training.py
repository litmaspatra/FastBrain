from __future__ import annotations
import json
from pathlib import Path


def _key(row):
    return (str(row.get('text','')).strip().lower(), str(row.get('skill','')).strip())


def export_jsonl(stack, output):
    rows=[]
    registry={s['id']:s for s in stack['registry'].all()}

    # Canonical skill examples remain the cleanest supervised source.
    for s in registry.values():
        if s['id']=='normal_hermes':
            continue
        for text in s.get('examples',[]):
            rows.append({
                'text':text,
                'domain':s.get('category','unknown'),
                'skill':s['id'],
                'source':'skill_example',
                'weight':1.0,
            })

    # Successful local routes capture real user phrasing. Require strong confidence
    # and known skills so failed/ambiguous routing does not train the classifier.
    for r in stack['db'].conn.execute("SELECT input,domain,skill,confidence,route,reason FROM route_log WHERE route='local' AND skill IS NOT NULL ORDER BY id"):
        d=dict(r); skill=d.get('skill')
        if skill not in registry or skill=='normal_hermes':
            continue
        conf=float(d.get('confidence') or 0.0)
        if conf < 0.90:
            continue
        rows.append({
            'text':d['input'],
            'domain':d.get('domain') or registry[skill].get('category','unknown'),
            'skill':skill,
            'source':'successful_route',
            'weight':round(min(1.0,max(0.5,conf)),3),
            'reason':d.get('reason'),
        })

    # Corrections are high-value examples. If metadata or corrected JSON identifies
    # a skill, emit a supervised corrected example; always preserve audit fields.
    for r in stack['db'].conn.execute("SELECT input,wrong,corrected,metadata FROM corrections ORDER BY id"):
        meta=json.loads(r['metadata']) if r['metadata'] else {}
        skill=meta.get('candidate_id') or meta.get('skill')
        corrected_raw=r['corrected']
        try:
            corrected_obj=json.loads(corrected_raw) if isinstance(corrected_raw,str) else corrected_raw
        except Exception:
            corrected_obj=None
        if isinstance(corrected_obj,dict):
            skill=corrected_obj.get('id') or skill
        domain=registry.get(skill,{}).get('category','unknown') if skill else 'unknown'
        row={
            'text':r['input'],
            'corrected':corrected_raw,
            'wrong':r['wrong'],
            'metadata':meta,
            'source':'correction',
            'weight':1.5,
        }
        if skill:
            row['skill']=skill; row['domain']=domain
        rows.append(row)

    # Keep strongest duplicate for (text, skill), while retaining unlabelled audit corrections.
    labelled={}; unlabelled=[]
    for row in rows:
        if row.get('skill'):
            k=_key(row)
            current=labelled.get(k)
            if current is None or float(row.get('weight',1)) > float(current.get('weight',1)):
                labelled[k]=row
        else:
            unlabelled.append(row)
    final=list(labelled.values())+unlabelled
    final.sort(key=lambda x:(str(x.get('skill','')),str(x.get('text','')).lower(),str(x.get('source',''))))

    path=Path(output).expanduser()
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8') as f:
        for row in final:
            f.write(json.dumps(row,ensure_ascii=False)+'\n')
    return len(final)
