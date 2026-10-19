"""第十八轮：仅关闭指定10个可写入口，原权限、仓库和员工自助行为不变。"""
import asyncio
import ast
import json
import os
import re
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import event, select

from app.main import app
from app.core.permissions import require_non_labor
from app.models.expense_fund import ExpenseFund
from app.models.payable import PayableBill
from app.models.recharge import IncomingFlow, ReconciliationResult, RechargeDeclaration
from app.models.reimbursement import Reimbursement, ReimbursementItem, ReimbCategory
from app.models.supplier import Supplier
from tests.test_round2_permissions import auth, set_perms, png
from tests.test_non_labor_guard import environment as batch1_environment, ALL_PERMISSIONS, no_guard
from tests.test_cash_advance_references import snapshot


CASES = [
    ('POST', '/reconciliation/unmatch', '/reconciliation/unmatch?record_id=1', None),
    ('POST', '/expense-fund/accounts/{account_id}/items', '/expense-fund/accounts/1/items',
        {'expense_date':'2026-10-20', 'category':'耗材', 'amount':10, 'description':'隔离测试开销',
         'receipt':'/uploads/fund_receipts/1/1/test.png'}),
    ('PUT', '/reimbursement/{reimb_id}', '/reimbursement/1',
        {'submit_date':'2026-10-20', 'items':[{'category':'交通费', 'amount':20}]}),
    ('POST', '/reimbursement/{reimb_id}/submit', '/reimbursement/1/submit', None),
    ('POST', '/payable/plans', '/payable/plans',
        {'plan_name':'隔离测试付款计划', 'planned_date':'2026-10-20', 'bill_ids':[1]}),
    ('POST', '/upload/recharge-screenshot', '/upload/recharge-screenshot', 'upload'),
    ('GET', '/reimbursement/categories', '/reimbursement/categories', None),
    ('GET', '/payable', '/payable', None),
    ('GET', '/payable/plans', '/payable/plans', None),
    ('GET', '/payable/batch-export', '/payable/batch-export', None),
]
AUTO_CASES = CASES[6:]


@asynccontextmanager
async def environment(tmp_path, monkeypatch):
    async with batch1_environment(tmp_path, monkeypatch) as (engine, factory, client):
        import app.api.v1.expense_fund as fund
        monkeypatch.setattr(fund, 'UPLOAD_DIR', str(tmp_path/'uploads'))
        receipt = tmp_path/'uploads/fund_receipts/1/1/test.png'
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_bytes(png())
        async with factory() as db:
            for fid,wid,uid in ((1,1,4),(2,2,6)):
                db.add(ExpenseFund(id=fid, warehouse_id=wid, employee_id=uid, receive_date=datetime(2026,10,1),
                    amount=1000, remaining_balance=1000, currency='THB', purpose='隔离测试'))
            for rid, wid, uid in ((1,1,5),(2,2,6)):
                db.add(Reimbursement(id=rid, warehouse_id=wid, employee_id=uid,
                    submit_date=datetime(2026,10,20), total_amount=10, status='pending'))
                db.add(ReimbursementItem(reimbursement_id=rid, category='交通费', amount=10))
                db.add(IncomingFlow(id=rid, warehouse_id=wid, received_date=datetime(2026,10,16),
                    amount=100, entrant_id=1, match_status='matched'))
                declaration=await db.get(RechargeDeclaration,rid)
                declaration.match_status='matched'
                db.add(ReconciliationResult(id=rid, warehouse_id=wid, reconciliation_month='2026-10',
                    declaration_id=rid, flow_id=rid, match_status='manual_matched'))
            db.add(Supplier(id=2, warehouse_id=2, name='外仓供应商'))
            for bid,wid,status,paid in ((21,1,'pending',0),(22,2,'pending',0),
                                         (23,1,'paid',100),(24,1,'voided',0)):
                db.add(PayableBill(id=bid, warehouse_id=wid, supplier_id=wid, bill_number=f'EXPIRED-{bid}',
                    bill_date=datetime(2020,1,1), due_date=datetime(2020,1,2), amount=100,
                    status=status, paid_amount=paid))
            await db.commit()
        yield engine, factory, client


async def call(client, case, uid):
    method, _, path, body=case
    kwargs={'headers':auth(uid)}
    if body=='upload':
        kwargs.update(data={'recharge_id':'1'}, files={'file':('test.png',png(),'image/png')})
    elif body is not None:
        kwargs['json']=body
    return await client.request(method,'/api/v1'+path,**kwargs)


def normalized_response(response):
    # 上传仍用原有随机文件名；比较路径结构和全部其他返回值。
    return response.status_code, re.sub(r'[0-9a-f]{32}', '<image-uuid>', response.text)


