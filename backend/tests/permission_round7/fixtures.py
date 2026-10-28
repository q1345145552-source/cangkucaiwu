"""Synthetic fixture copied from round-one evidence; never writes round-one evidence. Real JWT and DB."""
import os, sys, json, asyncio, uuid, hashlib, traceback, base64
from pathlib import Path
from datetime import date, datetime
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'backend'))
assert Path.cwd()==Path('/private/tmp/permissions-round7-env')
assert not Path('.env').exists(), 'Run from the isolated environment, never load project credentials'
URL=os.environ['ROUND7_DATABASE_URL']
assert urlparse(URL).hostname=='127.0.0.1' and urlparse(URL).path=='/round7' and urlparse(URL).port==65519
os.environ.update(DATABASE_URL=URL,SECRET_KEY='synthetic-round-one-audit-only-signing-key',UPLOAD_DIR=str(Path.cwd()/'uploads'))
import local_guard
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
OUT=ROOT/'docs/permissions-round7-20261028'/os.environ['ROUND7_RUN']
assert not OUT.exists(), 'Never overwrite round7 raw evidence'
OUT.mkdir(parents=True)
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
