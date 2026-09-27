import json,tempfile,threading
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
from fastbrain.config import Config
from fastbrain.app import build

class H(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def do_POST(self):
        n=int(self.headers['Content-Length']);q=json.loads(self.rfile.read(n));body=json.dumps({'type':q['type'],'subject':q['subject'],'scope':q['scope'],'value':'butagorira','confidence':.99}).encode();self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

def test_direct_and_hybrid_projection():
    srv=HTTPServer(('127.0.0.1',0),H);threading.Thread(target=srv.serve_forever,daemon=True).start()
    td=tempfile.TemporaryDirectory();root=Path(td.name);skills=Path(__file__).parents[1]/'skills'/'builtin.json';cfg=Config(root,root/'db',skills,memory_mode='hybrid',hindsight_url=f'http://127.0.0.1:{srv.server_port}',direct_timeout=1)
    s=build(cfg);r=s['memory'].lookup('alias','govind','communication');assert r['value']=='butagorira' and r['_source']=='direct';assert s['memory'].lookup_hot('alias','govind','communication')['value']=='butagorira';srv.shutdown()
