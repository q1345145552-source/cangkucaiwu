"""Actual registered management routes and employee ownership, using loopback native PostgreSQL."""
import asyncio
import base64
import json
import os
import re
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, text, event

from app.main import app
from app.core.menu_registry import MENU_PERMISSIONS
from app.core.permissions import require_non_labor
from app.core.timezone import THAI_TZ
from app.models import (User, UserWarehouse, Employee, PaymentAccount, Customer, SalaryTemplate,
    DeductionTemplate, Supplier, PayableBill, ExpenseFund, ExpenseFundItem, Reimbursement, ClockInRecord,
    LeaveRequest, RestDay, IncomeExpenseCategory, ExpenseRecord, IncomeRecord, CashAdvance)
from app.models.reimbursement import ReimbursementItem
from app.models.payroll import PayrollRecord
from app.models.employee_advance import EmployeeAdvance
from app.models.overtime import OvertimeTask, OvertimeAssignment
from app.models.data_change_history import DataChangeHistory
from app.models.market import MarketItem
from app.models.group_order import GroupOrder
from app.models.group_order import GroupOrderParticipant
from app.database import Base
from tests.test_incoming_operations import environment, URL
from tests.test_round2_permissions import auth, png

pytestmark = pytest.mark.skipif(not URL, reason="Requires explicitly configured loopback native PostgreSQL")
PERMISSIONS = [p.label for p in MENU_PERMISSIONS if p.selectable]
REPORT = {}


def actual(name, value):
    REPORT[name] = value
    if os.environ.get("MANAGEMENT_TEST_REPORT"):
        Path(os.environ["MANAGEMENT_TEST_REPORT"]).write_text(json.dumps(REPORT,ensure_ascii=False,indent=2,default=str))


def routes():
    return [r for r in app.routes if isinstance(r,APIRoute)]


def management_routes():
    return [r for r in routes() if (r.openapi_extra or {}).get("x-access-kind") in ("business_management","platform_management","shared_platform")]


