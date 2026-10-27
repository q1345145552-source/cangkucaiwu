"""备用金手工开销凭证：先上传再创建，历史只读保留，审核缺图整批回滚。"""
import asyncio
import ast
import json
import subprocess
from pathlib import Path
from datetime import datetime
import pytest
from sqlalchemy import select
from app.models import ExpenseFund, ExpenseFundItem, User, UserWarehouse
from tests.test_fund_disbursement import approve_expense, environment, topup, receipt, values, BASE
from tests.test_round2_permissions import auth, set_perms, png
from tests.test_cash_advances import finance_snapshot

BODY={"request_key":"receipt-regression-request","expense_date":"2026-10-19","category":"耗材","amount":2000,"currency":"THB","description":"购买包装耗材"}


def test_missing_rejected_uploaded_create_list_approve_and_no_extra_cost(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,f,c,fid):
            assert (await topup(c,fid)).status_code==200
            before=await values(c,fid); snapshot=await finance_snapshot(f)
            bad=await c.post(f"{BASE}/accounts/{fid}/items",headers=auth(4),json=BODY)
            assert bad.status_code==400 and bad.json()=={"detail":"请上传开销凭证"}
            assert await finance_snapshot(f)==snapshot
            path=await receipt(c,fid)
            assert path.startswith(f"/uploads/fund_receipts/1/{fid}/")
            assert await finance_snapshot(f)==snapshot  # 上传本身不生成任何账目。
            made=await c.post(f"{BASE}/accounts/{fid}/items",headers=auth(4),json={**BODY,"receipt":path})
            assert made.status_code==200, made.text
            assert made.json()["receipt"]==path
            iid=made.json()["id"]
            listed=(await c.get(f"{BASE}/accounts/{fid}/items",headers=auth(1))).json()["data"]
            assert listed[0]["receipt"]==path and listed[0]["id"]==iid
            approved=await approve_expense(c, [iid])
            assert approved.status_code==200 and approved.json()["message"]=="已通过1条记录"
            after=await values(c,fid)
            for field in ("expense_count","expense_amount","flow_count","flow_amount","company_cash"):
                assert before[field]==after[field]
            assert after["fund"]["available"]==8000
            print("FUND_RECEIPT_ACTUAL",json.dumps({"missing":{"status":bad.status_code,"body":bad.json()},"uploaded_receipt":path,"created":made.json(),"list_row":listed[0],"approved":approved.json()},ensure_ascii=False))
    asyncio.run(run())


@pytest.mark.parametrize("path",[None,"","  ","https://example.com/x.png","/uploads/fund_receipts/2/1/x.png","/uploads/fund_receipts/1/999/x.png","/uploads/fund_receipts/1/1/../x.png","/uploads/fund_receipts/1/1/missing.png"])
def test_empty_fake_or_wrong_scope_receipts_cannot_create(tmp_path,monkeypatch,path):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,f,c,fid):
            await topup(c,fid); before=await finance_snapshot(f)
            result=await c.post(f"{BASE}/accounts/{fid}/items",headers=auth(4),json={**BODY,"receipt":path})
            assert result.status_code==400, result.text
            assert await finance_snapshot(f)==before
    asyncio.run(run())


@pytest.mark.parametrize("content",[b"",b"not an image",b"x"*(10*1024*1024+1)])
def test_invalid_upload_does_not_leave_record(tmp_path,monkeypatch,content):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,f,c,fid):
            before=await finance_snapshot(f)
            result=await c.post(f"{BASE}/accounts/{fid}/upload-receipt",headers=auth(4),files={"file":("photo.png",content,"image/png")})
            assert result.status_code==400, result.text
            assert await finance_snapshot(f)==before
    asyncio.run(run())


def test_old_missing_kept_and_approve_rejected_then_manual_attachment_works(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,f,c,fid):
            await topup(c,fid)
            async with f() as db:
                for status in ("pending","approved","rejected"):
                    db.add(ExpenseFundItem(fund_id=fid,expense_date=datetime(2026,9,1),category="旧耗材",amount=123,
                        description="历史无凭证",receipt=None,review_status=status,cost_record_only=False))
                await db.commit()
                old=(await db.execute(select(ExpenseFundItem).order_by(ExpenseFundItem.id))).scalars().all()
                iid=old[0].id
            before=await finance_snapshot(f)
            listed=(await c.get(f"{BASE}/accounts/{fid}/items",headers=auth(1))).json()["data"]
            assert len(listed)==3 and sum(x["amount"] for x in listed)==369 and all(x["receipt"] is None for x in listed)
            bad=await c.post(BASE+"/review/batch",headers=auth(3),json={"item_ids":[iid],"action":"verify"})
            assert bad.status_code==400 and "该开销没有凭证" in bad.json()["detail"]
            assert await finance_snapshot(f)==before
            # 旧入口保留：用户主动为历史待审记录补图后可以审核，不自动改旧记录。
            up=await c.post(f"{BASE}/accounts/{fid}/items/{iid}/upload-receipt",headers=auth(1),files={"file":("receipt.png",png(),"image/png")})
            assert up.status_code==200
            assert (await approve_expense(c, [iid])).status_code==200
            print("LEGACY_RECEIPTS",{"count":3,"amount":369,"approve_missing":bad.json(),"records_preserved":True})
    asyncio.run(run())


