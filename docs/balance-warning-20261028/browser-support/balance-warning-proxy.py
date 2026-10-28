from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from http.client import HTTPConnection
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def handle_request(self):
  size=int(self.headers.get('Content-Length',0));body=self.rfile.read(size) if size else None
  port=19150 if self.path.startswith(('/api/','/uploads/')) else 19151
  headers={k:v for k,v in self.headers.items() if k.lower() not in ('host','content-length','connection','accept-encoding')}
  c=HTTPConnection('127.0.0.1',port,timeout=30);c.request(self.command,self.path,body=body,headers=headers);r=c.getresponse();data=r.read();self.send_response(r.status)
  for k,v in r.getheaders():
   if k.lower() not in ('content-length','transfer-encoding','connection','content-encoding'):self.send_header(k,v)
  self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);c.close()
 do_GET=do_POST=do_PUT=do_DELETE=handle_request
ThreadingHTTPServer(('127.0.0.1',19152),Handler).serve_forever()
