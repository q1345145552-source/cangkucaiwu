from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.timezone import thai_now, thai_today
from datetime import datetime, date, timedelta
from app.database import get_db
from app.models.credit import CreditCustomer, CreditRepayment, CreditShipment, CreditStatus
from app.models.customer import Customer
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role, check_staff_permission, require_non_labor
from app.services.flow_rules import exceeds_credit_limit
from pydantic import BaseModel, Field
from typing import Optional
from app.services.credit_shipments import (ShipmentData, ShipmentCreate, ShipmentVoid, active_shipment,
    currency_of, shipment_dict, scoped_credit, create_once, refresh_debt, editable_shipment, edit_shipment)
from app.services.warehouse_summary import warehouse_scope
from app.services.money_period import money_period
from app.services.data_history import record_history
from app.services.customer_receivables import positions, empty_position, credit_position, legacy_review, bind_receipt, overdue_from_position
from app.core.retired_entries import require_operating_entries_enabled

router = APIRouter()

class CreditCreate(BaseModel):
    customer_id: int; credit_limit: float; repayment_day: int = 15
    remark: Optional[str] = None

class CreditUpdate(BaseModel):
    credit_limit: Optional[float] = None; repayment_day: Optional[int] = None
    status: Optional[str] = None; current_debt: Optional[float] = None
    overdue_days: Optional[int] = None

class RepaymentCreate(BaseModel):
    repayment_date: str; amount: float; remark: Optional[str] = None
    request_key: Optional[str] = Field(default=None,max_length=64)
    account_id: Optional[int] = None
    incoming_flow_id: Optional[int] = None

async def _compute_debt_and_overdue(db: AsyncSession, credit_id: int):
    """同客户同币种真实发货减唯一实收；历史无来源回款只读待核对。"""
    credit = await db.get(CreditCustomer,credit_id)
    if not credit: return 0,0
    position = await credit_position(db,credit)
    debt = position['outstanding']
    return debt,overdue_from_position(position,thai_today())


@router.get("/shipments", dependencies=[Depends(require_operating_entries_enabled)])
async def list_shipments(request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200),
                         customer_id: int = None, currency: str = None, month: str = None,
                         start_date: str = None, end_date: str = None, status: str = None,
                         current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
                         _perm=Depends(check_staff_permission("账期管理"))):
    scope = [w.id for w in await warehouse_scope(db, current_user, request.headers.get('X-Warehouse-ID'))]
    if currency is not None and currency not in ('THB', 'CNY'): raise HTTPException(400, '不支持的币种')
    if status not in (None, 'active', 'voided'): raise HTTPException(400, '发货状态无效')
    start, end = money_period(month, start_date, end_date, default_start=date.min, default_end=date.max)
    cur = func.coalesce(CreditShipment.currency, CreditCustomer.currency, Customer.default_currency, 'THB')
    query = select(CreditShipment, CreditCustomer, Customer).join(CreditCustomer,
        CreditShipment.credit_customer_id == CreditCustomer.id).join(Customer,
        (Customer.id == CreditCustomer.customer_id) & (Customer.warehouse_id == CreditCustomer.warehouse_id)).where(
        CreditCustomer.warehouse_id.in_(scope), CreditShipment.ship_date >= datetime.combine(start, datetime.min.time()),
        CreditShipment.ship_date <= datetime.combine(end, datetime.max.time()))
    if customer_id is not None: query = query.where(Customer.id == customer_id)
    if currency is not None: query = query.where(cur == currency)
    if status is not None: query = query.where(func.coalesce(CreditShipment.status, 'active') == status)
    all_rows = query.subquery()
    total = (await db.execute(select(func.count()).select_from(all_rows))).scalar_one()
    # Amounts only total effective shipments; voided rows remain visible as history.
    totals_query = query.where(active_shipment()).with_only_columns(cur, func.count(), func.sum(CreditShipment.order_count),
        func.sum(CreditShipment.amount), func.count().filter(CreditShipment.order_count.is_(None))).group_by(cur)
    totals = {c: {'record_count': n, 'order_count': orders or 0, 'amount': round(float(amount or 0), 2),
        'unknown_order_count_records': unknown} for c, n, orders, amount, unknown in (await db.execute(totals_query)).all()}
    rows = (await db.execute(query.order_by(CreditShipment.ship_date.desc(), CreditShipment.id.desc())
        .offset((page-1)*page_size).limit(page_size))).all()
    return {'data': [shipment_dict(row, credit, customer) for row, credit, customer in rows], 'total': total,
        'page': page, 'page_size': page_size, 'totals_by_currency': totals, 'start_date': str(start), 'end_date': str(end)}


