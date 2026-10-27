// Loopback streaming test proxy: preserves actual browser multipart file bytes.
const fs=require('node:fs'),http=require('node:http');
const state=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
const server=http.createServer((req,res)=>{
 const port=req.url.startsWith('/api/v1/')?state.http_port:state.frontend_port;
 const target=http.request({hostname:'127.0.0.1',port,path:req.url,method:req.method,headers:{...req.headers,host:`127.0.0.1:${port}`}},reply=>{res.writeHead(reply.statusCode,reply.headers);reply.pipe(res);});
 target.on('error',()=>{res.writeHead(502,{'content-type':'application/json'});res.end(JSON.stringify({detail:'本地测试服务未就绪'}));});
 req.pipe(target);
});
server.listen(state.proxy_port,'127.0.0.1',()=>console.log(JSON.stringify({proxy_ready:true,port:state.proxy_port,localhost_only:true})));
process.on('SIGINT',()=>server.close(()=>process.exit(0)));
