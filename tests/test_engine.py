import tempfile
from pathlib import Path
from fastbrain.config import Config
from fastbrain.app import build

def stack(mode='hot'):
    td=tempfile.TemporaryDirectory();root=Path(td.name);skills=Path(__file__).parents[1]/'skills'/'builtin.json';cfg=Config(root,root/'db.sqlite',skills,memory_mode=mode);s=build(cfg);s['_td']=td;return s

def test_call_alias_hot():
    s=stack();s['memory'].project({'type':'alias','subject':'govind','value':'butagorira','scope':'communication'})
    r=s['engine'].route('call Govind');assert r.route=='local';assert r.skill=='call_contact';assert r.arguments['contact']=='butagorira';assert r.context_source=='hot'

def test_open_app():
    s=stack();r=s['engine'].route('open WhatsApp');assert r.route=='local' and r.arguments['app'].lower()=='whatsapp'

def test_complex_falls_back():
    s=stack();r=s['engine'].route('explain quantum computing');assert r.route=='hermes'

def test_music_context():
    s=stack();s['memory'].project({'type':'preference','subject':s['context'].time_bucket(),'value':'upbeat hindi','scope':'music'})
    r=s['engine'].route('play something');assert r.skill in {'play_music','choose_music_from_context'};assert r.arguments.get('query')=='upbeat hindi'
