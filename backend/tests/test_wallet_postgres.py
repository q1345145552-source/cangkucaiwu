"""真实 PostgreSQL：启动迁移幂等/保存点、泰国月界、逐笔付款与统一钱包查询。"""
import asyncio
import os
from pathlib import Path
from types import SimpleNamespace
from datetime import date
import pytest
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.schema import CreateTable
from app.database import Base
from app.models.wallet import PayablePayment, AccountTransfer
from app.services.wallet import flow_query, procurement_rows
from app.services.cost_funds_debt import cost_query
from scripts.seed import _migrate_wallet_basis
from tests.test_round12_migration_postgres import PostgreSQLConnection

pytestmark = pytest.mark.skipif(not os.environ.get('PGLITE_NODE'), reason='Requires embedded PostgreSQL')

@pytest.mark.parametrize('fail', [False, True])
def test_wallet_additive_migration_and_postgres_month_boundary(fail):
    async def run():
        process = await asyncio.create_subprocess_exec(os.environ['PGLITE_NODE'], str(Path(__file__).with_name('postgres_bridge.cjs')),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
        conn, pg = PostgreSQLConnection(process), dialect()
        try:
            for table in Base.metadata.sorted_tables:
                if table.name not in ('payable_payments', 'account_transfers'):
                    await conn.execute(CreateTable(table, include_foreign_key_constraints=[]).compile(dialect=pg))
            for table, columns in {'payment_accounts':['opening_balance_date'], 'payable_bills':['legacy_paid_amount','legacy_paid_at'],
                'incoming_flows':['account_id'], 'credit_repayments':['incoming_flow_id'],
                'expense_approvals':['payment_account_id','expense_record_id']}.items():
                for column in columns: await conn.execute(f'ALTER TABLE {table} DROP COLUMN {column}')
            await conn.execute("INSERT INTO warehouses(id,name,code) VALUES(1,'测试仓','TEST')")
            await conn.execute("INSERT INTO users(id,username,password_hash,display_name,role,warehouse_id) VALUES(1,'admin','unused','测试老板','warehouse_admin',1)")
            await conn.execute("INSERT INTO payment_accounts(id,warehouse_id,account_name,account_type,account_number,opening_balance,currency) VALUES(1,1,'现金','cash','-',10000,'THB')")
            await conn.execute("INSERT INTO payable_bills(id,warehouse_id,supplier_id,bill_number,bill_date,due_date,amount,paid_amount,paid_at,currency,status) VALUES(1,1,1,'OLD','2026-09-01','2026-10-01',1000,300,'2026-09-30 16:00:00+00','THB','voided')")
            before = await conn.execute('SELECT id,amount,paid_amount,paid_at,status FROM payable_bills')
            await conn.execute('BEGIN')
            if fail:
                original = conn.execute
                async def broken(statement):
                    return await original('SELECT * FROM intentionally_missing' if str(statement).startswith('ALTER TABLE incoming_flows') else statement)
                conn.execute = broken
                with pytest.raises(RuntimeError): await _migrate_wallet_basis(conn)
                conn.execute = original
                assert await conn.execute('SELECT 1 AS still_usable') == [{'still_usable': 1}]
            await _migrate_wallet_basis(conn)
            await _migrate_wallet_basis(conn)
            await conn.execute('COMMIT')
            assert await conn.execute('SELECT id,amount,paid_amount,paid_at,status FROM payable_bills') == before
            anchor = await conn.execute('SELECT opening_balance,opening_balance_date FROM payment_accounts')
            assert anchor[0]['opening_balance'] == 10000 and anchor[0]['opening_balance_date']
            await conn.execute('BEGIN')
            await conn.execute("UPDATE payment_accounts SET opening_balance_date='2026-08-01'")
            await _migrate_wallet_basis(conn)
            await conn.execute('COMMIT')
            assert (await conn.execute('SELECT opening_balance_date::text AS day FROM payment_accounts'))[0]['day'] == '2026-08-01'
            assert (await conn.execute('SELECT count(*)::int AS n FROM expense_records'))[0]['n'] == 0
            # 冻结旧累计300在9月；10月新付100、200不挪动旧值，作废也不抹掉实付。
            await conn.execute("UPDATE payable_bills SET legacy_paid_amount=300,legacy_paid_at=paid_at,paid_amount=600,paid_at='2026-10-31 17:00:00+00'")
            for when, value in [('2026-09-30 17:00:00+00',100), ('2026-10-31 16:59:59+00',200), ('2026-10-31 17:00:00+00',50)]:
                await conn.execute(f"INSERT INTO payable_payments(warehouse_id,bill_id,account_id,amount,currency,paid_at,operator_id) VALUES(1,1,1,{value},'THB','{when}',1)")
            db = SimpleNamespace(bind=SimpleNamespace(dialect=pg))
            rows = procurement_rows(db, [1])
            query = select(rows.c.payment_date, rows.c.amount).order_by(rows.c.payment_date)
            values = await conn.execute(query.compile(dialect=pg, compile_kwargs={'literal_binds':True}))
            assert [(r['payment_date'][:10], float(r['amount'])) for r in values] == [
                ('2026-09-30',300), ('2026-10-01',100), ('2026-10-31',200), ('2026-11-01',50)]
            q = flow_query(db, [1])
            query = select(func.sum(q.c.amount).label('amount')).where(q.c.date >= date(2026,10,1),
                q.c.date <= date(2026,10,31), q.c.type == 'expense', q.c.status == 'active', q.c.is_internal_transfer.is_(False))
            assert float((await conn.execute(query.compile(dialect=pg,compile_kwargs={'literal_binds':True})))[0]['amount']) == 300
            costs = cost_query(db, [1])
            query = select(func.sum(costs.c.amount).label('amount')).where(costs.c.date >= date(2026,10,1), costs.c.date <= date(2026,10,31))
            assert float((await conn.execute(query.compile(dialect=pg,compile_kwargs={'literal_binds':True})))[0]['amount']) == 300
        finally:
            process.stdin.close(); await process.wait()
    asyncio.run(run())
