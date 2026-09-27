from __future__ import annotations
import argparse,json,platform,statistics,sys,time
from .app import build
from .api import serve

def main():
    p=argparse.ArgumentParser(prog='fastbrain');sub=p.add_subparsers(dest='cmd',required=True)
    r=sub.add_parser('route');r.add_argument('text',nargs='+');r.add_argument('--execute',action='store_true');r.add_argument('--dry-run',action='store_true')
    sub.add_parser('doctor')
    b=sub.add_parser('benchmark-memory');b.add_argument('--iterations',type=int,default=20);b.add_argument('--subject',default='govind')
    s=sub.add_parser('serve');s.add_argument('--host',default='127.0.0.1');s.add_argument('--port',type=int,default=8766)
    c=sub.add_parser('cache-put');c.add_argument('type');c.add_argument('subject');c.add_argument('value');c.add_argument('--scope',default='')
    sub.add_parser('skills');sub.add_parser('stats');e=sub.add_parser('export-training');e.add_argument('--output',default='fastbrain-training.jsonl')
    a=p.parse_args();stack=build()
    if a.cmd=='doctor':
        cfg=stack['config'];checks={'python':sys.version.split()[0],'python_ok':sys.version_info[:2]==(3,13),'platform':sys.platform,'machine':platform.machine(),'db':str(cfg.db_path),'memory_mode':cfg.memory_mode,'hindsight_direct_configured':bool(cfg.hindsight_url or cfg.hindsight_cmd),'skills':len(stack['registry'].all())}
        print(json.dumps(checks,indent=2));return 0 if checks['python_ok'] else 2
    if a.cmd=='route':
        out=stack['engine'].route(' '.join(a.text));payload=out.to_dict()
        if a.execute or a.dry_run:payload['execution']=stack['executor'].execute(out,dry_run=a.dry_run)
        print(json.dumps(payload,indent=2,ensure_ascii=False))
        if a.execute and not payload.get('execution',{}).get('success',False): return 64
        return 0
    if a.cmd=='cache-put':stack['memory'].project({'type':a.type,'subject':a.subject,'value':a.value,'scope':a.scope,'confidence':1,'priority':90});print('OK');return 0
    if a.cmd=='benchmark-memory':
        mem=stack['memory']; mem.project({'type':'alias','subject':a.subject,'value':'benchmark-value','scope':'communication','confidence':1})
        hot=[];direct=[]
        for _ in range(a.iterations):
            t=time.perf_counter();mem.lookup_hot('alias',a.subject,'communication');hot.append((time.perf_counter()-t)*1000)
            t=time.perf_counter();mem.lookup_direct('alias',a.subject,'communication');direct.append((time.perf_counter()-t)*1000)
        def summary(x):return {'median_ms':statistics.median(x),'p95_ms':sorted(x)[max(0,int(len(x)*.95)-1)],'mean_ms':statistics.mean(x)}
        print(json.dumps({'hot':summary(hot),'direct':summary(direct),'direct_configured':bool(stack['config'].hindsight_url or stack['config'].hindsight_cmd),'recommendation':'measure on device; prefer direct if consistently <500ms, hot if >=1000ms, otherwise hybrid'},indent=2));return 0
    if a.cmd=='serve':serve(a.host,a.port);return 0
    if a.cmd=='skills':print(json.dumps(stack['registry'].all(),indent=2));return 0
    if a.cmd=='stats':print(json.dumps(stack['experience'].stats(),indent=2));return 0
    if a.cmd=='export-training':
        from .training import export_jsonl
        n=export_jsonl(stack,a.output);print(json.dumps({'output':a.output,'examples':n},indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