def test_batch_with_missing_receipt_rolls_back_other_approvals(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,f,c,fid):
            await topup(c,fid); path=await receipt(c,fid)
            made=(await c.post(f"{BASE}/accounts/{fid}/items",headers=auth(4),json={**BODY,"receipt":path})).json()
            async with f() as db:
                old=ExpenseFundItem(fund_id=fid,expense_date=datetime(2026,9,1),category="报销",amount=100,
                    description="手工类别不能冒充关联报销绕过校验",receipt="  ",review_status="pending")
                db.add(old);await db.commit(); missing=old.id
            before=await finance_snapshot(f)
            result=await c.post(BASE+"/review/batch",headers=auth(1),json={"item_ids":[made["id"],missing],"action":"verify"})
            assert result.status_code==400
            assert await finance_snapshot(f)==before
            # 驳回不需要凭证；不触及原审核扣款/退款流程。
            assert (await c.post(BASE+"/review/batch",headers=auth(1),json={"item_ids":[missing],"action":"reject","remark":"无有效凭证"})).status_code==200
    asyncio.run(run())


def test_scope_roles_other_fund_and_legacy_uploads(tmp_path,monkeypatch):
    async def run():
        async with environment(tmp_path,monkeypatch) as (_,f,c,fid):
            await topup(c,fid);path=await receipt(c,fid)
            async with f() as db:
                db.add(User(id=7,username="other",display_name="外仓",password_hash="unused",role="warehouse_admin",warehouse_id=2))
                db.add(UserWarehouse(user_id=7,warehouse_id=2))
                other=ExpenseFund(warehouse_id=1,employee_id=1,receive_date=datetime(2026,10,19),amount=1000,purpose="另一账户",remaining_balance=1000)
                db.add(other);await db.commit();oid=other.id
            assert (await c.post(f"{BASE}/accounts/{oid}/items",headers=auth(1),json={**BODY,"amount":100,"receipt":path})).status_code==400
            for uid in (2,5,7):
                await set_perms(f,uid,["备用金管理"])
                result=await c.post(f"{BASE}/accounts/{fid}/upload-receipt",headers=auth(uid),files={"file":("receipt.png",png(),"image/png")})
                assert result.status_code==403, result.text
            await set_perms(f,3,["备用金管理"])
            assert (await c.post(f"{BASE}/accounts/{fid}/upload-receipt",headers=auth(3),files={"file":("receipt.png",png(),"image/png")})).status_code==403
    asyncio.run(run())


def test_payout_and_other_business_paths_unchanged():
    root=Path(__file__).resolve().parents[2]
    for path in ("backend/app/api/v1/reimbursement.py","backend/app/api/v1/payroll.py","backend/app/api/v1/employee_advance.py"):
        previous=subprocess.check_output(["git","show",f"14e2541:{path}"],cwd=root,text=True)
        if path.endswith('/reimbursement.py'):
            def actions(source): return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(source).body if isinstance(n,ast.AsyncFunctionDef) and n.name != 'review_reimb'}
            assert actions((root/path).read_text()) == actions(previous)
        else:
            assert (root/path).read_text() == previous
    path="backend/app/api/v1/expense_fund.py"
    def functions(source):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(source).body if isinstance(n,ast.AsyncFunctionDef)}
    old=functions(subprocess.check_output(["git","show",f"4cbf9e8:{path}"],cwd=root,text=True)); now=functions((root/path).read_text())
    for name in old:
        if name not in ("add_item","upload_receipt","batch_review","list_accounts","list_items","list_pending_reviews","list_recharge_requests","create_account","topup_account","submit_recharge_request","review_recharge_request","update_settings","edit_item","void_item","upload_new_item_receipt"):
            assert old[name]==now[name],name
