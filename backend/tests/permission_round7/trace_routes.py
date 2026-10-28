"""Supplementary per-test request evidence. No role/dependency changes.
This is route reachability, NOT proof of DB invariants or complete branch acceptance.
"""
import os,json,gzip,hashlib,time
from pathlib import Path
import pytest

@pytest.fixture(autouse=True)
def capture_actual_routes(monkeypatch,request):
    import httpx
    original=httpx.AsyncClient.request
    output=os.environ.get('ROUND7_ROUTE_TRACE')
    if not output:return
    async def traced(client,method,url,*args,**kwargs):
        result=await original(client,method,url,*args,**kwargs)
        path=result.request.url.path
        if path.startswith(('/api/v1','/uploads')) or path in ('/','/health'):
            from app.main import app
            from app.core.security import decode_token
            token=result.request.headers.get('authorization','')
            identity=decode_token(token[7:]) if token.lower().startswith('bearer ') else None
            record={'test':request.node.nodeid,'method':method,'path':path,'query':str(result.request.url.query),
                'warehouse_header':result.request.headers.get('x-warehouse-id'),'subject':identity.get('sub') if identity else None,
                'status':result.status_code,'content_type':result.headers.get('content-type'),
                'sha256':hashlib.sha256(result.content).hexdigest(),'bytes':len(result.content),
                'dependency_overrides':[getattr(f,'__name__',str(f)) for f in app.dependency_overrides],
                'scope':'supplementary route evidence; see test assertions for side effects'}
            try:
                body=result.json()
                # Synthetic responses only. Never persist login tokens or secrets.
                def safe(v):
                    if isinstance(v,dict):return {k:('[omitted]' if any(x in k.lower() for x in ('token','password','secret')) else safe(x)) for k,x in v.items()}
                    if isinstance(v,list):return [safe(x) for x in v]
                    return v
                record['response']=safe(body)
            except ValueError:pass
            with gzip.open(output,'at',encoding='utf-8') as f:f.write(json.dumps(record,ensure_ascii=False,default=str)+'\n')
        return result
    monkeypatch.setattr(httpx.AsyncClient,'request',traced)
