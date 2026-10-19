"""在真实 PostgreSQL 执行与报表相同的成本/资金 SQL，包括泰国跨日边界。"""
import asyncio
from datetime import date
from pathlib import Path
from types import SimpleNamespace
import os
import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable
from app.services import cost_funds_debt as s
from tests.test_round12_migration_postgres import PostgreSQLConnection

pytestmark = pytest.mark.skipif(not os.environ.get("PGLITE_NODE"), reason="Requires embedded PostgreSQL")


def test_actual_postgres_union_types_currency_and_business_day():
    async def run():
        proc = await asyncio.create_subprocess_exec(os.environ["PGLITE_NODE"], str(Path(__file__).with_name("postgres_bridge.cjs")), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        conn = PostgreSQLConnection(proc)
        dialect = postgresql.dialect()
        db = SimpleNamespace(bind=SimpleNamespace(dialect=dialect))
        try:
            for model in (s.ExpenseRecord, s.IncomeExpenseCategory, s.PayrollRecord, s.Reimbursement, s.ExpenseFund,
                s.ExpenseFundItem, s.IncomeRecord, s.ReimbursementPayment, s.CashAdvanceRepayment,
                s.IncomingFlow, s.PayableBill, s.PaymentAccount, s.EmployeeAdvance):
                await conn.execute(str(CreateTable(model.__table__, include_foreign_key_constraints=[]).compile(dialect=dialect)))
            for sql in (
                "INSERT INTO income_expense_categories(id,warehouse_id,type,name,category_group) VALUES(1,1,'expense','报销','operating')",
                "INSERT INTO payment_accounts(id,warehouse_id,account_name,account_type,account_number,currency,opening_balance) VALUES(1,1,'现金','cash','1','THB',10000)",
                "INSERT INTO expense_records(id,warehouse_id,category_id,account_id,amount,currency,expense_date) VALUES(1,1,1,1,2000,'THB','2026-10-19')",
                "INSERT INTO reimbursements(id,warehouse_id,employee_id,submit_date,total_amount,currency,status,funding_source,expense_record_id) VALUES(1,1,1,'2026-10-18',2000,'THB','paid','company_account',1)",
                "INSERT INTO reimbursement_payments(id,reimbursement_id,warehouse_id,amount,currency,funding_source,payment_account_id,previous_status,paid_by_name,paid_at,status) VALUES(1,1,1,2000,'THB','company_account',1,'approved','老板','2026-10-18 18:30:00+00','active')",
                "INSERT INTO expense_funds(id,warehouse_id,employee_id,receive_date,amount,purpose,currency) VALUES(1,1,1,'2026-09-30',1000,'备用金','THB')",
                "INSERT INTO expense_fund_items(id,fund_id,expense_date,category,amount,currency,description,review_status) VALUES(1,1,'2026-10-19','运输费',100,'THB','测试','approved')",
                "INSERT INTO income_records(id,warehouse_id,category_id,account_id,amount,currency,income_date) VALUES(1,1,1,1,300,'THB','2026-10-19')",
            ): await conn.execute(sql)
            cq, fq = s.cost_query(db, [1]), s.flow_query(db, [1])
            def sql(q): return str(q.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))
            start = end = date(2026, 10, 19)
            costs = await conn.execute(sql(select(cq).where(*s.cost_filters(cq, start, end))))
            assert sum(float(r["amount"]) for r in costs) == 2100 and len(costs) == 2
            flows = await conn.execute(sql(select(fq).where(*s.flow_filters(fq, start, end))))
            assert {(r["source"], float(r["amount"]), r["account_id"]) for r in flows} == {("manual", 300, 1), ("reimbursement", 2000, 1)}
            assert await conn.execute(sql(select(fq).where(*s.flow_filters(fq, date(2026, 10, 18), date(2026, 10, 18))))) == []
            assert await conn.execute(sql(select(cq).where(cq.c.warehouse_id == 2))) == []
            print("THREE_BOOKS_PG", {"cost": 2100, "outflow": 2000, "inflow": 300, "thai_business_date": "2026-10-19", "no_duplicate_reimbursement_or_fund_flow": True})
        finally:
            proc.stdin.close(); await proc.wait()
    asyncio.run(run())
