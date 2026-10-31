"""Read-only warehouse overview over the existing wallet; never lazy-load a User relationship."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select, func

from app.models.warehouse import Warehouse
from app.models.recharge import RechargeDeclaration
from app.core.permissions import Role
from app.services.wallet import flow_query, grouped_totals, day, money
from app.services.money_period import money_period
from app.core.timezone import thai_now, thai_today


async def warehouse_scope(db, user, header, warehouse_id=None, warehouse_ids=None):
    # Authentication reloads this list from the database on every request, never from token claims.
    allowed = set(getattr(user, '_warehouse_ids', []))
    active = (await db.execute(select(Warehouse).where(Warehouse.id.in_(allowed), Warehouse.is_active.is_(True)).order_by(Warehouse.id))).scalars().all()
    active_ids = {w.id for w in active}
    requested = set(warehouse_ids or [])
    if warehouse_id is not None:requested.add(warehouse_id)
    if header == 'all':
        if user.role != Role.WAREHOUSE_ADMIN:raise HTTPException(403, '无权汇总全部仓库')
    elif header is not None:
        try: selected = int(header)
        except ValueError:raise HTTPException(403, '无权访问所选仓库')
        if selected not in active_ids:raise HTTPException(403, '无权访问所选仓库')
        if requested and requested != {selected}:raise HTTPException(403, '仓库筛选与当前仓库不一致')
        requested = {selected}
    if requested:
        if not requested.issubset(active_ids):raise HTTPException(403, '无权访问所选仓库')
        if len(requested) > 1 and user.role != Role.WAREHOUSE_ADMIN:raise HTTPException(403, '无权汇总全部仓库')
    elif header != 'all':
        # Keep an old account's primary warehouse fallback, but only from freshly loaded membership.
        preferred = getattr(user, '_active_wh_id', None)
        requested = {preferred} if preferred in active_ids else ({active[0].id} if active else set())
    return [w for w in active if not requested or w.id in requested]


async def _overview_charts(db, warehouses):
    """Six Thai calendar months plus yesterday, using the wallet flow projection and filters."""
    today = thai_today()
    month_index = today.year * 12 + today.month - 1 - 5
    start = date(month_index // 12, month_index % 12 + 1, 1)
    yesterday = today - timedelta(days=1)
    ids = [w.id for w in warehouses]
    names = {w.id: w.name for w in warehouses}
    monthly = {}
    cursor = start
    while cursor <= today:
        key = cursor.strftime('%Y-%m')
        monthly[key] = {'income': defaultdict(Decimal), 'expense': defaultdict(Decimal),
                        'warehouse_expense': defaultdict(Decimal)}
        next_month = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
        cursor = next_month

    yesterday_expense = defaultdict(Decimal)
    if ids:
        wallet = flow_query(db, ids)
        rows = (await db.execute(select(wallet.c.date, wallet.c.warehouse_id, wallet.c.currency,
            wallet.c.type, func.sum(wallet.c.amount)).where(wallet.c.date >= start,
            wallet.c.date <= today, wallet.c.status == 'active',
            wallet.c.is_internal_transfer.is_(False)).group_by(wallet.c.date,
            wallet.c.warehouse_id, wallet.c.currency, wallet.c.type))).all()
        for day_value, warehouse_id, currency, kind, value in rows:
            currency = currency or 'THB'
            amount = money(value)
            bucket = monthly.get(day_value.strftime('%Y-%m'))
            if bucket is not None and kind in ('income', 'expense'):
                bucket[kind][currency] += amount
                if kind == 'expense':
                    bucket['warehouse_expense'][(warehouse_id, currency)] += amount
            if day_value == yesterday and kind == 'expense':
                yesterday_expense[(warehouse_id, currency)] += amount

    serialize = lambda values: {currency: format(money(amount), '.2f')
                                for currency, amount in sorted(values.items())}
    return {
        'as_of': thai_now().isoformat(),
        'months': [{
            'month': key,
            'income_by_currency': serialize(bucket['income']),
            'expense_by_currency': serialize(bucket['expense']),
            'expense_by_warehouse': [
                {'warehouse_id': warehouse_id, 'warehouse_name': names[warehouse_id],
                 'currency': currency, 'amount': format(money(amount), '.2f')}
                for (warehouse_id, currency), amount in sorted(bucket['warehouse_expense'].items())
            ],
        } for key, bucket in monthly.items()],
        'yesterday_expense_by_warehouse': [
            {'warehouse_id': warehouse_id, 'expense_by_currency': serialize({
                currency: amount for (wid, currency), amount in yesterday_expense.items()
                if wid == warehouse_id
            })} for warehouse_id in ids
        ],
        'basis': '钱包实际收付；泰国时间；内部转账不计收支；按币种分别汇总',
    }


async def summarize(db, warehouses, start_date=None, end_date=None, month=None, include_charts=False):
    start, end = money_period(month, start_date, end_date, default_start=date.min, default_end=date.max)
    ids = [w.id for w in warehouses]
    wallet = flow_query(db, ids)
    rows = (await db.execute(select(wallet.c.warehouse_id, wallet.c.currency, wallet.c.type,
        func.sum(wallet.c.amount), func.count()).where(wallet.c.date >= start, wallet.c.date <= end,
        wallet.c.status == 'active', wallet.c.is_internal_transfer.is_(False)).group_by(
        wallet.c.warehouse_id, wallet.c.currency, wallet.c.type))).all()
    incoming = (await db.execute(select(wallet.c.warehouse_id, wallet.c.currency, func.sum(wallet.c.amount)).where(
        wallet.c.date >= start, wallet.c.date <= end, wallet.c.status == 'active', wallet.c.source == 'incoming'
        ).group_by(wallet.c.warehouse_id, wallet.c.currency))).all()
    r = RechargeDeclaration
    declaration_currency = func.coalesce(r.currency,'THB')
    declarations = (await db.execute(select(r.warehouse_id, declaration_currency, func.sum(r.amount)).where(
        r.warehouse_id.in_(ids), r.is_voided.is_(False), day(db,r.declare_date) >= start, day(db,r.declare_date) <= end
        ).group_by(r.warehouse_id,declaration_currency))).all()
    unmatched = dict((await db.execute(select(r.warehouse_id,func.count()).where(r.warehouse_id.in_(ids),
        r.is_voided.is_(False),day(db,r.declare_date) >= start,day(db,r.declare_date) <= end,r.match_status == 'unmatched').group_by(r.warehouse_id))).all())
    def amounts(source,wid):return {cur:float(money(value)) for warehouse,cur,value in source if warehouse == wid}
    def legacy_single(values):return next(iter(values.values())) if len(values)==1 else None if values else 0
    from app.services.internal_transfers import transfer_summary
    result = []
    for wh in warehouses:
        own = [(cur,kind,value) for wid,cur,kind,value,count in rows if wid == wh.id]
        counts = {kind:{cur:count for wid,cur,k,value,count in rows if wid == wh.id and k == kind} for kind in ('income','expense')}
        declared = amounts(declarations,wh.id); received = amounts(incoming,wh.id)
        result.append({'internal_transfers':await transfer_summary(db,[wh.id],start,end),'warehouse_id':wh.id,'warehouse_name':wh.name,**grouped_totals(own),
            'income_count_by_currency':counts['income'],'expense_count_by_currency':counts['expense'],
            'income_count':sum(counts['income'].values()),'expense_count':sum(counts['expense'].values()),
            'recharge_total_by_currency':declared,'incoming_total_by_currency':received,
            'recharge_total':legacy_single(declared),'incoming_total':legacy_single(received),
            'unmatched_count':unmatched.get(wh.id,0)})
    all_totals = {}
    for wid,cur,kind,value,count in rows:all_totals[(cur,kind)] = all_totals.get((cur,kind),0) + money(value)
    response = {'data':result,'warehouse_count':len(result),'start_date':str(start),'end_date':str(end),
        'totals':{'internal_transfers':await transfer_summary(db,ids,start,end),**grouped_totals([(cur,kind,value) for (cur,kind),value in all_totals.items()]),
            'income_count':sum(r['income_count'] for r in result),'expense_count':sum(r['expense_count'] for r in result)},
        'basis':'公司钱包实际收付，内部转账不计收支；充值申报另列，不计实收'}
    if include_charts:
        response['overview_charts'] = await _overview_charts(db, warehouses)
    return response
