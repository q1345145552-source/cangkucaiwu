"""采购实付：真实请求、跨月、作废、多币种、只读和旧盈亏保护。"""
import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime
import json

import pytest
from sqlalchemy import event, select

from app.database import Base
from app.models import IncomingFlow, PaymentAccount, PayablePayment
from app.models.income_expense import ExpenseRecord, IncomeExpenseCategory
from app.models.payable import PayableBill
from app.models.supplier import PurchaseOrder, Supplier
from app.services.procurement_payments import procurement_payment_rows, procurement_payment_totals
import app.api.v1.dashboard as dashboard
from tests.test_round2_permissions import auth, set_perms
from tests.test_round3_permissions import hr_environment
from tests.test_incoming_operations import URL, environment as pg_environment
from app.core.timezone import THAI_TZ

RANGE = {"start_date": "2026-10-01", "end_date": "2026-10-31"}


@asynccontextmanager
async def environment(tmp_path, monkeypatch):
    async with hr_environment(tmp_path, monkeypatch) as (engine, f, c):
        @event.listens_for(engine.sync_engine, "connect")
        def functions(conn, _):
            conn.create_function("to_char", 2, lambda value, fmt: str(value)[:7] if value else None)
        await engine.dispose()
        monkeypatch.setattr(dashboard, "thai_today", lambda: date(2026, 10, 19))
        await set_perms(f, 3, ["报表中心"])
        await set_perms(f, 4, ["报表中心"])
        async with f() as db:
            db.add_all([Supplier(id=i, warehouse_id=i, name=f"隔离供应商{i}") for i in (1, 2)])
            db.add_all([
                IncomeExpenseCategory(id=80, warehouse_id=1, type="expense", category_group="operating", name="采购"),
                IncomeExpenseCategory(id=81, warehouse_id=1, type="expense", category_group="operating", name="其他费用"),
            ])
            await db.flush()
            db.add(ExpenseRecord(warehouse_id=1, category_id=80, account_id=1, amount=250, currency="THB",
                expense_date=datetime(2026, 10, 8), remark="原独立手工采购，未与应付单关联"))
            db.add(ExpenseRecord(warehouse_id=1, category_id=81, account_id=1, amount=750, currency="THB",
                expense_date=datetime(2026, 10, 8), remark="原运营支出"))
            db.add_all([
                PayableBill(id=1, warehouse_id=1, supplier_id=1, bill_number="TEST-OCT-UNPAID",
                    bill_date=datetime(2026, 10, 4), due_date=datetime(2026, 11, 1), amount=1000, paid_amount=0, status="pending", currency="THB"),
                PayableBill(id=2, warehouse_id=1, supplier_id=1, bill_number="TEST-SEP-PAID-OCT",
                    bill_date=datetime(2026, 9, 20), due_date=datetime(2026, 11, 1), amount=3000, paid_amount=3000,
                    paid_at=datetime(2026, 10, 10, 12), status="paid", currency="THB"),
            ])
            await db.commit()
        yield engine, f, c


async def snapshot(factory):
    async with factory() as db:
        return {table.name: [tuple(row) for row in (await db.execute(select(table).order_by(*table.primary_key.columns))).all()]
            for table in Base.metadata.sorted_tables}


async def read_views(c, uid=1):
    cockpit = await c.get("/api/v1/dashboard/cockpit", headers=auth(uid))
    report = await c.get("/api/v1/reports/cost-funds-debt", headers=auth(uid), params=RANGE)
    assert cockpit.status_code == report.status_code == 200, (cockpit.text, report.text)
    return cockpit.json(), report.json()


def category(report, name, currency="THB"):
    block = next(b for b in report["currencies"] if b["currency"] == currency)
    return next((r for r in block["costs"]["data"] if r["name"] == name), {"count": 0, "amount": 0})


def nonzero(rows):
    """新口径按仓库币种补零显示；0 值币种不代表发生额，比较时只取非零项。"""
    return {row["currency"]: row["amount"] for row in rows if row["amount"]}


