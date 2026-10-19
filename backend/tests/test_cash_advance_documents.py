"""垫款关联用途不代表付款；真实请求验证金额、审核、编辑、隔离及事务。"""
import asyncio
import ast
import json
import subprocess
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models import CashAdvance, CashAdvanceDocument, CashAdvanceRepayment, PayableBill, Reimbursement, EmployeeAdvance, User, UserWarehouse
from app.models.payroll import PayrollRecord
from app.models.data_change_history import DataChangeHistory
import app.api.v1.cash_advance as api
from tests.test_round2_permissions import auth, set_perms
from tests.test_round3_permissions import hr_environment
from tests.test_cash_advances import create, finance_snapshot, URL


REFS = [{"document_type": "payroll", "document_id": rid} for rid in (2, 4)]


async def prepare(factory):
    await set_perms(factory, 4, ["垫款单"])
    await set_perms(factory, 3, ["垫款单"])
    async with factory() as db:
        (await db.get(PayrollRecord, 2)).net_pay = 3000
        db.add(PayrollRecord(id=4, warehouse_id=1, employee_id=1, period="2026-10", status="confirmed", disbursed=False,
            net_pay=4000, settle_start_date=date(2026, 10, 16), settle_end_date=date(2026, 10, 31)))
        db.add(PayableBill(id=31, warehouse_id=1, supplier_id=1, bill_number="AP-31", bill_date=datetime(2026,10,1),
            due_date=datetime(2026,10,30), amount=2500, paid_amount=500, status="partially_paid", currency="THB"))
        for rid, status, currency in [(31,"approved","THB"), (32,"pending","THB"), (33,"paid","THB"), (34,"approved","CNY")]:
            db.add(Reimbursement(id=rid, warehouse_id=1, employee_id=4, submit_date=datetime(2026,10,10), total_amount=1000, status=status, currency=currency))
        for rid, status, approval in [(31,"unpaid","approved"), (32,"partial","approved"), (33,"deducted","approved"), (34,"unpaid","rejected"), (35,"voided","approved"), (36,"unpaid","pending")]:
            db.add(EmployeeAdvance(id=rid, warehouse_id=1, employee_id=1, advance_date=date(2026,10,10),
                period="2026-10", amount=1000, deducted_amount=200 if status=="partial" else 0, status=status, approval_status=approval))
        await db.commit()


