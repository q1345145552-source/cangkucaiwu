"""Advisory balance snapshots only; callers keep their existing monetary calculations."""
from decimal import Decimal
from app.core.timezone import thai_now
from app.services.data_history import record_history


def balance_warning(balance, amount, currency, *, source, source_id):
    before, value = Decimal(str(balance)), Decimal(str(amount))
    if before >= value: return None
    after = before - value
    return {'message': f'当前账户余额不足（可用 {before:,.2f}，本次 {value:,.2f}），确认继续吗',
            'balance_before':float(before),'amount':float(value),'balance_after':float(after),
            'currency':currency,'source':source,'source_id':source_id}


async def record_balance_warning(db, warning, operator, *, module, record_id, warehouse_id):
    if warning is None: return
    await record_history(db,module=module,record_id=record_id,operator=operator,operation_type='edit',
        before={'balance':warning['balance_before']},
        after={**warning,'remark':'余额不足仍然执行','executed_at':thai_now().isoformat()},warehouse_id=warehouse_id)