@asynccontextmanager
async def management_environment(tmp_path, monkeypatch):
    import app.api.v1.clock_in as clock
    import app.api.v1.attendance as attendance
    import app.api.v1.overtime as overtime
    import app.api.v1.upload as upload
    folder=tmp_path/"uploads"
    folder.mkdir(parents=True,exist_ok=True)
    monkeypatch.setenv("UPLOAD_DIR",str(folder))
    for module in (clock,attendance,upload):
        monkeypatch.setattr(module,"UPLOAD_DIR",str(folder))
    for module in (clock,attendance,overtime):
        monkeypatch.setattr(module,"thai_now",lambda:datetime(2026,10,20,9,0,tzinfo=THAI_TZ))
        monkeypatch.setattr(module,"thai_today",lambda:date(2026,10,20))
    async with environment(tmp_path,monkeypatch) as (engine,factory,client):
        async with factory() as db:
            db.add_all([User(id=6,username="labor-b",display_name="Somchai",password_hash="unused",warehouse_id=1,role="warehouse_labor"),
                User(id=8,username="labor-c",display_name="Somchai",password_hash="unused",warehouse_id=2,role="warehouse_labor")])
            await db.flush()
            db.add_all([UserWarehouse(user_id=6,warehouse_id=1),UserWarehouse(user_id=8,warehouse_id=2)])
            for uid in (3,4,5,6,8):
                user=await db.get(User,uid)
                user.extra_permissions=PERMISSIONS
                if uid==5: user.display_name="Somchai"
            (await db.get(PaymentAccount,1)).opening_balance=20000
            db.add(Customer(id=2,warehouse_id=2,customer_code="FOREIGN",company_name="SECRET-WH2-CUSTOMER"))
            for wid in (1,2):
                db.add(SalaryTemplate(id=wid,warehouse_id=wid,name=f"salary-{wid}",type="daily",amount=400))
                db.add(DeductionTemplate(id=wid,warehouse_id=wid,name=f"deduction-{wid}"))
                db.add(IncomeExpenseCategory(id=wid,warehouse_id=wid,type="expense",name="运营支出",category_group="operating"))
                db.add(Supplier(id=wid,warehouse_id=wid,name="supplier" if wid==1 else "SECRET-WH2-SUPPLIER"))
                db.add(ExpenseFund(id=wid,warehouse_id=wid,employee_id=4 if wid==1 else 7,receive_date=datetime(2026,10,1),
                    amount=1000,remaining_balance=1000,currency="THB",purpose="test"))
            await db.flush()
            for eid,uid,wid in ((1,5,1),(2,8,2),(3,6,1)):
                db.add(Employee(id=eid,warehouse_id=wid,name="Somchai",user_id=uid,hire_date=datetime(2026,10,1),status="regular",salary_template_id=wid,deduction_template_id=wid))
            await db.flush()
            for wid,uid in ((1,5),(2,8)):
                marker="local" if wid==1 else "SECRET-WH2"
                path=f"uploads/{wid}/2026-10-19/{marker}-clock.png"
                local=folder.joinpath(*Path(path).parts[1:]);local.parent.mkdir(parents=True,exist_ok=True);local.write_bytes(png())
                db.add(ClockInRecord(id=wid,user_id=uid,warehouse_id=wid,clock_date=date(2026,10,19),session=1,
                    clocked_in_at=datetime(2026,10,19,9),status="normal",photo_path=path))
                db.add(PayrollRecord(id=wid,warehouse_id=wid,employee_id=wid,period="2026-10",half="first_half",net_pay=400,status="pending",detail="{}"))
                db.add(EmployeeAdvance(id=wid,warehouse_id=wid,employee_id=wid,period="2026-10",advance_date=date(2026,10,19),amount=100,source="supervisor",status="unpaid"))
                db.add(LeaveRequest(id=wid,warehouse_id=wid,employee_id=wid,leave_date=date(2026,10,21),leave_type="personal",status="pending",duration_type="hours",hours=1))
                db.add(RestDay(id=wid,warehouse_id=wid,employee_id=wid,rest_date=date(2026,10,18)))
                db.add(OvertimeTask(id=wid,warehouse_id=wid,date=date(2026,10,19),start_time="18:00",end_time="19:00",hours=1,created_by=1,status="已核实",needs_verification=False))
                db.add(Reimbursement(id=wid,warehouse_id=wid,employee_id=4 if wid==1 else 7,submit_date=datetime(2026,10,19),total_amount=200,status="pending"))
                db.add(PayableBill(id=wid,warehouse_id=wid,supplier_id=wid,bill_number=marker,bill_date=datetime(2026,10,1),due_date=datetime(2026,12,30),amount=300))
                db.add(ExpenseFundItem(id=wid,fund_id=wid,expense_date=datetime(2026,10,19),category="耗材",amount=10,description=marker,review_status="pending"))
                db.add(CashAdvance(id=wid,warehouse_id=wid,payer_id=4 if wid==1 else 7,payer_name=marker,advance_date=date(2026,10,1),amount=1000,
                    currency="THB",purpose="salary",status="confirmed",created_by_id=1,created_by_name="test"))
                db.add(MarketItem(id=wid,warehouse_id=wid,uploader_id=1 if wid==1 else 7,name=marker,quantity=1,price=100,status="approved"))
                db.add(GroupOrder(id=wid,warehouse_id=wid,initiator_id=1 if wid==1 else 7,item_name=marker,target_quantity=10,target_price=100,deadline=datetime(2026,12,30)))
                db.add(DataChangeHistory(id=wid,warehouse_id=wid,module="employees",record_id=wid,operator_id=1,operation_type="create",after_data={"marker":marker}))
            await db.flush()
            for wid,uid in ((1,5),(2,8)):
                db.add(OvertimeAssignment(id=wid,overtime_id=wid,employee_id=wid,user_id=uid,actual_hours=1,earned_amount=50))
                db.add(ReimbursementItem(id=wid,reimbursement_id=wid,category="交通费",amount=200,description="test"))
            db.add(OvertimeTask(id=3,warehouse_id=1,date=date(2026,10,18),start_time="18:00",end_time="19:00",hours=1,created_by=1,status="已核实",needs_verification=False))
            await db.flush()
            db.add(OvertimeAssignment(id=3,overtime_id=3,employee_id=1,user_id=5,actual_hours=1,earned_amount=50))
            await db.commit()
            # Explicit IDs above must not collide with later real API inserts.
            for table in Base.metadata.tables.values():
                if "id" not in table.c:continue
                sequence=(await db.execute(text("SELECT pg_get_serial_sequence(:table,'id')"),{"table":table.name})).scalar()
                if sequence:
                    await db.execute(text(f'SELECT setval(CAST(:sequence AS regclass), GREATEST((SELECT coalesce(max(id),0) FROM "{table.name}"),1))'),{"sequence":sequence})
            await db.commit()
        async with AsyncClient(transport=ASGITransport(app=app),base_url="http://isolated-test") as http:
            yield engine,factory,http


def concrete(route, number=1):
    return re.sub(r"\{[^}]+\}",str(number),route.path)