@router.get("")
async def list_credit_customers(
    request: Request,
    page: int = 1, page_size: int = 20,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("账期管理")),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    scope = [w.id for w in await warehouse_scope(db, current_user, request.headers.get('X-Warehouse-ID'))]
    query = select(CreditCustomer).where(CreditCustomer.warehouse_id.in_(scope))
    count_q = select(func.count(CreditCustomer.id)).where(CreditCustomer.warehouse_id.in_(scope))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(CreditCustomer.warehouse_id.in_(get_wh_ids(current_user)))
        count_q = count_q.where(CreditCustomer.warehouse_id.in_(get_wh_ids(current_user)))
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(query.order_by(CreditCustomer.created_at.desc()).offset((page-1)*page_size).limit(page_size))
    records = result.scalars().all()
    cids = {r.customer_id for r in records}
    cmap = {}
    if cids:
        custs = (await db.execute(select(Customer).where(Customer.id.in_(cids)))).scalars().all()
        cmap = {c.id: c.company_name for c in custs}

    balances = await positions(db,scope,[r.customer_id for r in records],sources=True)
    reviews = await legacy_review(db,scope,[r.customer_id for r in records])
    data = []
    for r in records:
        currency = r.currency or next((c.default_currency or 'THB' for c in custs if c.id==r.customer_id),'THB')
        position = balances.get(r.customer_id,{}).get(currency,empty_position(r.customer_id,currency))
        debt = position['outstanding']
        overdue = overdue_from_position(position,thai_today())
        data.append({
            "id": r.id, "warehouse_id": r.warehouse_id, "customer_id": r.customer_id,
            "customer_name": cmap.get(r.customer_id, ""), "currency": r.currency or next((c.default_currency or "THB" for c in custs if c.id == r.customer_id), "THB"),
            "credit_limit": r.credit_limit, "current_debt": debt, "receivable_position": position,
            "legacy_current_debt":r.current_debt,"needs_review":bool(reviews.get(r.customer_id)),
            "review_items":reviews.get(r.customer_id,[]),"balance_scope":"customer_currency",
            "overdue_days": overdue, "repayment_day": r.repayment_day,
            "status": r.status, "remark": r.remark,
        })

    return {"data": data, "total": total, "page": page, "page_size": page_size}

@router.post("")
async def create_credit(req: CreditCreate, request: Request, current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db),
                        _perm=Depends(check_staff_permission("账期管理"))):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    if req.credit_limit is not None and req.credit_limit < 0:
        raise HTTPException(400, "信用额度不能为负")
    scope = await warehouse_scope(db, current_user, request.headers.get('X-Warehouse-ID'))
    if len(scope) != 1: raise HTTPException(400, '请先选择一个仓库再开通账期')
    wh_id = scope[0].id
    # 校验客户属于本仓库
    cust = (await db.execute(select(Customer).where(Customer.id == req.customer_id))).scalar_one_or_none()
    if not cust:
        raise HTTPException(404, "客户不存在")
    if cust.warehouse_id != wh_id:
        raise HTTPException(403, "只能为本仓库客户开通账期")
    # 去重：同仓库同客户不允许重复建卡（避免欠款/额度被重复统计）
    dup = (await db.execute(select(CreditCustomer).where(
        CreditCustomer.warehouse_id == wh_id,
        CreditCustomer.customer_id == req.customer_id,
    ))).scalar_one_or_none()
    if dup:
        raise HTTPException(400, "该客户已有账期账户，请勿重复创建")
    c = CreditCustomer(
        warehouse_id=wh_id, customer_id=req.customer_id, currency=cust.default_currency or "THB",
        credit_limit=req.credit_limit, repayment_day=req.repayment_day,
        remark=req.remark, created_by=current_user.id,
    )
    db.add(c); await db.flush(); return {"id": c.id, "message": "账期客户创建成功"}