@pytest.mark.parametrize('case', CASES, ids=lambda c:f'{c[0]} {c[1]}')
def test_labor_all_ten_denied_before_validation_or_writes(tmp_path, monkeypatch, case):
    async def run():
        async with environment(tmp_path,monkeypatch) as (engine,factory,client):
            for uid in (5,6):
                await set_perms(factory,uid,ALL_PERMISSIONS)
            before=await snapshot(factory)
            files_before=sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob('*') if p.is_file())
            writes=[]
            def track(conn,cursor,statement,*args):
                if statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')):
                    writes.append(statement)
            event.listen(engine.sync_engine,'before_cursor_execute',track)
            try:
                for uid in (5,6):
                    response=await call(client,case,uid)
                    assert response.status_code==403 and response.json()=={'detail':'无权访问'},response.text
                    path=re.sub(r'\{[^}]+\}','not-an-id',case[1])
                    response=await client.request(case[0],'/api/v1'+path,
                        headers={**auth(uid),'X-Warehouse-ID':'all'},params={'view':'self'},json={})
                    assert response.status_code==403 and response.json()=={'detail':'无权访问'},response.text
                assert not writes,writes
            finally:
                event.remove(engine.sync_engine,'before_cursor_execute',track)
            assert await snapshot(factory)==before
            assert sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob('*') if p.is_file())==files_before
    asyncio.run(run())


@pytest.mark.parametrize('case', CASES, ids=lambda c:f'{c[0]} {c[1]}')
@pytest.mark.parametrize('uid,granted',[(1,False),(2,False),(3,True),(4,True),(3,False),(4,False)])
def test_every_management_role_preserves_original_response(tmp_path,monkeypatch,case,uid,granted):
    async def run():
        results=[]
        for enabled in (False,True):
            with monkeypatch.context() as scoped:
                if not enabled:
                    scoped.setitem(app.dependency_overrides,require_non_labor,no_guard)
                async with environment(tmp_path/str(enabled),scoped) as (_,factory,client):
                    if granted:
                        await set_perms(factory,uid,ALL_PERMISSIONS)
                    response=await call(client,case,uid)
                    if uid==1 or granted:
                        assert response.status_code==200,response.text
                    if uid==2:
                        assert response.status_code==(200 if case[1]=='/upload/recharge-screenshot' else 403)
                    if uid in (3,4) and not granted:
                        assert response.status_code==403 and '无此操作权限' in response.json()['detail']
                    results.append(normalized_response(response))
        assert results[0]==results[1],results
    asyncio.run(run())


@pytest.mark.parametrize('case',AUTO_CASES,ids=lambda c:f'{c[0]} {c[1]}')
def test_automatic_writes_require_permission_and_remain_scoped_and_idempotent(tmp_path,monkeypatch,case):
    async def run():
        async with environment(tmp_path,monkeypatch) as (engine,factory,client):
            before=await snapshot(factory)
            writes=[]
            def track(conn,cursor,statement,*args):
                if statement.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')):
                    writes.append(statement)
            event.listen(engine.sync_engine,'before_cursor_execute',track)
            try:
                for uid in (5,6,3,4,2):
                    response=await call(client,case,uid)
                    assert response.status_code==403,response.text
                assert not writes,writes
            finally:
                event.remove(engine.sync_engine,'before_cursor_execute',track)
            assert await snapshot(factory)==before
            for uid in (1,3,4):
                if uid!=1:
                    await set_perms(factory,uid,ALL_PERMISSIONS)
                # 单独还原这次请求要处理的测试数据，证明每个授权角色都可触发。
                async with factory() as db:
                    if case[1]=='/reimbursement/categories':
                        for category in (await db.execute(select(ReimbCategory))).scalars().all():
                            await db.delete(category)
                    else:
                        (await db.get(PayableBill,21)).status='pending'
                    await db.commit()
                response=await call(client,case,uid)
                assert response.status_code==200,response.text
                async with factory() as db:
                    if case[1]=='/reimbursement/categories':
                        from app.api.v1.reimbursement import DEFAULT_REIMB_CATEGORIES
                        cats=(await db.execute(select(ReimbCategory))).scalars().all()
                        assert len(cats)==len(DEFAULT_REIMB_CATEGORIES)
                        assert [c.name for c in cats]==DEFAULT_REIMB_CATEGORIES
                        assert all(c.warehouse_id==1 for c in cats)
                    else:
                        assert [(await db.get(PayableBill,bid)).status for bid in (21,22,23,24)]==[
                            'overdue','pending','paid','voided']
                after=await snapshot(factory)
                response=await call(client,case,uid)
                assert response.status_code==200,response.text
                assert await snapshot(factory)==after
                if case[1]=='/payable':
                    assert next(b for b in response.json()['data'] if b['id']==21)['status']=='overdue'
                elif case[1]=='/payable/batch-export':
                    assert next(b for b in response.json()['data'] if b['bill_id']==21)['status']=='overdue'
    asyncio.run(run())


