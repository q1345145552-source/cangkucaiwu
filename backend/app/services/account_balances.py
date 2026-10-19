"""账户余额与报表使用同一套实际收付；内部转账只改变各账户，不改变公司收支。"""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from sqlalchemy import select, func
from app.core.timezone import thai_today


async def balances_at(db, accounts, at):
    """at 当天开始的余额；期初日期前后均按原始币种正反推，不移动历史日期。"""
    if not accounts: return {}
    from app.services.wallet import flow_query, money
    q = flow_query(db, sorted({a.warehouse_id for a in accounts}))
    anchors = {a.id: a.opening_balance_date or thai_today().replace(day=1) for a in accounts}
    low, high = min([at, *anchors.values()]), max([at, *anchors.values()])
    changes = defaultdict(lambda: Decimal('0.00'))
    if low < high:
        rows = (await db.execute(select(q.c.account_id, q.c.date, q.c.type, func.sum(q.c.amount)).where(
            q.c.account_id.in_(anchors), q.c.date >= low, q.c.date < high, q.c.status == 'active'
        ).group_by(q.c.account_id, q.c.date, q.c.type))).all()
        for aid, day, kind, value in rows:
            anchor = anchors[aid]
            if min(anchor, at) <= day < max(anchor, at):
                changes[aid] += money(value) * (1 if kind == 'income' else -1) * (1 if at >= anchor else -1)
    return {a.id: money(a.opening_balance) + changes[a.id] for a in accounts}


async def current_account_balances(db, accounts):
    return await balances_at(db, accounts, thai_today() + timedelta(days=1))