@router.put("/{credit_id}")
async def update_credit(credit_id: int, req: CreditUpdate,
                        current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db),
                        _perm=Depends(check_staff_permission("账期管理"))):
    result = await db.execute(select(CreditCustomer).where(CreditCustomer.id == credit_id))
    c = result.scalar_one_or_none()
    if not c: raise HTTPException(404, "记录不存在")
    if current_user.role == Role.SUPER_ADMIN:
        pass
    elif current_user.role in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        if c.warehouse_id not in get_wh_ids(current_user):
            raise HTTPException(403, "只能修改自己仓库的账期客户")
    else:
        raise HTTPException(403, "无权限")
    if req.credit_limit is not None: c.credit_limit = req.credit_limit
    if req.repayment_day is not None: c.repayment_day = req.repayment_day
    if req.status is not None: c.status = req.status
    if req.current_debt is not None: c.current_debt = req.current_debt
    if req.overdue_days is not None: c.overdue_days = req.overdue_days
    await db.flush(); return {"message": "更新成功"}

@router.get("/{credit_id}/detail")
async def credit_detail(credit_id: int, request: Request, start_date: str = None, end_date: str = None, month: str = None,
                        current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db),
                        _perm=Depends(check_staff_permission("账期管理"))):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    c, cust = await scoped_credit(db, current_user, request.headers.get('X-Warehouse-ID'), credit_id)
    start, end = money_period(month, start_date, end_date, default_start=date.min, default_end=date.max)
    start_dt = datetime.combine(start, datetime.min.time())
    end_dt = datetime.combine(end, datetime.max.time())

    # Get repayments（按范围）
    rep_q = select(CreditRepayment).where(CreditRepayment.credit_customer_id == credit_id)
    if start_dt: rep_q = rep_q.where(CreditRepayment.repayment_date >= start_dt)
    if end_dt: rep_q = rep_q.where(CreditRepayment.repayment_date <= end_dt)
    reps = (await db.execute(rep_q.order_by(CreditRepayment.created_at.desc()))).scalars().all()

    # Get shipments（按范围）
    ship_q = select(CreditShipment).where(CreditShipment.credit_customer_id == credit_id)
    if start_dt: ship_q = ship_q.where(CreditShipment.ship_date >= start_dt)
    if end_dt: ship_q = ship_q.where(CreditShipment.ship_date <= end_dt)
    ships = (await db.execute(ship_q.order_by(CreditShipment.ship_date.desc()))).scalars().all()

    # Compute debt/overdue
    debt, overdue = await _compute_debt_and_overdue(db, credit_id)

    # Get assessment for this single customer
    ass_data = await _compute_assessment(current_user, db)
    assessment = next((a for a in ass_data["data"] if a["customer_id"] == c.customer_id), None)

    return {
        "id": c.id, "warehouse_id": c.warehouse_id, "customer_id": c.customer_id,
        "customer_name": cust.company_name if cust else "", "currency": currency_of(c, cust),
        "credit_limit": c.credit_limit, "current_debt": debt,
        "receivable_position":await credit_position(db,c),
        "review_items":(await legacy_review(db,[c.warehouse_id],[c.customer_id])).get(c.customer_id,[]),
        "legacy_current_debt":c.current_debt,
        "overdue_days": overdue, "repayment_day": c.repayment_day,
        "status": c.status, "remark": c.remark,
        "rating": assessment["rating"] if assessment else "B",
        "coop_months": assessment["coop_months"] if assessment else 0,
        "on_time_rate": assessment["on_time_rate"] if assessment else 100,
        "overdue_count": assessment["overdue_count"] if assessment else 0,
        "max_overdue_days": assessment["max_overdue_days"] if assessment else 0,
        "avg_monthly_repay": assessment["avg_monthly_repay"] if assessment else 0,
        "utilization_rate": assessment["utilization_rate"] if assessment else 0,
        "repayments": [{"id": r.id, "repayment_date": r.repayment_date.isoformat() if r.repayment_date else None,
                        "amount": r.amount, "remark": r.remark, "incoming_flow_id": r.incoming_flow_id,
                        "created_at": r.created_at.isoformat() if r.created_at else None} for r in reps],
        "shipments": [shipment_dict(s, c, cust) for s in ships],
        "shipment_totals": {"record_count": sum((s.status or 'active') == 'active' for s in ships),
            "order_count": sum(s.order_count or 0 for s in ships if (s.status or 'active') == 'active'),
            "unknown_order_count_records": sum(s.order_count is None for s in ships if (s.status or 'active') == 'active'),
            "amount": round(sum(s.amount for s in ships if (s.status or 'active') == 'active'), 2),
            "currency": currency_of(c, cust)},
    }