@pytest.mark.parametrize('uid',[1,3,4])
def test_original_id_write_warehouse_checks_remain(tmp_path,monkeypatch,uid):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,factory,client):
            await set_perms(factory,uid,ALL_PERMISSIONS)
            before=await snapshot(factory)
            foreign=[
                ('POST','/reconciliation/unmatch?record_id=2',None),
                ('POST','/expense-fund/accounts/2/items',CASES[1][3]),
                ('PUT','/reimbursement/2',CASES[2][3]),
                ('POST','/reimbursement/2/submit',None),
                ('POST','/payable/plans',{**CASES[4][3],'bill_ids':[22]}),
            ]
            for method,path,body in foreign:
                response=await call(client,(method,path,path,body),uid)
                assert response.status_code==403,response.text
            response=await client.post('/api/v1/upload/recharge-screenshot',headers=auth(uid),
                data={'recharge_id':'2'},files={'file':('test.png',png(),'image/png')})
            assert response.status_code==403,response.text
            assert await snapshot(factory)==before
    asyncio.run(run())


def test_batch_report_all_ten_and_automatic_writes(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,factory,client):
            before=await snapshot(factory)
            rows=[]
            for case in CASES:
                response=await call(client,case,5)
                assert response.status_code==403 and response.json()=={'detail':'无权访问'}
                rows.append({'method':case[0],'path':'/api/v1'+case[1],
                    'labor':{'status':response.status_code,'body':response.json()}})
            assert await snapshot(factory)==before
            for case,row in zip(CASES,rows):
                response=await call(client,case,1)
                assert response.status_code==200,response.text
                row['warehouse_admin']={'status':response.status_code,'body':response.json()}
            async with factory() as db:
                statuses={str(i):(await db.get(PayableBill,i)).status for i in (21,22,23,24)}
                categories=[{'name':c.name,'warehouse_id':c.warehouse_id} for c in
                    (await db.execute(select(ReimbCategory))).scalars().all()]
            assert statuses=={'21':'overdue','22':'pending','23':'paid','24':'voided'}
            report={'environment':'isolated SQLite; synthetic data; no production changes',
                'requests':rows,'denied_requests_all_tables_unchanged':True,
                'automatic_write_results':{'bill_statuses':statuses,'categories':categories}}
        async with environment(tmp_path/'finance',monkeypatch) as (_,factory,client):
            await set_perms(factory,3,ALL_PERMISSIONS)
            checks=[]
            for index in (0,1,2,4,9):
                case=CASES[index]
                response=await call(client,case,3)
                assert response.status_code==200,response.text
                checks.append({'method':case[0],'path':'/api/v1'+case[1],
                    'status':response.status_code,'body':response.json()})
            report['finance_five_actual_requests']=checks
        if os.environ.get('NON_LABOR_BATCH2_REPORT'):
            Path(os.environ['NON_LABOR_BATCH2_REPORT']).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    asyncio.run(run())


def test_only_ten_requested_decorators_added_and_handlers_unchanged():
    from tests.non_labor_test_support import without_non_labor_guard
    from tests.test_non_labor_guard import CASES as BATCH1
    from tests.test_non_labor_read_group1 import CASES as READ_GROUP1
    guarded=[r for r in app.routes if isinstance(r,APIRoute)
        and any(d.call is require_non_labor for d in r.dependant.dependencies)]
    expected={(method,'/api/v1'+template) for method,template,_,_ in BATCH1+CASES+READ_GROUP1}
    from tests.wallet_contract_support import WALLET_GUARDED_ROUTES
    expected.update(WALLET_GUARDED_ROUTES)
    assert {(method,r.path) for r in guarded for method in r.methods}==expected
    for route in guarded:
        assert route.dependant.dependencies[0].call is require_non_labor
    root=Path(__file__).resolve().parents[2]
    for name in ('reconciliation','expense_fund','reimbursement','payable','upload'):
        path='backend/app/api/v1/'+name+'.py'
        old=subprocess.check_output(['git','show','e4a2bb7:'+path],cwd=root,text=True)
        from tests.wallet_contract_support import without_wallet_contract_changes
        assert without_wallet_contract_changes(without_non_labor_guard((root/path).read_text())) == without_wallet_contract_changes(without_non_labor_guard(old)),path
