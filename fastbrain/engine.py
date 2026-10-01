from __future__ import annotations
import re,time
from .models import RouteResult

class FastBrain:
    def __init__(self,cfg,db,registry,semantic,context,micro,experience):
        self.cfg=cfg;self.db=db;self.registry=registry;self.semantic=semantic;self.context=context;self.micro=micro;self.experience=experience

    @staticmethod
    def _primary_action_text(text):
        """Return the first actionable clause for safe non-communication routing.

        The full original text is still passed to MicroReasoner for ordered plan
        construction. We only shorten the text used to choose/extract the primary
        skill, and only when the suffix clearly begins another known local action.
        """
        t=' '.join(str(text or '').strip().split())
        low=t.lower()
        if re.match(r'^(?:message|send|tell|text|sms|whatsapp|call|phone|ring)\b',low):
            return t
        action_start=r'(?:open|launch|play|set\s+volume|volume|turn\s+torch|torch\s+(?:on|off)|flashlight\s+(?:on|off)|battery|wifi\s+status)\b'
        patterns=[
            rf'^(.*?)(?:\s*,\s*(?:after\s+that\s+|next\s+)?)(?={action_start})',
            rf'^(.*?)(?:\s+(?:and\s+then|then|after\s+that|next)\s+)(?={action_start})',
            rf'^(.*?)(?:\s+and\s+)(?={action_start})',
        ]
        for pattern in patterns:
            m=re.match(pattern,t,re.I)
            if m and m.group(1).strip():return m.group(1).strip(' ,')
        return t

    def _confirmation_intent(self,text):
        low=' '.join(text.lower().strip().split());pending=self.context.pending_confirmation()
        if not pending:return None,0,{},''
        yes={'yes','yeah','yep','correct','right','haan','ha','han','yes do it','haan karo','yes call','yes send'};no={'no','nope','nah','nahi','nahin','cancel','cancel it'}
        if low in yes:
            args=dict(pending.get('arguments') or {});args['contact']=pending.get('suggestion') or args.get('contact');return pending.get('skill'),.995,args,'working_memory'
        if low in no:self.context.clear_pending_confirmation();return 'normal_hermes',1.0,{},'confirmation_rejected'
        m=re.match(r'^(?:no|nope|nah|nahi|nahin)[,\s]+(.+)$',text.strip(),re.I)
        if m:
            args=dict(pending.get('arguments') or {});args['contact']=m.group(1).strip();self.context.clear_pending_confirmation();return pending.get('skill'),.995,args,'deterministic'
        return None,0,{},''

    def _message_intent(self,text):
        t=' '.join(text.strip().split());low=t.lower();recent_person=self.context.recent('person');recent_message=self.context.recent('message')
        m=re.match(r'^(?:sms|text)\s+([^\s]+)\s+(.+)$',t,re.I)
        if m:return 'send_sms',.995,{'contact':m.group(1).strip(),'message':m.group(2).strip()},'deterministic'
        m=re.match(r'^send\s+sms\s+to\s+([^\s]+)\s+(.+)$',t,re.I)
        if m:return 'send_sms',.995,{'contact':m.group(1).strip(),'message':m.group(2).strip()},'deterministic'
        if low in {'send the same message by sms','send same message by sms','send it by sms'} and recent_person and recent_message:return 'send_sms',.995,{'contact':recent_person,'message':recent_message},'working_memory'
        m=re.match(r'^(?:send\s+)?(?:a\s+)?(?:whatsapp|whatsapp\s+message)\s+to\s+([^\s]+)\s+(?:saying|that)\s+(.+)$',t,re.I)
        if m:return 'send_whatsapp',.995,{'contact':m.group(1).strip(),'message':m.group(2).strip()},'deterministic'
        m=re.match(r'^(?:message|whatsapp)\s+([^\s]+)\s+(.+)$',t,re.I)
        if m:return 'send_whatsapp',.995,{'contact':m.group(1).strip(),'message':m.group(2).strip()},'deterministic'
        m=re.match(r'^send\s+([^\s]+)\s+(.+)$',t,re.I)
        if m and m.group(1).lower() not in {'a','an','it','that','this','the','same','sms','whatsapp'}:return 'send_whatsapp',.995,{'contact':m.group(1).strip(),'message':m.group(2).strip()},'deterministic'
        m=re.match(r'^send\s+(.+?)\s+to\s+([^\s]+)$',t,re.I)
        if m and m.group(1).lower() not in {'it','that','this','the same message','same message'}:return 'send_whatsapp',.995,{'contact':m.group(2).strip(),'message':m.group(1).strip()},'deterministic'
        m=re.match(r'^(?:message|send|whatsapp)\s+(?:him|her|them)\s+(.+)$',t,re.I)
        if m and recent_person:return 'send_whatsapp',.995,{'contact':recent_person,'message':m.group(1).strip()},'working_memory'
        if low in {'send the same message','send same message','message him the same','send it again','send it to him','send it to her','send it to them','send that to him','send that to her'} and recent_person and recent_message:return 'send_whatsapp',.995,{'contact':recent_person,'message':recent_message},'working_memory'
        m=re.match(r'^send\s+(?:the\s+)?same\s+message\s+to\s+([^\s]+)$',t,re.I)
        if m and recent_message:return 'send_whatsapp',.995,{'contact':m.group(1).strip(),'message':recent_message},'working_memory'
        m=re.match(r'^send\s+(?:it|that|this)\s+to\s+([^\s]+)$',t,re.I)
        if m and recent_message:return 'send_whatsapp',.995,{'contact':m.group(1).strip(),'message':recent_message},'working_memory'
        return None,0,{},''

    def _media_intent(self,text):
        t=' '.join(text.strip().split());low=t.lower();recent=self.context.recent('media_query')
        if re.fullmatch(r'(?:play|open) (?:it|this)(?: again)? on (?:yt music|youtube music)',low) and recent:return 'play_music',.995,{'query':recent,'player':'ytmusic'},'working_memory'
        if re.fullmatch(r'(?:play|open) (?:it|this)(?: again)? on youtube',low) and recent:return 'play_video',.995,{'query':recent,'player':'youtube','latest':False},'working_memory'
        if re.fullmatch(r'(?:play|open) (?:it|this)(?: again)? on simpmusic',low) and recent:return 'play_music',.995,{'query':recent,'player':'simpmusic'},'working_memory'
        m=re.match(r'^(?:play|show|open|watch)?\s*(?:the\s+)?latest\s+video\s+(?:of|by|from)\s+(.+)$',low,re.I)
        if m:return 'play_video',.995,{'query':m.group(1).strip(),'player':'youtube','latest':True},'deterministic'
        m=re.match(r'^play\s+(.+?)\s+on\s+(?:yt music|youtube music)$',t,re.I)
        if m:return 'play_music',.995,{'query':m.group(1).strip(),'player':'ytmusic'},'deterministic'
        m=re.match(r'^play\s+(.+?)\s+on\s+simpmusic$',t,re.I)
        if m:return 'play_music',.995,{'query':m.group(1).strip(),'player':'simpmusic'},'deterministic'
        m=re.match(r'^(?:play|show|open|watch)\s+(.+?)\s+on\s+youtube$',t,re.I)
        if m:return 'play_video',.995,{'query':m.group(1).strip(),'player':'youtube','latest':False},'deterministic'
        m=re.match(r'^(?:play|show|open|watch)\s+(?:the\s+)?(.+?\s+video)$',t,re.I)
        if m:return 'play_video',.98,{'query':m.group(1).strip(),'player':'youtube','latest':False},'deterministic'
        m=re.match(r'^play\s+(.+)$',t,re.I)
        if m:
            query=m.group(1).strip();vague={'music','some music','something','something nice','something good','something i would like','something suitable','another','another one','another song','something else'}
            if query.lower() not in vague and not re.search(r'\b(?:video|youtube|yt music|youtube music|simpmusic)\b',query,re.I):return 'play_music',.995,{'query':query,'player':'simpmusic'},'deterministic'
        return None,0,{},''

    def _followup(self,text):
        low=' '.join(text.lower().split())
        if low in {'call him','call her','call them','phone him','phone her','ring him','ring her'}:
            person=self.context.recent('person')
            if person:return 'call_contact',.995,{'contact':person},'working_memory'
        if low in {'open it again','open again','launch it again'}:
            app=self.context.recent('app')
            if app:return 'open_app',.995,{'app':app},'working_memory'
        if low in {'play another one','play another','another song','play something else'}:
            recent=self.context.recent('music_query')
            if recent:return 'play_music',.995,{'query':recent,'avoid':recent,'player':'simpmusic'},'working_memory'
            return None,0,{},''
        return None,0,{},''

    def _extract(self,text,skill):
        t=text.strip();low=t.lower();args={}
        if skill=='call_contact':
            for p in [r'^(?:please\s+)?(?:call|phone|ring)\s+(.+?)(?:\s+please)?$',r'^(.+?)\s+ko\s+(?:call|phone)(?:\s+laga(?:o|do))?(?:\s+karo)?$']:
                m=re.match(p,low,re.I)
                if m:args['contact']=m.group(1).strip();break
        elif skill in {'send_whatsapp','send_sms'}:
            m=re.match(r'^(?:message|text|tell)\s+(\S+)\s+(.+)$',t,re.I)
            if m:args={'contact':m.group(1),'message':m.group(2)}
        elif skill=='open_app':
            for p in [r'^(?:open|launch)\s+(.+)$',r'^(.+?)\s+(?:kholo|open karo)$',r'^(?:take me (?:into|to)|go to|switch to|bring up)\s+(.+)$']:
                m=re.match(p,t,re.I)
                if m:args['app']=m.group(1).strip();break
        elif skill=='set_volume':
            m=re.search(r'volume(?:\s+to)?\s+(\d{1,3})',low)
            if m:args['level']=max(0,min(100,int(m.group(1))))
        elif skill=='create_reminder':args['text']=t
        return args

    def _deterministic(self,text):
        low=' '.join(text.lower().split());fixed={'torch on':'torch_on','turn torch on':'torch_on','turn the torch on':'torch_on','turn on the torch':'torch_on','flashlight on':'torch_on','turn the flashlight on':'torch_on','turn on the flashlight':'torch_on','switch on the torch':'torch_on','torch jalao':'torch_on','torch off':'torch_off','turn torch off':'torch_off','torch band karo':'torch_off','battery':'battery_status','battery status':'battery_status','wifi status':'wifi_status','wi-fi status':'wifi_status','pause music':'pause_music','resume music':'resume_music'}
        if low in fixed:return fixed[low],.995
        if re.match(r'^(?:check|show|get)\s+(?:my\s+|the\s+)?battery\b',low):return 'battery_status',.995
        if re.match(r'^(?:(?:check|show|get)\s+(?:my\s+|the\s+)?)?(?:wifi|wi-fi)(?:\s+status)?\b',low):return 'wifi_status',.995
        for phrase in sorted(fixed,key=len,reverse=True):
            if not low.startswith(phrase):continue
            rest=low[len(phrase):];m=re.match(r'^(?:\s*,\s*|\s+and\s+then\s+|\s+then\s+|\s+and\s+)(.+)$',rest)
            if not m:continue
            follow=m.group(1).strip()
            if re.match(r'^(?:open|launch|play|set\s+volume|volume|turn\s+torch|torch\s+(?:on|off)|battery|wifi\s+status)\b',follow):return fixed[phrase],.995
        if re.search(r'\b(?:battery|charge)\b',low) and re.search(r'\b(?:how much|how many|left|remaining|status|level|percent|percentage|kitni|kitna)\b',low):return 'battery_status',.995
        if re.match(r'^(?:open|launch|take me (?:into|to)|go to|switch to|bring up)\s+.+$',low) or re.match(r'^.+\s+(?:kholo|open karo)$',low):return 'open_app',.98
        if re.match(r'^(?:call|phone|ring)\s+.+$',low) or re.match(r'^.+\s+ko\s+(?:call|phone)',low):return 'call_contact',.98
        if re.search(r'\bvolume(?:\s+to)?\s+\d{1,3}\b',low) and not any(x in low for x in ('play ','music','song')):return 'set_volume',.98
        return None,0

    def route(self,text):
        start=time.perf_counter();primary_text=self._primary_action_text(text);skill,conf,args,reason=self._confirmation_intent(text)
        routing_text=text if re.match(r'^(?:message|send|tell|text|sms|whatsapp|call|phone|ring)\b',text.strip(),re.I) else primary_text
        if not skill:skill,conf,args,reason=self._message_intent(routing_text)
        if not skill:skill,conf,args,reason=self._media_intent(routing_text)
        if not skill:skill,conf,args,reason=self._followup(routing_text)
        if not skill:skill,conf=self._deterministic(routing_text);reason='deterministic' if skill else 'semantic';args={}
        if not skill:
            _,d,_=self.semantic.route(routing_text);skill,conf=d.choice,d.confidence
        s=self.registry.get(skill) if skill else None
        if not s or skill=='normal_hermes':r=RouteResult('hermes',confidence=conf,reason=reason if skill=='normal_hermes' else 'unknown_or_complex')
        else:
            if not args:args=self._extract(routing_text,skill)
            needs=s.get('arguments',{})
            if skill in {'call_contact','send_whatsapp','send_sms'} and args.get('contact') in {'him','her','them'}:
                recent=self.context.recent('person')
                if recent:args['contact']=recent;reason='working_memory'
            args,plan=self.micro.build(text,skill,args)
            if reason=='working_memory':plan=[{'op':'resolve_followup','source':'working_memory'}]+list(plan or [])
            if skill in {'call_contact','send_whatsapp','send_sms'} and reason=='semantic' and conf>=self.cfg.context_threshold:
                trusted_contact=any(p.get('op')=='resolve_contact' and p.get('source') in {'hot','working_memory'} for p in (plan or []))
                if trusted_contact:conf=max(conf,.965)
            required=[k for k,v in needs.items() if v.get('required')];missing=[x for x in required if not args.get(x)];risk=s.get('risk','low');threshold=max(self.cfg.execute_threshold,0.96 if risk=='medium' else self.cfg.execute_threshold)
            if missing:r=RouteResult('hermes',s.get('category','unknown'),skill,args,conf,'missing_arguments:'+','.join(missing),plan=plan)
            elif conf>=threshold:
                src='none'
                if plan:
                    for p in plan:
                        if p.get('source') and p['source']!='none':src=p['source'];break
                    if src=='none' and args.get('context',{}).get('source'):src=args['context']['source']
                r=RouteResult('local',s.get('category','unknown'),skill,args,conf,reason,src,plan)
            elif conf>=self.cfg.context_threshold:r=RouteResult('hermes',s.get('category','unknown'),skill,args,conf,'confidence_needs_context',plan=plan)
            else:r=RouteResult('hermes',s.get('category','unknown'),skill,args,conf,'low_confidence',plan=plan)
        r.latency_ms=(time.perf_counter()-start)*1000;self.db.record_route(text,r);return r