from __future__ import annotations
import re

class MicroReasoner:
    def __init__(self,cfg,registry,context): self.cfg=cfg; self.registry=registry; self.context=context
    def build(self,text,skill,args):
        plan=[]; low=text.lower()
        if skill in {'call_contact','send_whatsapp','send_sms'} and args.get('contact'):
            resolved,source=self.context.resolve_alias(args['contact']); args['contact']=resolved; plan.append({'op':'resolve_contact','source':source,'value':resolved})
        if skill in {'play_music','choose_music_from_context'}:
            mc=self.context.music_context(); args.setdefault('query',mc.get('preference') or 'music'); args['context']=mc; plan.append({'op':'choose_music','context':mc})
        m=re.search(r'\b(?:and\s+)?(?:set\s+)?volume(?:\s+to)?\s+(\d{1,3})\b',low)
        if m and skill in {'play_music','choose_music_from_context'}:
            plan.append({'skill':'set_volume','arguments':{'level':max(0,min(100,int(m.group(1))))}})
        return args, plan[:self.cfg.max_plan_steps]
