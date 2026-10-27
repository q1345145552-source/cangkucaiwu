"""Stable manual-operation IDs; all money remains in the existing income/expense tables."""
import hashlib
import json
import re
from decimal import Decimal,InvalidOperation

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.models.income_expense import IncomeRecord,ExpenseRecord
from app.services.wallet import lock_account,money
from app.services.account_balances import current_account_balances


def values_fingerprint(values):
    try:
        n=Decimal(str(values['amount']))
        if not n.is_finite() or n==0 or abs(n)>=Decimal('1000000000000') or n!=n.quantize(Decimal('0.01')):raise ValueError
    except (ValueError,InvalidOperation):raise HTTPException(400,'金额必须非零且最多两位小数')
    canonical={k:v for k,v in values.items() if k not in ('voucher','confirmed_by','approved_by')}
    canonical['amount']=str(money(values['amount']))
    return hashlib.sha256(json.dumps(canonical,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()


async def existing(db,model,warehouse_id,key,fingerprint):
    if not key:return None
    row=(await db.execute(select(model).where(model.warehouse_id==warehouse_id,model.request_key==key))).scalar_one_or_none()
    if row and row.request_fingerprint!=fingerprint:
        raise HTTPException(409,'本次收付已保存，内容不一致；请核对原记录，另一笔请重新录入')
    return row


async def lookup(db,kind,values,key):
    if key is not None and not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',key):raise HTTPException(400,'收付请求编号无效')
    return await existing(db,IncomeRecord if kind=='income' else ExpenseRecord,values['warehouse_id'],key,values_fingerprint(values))


async def prepare(db,kind,values,key,*,account=None):
    if key is not None and not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',key):raise HTTPException(400,'收付请求编号无效')
    model=IncomeRecord if kind=='income' else ExpenseRecord
    fingerprint=values_fingerprint(values)
    row=await existing(db,model,values['warehouse_id'],key,fingerprint)
    if row:return row,fingerprint,None
    if account is None:account=await lock_account(db,values['warehouse_id'],values['account_id'],values['currency'])
    if account.account_type=='cash' and not key:
        raise HTTPException(400,'现金收付款必须提供请求编号，请刷新页面后重试')
    # Account locks serialize money across receipts, payments and internal transfers.
    row=await existing(db,model,values['warehouse_id'],key,fingerprint)
    if row:return row,fingerprint,None
    warning=None
    if kind=='expense' and money(values['amount'])>0:
        balance=(await current_account_balances(db,[account]))[account.id]
        from app.services.balance_warning import balance_warning
        warning=balance_warning(balance,money(values['amount']),values['currency'],source='company_account',source_id=account.id)
    return None,fingerprint,warning


async def insert_once(db,kind,values,key,fingerprint):
    model=IncomeRecord if kind=='income' else ExpenseRecord
    if not key:
        row=model(**values);db.add(row);await db.flush();return row,True
    insert=sqlite_insert if db.bind.dialect.name=='sqlite' else pg_insert
    rid=(await db.execute(insert(model).values(**values,request_key=key,request_fingerprint=fingerprint)
        .on_conflict_do_nothing(index_elements=['warehouse_id','request_key']).returning(model.id))).scalar_one_or_none()
    if rid is None:return await existing(db,model,values['warehouse_id'],key,fingerprint),False
    return await db.get(model,rid),True
