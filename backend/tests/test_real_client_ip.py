"""Exact Uvicorn 0.30.6 proxy processing, real HTTP audit rows and spoof rejection."""
import asyncio
import ast
import json
import os
import socket
import subprocess
from pathlib import Path

import pytest
import httpx
import yaml
from sqlalchemy import select
from starlette.requests import Request
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from app.main import app
from app.core.client_ip import get_client_ip
from app.core.security import hash_password
from app.models import User
from app.models.audit_log import AuditLog
from scripts import start_server
from tests.test_round2_permissions import auth
from tests.test_round3_permissions import hr_environment, snapshot

PROXY = '172.19.0.2'
REAL = '198.51.100.24'  # Reserved test address, not a real visitor.
SECOND = '203.0.113.42'
FAKE = '203.0.113.99'
PASSWORD = 'ip-audit-test-password'


def request(peer, headers):
    return {'type':'http','client':(peer,40123) if peer else None,'headers':[(k.lower().encode(),v.encode()) for k,v in headers.items()]}


@pytest.mark.parametrize('peer,headers,expected',[
    (REAL, {}, REAL),
    (REAL, {'X-Forwarded-For':FAKE,'X-Real-IP':FAKE}, REAL),
    ('172.19.0.8', {'X-Forwarded-For':FAKE,'X-Real-IP':FAKE}, '172.19.0.8'),
    (PROXY, {'X-Forwarded-For':REAL,'X-Real-IP':REAL}, REAL),
    (PROXY, {'X-Forwarded-For':f'{FAKE}, {REAL}','X-Real-IP':REAL}, REAL),
    (PROXY, {'X-Forwarded-For':f'{FAKE}, 192.0.2.2, {REAL}','X-Real-IP':REAL}, REAL),
    (PROXY, {'X-Real-IP':REAL}, REAL),
    (PROXY, {}, PROXY),
    (PROXY, {'X-Real-IP':'not-an-ip'}, PROXY),
    (PROXY, {'X-Forwarded-For':f'garbage, {REAL}','X-Real-IP':REAL}, REAL),
    (PROXY, {'X-Forwarded-For':'2001:db8:0000:0000:0000:0000:0000:0024','X-Real-IP':'2001:db8::24'}, '2001:db8::24'),
    (PROXY, {'X-Forwarded-For':f'{REAL}, {PROXY}'}, REAL),
    (None, {'X-Forwarded-For':FAKE}, None),
])
@pytest.mark.parametrize('with_uvicorn',[True,False])
def test_trusted_forwarding_and_spoofing(monkeypatch,peer,headers,expected,with_uvicorn):
    monkeypatch.setenv('FORWARDED_ALLOW_IPS',PROXY)
    scope=request(peer,headers)
    result=[]
    async def capture(scope,receive,send):result.append(get_client_ip(Request(scope)))
    if with_uvicorn:asyncio.run(ProxyHeadersMiddleware(capture,trusted_hosts=PROXY)(scope,None,None))
    else:result.append(get_client_ip(Request(scope)))
    assert result==[expected]


async def audit_rows(factory):
    async with factory() as db:
        return (await db.execute(select(AuditLog).order_by(AuditLog.id))).scalars().all()


async def setup_password(factory):
    async with factory() as db:
        (await db.get(User,1)).password_hash=hash_password(PASSWORD)
        db.add(AuditLog(id=1,user_id=1,warehouse_id=1,action_type='edit',module='legacy',ip_address='172.19.0.9',detail={'old':True}))
        await db.commit()


