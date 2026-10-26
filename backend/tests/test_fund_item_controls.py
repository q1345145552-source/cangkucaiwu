"""手工开销管理员编辑与软作废：真实 HTTP、台账、修改日志、跨仓和回滚。"""
import asyncio
import json
import ast
import subprocess
from pathlib import Path
from datetime import datetime
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.models import ExpenseFundItem, EmployeeAdvance, Reimbursement, User, UserWarehouse
from app.models.data_change_history import DataChangeHistory
from app.services import fund_item_controls as controls
from tests.test_fund_disbursement import environment, spend, topup, receipt, values, BASE
from tests.test_round2_permissions import auth, set_perms, png
from tests.test_cash_advances import finance_snapshot


async def path_for(c,fid):
    result=await spend(c,fid);assert result.status_code==200,result.text
    return result.json()["id"],f"{BASE}/accounts/{fid}/items/{result.json()['id']}"


def test_supervisor_denied_admin_edit_void_history_and_balance(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,f,c,fid):
            await topup(c,fid); iid,url=await path_for(c,fid)
            before=await values(c,fid)
            edit_denied=await c.put(url,headers=auth(4),json={"amount":1500})
            delete_denied=await c.request("DELETE",url,headers=auth(4),json={"reason":"主管不许作废"})
            photo_denied=await c.post(url+"/upload-receipt",headers=auth(4),files={"file":("photo.png",png(),"image/png")})
            assert edit_denied.status_code==403 and edit_denied.json()["detail"]=="开销记录只有仓库管理员可以修改"
            assert delete_denied.status_code==403 and delete_denied.json()["detail"]=="开销记录只有仓库管理员可以删除"
            assert photo_denied.status_code==403 and photo_denied.json()["detail"]==edit_denied.json()["detail"]
            changed=await c.put(url,headers=auth(1),json={"amount":1500,"category":"办公用品","description":"老板核对金额"})
            assert changed.status_code==200 and changed.json()["amount"]==1500 and changed.json()["category"]=="办公用品",changed.text
            replacement=await receipt(c,fid,uid=1)
            changed_photo=await c.put(url,headers=auth(1),json={"receipt":replacement})
            assert changed_photo.status_code==200 and changed_photo.json()["receipt"]==replacement
            after_edit=await values(c,fid);assert before["fund"]["available"]==8000 and after_edit["fund"]["available"]==8500
            assert (await c.request("DELETE",url,headers=auth(1),json={"reason":"  "})).status_code==400
            voided=await c.request("DELETE",url,headers=auth(1),json={"reason":"重复登记，保留记录作废"})
            assert voided.status_code==200,voided.text
            data=voided.json();assert data["review_status"]=="voided" and data["is_voided"] and data["voided_by"]==1 and data["voided_at"]
            after_void=await values(c,fid);assert after_void["fund"]["available"]==10000 and after_void["fund"]["total_spent"]==0
            for name in ("expense_count","expense_amount","flow_count","flow_amount","company_cash"):
                assert before[name]==after_void[name]
            listed=(await c.get(f"{BASE}/accounts/{fid}/items",headers=auth(1))).json()["data"]
            assert len(listed)==1 and listed[0]["review_status"]=="voided" and not listed[0]["can_edit"] and not listed[0]["can_void"]
            history=(await c.get(f"/api/v1/history?module=expense_fund_item&record_id={iid}",headers=auth(1))).json()["data"]
            identity_history=[r for r in history if r['operation_type']=='cost_identity']
            assert len(identity_history)==4 and sorted(r['operator_id'] for r in identity_history)==[1,1,1,4]
            assert all(r['created_at'] for r in identity_history)
            history=[r for r in history if r['operation_type']!='cost_identity']
            assert len(history)==3 and {r["operation_type"] for r in history}=={"edit","void"}
            amount_log=next(row for row in history if row["operation_type"]=="edit" and row["before_data"]["amount"]!=row["after_data"]["amount"])
            assert amount_log["before_data"]["amount"]==2000 and amount_log["after_data"]["amount"]==1500
            assert all(row["operator_id"]==1 and row["created_at"] for row in history)
            assert next(row for row in history if row["operation_type"]=="void")["after_data"]["void_reason"]=="重复登记，保留记录作废"
            async with f() as db:assert (await db.get(ExpenseFundItem,iid)).amount==1500
            for action in ("approve","reject"):
                assert (await c.post(BASE+"/review/batch",headers=auth(1),json={"item_ids":[iid],"action":action})).status_code==400
            assert (await c.put(url,headers=auth(1),json={"amount":100})).status_code==400
            assert (await c.request("DELETE",url,headers=auth(1),json={"reason":"再作废"})).status_code==400
            print("FUND_CONTROL_ACTUAL",json.dumps({"supervisor_edit":{"status":403,"body":edit_denied.json()},"supervisor_delete":{"status":403,"body":delete_denied.json()},"edited":changed.json(),"voided":data,"available":[before["fund"]["available"],after_edit["fund"]["available"],after_void["fund"]["available"]],"amount_log":amount_log,"history":history},ensure_ascii=False))
    asyncio.run(run())


