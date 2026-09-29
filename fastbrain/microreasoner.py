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

    @staticmethod
    def _split_actions(text):
        # Explicit sequencing only. Natural fillers such as "after that" and
        # "next" are accepted, but ordinary prose is not split aggressively.
        parts=re.split(
            r'\s*(?:,|\band\s+then\b|\bthen\b|\band\s+after\s+that\b|\bafter\s+that\b|\bnext\b|\band\b)\s*',
            text.strip(), flags=re.I,
        )
        return [p.strip() for p in parts if p.strip()]

    @staticmethod
    def _split_communication_actions(text):
        # Communication message bodies may legitimately contain "and", so only
        # split on stronger sequencing markers here.
        parts=re.split(
            r'\s*(?:,|\band\s+then\b|\bthen\b|\band\s+after\s+that\b|\bafter\s+that\b|\bnext\b)\s*',
            text.strip(), flags=re.I,
        )
        return [p.strip() for p in parts if p.strip()]

    @staticmethod
    def _low_risk_clause(clause, state=None):
        state=state or {}
        c=' '.join(clause.strip().split())
        low=c.lower()

        # Same-command referents are resolved from the plan state, never from
        # stale global working memory.
        if low in {'open it','open it again','launch it','launch it again'} and state.get('app'):
            return {'skill':'open_app','arguments':{'app':state['app']},'source':'plan_context'}
        if re.fullmatch(r'(?:play|open) (?:it|this)(?: again)? on (?:yt music|youtube music)',low) and state.get('music_query'):
            return {'skill':'play_music','arguments':{'query':state['music_query'],'player':'ytmusic'},'source':'plan_context'}
        if re.fullmatch(r'(?:play|open) (?:it|this)(?: again)? on simpmusic',low) and state.get('music_query'):
            return {'skill':'play_music','arguments':{'query':state['music_query'],'player':'simpmusic'},'source':'plan_context'}
        if re.fullmatch(r'(?:play|open) (?:it|this)(?: again)? on youtube',low) and state.get('media_query'):
            return {'skill':'play_video','arguments':{'query':state['media_query'],'player':'youtube','latest':False},'source':'plan_context'}

        m=re.match(r'^(?:open|launch)\s+(.+)$',c,re.I)
        if m:return {'skill':'open_app','arguments':{'app':m.group(1).strip()},'source':'microreasoner'}
        m=re.match(r'^(?:set\s+)?volume(?:\s+to)?\s+(\d{1,3})$',c,re.I)
        if m:return {'skill':'set_volume','arguments':{'level':max(0,min(100,int(m.group(1))))},'source':'microreasoner'}
        if low in {'torch on','turn torch on','flashlight on'}:
            return {'skill':'torch_on','arguments':{},'source':'microreasoner'}
        if low in {'torch off','turn torch off','flashlight off'}:
            return {'skill':'torch_off','arguments':{},'source':'microreasoner'}
        m=re.match(r'^play\s+(.+)$',c,re.I)
        if m:
            q=m.group(1).strip()
            vague={'music','some music','something','something nice','something good','something i would like','something suitable'}
            return {'skill':'play_music','arguments':({} if q.lower() in vague else {'query':q}),'source':'microreasoner'}
        return None

    @staticmethod
    def _communication_followup_clause(clause, state=None):
        state=state or {}
        c=' '.join(clause.strip().split())
        low=c.lower()
        contact=state.get('contact')
        if contact and low in {'call him','call her','call them','phone him','phone her','phone them','ring him','ring her','ring them'}:
            return {'skill':'call_contact','arguments':{'contact':contact},'source':'plan_context'}
        if contact:
            m=re.match(r'^(?:message|whatsapp|text)\s+(?:him|her|them)\s+(.+)$',c,re.I)
            if m:
                return {'skill':'send_whatsapp','arguments':{'contact':contact,'message':m.group(1).strip()},'source':'plan_context'}
        return MicroReasoner._low_risk_clause(c,state)

    @staticmethod
    def _update_plan_state(state, skill, arguments):
        arguments=arguments or {}
        if skill=='open_app' and arguments.get('app'):
            state['app']=arguments['app']
        if skill in {'play_music','choose_music_from_context'} and arguments.get('query'):
            state['music_query']=arguments['query']
            state['media_query']=arguments['query']
            if arguments.get('player'):state['music_player']=arguments['player']
        if skill=='play_video' and arguments.get('query'):
            state['media_query']=arguments['query']
        if skill in {'call_contact','send_whatsapp','send_sms'} and arguments.get('contact'):
            state['contact']=arguments['contact']
        return state

    def _natural_communication(self,text,skill,args):
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
                r'^(?:message|whatsapp|text)\s+(\S+)\s+(.+)$',
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
        comm_parts=self._split_communication_actions(text) if skill in {'send_whatsapp','send_sms'} else []
        parse_text=comm_parts[0] if len(comm_parts)>1 else text
        # When a communication command has sequenced follow-ups, re-parse only
        # the first clause so the message body does not absorb the later actions.
        if len(comm_parts)>1:
            parsed,extraction_plan=self._natural_communication(parse_text,skill,{})
            if parsed:
                args.update(parsed)
            else:
                args,extraction_plan=self._natural_communication(parse_text,skill,args)
        else:
            args,extraction_plan=self._natural_communication(text,skill,args)
        plan.extend(extraction_plan)

        if skill in {'send_whatsapp','send_sms'} and args.get('message') and len(comm_parts)<=1:
            m=re.match(r'^(.*?)(?:\s+and\s+then\s+|\s+then\s+)(?:open|launch)\s+([\w .+-]+?)\s*$',str(args['message']),re.I)
            if m and m.group(1).strip() and m.group(2).strip():
                args['message']=m.group(1).strip(' ,')
                app=m.group(2).strip(' .,!?:;')
                plan.append({'skill':'open_app','arguments':{'app':app},'source':'microreasoner'})
            m=re.match(r'^(.*?)(?:\s+and\s+then\s+|\s+then\s+)(?:call|phone|ring)\s+(?:him|her|them)\s*$',str(args['message']),re.I)
            if m and m.group(1).strip():
                args['message']=m.group(1).strip(' ,')
                follow_contact=args.get('contact')
                if follow_contact:
                    plan.append({'skill':'call_contact','arguments':{'contact':follow_contact},'source':'working_memory'})

        if skill in {'call_contact','send_whatsapp','send_sms'} and args.get('contact'):
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
            for step in plan:
                if step.get('skill')=='call_contact' and step.get('source')=='working_memory':
                    step.setdefault('arguments',{})['contact']=resolved

        if skill in {'play_music','choose_music_from_context'}:
            if args.get('query'):
                cleaned=re.sub(r'\s+(?:and\s+)?(?:then\s+)?(?:set\s+)?volume(?:\s+to)?\s+\d{1,3}\s*$', '', str(args['query']), flags=re.I).strip()
                cleaned=re.sub(r'\s+(?:and\s+then\s+|then\s+|and\s+)(?:open|launch)\s+.+$', '', cleaned, flags=re.I).strip()
                vague={'music','some music','something','something nice','something good','something i would like','something suitable'}
                if cleaned.lower() in vague:
                    args.pop('query',None)
                elif cleaned:
                    args['query']=cleaned
            mc=self.context.music_context()
            if not args.get('query'):
                chosen=None
                if mc.get('preference'):
                    chosen={'query':str(mc['preference']),'player':None}
                else:
                    chosen=self.context.choose_music_from_history(mc.get('history_candidates') or [])
                if chosen:
                    args['query']=str(chosen['query'])
                    if chosen.get('player'):args.setdefault('player',chosen['player'])
                else:
                    args['query']='popular songs'
            args.setdefault('player','simpmusic')
            args['context']=mc
            plan.append({'op':'choose_music','context':mc,'player':args['player'],'query':args['query']})

        if skill=='open_app':
            m=re.match(r'^(?:open|launch)\s+(.+?)(?=\s*(?:,|\band\s+then\b|\bthen\b|\band\b)|$)',text.strip(),re.I)
            if m:
                args['app']=m.group(1).strip(' .,!?:;')
            elif not args.get('app'):
                patterns=[
                    r'^(?:get|put|take)\s+me\s+(?:into|inside|to)\s+([\w .+-]+?)(?:\s+(?:somehow|please|pls))?$',
                    r'^(?:let me (?:use|into)|bring me to|switch me to)\s+([\w .+-]+?)(?:\s+(?:somehow|please|pls))?$',
                ]
                for pattern in patterns:
                    mm=re.match(pattern,text.strip(),re.I)
                    if mm:
                        app=mm.group(1).strip(' .,!?:;')
                        if app:
                            args['app']=app
                            plan.append({'op':'extract_app','source':'microreasoner','value':app})
                            break

        # Communication compounds reuse the canonical contact resolved above.
        if len(comm_parts)>1 and skill in {'send_whatsapp','send_sms'}:
            state=self._update_plan_state({},skill,args)
            for clause in comm_parts[1:]:
                step=self._communication_followup_clause(clause,state)
                if not step:
                    plan.append({'op':'hermes_clause','text':clause,'source':'planner','deferred':True})
                    continue
                plan.append(step)
                self._update_plan_state(state,step['skill'],step.get('arguments'))

        # Generic ordered low-risk follow-ups. Seed state from the already parsed
        # primary action so later clauses can refer to it using "it/this".
        parts=self._split_actions(text)
        if len(parts)>1 and skill not in {'send_whatsapp','send_sms'}:
            state=self._update_plan_state({},skill,args)
            for clause in parts[1:]:
                step=self._low_risk_clause(clause,state)
                if not step:
                    plan.append({'op':'hermes_clause','text':clause,'source':'planner','deferred':True})
                    continue
                if step['skill']=='play_music' and not step['arguments'].get('query'):
                    mc=self.context.music_context(); chosen=self.context.choose_music_from_history(mc.get('history_candidates') or [])
                    step['arguments']['query']=str(chosen['query']) if chosen else (str(mc.get('preference')) if mc.get('preference') else 'popular songs')
                    step['arguments']['player']=(chosen.get('player') if chosen else None) or 'simpmusic'
                plan.append(step)
                self._update_plan_state(state,step['skill'],step.get('arguments'))

        m=re.search(r'\b(?:and\s+)?(?:then\s+)?(?:set\s+)?volume(?:\s+to)?\s+(\d{1,3})\b',low)
        if m and skill in {'play_music','choose_music_from_context'} and not any(p.get('skill')=='set_volume' for p in plan):
            plan.append({'skill':'set_volume','arguments':{'level':max(0,min(100,int(m.group(1))))},'source':'microreasoner'})
        return args, plan[:self.cfg.max_plan_steps]
