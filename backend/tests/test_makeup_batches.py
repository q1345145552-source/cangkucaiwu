"""批次创建/撤销真实 HTTP、仓库隔离、工资重算和历史记录保护。"""
import ast
import asyncio
import copy
import json
import subprocess
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import event, select
from app.models import User, UserWarehouse, ClockInRecord, ClockInMakeupBatch
from app.models.payroll import PayrollRecord
from tests.test_round2_permissions import auth, set_perms
from tests.test_round3_permissions import hr_environment, snapshot
from tests.test_batch_makeup import BODY, DAY, assert_record_dict_only_adds_makeup_batch_id, seed_batch

BASE = "/api/v1/clock-in"


async def records_snapshot(factory):
    async with factory() as db:
        return [tuple(r) for r in (await db.execute(select(ClockInRecord.__table__).order_by(ClockInRecord.id))).all()]


async def calendar(client):
    r = await client.get("/api/v1/attendance/calendar?start_date=2026-10-18&end_date=2026-10-18", headers=auth(1))
    assert r.status_code == 200, r.text
    return {e["employee_id"]: e for e in r.json()["events"] if e["employee_id"] in (1, 3)}


def test_create_revoke_calendar_and_manual_payroll(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            await seed_batch(f, monkeypatch)
            old_records = await records_snapshot(f)
            old_payroll = await snapshot(f)
            counts = [f"{BASE}/makeup-count?employee_id={eid}&date=2026-10-18" for eid in (1, 3)]
            quota_before = [(await c.get(p, headers=auth(1))).json() for p in counts]
            created = await c.post(BASE + "/batch-makeup", headers=auth(1), json={**BODY, "employee_ids": [1, 3]})
            assert created.status_code == 200, created.text
            result = created.json(); bid = result["batch_id"]
            assert result["created_count"] == 8 and result["skipped_count"] == 0
            async with f() as db:
                batch = await db.get(ClockInMakeupBatch, bid)
                assert batch.created_count == 8 and batch.status == "active" and batch.operator_id == 1
                rows = (await db.execute(select(ClockInRecord).where(ClockInRecord.makeup_batch_id == bid))).scalars().all()
                assert len(rows) == 8 and all(r.is_makeup and not r.makeup_counts_toward_limit for r in rows)
            listed = await c.get(BASE + "/makeup-batches?start_date=2026-10-18&end_date=2026-10-18", headers=auth(1))
            assert listed.status_code == 200 and listed.json()["total"] == 1
            assert listed.headers["cache-control"] == "no-store"
            item = listed.json()["data"][0]
            assert item["id"] == bid and item["created_count"] == 8 and item["can_revoke"] and item["operator_name"] == "warehouse_admin"
            before = await calendar(c)
            assert {eid: e["work_hours"] for eid, e in before.items()} == {1: 8, 3: 8}
            assert await snapshot(f) == old_payroll
            import app.api.v1.payroll as payroll
            monkeypatch.setattr(payroll, "thai_today", lambda: date(2026, 10, 19))
            calc = await c.post("/api/v1/payroll/calculate", headers=auth(1), json={"employee_ids": [3], "end_date": DAY.isoformat()})
            assert calc.status_code == 200, calc.text
            async with f() as db:
                rec = (await db.execute(select(PayrollRecord).where(PayrollRecord.employee_id == 3))).scalar_one()
                old_id, before_net = rec.id, rec.net_pay
                assert before_net == 400
            before_revoke_payroll = await snapshot(f)
            revoked = await c.post(f"{BASE}/makeup-batches/{bid}/revoke", headers=auth(1), json={})
            assert revoked.status_code == 200, revoked.text
            assert revoked.json()["deleted_count"] == 8 and revoked.json()["batch"]["status"] == "revoked"
            assert revoked.json()["batch"]["revoked_by"] == 1 and revoked.json()["batch"]["revoked_at"]
            assert not revoked.json()["batch"]["can_revoke"]
            assert revoked.json()["batch"]["created_count"] == 8
            after = await calendar(c)
            assert {eid: e["work_hours"] for eid, e in after.items()} == {1: 0, 3: 0}
            assert await records_snapshot(f) == old_records
            assert await snapshot(f) == before_revoke_payroll  # 撤销补卡不自动重算工资。
            assert [(await c.get(p, headers=auth(1))).json() for p in counts] == quota_before
            listed_after = (await c.get(BASE + "/makeup-batches", headers=auth(1))).json()
            assert listed_after["data"][0]["status_label"] == "已撤销" and not listed_after["data"][0]["can_revoke"]
            again = await c.post(f"{BASE}/makeup-batches/{bid}/revoke", headers=auth(1), json={})
            assert again.status_code == 400 and again.json() == {"detail": "该批次已撤销"}
            recalc = await c.post(f"/api/v1/payroll/{old_id}/recalc", headers=auth(1), json={"void_reason": "测试撤销批量补卡后人工重算", "mode": "recalc"})
            assert recalc.status_code == 200, recalc.text
            async with f() as db:
                new_rec = await db.get(PayrollRecord, recalc.json()["new_record_id"])
                assert new_rec.net_pay == 0 and new_rec.base_pay == 0
                assert all(d["hours"] == 0 for d in json.loads(new_rec.detail)["daily_hours"])
                old = await db.get(PayrollRecord, old_id)
                assert old.voided and old.net_pay == before_net
            print("MAKEUP_BATCH_CREATED", json.dumps({k: result[k] for k in ("message", "batch_id", "created_count", "skipped_count")}, ensure_ascii=False))
            print("MAKEUP_BATCH_REVOKED", json.dumps(revoked.json(), ensure_ascii=False))
            print("MAKEUP_BATCH_CALENDAR", json.dumps({"before": before, "after": after}, ensure_ascii=False))
            print("MAKEUP_BATCH_PAYROLL", {"before_net": before_net, "after_manual_recalc_net": new_rec.net_pay})
            print("MAKEUP_BATCH_QUOTA", quota_before)
    asyncio.run(run())


def test_revoke_only_own_new_records_preserves_skipped_and_legacy(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            await seed_batch(f, monkeypatch)
            async with f() as db:
                db.add(ClockInRecord(user_id=5, warehouse_id=1, clock_date=DAY, session=1, clocked_in_at=datetime(2026, 10, 18, 10), status="late_one", penalty_amount=99))
                await db.commit()
            old = await records_snapshot(f)
            a = (await c.post(BASE + "/batch-makeup", headers=auth(1), json={**BODY, "sessions": [1, 4]})).json()
            assert (a["created_count"], a["skipped_count"]) == (1, 1)
            b = (await c.post(BASE + "/batch-makeup", headers=auth(1), json=BODY)).json()
            assert (b["created_count"], b["skipped_count"]) == (2, 2)
            empty = (await c.post(BASE + "/batch-makeup", headers=auth(1), json=BODY)).json()
            assert (empty["created_count"], empty["skipped_count"]) == (0, 4)
            for batch, expected in ((empty, 0), (a, 1), (b, 2)):
                r = await c.post(f"{BASE}/makeup-batches/{batch['batch_id']}/revoke", headers=auth(1), json={})
                assert r.status_code == 200 and r.json()["deleted_count"] == expected
            assert await records_snapshot(f) == old
            await set_perms(f, 4, ["考勤"])
            single = await c.post(BASE + "/makeup", headers=auth(4), json={"employee_id": 1, "date": "2026-10-15", "sessions": [1], "reason": "旧单条路径"})
            assert single.status_code == 200 and single.json()["used_days"] == 2
            async with f() as db:
                record = (await db.execute(select(ClockInRecord).where(ClockInRecord.clock_date == date(2026, 10, 15)))).scalar_one()
                assert record.makeup_batch_id is None and record.makeup_counts_toward_limit
    asyncio.run(run())


@pytest.mark.parametrize("uid", [2, 3, 4, 5, 6])
def test_other_roles_cannot_list_or_revoke(tmp_path, monkeypatch, uid):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            await seed_batch(f, monkeypatch); await set_perms(f, uid, ["考勤"])
            created = (await c.post(BASE + "/batch-makeup", headers=auth(1), json=BODY)).json()
            before = await records_snapshot(f)
            for method, path in (("GET", BASE + "/makeup-batches"), ("POST", f"{BASE}/makeup-batches/{created['batch_id']}/revoke")):
                r = await c.request(method, path, headers=auth(uid))
                assert r.status_code == 403 and r.json() == {"detail": "超级管理员请使用各仓库管理员账号操作" if uid == 2 else "无权访问" if uid in (5,6) else "只能由仓库管理员查看或撤销补卡批次"}
            assert await records_snapshot(f) == before
    asyncio.run(run())


def test_history_warehouse_filter_pagination_and_unknown_batch(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            await seed_batch(f, monkeypatch)
            async with f() as db:
                db.add(User(id=99, username="other_admin", display_name="外仓管理员", role="warehouse_admin", warehouse_id=2, password_hash="unused"))
                db.add(UserWarehouse(user_id=99, warehouse_id=2)); await db.commit()
            mine = (await c.post(BASE + "/batch-makeup", headers=auth(1), json=BODY)).json()["batch_id"]
            other = (await c.post(BASE + "/batch-makeup", headers=auth(99), json={**BODY, "employee_ids": [2]})).json()["batch_id"]
            second = (await c.post(BASE + "/batch-makeup", headers=auth(1), json={**BODY, "date": "2026-10-17"})).json()["batch_id"]
            for uid, ids in ((1, {mine, second}), (99, {other})):
                r = await c.get(BASE + "/makeup-batches", headers=auth(uid)); assert r.status_code == 200
                assert r.json()["total"] == len(ids) and {x["id"] for x in r.json()["data"]} == ids
            for page in (1, 2):
                r = await c.get(f"{BASE}/makeup-batches?page_size=1&page={page}", headers=auth(1))
                assert r.json()["total"] == 2 and len(r.json()["data"]) == 1
            r = await c.get(BASE + "/makeup-batches?start_date=2026-10-18&end_date=2026-10-18", headers=auth(1))
            assert r.json()["total"] == 1 and r.json()["data"][0]["id"] == mine
            assert (await c.get(BASE + "/makeup-batches?start_date=2026-10-19", headers=auth(1))).json()["total"] == 0
            for query, code in (("start_date=bad", 422), ("start_date=2026-10-19&end_date=2026-10-18", 400), ("page=0", 422)):
                assert (await c.get(BASE + "/makeup-batches?" + query, headers=auth(1))).status_code == code
            for bid in (other, 999):
                r = await c.post(f"{BASE}/makeup-batches/{bid}/revoke", headers={**auth(1), "X-Warehouse-ID": "2"}, json={})
                assert r.status_code == 403
                unknown = await c.post(f"{BASE}/makeup-batches/{bid}/revoke", headers=auth(1), json={})
                assert unknown.status_code == 404
            # 授权多仓管理员选择仓2时，也只列出/撤销该当前仓，不能碰仓1。
            async with f() as db: db.add(UserWarehouse(user_id=1, warehouse_id=2)); await db.commit()
            r = await c.get(BASE + "/makeup-batches", headers={**auth(1), "X-Warehouse-ID": "2"})
            assert {x["id"] for x in r.json()["data"]} == {other}
            assert (await c.post(f"{BASE}/makeup-batches/{mine}/revoke", headers={**auth(1), "X-Warehouse-ID": "2"})).status_code == 404
    asyncio.run(run())


@pytest.mark.parametrize("operation", ["create", "revoke"])
def test_batch_and_records_rollback_together(tmp_path, monkeypatch, operation):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            await seed_batch(f, monkeypatch)
            bid = None
            if operation == "revoke": bid = (await c.post(BASE + "/batch-makeup", headers=auth(1), json=BODY)).json()["batch_id"]
            before = await records_snapshot(f)
            def fail(*args): raise RuntimeError("simulated database failure")
            model, action = (ClockInRecord, "before_insert") if operation == "create" else (ClockInMakeupBatch, "before_update")
            event.listen(model, action, fail)
            try:
                with pytest.raises(RuntimeError, match="simulated database failure"):
                    await c.post(BASE + "/batch-makeup" if operation == "create" else f"{BASE}/makeup-batches/{bid}/revoke", headers=auth(1), json=BODY if operation == "create" else {})
            finally: event.remove(model, action, fail)
            assert await records_snapshot(f) == before
            async with f() as db:
                batches = (await db.execute(select(ClockInMakeupBatch))).scalars().all()
                assert len(batches) == (0 if operation == "create" else 1)
                if batches: assert batches[0].status == "active" and batches[0].revoked_at is None
    asyncio.run(run())


def test_first_round_logic_and_quota_unchanged_except_batch_link():
    from tests.full_day_leave_test_support import before_full_day_guards
    root = Path(__file__).resolve().parents[2]
    filename = "backend/app/api/v1/clock_in.py"
    old = ast.parse(subprocess.check_output(["git", "show", "f8a4341:" + filename], cwd=root, text=True))
    new = ast.parse(before_full_day_guards((root / filename).read_text()))
    funcs = lambda tree: {n.name: copy.deepcopy(n) for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    previous, current = funcs(old), funcs(new)
    for name in previous:
        if name not in ("batch_makeup_clock_in", "list_records"): assert ast.dump(previous[name]) == ast.dump(current[name]), name
    assert_record_dict_only_adds_makeup_batch_id(
        subprocess.check_output(["git", "show", "f8a4341:" + filename], cwd=root, text=True),
        (root / filename).read_text(),
    )
    batch = current["batch_makeup_clock_in"]
    start = next(i for i, n in enumerate(batch.body) if isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == "batch")
    assert ast.unparse(batch.body[start + 1]) == "db.add(batch)" and ast.unparse(batch.body[start + 2]) == "await db.flush()"
    del batch.body[start:start + 3]
    batch.body = [n for n in batch.body if not (isinstance(n, ast.Assign) and ast.unparse(n.targets[0]) == "batch.created_count")]
    class Unlink(ast.NodeTransformer):
        def visit_Call(self, node):
            node.keywords = [kw for kw in node.keywords if kw.arg != "makeup_batch_id"]
            return self.generic_visit(node)
        def visit_Dict(self, node):
            pairs = [(k, v) for k, v in zip(node.keys, node.values) if not (isinstance(k, ast.Constant) and k.value == "batch_id")]
            node.keys, node.values = [k for k, _ in pairs], [v for _, v in pairs]
            return self.generic_visit(node)
    assert ast.dump(Unlink().visit(batch)) == ast.dump(previous["batch_makeup_clock_in"])
