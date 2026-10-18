"""批量补卡真实 HTTP、额度、配置时点、工资与原记录快照验证。"""
import ast
import asyncio
import json
import subprocess
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import delete, select
from app.models import User, UserWarehouse, Employee, ClockInRecord, LeaveRequest, RestDay, SystemSetting
from app.models.payroll import PayrollRecord
from app.core.timezone import THAI_TZ
from tests.test_round2_permissions import auth, set_perms
from tests.test_round3_permissions import hr_environment, snapshot

DAY = date(2026, 10, 18)
BODY = {"date": DAY.isoformat(), "employee_ids": [1], "sessions": [1, 2, 3, 4], "reason": "系统故障"}


async def seed_batch(factory, monkeypatch):
    import app.api.v1.clock_in as clock
    import app.api.v1.payroll as payroll
    monkeypatch.setattr(clock, "thai_today", lambda: DAY)
    monkeypatch.setattr(payroll, "thai_today", lambda: DAY)
    async with factory() as db:
        # 本仓五人，取消两位请假、一位休息后选中两人。
        employee = await db.get(Employee, 1)
        employee.status = "regular"
        employee.hire_date = datetime(2026, 10, 17)
        for eid, name in [(3, "选中员工B"), (4, "请假员工A"), (5, "请假员工B"), (6, "休息员工")]:
            uid = eid + 10
            db.add(User(id=uid, username=f"batch{eid}", display_name=name, role="warehouse_labor", warehouse_id=1, password_hash="unused", extra_permissions=[]))
            db.add(UserWarehouse(user_id=uid, warehouse_id=1))
            db.add(Employee(id=eid, name=name, warehouse_id=1, user_id=uid, status="regular", hire_date=datetime(2026, 10, 18), salary_template_id=1, deduction_template_id=1))
        for eid in (4, 5):
            db.add(LeaveRequest(employee_id=eid, warehouse_id=1, leave_date=DAY, leave_type="personal", duration_type="full", status="approved"))
        db.add(RestDay(employee_id=6, warehouse_id=1, rest_date=DAY))
        # 与默认不同的配置：08:30/11:30/12:30/17:30，仍为8小时。
        for key, value in {"morning_start": "08:30", "noon_break_start": "11:30", "noon_break_end": "12:30", "afternoon_end": "17:30"}.items():
            db.add(SystemSetting(warehouse_id=1, key=f"schedule_{key}", value=value))
        # 一条历史普通补卡已经占用一天额度。
        db.add(ClockInRecord(user_id=5, warehouse_id=1, clock_date=date(2026, 10, 16), session=1, clocked_in_at=datetime(2026, 10, 16, 9), is_makeup=True))
        await db.commit()


@pytest.mark.parametrize("uid", [2, 3, 4, 5, 6])
def test_only_warehouse_admin(tmp_path, monkeypatch, uid):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            await set_perms(f, uid, ["考勤"])
            r = await c.post("/api/v1/clock-in/batch-makeup", headers=auth(uid), json=BODY)
            assert r.status_code == 403 and r.json() == {"detail": "只能由仓库管理员批量补卡"}
            async with f() as db:
                assert not (await db.execute(select(ClockInRecord))).first()
            print("BATCH_ROLE", uid, r.status_code, r.json())
    asyncio.run(run())


