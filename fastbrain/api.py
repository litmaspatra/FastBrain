from __future__ import annotations
import json
from http.server import BaseHTTPRequestHandler,HTTPServer
from .app import build

class Handler(BaseHTTPRequestHandler):
    stack=None
    def log_message(self,*a):return
    def _json(self,code,obj):
        raw=json.dumps(obj).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    MAX_BODY=65536
    def _body(self):
        # Browsers can't send application/json cross-site without a CORS preflight, which we never answer,
        # so requiring it stops a random web page from POSTing to localhost.
        if 'application/json' not in (self.headers.get('Content-Type') or '').lower():raise ValueError('Content-Type must be application/json')
        n=int(self.headers.get('Content-Length','0') or 0)
        if n<0 or n>self.MAX_BODY:raise ValueError('body too large')
        data=json.loads(self.rfile.read(n) or b'{}')
        if not isinstance(data,dict):raise ValueError('JSON object expected')
        return data
    def do_GET(self):
        if self.path=='/health':return self._json(200,{'ok':True,'version':'0.1.0'})
        if self.path=='/v1/skills':return self._json(200,{'skills':self.stack['registry'].all()})
        if self.path=='/v1/stats':return self._json(200,{'experience':self.stack['experience'].stats()})
        if self.path=='/v1/context':return self._json(200,{'hot':self.stack['db'].hot_list()})
        return self._json(404,{'error':'not_found'})
    def do_POST(self):
        try:
            b=self._body()
        except (ValueError,TypeError) as e:
            return self._json(400,{'error':str(e)})
        try:
            return self._dispatch(b)
        except ValueError as e:
            return self._json(400,{'error':str(e)})
        except Exception as e:
            return self._json(500,{'error':f'{type(e).__name__}: {e}'})
    def _dispatch(self,b):
        if self.path in {'/v1/route','/v1/decide'}:
            r=self.stack['engine'].route(b.get('text',''));return self._json(200,r.to_dict())
        if self.path=='/v1/context':
            self.stack['memory'].project(b);return self._json(200,{'ok':True})
        if self.path=='/v1/skills':
            try:
                self.stack['learner'].learn(b)
                return self._json(200,{'ok':True,'skill':b})
            except Exception as e:
                return self._json(400,{'error':str(e)})
        if self.path=='/v1/skills/test':
            r=self.stack['engine'].route(b.get('text',''));return self._json(200,r.to_dict())
        if self.path=='/v1/learn':
            try:return self._json(200,{'skill':self.stack['learner'].learn(b)})
            except Exception as e:return self._json(400,{'error':str(e)})
        if self.path=='/v1/correction':
            self.stack['learner'].correction(b.get('input',''),b.get('wrong',''),b.get('corrected',''),b.get('metadata'));return self._json(200,{'ok':True})
        return self._json(404,{'error':'not_found'})

def serve(host='127.0.0.1',port=8766):
    # Single-threaded on purpose: one SQLite connection is shared by every request.
    Handler.stack=build();HTTPServer((host,port),Handler).serve_forever()
