"""客户应收的只读事实投影；不另建欠款、预收或核销金额账。

同客户、同仓、同币种按总应收抵总实收，不猜逐票核销。
来源记录依原ID追溯；不同关联指向同一到账时只出现一个到账事件。
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import Integer, Numeric, and_, case, cast, func, literal, select, union_all
from app.models.income_expense import IncomeRecord
from app.models.customer import Customer
from app.models.credit import CreditCustomer, CreditShipment, CreditRepayment
from app.models.recharge import IncomingFlow, RechargeDeclaration, ReconciliationResult
from app.services.wallet import day, money


ACTIVE_MATCHES = ('matched', 'manual_matched')


def receipt_candidates_query():
    """Only explicit IDs qualify; conflicting/foreign/currency-invalid links are quarantined."""
    f, c, d, r, account, payment = IncomingFlow, Customer, RechargeDeclaration, ReconciliationResult, CreditCustomer, CreditRepayment
    direct = select(f.id.label('flow_id'), f.warehouse_id, f.customer_id,
        cast(and_(c.warehouse_id == f.warehouse_id, f.amount > 0), Integer).label('valid')).select_from(f).outerjoin(
            c, c.id == f.customer_id).where(f.customer_id.is_not(None))
    matched = select(f.id.label('flow_id'), f.warehouse_id, d.customer_id,
        cast(and_(r.warehouse_id == f.warehouse_id, d.warehouse_id == f.warehouse_id,
            c.warehouse_id == f.warehouse_id, func.coalesce(d.currency, 'THB') == func.coalesce(f.currency, 'THB'),
            f.amount > 0), Integer).label('valid')).select_from(f).join(r, r.flow_id == f.id).join(
                d, d.id == r.declaration_id).outerjoin(c, c.id == d.customer_id).where(r.match_status.in_(ACTIVE_MATCHES))
    repaid = select(f.id.label('flow_id'), f.warehouse_id, account.customer_id,
        cast(and_(account.warehouse_id == f.warehouse_id, c.warehouse_id == f.warehouse_id,
            func.coalesce(account.currency, c.default_currency, 'THB') == func.coalesce(f.currency, 'THB'),
            cast(payment.amount, Numeric(18,2)) == cast(f.amount, Numeric(18,2)), payment.amount > 0,
            func.date(payment.repayment_date) == func.date(f.received_date)), Integer).label('valid')).select_from(f).join(
                payment, payment.incoming_flow_id == f.id).join(account, account.id == payment.credit_customer_id).outerjoin(
                    c, c.id == account.customer_id)
    return union_all(direct, matched, repaid).subquery('receipt_customer_candidates')


def receipt_identity_query():
    candidates = receipt_candidates_query()
    unambiguous = and_(func.count(func.distinct(candidates.c.customer_id)) == 1,
        func.min(func.coalesce(candidates.c.valid, 0)) == 1)
    return select(candidates.c.flow_id, candidates.c.warehouse_id,
        case((unambiguous, func.min(candidates.c.customer_id)), else_=None).label('customer_id'),
        func.count(func.distinct(candidates.c.customer_id)).label('customer_count'),
        func.min(func.coalesce(candidates.c.valid, 0)).label('valid')).group_by(
            candidates.c.flow_id, candidates.c.warehouse_id).subquery('receipt_customer_identity')


def event_query(db, warehouse_ids, customer_ids=None):
    """One statement/snapshot supplies both balances and their source rows."""
    f, c, s, account = IncomingFlow, Customer, CreditShipment, CreditCustomer
    cur = func.coalesce(s.currency, account.currency, c.default_currency, 'THB')
    shipping = select(s.id.label('source_id'), literal('shipment').label('source'),
        account.warehouse_id, account.customer_id, cur.label('currency'), day(db,s.ship_date).label('date'),
        cast(s.amount, Numeric(18,2)).label('amount'), s.credit_customer_id.label('credit_id'),
        s.order_count, s.order_no, s.remark).join(account, account.id == s.credit_customer_id).join(
            c, and_(c.id == account.customer_id, c.warehouse_id == account.warehouse_id)).where(
                account.warehouse_id.in_(warehouse_ids), func.coalesce(s.status, 'active') == 'active', s.amount > 0)
    identity = receipt_identity_query()
    receipts = select(f.id.label('source_id'), literal('incoming').label('source'), f.warehouse_id,
        identity.c.customer_id, func.coalesce(f.currency,'THB').label('currency'), day(db,f.received_date).label('date'),
        cast(f.amount, Numeric(18,2)).label('amount'), cast(literal(None),Integer).label('credit_id'),
        cast(literal(None),Integer).label('order_count'), literal(None).label('order_no'), f.remark).join(identity,
            and_(identity.c.flow_id == f.id, identity.c.warehouse_id == f.warehouse_id)).where(
                f.warehouse_id.in_(warehouse_ids), identity.c.customer_id.is_not(None), f.amount > 0)
    events = union_all(shipping, receipts).subquery('customer_receivable_events')
    query = select(events)
    if customer_ids is not None: query = query.where(events.c.customer_id.in_(customer_ids))
    return query, events


async def positions(db, warehouse_ids, customer_ids=None, *, end_date=date.max, start_date=date.min, sources=False):
    query, events = event_query(db, warehouse_ids, customer_ids)
    rows = (await db.execute(query.where(events.c.date <= end_date).order_by(
        events.c.date, events.c.source, events.c.source_id))).mappings().all()
    groups = {}
    for row in rows:
        key = (row['customer_id'], row['currency'])
        group = groups.setdefault(key, {'customer_id': key[0], 'currency': key[1], 'shipped': Decimal(0),
            'received': Decimal(0), 'shipment_count': 0, 'receipt_count': 0, 'order_count': 0,
            'unknown_order_count_records': 0, 'opening_signed_balance': Decimal(0), 'events': []})
        value = money(row['amount'])
        is_ship = row['source'] == 'shipment'
        group['shipped' if is_ship else 'received'] += value
        group['shipment_count' if is_ship else 'receipt_count'] += 1
        if is_ship:
            group['order_count'] += row['order_count'] or 0
            group['unknown_order_count_records'] += int(row['order_count'] is None)
        signed = group['shipped'] - group['received']
        if row['date'] < start_date:
            group['opening_signed_balance'] = signed
        elif sources:
            group['events'].append({**dict(row), 'date': str(row['date']), 'amount': float(value),
                'outstanding_after': float(max(signed,0)), 'prepayment_after': float(max(-signed,0)),
                'source_link': '/incoming' if not is_ship else '/credit'})
    result = defaultdict(dict)
    for (cid, cur), group in groups.items():
        shipping, receipts = group['shipped'], group['received']
        group.update(applied=float(min(shipping, receipts)), outstanding=float(max(shipping-receipts,0)),
            prepayment=float(max(receipts-shipping,0)))
        for field in ('shipped','received','opening_signed_balance'): group[field] = float(money(group[field]))
        if not sources: group.pop('events')
        result[cid][cur] = group
    return dict(result)


def empty_position(customer_id, currency):
    return {'customer_id':customer_id, 'currency':currency, 'shipped':0, 'received':0, 'applied':0,
        'outstanding':0, 'prepayment':0, 'shipment_count':0, 'receipt_count':0,
        'order_count':0, 'unknown_order_count_records':0, 'opening_signed_balance':0}


async def assert_receipt_customer(db, flow, customer_id):
    """Caller owns the flow row lock; binding cannot move one receipt to another customer."""
    identity = receipt_identity_query()
    current = (await db.execute(select(identity).where(identity.c.flow_id == flow.id))).mappings().one_or_none()
    if current and (current['customer_id'] is None or current['customer_id'] != customer_id):
        raise HTTPException(409, '该到账已关联其他客户或存在历史冲突，请先核对，不能重复分配')
    if flow.customer_id is not None and flow.customer_id != customer_id:
        raise HTTPException(409, '该到账已关联其他客户，不能重复分配')


async def legacy_review(db, warehouse_ids, customer_ids):
    """只读列出无法当作期初或新实收的旧记录；不回填、不删、不重分配。"""
    reviews = defaultdict(list)
    customers = (await db.execute(select(Customer).where(Customer.id.in_(customer_ids), Customer.warehouse_id.in_(warehouse_ids)))).scalars().all()
    for c in customers:
        if c.debt_amount:
            reviews[c.id].append({'type':'legacy_manual_debt', 'source_id':c.id, 'amount':float(money(c.debt_amount)),
                'currency':c.default_currency or 'THB', 'message':'历史手填欠款，没有期初来源；仅列出待核对，不自动补期初'})
    manual = (await db.execute(select(IncomeRecord).where(IncomeRecord.warehouse_id.in_(warehouse_ids),IncomeRecord.customer_id.in_(customer_ids)))).scalars().all()
    for row in manual:
        reviews[row.customer_id].append({'type':'manual_income_purpose_unconfirmed','source_id':row.id,
            'date':str(row.income_date.date()),'amount':float(money(row.amount)),'currency':row.currency or 'THB',
            'message':'手工收入未明确用于抵运费，保留原收支记录，不自动抵客户应收'})
    accounts = CreditCustomer
    cached = (await db.execute(select(accounts,Customer).join(Customer,
        and_(Customer.id == accounts.customer_id,Customer.warehouse_id == accounts.warehouse_id)).where(
            accounts.warehouse_id.in_(warehouse_ids),accounts.customer_id.in_(customer_ids),accounts.current_debt != 0))).all()
    factual = await positions(db,warehouse_ids,customer_ids) if cached else {}
    for account, customer in cached:
        cur = account.currency or customer.default_currency or 'THB'
        confirmed = factual.get(customer.id,{}).get(cur,{}).get('outstanding',0)
        if money(account.current_debt) != money(confirmed):
            reviews[customer.id].append({'type':'legacy_credit_cache_difference','source_id':account.id,
                'amount':float(money(account.current_debt)),'currency':cur,
                'message':'旧账期欠款缓存与可核实来源不一致，原值保留待核对，不自动作期初或覆盖'})
    old = (await db.execute(select(CreditRepayment, accounts, Customer).join(accounts,
        accounts.id == CreditRepayment.credit_customer_id).join(Customer,
            and_(Customer.id == accounts.customer_id, Customer.warehouse_id == accounts.warehouse_id)).where(
                accounts.warehouse_id.in_(warehouse_ids), accounts.customer_id.in_(customer_ids),
                CreditRepayment.incoming_flow_id.is_(None)))).all()
    for payment, account, customer in old:
        reviews[customer.id].append({'type':'legacy_unlinked_payment','source_id':payment.id,
            'credit_id':account.id,'date':str(payment.repayment_date.date()),'amount':float(money(payment.amount)),
            'currency':account.currency or customer.default_currency or 'THB',
            'message':'历史回款没有到账编号，保留原记录，不能证明新的实收或可用预收'})
    candidates, identity, f = receipt_candidates_query(), receipt_identity_query(), IncomingFlow
    conflicts = (await db.execute(select(candidates.c.customer_id, f.id, f.currency, f.amount).join(
        identity, identity.c.flow_id == candidates.c.flow_id).join(f, f.id == candidates.c.flow_id).where(
            candidates.c.customer_id.in_(customer_ids), f.warehouse_id.in_(warehouse_ids), identity.c.customer_id.is_(None))
            .distinct())).all()
    for cid, rid, cur, amount in conflicts:
        reviews[cid].append({'type':'receipt_identity_conflict','source_id':rid,'currency':cur,
            'amount':float(money(amount)), 'message':'到账关联客户、仓库、币种或回款来源冲突，未自动分配'})
    return dict(reviews)


async def bind_receipt(db, customer, flow, user):
    from app.core.timezone import thai_now
    from app.services.data_history import record_history
    if flow.warehouse_id != customer.warehouse_id:
        raise HTTPException(403, '只能关联本仓库的客户和到账')
    if flow.amount <= 0: raise HTTPException(400, '只有正数实际到账可以关联客户')
    await assert_receipt_customer(db, flow, customer.id)
    if flow.customer_id == customer.id: return False
    before = flow.customer_id
    flow.customer_id = customer.id
    await record_history(db,module='credit',record_id=flow.id,operator=user,operation_type='edit',
        before={'incoming_id':flow.id,'customer_id':before},
        after={'incoming_id':flow.id,'customer_id':customer.id,'amount':flow.amount,'currency':flow.currency,
            'linked_at':thai_now().isoformat(),'action':'明确到账客户归属，钱包不重复入账'},warehouse_id=customer.warehouse_id)
    await db.flush()
    return True


async def credit_position(db, credit):
    customer = await db.get(Customer,credit.customer_id)
    currency = credit.currency or (customer.default_currency if customer else None) or 'THB'
    groups = await positions(db,[credit.warehouse_id],[credit.customer_id],sources=True)
    return groups.get(credit.customer_id,{}).get(currency,{**empty_position(credit.customer_id,currency),'events':[]})


async def customer_credit_totals(db, warehouse_ids):
    """只按每个客户的正应收汇总，不拿甲的预收抵乙的应收。"""
    balances = await positions(db,warehouse_ids)
    totals = {}
    for groups in balances.values():
        for cur, group in groups.items(): totals[cur] = money(totals.get(cur,0)) + money(group['outstanding'])
    return {cur:float(value) for cur,value in totals.items()}


def overdue_from_position(position, today):
    if position['outstanding'] <= 0: return 0
    receipts = [date.fromisoformat(e['date']) for e in position.get('events',[]) if e['source']=='incoming']
    shipments = [date.fromisoformat(e['date']) for e in position.get('events',[]) if e['source']=='shipment']
    reference = max(receipts) if receipts else max(shipments) if shipments else None
    return max((today-reference).days,0) if reference else 0
