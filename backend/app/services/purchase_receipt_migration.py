"""Nullable metadata + a new empty event table; no fabricated historical receipts."""
from sqlalchemy import text, inspect
from app.models.purchase_receipt import PurchaseReceiptEvent


async def migrate_purchase_receipts(conn):
    for table, fields in {'purchase_orders': {'receipt_baseline': 'JSON'},
            'payable_bills': {'matching_kind': 'VARCHAR(20)', 'match_lines': 'JSON', 'match_review': 'JSON'}}.items():
        for name, kind in fields.items():
            async with conn.begin_nested():
                await conn.execute(text(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {kind}'))
    async with conn.begin_nested():
        await conn.run_sync(lambda c: PurchaseReceiptEvent.__table__.create(c, checkfirst=True))
    await ensure_receipt_guard(conn)
    print('分批收货迁移 READY：4个可空字段和空批次表；未生成历史事件或重算旧账')


async def ensure_receipt_guard(conn):
    from fastapi import HTTPException
    def check(c):
        i = inspect(c)
        if not i.has_table('purchase_receipt_events'):
            return False
        constraints = i.get_unique_constraints('purchase_receipt_events')
        return any(v['name'] == 'uq_purchase_receipt_operation' and v['column_names'] ==
            ['warehouse_id', 'purchase_order_id', 'request_key'] for v in constraints)
    if not await conn.run_sync(check):
        raise HTTPException(503, '分批收货唯一约束未就绪，已停止新增，请管理员检查迁移')
