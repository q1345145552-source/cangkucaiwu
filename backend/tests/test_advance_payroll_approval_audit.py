"""预支审批过滤复核：真实接口算薪、手动重算和只读 PostgreSQL 历史审计。"""
import asyncio
import json
import os
from pathlib import Path

import pytest

import app.api.v1.payroll as payroll
from app.models.employee_advance import EmployeeAdvance
from tests.test_employee_advance_expense import BODY, supervisor_self
from tests.test_round2_permissions import auth
from tests.test_round3_permissions import hr_environment, snapshot
from tests.test_round18_advance_review import (
    add, calculate, get, period_record, prepare_work,
)
from tests.test_round12_migration_postgres import PostgreSQLConnection


def test_pending_1000_approved_only_after_manual_recalc(tmp_path, monkeypatch):
    async def run():
        from datetime import date

        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            monkeypatch.setattr(payroll, "thai_today", lambda: date(2026, 10, 20))
            await supervisor_self(factory)
            legacy = await snapshot(factory)
            base = "/api/v1/employee-advances"
            pending = await client.post(base, headers=auth(4), json=BODY)
            assert pending.status_code == 200, pending.text
            aid = pending.json()["id"]
            async with factory() as db:
                assert (await db.get(EmployeeAdvance, aid)).amount == 1000
            assert pending.json()["approval_status"] == "pending"
            rejected = await client.post(base, headers=auth(4), json={**BODY, "amount": 5000})
            assert rejected.status_code == 200, rejected.text
            rid = rejected.json()["id"]
            response = await client.post(f"{base}/{rid}/reject", headers=auth(1),
                json={"reject_reason": "隔离验证：不参与工资抵扣"})
            assert response.status_code == 200 and response.json()["approval_status"] == "rejected"

            await calculate(client, "2026-10-18")
            before = await period_record(factory)
            assert (before.base_pay, before.advance_deduction, before.net_pay) == (1200, 0, 1200)
            assert json.loads(before.detail)["advance_deductions"] == []
            assert before.remaining_debt == 0
            saved = await snapshot(factory)
            approved = await client.post(f"{base}/{aid}/approve", headers=auth(1))
            assert approved.status_code == 200, approved.text
            assert approved.json()["amount"] == 1000
            assert approved.json()["approval_status"] == "approved"
            assert await snapshot(factory) == saved  # 审批不会自动改变已经算出的工资。

            response = await client.post(f"/api/v1/payroll/{before.id}/recalc", headers=auth(1),
                json={"mode": "recalc", "void_reason": "验证审批通过后才扣1000"})
            assert response.status_code == 200, response.text
            after = await period_record(factory)
            assert (after.base_pay, after.advance_deduction, after.net_pay) == (1200, 1000, 200)
            assert before.net_pay - after.net_pay == 1000
            assert json.loads(after.detail)["advance_deductions"] == [{"advance_id": aid, "amount": 1000}]
            assert (await get(factory, rid))["deducted_amount"] == 0
            response = await client.post(f"/api/v1/payroll/{after.id}/recalc", headers=auth(1),
                json={"mode": "recalc", "void_reason": "验证重复重算不重复扣款"})
            assert response.status_code == 200, response.text
            repeated = await period_record(factory)
            assert (repeated.advance_deduction, repeated.net_pay) == (1000, 200)
            assert (await get(factory, aid))["deducted_amount"] == 1000
            current = await snapshot(factory)
            assert [row for row in current if row[0] in {r[0] for r in legacy}] == legacy
            print("ADVANCE_APPROVAL_1000", json.dumps({
                "gross_pay": 1200, "pending_advance": 1000,
                "pending_deduction": before.advance_deduction, "pending_net": before.net_pay,
                "approved_deduction": after.advance_deduction, "approved_net": after.net_pay,
                "difference": before.net_pay - after.net_pay,
                "rejected_advance": 5000, "rejected_deduction": 0,
                "repeated_recalc_net": repeated.net_pay, "legacy_payroll_unchanged": True,
            }, ensure_ascii=False))
    asyncio.run(run())


def test_approved_current_amount_minus_previously_deducted(tmp_path, monkeypatch):
    async def run():
        from datetime import date

        async with hr_environment(tmp_path, monkeypatch) as (_, factory, client):
            monkeypatch.setattr(payroll, "thai_today", lambda: date(2026, 10, 20))
            await prepare_work(factory)
            aid = await add(factory, status="approved", amount=750.25)
            async with factory() as db:
                advance = await db.get(EmployeeAdvance, aid)
                advance.deducted_amount, advance.status = 100, "partial"
                await db.commit()
            await calculate(client, "2026-10-18")
            pay = await period_record(factory)
            assert (pay.advance_deduction, pay.net_pay) == (650.25, 549.75)
            assert (await get(factory, aid))["deducted_amount"] == 750.25
    asyncio.run(run())


