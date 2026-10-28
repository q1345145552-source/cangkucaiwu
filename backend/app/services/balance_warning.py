"""Advisory balance snapshots only; callers keep their existing monetary calculations."""
from decimal import Decimal
from app.core.timezone import thai_now
from app.services.data_history import record_history


def balance_warning(balance, amount, currency, *, source, source_id):
    before, value = Decimal(str(balance)), Decimal(str(amount))
    if value <= 0 or before >= value: return None
    after = before - value
    return {'message': f'当前账户余额不足（可用 {before:,.2f}，本次 {value:,.2f}），确认继续吗',
            'balance_before':float(before),'amount':float(value),'balance_after':float(after),
            'currency':currency,'source':source,'source_id':source_id}


async def record_balance_warning(db, warning, operator, *, module, record_id, warehouse_id, operation_id=None):
    if warning is None: return
    await record_history(db,module=module,record_id=record_id,operator=operator,operation_type='edit',
        before={'balance':warning['balance_before']},
        after={**warning,'operation_id':operation_id,'remark':'余额不足仍然执行','executed_at':thai_now().isoformat()},warehouse_id=warehouse_id)


async def saved_balance_warning(db, *, module, record_id, operation_id=None):
    """Replay the original snapshot; never recompute a past transaction from today's balance."""
    from sqlalchemy import select
    from app.models.data_change_history import DataChangeHistory
    rows=(await db.execute(select(DataChangeHistory).where(DataChangeHistory.module==module,
        DataChangeHistory.record_id==record_id).order_by(DataChangeHistory.id.desc()))).scalars().all()
    for row in rows:
        data=row.after_data or {}
        if data.get('remark')=='余额不足仍然执行' and (operation_id is None or data.get('operation_id')==operation_id):
            return {k:v for k,v in data.items() if k not in ('remark','executed_at','operation_id')}
    return None
