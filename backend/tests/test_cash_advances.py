"""垫款单：隔离数据库真实 HTTP、精确欠款、角色/仓库边界及旧财务快照。"""
import asyncio
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.database import Base
from app.models import CashAdvance, User, UserWarehouse, SystemSetting
from app.models.data_change_history import DataChangeHistory
import app.api.v1.cash_advance as api
from app.services.permission_migrations import backfill_cash_advances_permission, CASH_ADVANCES_PERMISSION_MARKER
from tests.test_round2_permissions import auth, set_perms, png
from tests.test_round3_permissions import hr_environment

URL = "/api/v1/cash-advances"
BODY = {"advance_date": "2026-10-18", "amount": "3000.00", "purpose": "salary", "description": "主管垫付工资"}


async def create(client, uid=1, **changes):
    return await client.post(URL, headers=auth(uid), json={**BODY, **changes})


async def finance_snapshot(factory):
    names = ("payroll_records", "reimbursements", "reimbursement_items", "expense_funds", "expense_fund_items", "expense_records", "income_records", "employee_advances", "payable_bills", "clock_in_records", "employees")
    async with factory() as db:
        return {name: [tuple(r) for r in (await db.execute(select(Base.metadata.tables[name]).order_by(Base.metadata.tables[name].c.id))).all()] for name in names}


def test_supervisor_voucher_admin_confirmation_exact_summary_and_finance_unchanged(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, c):
            await set_perms(factory, 4, ["垫款单"])
            before = await finance_snapshot(factory)
            uploaded = await c.post(URL + "/voucher", headers=auth(4), files={"file": ("凭证.png", png(), "image/png")})
            assert uploaded.status_code == 200, uploaded.text
            path = uploaded.json()["path"]
            assert path.startswith("uploads/1/") and "/cash-advances/" in path
            assert list((tmp_path / "hr-uploads").rglob(Path(path).name))
            made = await create(c, 4, voucher_path=path)
            assert made.status_code == 200, made.text
            first = made.json()
            assert (first["payer_id"], first["payer_name"], first["status"], first["outstanding_amount"]) == (4, "supervisor", "pending", 0)
            assert first["amount"] == 3000 and first["created_by_id"] == 4 and first["created_at"]
            assert (await c.get(URL + "/summary", headers=auth(1))).json()["total_outstanding"] == 0
            confirmed = await c.post(f'{URL}/{first["id"]}/confirm', headers=auth(1))
            assert confirmed.status_code == 200, confirmed.text
            second = confirmed.json()
            assert second["status"] == "confirmed" and second["outstanding_amount"] == 3000
            assert second["repaid_amount"] == 0 and second["reviewed_by_id"] == 1 and second["reviewed_at"]
            listing = (await c.get(URL + "?status=confirmed", headers=auth(1))).json()
            assert listing["data"][0]["outstanding_amount"] == 3000
            totals = (await c.get(URL + "/summary", headers=auth(1))).json()
            assert totals == {"payer_count": 1, "total_outstanding": 3000, "totals_by_currency": [{"currency": "THB", "amount": 3000}], "data": [{"payer_id": 4, "payer_name": "supervisor", "outstanding_amount": 3000, "totals_by_currency": [{"currency": "THB", "amount": 3000}]}]}
            assert sum(r["outstanding_amount"] for r in listing["data"]) == totals["total_outstanding"]
            assert await finance_snapshot(factory) == before
            async with factory() as db:
                history = (await db.execute(select(DataChangeHistory).where(DataChangeHistory.module == "cash_advances"))).scalars().all()
                assert len(history) == 2 and {h.operation_type for h in history} == {"create", "confirm"}
            print("CASH_ADVANCE_ACTUAL", json.dumps({"created": first, "confirmed": second, "list_row": listing["data"][0], "summary": totals}, ensure_ascii=False))
    asyncio.run(run())