@pytest.mark.skipif(not os.environ.get("PGLITE_NODE"), reason="Set PGLITE_NODE and NODE_PATH for embedded PostgreSQL")
def test_history_audit_tracks_suspects_missing_evidence_and_never_writes():
    async def run():
        process = await asyncio.create_subprocess_exec(os.environ["PGLITE_NODE"],
            str(Path(__file__).with_name("postgres_bridge.cjs")),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        conn = PostgreSQLConnection(process)
        try:
            await conn.execute("""CREATE TABLE employee_advances (
                id INTEGER, warehouse_id INTEGER, employee_id INTEGER,
                approval_status TEXT, reviewed_at TIMESTAMPTZ, currency TEXT)""")
            await conn.execute("""CREATE TABLE payroll_records (
                id INTEGER, warehouse_id INTEGER, employee_id INTEGER, created_at TIMESTAMPTZ,
                voided BOOLEAN, advance_deduction NUMERIC, detail TEXT)""")
            await conn.execute("""INSERT INTO employee_advances VALUES
                (1,1,1,'pending',NULL,'THB'), (2,1,1,'rejected','2026-10-18','THB'),
                (3,1,1,'approved','2026-10-18','CNY'), (4,1,1,'approved',NULL,'THB'),
                (5,2,1,'approved','2026-10-01','THB'), (6,1,1,'approved','2026-10-01','THB'),
                (7,1,1,NULL,NULL,'THB')""")
            cases = [
                (1, False, 300, [{"advance_id": 1, "amount": 100}, {"advance_id": 2, "amount": 200}]),
                (2, True, 100, [{"advance_id": 1, "amount": 100}]),
                (3, False, 50, [{"advance_id": 3, "amount": 50}]),
                (4, False, 60, [{"advance_id": 4, "amount": 60}]),
                (5, False, 150, [{"advance_id": 99, "amount": 70}, {"advance_id": 5, "amount": 80}]),
                (6, False, 90, [{"advance_id": 6, "amount": 90}]),
                (7, False, 10, "not json"),
                (8, False, 20, [{"advance_id": "invalid", "amount": "invalid"}]),
                (9, False, 30, [{"advance_id": 7, "amount": 30}]),
                (10, False, 0, []),
            ]
            for pid, voided, amount, deductions in cases:
                detail = deductions if isinstance(deductions, str) else json.dumps({"advance_deductions": deductions})
                literal = "'" + detail.replace("'", "''") + "'"
                await conn.execute(f"INSERT INTO payroll_records VALUES ({pid},1,1,'2026-10-16', {str(voided).lower()}, {amount}, {literal})")
            original_payroll = await conn.execute("SELECT * FROM payroll_records ORDER BY id")
            original_advances = await conn.execute("SELECT * FROM employee_advances ORDER BY id")
            script = (Path(__file__).parents[1] / "scripts/audit_advance_payroll.sql").read_text()
            begin, query = script.split(";", 1)
            query, rollback = query.rsplit(";", 2)[:2]
            await conn.execute(begin)
            result = (await conn.execute(query))[0]["advance_payroll_audit"]
            assert result["transaction_read_only"] == "on"
            # The audit transaction itself must reject a write, even if a caller attempts one.
            with pytest.raises(RuntimeError, match="read-only"):
                await conn.execute("UPDATE payroll_records SET advance_deduction=0")
            await conn.execute(rollback)
            assert result["payroll_count"] == 10 and result["advance_count"] == 7
            assert result["currently_unapproved_payroll_count"] == 2
            assert result["approved_after_creation_payroll_count"] == 1
            groups = {row["issue"]: row for row in result["issues_by_warehouse_currency"]}
            pending = groups["currently_unapproved"]
            assert (pending["payroll_count"], pending["active_payroll_count"], pending["amount"], pending["active_amount"]) == (2, 1, 400, 300)
            late = groups["approved_after_payroll_creation"]
            assert (late["currency"], late["amount"]) == ("CNY", 50)
            assert result["coverage"] == {
                "missing_or_foreign_advance_lines": 2,
                "invalid_deduction_lines": 1,
                "deduction_without_valid_detail": 1,
                "deduction_detail_amount_mismatch": 2,
                "approved_without_review_time_lines": 1,
                "unknown_approval_status_lines": 1,
            }
            missing = result["missing_or_foreign_advance_details"]
            assert [r["advance_id"] for r in missing] == [5, 99]
            unknown = next(r for r in result["unresolved_by_warehouse_currency"] if r["reason"] == "missing_or_foreign_advance")
            assert unknown["currency"] == "<unknown>" and unknown["amount"] == 150
            assert await conn.execute("SELECT * FROM payroll_records ORDER BY id") == original_payroll
            assert await conn.execute("SELECT * FROM employee_advances ORDER BY id") == original_advances
        finally:
            process.stdin.close()
            await process.wait()
    asyncio.run(run())