def test_all_registered_management_routes_deny_labor_before_business_queries(tmp_path,monkeypatch):
    async def run():
        async with management_environment(tmp_path,monkeypatch) as (engine,factory,client):
            tested=[];statements=[]
            def trace(conn,cursor,statement,*args):statements.append(statement)
            event.listen(engine.sync_engine,"before_cursor_execute",trace)
            try:
                for route in management_routes():
                    for method in sorted(route.methods):
                        outcomes=[]
                        for uid in (5,8):
                            response=await client.request(method,concrete(route,2),headers={**auth(uid),"X-Warehouse-ID":"all"},
                                params={"view":"self","warehouse_id":2,"employee_id":2},json={"employee_ids":[1,2],"record_ids":[1,2]})
                            assert response.status_code==403 and response.json()=={"detail":"无权访问"},(method,route.path,response.status_code,response.text)
                            outcomes.append(response.status_code)
                        tested.append({"method":method,"path":route.path,"module":route.endpoint.__module__.rsplit('.',1)[-1],"labor_same_and_foreign":outcomes})
                assert len(tested)==334  # Round 11 adds customer receivables and explicit receipt linking.
                for statement in statements:
                    assert not statement.lstrip().upper().startswith(("INSERT","UPDATE","DELETE")),statement
                    assert set(re.findall(r"\b(?:FROM|JOIN)\s+(\w+)",statement,re.I)) <= {"users","user_warehouses"},statement
            finally:event.remove(engine.sync_engine,"before_cursor_execute",trace)
            actual("management_labor_inventory",{"routes":len(tested),"requests":len(tested)*2,"business_queries":0,"data":tested})
    asyncio.run(run())


def test_all_business_management_rejects_super_but_system_account_management_remains(tmp_path,monkeypatch):
    async def run():
        async with management_environment(tmp_path,monkeypatch) as (_,factory,client):
            tested=[]
            for route in management_routes():
                if route.openapi_extra["x-access-kind"]!="business_management":continue
                for method in route.methods:
                    response=await client.request(method,concrete(route),headers=auth(2),json={})
                    assert response.status_code==403 and "超级管理员" in response.text,(route.path,response.status_code,response.text)
                    tested.append(route.path)
            for path in ("/users","/users/permissions","/warehouses","/history","/settings/logs","/settings/boss-contact"):
                response=await client.get("/api/v1"+path,headers=auth(2))
                assert response.status_code==200,(path,response.status_code,response.text)
            actual("super_admin",{"business_denied":len(tested),"platform_reads":6})
    asyncio.run(run())


READS = ["/users","/customers","/accounts","/suppliers","/recharge","/incoming",
    "/reconciliation/results","/income-expense/expense","/income-expense/ledger","/expense-fund/accounts",
    "/reimbursement","/payable","/payable/plans","/credit","/market","/group-order",
    "/reports/previews","/reports/income-expense","/reports/cost-funds-debt","/settings/logs",
    "/config/work-schedule","/rates","/employees","/clock-in/records","/attendance/calendar",
    "/attendance/leaves","/attendance/rest-days","/overtime","/payroll","/history","/efficiency/standard",
    "/employee-advances","/salary-templates","/deduction-templates","/employee-deductions","/expense-approvals","/cash-advances"]


def test_admin_and_authorized_office_reads_and_revoked_permissions(tmp_path,monkeypatch):
    async def run():
        async with management_environment(tmp_path,monkeypatch) as (_,factory,client):
            results=[]
            for uid in (1,3,4):
                for path in READS:
                    response=await client.get("/api/v1"+path,headers=auth(uid),params={"start_date":"2026-10-19","end_date":"2026-10-20","month":"2026-10"})
                    assert response.status_code==200,(uid,path,response.status_code,response.text)
                    # Cross-warehouse commerce is an explicit existing product policy, pending user decision.
                    if path not in ("/market","/group-order"):
                        assert "SECRET-WH2" not in response.text,(uid,path,response.text)
                    results.append({"user":uid,"path":path,"status":response.status_code})
            for uid in (3,4):
                async with factory() as db:
                    (await db.get(User,uid)).extra_permissions=[]
                    await db.commit()
                for path in READS:
                    response=await client.get("/api/v1"+path,headers=auth(uid),params={"start_date":"2026-10-19","end_date":"2026-10-20","month":"2026-10"})
                    assert response.status_code==403 and "无此操作权限" in response.text,(uid,path,response.status_code,response.text)
            actual("office_positive_and_revoke",{"admin_granted_finance_granted_supervisor":results,"ungranted_requests":2*len(READS)})
    asyncio.run(run())


