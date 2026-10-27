"""Round-one observation harness. Real app, JWT auth, isolated PostgreSQL; no business patches.
Run from a fresh directory without .env with explicit local URL. This records current behavior,
not acceptance of future policy. See manifest and expected-current.json for repeatable assertions.
"""
import os, sys, json, asyncio, uuid, hashlib, traceback, base64
from pathlib import Path
from datetime import date, datetime
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'backend'))
assert not Path('.env').exists(), 'Run from the isolated environment, never load project credentials'
URL=os.environ['AUDIT_DATABASE_URL']
assert urlparse(URL).hostname=='127.0.0.1' and urlparse(URL).path=='/audit_round1'
os.environ.update(DATABASE_URL=URL,SECRET_KEY='synthetic-round-one-audit-only-signing-key',UPLOAD_DIR=str(Path.cwd()/'uploads'))
from sqlalchemy import select,text
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from httpx import ASGITransport,AsyncClient
import app.database as database
from app.main import app
import app.api.v1.clock_in as clock_module
import app.api.v1.attendance as attendance_module
clock_module.UPLOAD_DIR=os.environ['UPLOAD_DIR']
attendance_module.UPLOAD_DIR=os.environ['UPLOAD_DIR']
from app.core.security import create_access_token
from app.core.menu_registry import MENU_PERMISSIONS
from app.models import *
from app.models.expense_fund import ExpenseFund,ExpenseFundItem
from app.models.reimbursement import Reimbursement,ReimbursementItem
from app.models.payable import PayableBill,PayablePlan
from app.models.supplier import Supplier
from app.models.payroll import PayrollRecord
from app.models.overtime import OvertimeTask,OvertimeAssignment
from app.models.income_expense import IncomeExpenseCategory
from app.models.expense_approval import ExpenseApproval
from app.models.employee_advance import EmployeeAdvance
OUT=ROOT/'docs/permissions-audit-round1-20261028'
ALL=list(dict.fromkeys([p.label for p in MENU_PERMISSIONS if p.selectable]+[p.key for p in MENU_PERMISSIONS if p.selectable]))
ROLES={1:('warehouse_admin',1),2:('supervisor',1),3:('staff',1),4:('staff',1),5:('warehouse_labor',1),6:('supervisor',1),7:('staff',1),8:('warehouse_admin',2)}
LOG=[];FAIL=[]
STATE_FIELDS={'id','warehouse_id','employee_id','user_id','role','is_active','status','approval_status','review_status','reviewer_id','reviewed_by','approver_id','payer_id','operator_id','paid_by_id','created_by','attendance_enabled','attendance_employee_id','amount','total_amount','paid_amount','net_pay','disbursed','opening_balance','remaining_balance','fund_limit','key','value','updated_by','daily_wage','base_salary','salary_template_id','deduction_template_id','expense_record_id','payment_account_id','account_id','fund_item_id','extra_permissions','actual_hours','confirmed','funding_source'}
def semantic_effects(diff):
    return {table:{side:sorted([{k:v for k,v in row.items() if k in STATE_FIELDS} for row in values],key=lambda x:json.dumps(x,sort_keys=True)) for side,values in change.items()} for table,change in diff.items() if table not in ('audit_logs','data_change_history','cost_identities')}
PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
async def seed(db):
    db.add_all([Warehouse(id=i,name=f'SYNTHETIC WH{i}',code=f'AUDIT{i}') for i in (1,2)]);await db.flush()
    for uid,(role,wid) in ROLES.items():
        db.add(User(id=uid,username=f'audit-{uid}',display_name=f'SYNTHETIC {role} {uid}',role=role,password_hash='not-a-login-password',warehouse_id=wid,extra_permissions=[] if uid in (5,6) else ALL,is_active=uid!=7,attendance_enabled=uid in (2,3,4)))
    await db.flush()
    for uid,(_,wid) in ROLES.items():db.add(UserWarehouse(user_id=uid,warehouse_id=wid))
    for wid in (1,2):
        db.add(SalaryTemplate(id=wid,warehouse_id=wid,name=f'AUDIT SALARY {wid}',type='daily',amount=400))
        db.add(DeductionTemplate(id=wid,warehouse_id=wid,name=f'AUDIT DEDUCT {wid}'))
        db.add(PaymentAccount(id=wid,warehouse_id=wid,account_name=f'SYNTHETIC ACCOUNT {wid}',account_type='cash',account_number='-',currency='THB',opening_balance=100000,opening_balance_date=date(2026,10,1),status='active'))
        db.add(Supplier(id=wid,warehouse_id=wid,name=f'SYNTHETIC SUPPLIER {wid}'))
        for category in ('员工工资','报销','备用金','其他','员工预支'):
            db.add(IncomeExpenseCategory(warehouse_id=wid,type='expense',name=category,category_group='operating',status='active'))
    await db.flush()
    for eid,uid,wid in [(1,5,1),(2,2,1),(3,3,1),(4,4,1),(8,8,2)]:
        db.add(Employee(id=eid,user_id=uid,warehouse_id=wid,name=f'SYNTHETIC EMP {eid}',passport_photo_path=f'uploads/{wid}/audit/passport-{eid}.png',hire_date=datetime(2026,10,1),salary_template_id=wid,deduction_template_id=wid))
    await db.flush()
    for uid in (2,3,4):
        u=await db.get(User,uid);u.attendance_employee_id=uid
    for eid,wid in [(1,1),(2,1),(3,1),(4,1),(8,2)]:
        for d in range(1,16):db.add(RestDay(employee_id=eid,warehouse_id=wid,rest_date=date(2026,10,d)))
    for rid,eid,wid,status,paid in [(1,1,1,'pending',False),(2,1,1,'confirmed',False),(3,2,1,'confirmed',True),(8,8,2,'pending',False)]:
        db.add(PayrollRecord(id=rid,employee_id=eid,warehouse_id=wid,period='2026-10',settle_start_date=date(2026,10,1),settle_end_date=date(2026,10,15),status=status,disbursed=paid,net_pay=100,base_pay=100,gross_pay=100,total_deductions=0,overtime_pay=0,detail='{}'))
    for eid,wid in [(1,1),(2,1),(3,1),(8,2)]:
        db.add(LeaveRequest(id=eid,employee_id=eid,warehouse_id=wid,leave_date=date(2026,10,20),leave_type='personal',duration_type='hours',hours=1,status='pending',notified_at=datetime(2026,10,19)))
    for tid,eid,uid,wid in [(1,1,5,1),(2,2,2,1),(3,3,3,1),(8,8,8,2)]:
        db.add(OvertimeTask(id=tid,warehouse_id=wid,date=date(2026,10,20),start_time='18:00',end_time='19:00',hours=1,hourly_rate=0,status='待核实',needs_verification=True,created_by=1))
        await db.flush()
        db.add(OvertimeAssignment(id=tid,overtime_id=tid,employee_id=eid,user_id=uid,confirmed=False))
    for rid,uid,wid,status in [(1,3,1,'pending'),(2,2,1,'approved'),(3,4,1,'approved'),(8,8,2,'pending')]:
        db.add(Reimbursement(id=rid,employee_id=uid,warehouse_id=wid,submit_date=datetime(2026,10,20),total_amount=100,status=status,currency='THB'))
        await db.flush()
        db.add(ReimbursementItem(id=rid,reimbursement_id=rid,category='其他',amount=100,description='SYNTHETIC',review_status='pending'))
        db.add(PayableBill(id=rid,warehouse_id=wid,supplier_id=wid,bill_number=f'AUDIT-{rid}',bill_date=datetime(2026,10,20),due_date=datetime(2026,10,30),amount=100,currency='THB',matching_kind='non_goods',status='pending',created_by=uid))
        db.add(ExpenseApproval(id=rid,warehouse_id=wid,applicant_id=uid,amount=100,currency='THB',purpose='SYNTHETIC',expense_date=date(2026,10,20),status='pending' if rid==1 else 'approved',fund_source='company'))
    await db.flush()
    db.add(PayablePlan(id=1,warehouse_id=1,plan_name='SYNTHETIC PLAN',planned_date=datetime(2026,10,28),total_amount=100,bill_ids=[3],status='pending',created_by=3))
    db.add(ExpenseFund(id=1,warehouse_id=1,employee_id=3,receive_date=datetime(2026,10,1),amount=500,purpose='SYNTHETIC',remaining_balance=500,fund_limit=5000,currency='THB',status='active'))
    await db.flush()
    db.add(ExpenseFundItem(id=1,fund_id=1,expense_date=datetime(2026,10,20),category='其他',amount=10,currency='THB',description='SYNTHETIC',receipt='/uploads/fund_receipts/1/1/a.png',review_status='pending'))
    for rid,eid,uid in [(1,2,2),(2,3,3)]:db.add(EmployeeAdvance(id=rid,warehouse_id=1,employee_id=eid,amount=100,currency='THB',advance_date=date(2026,10,20),period='2026-10',operator_id=uid,approval_status='pending',funding_source='company_account',payment_account_id=1,expense_tracking_enabled=True))
    await db.commit()
    # Explicit fixture ids must not collide with actual API inserts.
    for table in database.Base.metadata.sorted_tables:
        if 'id' in table.c and str(table.c.id.type)=='INTEGER':
            await db.execute(text(f"SELECT setval(pg_get_serial_sequence('{table.name}', 'id'), COALESCE((SELECT MAX(id) FROM {table.name}),0)+1, false) WHERE pg_get_serial_sequence('{table.name}', 'id') IS NOT NULL"))
    await db.commit()