@pytest.mark.parametrize("uid", [1, 3, 4])
def test_unpaid_excluded_cross_month_paid_included_shared_report_and_other_dashboard_data_unchanged(tmp_path, monkeypatch, uid):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            before = await snapshot(f)
            now, report = await read_views(c, uid)
            # 采购只按实际付款：本月未付 1000 单不计，上月开单本月付款 3000 计入。
            assert nonzero(now["finance"]["procurement"]["expense"]) == {"THB": 3000}
            assert nonzero(now["finance"]["month"]["procurement_expense"]) == {"THB": 3000}
            assert category(report, "采购") == {"name": "采购", "count": 1, "amount": 3000}
            assert category(report, "手工采购") == {"name": "手工采购", "count": 1, "amount": 250}
            # 采购口径之外的钱包数字逐项锁定为具体金额，不再与旧版源码输出逐字段对比。
            assert nonzero(now["finance"]["month"]["operating_expense"]) == {"THB": 1000}
            # 收入只认实际到账：隔离库里只有一条 100 的充值申报，不计实收，所以收入为 0。
            assert nonzero(now["finance"]["month"]["income"]) == {}
            assert nonzero(now["finance"]["month"]["expense"]) == {"THB": 4000}
            assert nonzero(now["finance"]["month"]["profit"]) == {"THB": -4000}
            assert nonzero(now["finance"]["balances"]["payment_accounts"]) == {"THB": -1000.0}
            assert nonzero(now["finance"]["receivable_payable"]["payable"]) == {"THB": 1000.0}
            assert nonzero(now["finance"]["receivable_payable"]["receivable"]) == {}
            trends = (await c.get("/api/v1/dashboard/trends", headers=auth(uid))).json()
            assert sum(r["amount"] for r in trends["procurement_suppliers"]["THB"]) == 3000
            costs = (await c.get("/api/v1/reports/cost-funds-debt/costs", headers=auth(uid),
                params={**RANGE, "cost_category": "采购"})).json()
            assert costs["total"] == 1 and costs["totals_by_currency"]["THB"] == 3000
            row = costs["data"][0]
            assert row["source"] == "payable" and row["is_read_only"] is True
            # 历史累计付款行用负数 id 与逐笔付款 id 区分（wallet.procurement_rows 里取 -bill_id），
            # 金额和日期仍是那笔真实付款：泰铢 3000 在 2026-10-10。
            assert row["source_id"] == -2 and row["id"] == "payable--2"
            assert float(row["amount"]) == 3000 and row["date"] == "2026-10-10"
            assert row["ref_no"] == "PB-2" and row["remark"] == "TEST-SEP-PAID-OCT"
            async with f() as db:
                assert (await db.get(PayableBill, 1)).paid_amount == 0
                assert len((await db.execute(select(ExpenseRecord))).scalars().all()) == 2  # 只读投影，不自动补支出。
            assert await snapshot(f) == before
            if uid == 1:
                print("PROCUREMENT_MONTH", json.dumps({"unpaid_bill": "TEST-OCT-UNPAID", "unpaid_amount": 1000,
                    "cross_month_bill": "TEST-SEP-PAID-OCT", "paid_in_october": 3000, "dashboard_procurement": 3000,
                    "report_purchase": 3000, "manual_purchase_preserved": 250,
                    "operating_expense": 1000, "income": 0, "expense": 4000, "profit": -4000,
                    "payment_accounts_balance": -1000.0, "payable_open": 1000.0, "database_unchanged": True}, ensure_ascii=False))
    asyncio.run(run())


