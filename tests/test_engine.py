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

def test_whatsapp_is_default_message_channel():
    s=stack();s['memory'].project({'type':'alias','subject':'govind','value':'butagorira','scope':'communication'})
    r=s['engine'].route('message Govind I am late');assert r.route=='local';assert r.skill=='send_whatsapp';assert r.arguments['contact']=='butagorira';assert r.arguments['message']=='I am late'

def test_sms_requires_explicit_sms_intent():
    s=stack();r=s['engine'].route('sms Ravi hello');assert r.route=='local';assert r.skill=='send_sms';assert r.arguments['message']=='hello'

def test_send_it_to_him_uses_successful_working_memory():
    s=stack();s['context'].remember_action('send_whatsapp',{'contact':'butagorira','message':'I am late'})
    r=s['engine'].route('send it to him');assert r.route=='local';assert r.skill=='send_whatsapp';assert r.arguments['contact']=='butagorira';assert r.arguments['message']=='I am late';assert r.reason=='working_memory'

def test_same_message_to_new_contact():
    s=stack();s['context'].remember_action('send_whatsapp',{'contact':'butagorira','message':'Meeting at 5'})
    s['memory'].project({'type':'alias','subject':'ravi','value':'ravi','scope':'communication'})
    r=s['engine'].route('send the same message to Ravi');assert r.route=='local';assert r.skill=='send_whatsapp';assert r.arguments['contact']=='ravi';assert r.arguments['message']=='Meeting at 5'

def test_battery_condition_is_deterministic():
    s=stack();r=s['engine'].route("check battery and if it's below 20 open battery settings")
    assert r.route=='local';assert r.skill=='battery_status';assert r.reason=='deterministic';assert r.confidence>=.99
    c=next(p for p in r.plan if p.get('op')=='conditional');assert c['conditions'][0]['source_result']=='battery_status';assert c['conditions'][0]['operator']=='lt';assert c['conditions'][0]['threshold']==20

def test_charging_condition_with_else():
    s=stack();r=s['engine'].route("check battery and if it's charging set volume to 30 otherwise set volume to 20")
    c=next(p for p in r.plan if p.get('op')=='conditional');assert c['conditions']==[{'source_result':'battery_charging','operator':'eq','threshold':True}]
    assert c['then']['skill']=='set_volume' and c['then']['arguments']['level']==30
    assert c['else']['skill']=='set_volume' and c['else']['arguments']['level']==20

def test_wifi_condition_is_deterministic():
    s=stack();r=s['engine'].route('check wifi and if wifi is connected open Maps otherwise do nothing')
    assert r.route=='local';assert r.skill=='wifi_status';assert r.reason=='deterministic'
    c=next(p for p in r.plan if p.get('op')=='conditional');assert c['conditions'][0]['source_result']=='wifi_connected';assert c['else']['op']=='noop'

def test_compound_conditional_branch_is_bounded_sequence():
    s=stack();r=s['engine'].route("check battery and if it's below 20 open battery settings and set volume to 20")
    c=next(p for p in r.plan if p.get('op')=='conditional');seq=c['then'];assert seq['op']=='sequence';assert len(seq['steps'])==2
    assert seq['steps'][0]['skill']=='open_app';assert seq['steps'][1]['skill']=='set_volume'

def test_combined_battery_conditions_reuse_one_source_read():
    s=stack();r=s['engine'].route("check battery and if it's below 20 and not charging open battery settings otherwise do nothing")
    c=next(p for p in r.plan if p.get('op')=='conditional')
    assert c['conditions'][0]=={'source_result':'battery_status','operator':'lt','threshold':20}
    assert c['conditions'][1]=={'source_result':'battery_charging','operator':'eq','threshold':False}
    assert c['then']['skill']=='open_app';assert c['else']['op']=='noop'

def test_unclear_step_inside_branch_stays_deferred():
    s=stack();r=s['engine'].route("check battery and if it's below 20 open Maps and do something clever there")
    c=next(p for p in r.plan if p.get('op')=='conditional');seq=c['then'];assert seq['op']=='sequence';assert seq['steps'][0]['skill']=='open_app';assert seq['steps'][1]['op']=='hermes_clause'
