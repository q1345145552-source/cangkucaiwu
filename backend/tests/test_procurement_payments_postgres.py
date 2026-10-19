"""真实 PostgreSQL 验证付款日的泰国月份边界、作废和币种过滤。"""
import asyncio
from datetime import date
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import dialect as pg_dialect
from sqlalchemy.schema import CreateTable

from app.models.payable import PayableBill
from app.models.supplier import PurchaseOrder
from app.services.procurement_payments import procurement_payment_rows
from tests.test_round12_migration_postgres import PostgreSQLConnection

pytestmark = pytest.mark.skipif(not os.environ.get("PGLITE_NODE"), reason="Requires embedded PostgreSQL")


def test_actual_postgres_thai_payment_month_bounds_currency_and_void_filter():
    async def run():
        proc = await asyncio.create_subprocess_exec(os.environ["PGLITE_NODE"], str(Path(__file__).with_name("postgres_bridge.cjs")),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        conn = PostgreSQLConnection(proc)
        dialect = pg_dialect()
        db = SimpleNamespace(bind=SimpleNamespace(dialect=dialect))
        try:
            for model in (PayableBill, PurchaseOrder):
                await conn.execute(str(CreateTable(model.__table__, include_foreign_key_constraints=[]).compile(dialect=dialect)))
            for i, when, paid, cur, status, wid in (
                (1, "2026-09-30 16:59:59+00", 99, "THB", "paid", 1),
                (2, "2026-09-30 17:00:00+00", 100, "THB", "paid", 1),
                (3, "2026-10-31 16:59:59+00", 200, "THB", "paid", 1),
                (4, "2026-10-31 17:00:00+00", 300, "THB", "paid", 1),
                (5, "2026-10-15 00:00:00+00", 400, "THB", "voided", 1),
                (6, "2026-10-15 00:00:00+00", 500, "THB", "paid", 2),
                (7, "2026-10-15 00:00:00+00", 10.05, "CNY", "partially_paid", 1),
                (8, "2026-10-15 00:00:00+00", 0, "THB", "pending", 1),
            ):
                await conn.execute(f"INSERT INTO payable_bills(id,warehouse_id,supplier_id,bill_number,bill_date,due_date,amount,paid_amount,paid_at,currency,status) VALUES({i},{wid},1,'PG-{i}','2026-09-01','2026-11-01',1000,{paid},'{when}','{cur}','{status}')")
            rows = procurement_payment_rows(db, [1])
            query = select(rows.c.currency, func.sum(rows.c.amount).label("amount"), func.count().label("count")).where(
                rows.c.payment_date >= date(2026, 10, 1), rows.c.payment_date <= date(2026, 10, 31),
            ).group_by(rows.c.currency).order_by(rows.c.currency)
            result = await conn.execute(str(query.compile(dialect=dialect, compile_kwargs={"literal_binds": True})))
            assert [{**r, "amount": float(r["amount"])} for r in result] == [
                {"currency": "CNY", "amount": 10.05, "count": 1}, {"currency": "THB", "amount": 300, "count": 2}]
        finally:
            proc.stdin.close()
            await proc.wait()
    asyncio.run(run())