@router.post("/{credit_id}/shipment", dependencies=[Depends(require_operating_entries_enabled)])
async def create_shipment(credit_id: int, req: ShipmentCreate, request: Request,
                          current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
                          _perm=Depends(check_staff_permission("账期管理"))):
    c, cust = await scoped_credit(db, current_user, request.headers.get('X-Warehouse-ID'), credit_id, lock=True)
    row, created = await create_once(db, c, cust, req, current_user)
    debt = await refresh_debt(db, c)
    return {**shipment_dict(row, c, cust), **debt, 'created': created,
        'message': '发货记录创建成功' if created else '该次发货已保存，未重复登记'}


@router.put("/{credit_id}/shipment/{shipment_id}", dependencies=[Depends(require_operating_entries_enabled)])
async def update_shipment(credit_id: int, shipment_id: int, req: ShipmentData, request: Request,
                          current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
                          _perm=Depends(check_staff_permission("账期管理"))):
    c, cust = await scoped_credit(db, current_user, request.headers.get('X-Warehouse-ID'), credit_id, lock=True)
    row = await editable_shipment(db, c, shipment_id)
    await edit_shipment(db, c, cust, row, req, current_user)
    debt = await refresh_debt(db, c)
    return {**shipment_dict(row, c, cust), **debt, 'message': '发货记录已更新'}


@router.post("/{credit_id}/shipment/{shipment_id}/void", dependencies=[Depends(require_operating_entries_enabled)])
async def void_shipment(credit_id: int, shipment_id: int, req: ShipmentVoid, request: Request,
                        current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
                        _perm=Depends(check_staff_permission("账期管理"))):
    if not req.reason.strip(): raise HTTPException(400, '请填写作废原因')
    c, cust = await scoped_credit(db, current_user, request.headers.get('X-Warehouse-ID'), credit_id, lock=True)
    row = await editable_shipment(db, c, shipment_id)
    before = shipment_dict(row, c, cust)
    row.status, row.voided_by, row.voided_at, row.void_reason = 'voided', current_user.id, thai_now(), req.reason.strip()
    await record_history(db, module='credit', record_id=row.id, operator=current_user, operation_type='edit',
        before={'shipment': before}, after={'shipment': shipment_dict(row, c, cust)}, warehouse_id=c.warehouse_id)
    debt = await refresh_debt(db, c)
    return {**shipment_dict(row, c, cust), **debt, 'message': '发货记录已作废，历史记录保留'}