def test_employee_self_records_and_other_people_are_never_visible(tmp_path,monkeypatch):
    async def run():
        async with management_environment(tmp_path,monkeypatch) as (_,factory,client):
            requests=[]
            params={"start_date":"2026-10-19","end_date":"2026-10-20","month":"2026-10",
                "employee_id":2,"user_id":8,"warehouse_id":2,"view":"self"}
            for path in ("/clock-in/today","/clock-in/records","/attendance/calendar","/attendance/leaves","/attendance/rest-days",
                "/overtime","/overtime/pending","/overtime/monthly-hours","/overtime/limit","/payroll/my-payslip","/employee-advances/my-debt"):
                response=await client.get("/api/v1"+path,headers={**auth(5),"X-Warehouse-ID":"2","X-Language":"th"},params=params)
                assert response.status_code==200,(path,response.status_code,response.text)
                assert "SECRET-WH2" not in response.text
                data=response.json()
                if path=="/payroll/my-payslip":assert [r['id'] for r in data['data']]==[1]
                if path=="/employee-advances/my-debt":assert [r['id'] for r in data['data']]==[1]
                if path=="/attendance/calendar":assert {r['id'] for r in data['employees']}=={1}
                requests.append({"path":path,"status":200})
            for eid in (2,3):
                response=await client.get('/api/v1/clock-in/photos',headers=auth(5),params={"employee_id":eid,"date":"2026-10-19"})
                assert response.status_code==403,response.text
            own=await client.get('/api/v1/clock-in/photos',headers=auth(5),params={"employee_id":1,"date":"2026-10-19"})
            assert own.status_code==200,own.text
            for tid in (2,999):
                response=await client.post(f'/api/v1/overtime/{tid}/confirm',headers=auth(5))
                assert response.status_code in (403,404),response.text
                response=await client.post(f'/api/v1/overtime/{tid}/dispute',headers=auth(5),data={"reason":"test"})
                assert response.status_code in (403,404),response.text
            image="data:image/png;base64,"+base64.b64encode(png()).decode()
            punched=await client.post('/api/v1/clock-in',headers={**auth(5),"X-Language":"th","X-Warehouse-ID":"2"},
                data={"session":"1","photo_base64":image,"user_id":"8","employee_id":"2"})
            assert punched.status_code==200,punched.text
            leave=await client.post('/api/v1/attendance/leaves',headers={**auth(5),"X-Language":"th"},
                data={"leave_date":"2026-10-22","leave_type":"personal","duration_type":"hours","hours":"1","employee_id":"2"})
            assert leave.status_code==200,leave.text
            async with factory() as db:
                recorded=await db.get(LeaveRequest,leave.json()['id'])
                assert recorded.employee_id==1 and recorded.warehouse_id==1 and recorded.status=="pending"
                punch=(await db.execute(select(ClockInRecord).where(ClockInRecord.clock_date==date(2026,10,20)))).scalar_one()
                assert punch.user_id==5 and punch.warehouse_id==1
            confirm=await client.post('/api/v1/overtime/1/confirm',headers=auth(5))
            assert confirm.status_code==200,confirm.text
            dispute=await client.post('/api/v1/overtime/3/dispute',headers={**auth(5),'X-Language':'th'},data={'reason':'test hours'},files={'file':('test.png',png(),'image/png')})
            assert dispute.status_code==200,dispute.text
            actual("employee_self",{"reads":requests,"foreign_and_same_warehouse_photos":403,"clock":punched.json(),"leave":leave.json(),"confirm":confirm.json(),'dispute':dispute.json()})
    asyncio.run(run())


def test_granted_office_writes_still_work_and_revocation_denies_them(tmp_path,monkeypatch):
    async def run():
        async with management_environment(tmp_path,monkeypatch) as (_,factory,client):
            cases=[('PUT','/employees/1',{'remark':'office test'}),
                ('PUT','/customers/1',{'company_name':'local customer'}),
                ('PUT','/accounts/1',{'account_name':'local cash','account_type':'cash','account_number':'cash'}),
                ('PUT','/salary-templates/1',{'name':'local salary'}),
                ('PUT','/deduction-templates/1',{'name':'local deduction'}),
                ('PUT','/efficiency/standard',{'standard':450}),
                ('PUT','/suppliers/1',{'name':'local supplier'})]
            results=[]
            for uid in (1,3,4):
                for method,path,body in cases:
                    response=await client.request(method,'/api/v1'+path,headers=auth(uid),json=body)
                    assert response.status_code==200,(uid,path,response.status_code,response.text)
                    results.append({'user':uid,'method':method,'path':path,'status':200})
                uploaded=await client.post('/api/v1/upload',headers=auth(uid),files={'file':('test.png',png(),'image/png')})
                assert uploaded.status_code==200,uploaded.text
                image=await client.get('/'+uploaded.json()['path'],headers=auth(uid))
                assert image.status_code==200,image.text
            for uid in (3,4):
                async with factory() as db:
                    (await db.get(User,uid)).extra_permissions=[]
                    await db.commit()
                for method,path,body in cases:
                    response=await client.request(method,'/api/v1'+path,headers=auth(uid),json=body)
                    assert response.status_code==403 and '无此操作权限' in response.text,(uid,path,response.status_code,response.text)
                uploaded=await client.post('/api/v1/upload',headers=auth(uid),files={'file':('test.png',png(),'image/png')})
                assert uploaded.status_code==403
            actual('office_positive_writes',{'writes':results,'upload_and_private_preview':3,'revoked_writes':16})
    asyncio.run(run())


