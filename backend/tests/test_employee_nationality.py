"""Nationality/document/payment fields: real HTTP and additive migration acceptance."""
import asyncio
import json
import os
from pathlib import Path
import pytest
from sqlalchemy import select, func, text
from app.models import Employee, User
from app.api.v1.employees import IDENTITY_FIELDS
from tests.test_round3_permissions import hr_environment, snapshot
from tests.test_round2_permissions import auth


def new_employee(number, **overrides):
    return {'name':'证件验收员工'+number,'employee_no':'identity-'+number,'password':'test-password',
            'salary_template_id':1,'hire_date':'2026-10-01', **overrides}


def test_acceptance_and_validation(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path,monkeypatch) as (_,factory,client):
            async with factory() as db:
                old=await db.get(Employee,1)
                old.passport_number='LEGACY-PASSPORT'
                old.work_permit_number='LEGACY-PERMIT'
                from datetime import date
                old.passport_expiry=date(2030,1,2)
                old.work_permit_expiry=date(2029,2,3)
                old.passport_photo_path='uploads/1/legacy-passport.jpg'
                old.work_permit_photo_path='uploads/1/legacy-permit.jpg'
                old.myanmar_id='LEGACY-NRC'
                await db.commit()
            prior_payroll=await snapshot(factory)
            actual={}
            async def call(key,method,path='',uid=1,expected=200,**kwargs):
                r=await client.request(method,'/api/v1/employees'+path,headers=auth(uid),**kwargs)
                assert r.status_code==expected,r.text
                actual[key]={'http_status':r.status_code,'body':r.json()}
                return r.json()
            thai=await call('step1_create_thai','POST',json=new_employee('thai',nationality='泰国',thai_id_number='0123456789012',sso_number='SSO-001',bank_account_number='001234567890',bank_name='测试银行',bank_account_holder='测试开户人'))
            assert thai['nationality']=='泰国' and thai['thai_id_number']=='0123456789012' and thai['warnings']==[]
            foreign=await call('step2_create_myanmar','POST',json=new_employee('myanmar',nationality='缅甸',passport_number='MM-TEST-001',passport_expiry='2031-03-04',work_permit_number='WP-TEST-001',work_permit_expiry='2028-04-05',bank_account_number='000111222333'))
            assert foreign['bank_account_number']=='000111222333'
            listed=await call('step1_and_2_saved_documents','GET')
            foreign_saved=next(e for e in listed['data'] if e['id']==foreign['id'])
            assert foreign_saved['passport_number']=='MM-TEST-001' and foreign_saved['passport_expiry']=='2031-03-04'
            assert foreign_saved['work_permit_number']=='WP-TEST-001' and foreign_saved['work_permit_expiry']=='2028-04-05'
            old_saved=next(e for e in listed['data'] if e['id']==1)
            assert all(old_saved[k] is None for k in IDENTITY_FIELDS)
            await call('step3_thai_id_required','POST',json=new_employee('no-id',nationality='泰国',bank_account_number='01234567'),expected=400)
            empty_bank=await call('step3_empty_bank_allowed','POST',json=new_employee('no-bank',nationality='泰国',thai_id_number='1234567890123',bank_account_number='   '))
            assert empty_bank['warnings']==['未填银行账号'] and empty_bank['bank_account_number'] is None
            await call('step4_legacy_edit','PUT','/1',json={'remark':'仅修改备注，不补国籍'})
            listed=await call('step4_legacy_preserved','GET',params={'nationality':'未填'})
            after=next(e for e in listed['data'] if e['id']==1)
            for field in (*IDENTITY_FIELDS,'passport_number','passport_expiry','work_permit_number','work_permit_expiry','passport_photo_path','work_permit_photo_path','myanmar_id'):
                assert after[field]==old_saved[field]
            # Switching nationality preserves both stored identity sets and all document attachments.
            await call('legacy_switch_thai','PUT','/1',json={'nationality':'泰国','thai_id_number':'1234567890123'})
            async with factory() as db:
                old=await db.get(Employee,1)
                assert old.passport_number=='LEGACY-PASSPORT' and old.passport_photo_path=='uploads/1/legacy-passport.jpg'
            await call('legacy_switch_foreign','PUT','/1',json={'nationality':'中国'})
            async with factory() as db:
                assert (await db.get(Employee,1)).thai_id_number=='1234567890123'
            await call('legacy_restore_unspecified','PUT','/1',json={'nationality':None})
            for nationality in ('泰国','缅甸','中国','其他','未填'):
                result=await call('filter_'+nationality,'GET',params={'nationality':nationality})
                assert result['total']==len(result['data'])
                assert all(e['nationality']==nationality if nationality!='未填' else not e['nationality'] for e in result['data'])
            for value in ('123','12345678901234','123456789012a','１２３４５６７８９０１２３'):
                await call('bad_id_'+value,'POST',json=new_employee('invalid',nationality='泰国',thai_id_number=value),expected=400)
            for nationality in ('缅甸','中国','其他'):
                await call('passport_required_'+nationality,'POST',json=new_employee('invalid',nationality=nationality,passport_number='  '),expected=400)
            await call('cannot_clear_required_thai_id','PUT',f"/{thai['id']}",json={'thai_id_number':None},expected=400)
            await call('cannot_clear_required_passport','PUT',f"/{foreign['id']}",json={'passport_number':' '},expected=400)
            await call('invalid_nationality','POST',json=new_employee('invalid',nationality='invalid'),expected=400)
            # Old callers can omit nationality; either identity set also works without choosing it.
            await call('unspecified_with_passport','POST',json=new_employee('unknown-passport',passport_number='UNSPECIFIED-P'))
            await call('unspecified_with_id','POST',json=new_employee('unknown-id',thai_id_number='1234567890123'))
            from tests.test_round2_permissions import set_perms
            await set_perms(factory,4,['员工档案'])
            await call('supervisor_create_foreign','POST',uid=4,expected=403,json=new_employee('supervisor',nationality='中国',passport_number='CN-TEST-001',bank_account_number='00123456'))
            await call('worker_cannot_read_management','GET',uid=5,expected=403)
            await call('foreign_warehouse_cannot_edit','PUT','/2',json={'bank_account_number':'tampered'},expected=403)
            assert await snapshot(factory)==prior_payroll
            async with factory() as db:
                assert (await db.scalar(select(func.count()).select_from(User).where(User.username=='identity-invalid')))==0
            if os.environ.get('EMPLOYEE_IDENTITY_REPORT'):
                Path(os.environ['EMPLOYEE_IDENTITY_REPORT']).write_text(json.dumps(actual,ensure_ascii=False,indent=2))
    asyncio.run(run())