def test_login_business_operations_two_sources_and_logs_api(tmp_path,monkeypatch):
    async def run():
        monkeypatch.setenv('FORWARDED_ALLOW_IPS',PROXY)
        async with hr_environment(tmp_path,monkeypatch) as (_,factory,_):
            await setup_password(factory);old=await snapshot(factory)
            proxy_app=ProxyHeadersMiddleware(app,trusted_hosts=PROXY)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=proxy_app,client=(PROXY,40123)),base_url='https://test') as c:
                responses=[]
                for real in (REAL,SECOND):
                    # Exactly nginx's output for an attacker sending fake XFF and X-Real-IP:
                    # XFF is appended; X-Real-IP is overwritten with the observed connection.
                    headers={'X-Forwarded-For':f'{FAKE}, {real}','X-Real-IP':real,'X-Forwarded-Proto':'https',**auth(2),'X-Warehouse-ID':'2'}
                    r=await c.post('/api/v1/auth/login',headers=headers,json={'username':'warehouse_admin','password':PASSWORD})
                    assert r.status_code==200 and r.json()['user_id']==1,r.text
                    responses.append(r.json()['access_token'])
                logs=await audit_rows(factory)
                assert len(logs)==3
                assert [r.ip_address for r in logs[1:]]==[REAL,SECOND]
                assert all(r.action_type=='login' and r.user_id==1 and r.warehouse_id==1 and r.module=='auth' and r.created_at for r in logs[1:])
                r=await c.put('/api/v1/customers/1',headers={**auth(1),'X-Warehouse-ID':'1','X-Forwarded-For':f'{FAKE}, {REAL}','X-Real-IP':REAL},json={'company_name':'IP验收客户'})
                assert r.status_code==200,r.text
                listing=await c.get('/api/v1/settings/logs',headers=auth(1));assert listing.status_code==200
                data=listing.json()['data'];assert len(data)==4
                assert next(row for row in data if row['module']=='customers')['ip_address']==REAL
                login_rows=[row for row in data if row['action_type']=='login'];assert len(login_rows)==2
                assert {r['ip_address'] for r in login_rows}=={REAL,SECOND}
                assert (await c.get('/api/v1/settings/logs?action_type=login',headers=auth(1))).json()['total']==2
                after=await audit_rows(factory)
                assert after[0].ip_address=='172.19.0.9' and after[0].detail=={'old':True}
                assert after[-1].action_type=='edit' and after[-1].module=='customers' and after[-1].ip_address==REAL
                details=json.dumps([row.detail for row in after],ensure_ascii=False)
                assert PASSWORD not in details and all(token not in details for token in responses)
                assert 'password' not in details and 'Authorization' not in details
                assert await snapshot(factory)==old
                print('REAL_IP_AUDIT',json.dumps({'environment':'isolated; reserved test addresses','login_rows':login_rows,'write_row':next(row for row in data if row['module']=='customers'),'old_log':next(row for row in data if row['module']=='legacy'),'spoofed_prefix':FAKE},ensure_ascii=False))
    asyncio.run(run())


def test_direct_caller_headers_ignored_and_failed_login_not_logged(tmp_path,monkeypatch):
    async def run():
        monkeypatch.setenv('FORWARDED_ALLOW_IPS',PROXY)
        async with hr_environment(tmp_path,monkeypatch) as (_,f,_):
            await setup_password(f)
            proxy=ProxyHeadersMiddleware(app,trusted_hosts=PROXY)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=proxy,client=(REAL,1)),base_url='http://test') as c:
                body={'username':'warehouse_admin','password':PASSWORD}
                headers={'X-Forwarded-For':FAKE,'X-Real-IP':FAKE}
                r=await c.post('/api/v1/auth/login',headers=headers,json=body);assert r.status_code==200
                assert (await audit_rows(f))[-1].ip_address==REAL
                body['password']='wrong-password'
                assert (await c.post('/api/v1/auth/login',headers=headers,json=body)).status_code==401
                assert len(await audit_rows(f))==2
    asyncio.run(run())