@router.post("/{credit_id}/payment", dependencies=[Depends(require_non_labor)])
async def record_repayment(credit_id: int, req: RepaymentCreate, request: Request,
                           current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
                           _perm=Depends(check_staff_permission("账期管理"))):
    c, customer = await scoped_credit(db,current_user,request.headers.get('X-Warehouse-ID'),credit_id,lock=True)
    from app.models.recharge import IncomingFlow
    from app.services.wallet import positive_money, money
    from app.services.incoming_receipts import create_once as create_receipt
    from app.schemas.business import IncomingCreate
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    import hashlib, uuid
    value = positive_money(req.amount)
    try: when = datetime.fromisoformat(req.repayment_date)
    except ValueError: raise HTTPException(400,'回款日期格式错误')
    if when.tzinfo is not None: raise HTTPException(400,'回款请使用本地业务日期，不带时区')
    currency = currency_of(c,customer)
    async def replay(old):
        old_flow = await db.get(IncomingFlow,old.incoming_flow_id)
        if old.credit_customer_id != credit_id or money(old.amount) != value or old.repayment_date.date() != when.date() or not old_flow or (req.account_id is not None and req.account_id != old_flow.account_id) or (req.incoming_flow_id is not None and req.incoming_flow_id != old_flow.id):
            raise HTTPException(409,'回款请求已使用，请刷新后重试')
        debt = await _compute_debt_and_overdue(db,credit_id)
        return {'id':old.id,'incoming_flow_id':old.incoming_flow_id,'current_debt':debt[0],'overdue_days':debt[1],'message':'回款已登记，实收未重复计算'}
    if req.request_key:
        old = (await db.execute(select(CreditRepayment).where(CreditRepayment.request_key == req.request_key))).scalar_one_or_none()
        if old: return await replay(old)
    if req.incoming_flow_id:
        flow = (await db.execute(select(IncomingFlow).where(IncomingFlow.id == req.incoming_flow_id)
            .with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if flow is not None and flow.warehouse_id != c.warehouse_id: raise HTTPException(403,'只能关联本仓库到账')
        if flow is None or money(flow.amount) != value or flow.currency != currency:
            raise HTTPException(400,'到账流水不存在、币种或金额不一致')
        if flow.received_date.date() != when.date(): raise HTTPException(400,'回款日期必须与到账日期一致')
        if (await db.execute(select(CreditRepayment.id).where(CreditRepayment.incoming_flow_id == flow.id))).first():
            raise HTTPException(400,'该到账流水已登记回款')
        await bind_receipt(db,customer,flow,current_user)
    else:
        receipt_key = hashlib.sha256(('credit:'+req.request_key).encode()).hexdigest() if req.request_key else uuid.uuid4().hex
        flow,_ = await create_receipt(db,IncomingCreate(request_key=receipt_key,customer_id=customer.id,
            account_id=req.account_id,received_date=when.isoformat(),amount=float(value),currency=currency,
            payer_name=customer.company_name,remark=f'账期回款 #{credit_id} {req.remark or ""}'),c.warehouse_id,current_user)
    insert = sqlite_insert if db.bind.dialect.name == 'sqlite' else pg_insert
    rid = (await db.execute(insert(CreditRepayment).values(credit_customer_id=credit_id,repayment_date=when,
        amount=float(value),remark=req.remark,recorded_by=current_user.id,incoming_flow_id=flow.id,request_key=req.request_key)
        .on_conflict_do_nothing().returning(CreditRepayment.id))).scalar_one_or_none()
    if rid is None:
        old = (await db.execute(select(CreditRepayment).where(CreditRepayment.request_key == req.request_key))).scalar_one_or_none() if req.request_key else None
        if old: return await replay(old)
        raise HTTPException(409,'该到账或回款请求已登记，请刷新后核对')
    await record_history(db,module='credit',record_id=rid,operator=current_user,operation_type='create',
        after={'credit_id':credit_id,'incoming_flow_id':flow.id,'customer_id':customer.id,'amount':float(value),
            'currency':currency,'action':'关联唯一实际到账，不另增一次实收'},warehouse_id=c.warehouse_id)
    debt = await refresh_debt(db,c)
    return {'id':rid,'incoming_flow_id':flow.id,**debt,'message':'回款已关联实际到账，同笔资金只计一次'}

@router.get("/dashboard")
async def credit_dashboard(request: Request, current_user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db),
                           _perm=Depends(check_staff_permission("账期管理"))):
    # 全局统计
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    # Get all active credit customers for this warehouse and compute debt in realtime (batch)
    scope = [w.id for w in await warehouse_scope(db, current_user, request.headers.get('X-Warehouse-ID'))]
    cust_query = select(CreditCustomer).where(CreditCustomer.warehouse_id.in_(scope))
    if current_user.role != Role.SUPER_ADMIN:
        cust_query = cust_query.where(CreditCustomer.warehouse_id.in_(get_wh_ids(current_user)))
    all_credits = (await db.execute(cust_query)).scalars().all()
    total_cust = len(all_credits)
    fact_balances = await positions(db,scope,[c.customer_id for c in all_credits],sources=True)
    customer_map = {r.id:r for r in (await db.execute(select(Customer).where(Customer.id.in_({c.customer_id for c in all_credits})))).scalars()}
    overdue_count = sum(1 for c in all_credits if c.status == CreditStatus.ACTIVE.value and
        overdue_from_position(fact_balances.get(c.customer_id,{}).get(
            currency_of(c,customer_map[c.customer_id]),empty_position(c.customer_id,c.currency or 'THB')),thai_today()) > 0)

    # Rating distribution
    try:
        assessment_result = await _compute_assessment(current_user, db)
        rating_dist = {"A": 0, "B": 0, "C": 0}
        for item in assessment_result["data"]:
            r = item.get("rating", "B")
            rating_dist[r] = rating_dist.get(r, 0) + 1
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"评级计算失败: {e}")
        rating_dist = {"A": 0, "B": 0, "C": 0}

    customers = {c.id: c for c in (await db.execute(select(Customer).where(Customer.id.in_({c.customer_id for c in all_credits})))).scalars().all()}
    currency_totals = {cur:{'total_debt':0,'total_credit_limit':0} for groups in fact_balances.values() for cur in groups}
    for c in all_credits:
        customer = customers.get(c.customer_id)
        if not customer or customer.warehouse_id != c.warehouse_id: continue
        cur = currency_of(c, customer)
        group = currency_totals.setdefault(cur, {'total_debt': 0, 'total_credit_limit': 0})
        group['total_credit_limit'] += c.credit_limit or 0
    for cur,group in currency_totals.items():
        group['total_debt'] = round(sum(groups.get(cur,{}).get('outstanding',0) for groups in fact_balances.values()), 2)
        group['total_credit_limit'] = round(group['total_credit_limit'],2)
        group['utilization_rate'] = round(group['total_debt'] / group['total_credit_limit'] * 100, 1) if group['total_credit_limit'] else 0
    # 旧单币种字段兼容；混合币种不能伪装成一个泰铢合计。
    total_debt = next(iter(currency_totals.values()))['total_debt'] if len(currency_totals)==1 else None if currency_totals else 0
    total_limit = next(iter(currency_totals.values()))['total_credit_limit'] if len(currency_totals)==1 else None if currency_totals else 0

    return {
        "currency_totals": currency_totals, "total_debt": float(total_debt) if total_debt is not None else None, "total_credit_limit": float(total_limit) if total_limit is not None else None,
        "total_customers": total_cust or 0, "overdue_count": overdue_count,
        "utilization_rate": round(float(total_debt or 0) / float(total_limit or 1) * 100, 1) if total_limit else 0,
        "rating_dist": rating_dist,
    }