def test_partial_payment_not_bill_total_and_date_currency_warehouse_void_guards(tmp_path, monkeypatch):
    async def run():
        async with environment(tmp_path, monkeypatch) as (_, f, c):
            async with f() as db:
                cases = [
                    (3, 1, "PARTIAL", 9000, 400.25, datetime(2026, 10, 12), "partially_paid", "THB"),
                    (4, 1, "VOIDED", 700, 700, datetime(2026, 10, 12), "voided", "THB"),
                    (5, 1, "PRIOR-PAID", 800, 800, datetime(2026, 9, 30), "paid", "THB"),
                    (6, 1, "NEXT-PAID", 900, 900, datetime(2026, 11, 1), "paid", "THB"),
                    (7, 1, "UNKNOWN-DATE", 600, 600, None, "paid", "THB"),
                    (8, 2, "OTHER-WH", 10000, 10000, datetime(2026, 10, 12), "paid", "THB"),
                    (9, 1, "CNY", 200, 200, datetime(2026, 10, 1), "paid", "CNY"),
                    (10, 1, "MONTH-END", 50, 50, datetime(2026, 10, 31, 23, 59, 59), "paid", "THB"),
                ]
                for bid, wid, number, total, paid, when, status, cur in cases:
                    db.add(PayableBill(id=bid, warehouse_id=wid, supplier_id=wid, bill_number=number,
                        bill_date=datetime(2026, 10, 1), due_date=datetime(2026, 11, 1), amount=total,
                        paid_amount=paid, paid_at=when, status=status, currency=cur))
                db.add(PurchaseOrder(id=1, warehouse_id=1, supplier_id=1, order_number="DRAFT-PO", status="draft", total_amount=500, items=[]))
                await db.flush()
                db.add(PayableBill(id=11, warehouse_id=1, supplier_id=1, bill_number="DRAFT-PO-BILL", purchase_order_id=1,
                    bill_date=datetime(2026, 10, 1), due_date=datetime(2026, 11, 1), amount=500, paid_amount=500,
                    paid_at=datetime(2026, 10, 12), status="paid", currency="THB"))
                await db.commit()
                totals = dict(await procurement_payment_totals(db, [1], date(2026, 10, 1), date(2026, 10, 31)))
                # 实付口径：已付出去的钱即使单据作废、采购单仍是草稿也保留，合计
                # 3000.00（种子跨月单）+ 400.25（部分付款）+ 700.00（作废但已付）
                # + 50.00（月末最后一秒）+ 500.00（草稿采购单已付）= 4650.25。
                assert totals == {"THB": 4650.25, "CNY": 200}
            before = await snapshot(f)
            cockpit, report = await read_views(c)
            assert {r["currency"]: r["amount"] for r in cockpit["finance"]["procurement"]["expense"]} == {"THB": 4650.25, "CNY": 200}
            assert category(report, "采购")["amount"] == 4650.25 and category(report, "采购", "CNY")["amount"] == 200
            assert await snapshot(f) == before
    asyncio.run(run())