def test_audit_failure_does_not_break_login(tmp_path,monkeypatch):
    async def run():
        import app.core.audit as audit
        async with hr_environment(tmp_path,monkeypatch) as (_,f,c):
            await setup_password(f)
            def fail(_):raise RuntimeError('isolated audit failure')
            monkeypatch.setattr(audit,'get_client_ip',fail)
            r=await c.post('/api/v1/auth/login',json={'username':'warehouse_admin','password':PASSWORD})
            assert r.status_code==200 and r.json()['access_token']
            assert len(await audit_rows(f))==1
    asyncio.run(run())


def test_proxy_resolution_and_startup_command(monkeypatch):
    def resolve(host,*args,**kwargs):
        assert host=='nginx'
        return [(socket.AF_INET,socket.SOCK_STREAM,6,'',(PROXY,0)),(socket.AF_INET6,socket.SOCK_STREAM,6,'',('fd00::2',0,0,0))]
    monkeypatch.setattr(start_server.socket,'getaddrinfo',resolve)
    monkeypatch.setenv('TRUSTED_PROXY_HOSTS','nginx');monkeypatch.delenv('FORWARDED_ALLOW_IPS',raising=False)
    monkeypatch.setattr(start_server.sys,'argv',['start_server.py'])
    called=[]
    monkeypatch.setattr(start_server.os,'execv',lambda executable,args:called.append(args))
    start_server.main()
    assert os.environ['FORWARDED_ALLOW_IPS']==PROXY+',fd00::2'
    assert called[0][1:]==['-m','uvicorn','app.main:app','--host','0.0.0.0','--port','8000','--proxy-headers']
    assert '*' not in os.environ['FORWARDED_ALLOW_IPS']


def test_unresolved_proxy_fails_closed_and_retries(monkeypatch):
    attempts=[]
    def resolve(*args,**kwargs):attempts.append(1);raise socket.gaierror('not ready')
    monkeypatch.setattr(start_server.socket,'getaddrinfo',resolve);monkeypatch.setattr(start_server.time,'sleep',lambda _:None)
    with pytest.raises(RuntimeError,match='无法解析受信任代理'):start_server.resolve_proxy_ips('nginx',attempts=3)
    assert len(attempts)==3


@pytest.mark.parametrize('hosts,extra',[('*',''),('172.16.0.0/12',''),('','*'),('','0.0.0.0/0')])
def test_cannot_start_with_wildcard_or_unbounded_proxy_range(hosts,extra):
    with pytest.raises(ValueError):start_server.resolve_proxy_ips(hosts,extra,attempts=1)


def test_compose_backend_not_published_and_no_business_frontend_or_nginx_changes():
    root=Path(__file__).resolve().parents[2]
    compose=yaml.safe_load((root/'docker-compose.yml').read_text())
    backend=compose['services']['backend']
    assert not backend.get('ports') and backend.get('network_mode')!='host'
    assert backend['environment']['TRUSTED_PROXY_HOSTS']=='nginx'
    assert 'scripts/start_server.py' in backend['command'] and 'scripts/seed.py' in backend['command']
    assert compose['volumes']=={'pgdata':None,'uploads':None}
    for path in ('frontend/src','nginx','backend/app/models','backend/scripts/seed.py','backend/app/api/v1/users.py'):
        assert not subprocess.check_output(['git','diff','2ee4964','--',path],cwd=root),path
    # Authentication/authorization behavior remains identical after removing audit metadata only.
    path='backend/app/api/v1/auth.py'
    class StripAudit(ast.NodeTransformer):
        def visit_AsyncFunctionDef(self,node):
            node.args.args=[a for a in node.args.args if a.arg!='request']
            return self.generic_visit(node)
        def visit_Assign(self,node):
            return None if any(isinstance(t,ast.Attribute) and t.attr.startswith('audit_login_') for t in node.targets) else self.generic_visit(node)
    def functions(source):
        return {n.name:ast.dump(StripAudit().visit(n),include_attributes=False) for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    assert functions((root/path).read_text())==functions(subprocess.check_output(['git','show',f'2ee4964:{path}'],cwd=root,text=True))
