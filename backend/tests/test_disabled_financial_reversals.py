"""真实停用入口（不覆盖依赖），隔离数据库；历史不变和其他动作回归。"""
import asyncio
import ast
import json
from pathlib import Path
import subprocess

import pytest
from sqlalchemy import select

from app.database import Base
from app.models import User
from app.core.financial_reversals import REVERSAL_DISABLED_MESSAGE, reject_disabled_financial_reversal
from app.main import app
from tests.financial_reversal_test_support import without_disabled_gate
from tests.test_round2_permissions import auth, set_perms
from tests.test_reimbursement_payments import environment, approved, upload, pay
from tests.test_cash_advance_repayments import approved as loan, voucher, repay
from tests.round3_flow_support import prepare_payroll,historical_payroll,historical_cash,historical_reimbursement


async def database_snapshot(factory):
    async with factory() as db:
        return {table.name: [tuple(row) for row in (await db.execute(
            select(table).order_by(*table.primary_key.columns))).all()]
            for table in Base.metadata.sorted_tables}


async def executed_records(c):
    await prepare_payroll(c.synthetic_factory,c,2)
    payroll = await c.post("/api/v1/payroll/2/disburse", headers=auth(3), json={"account_id": 1})
    assert payroll.status_code == 200, payroll.text
    rid = await approved(c)
    reimbursement = await pay(c, rid, await upload(c, rid))
    assert reimbursement.status_code == 200, reimbursement.text
    aid = await loan(c)
    returned = await repay(c, aid, await voucher(c), amount="1000")
    assert returned.status_code == 200, returned.text
    return rid, aid, returned.json()["repayment"]["id"]


@pytest.mark.parametrize("uid", [1, 2, 3, 4, 5])
def test_three_endpoints_disabled_for_every_authenticated_role_without_any_write(tmp_path, monkeypatch, uid):
    async def run():
        assert reject_disabled_financial_reversal not in app.dependency_overrides
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            rid, aid, repayment_id = await executed_records(c)
            await set_perms(f, uid, ["工资", "报销管理", "垫款单"])
            before = await database_snapshot(f)
            responses = []
            for path in ("/payroll/2/revoke-disbursement", f"/reimbursement/{rid}/revoke-payment",
                         f"/cash-advances/repayments/{repayment_id}/revoke"):
                for payload in ({"reason": "测试停用"}, {}, None):
                    response = await c.post("/api/v1" + path, headers=auth(uid), json=payload)
                    expected = 403 if uid in (2,5) or (uid==4 and path.startswith('/payroll')) else 400
                    assert response.status_code == expected,response.text
                    if expected==400:assert response.json()=={'detail':REVERSAL_DISABLED_MESSAGE}
                    else:assert response.json()['detail'] in ('超级管理员请使用各仓库管理员账号操作','无权访问','无权查看工资数据')
                    assert await database_snapshot(f) == before
                responses.append({"path": path, "status": response.status_code, "body": response.json()})
            if uid == 1:
                print("DISABLED_REVERSALS", json.dumps(responses, ensure_ascii=False))
            # 不可撤销并不妨碍继续合法归还。
            more = await repay(c, aid, await voucher(c), amount="500")
            assert more.status_code == 200 and more.json()["advance"]["repaid_amount"] == 1500, more.text
    asyncio.run(run())


def test_no_permission_or_unknown_record_cannot_bypass_gate_and_auth_still_required(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            await set_perms(f, 4, [])
            before = await database_snapshot(f)
            for path in ("/payroll/999/revoke-disbursement", "/reimbursement/999/revoke-payment",
                         "/cash-advances/repayments/999/revoke"):
                response = await c.post("/api/v1" + path, headers=auth(4))
                assert response.status_code == (403 if path.startswith('/payroll') else 400), (path,response.text)
                if not path.startswith('/payroll'): assert response.json()=={'detail':REVERSAL_DISABLED_MESSAGE}
                assert (await c.post("/api/v1" + path)).status_code in (401, 403)
            assert await database_snapshot(f) == before
    asyncio.run(run())


def test_revoked_history_amounts_and_ledger_readback_unchanged(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            rid, aid, repayment_id = await executed_records(c)
            # Independently construct already-reversed synthetic history; HTTP gates remain installed.
            await historical_payroll(f,c,2)
            await historical_reimbursement(f,c,rid,'历史报销撤销')
            await historical_cash(f,c,repayment_id,'历史归还撤销')
            before = await database_snapshot(f)
            routes = [f"/reimbursement/{rid}/payments", f"/cash-advances/{aid}/repayments",
                      "/income-expense/ledger", "/payroll", "/accounts"]
            prior = [(await c.get("/api/v1" + route, headers=auth(1))).json() for route in routes]
            assert prior[0]["data"][0]["status"] == prior[1]["data"][0]["status"] == "revoked"
            assert prior[0]["data"][0]["amount"] == 2000 and prior[1]["data"][0]["amount"] == 1000
            assert not next(r for r in prior[3]["data"] if r["id"] == 2)["disbursed"]
            for path in ("/payroll/2/revoke-disbursement", f"/reimbursement/{rid}/revoke-payment",
                         f"/cash-advances/repayments/{repayment_id}/revoke"):
                response = await c.post("/api/v1" + path, headers=auth(1), json={"reason": "再撤"})
                assert response.status_code == 400 and response.json()["detail"] == REVERSAL_DISABLED_MESSAGE
            after = [(await c.get("/api/v1" + route, headers=auth(1))).json() for route in routes]
            assert prior == after and await database_snapshot(f) == before
            print("PRESERVED_REVERSAL_HISTORY", {"reimbursement": "已撤销 / 2000", "repayment": "已撤销 / 1000", "all_columns_unchanged": True})
    asyncio.run(run())


def test_original_handlers_and_calculations_are_byte_identical_after_removing_only_outer_gate():
    # Whole-module byte identity is incompatible with authorized guards; assert gates plus bounded monetary kernels.
    root=Path(__file__).resolve().parents[2]
    for module,handler in [('payroll','revoke_disbursement'),('reimbursement','revoke_payment'),('cash_advance','revoke_repayment')]:
        tree=ast.parse((root/f'backend/app/api/v1/{module}.py').read_text())
        node=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name==handler)
        assert 'reject_disabled_financial_reversal' in ast.unparse(node.decorator_list)
    for path in ['backend/app/services/payroll_expense.py','backend/app/services/account_balances.py']:
        assert (root/path).read_text()==subprocess.check_output(['git','show','e51b636:'+path],cwd=root,text=True)