def test_approved_cannot_edit_void_or_replace_receipt(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,f,c,fid):
            await topup(c,fid);iid,url=await path_for(c,fid)
            assert (await c.post(BASE+"/review/batch",headers=auth(1),json={"item_ids":[iid],"action":"approve"})).status_code==200
            before=await finance_snapshot(f)
            changed=await c.put(url,headers=auth(1),json={"amount":1500})
            deleted=await c.request("DELETE",url,headers=auth(1),json={"reason":"不能动已通过"})
            photo=await c.post(url+"/upload-receipt",headers=auth(1),files={"file":("receipt.png",png(),"image/png")})
            assert changed.status_code==photo.status_code==400 and changed.json()["detail"]=="该开销已审核通过 不能修改"
            assert deleted.status_code==400 and deleted.json()["detail"]=="该开销已审核通过 不能作废"
            assert before==await finance_snapshot(f)
            print("APPROVED_CONTROL",json.dumps({"edit":changed.json(),"void":deleted.json()},ensure_ascii=False))
    asyncio.run(run())


@pytest.mark.parametrize("uid",[2,3,5])
def test_other_roles_cannot_change_record(tmp_path,monkeypatch,uid):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,f,c,fid):
            await topup(c,fid);_,url=await path_for(c,fid);await set_perms(f,uid,["备用金管理"])
            assert (await c.put(url,headers=auth(uid),json={"amount":100})).status_code==403
            assert (await c.request("DELETE",url,headers=auth(uid),json={"reason":"无权"})).status_code==403
    asyncio.run(run())


def test_warehouse_scope_and_protected_linked_items(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,f,c,fid):
            await topup(c,fid);iid,url=await path_for(c,fid)
            async with f() as db:
                db.add(User(id=7,username="other",display_name="外仓老板",password_hash="unused",role="warehouse_admin",warehouse_id=2))
                db.add(UserWarehouse(user_id=7,warehouse_id=2));await db.commit()
            for suffix, method, body in [("","PUT",{"amount":100}),("","DELETE",{"reason":"跨仓"})]:
                assert (await c.request(method,url+suffix,headers=auth(7),json=body)).status_code==404
            assert (await c.put(f"{BASE}/accounts/999/items/{iid}",headers=auth(1),json={"amount":100})).status_code==404
            async with f() as db:
                a=EmployeeAdvance(warehouse_id=1,employee_id=1,amount=100,advance_date=datetime(2026,10,19).date(),period="2026-10",fund_account_id=fid,fund_item_id=iid,approval_status="pending")
                db.add(a);await db.commit()
            assert (await c.put(url,headers=auth(1),json={"amount":100})).status_code==400
            assert (await c.request("DELETE",url,headers=auth(1),json={"reason":"误走入口"})).status_code==400
            async with f() as db:
                a=(await db.execute(select(EmployeeAdvance))).scalars().one();a.fund_item_id=None
                db.add(Reimbursement(warehouse_id=1,employee_id=4,submit_date=datetime(2026,10,19),total_amount=2000,status="fund_linked",fund_item_id=iid,is_fund_linked="1"));await db.commit()
            assert (await c.put(url,headers=auth(1),json={"amount":100})).status_code==400
            assert (await c.request("DELETE",url,headers=auth(1),json={"reason":"误走入口"})).status_code==400
    asyncio.run(run())


