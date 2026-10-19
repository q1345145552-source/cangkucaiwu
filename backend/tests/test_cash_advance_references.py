"""Reverse links use actual payment fields; all reads preserve money and old data."""
import asyncio
import ast
import json
import subprocess
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select, event

from app.database import Base
from app.models import User, CashAdvance, CashAdvanceDocument, EmployeeAdvance
from app.models.payroll import PayrollRecord
from app.services.cash_advance_reference import cash_advance_numbers, cash_advance_reference
from tests.test_round2_permissions import auth, set_perms
from tests.test_reimbursement_payments import environment, approved, upload, pay
from tests.test_cash_advance_repayments import approved as loan
from tests.test_employee_advance_funding import create as advance


async def seed(factory, client):
    for uid in (3, 4):
        await set_perms(factory, uid, ['工资', '员工预支', '报销管理', '垫款单'])
    async with factory() as db:
        first, second = await db.get(PayrollRecord, 1), await db.get(PayrollRecord, 2)
        first.status, first.net_pay, second.net_pay = 'confirmed', 500, 7000
        await db.commit()
    aid = await loan(client, amount=20000)
    paid = await client.post('/api/v1/payroll/2/disburse', headers=auth(1), json={'funding_source':'cash_advance','cash_advance_id':aid})
    assert paid.status_code == 200, paid.text
    company = await client.post('/api/v1/payroll/1/disburse', headers=auth(1), json={'account_id':1})
    assert company.status_code == 200, company.text
    a = await advance(client, funding_source='cash_advance', cash_advance_id=aid, amount=1000)
    assert a.status_code == 200, a.text
    rid = await approved(client, amount=2000)
    payment = await pay(client, rid, await upload(client, rid), funding_source='cash_advance', payment_account_id=None, cash_advance_id=aid)
    assert payment.status_code == 200, payment.text
    return {'cash_advance_id':aid,'advance_id':a.json()['id'],'reimbursement_id':rid}


async def snapshot(factory):
    async with factory() as db:
        return {table.name:[tuple(row) for row in (await db.execute(select(table).order_by(*table.primary_key.columns))).all()]
            for table in Base.metadata.tables.values()}


def test_real_payments_list_details_numbers_company_and_legacy_empty_reads_unchanged(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,factory,c):
            ids=await seed(factory,c);aid=ids['cash_advance_id'];before=await snapshot(factory)
            payroll=(await c.get('/api/v1/payroll',headers=auth(1))).json()['data']
            cash=next(r for r in payroll if r['id']==2)
            company=next(r for r in payroll if r['id']==1)
            legacy=next(r for r in payroll if r['id']==3)
            assert (cash['cash_advance_id'],cash['cash_advance_number'],cash['net_pay'])==(aid,f'#{aid}',7000)
            for row in (company,legacy):assert row['cash_advance_id'] is None and row['cash_advance_number'] is None
            detail=await c.get('/api/v1/payroll/2',headers=auth(1));assert detail.status_code==200 and detail.json()==cash
            a=(await c.get('/api/v1/employee-advances',headers=auth(1))).json()['data'][0]
            assert a['cash_advance_id']==aid and a['cash_advance_number']==f'#{aid}'
            assert (await c.get(f'/api/v1/employee-advances/{a["id"]}',headers=auth(1))).json()==a
            rid=ids['reimbursement_id']
            payments=(await c.get(f'/api/v1/reimbursement/{rid}/payments',headers=auth(1))).json()['data']
            assert len(payments)==1 and payments[0]['cash_advance_id']==aid and payments[0]['cash_advance_number']==f'#{aid}'
            r=(await c.get(f'/api/v1/reimbursement/{rid}',headers=auth(1))).json()
            listing=(await c.get('/api/v1/reimbursement',headers=auth(1))).json()['data']
            assert r['cash_advance_number']==listing[0]['cash_advance_number']==f'#{aid}'
            destination=await c.get(f'/api/v1/cash-advances/{aid}/repayments',headers=auth(1))
            assert destination.status_code==200 and destination.json()['advance']['id']==aid
            assert await snapshot(factory)==before
            print('REVERSE_REFERENCE_ACTUAL',json.dumps({'payroll':cash,'company_payroll':company,'legacy_payroll':legacy,
                'advance':a,'reimbursement_payment':payments[0],'destination':destination.json()['advance'],'all_tables_unchanged_after_reads':True},ensure_ascii=False))
    asyncio.run(run())


@pytest.mark.parametrize('uid',[1,3,4])
def test_permissions_warehouse_isolation_and_unpaid_purpose_links_not_payment_links(tmp_path,monkeypatch,uid):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,f,c):
            ids=await seed(f,c);aid=ids['cash_advance_id']
            async with f() as db:
                db.add(CashAdvanceDocument(cash_advance_id=aid,warehouse_id=1,document_type='payroll',document_id=3,
                    document_number='工资单 #3',title='用途关联尚不代表付款',amount=1234.56,currency='THB'))
                db.add(EmployeeAdvance(id=50,warehouse_id=2,employee_id=2,period='2026-10',amount=10,advance_date=__import__('datetime').date(2026,10,18),status='unpaid',approval_status='approved'))
                await db.commit()
            before=await snapshot(f)
            for route in ('/payroll/2',f'/employee-advances/{ids["advance_id"]}',f'/reimbursement/{ids["reimbursement_id"]}/payments'):
                r=await c.get('/api/v1'+route,headers=auth(uid));assert r.status_code==200,r.text
            assert (await c.get('/api/v1/payroll/10',headers=auth(uid))).status_code==404
            assert (await c.get('/api/v1/employee-advances/50',headers=auth(uid))).status_code==404
            old=(await c.get('/api/v1/payroll/3',headers=auth(uid))).json()
            assert old['cash_advance_id'] is None and old['cash_advance_number'] is None
            for route in ('/payroll/99999','/employee-advances/99999'):
                assert (await c.get('/api/v1'+route,headers=auth(uid))).status_code==404
            if uid in (3,4):
                await set_perms(f,uid,['工资','员工预支','报销管理'])
                # Seeing a reference does not grant access to the advance's contents.
                assert (await c.get(f'/api/v1/cash-advances/{aid}/repayments',headers=auth(uid))).status_code==403
                await set_perms(f,uid,['工资','员工预支','报销管理','垫款单'])
            assert await snapshot(f)==before
    asyncio.run(run())