@pytest.mark.parametrize("uid,grant", [(1, False), (2, True), (3, True), (3, False), (4, True), (4, False), (5, True)])
def test_permission_matrix(tmp_path, monkeypatch, uid, grant):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, c):
            await set_perms(factory, uid, ["垫款单"] if grant else [])
            made = await create(c, uid)
            assert made.status_code == (200 if uid == 1 or uid == 4 and grant else 403), made.text
            for endpoint in ("", "/summary", "/payers"):
                r = await c.get(URL + endpoint, headers=auth(uid))
                assert r.status_code == (200 if uid == 1 or uid in (3, 4) and grant else 403), r.text
                if uid in (3, 4) and not grant: assert "无此操作权限" in r.json()["detail"]
            up = await c.post(URL + "/voucher", headers=auth(uid), files={"file": ("receipt.png", png(), "image/png")})
            assert up.status_code == (200 if uid == 1 or uid == 4 and grant else 403), up.text
            await set_perms(factory, 4, ["垫款单"])
            row = (await create(c, 4)).json()
            for action, data in (("confirm", {}), ("reject", {"reject_reason": "不实垫款"})):
                r = await c.post(f'{URL}/{row["id"]}/{action}', headers=auth(uid), json=data)
                if uid == 1:
                    assert r.status_code == (200 if action == "confirm" else 400)
                else:
                    assert r.status_code == 403 and r.json()["detail"] == "只有仓库管理员可以确认或驳回垫款单"
    asyncio.run(run())


def test_rejection_and_terminal_states(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, c):
            await set_perms(factory, 4, ["垫款单"])
            row = (await create(c, 4)).json(); aid = row["id"]
            for body in (None, {}, {"reject_reason": None}, {"reject_reason": " \n "}):
                r = await c.post(f"{URL}/{aid}/reject", headers=auth(1), **({"json": body} if body is not None else {}))
                assert r.status_code == 400 and r.json()["detail"] == "请填写驳回原因"
            r = await c.post(f"{URL}/{aid}/reject", headers=auth(1), json={"reject_reason": "  凭证不符  "})
            assert r.status_code == 200 and r.json()["status"] == "rejected" and r.json()["reject_reason"] == "凭证不符" and r.json()["outstanding_amount"] == 0
            for status in ("rejected", "confirmed", "repaid"):
                async with factory() as db:
                    item = await db.get(CashAdvance, aid); item.status = status; await db.commit()
                for action in ("confirm", "reject"):
                    r = await c.post(f"{URL}/{aid}/{action}", headers=auth(1), json={"reject_reason": "再次驳回"})
                    assert r.status_code == 400 and "不能重复确认或驳回" in r.json()["detail"]
    asyncio.run(run())


@pytest.mark.parametrize("changes", [{"amount": 0}, {"amount": -1}, {"amount": "NaN"}, {"amount": "Infinity"}, {"amount": "0.001"}, {"purpose": ""}, {"purpose": "invalid"}, {"advance_date": "bad-date"}, {"payer_name": "x" * 101}])
def test_invalid_input_creates_nothing(tmp_path, monkeypatch, changes):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, c):
            assert (await create(c, **changes)).status_code == 422
            assert (await c.get(URL, headers=auth(1))).json()["total"] == 0
    asyncio.run(run())


def test_warehouse_isolation_for_every_read_write_and_payer(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, c):
            async with factory() as db:
                db.add(User(id=7, username="other-admin", display_name="外仓老板", role="warehouse_admin", password_hash="unused", warehouse_id=2))
                db.add(UserWarehouse(user_id=7, warehouse_id=2)); await db.commit()
            await set_perms(factory, 4, ["垫款单"])
            aid = (await create(c)).json()["id"]
            for action in ("confirm", "reject"):
                r = await c.post(f"{URL}/{aid}/{action}", headers=auth(7), json={"reject_reason": "跨仓驳回"})
                assert r.status_code == 404
            assert (await c.get(URL, headers=auth(7))).json()["total"] == 0
            assert (await c.get(URL + "/summary", headers=auth(7))).json()["payer_count"] == 0
            payers = (await c.get(URL + "/payers", headers=auth(1))).json()["data"]
            assert 6 not in [p["id"] for p in payers] and 7 not in [p["id"] for p in payers]
            assert (await create(c, payer_id=6)).status_code == 400
            assert (await create(c, payer_id=999)).status_code == 400
            assert (await create(c, voucher_path="uploads/2/2026-10-18/cash-advances/a.png")).status_code == 400
            assert (await create(c, voucher_path="uploads/1/../cash-advances/a.png")).status_code == 400
            all_headers = {**auth(1), "X-Warehouse-ID": "all"}
            assert (await c.get(URL, headers=all_headers)).status_code == 400
            assert (await c.post(URL, headers=all_headers, json=BODY)).status_code == 400
            # Sending an inaccessible header never changes the authenticated account's scope.
            r = await c.get(URL, headers={**auth(7), "X-Warehouse-ID": "1"})
            assert r.status_code == 200 and r.json()["total"] == 0
    asyncio.run(run())


