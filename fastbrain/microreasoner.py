from __future__ import annotations
import re

class MicroReasoner:
    def __init__(self,cfg,registry,context): self.cfg=cfg; self.registry=registry; self.context=context

    def _app_from_text(self,text):
        t=' '.join(text.strip().split())
        patterns=[
            r'^(?:open|launch|start)\s+(.+?)(?:\s+please)?$',
            r'^(.+?)\s+(?:kholo|open karo)$',
            r'^(?:take me (?:into|to)|go to|switch to|bring up|show me|put me (?:in|into|inside)|get me (?:in|into|inside))\s+(.+?)(?:\s+(?:somehow|please|now))?$',
            r'^(?:i want to (?:open|use|go to)|let me (?:open|use|go to))\s+(.+?)(?:\s+(?:please|now))?$',
        ]
        for pattern in patterns:
            m=re.match(pattern,t,re.I)
            if m:
                value=m.group(1).strip(' .,!?')
                if value:
                    return value
        return None

    def build(self,text,skill,args):
        plan=[]; low=' '.join(text.lower().split())
        if skill=='open_app' and not args.get('app'):
            app=self._app_from_text(text)
            if app:
                args['app']=app
                plan.append({'op':'extract_app','source':'microreasoner','value':app})
        if skill in {'call_contact','send_whatsapp','send_sms'} and args.get('contact'):
            # Skip alias lookup only when the contact itself came from pronoun-based working memory.
            # Named contacts in follow-up commands (e.g. "send the same message to Govind")
            # must still resolve through the alias cache.
            pronoun_followup = low in {
                'call him','call her','call them','phone him','phone her','ring him','ring her',
                'message him the same','send it again','send the same message','send same message',
                'send it to him','send it to her','send it to them','send that to him','send that to her',
                'send that to them','send this to him','send this to her','send this to them',
                'send the same message by sms','send same message by sms','send it by sms'
            } or bool(re.match(r'^(?:message|send|whatsapp)\s+(?:him|her|them)\s+.+$',low))
            if pronoun_followup:
                resolved=args['contact']; source='working_memory'
            else:
                resolved,source=self.context.resolve_alias(args['contact']); args['contact']=resolved
            plan.append({'op':'resolve_contact','source':source,'value':resolved})
        if skill in {'play_music','choose_music_from_context'}:
            mc=self.context.music_context()
            args.setdefault('query',mc.get('preference') or 'popular songs')
            args.setdefault('player','simpmusic')
            args['context']=mc
            plan.append({'op':'choose_music','context':mc,'player':args['player']})
        m=re.search(r'\b(?:and\s+)?(?:set\s+)?volume(?:\s+to)?\s+(\d{1,3})\b',low)
        if m and skill in {'play_music','choose_music_from_context'}:
            plan.append({'skill':'set_volume','arguments':{'level':max(0,min(100,int(m.group(1))))}})
        return args, plan[:self.cfg.max_plan_steps]