def test_selected_people_sessions_quota_payroll_and_single_makeup(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            await seed_batch(f, monkeypatch)
            old_payroll = await snapshot(f)
            count_path = "/api/v1/clock-in/makeup-count?employee_id=1&date=2026-10-18"
            before = (await c.get(count_path, headers=auth(1))).json()
            assert before == {"used_days": 1, "remaining": 1}
            fresh_path = "/api/v1/clock-in/makeup-count?employee_id=3&date=2026-10-18"
            fresh_before = (await c.get(fresh_path, headers=auth(1))).json()
            assert fresh_before == {"used_days": 0, "remaining": 2}
            body = {**BODY, "employee_ids": [1, 3]}
            r = await c.post("/api/v1/clock-in/batch-makeup", headers=auth(1), json=body)
            assert r.status_code == 200, r.text
            assert (r.json()["created_count"], r.json()["skipped_count"]) == (8, 0)
            async with f() as db:
                rows = (await db.execute(select(ClockInRecord).where(ClockInRecord.clock_date == DAY))).scalars().all()
                assert len(rows) == 8 and {x.user_id for x in rows} == {5, 13}
                for row in rows:
                    assert row.is_makeup and not row.makeup_counts_toward_limit
                    assert row.makeup_by == 1 and row.makeup_at and row.makeup_reason == "系统故障"
                    assert row.clocked_in_at.strftime("%H:%M") == {1: "08:30", 2: "11:30", 3: "12:30", 4: "17:30"}[row.session]
                protected = [tuple(x) for x in (await db.execute(select(LeaveRequest.__table__))).all()]
            again = await c.post("/api/v1/clock-in/batch-makeup", headers=auth(1), json=body)
            assert again.status_code == 200 and (again.json()["created_count"], again.json()["skipped_count"]) == (0, 8)
            partial = await c.post("/api/v1/clock-in/batch-makeup", headers=auth(1), json={**body, "date": "2026-10-17", "sessions": [1, 4]})
            assert partial.status_code == 200 and partial.json()["created_count"] == 4
            async with f() as db:
                rows = (await db.execute(select(ClockInRecord).where(ClockInRecord.clock_date == date(2026, 10, 17)))).scalars().all()
                assert len(rows) == 4 and {x.session for x in rows} == {1, 4}
            after = (await c.get(count_path, headers=auth(1))).json()
            assert after == before
            fresh_after = (await c.get(fresh_path, headers=auth(1))).json()
            assert fresh_after == fresh_before
            records = await c.get("/api/v1/clock-in/records?start_date=2026-10-18&end_date=2026-10-18", headers=auth(1))
            assert records.status_code == 200 and len(records.json()["records"]) == 8
            assert all(r["is_makeup"] and r["makeup_by"] == 1 and r["makeup_reason"] == "系统故障" and r["makeup_at"] for r in records.json()["records"])
            # 打卡记录接口必须回传批次号，前端详情用它显示「补卡批次」
            assert {x["makeup_batch_id"] for x in records.json()["records"]} == {r.json()["batch_id"]}
            assert await snapshot(f) == old_payroll
            cal = await c.get("/api/v1/attendance/calendar?start_date=2026-10-18&end_date=2026-10-18", headers=auth(1))
            assert cal.status_code == 200, cal.text
            selected = {e["employee_id"]: e["work_hours"] for e in cal.json()["events"] if e["employee_id"] in (1, 3)}
            assert selected == {1: 8, 3: 8}, cal.text
            # 不重算老单，先前快照一致；只对测试的另一名员工人工算工资。
            # 正常工资不结算尚未过完的今天，仅在隔离测试把工资侧日期推进到次日。
            import app.api.v1.payroll as payroll
            monkeypatch.setattr(payroll, "thai_today", lambda: date(2026, 10, 19))
            calc = await c.post("/api/v1/payroll/calculate", headers=auth(1), json={"employee_ids": [3], "end_date": "2026-10-18"})
            assert calc.status_code == 200, calc.text
            async with f() as db:
                rec = (await db.execute(select(PayrollRecord).where(PayrollRecord.employee_id == 3))).scalar_one()
                details = json.loads(rec.detail)
                full_day = next(d for d in details["daily_hours"] if d["date"] == DAY.isoformat())
                assert full_day["hours"] == 8 and full_day["attendance"] == 1
                assert rec.base_pay == rec.net_pay == 400
                assert [tuple(x) for x in (await db.execute(select(LeaveRequest.__table__))).all()] == protected
                payroll_result = {"day_hours": full_day["hours"], "day_pay": rec.base_pay, "net_pay": rec.net_pay}
            # 主管普通单条补卡继续生效并占额度；批量已经用掉的日期仍不占。
            await set_perms(f, 4, ["考勤"])
            single = await c.post("/api/v1/clock-in/makeup", headers=auth(4), json={"employee_id": 1, "date": "2026-10-15", "sessions": [1], "reason": "普通漏打"})
            assert single.status_code == 200 and single.json()["used_days"] == 2, single.text
            print("BATCH_SELECTED", json.dumps(r.json(), ensure_ascii=False))
            print("BATCH_EXCLUDED", {"leave_employees": [4, 5], "rest_employee": 6, "records": 0})
            print("BATCH_PARTIAL", json.dumps(partial.json(), ensure_ascii=False))
            print("BATCH_REPEAT", json.dumps(again.json(), ensure_ascii=False))
            print("BATCH_QUOTA", before, after)
            print("BATCH_FRESH_QUOTA", fresh_before, fresh_after)
            print("BATCH_PAYROLL", payroll_result)
            print("SINGLE_MAKEUP", single.json())
    asyncio.run(run())


@pytest.mark.parametrize("patch,status", [
    ({"date": "2026-10-19"}, 400), ({"reason": "   "}, 400),
    ({"employee_ids": []}, 422), ({"sessions": []}, 422),
    ({"sessions": [0, 5]}, 400), ({"sessions": [True]}, 422),
    ({"employee_ids": [1, 2]}, 404), ({"employee_ids": [1, 999]}, 404),
])
def test_invalid_batch_is_atomic(tmp_path, monkeypatch, patch, status):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            await seed_batch(f, monkeypatch)
            async with f() as db:
                before = [tuple(x) for x in (await db.execute(select(ClockInRecord.__table__))).all()]
            r = await c.post("/api/v1/clock-in/batch-makeup", headers={**auth(1), "X-Warehouse-ID": "2"}, json={**BODY, **patch})
            assert r.status_code == status, r.text
            async with f() as db:
                assert [tuple(x) for x in (await db.execute(select(ClockInRecord.__table__))).all()] == before
    asyncio.run(run())


@pytest.mark.parametrize("problem", ["no_account", "cross_account", "resigned", "deleted"])
def test_bad_employee_rejects_whole_batch(tmp_path, monkeypatch, problem):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            await seed_batch(f, monkeypatch)
            async with f() as db:
                employee = await db.get(Employee, 3)
                if problem == "no_account": employee.user_id = None; employee.name = "无账号"
                if problem == "cross_account":
                    db.add(User(id=99, username="cross_account", display_name="外仓账号", role="warehouse_labor", warehouse_id=2, password_hash="unused"))
                    await db.flush()
                    employee.user_id = 99
                if problem == "resigned": employee.status = "resigned"
                if problem == "deleted": employee.is_deleted = True
                await db.commit()
            r = await c.post("/api/v1/clock-in/batch-makeup", headers=auth(1), json={**BODY, "employee_ids": [1, 3]})
            assert r.status_code in (400, 404), r.text
            async with f() as db:
                assert not (await db.execute(select(ClockInRecord).where(ClockInRecord.clock_date == DAY))).first()
    asyncio.run(run())


def test_existing_late_record_untouched_and_input_deduplicated(tmp_path, monkeypatch):
    async def run():
        async with hr_environment(tmp_path, monkeypatch) as (_, f, c):
            await seed_batch(f, monkeypatch)
            async with f() as db:
                db.add(ClockInRecord(user_id=5, warehouse_id=1, clock_date=DAY, session=1, clocked_in_at=datetime(2026, 10, 18, 10), status="late_one", penalty_amount=99))
                await db.commit()
                before = tuple((await db.execute(select(ClockInRecord.__table__).where(ClockInRecord.clock_date == DAY))).one())
            r = await c.post("/api/v1/clock-in/batch-makeup", headers=auth(1), json={**BODY, "employee_ids": [1, 1], "sessions": [1, 1, 4]})
            assert r.status_code == 200 and (r.json()["created_count"], r.json()["skipped_count"]) == (1, 1)
            async with f() as db:
                assert tuple((await db.execute(select(ClockInRecord.__table__).where(ClockInRecord.clock_date == DAY, ClockInRecord.session == 1))).one()) == before
    asyncio.run(run())


def assert_record_dict_only_adds_makeup_batch_id(before_src, after_src):
    """list_records 的打卡记录字典只允许新增 makeup_batch_id，其余键与取值顺序保持不变。"""
    def record_dict(src):
        tree = ast.parse(src)
        fn = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "list_records")
        for node in ast.walk(fn):
            if isinstance(node, ast.Dict):
                keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
                if "is_makeup" in keys:
                    return node
        raise AssertionError("未找到 list_records 的打卡记录序列化字典")
    old_dict, new_dict = record_dict(before_src), record_dict(after_src)
    old_keys = [k.value for k in old_dict.keys if isinstance(k, ast.Constant)]
    new_keys = [k.value for k in new_dict.keys if isinstance(k, ast.Constant)]
    assert [k for k in new_keys if k not in old_keys] == ["makeup_batch_id"], new_keys
    assert [k for k in new_keys if k != "makeup_batch_id"] == old_keys, new_keys
    pairs = [(k, v) for k, v in zip(new_dict.keys, new_dict.values)
             if not (isinstance(k, ast.Constant) and k.value == "makeup_batch_id")]
    new_dict.keys = [k for k, _ in pairs]
    new_dict.values = [v for _, v in pairs]
    assert ast.dump(new_dict) == ast.dump(old_dict)