@pytest.mark.skipif(not URL, reason="需要显式配置的隔离 PostgreSQL")
def test_money_basis_numbers_on_real_postgres(tmp_path, monkeypatch):
    """真实 PostgreSQL 上以具体数字验证收入、支出、余额、逐笔付款与防重。

    取代原先对 6f9243b/7dbf327 的源码逐字快照：本轮钱口径统一按批准改动重写了
    income_expense.py、account_balances.py、payable.py、payroll.py，
    旧快照已不能作为正确性证明，改为断言具体金额。
    """
    async def run():
        async with pg_environment(tmp_path, monkeypatch) as (_, f, c):
            import app.services.payable_payment as payable_payment
            monkeypatch.setattr(payable_payment, "thai_now", lambda: datetime(2026, 10, 20, 12, tzinfo=THAI_TZ))
            async with f() as db:
                thb = await db.get(PaymentAccount, 1)
                thb.opening_balance, thb.opening_balance_date = 10000, date(2026, 9, 1)
                db.add(PaymentAccount(id=30, warehouse_id=1, account_name="人民币现金", account_type="cash",
                    account_number="-", opening_balance=0, opening_balance_date=date(2026, 9, 1), currency="CNY"))
                db.add(Supplier(id=1, warehouse_id=1, name="隔离供应商1"))
                db.add(IncomeExpenseCategory(id=90, warehouse_id=1, type="expense",
                    category_group="operating", name="运营支出"))
                await db.flush()
                db.add(IncomingFlow(warehouse_id=1, received_date=datetime(2026, 9, 10), amount=500,
                    currency="THB", payer_name="到账客户", account_id=1, entrant_id=1, request_key="pg-income-thb"))
                db.add(IncomingFlow(warehouse_id=1, received_date=datetime(2026, 9, 11), amount=100,
                    currency="CNY", payer_name="到账客户", account_id=30, entrant_id=1, request_key="pg-income-cny"))
                db.add(ExpenseRecord(warehouse_id=1, category_id=90, account_id=1, amount=200, currency="THB",
                    expense_date=datetime(2026, 9, 15), remark="手工运营支出", request_key="pg-expense-1"))
                db.add(PayableBill(id=40, warehouse_id=1, supplier_id=1, bill_number="PG-SEP-UNPAID",
                    bill_date=datetime(2026, 9, 20), due_date=datetime(2026, 11, 1), amount=1000,
                    paid_amount=0, status="pending", currency="THB"))
                await db.commit()
            paid = await c.put("/api/v1/payable/40/pay", headers=auth(1),
                params={"paid_amount": 300, "account_id": 1, "payment_method": "银行转账", "request_key": "pg-pay-A"})
            assert paid.status_code == 200, paid.text
            assert paid.json()["amount"] == 300
            replay = await c.put("/api/v1/payable/40/pay", headers=auth(1),
                params={"paid_amount": 300, "account_id": 1, "payment_method": "银行转账", "request_key": "pg-pay-A"})
            assert replay.json()["payment_id"] == paid.json()["payment_id"]
            conflict = await c.put("/api/v1/payable/40/pay", headers=auth(1),
                params={"paid_amount": 200, "account_id": 1, "payment_method": "银行转账", "request_key": "pg-pay-A"})
            assert conflict.status_code == 409
            september = (await c.get("/api/v1/reports/income-expense", headers=auth(1),
                params={"start_date": "2026-09-01", "end_date": "2026-09-30"})).json()
            october = (await c.get("/api/v1/reports/income-expense", headers=auth(1),
                params={"start_date": "2026-10-01", "end_date": "2026-10-31"})).json()
            # 收入只认到账：9 月泰铢 500、人民币 100，10 月 0。
            assert september["income_by_currency"] == {"THB": 500.0, "CNY": 100.0}
            assert october["income_by_currency"] == {}
            # 支出按实付：9 月只有手工 200；9 月开单、10 月付款的 300 归 10 月。
            assert september["expense_by_currency"] == {"THB": 200.0}
            assert october["expense_by_currency"] == {"THB": 300.0}
            accounts = {a["id"]: a for a in (await c.get("/api/v1/accounts", headers=auth(1))).json()["data"]}
            # 余额 = 期初 + 实收 - 实付；泰铢 10000 + 500 - 200 - 300，人民币 0 + 100 - 0。
            assert accounts[1]["current_balance"] == 10000.0
            assert accounts[30]["current_balance"] == 100.0
            ledger = (await c.get("/api/v1/income-expense/ledger", headers=auth(1),
                params={"start_date": "2026-10-01", "end_date": "2026-10-31", "source": "payable"})).json()
            # 逐笔付款只计一次：重放同请求号不新增，改金额被拒。
            assert ledger["total"] == 1
            assert [(r["source"], float(r["amount"]), r["currency"]) for r in ledger["data"]] == [("payable", 300.0, "THB")]
            async with f() as db:
                payments = (await db.execute(select(PayablePayment).order_by(PayablePayment.id))).scalars().all()
                assert [(p.bill_id, float(p.amount), p.account_id) for p in payments] == [(40, 300.0, 1)]
                bill = await db.get(PayableBill, 40)
                assert float(bill.paid_amount) == 300 and float(bill.legacy_paid_amount or 0) == 0
            print("MONEY_BASIS_POSTGRES", json.dumps({"september_income": september["income_by_currency"],
                "september_expense": september["expense_by_currency"], "october_income": october["income_by_currency"],
                "october_expense": october["expense_by_currency"], "thb_balance": accounts[1]["current_balance"],
                "cny_balance": accounts[30]["current_balance"], "payable_ledger_count": ledger["total"],
                "payable_ledger_amount": [float(r["amount"]) for r in ledger["data"]], "payment_rows": 1,
                "replay_same_key_payment_id": replay.json()["payment_id"],
                "changed_amount_same_key": conflict.status_code}, ensure_ascii=False))
    asyncio.run(run())

