const http=require('node:http');
http.createServer((req,res)=>{const port=req.url.startsWith('/api/v1/')||req.url.startsWith('/uploads/')?65330:65331;
const target=http.request({hostname:'127.0.0.1',port,path:req.url,method:req.method,headers:{...req.headers,host:`127.0.0.1:${port}`}},r=>{res.writeHead(r.statusCode,r.headers);r.pipe(res)});target.on('error',()=>{res.writeHead(502);res.end('isolated service unavailable')});req.pipe(target)}).listen(65332,'127.0.0.1');