def test_attachments_are_private_scoped_and_browser_cookie_is_file_only(tmp_path,monkeypatch):
    async def run():
        async with management_environment(tmp_path,monkeypatch) as (_,factory,client):
            own='/uploads/1/2026-10-19/local-clock.png'
            foreign='/uploads/2/2026-10-19/SECRET-WH2-clock.png'
            assert (await client.get(own)).status_code==401
            for uid in (1,3,4,5):assert (await client.get(own,headers=auth(uid))).status_code==200
            for uid in (1,3,4,5,6,2):
                response=await client.get(foreign,headers=auth(uid))
                assert response.status_code==403,(uid,response.text)
            assert (await client.get(own,headers=auth(6))).status_code==403
            # Attendance-enabled supervisors retain their own employee photos without management grants.
            async with factory() as db:
                supervisor=await db.get(User,4)
                supervisor.attendance_enabled=True
                supervisor.attendance_employee_id=3
                supervisor.extra_permissions=[]
                (await db.get(Employee,3)).user_id=4
                record=await db.get(ClockInRecord,1)
                record.user_id=4
                await db.commit()
            assert (await client.get(own,headers=auth(4))).status_code==200
            assert (await client.get(foreign,headers=auth(4))).status_code==403
            async with factory() as db:
                (await db.get(ClockInRecord,1)).user_id=5
                await db.commit()
            async with factory() as db:
                (await db.get(User,3)).extra_permissions=[]
                await db.commit()
            assert (await client.get(own,headers=auth(3))).status_code==403
            session=await client.post('/api/v1/auth/attachment-session',headers=auth(5),json={})
            assert session.status_code==200 and 'HttpOnly' in session.headers['set-cookie'] and 'Path=/uploads' in session.headers['set-cookie']
            response=await client.get(own)
            assert response.status_code==200 and response.content==png() and response.headers['cache-control']=='private, no-store'
            # That cookie does not authenticate API writes or reopen any management endpoint.
            assert (await client.get('/api/v1/employees')).status_code in (401,403)
            assert (await client.post('/api/v1/auth/attachment-session',headers=auth(5),json={"clear":True})).status_code==200
            assert (await client.get(own)).status_code==401
            assert (await client.get('/uploads/1/../../../etc/passwd',headers=auth(1))).status_code in (403,404)
            actual("attachments",{"anonymous":401,"own_labor":200,"different_labor_same_warehouse":403,"cross_warehouse":403,
                "super_admin_business_photo":403,"permission_revoked":403,"attendance_supervisor_own_without_management_permission":200,
                "http_only_file_session":True,"public_nginx_alias_removed":True})
    asyncio.run(run())


def test_attendance_supervisor_self_service_needs_no_management_grant_and_old_token_is_revoked(tmp_path,monkeypatch):
    async def run():
        async with management_environment(tmp_path,monkeypatch) as (_,factory,client):
            async with factory() as db:
                supervisor=await db.get(User,4)
                supervisor.attendance_enabled=True
                supervisor.attendance_employee_id=1
                supervisor.extra_permissions=[]
                (await db.get(Employee,1)).user_id=4
                (await db.get(ClockInRecord,1)).user_id=4
                for aid in (1,3):(await db.get(OvertimeAssignment,aid)).user_id=4
                await db.commit()
            paths=['/clock-in/today','/clock-in/records','/attendance/calendar','/attendance/leaves','/attendance/rest-days',
                '/overtime','/overtime/pending','/overtime/monthly-hours','/overtime/limit','/payroll/my-payslip','/employee-advances/my-debt']
            params={'view':'self','employee_id':2,'warehouse_id':2,'start_date':'2026-10-19','end_date':'2026-10-20'}
            for path in paths:
                response=await client.get('/api/v1'+path,headers=auth(4),params=params)
                assert response.status_code==200 and 'SECRET-WH2' not in response.text,(path,response.status_code,response.text)
                if path=='/attendance/calendar':assert [e['id'] for e in response.json()['employees']]==[1]
            image='data:image/png;base64,'+base64.b64encode(png()).decode()
            clock=await client.post('/api/v1/clock-in?view=self',headers=auth(4),data={'session':'1','photo_base64':image})
            assert clock.status_code==200,clock.text
            leave=await client.post('/api/v1/attendance/leaves?view=self',headers=auth(4),data={'leave_date':'2026-10-22','leave_type':'personal','duration_type':'hours','hours':'1'})
            assert leave.status_code==200,leave.text
            assert (await client.post('/api/v1/overtime/1/confirm?view=self',headers=auth(4))).status_code==200
            dispute=await client.post('/api/v1/overtime/3/dispute?view=self',headers=auth(4),data={'reason':'test'},files={'file':('test.png',png(),'image/png')})
            assert dispute.status_code==200,dispute.text
            async with factory() as db:
                (await db.get(User,4)).attendance_enabled=False
                await db.commit()
            for path in paths:
                assert (await client.get('/api/v1'+path,headers=auth(4),params=params)).status_code==403
            for uid in (1,2,3):
                assert (await client.get('/api/v1/payroll/my-payslip?view=self',headers=auth(uid))).status_code==403
            actual('attendance_supervisor_self',{'reads':11,'clock':200,'leave':200,'confirm':200,'dispute':200,'management_permissions':[],
                'disabled_with_same_token':403,'admin_super_finance_personal_payslip':403})
    asyncio.run(run())