def test_single_makeup_function_and_unrelated_business_unchanged():
    root = Path(__file__).resolve().parents[2]
    filename = "backend/app/api/v1/clock_in.py"
    original = subprocess.check_output(["git", "show", "c515151:" + filename], cwd=root, text=True)
    current = (root / filename).read_text()
    functions = lambda s: {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(s).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    old, new = functions(original), functions(current)
    for key in old:
        if key not in ("_count_makeup_days", "list_records"): assert new[key] == old[key], key
    assert_record_dict_only_adds_makeup_batch_id(original, current)
    for filename in ("backend/app/api/v1/attendance.py", "backend/app/api/v1/payroll.py", "backend/app/services/schedule.py"):
        baseline = subprocess.check_output(["git", "show", "c515151:" + filename], cwd=root)
        if filename.endswith("/payroll.py"):
            # 后续允许发放选择垫款；工资计算及其他函数仍严格守住补卡前的版本。
            changed = {"list_payroll", "batch_disburse_payroll", "disburse_payroll", "revoke_disbursement", "_disbursement_funding", "payroll_cash_advance_sources"}
            before_funcs, after_funcs = functions(baseline), functions((root / filename).read_text())
            assert {k: v for k, v in before_funcs.items() if k not in changed} == {k: v for k, v in after_funcs.items() if k not in changed}
        else:
            assert (root / filename).read_bytes() == baseline

    # 本轮只给唯一清单追加垫款单；其余菜单仍与补卡前相同。
    registry = "backend/app/core/menu_registry.py"
    current_registry = (root / registry).read_text()
    without_cash = "\n".join(line for line in current_registry.split("\n") if 'MenuPermission("cash_advances"' not in line)
    assert without_cash == subprocess.check_output(["git", "show", "c515151:" + registry], cwd=root, text=True)