def test_nullable_migration_preserves_all_old_data(tmp_path,monkeypatch):
    if not os.environ.get('INCOMING_TEST_DATABASE_URL'):
        pytest.skip('Requires explicitly configured isolated PostgreSQL')
    from tests.test_incoming_operations import environment
    from app.services.employee_identity_migration import COLUMNS, migrate_employee_identity
    async def run():
        async with environment(tmp_path,monkeypatch) as (engine,factory,client):
            async with factory() as db:
                db.add(Employee(id=10,warehouse_id=1,name='迁移前员工',passport_number='P-OLD',work_permit_number='W-OLD',passport_photo_path='uploads/1/p.jpg',work_permit_photo_path='uploads/1/w.jpg',myanmar_id='NRC-OLD'))
                await db.commit()
            async with engine.begin() as conn:
                for name in COLUMNS:
                    await conn.execute(text(f'ALTER TABLE employees DROP COLUMN {name}'))
                before=[dict(r) for r in (await conn.execute(text('SELECT * FROM employees ORDER BY id'))).mappings()]
                await migrate_employee_identity(conn)
                await migrate_employee_identity(conn)
                after=[dict(r) for r in (await conn.execute(text('SELECT employees.* FROM employees ORDER BY id'))).mappings()]
                assert [{k:v for k,v in r.items() if k not in COLUMNS} for r in after]==before
                assert all(row[name] is None for row in after for name in COLUMNS)
                column_rows=(await conn.execute(text("SELECT column_name,is_nullable,column_default FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='employees'"))).mappings().all()
                assert all(r['is_nullable']=='YES' and r['column_default'] is None for r in column_rows if r['column_name'] in COLUMNS)
                await conn.execute(text("UPDATE employees SET nationality='泰国',thai_id_number='0123456789012',bank_account_number='000123' WHERE id=10"))
                await migrate_employee_identity(conn)
            async with factory() as db:
                saved=await db.get(Employee,10)
                assert saved.bank_account_number=='000123' and saved.passport_number=='P-OLD'
    asyncio.run(run())


@pytest.mark.parametrize('bank_account',[None,'000987654321'])
def test_bank_metadata_does_not_change_salary_or_block_payment(tmp_path,monkeypatch,bank_account):
    from app.models import PaymentAccount
    from app.models.payroll import PayrollRecord
    async def run():
        async with hr_environment(tmp_path,monkeypatch) as (_,factory,client):
            before=await snapshot(factory)
            updated=await client.put('/api/v1/employees/1',headers=auth(1),json={
                'nationality':'泰国','thai_id_number':'0123456789012','bank_account_number':bank_account})
            assert updated.status_code==200,updated.text
            assert await snapshot(factory)==before
            async with factory() as db:
                account=await db.get(PaymentAccount,1)
                account.opening_balance=10000
                account.currency='THB'
                await db.commit()
            from tests.round3_flow_support import prepare_payroll
            await prepare_payroll(factory, client, 2)
            paid=await client.post('/api/v1/payroll/2/disburse',headers=auth(3),json={'account_id':1})
            assert paid.status_code==200,paid.text
            assert paid.json()['net_pay']==1234.56
            async with factory() as db:
                payroll=await db.get(PayrollRecord,2)
                assert payroll.disbursed and payroll.net_pay==1234.56
                assert (await db.get(Employee,1)).bank_account_number==bank_account
    asyncio.run(run())