async def snapshot(factory):
    result={}
    async with factory() as db:
        for table in database.Base.metadata.sorted_tables:
            rows=[dict(r) for r in (await db.execute(select(table))).mappings()]
            for r in rows:
                for k in ('password_hash','line_user_id'):
                    if k in r:r[k]='[synthetic omitted]'
            result[table.name]=sorted(rows,key=lambda r:json.dumps(r,sort_keys=True,default=str))
    return json.loads(json.dumps(result,default=str,ensure_ascii=False))
def flushlog():
    (OUT/'requests.json').write_text(json.dumps(LOG,ensure_ascii=False,indent=2))
    (OUT/'run-status.json').write_text(json.dumps({'requests':len(LOG),'assertion_failures':FAIL,'purpose':'CURRENT BEHAVIOR REPRODUCTION; NOT FUTURE TARGET ACCEPTANCE'},ensure_ascii=False,indent=2))
async def run_group(group,actions):
    schema='audit_'+group.lower()+'_'+uuid.uuid4().hex[:8]
    root=create_async_engine(URL)
    async with root.begin() as c:await c.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine=create_async_engine(URL,connect_args={'server_settings':{'search_path':schema}})
    factory=async_sessionmaker(engine,expire_on_commit=False)
    database._engine=engine;database._session_maker=factory
    try:
        async with engine.begin() as c:await c.run_sync(database.Base.metadata.create_all)
        async with factory() as db:await seed(db)
        async with AsyncClient(transport=ASGITransport(app=app,raise_app_exceptions=False),base_url='http://audit.local') as client:
            for index,action in enumerate(actions,1):
                uid,method,path,payload,*options=action;opt=options[0] if options else {}
                if 'permissions' in opt:
                    async with factory() as db:
                        (await db.get(User,uid)).extra_permissions=opt['permissions']
                        await db.commit()
                before=await snapshot(factory)
                headers={'Authorization':'Bearer '+create_access_token({'sub':str(uid)}),**opt.get('headers',{})}
                kwargs={'headers':headers}
                if payload is not None:kwargs['data' if opt.get('form') else 'json']=payload
                if opt.get('photo'):kwargs['files']={'file':('synthetic.png',PNG,'image/png')}
                response=await client.request(method,path if path.startswith('/uploads/') else '/api/v1'+path,**kwargs)
                after=await snapshot(factory)
                changed={k:{'before':before[k],'after':after[k]} for k in before if before[k]!=after[k]}
                try:body=response.json()
                except Exception:
                    body={'content_type':response.headers.get('content-type'),'bytes':len(response.content),'sha256':hashlib.sha256(response.content).hexdigest()}
                    if 'spreadsheet' in response.headers.get('content-type',''):
                        from openpyxl import load_workbook
                        from io import BytesIO
                        wb=load_workbook(BytesIO(response.content),read_only=True)
                        body['sheets']={s.title:list(s.values)[:8] for s in wb}
                    elif len(response.content)<1000:body['text']=response.text
                case={'id':f'{group}-{index:02d}','uid':uid,'role':ROLES[uid][0],'method':method,'path':path,'payload':payload,'permission_override':opt.get('permissions'),'warehouse_header':headers.get('X-Warehouse-ID'),'status':response.status_code,'response':body,'cache_control':response.headers.get('cache-control'),'changed_tables':list(changed),'database_diff':changed,'schema':schema,'assertions':[]}
                # A denied request must not mutate any business row; GET requests too.
                if response.status_code>=400 or method=='GET':
                    ok=not changed;case['assertions'].append({'denied_or_read_has_no_db_changes':ok})
                    if not ok:FAIL.append(case['id']+': unexpected DB change')
                if 'expected' in opt:
                    ok=response.status_code==opt['expected'];case['assertions'].append({'expected_status':opt['expected'],'passed':ok})
                    if not ok:FAIL.append(case['id']+': status mismatch')
                case['semantic_effects']=semantic_effects(changed)
                LOG.append(case);flushlog();print(case['id'],uid,method,path,response.status_code,list(changed),flush=True)
    finally:
        await engine.dispose()
        async with root.begin() as c:await c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await root.dispose()