def test_legacy_employee_fallback_is_unique_and_cannot_borrow_bound_same_name(tmp_path,monkeypatch):
    async def run():
        async with management_environment(tmp_path,monkeypatch) as (_,factory,client):
            async with factory() as db:
                employee=await db.get(Employee,1)
                employee.user_id=None
                employee.phone='test-5'
                await db.commit()
            own=await client.get('/api/v1/payroll/my-payslip',headers=auth(5))
            assert own.status_code==200 and [p['id'] for p in own.json()['data']]==[1]
            async with factory() as db:
                (await db.get(Employee,1)).phone=None
                db.add(Employee(warehouse_id=1,name='Somchai',status='regular'))
                await db.commit()
            ambiguous=await client.get('/api/v1/payroll/my-payslip',headers={**auth(5),'X-Language':'th'})
            assert ambiguous.status_code==403 and not re.search(r'[\u3400-\u9fff]',ambiguous.json()['detail'])
            bound=await client.get('/api/v1/payroll/my-payslip',headers=auth(6))
            assert bound.status_code==200 and bound.json()['data']==[]
            actual('legacy_employee_binding',{'unique_username_phone':200,'ambiguous_unbound_name':403,'formal_same_name_other_account_only_own':200})
    asyncio.run(run())


def test_mixed_warehouse_batches_reject_without_partial_changes(tmp_path,monkeypatch):
    async def run():
        async with management_environment(tmp_path,monkeypatch) as (_,factory,client):
            cases=[('POST','/employees/batch-set-templates',{'employee_ids':[1,2],'salary_template_id':1,'deduction_template_id':1}),
                ('POST','/payroll/batch-confirm',{'record_ids':[1,2]}),
                ('POST','/payroll/batch-disburse',{'record_ids':[1,2],'account_id':1}),
                ('POST','/payroll/batch-delete',{'record_ids':[1,2]}),
                ('POST','/clock-in/batch-makeup',{'date':'2026-10-19','employee_ids':[1,2],'sessions':[1,4],'reason':'test'}),
                ('POST','/overtime',{'date':'2026-10-19','employee_ids':[1,2],'start_time':'18:00','end_time':'19:00'})]
            outcomes=[]
            for method,path,body in cases:
                result=await client.request(method,'/api/v1'+path,headers=auth(1),json=body)
                assert result.status_code in (400,403,404),(path,result.status_code,result.text)
                outcomes.append({'path':path,'status':result.status_code,'body':result.json()})
            async with factory() as db:
                assert (await db.get(PayrollRecord,1)).status=='pending'
                assert not (await db.get(PayrollRecord,1)).disbursed
                assert (await db.get(Employee,1)).salary_template_id==1
                assert (await db.get(Employee,2)).salary_template_id==2
            actual('mixed_warehouse_batches',outcomes)
    asyncio.run(run())


def test_single_permissions_keep_shared_selectors_working(tmp_path,monkeypatch):
    async def run():
        async with management_environment(tmp_path,monkeypatch) as (_,factory,client):
            checked=[]
            for uid in (3,4):
                for permission,path in [("充值申报","/customers"),("到账流水","/customers"),("账期管理","/customers"),
                    ("运营收支","/accounts"),("其他收支","/accounts"),("费用审批","/accounts"),("工资","/accounts"),
                    ("应付账款","/suppliers"),("付款计划","/suppliers")]:
                    async with factory() as db:
                        (await db.get(User,uid)).extra_permissions=[permission]
                        await db.commit()
                    response=await client.get('/api/v1'+path,headers=auth(uid))
                    assert response.status_code==200 and 'SECRET-WH2' not in response.text,(uid,permission,path,response.status_code,response.text)
                    checked.append({'user':uid,'permission':permission,'path':path,'status':200})
            actual('shared_selectors',checked)
    asyncio.run(run())


