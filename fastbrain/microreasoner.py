from __future__ import annotations
import re

class MicroReasoner:
    def __init__(self,cfg,registry,context): self.cfg=cfg; self.registry=registry; self.context=context

    @staticmethod
    def _clean_contact(value):
        value=' '.join(str(value or '').strip().split())
        value=re.sub(r'^(?:to\s+)', '', value, flags=re.I)
        value=re.sub(r'\s+(?:please|pls)$', '', value, flags=re.I)
        return value.strip(' ,.!?')

    def _natural_communication(self,text,skill,args):
        """Fill missing communication arguments after semantic intent selection.

        This never bypasses executor contact verification. It only extracts what
        the user appears to have said so the existing alias/contact guard can
        decide whether execution is safe.
        """
        t=' '.join(text.strip().split())
        if skill=='call_contact' and not args.get('contact'):
            patterns=[
                r'^(?:can you\s+|could you\s+|please\s+)?(?:call|phone|ring)\s+(.+?)(?:\s+please)?$',
                r'^(?:can you\s+|could you\s+|please\s+)?give\s+(.+?)\s+(?:a\s+)?call(?:\s+please)?$',
                r'^(?:can you\s+|could you\s+|please\s+)?make\s+a\s+call\s+to\s+(.+?)(?:\s+please)?$',
            ]
            for pattern in patterns:
                m=re.match(pattern,t,re.I)
                if m:
                    contact=self._clean_contact(m.group(1))
                    if contact:
                        args['contact']=contact
                        return args,[{'op':'extract_contact','source':'microreasoner','value':contact}]
        if skill in {'send_whatsapp','send_sms'} and (not args.get('contact') or not args.get('message')):
            patterns=[
                r'^(?:please\s+)?(?:tell|message|whatsapp)\s+(.+?)\s+(?:that|saying)\s+(.+)$',
                r'^(?:please\s+)?(?:send|drop)\s+(.+?)\s+(?:a\s+)?(?:whatsapp\s+)?message\s+(?:that\s+|saying\s+)?(.+)$',
                r'^(?:please\s+)?send\s+(?:a\s+)?whatsapp\s+(?:message\s+)?to\s+(.+?)\s+(?:that|saying)\s+(.+)$',
                r'^(?:please\s+)?(?:text|sms)\s+(.+?)\s+(?:that|saying)\s+(.+)$',
            ]
            for pattern in patterns:
                m=re.match(pattern,t,re.I)
                if m:
                    contact=self._clean_contact(m.group(1)); message=m.group(2).strip()
                    if contact and message:
                        args.setdefault('contact',contact);args.setdefault('message',message)
                        return args,[{'op':'extract_message','source':'microreasoner','contact':contact}]
        return args,[]

    def build(self,text,skill,args):
        plan=[]; low=' '.join(text.lower().split())
        args,extraction_plan=self._natural_communication(text,skill,args)
        plan.extend(extraction_plan)
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
        if skill=='open_app' and not args.get('app'):
            patterns=[
                r'^(?:get|put|take)\s+me\s+(?:into|inside|to)\s+([\w .+-]+?)(?:\s+(?:somehow|please|pls))?$',
                r'^(?:let me (?:use|into)|bring me to|switch me to)\s+([\w .+-]+?)(?:\s+(?:somehow|please|pls))?$',
            ]
            for pattern in patterns:
                m=re.match(pattern,text.strip(),re.I)
                if m:
                    app=m.group(1).strip(' .,!?:;')
                    if app:
                        args['app']=app
                        plan.append({'op':'extract_app','source':'microreasoner','value':app})
                        break
        m=re.search(r'\b(?:and\s+)?(?:set\s+)?volume(?:\s+to)?\s+(\d{1,3})\b',low)
        if m and skill in {'play_music','choose_music_from_context'}:
            plan.append({'skill':'set_volume','arguments':{'level':max(0,min(100,int(m.group(1))))}})
        return args, plan[:self.cfg.max_plan_steps]
