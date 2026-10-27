from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from http.client import HTTPConnection
from pathlib import Path
from email.parser import BytesParser
from email import policy
import json,time,threading,hashlib
lock=threading.RLock()
control=Path('/tmp/excel-import-browser-control.json')
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def handle_request(self):
        n=int(self.headers.get('Content-Length',0));body=self.rfile.read(n) if n else None
        port=19140 if self.path.startswith(('/api/','/uploads/','/health')) else 19141
        connection=HTTPConnection('127.0.0.1',port,timeout=30)
        headers={k:v for k,v in self.headers.items() if k.lower() not in ('host','content-length','connection','accept-encoding')};headers['Host']='127.0.0.1:19142'
        connection.request(self.command,self.path,body=body,headers=headers);r=connection.getresponse();upstream=r.status;data=r.read();response_headers=r.getheaders();connection.close()
        status=upstream
        try:result=json.loads(data)
        except (ValueError,UnicodeDecodeError):result=None
        with lock:
            settings=json.loads(control.read_text())
            injected=bool(settings.get('drop_next_expense_response') and self.command=='POST' and self.command=='POST' and result and result.get('mode')=='confirmed' and upstream==200)
            if injected:
                settings['drop_next_expense_response']=False;control.write_text(json.dumps(settings));status=503
                data=json.dumps({'detail':'隔离故障注入：服务端已提交，本次响应中断，请沿用原请求重试'},ensure_ascii=False).encode()
                response_headers=[('Content-Type','application/json; charset=utf-8')]
        self.send_response(status)
        for k,v in response_headers:
            if k.lower() not in ('content-length','transfer-encoding','connection','content-encoding'):self.send_header(k,v)
        self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        if self.path.startswith('/api/'):
            entry={'method':self.command,'path':self.path,'upstream_status':upstream,'client_status':status,'injected':injected,
                'warehouse_header':self.headers.get('X-Warehouse-ID'),'time':time.time()}
            if body and any(p in self.path for p in ('/import/products','/import/logistics','/import-excel')) and 'multipart/form-data' in (self.headers.get('Content-Type') or ''):
                message=BytesParser(policy=policy.default).parsebytes(('Content-Type: '+self.headers['Content-Type']+'\r\n\r\n').encode()+body)
                entry['fields']={};entry['files']=[]
                for part in message.iter_parts():
                    value=part.get_payload(decode=True)
                    if part.get_filename():entry['files'].append({'name':part.get_filename(),'bytes':len(value),'sha256':hashlib.sha256(value).hexdigest()})
                    else:entry['fields'][part.get_param('name',header='content-disposition')]=value.decode()
            if self.path.startswith(('/api/v1/sku-catalog','/api/v1/suppliers','/api/v1/incoming')) and result is not None:entry['upstream_response']=result
            with lock:
                with Path('/Users/xiongliu/Desktop/海外仓财务系统/docs/excel-import-20261027/browser-requests.jsonl').open('a') as f:f.write(json.dumps(entry,ensure_ascii=False)+'\n')
    do_GET=do_POST=do_PUT=handle_request
ThreadingHTTPServer(('127.0.0.1',19142),Handler).serve_forever()