def test_foreign_details_updates_and_photos_rejected_for_all_office_roles(tmp_path,monkeypatch):
    async def run():
        async with management_environment(tmp_path,monkeypatch) as (_,factory,client):
            cases=[('GET','/customers/2',None),('PUT','/customers/2',{'company_name':'must-not-save'}),
                ('PUT','/accounts/2',{'account_name':'must-not-save','account_type':'cash','account_number':'-'}),
                ('PUT','/suppliers/2',{'name':'must-not-save'}),('GET','/employees/2/summary',None),
                ('PUT','/employees/2',{'name':'must-not-save'}),('GET','/payroll/2',None),
                ('GET','/reimbursement/2',None),('GET','/expense-fund/accounts/2/items',None),
                ('GET','/cash-advances/2/repayments',None),('GET','/employee-advances/2',None),
                ('PUT','/salary-templates/2',{'amount':999}),('PUT','/deduction-templates/2',{'name':'must-not-save'})]
            checked=[]
            for uid in (1,3,4):
                for method,path,body in cases:
                    kwargs={'json':body} if body is not None else {}
                    response=await client.request(method,'/api/v1'+path,headers=auth(uid),**kwargs)
                    assert response.status_code in (400,403,404),(uid,method,path,response.status_code,response.text)
                    assert 'SECRET-WH2' not in response.text
                    checked.append({'user':uid,'method':method,'path':path,'status':response.status_code})
            for uid in (1,3,4):
                response=await client.get('/api/v1/clock-in/photos',headers=auth(uid),params={'employee_id':2,'date':'2026-10-19'})
                assert response.status_code==403
            async with factory() as db:
                assert (await db.get(Employee,2)).name=='Somchai'
                assert (await db.get(Customer,2)).company_name=='SECRET-WH2-CUSTOMER'
                assert (await db.get(Supplier,2)).name=='SECRET-WH2-SUPPLIER'
                assert (await db.get(SalaryTemplate,2)).amount==400
            actual('office_cross_warehouse_details_and_writes',checked)
    asyncio.run(run())