@pytest.mark.parametrize('uid',[3,4,5])
def test_denied_document_details_remain_denied(tmp_path,monkeypatch,uid):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,f,c):
            if uid!=5:await set_perms(f,uid,[])
            before=await snapshot(f)
            for route in ('/payroll/2','/employee-advances/1'):
                r=await c.get('/api/v1'+route,headers=auth(uid));assert r.status_code==403,r.text
            assert await snapshot(f)==before
    asyncio.run(run())


def test_metadata_batches_same_warehouse_only_and_missing_ids_are_empty(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (engine,f,c):
            aid=await loan(c,amount=10000)
            records=[SimpleNamespace(cash_advance_id=aid,warehouse_id=1) for _ in range(100)]
            records.extend([SimpleNamespace(cash_advance_id=aid,warehouse_id=2),SimpleNamespace(cash_advance_id=99999,warehouse_id=1),SimpleNamespace(cash_advance_id=None,warehouse_id=1)])
            queries=[]
            def count(conn,cursor,statement,*args):
                if 'FROM cash_advances' in statement:queries.append(statement)
            event.listen(engine.sync_engine,'before_cursor_execute',count)
            try:
                async with f() as db:
                    numbers=await cash_advance_numbers(db,records)
                    for row in records[:100]:assert cash_advance_reference(row,numbers)=={'cash_advance_number':f'#{aid}'}
                    for row in records[100:]:assert cash_advance_reference(row,numbers)=={'cash_advance_number':None}
                    assert len(queries)==1
                    assert await cash_advance_numbers(db,[records[-1]])=={}
                    assert len(queries)==1
            finally:event.remove(engine.sync_engine,'before_cursor_execute',count)
    asyncio.run(run())


def test_all_calculation_payment_repayment_and_other_functions_unchanged():
    from tests.non_labor_test_support import without_non_labor_guard
    root=Path(__file__).resolve().parents[2]
    allowed={'payroll.py':{'list_payroll','payroll_detail','reject_labor_management_payroll'},'employee_advance.py':{'list_advances','advance_detail'},
        'reimbursement.py':{'list_reimbursements','get_reimb_detail','payment_history'}}
    def funcs(source,skip):
        return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(without_non_labor_guard(source)).body
            if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name not in skip}
    for name,skip in allowed.items():
        path='backend/app/api/v1/'+name
        assert funcs((root/path).read_text(),skip)==funcs(subprocess.check_output(['git','show','5af2588:'+path],cwd=root,text=True),skip)
    payable='backend/app/api/v1/payable.py'
    assert without_non_labor_guard((root/payable).read_text()) == without_non_labor_guard(
        subprocess.check_output(['git','show','5af2588:'+payable],cwd=root,text=True))
    untouched=['backend/app/models','backend/scripts/seed.py','backend/app/api/v1/cash_advance.py',
        'backend/app/services/payroll_expense.py','backend/app/services/employee_advance_funding.py',
        'backend/app/services/reimbursement_payment.py','frontend/src/app/(dashboard)/cash-advances/page.tsx']
    assert not subprocess.check_output(['git','diff','5af2588','--',*untouched],cwd=root)


@pytest.mark.parametrize('module,function', [('payroll','list_payroll'),('employee_advance','list_advances'),
    ('reimbursement','list_reimbursements'),('reimbursement','get_reimb_detail'),('reimbursement','payment_history')])
def test_every_original_response_field_matches_previous_version(tmp_path,monkeypatch,module,function):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,factory,c):
            ids=await seed(factory,c);before=await snapshot(factory)
            root=Path(__file__).resolve().parents[2]
            baseline=types.ModuleType('previous_reference_'+module)
            exec(compile(subprocess.check_output(['git','show',f'5af2588:backend/app/api/v1/{module}.py'],cwd=root,text=True),
                'previous_reference_'+module,'exec'),baseline.__dict__)
            import importlib
            current=importlib.import_module('app.api.v1.'+module)
            def strip(value):
                if isinstance(value,dict):return {k:strip(v) for k,v in value.items() if k!='cash_advance_number'}
                if isinstance(value,list):return [strip(v) for v in value]
                return value
            async with factory() as db:
                user=await db.get(User,1)
                kwargs={'db':db,'current_user':user}
                if function in ('get_reimb_detail','payment_history'):kwargs['reimb_id']=ids['reimbursement_id']
                old=await getattr(baseline,function)(**kwargs)
                now=await getattr(current,function)(**kwargs)
                assert strip(now)==old
            assert await snapshot(factory)==before
    asyncio.run(run())
