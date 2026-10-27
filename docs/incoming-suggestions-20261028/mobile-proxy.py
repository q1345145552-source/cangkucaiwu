from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from http.client import HTTPConnection
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def handle_request(self):
  body=self.rfile.read(int(self.headers.get('Content-Length',0)))
  conn=HTTPConnection('127.0.0.1',19210 if self.path.startswith(('/api/','/uploads/')) else 19211,timeout=30)
  headers={k:v for k,v in self.headers.items() if k.lower() not in ('host','connection','content-length','accept-encoding')}
  conn.request(self.command,self.path,body=body,headers=headers);r=conn.getresponse();data=r.read()
  self.send_response(r.status)
  for k,v in r.getheaders():
   if k.lower() not in ('content-length','connection','transfer-encoding','content-encoding'):self.send_header(k,v)
  self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);conn.close()
 do_GET=do_POST=do_PUT=do_DELETE=handle_request
ThreadingHTTPServer(('127.0.0.1',19212),Handler).serve_forever()
