"""复用账期发货事实；登记、编辑及作废不触碰公司钱包。"""
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.core.timezone import thai_now
from app.models.credit import CreditCustomer, CreditShipment, CreditRepayment
from app.models.customer import Customer
from app.services.data_history import record_history
from app.services.warehouse_summary import warehouse_scope


class ShipmentData(BaseModel):
    model_config = ConfigDict(extra='forbid')
    ship_date: date
    order_count: int = Field(gt=0, le=10000000, strict=True)
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: Literal['THB', 'CNY']
    order_no: str | None = Field(default=None, max_length=100)
    remark: str | None = Field(default=None, max_length=500)


class ShipmentCreate(ShipmentData):
    request_key: str = Field(min_length=8, max_length=64, pattern=r'^[A-Za-z0-9_-]+$')


class ShipmentVoid(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


def active_shipment():
    return func.coalesce(CreditShipment.status, 'active') == 'active'


def currency_of(credit, customer):
    return credit.currency or customer.default_currency or 'THB'


def shipment_dict(row, credit, customer):
    return {'id': row.id, 'credit_customer_id': credit.id, 'customer_id': customer.id,
        'customer_name': customer.company_name, 'warehouse_id': credit.warehouse_id,
        'ship_date': row.ship_date.date().isoformat(), 'order_no': row.order_no,
        'order_count': row.order_count, 'amount': row.amount,
        'currency': row.currency or currency_of(credit, customer), 'remark': row.remark,
        'status': row.status or 'active', 'entrant_id': row.entrant_id,
        'created_at': row.created_at.isoformat() if row.created_at else None,
        'updated_at': row.updated_at.isoformat() if row.updated_at else None,
        'voided_by': row.voided_by, 'voided_at': row.voided_at.isoformat() if row.voided_at else None,
        'void_reason': row.void_reason}


async def scoped_credit(db, user, header, credit_id, *, lock=False):
    warehouses = await warehouse_scope(db, user, header)
    if not warehouses: raise HTTPException(403, '无权访问所选仓库')
    query = select(CreditCustomer).where(CreditCustomer.id == credit_id)
    if lock: query = query.with_for_update().execution_options(populate_existing=True)
    credit = (await db.execute(query)).scalar_one_or_none()
    if not credit: raise HTTPException(404, '账期客户不存在')
    if credit.warehouse_id not in {w.id for w in warehouses}:
        raise HTTPException(403, '只能操作当前仓库的账期客户')
    customer = await db.get(Customer, credit.customer_id)
    if not customer or customer.warehouse_id != credit.warehouse_id:
        raise HTTPException(409, '账期客户与客户档案仓库不一致，请先核对')
    return credit, customer


async def refresh_debt(db, credit):
    from app.api.v1.credit import _compute_debt_and_overdue
    await db.flush()
    credit.current_debt, credit.overdue_days = await _compute_debt_and_overdue(db, credit.id)
    await db.flush()
    return {'current_debt': credit.current_debt, 'overdue_days': credit.overdue_days}


def values_for(req):
    return {'ship_date': datetime.combine(req.ship_date, datetime.min.time()), 'amount': float(req.amount),
        'order_count': req.order_count, 'currency': req.currency, 'order_no': req.order_no or None,
        'remark': req.remark or None}


async def validate_new_value(db, credit, customer, values, old_amount=0):
    from app.api.v1.credit import _compute_debt_and_overdue
    from app.services.flow_rules import exceeds_credit_limit
    if credit.status != 'active': raise HTTPException(400, '账期账户未启用，不能登记或修改发货')
    if values['currency'] != currency_of(credit, customer):
        raise HTTPException(400, '发货币种必须与账期账户币种一致')
    incompatible = (await db.execute(select(CreditShipment.id).where(
        CreditShipment.credit_customer_id == credit.id, CreditShipment.currency.is_not(None),
        CreditShipment.currency != values['currency']).limit(1))).first()
    if incompatible: raise HTTPException(409, '已有发货币种不一致，请先核对账期币种')
    debt, _ = await _compute_debt_and_overdue(db, credit.id)
    if exceeds_credit_limit(max(debt - old_amount, 0), values['amount'], credit.credit_limit):
        raise HTTPException(400, '超出授信额度，请先核对账期额度')


async def create_once(db, credit, customer, req, user):
    values = values_for(req)
    canonical = {**values, 'ship_date': req.ship_date.isoformat(), 'amount': str(req.amount.quantize(Decimal('.01'))), 'credit_id': credit.id}
    fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    async def existing():
        return (await db.execute(select(CreditShipment).where(CreditShipment.request_key == req.request_key))).scalar_one_or_none()
    def replay(row):
        if row.credit_customer_id != credit.id or row.request_fingerprint != fingerprint:
            raise HTTPException(409, '该发货请求已保存且内容不一致，请查看原记录；新发货请重新登记')
        return row, False
    old = await existing()
    if old: return replay(old)
    await validate_new_value(db, credit, customer, values)
    insert = sqlite_insert if db.bind.dialect.name == 'sqlite' else pg_insert
    sid = (await db.execute(insert(CreditShipment).values(**values, credit_customer_id=credit.id,
        entrant_id=user.id, status='active', request_key=req.request_key, request_fingerprint=fingerprint)
        .on_conflict_do_nothing(index_elements=['request_key']).returning(CreditShipment.id))).scalar_one_or_none()
    if sid is None: return replay(await existing())
    if credit.currency is None: credit.currency = values['currency']
    row = await db.get(CreditShipment, sid)
    await record_history(db, module='credit', record_id=sid, operator=user, operation_type='create',
        after={'shipment': shipment_dict(row, credit, customer)}, warehouse_id=credit.warehouse_id)
    return row, True


async def editable_shipment(db, credit, shipment_id):
    row = (await db.execute(select(CreditShipment).where(CreditShipment.id == shipment_id,
        CreditShipment.credit_customer_id == credit.id).with_for_update())).scalar_one_or_none()
    if row is None: raise HTTPException(404, '发货记录不存在或不属于该账期客户')
    if row.status == 'voided': raise HTTPException(400, '该发货记录已作废')
    # 现有回款仅关联账期账户，没有逐票核销分配；不猜哪一票已核销。
    if (await db.execute(select(CreditRepayment.id).where(CreditRepayment.credit_customer_id == credit.id).limit(1))).first():
        raise HTTPException(409, '该账期已有回款记录，不能修改或作废发货，请先核对账务')
    return row


async def edit_shipment(db, credit, customer, row, req, user):
    values = values_for(req)
    await validate_new_value(db, credit, customer, values, row.amount)
    before = shipment_dict(row, credit, customer)
    for key, value in values.items(): setattr(row, key, value)
    row.updated_at = thai_now()
    if credit.currency is None: credit.currency = values['currency']
    await record_history(db, module='credit', record_id=row.id, operator=user, operation_type='edit',
        before={'shipment': before}, after={'shipment': shipment_dict(row, credit, customer)}, warehouse_id=credit.warehouse_id)
