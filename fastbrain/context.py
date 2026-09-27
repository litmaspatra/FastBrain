from __future__ import annotations
import time

class ContextEngine:
    def __init__(self, db, memory): self.db=db; self.memory=memory
    def needs(self, skill:str)->list[str]:
        if skill in {'call_contact','send_whatsapp','send_sms'}: return ['aliases','recent_people']
        if skill in {'play_music','choose_music_from_context'}: return ['music_preferences','recent_tracks','time_of_day']
        if skill=='open_app': return ['recent_apps']
        return []
    def resolve_alias(self,name:str):
        m=self.memory.lookup('alias',name,'communication')
        return (m.get('value') if m else name, m.get('_source','none') if m else 'none')
    def recent(self,kind):
        r=self.db.work_recent(kind,1); return r[0]['value'] if r else None
    def remember_entity(self,kind,value): self.db.work_set(kind,str(value).lower(),value)
    def time_bucket(self):
        h=time.localtime().tm_hour
        return 'morning' if 5<=h<12 else 'afternoon' if 12<=h<17 else 'evening' if 17<=h<22 else 'night'
    def music_context(self):
        bucket=self.time_bucket(); m=self.memory.lookup('preference',bucket,'music')
        return {'time_of_day':bucket,'preference':m.get('value') if m else None,'recent_tracks':[x['value'] for x in self.db.work_recent('track',5)],'source':m.get('_source','none') if m else 'none'}