def test_shared_platform_is_cross_warehouse_but_publication_and_moderation_are_super_only(tmp_path,monkeypatch):
    async def run():
        async with management_environment(tmp_path,monkeypatch) as (_,factory,client):
            async with factory() as db:
                (await db.get(User,2)).warehouse_id=None
                await db.commit()
            for uid in (1,3,4,5,7,8):
                denied=await client.post('/api/v1/market/image',headers=auth(uid),data={'warehouse_id':2},files={'file':('test.png',png(),'image/png')})
                assert denied.status_code==403,(uid,denied.text)
                assert (await client.post('/api/v1/market',headers=auth(uid),json={'name':'must not publish','quantity':1,'warehouse_id':2})).status_code==403
                assert (await client.post('/api/v1/group-order',headers=auth(uid),json={'item_name':'must not publish','target_quantity':10,'target_price':50,'deadline':'2026-12-30','warehouse_id':2})).status_code==403
            image=await client.post('/api/v1/market/image',headers=auth(2),data={'warehouse_id':2},files={'file':('test.png',png(),'image/png')})
            assert image.status_code==200,image.text
            image_path='/'+image.json()['path']
            assert (await client.get(image_path,headers=auth(2))).status_code==200
            for uid in (1,3,4,5,7,8):assert (await client.get(image_path,headers=auth(uid))).status_code==403
            created=await client.post('/api/v1/market',headers=auth(2),json={'name':'PLATFORM-PUBLIC','quantity':10,'price':50,'warehouse_id':2,'image':image_path})
            assert created.status_code==200,created.text
            mid=created.json()['id']
            assert 'PLATFORM-PUBLIC' not in (await client.get('/api/v1/market',headers=auth(1))).text
            assert 'PLATFORM-PUBLIC' in (await client.get('/api/v1/market/review-list',headers=auth(2))).text
            for uid in (1,3,4,7):
                assert (await client.get('/api/v1/market/review-list',headers=auth(uid))).status_code==403
                assert (await client.put(f'/api/v1/market/{mid}/review',headers=auth(uid),json={'status':'approved'})).status_code==403
            approved=await client.put(f'/api/v1/market/{mid}/review',headers=auth(2),json={'status':'approved'})
            assert approved.status_code==200,approved.text
            for uid in (1,2,3,4,7):
                visible=await client.get('/api/v1/market',headers=auth(uid))
                assert visible.status_code==200 and 'PLATFORM-PUBLIC' in visible.text
                assert (await client.get(image_path,headers=auth(uid))).status_code==200
            assert (await client.get(image_path)).status_code==401
            for uid in (5,8):assert (await client.get(image_path,headers=auth(uid))).status_code==403
            async with factory() as db:
                user=await db.get(User,3);user.extra_permissions=[p for p in PERMISSIONS if p!='市场']
                await db.commit()
            assert (await client.get(image_path,headers=auth(3))).status_code==403
            assert (await client.get('/api/v1/market',headers=auth(3))).status_code==403
            async with factory() as db:
                (await db.get(User,3)).extra_permissions=PERMISSIONS
                await db.commit()
            purchased=await client.post(f'/api/v1/market/{mid}/purchase',headers=auth(1),json={'contact_info':'PRIVATE-BUYER-CONTACT'})
            assert purchased.status_code==200,purchased.text
            assert 'PRIVATE-BUYER-CONTACT' not in (await client.get('/api/v1/market',headers=auth(7))).text
            assert 'PRIVATE-BUYER-CONTACT' in (await client.get('/api/v1/market',headers=auth(2))).text
            assert (await client.put(f'/api/v1/market/{mid}/confirm',headers=auth(1))).status_code==403
            private='/uploads/2/2026-10-19/SECRET-WH2-clock.png'
            assert (await client.post('/api/v1/market',headers=auth(2),json={'name':'must not expose','quantity':1,'warehouse_id':2,'image':private})).status_code==403
            async with factory() as db:
                (await db.get(MarketItem,2)).image=private
                await db.commit()
            for uid in (1,2,3,4):assert (await client.get(private,headers=auth(uid))).status_code==403
            assert (await client.put('/api/v1/market/2/review',headers=auth(2),json={'status':'approved'})).status_code==403
            # A private record storing the thumbnail must also prevent sharing the original.
            async with factory() as db:
                from app.services.image_utils import thumb_path_of
                (await db.get(PayrollRecord,2)).signature_path=thumb_path_of(image.json()['path'])
                await db.commit()
            for uid in (1,2,3,4):assert (await client.get(image_path,headers=auth(uid))).status_code==403
            async with factory() as db:
                (await db.get(PayrollRecord,2)).signature_path=None
                await db.commit()
            assert (await client.post('/api/v1/market',headers=auth(2),json={'name':'missing origin','quantity':1})).status_code==400
            assert (await client.post('/api/v1/market',headers=auth(2),json={'name':'bad origin','quantity':1,'warehouse_id':999})).status_code==400
            assert (await client.put(f'/api/v1/market/{mid}/confirm',headers=auth(2))).status_code==200
            group=await client.post('/api/v1/group-order',headers=auth(2),json={'item_name':'PLATFORM-GROUP','target_quantity':10,'target_price':50,'deadline':'2026-12-30','warehouse_id':2})
            assert group.status_code==200,group.text
            gid=group.json()['id']
            for uid in (1,2,3,4,7):
                assert (await client.get('/api/v1/group-order',headers=auth(uid))).status_code==200
                assert (await client.get(f'/api/v1/group-order/{gid}/participants',headers=auth(uid))).status_code==200
            assert (await client.post(f'/api/v1/group-order/{gid}/join',headers=auth(2),json={'quantity':1})).status_code==403
            participants=[]
            for uid,qty in ((1,2),(7,3)):
                joined=await client.post(f'/api/v1/group-order/{gid}/join',headers=auth(uid),json={'quantity':qty,'delivery_address':f'PRIVATE-ADDRESS-{uid}','warehouse_id':999})
                assert joined.status_code==200,joined.text
                participants.append(joined.json()['id'])
            own=await client.get(f'/api/v1/group-order/{gid}',headers=auth(1))
            assert own.status_code==200 and own.json()['current_quantity']==5
            assert 'PRIVATE-ADDRESS-1' in own.text and 'PRIVATE-ADDRESS-7' not in own.text
            platform=await client.get(f'/api/v1/group-order/{gid}',headers=auth(2))
            assert 'PRIVATE-ADDRESS-1' in platform.text and 'PRIVATE-ADDRESS-7' in platform.text
            for uid in (1,3,4,7):
                for action,payload in [('close',{}),('complete',{'final_price':50}),('cancel',{'reason':'test'})]:
                    assert (await client.put(f'/api/v1/group-order/{gid}/{action}',headers=auth(uid),json=payload)).status_code==403
                assert (await client.put(f'/api/v1/group-order/participant/{participants[1]}/ban',headers=auth(uid))).status_code==403
            assert (await client.put(f'/api/v1/group-order/participant/{participants[1]}/ban',headers=auth(2))).status_code==200
            assert (await client.post(f'/api/v1/group-order/{gid}/join',headers=auth(7),json={'quantity':1})).status_code==403
            closed=await client.put(f'/api/v1/group-order/{gid}/close',headers=auth(2))
            assert closed.status_code==200 and closed.json()['summary']['total_quantity']==5
            assert (await client.put(f'/api/v1/group-order/{gid}/complete',headers=auth(2),json={'final_price':50})).status_code==200
            history=await client.get('/api/v1/group-order/history',headers=auth(1))
            assert history.status_code==200 and 'PLATFORM-GROUP' in history.text and 'PRIVATE-ADDRESS-7' not in history.text
            async with factory() as db:
                stored=(await db.execute(select(GroupOrderParticipant).where(GroupOrderParticipant.id.in_(participants)))).scalars().all()
                assert {p.warehouse_id for p in stored}=={1,2}
            assert (await client.get('/api/v1/payroll',headers=auth(2))).status_code==403
            assert (await client.post('/api/v1/upload',headers=auth(2),files={'file':('test.png',png(),'image/png')})).status_code==403
            actual('shared_platform',{'super_without_primary_warehouse_explicit_origin':200,'other_roles_publication_and_moderation':403,
                'cross_warehouse_approved_list_and_image':200,'before_approval_image':403,'labor_image':403,'anonymous_image':401,
                'revoked_market_permission':403,'private_business_file_as_market_image':403,'cross_warehouse_join_quantities':[2,3],
                'total_quantity':5,'other_warehouse_addresses_and_buyer_contact_hidden':True,'super_ordinary_business_still_denied':403})
    asyncio.run(run())