def test_two_wages_difference_manual_status_detail_and_other_books_unchanged(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            await prepare(f)
            before = await finance_snapshot(f)
            choices = (await c.get(URL+"/document-options?document_type=payroll", headers=auth(4))).json()
            assert {r["document_id"] for r in choices["data"]} == {2,4}
            assert sum(r["amount"] for r in choices["data"]) == 7000
            r = await create(c, 4, amount="7000", linked_documents=REFS)
            assert r.status_code == 200, r.text
            made = r.json()
            assert made["status"] == "pending" and made["linked_documents_total"] == 7000
            assert {d["document_id"] for d in made["linked_documents"]} == {2,4}
            assert made["reviewed_by_id"] is None
            bad = await create(c, 4, amount="6000", linked_documents=REFS, amount_difference_note="   ")
            assert bad.status_code == 400 and "差额备注" in bad.json()["detail"]
            changed = (await create(c, 4, amount="6000", linked_documents=REFS, amount_difference_note="差额1000另行结算")).json()
            assert changed["amount"] == 6000 and changed["amount_difference_note"] == "差额1000另行结算"
            manual = (await create(c, amount="600", purpose="expense", description="临时购买耗材，无供应商单据")).json()
            assert manual["status"] == "confirmed" and manual["linked_documents"] == []
            assert manual["reviewed_by_id"] == 1 and manual["reviewed_at"] == manual["created_at"]
            admin = (await create(c, amount="7000", linked_documents=REFS)).json()
            assert admin["status"] == "confirmed" and admin["outstanding_amount"] == 7000
            assert (await c.post(f'{URL}/{admin["id"]}/confirm', headers=auth(1))).status_code == 400
            listing = (await c.get(URL, headers=auth(1))).json()["data"]
            assert next(r for r in listing if r["id"] == made["id"])["linked_documents_total"] == 7000
            details = []
            for link in made["linked_documents"]:
                detail = await c.get(f'{URL}/{made["id"]}/documents/{link["id"]}', headers=auth(3))
                assert detail.status_code == 200, detail.text
                data = detail.json(); assert data["current"]["document_id"] == link["document_id"]
                assert data["current"]["detail"]["disbursed"] is False
                details.append(data)
            assert await finance_snapshot(f) == before
            print("ROUND9_ACTUAL", json.dumps({"wages": made, "difference_rejected": bad.json(), "difference_saved": changed,
                "manual": manual, "admin": admin, "linked_details": details}, ensure_ascii=False))
    asyncio.run(run())


@pytest.mark.parametrize("kind, expected", [("payroll",{2,4}), ("payable",{31}), ("reimbursement",{31}), ("employee_advance",{31,32,36})])
def test_four_types_eligibility_residual_currency_paging_and_search(tmp_path, monkeypatch, kind, expected):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            await prepare(f)
            url=URL+f"/document-options?document_type={kind}"
            result=(await c.get(url,headers=auth(1))).json()
            assert {r["document_id"] for r in result["data"]} == expected, result
            assert result["total"] == len(expected)
            if kind=="payable": assert result["data"][0]["amount"] == 2000
            if kind=="employee_advance": assert next(r for r in result["data"] if r["document_id"]==32)["amount"] == 800
            page=(await c.get(url+"&page_size=1&page=1",headers=auth(1))).json()
            assert len(page["data"])==1 and page["total"]==len(expected)
            search=(await c.get(url+f'&search={page["data"][0]["document_id"]}',headers=auth(1))).json()
            assert len(search["data"])==1
            assert (await c.get(url+"&search=%25",headers=auth(1))).json()["total"]==0
            cny=(await c.get(url+"&currency=CNY",headers=auth(1))).json()
            assert {r["document_id"] for r in cny["data"]}==({34} if kind=="reimbursement" else set())
            if kind!="payroll":
                refs=[{"document_type":kind,"document_id":page["data"][0]["document_id"]}]
                r=await create(c, linked_documents=refs, amount=str(page["data"][0]["amount"]))
                assert r.status_code==200, r.text
    asyncio.run(run())


@pytest.mark.parametrize("refs, currency", [([{"document_type":"payroll","document_id":10}],"THB"),
    ([{"document_type":"payroll","document_id":1}],"THB"), ([{"document_type":"payroll","document_id":3}],"THB"),
    ([{"document_type":"reimbursement","document_id":32}],"THB"), ([{"document_type":"reimbursement","document_id":34}],"THB"),
    ([{"document_type":"employee_advance","document_id":35}],"THB"), (REFS+REFS,"THB"), (REFS,"CNY")])
def test_invalid_or_cross_warehouse_links_rejected_without_any_write(tmp_path, monkeypatch, refs, currency):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            await prepare(f); before=await finance_snapshot(f)
            r=await create(c, amount="7000", currency=currency, linked_documents=refs, amount_difference_note="差额")
            assert r.status_code==400, r.text
            async with f() as db:
                assert not (await db.execute(select(CashAdvance))).scalars().all()
                assert not (await db.execute(select(CashAdvanceDocument))).scalars().all()
            assert await finance_snapshot(f)==before
    asyncio.run(run())


def test_edit_pending_confirmed_permissions_and_warehouse(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            await prepare(f)
            pending=(await create(c,4,amount="7000",linked_documents=REFS)).json()
            body={"advance_date":"2026-10-18","amount":"6000","purpose":"salary","linked_documents":REFS,"amount_difference_note":"差额1000"}
            r=await c.put(f'{URL}/{pending["id"]}',headers=auth(4),json=body)
            assert r.status_code==200 and r.json()["status"]=="pending" and r.json()["amount"]==6000, r.text
            assert len(r.json()["linked_documents"])==2
            assert (await c.put(f'{URL}/{pending["id"]}',headers=auth(1),json={**body,"amount_difference_note":None})).status_code==400
            confirmed=(await create(c)).json()
            assert (await c.put(f'{URL}/{confirmed["id"]}',headers=auth(4),json=body)).status_code==400
            r=await c.put(f'{URL}/{confirmed["id"]}',headers=auth(1),json=body)
            assert r.status_code==200 and r.json()["status"]=="confirmed" and r.json()["reviewed_by_id"]==1
            for uid in (2,3,5):
                assert (await c.put(f'{URL}/{pending["id"]}',headers=auth(uid),json=body)).status_code==403
                assert (await c.get(URL+"/document-options?document_type=payroll",headers=auth(uid))).status_code==403
            async with f() as db:
                db.add(User(id=7,username="other-admin",display_name="外仓老板",role="warehouse_admin",password_hash="unused",warehouse_id=2))
                db.add(UserWarehouse(user_id=7,warehouse_id=2)); await db.commit()
            assert (await c.put(f'{URL}/{pending["id"]}',headers=auth(7),json=body)).status_code==404
            link=pending["linked_documents"][0]
            assert (await c.get(f'{URL}/{pending["id"]}/documents/{link["id"]}',headers=auth(7))).status_code==404
            assert (await c.get(URL+"/document-options?document_type=payroll",headers=auth(7))).json()["data"]==[]
    asyncio.run(run())


@pytest.mark.parametrize("usage", ["payroll","reimbursement","employee_advance","repayment"])
def test_used_or_repaid_cash_advance_cannot_be_edited(tmp_path,monkeypatch,usage):
    async def run():
        async with hr_environment(tmp_path,monkeypatch) as (_,f,c):
            await prepare(f); aid=(await create(c)).json()["id"]
            async with f() as db:
                if usage=="payroll":
                    wage=await db.get(PayrollRecord,3); wage.cash_advance_id=aid
                elif usage=="employee_advance":
                    a=await db.get(EmployeeAdvance,31); a.cash_advance_id=aid; a.funding_source="cash_advance"
                elif usage=="reimbursement":
                    from app.models.reimbursement_payment import ReimbursementPayment
                    db.add(ReimbursementPayment(reimbursement_id=31,warehouse_id=1,cash_advance_id=aid,
                        amount=1000,currency="THB",funding_source="cash_advance",previous_status="approved",paid_by_name="老板",paid_at=datetime(2026,10,19),status="active"))
                else:
                    db.add(CashAdvanceRepayment(cash_advance_id=aid,warehouse_id=1,repayment_date=date(2026,10,19),
                        amount=100,account_id=1,account_name="现金",currency="THB",payment_method="cash",voucher_path="test.png",created_by_name="老板",status="revoked"))
                await db.commit()
            rows=(await c.get(URL,headers=auth(1))).json()["data"]
            assert not next(r for r in rows if r["id"]==aid)["can_edit"]
            r=await c.put(f"{URL}/{aid}",headers=auth(1),json={"advance_date":"2026-10-18","amount":"3000","purpose":"salary"})
            assert r.status_code==400, r.text
    asyncio.run(run())


def test_snapshot_survives_payment_change_and_log_failure_rolls_back_edit(tmp_path,monkeypatch):
    async def run():
        async with hr_environment(tmp_path,monkeypatch) as (_,f,c):
            await prepare(f)
            made=(await create(c,4,amount="7000",linked_documents=REFS)).json(); aid=made["id"]
            before=await finance_snapshot(f)
            async def fail(*args,**kwargs): raise HTTPException(500,"模拟日志失败")
            monkeypatch.setattr(api,"record_history",fail)
            body={"advance_date":"2026-10-18","amount":"3000","purpose":"salary","linked_documents":REFS[:1]}
            assert (await c.put(f"{URL}/{aid}",headers=auth(4),json=body)).status_code==500
            assert (await create(c,linked_documents=REFS,amount="7000")).status_code==500
            row=(await c.get(URL,headers=auth(1))).json()["data"][0]
            assert row["amount"]==7000 and len(row["linked_documents"])==2
            assert await finance_snapshot(f)==before
            async with f() as db:
                wage=await db.get(PayrollRecord,2); wage.disbursed=True; wage.net_pay=2500; await db.commit()
            link=next(d for d in made["linked_documents"] if d["document_id"]==2)
            detail=(await c.get(f'{URL}/{aid}/documents/{link["id"]}',headers=auth(4))).json()
            assert detail["snapshot"]["amount"]==3000 and detail["current"]["amount"]==2500
            assert detail["current"]["detail"]["disbursed"] is True
    asyncio.run(run())


def test_payment_and_repayment_business_functions_unchanged():
    root=Path(__file__).resolve().parents[2]
    for path in ("backend/app/api/v1/payroll.py","backend/app/api/v1/payable.py","backend/app/api/v1/reimbursement.py","backend/app/api/v1/employee_advance.py"):
        assert (root/path).read_text()==subprocess.check_output(["git","show",f"7b8b05b:{path}"],cwd=root,text=True)
    path="backend/app/api/v1/cash_advance.py"
    def functions(text): return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(text).body if isinstance(n,ast.AsyncFunctionDef)}
    old=functions(subprocess.check_output(["git","show",f"7b8b05b:{path}"],cwd=root,text=True)); now=functions((root/path).read_text())
    for name in ("repay_advance","revoke_repayment","_repayment_result","_review"):
        assert now[name]==old[name]


@pytest.mark.parametrize("kind", ["payroll", "payable", "reimbursement", "employee_advance"])
def test_each_type_hides_and_rejects_foreign_documents(tmp_path, monkeypatch, kind):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            await prepare(f)
            async with f() as db:
                db.add(PayrollRecord(id=81, warehouse_id=2, employee_id=2, period="2026-10", status="confirmed", disbursed=False, net_pay=900))
                db.add(PayableBill(id=81, warehouse_id=2, supplier_id=2, bill_number="FOREIGN-81", bill_date=datetime(2026,10,1), due_date=datetime(2026,10,30), amount=900, paid_amount=0, status="pending", currency="THB"))
                db.add(Reimbursement(id=81, warehouse_id=2, employee_id=6, submit_date=datetime(2026,10,10), total_amount=900, status="approved", currency="THB"))
                db.add(EmployeeAdvance(id=81, warehouse_id=2, employee_id=2, advance_date=date(2026,10,10), period="2026-10", amount=900, status="unpaid", approval_status="approved"))
                await db.commit()
            result=(await c.get(URL+f"/document-options?document_type={kind}",headers=auth(1))).json()
            assert 81 not in [r["document_id"] for r in result["data"]]
            r=await create(c,linked_documents=[{"document_type":kind,"document_id":81}],amount="900")
            assert r.status_code==400 and "不属于当前仓库" in r.json()["detail"]
    asyncio.run(run())