# ==== Assessment & Rating ====
async def _compute_assessment(
    current_user: User, db: AsyncSession,
) -> dict:
    """核心评级计算逻辑，供端点和看板复用"""
    wh_id = get_wh_id(current_user)
    query = select(CreditCustomer).where(CreditCustomer.status == CreditStatus.ACTIVE.value)
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(CreditCustomer.warehouse_id.in_(get_wh_ids(current_user)))
    records = (await db.execute(query)).scalars().all()

    cids = {r.customer_id for r in records}
    cmap = {}
    if cids:
        custs = (await db.execute(select(Customer).where(Customer.id.in_(cids)))).scalars().all()
        cmap = {c.id: {"name": c.company_name, "created_at": c.created_at} for c in custs}

    balances = await positions(db,get_wh_ids(current_user),[r.customer_id for r in records],sources=True)
    today = thai_today()
    data = []
    for r in records:
        cust_info = cmap.get(r.customer_id, {"name": "", "created_at": None})

        coop_months = 0
        if cust_info["created_at"] and hasattr(cust_info["created_at"], 'date'):
            coop_months = max(0, (today - cust_info["created_at"].date()).days // 30)

        reps = (await db.execute(
            select(CreditRepayment).where(CreditRepayment.credit_customer_id == r.id)
            .order_by(CreditRepayment.repayment_date.asc())
        )).scalars().all()

        ships = (await db.execute(
            select(CreditShipment).where(CreditShipment.credit_customer_id == r.id, active_shipment())
            .order_by(CreditShipment.ship_date.asc())
        )).scalars().all()

        total_repayments = len(reps)
        on_time_count = 0
        overdue_count = 0
        max_overdue_days = 0

        for rep in reps:
            rep_date = rep.repayment_date.date() if hasattr(rep.repayment_date, 'date') else rep.repayment_date
            relevant_ship_date = None
            for s in ships:
                sd = s.ship_date.date() if hasattr(s.ship_date, 'date') else s.ship_date
                if sd <= rep_date:
                    relevant_ship_date = sd
            if relevant_ship_date:
                days_since = (rep_date - relevant_ship_date).days
                if days_since <= (r.repayment_day or 15):
                    on_time_count += 1
                else:
                    overdue_count += 1
                    max_overdue_days = max(max_overdue_days, days_since - (r.repayment_day or 15))
            else:
                on_time_count += 1

        on_time_rate = round(on_time_count / total_repayments * 100, 1) if total_repayments > 0 else 100

        three_months_ago = today.replace(day=1)
        if three_months_ago.month > 2:
            three_months_ago = three_months_ago.replace(month=three_months_ago.month - 2)
        else:
            three_months_ago = three_months_ago.replace(year=three_months_ago.year - 1, month=three_months_ago.month + 10)

        recent_reps = [rep for rep in reps if rep.repayment_date and
                       (rep.repayment_date.date() if hasattr(rep.repayment_date, 'date') else rep.repayment_date) >= three_months_ago]
        avg_monthly_repay = round(sum(rp.amount for rp in recent_reps) / 3, 1) if recent_reps else 0

        customer = await db.get(Customer,r.customer_id)
        currency = currency_of(r,customer)
        factual_debt = balances.get(r.customer_id,{}).get(currency,{}).get('outstanding',0)
        utilization_rate = round(factual_debt / (r.credit_limit or 1) * 100, 1)

        if coop_months >= 6 and overdue_count == 0 and on_time_rate >= 95:
            rating = "A"
        elif coop_months < 3 or overdue_count >= 3 or max_overdue_days > 30:
            rating = "C"
        else:
            rating = "B"

        data.append({
            "id": r.id, "customer_id": r.customer_id,
            "customer_name": cust_info.get("name", ""),
            "rating": rating,
            "credit_limit": r.credit_limit or 0,
            "current_debt": factual_debt, "currency":currency,
            "overdue_days": overdue_from_position(balances.get(r.customer_id,{}).get(currency,empty_position(r.customer_id,currency)),today),
            "coop_months": coop_months,
            "on_time_rate": on_time_rate,
            "total_repayments": total_repayments,
            "overdue_count": overdue_count,
            "max_overdue_days": max_overdue_days,
            "avg_monthly_repay": avg_monthly_repay,
            "utilization_rate": utilization_rate,
        })

    return {"data": data}


@router.get("/assessment")
async def credit_assessment(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("账期管理")),
):
    """返回所有账期客户的评级和评估数据"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    return await _compute_assessment(current_user, db)


@router.get("/assessment/export")
async def export_assessment(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("账期管理")),
):
    """导出账期客户评估报告"""
    from fastapi.responses import StreamingResponse
    import io, openpyxl

    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")

    # Reuse assessment logic
    result = await _compute_assessment(current_user, db)
    data = result["data"]

    rating_labels = {"A": "A级-优质客户", "B": "B级-正常客户", "C": "C级-风险客户"}
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "账期客户评估"
    ws.append(["客户名称", "评级", "信用额度", "当前欠款", "逾期天数", "还款准时率(%)",
                "逾期次数", "最长逾期(天)", "合作时长(月)", "月均还款", "额度使用率(%)"])

    for d in data:
        ws.append([
            d["customer_name"], rating_labels.get(d["rating"], d["rating"]),
            d["credit_limit"], d["current_debt"], d["overdue_days"],
            d["on_time_rate"], d["overdue_count"], d["max_overdue_days"],
            d["coop_months"], d["avg_monthly_repay"], d["utilization_rate"],
        ])

    output = io.BytesIO()
    wb.save(output); output.seek(0)
    return StreamingResponse(output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=credit_assessment.xlsx"})


@router.get("/alerts")
async def credit_alerts(request: Request, level: str = None, current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db),
                        _perm=Depends(check_staff_permission("账期管理"))):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    # 拉取本仓库所有活跃账期客户，批量实时计算欠款/逾期（避免 N+1，且口径与列表页一致）
    scope = [w.id for w in await warehouse_scope(db, current_user, request.headers.get('X-Warehouse-ID'))]
    query = select(CreditCustomer).where(CreditCustomer.status == CreditStatus.ACTIVE.value, CreditCustomer.warehouse_id.in_(scope))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(CreditCustomer.warehouse_id.in_(get_wh_ids(current_user)))
    records = (await db.execute(query)).scalars().all()
    cids = {r.customer_id for r in records}
    cmap = {}
    if cids:
        custs = (await db.execute(select(Customer).where(Customer.id.in_(cids)))).scalars().all()
        cmap = {c.id: c.company_name for c in custs}

    balances = await positions(db,scope,[r.customer_id for r in records],sources=True)
    today = thai_today()
    data = []
    for r in records:
        customer = await db.get(Customer,r.customer_id)
        currency = currency_of(r,customer)
        debt = balances.get(r.customer_id,{}).get(currency,{}).get('outstanding',0)
        if debt <= 0:
            continue
        overdue = overdue_from_position(balances[r.customer_id][currency],today)
        if overdue <= 0:
            continue
        data.append({
            "id": r.id, "customer_name": cmap.get(r.customer_id, ""), "currency": currency,
            "current_debt": debt, "overdue_days": overdue,
            "credit_limit": r.credit_limit, "status": r.status,
        })
    data.sort(key=lambda x: x["overdue_days"], reverse=True)
    return {"data": data}
