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
    r=s['engine'].route('play something');assert r.skill in {'play_music','choose_music_from_context'};assert r.arguments.get('query')=='upbeat hindi';assert r.arguments.get('player')=='simpmusic'

def test_explicit_yt_music():
    s=stack();r=s['engine'].route('play Kesariya on yt music');assert r.route=='local';assert r.skill=='play_music';assert r.arguments['query']=='Kesariya';assert r.arguments['player']=='ytmusic'

def test_latest_video_routes_youtube():
    s=stack();r=s['engine'].route('play the latest video of Tanmay Bhat');assert r.route=='local';assert r.skill=='play_video';assert r.arguments['query']=='tanmay bhat';assert r.arguments['player']=='youtube';assert r.arguments['latest'] is True

def test_player_switch_uses_successful_working_memory():
    s=stack();s['context'].remember_action('play_music',{'query':'Kesariya','player':'simpmusic'})
    r=s['engine'].route('play it on yt music');assert r.route=='local';assert r.skill=='play_music';assert r.arguments['query']=='Kesariya';assert r.arguments['player']=='ytmusic';assert r.reason=='working_memory'