@pytest.mark.parametrize("operation",["edit","void","receipt"])
def test_history_failure_rolls_back_every_change(tmp_path,monkeypatch,operation):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,f,c,fid):
            await topup(c,fid);_,url=await path_for(c,fid);before=await finance_snapshot(f)
            async def fail(*args,**kwargs):raise HTTPException(500,"模拟留痕失败")
            monkeypatch.setattr(controls,"record_history",fail)
            if operation=="edit":result=await c.put(url,headers=auth(1),json={"amount":1000})
            elif operation=="void":result=await c.request("DELETE",url,headers=auth(1),json={"reason":"回滚验收"})
            else:result=await c.post(url+"/upload-receipt",headers=auth(1),files={"file":("receipt.png",png(),"image/png")})
            assert result.status_code==500 and before==await finance_snapshot(f)
    asyncio.run(run())


def test_void_restores_all_available_queries_and_preserves_legacy_rows(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,f,c,fid):
            await topup(c,fid)
            async with f() as db:
                old=ExpenseFundItem(fund_id=fid,expense_date=datetime(2026,9,1),category="旧开销",amount=123,description="原样保留",review_status="pending",cost_record_only=False)
                db.add(old);await db.commit();oldid=old.id
            iid,url=await path_for(c,fid)
            before=await finance_snapshot(f)
            assert (await c.request("DELETE",url,headers=auth(1),json={"reason":"不占额度"})).status_code==200
            after=await finance_snapshot(f)
            assert before["expense_fund_items"][0]==after["expense_fund_items"][0]
            assert len(before["expense_fund_items"])==len(after["expense_fund_items"])==2
            from app.services.employee_advance_funding import fund_available_amount
            from app.models import ExpenseFund
            async with f() as db: assert await fund_available_amount(db,await db.get(ExpenseFund,fid))==9877
            rows=(await c.get(f"{BASE}/accounts/{fid}/disbursements",headers=auth(1))).json()["data"]
            assert rows[0]["used_amount"]==123 and iid not in [x["item_id"] for x in rows[0]["items"]]
            assert (await c.post(BASE+"/recharge/request",headers=auth(4),json={"amount":100})).status_code==200
            req=(await c.get(BASE+"/recharge/requests",headers=auth(1))).json()["data"][0]
            assert req["available"]==9877
    asyncio.run(run())


def test_amount_validation_currency_and_rejected_entry(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,f,c,fid):
            await topup(c,fid);iid,url=await path_for(c,fid)
            assert (await c.put(url,headers=auth(1),json={"amount":11000})).status_code==400
            assert (await c.put(url,headers=auth(1),json={"amount":0})).status_code==422
            assert (await c.put(url,headers=auth(1),json={"currency":"CNY"})).status_code==400
            assert (await c.put(url,headers=auth(1),json={"receipt":""})).status_code==400
            assert (await c.post(BASE+"/review/batch",headers=auth(1),json={"item_ids":[iid],"action":"reject"})).status_code==200
            before=(await values(c,fid))["fund"]["available"]
            assert (await c.request("DELETE",url,headers=auth(1),json={"reason":"已驳回记录保留作废"})).status_code==200
            assert (await values(c,fid))["fund"]["available"]==before==10000
    asyncio.run(run())


def test_original_financial_functions_and_formula_preserved():
    root=Path(__file__).resolve().parents[2]
    for path in ("backend/app/api/v1/reimbursement.py","backend/app/api/v1/payroll.py","backend/app/api/v1/employee_advance.py","backend/app/services/flow_rules.py"):
        assert (root/path).read_text()==subprocess.check_output(["git","show",f"4cbf9e8:{path}"],cwd=root,text=True)
    path="backend/app/services/fund_disbursement.py"
    def functions(source):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(source).body if isinstance(n,ast.AsyncFunctionDef)}
    old=functions(subprocess.check_output(["git","show",f"4cbf9e8:{path}"],cwd=root,text=True));now=functions((root/path).read_text())
    for name in old:
        if name!="fund_sources":assert now[name]==old[name]
