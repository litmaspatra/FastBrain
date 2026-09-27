from __future__ import annotations
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from .app import build

class Handler(BaseHTTPRequestHandler):
    stack=None
    def log_message(self,*a):return
    def _json(self,code,obj):
        raw=json.dumps(obj).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def _body(self):
        n=int(self.headers.get('Content-Length','0'));return json.loads(self.rfile.read(n) or b'{}')
    def do_GET(self):
        if self.path=='/health':return self._json(200,{'ok':True,'version':'0.1.0'})
        if self.path=='/v1/skills':return self._json(200,{'skills':self.stack['registry'].all()})
        if self.path=='/v1/stats':return self._json(200,{'experience':self.stack['experience'].stats()})
        if self.path=='/v1/context':return self._json(200,{'hot':self.stack['db'].hot_list()})
        return self._json(404,{'error':'not_found'})
    def do_POST(self):
        b=self._body()
        if self.path in {'/v1/route','/v1/decide'}:
            r=self.stack['engine'].route(b.get('text',''));return self._json(200,r.to_dict())
        if self.path=='/v1/context':
            self.stack['memory'].project(b);return self._json(200,{'ok':True})
        if self.path=='/v1/skills/test':
            r=self.stack['engine'].route(b.get('text',''));return self._json(200,r.to_dict())
        if self.path=='/v1/learn':
            try:return self._json(200,{'skill':self.stack['learner'].learn(b)})
            except Exception as e:return self._json(400,{'error':str(e)})
        if self.path=='/v1/correction':
            self.stack['learner'].correction(b.get('input',''),b.get('wrong',''),b.get('corrected',''),b.get('metadata'));return self._json(200,{'ok':True})
        return self._json(404,{'error':'not_found'})

def serve(host='127.0.0.1',port=8766):
    Handler.stack=build();ThreadingHTTPServer((host,port),Handler).serve_forever()
