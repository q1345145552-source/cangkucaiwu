"""应付逐笔付款和账户归属；调用方统一提交或回滚。"""
from fastapi import HTTPException
from app.core.timezone import thai_now
from sqlalchemy import select
from app.models import PayablePayment
from app.services.wallet import positive_money, money, lock_account
from app.services.account_balances import current_account_balances
from app.services.data_history import record_history


async def record_payment(db, bill, value, account_id, method, operator, request_key=None):
    if request_key:
        old = (await db.execute(select(PayablePayment).where(PayablePayment.request_key == request_key))).scalar_one_or_none()
        if old:
            if old.bill_id != bill.id or old.warehouse_id != bill.warehouse_id or old.account_id != account_id or money(old.amount) != money(value):
                raise HTTPException(409, '付款请求已使用，请刷新后重试')
            return old
    if bill.status in ('voided', 'paid'): raise HTTPException(400, '已作废或已付清的账单不能付款')
    if bill.need_boss_confirm == 'true': raise HTTPException(400, '该账单存在收货差异，需老板确认后才能付款')
    n = positive_money(value)
    remaining = money(bill.amount) - money(bill.paid_amount)
    if n > remaining: raise HTTPException(400, '付款金额不能超过剩余应付')
    from app.services.purchase_matching import check_payment
    await check_payment(db,bill,n)
    account = await lock_account(db, bill.warehouse_id, account_id, bill.currency or 'THB')
    balance = (await current_account_balances(db, [account]))[account.id]
    if balance < n: raise HTTPException(400, f'公司账户余额不足（可用 {balance:,.2f}）')
    if bill.legacy_paid_amount is None:
        bill.legacy_paid_amount, bill.legacy_paid_at = bill.paid_amount or 0, bill.paid_at
    now = thai_now()
    row = PayablePayment(warehouse_id=bill.warehouse_id, bill_id=bill.id, account_id=account.id,
        amount=n, currency=bill.currency or 'THB', paid_at=now, payment_method=method, operator_id=operator.id, request_key=request_key)
    db.add(row)
    bill.paid_amount = float(money(bill.paid_amount) + n)
    bill.paid_at, bill.payment_method = now, method
    bill.status = 'paid' if money(bill.paid_amount) >= money(bill.amount) else 'partially_paid'
    await db.flush()
    await record_history(db, module='payable', record_id=bill.id, operator=operator,
        operation_type='pay', after={'payment_id': row.id, 'amount': float(n), 'account_id': account.id,
            'currency': row.currency, 'paid_at': now.isoformat()}, warehouse_id=bill.warehouse_id)
    return row
