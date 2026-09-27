import tempfile
from pathlib import Path
from fastbrain.config import Config
from fastbrain.app import build

def test_learn_skill_without_retrain():
    td=tempfile.TemporaryDirectory();root=Path(td.name);skills=Path(__file__).parents[1]/'skills'/'builtin.json';s=build(Config(root,root/'db',skills))
    new={'id':'archive_case_pdf','category':'files','risk':'medium','arguments':{},'examples':['archive this case pdf'],'executor':{'command':'archive-case-pdf','args':[]}}
    s['learner'].learn(new);assert s['registry'].get('archive_case_pdf') is not None;assert s['semantic'].choice('archive this case pdf').choice=='archive_case_pdf'