def test_filters_named_payers_precise_grouping_and_pending_exclusion(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, c):
            for fields in [dict(payer_name="张师傅", amount="0.10"), dict(payer_name="张师傅", amount="0.20"), dict(payer_id=4, amount="4000"), dict(payer_id=4, amount="3000", advance_date="2026-10-17")]:
                row = (await create(c, **fields)).json()
                assert row["status"] == "confirmed" and row["reviewed_by_id"] == 1
            await set_perms(factory, 4, ["垫款单"])
            await create(c, 4, payer_name="待确认的人", amount="999")
            s = (await c.get(URL + "/summary", headers=auth(1))).json()
            assert s["payer_count"] == 2 and s["total_outstanding"] == 7000.3
            assert [g["outstanding_amount"] for g in s["data"]] == [0.3, 7000]
            for query, count in [("status=pending", 1), ("status=confirmed", 4), ("payer_name=张师傅", 2), ("payer_id=4", 2), ("start_date=2026-10-17&end_date=2026-10-17", 1), ("payer_name=%25", 0)]:
                r = await c.get(URL + "?" + query, headers=auth(1)); assert r.status_code == 200 and r.json()["total"] == count, r.text
            r = await c.get(URL + "?page_size=2&page=2", headers=auth(1)); assert r.json()["total"] == 5 and len(r.json()["data"]) == 2
            assert (await c.get(URL + "?start_date=2026-10-19&end_date=2026-10-18", headers=auth(1))).status_code == 400
    asyncio.run(run())


def test_history_failure_rolls_back_registration_and_confirmation(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, factory, c):
            await set_perms(factory, 4, ["垫款单"])
            aid = (await create(c, 4)).json()["id"]
            async def fail(db, **kwargs): raise HTTPException(500, "模拟日志失败")
            monkeypatch.setattr(api, "record_history", fail)
            assert (await create(c)).status_code == 500
            assert (await c.post(f"{URL}/{aid}/confirm", headers=auth(1))).status_code == 500
            async with factory() as db:
                rows = (await db.execute(select(CashAdvance))).scalars().all()
                assert len(rows) == 1 and rows[0].status == "pending" and rows[0].reviewed_at is None
    asyncio.run(run())


def test_permission_backfill_once_only_for_existing_supervisor_and_staff(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (engine, factory, _):
            before = await finance_snapshot(factory)
            async with engine.begin() as conn: assert await backfill_cash_advances_permission(conn) == 2
            async with factory() as db:
                users = {u.id: u.extra_permissions for u in (await db.execute(select(User))).scalars()}
                assert users[3] == users[4] == ["垫款单"] and all(not p for uid, p in users.items() if uid not in (3, 4))
                assert (await db.execute(select(SystemSetting).where(SystemSetting.key == CASH_ADVANCES_PERMISSION_MARKER))).scalar_one()
            await set_perms(factory, 4, [])
            async with engine.begin() as conn: assert await backfill_cash_advances_permission(conn) == 0
            async with factory() as db: assert (await db.get(User, 4)).extra_permissions == []
            assert await finance_snapshot(factory) == before
    asyncio.run(run())


def test_bad_voucher_and_unknown_action(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, _, c):
            r = await c.post(URL + "/voucher", headers=auth(1), files={"file": ("fake.png", b"not an image", "image/png")})
            assert r.status_code == 400
            r = await c.post(URL + "/voucher", headers=auth(1), files={"file": ("huge.png", b"x" * (10*1024*1024+1), "image/png")})
            assert r.status_code == 400
            aid = (await create(c)).json()["id"]
            assert (await c.post(f"{URL}/{aid}/repay", headers=auth(1), json={"amount": 3000})).status_code == 404
    asyncio.run(run())