def groups():
    account={'account_name':'SYNTHETIC MODIFIED','account_type':'cash','account_number':'-','opening_balance':200000,'currency':'THB'}
    calc={'end_date':'2026-10-15','employee_ids':[4]}
    voucher='uploads/1/audit/reimbursement-payments/receipt.png'
    pay={'funding_source':'company_account','payment_account_id':1,'payment_method':'cash','payment_voucher_path':voucher}
    return {
'T01':[(2,'POST','/users',{'username':'audit-new-finance','password':'synthetic-password','display_name':'SYNTHETIC NEW FINANCE','role':'staff','warehouse_ids':[1],'extra_permissions':ALL}), (2,'DELETE','/users/9',None),(3,'POST','/users',{'username':'audit-new-labor','password':'synthetic-password','display_name':'SYNTHETIC LABOR','role':'warehouse_labor','warehouse_ids':[1]}),(2,'PUT','/users/3',{'is_active':False}),(6,'POST','/users',{'username':'blocked','password':'synthetic-password','display_name':'SYNTHETIC','role':'staff','warehouse_ids':[1]})],
'T02':[(2,'PUT','/accounts/1',account),(2,'PUT','/accounts/1/toggle-status',None),(3,'PUT','/accounts/1/toggle-status',None),(6,'PUT','/accounts/1',account),(2,'PUT','/accounts/2',account),(7,'GET','/accounts',None)],
'T03':[(2,'POST','/expense-fund/accounts',{'employee_id':2}),(2,'POST','/expense-fund/accounts/1/topup',{'amount':100,'payment_account_id':1,'receive_date':'2026-10-28'}),(2,'POST','/expense-fund/review/batch',{'item_ids':[1],'action':'approve'}),(2,'POST','/expense-fund/settings',{'key':'fund_limit','value':'6000'}),(3,'POST','/expense-fund/recharge/request',{'amount':50,'reason':'SYNTHETIC OWN'}),(3,'POST','/expense-fund/recharge/review',{'request_id':1,'action':'approve','payment_account_id':1,'receive_date':'2026-10-28'})],
'T04':[(3,'POST','/payroll/calculate',calc),(2,'POST','/payroll/calculate',calc),(3,'POST','/payroll/1/confirm',None),(2,'POST','/payroll/1/confirm',None),(3,'POST','/payroll/2/disburse',{'account_id':1}),(2,'POST','/payroll/2/disburse',{'account_id':1}),(1,'POST','/payroll/1/disburse',{'account_id':1})],
'T05':[(u,'GET',p,None) for u in (2,3,6,8) for p in ('/payroll','/payroll/1','/payroll/export','/reports/previews')],
'T06':[(3,'POST','/reimbursement/1/review',{'items':[{'item_id':1,'status':'approved'}]}),(3,'POST','/reimbursement/1/pay',pay),(2,'POST','/reimbursement/2/pay',pay),(4,'POST','/reimbursement/3/pay',pay),(3,'PUT','/payable/1/pay?account_id=1&paid_amount=100',None),(2,'PUT','/payable/1/pay?account_id=1&paid_amount=100',None),(3,'PUT','/payable/plans/1/execute?account_id=1',None),(2,'POST','/employee-advances/1/approve',None),(3,'POST','/employee-advances/2/approve',None),(1,'POST','/employee-advances/2/approve',None),(2,'POST','/expense-approvals/1/approve',None),(2,'POST','/expense-approvals/1/pay',{'payment_account_id':1,'voucher_base64':'data:image/png;base64,'+base64.b64encode(PNG).decode()})],
'T07':[(2,'PUT','/attendance/leaves/2/approve',None),(2,'POST','/attendance/leaves/admin-record',{'employee_id':2,'start_date':'2026-10-21','end_date':'2026-10-21','duration_type':'hours','hours':1}),(2,'POST','/overtime/2/verify',{'assignments':[{'assignment_id':2,'actual_hours':1}]}),(2,'POST','/employee-advances/1/approve',None),(2,'POST','/overtime',{'employee_ids':[2],'date':'2026-10-22','start_time':'18:00','end_time':'19:00'})],
'T08':[(2,'PUT','/suppliers/purchase-approval-threshold',{'threshold':0}),(2,'PUT','/suppliers/price-threshold',{'threshold':25}),(2,'PUT','/overtime/limit',{'max_hours':60}),(3,'PUT','/overtime/limit',{'max_hours':70}),(3,'POST','/expense-fund/settings',{'key':'overtime_monthly_limit','value':'70'}),(3,'POST','/expense-fund/settings',{'key':'purchase_approval_threshold','value':'0'}),(2,'PUT','/salary-templates/1',{'amount':999}),(2,'PUT','/employees/1',{'salary_template_id':2})],
'T09':[(u,'GET',p,None) for u in (2,3,4,5,6,7) for p in ('/clock-in/today','/attendance/leaves?view=self','/overtime/pending?view=self','/payroll/my-payslip')],
'T10':[(6,'GET','/accounts',None),(6,'PUT','/accounts/1',account),(2,'GET','/accounts',None),(2,'PUT','/accounts/1',account),(2,'POST','/payroll/batch-confirm',{'record_ids':[1]}),(6,'GET','/accounts',None,{'permissions':['运营收支']}),(6,'PUT','/accounts/1',account,{'permissions':['运营收支']}),(6,'GET','/accounts',None,{'permissions':['收款账户']}),(6,'PUT','/accounts/1',account,{'permissions':['收款账户']})],
'T11':[(2,'GET','/accounts',None,{'headers':{'X-Warehouse-ID':'2'}}),(2,'GET','/employees',None,{'headers':{'X-Warehouse-ID':'2'}}),(2,'GET','/payroll/8',None),(2,'PUT','/attendance/leaves/8/approve',None),(2,'POST','/reimbursement/8/review',{'items':[{'item_id':8,'status':'approved'}]}),(2,'POST','/reimbursement/1/review',{'items':[{'item_id':8,'status':'approved'}]}),(2,'POST','/reimbursement/2/pay',{**pay,'payment_account_id':2}),(2,'PUT','/employees/8',{'name':'SYNTHETIC CROSS WAREHOUSE'})],
'T12':[(2,'POST','/payroll/batch-confirm',{'record_ids':[1,8]}),(2,'GET','/payable/batch-export',None),(2,'GET','/payable/plans/export',None),(2,'GET','/expense-fund/balance',None),(6,'GET','/expense-fund/balance',None),(2,'GET','/clock-in/records/export?start_date=2026-10-01&end_date=2026-10-28',None),(3,'GET','/payable/plans/export',None)],
'T12B':[(u,'GET',p,None) for u in (1,2,3,5,6,7,8) for p in ('/uploads/1/audit/passport-1.png','/uploads/2/audit/passport-8.png')],
'T09B':[(u,'POST','/clock-in',{'session':'1','photo_base64':'data:image/png;base64,'+base64.b64encode(PNG).decode()},{'form':True}) for u in (2,3,5)]+[(u,'POST','/attendance/leaves?view=self',{'leave_date':'2026-10-29','leave_type':'personal','duration_type':'hours','hours':'1','reason':'SYNTHETIC'},{'form':True,'photo':True}) for u in (2,3)],
'T08B':[(2,'PUT','/employees/1',{'daily_wage':987,'base_salary':23456}),(3,'POST','/expense-fund/settings',{'key':'purchase_duty_separation_v1','value':'{}'}),(2,'GET','/supplier-controls/policy',None)],
'T01B':[(2,'POST','/employees/4/resign',{'reason':'voluntary','resignation_date':'2026-10-15'}),(3,'POST','/employees/1/resign',{'reason':'voluntary','resignation_date':'2026-10-15'})],
'T06B':[(3,'POST','/employee-advances',{'employee_id':3,'amount':10,'advance_date':'2026-10-28','funding_source':'company_account','payment_account_id':1}),(2,'POST','/employee-advances',{'employee_id':2,'amount':10,'advance_date':'2026-10-28','funding_source':'company_account','payment_account_id':1}),(2,'POST','/employee-advances',{'employee_id':1,'amount':10,'advance_date':'2026-10-28','funding_source':'company_account','payment_account_id':1}),(3,'POST','/expense-approvals/2/pay',{'payment_account_id':1})],
'T06C':[(2,'POST','/income-expense/expense',{'category_id':'4','account_id':'1','amount':'10','currency':'THB','expense_date':'2026-10-28','request_key':'audit-expense-1','remark':'SYNTHETIC DIRECT PAYMENT'},{'form':True}),(2,'GET','/income-expense/ledger',None),(2,'GET','/reports/operations',None)],
'T05B':[(u,'GET',p,None) for u in (2,3) for p in ('/reports/income-expense?format=excel','/reports/cost-funds-debt','/reports/previews?warehouse_id=2')],
'T06D':[(1,'POST','/reimbursement/1/review',{'items':[{'item_id':1,'status':'approved'}]}),(4,'POST','/reimbursement/1/pay',pay),(4,'POST','/reimbursement/1/pay',pay)],
'T09C':[(3,'POST','/attendance/leaves',{'leave_date':'2026-10-29','leave_type':'personal','duration_type':'hours','hours':'1','reason':'SYNTHETIC LEGACY SELF'},{'form':True,'photo':True})],
'T13':[(u,'POST',p,None) for u in (1,2,3,5,6,7) for p in ('/payroll/3/revoke-disbursement','/reimbursement/2/revoke-payment','/cash-advances/repayments/1/revoke')],
}
async def main():
    for relative in ('1/audit/reimbursement-payments/receipt.png','fund_receipts/1/1/a.png','1/audit/passport-1.png','1/audit/passport-2.png','1/audit/passport-3.png','2/audit/passport-8.png'):
        p=Path(os.environ['UPLOAD_DIR'])/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(PNG)
    (OUT/'roles.json').write_text(json.dumps({'roles':ROLES,'expanded_permissions':ALL,'disabled_uid':7,'no_extra_permissions_uid':6,'employee_bindings':{2:2,3:3,4:4},'identities':'synthetic only'},ensure_ascii=False,indent=2))
    for group,actions in groups().items():
        try:await run_group(group,actions)
        except Exception:
            FAIL.append(group+': fixture/runtime failure');print(traceback.format_exc(),flush=True);flushlog()
    expected_path=Path(__file__).with_name('expected-current.json')
    if expected_path.exists():
        expected=json.loads(expected_path.read_text())
        for r in LOG:
            if r['id'] in expected:
                e=expected[r['id']];ok=(r['status']==e['status'] and r['changed_tables']==e['changed_tables'] and r['semantic_effects']==e['semantic_effects'])
                r['assertions'].append({'current_behavior_baseline':ok})
                if not ok:FAIL.append(r['id']+': current behavior changed')
        if set(expected)!={r['id'] for r in LOG}:FAIL.append('case coverage differs from expected-current.json')
    flushlog();print('REQUESTS',len(LOG),'FAILURES',FAIL,flush=True)
    return bool(FAIL)
if __name__=='__main__':sys.exit(asyncio.run(main()))
