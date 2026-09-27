from __future__ import annotations
import shutil, subprocess, time

class Executor:
    def __init__(self,registry,experience):self.registry=registry;self.experience=experience
    def execute(self,result,dry_run=False):
        if result.route!='local':return {'executed':False,'route':result.route,'reason':result.reason}
        skill=self.registry.get(result.skill); argv=self.registry.render_command(skill,result.arguments)
        if not argv:return {'executed':False,'error':'no_executor'}
        path=shutil.which(argv[0])
        if not path:return {'executed':False,'error':'helper_not_found','command':argv[0]}
        argv[0]=path
        if dry_run:return {'executed':False,'dry_run':True,'command':argv}
        st=time.perf_counter()
        try:
            p=subprocess.run(argv,timeout=float(skill.get('timeout',8)),capture_output=True,text=True)
            ms=(time.perf_counter()-st)*1000;ok=p.returncode==0;self.experience.record(result.skill,ok,ms)
            return {'executed':True,'success':ok,'returncode':p.returncode,'latency_ms':ms,'stdout':p.stdout[-1000:],'stderr':p.stderr[-1000:]}
        except Exception as e:
            ms=(time.perf_counter()-st)*1000;self.experience.record(result.skill,False,ms);return {'executed':True,'success':False,'latency_ms':ms,'error':str(e)}
