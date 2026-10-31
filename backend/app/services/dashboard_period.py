"""One calendar-period wallet read feeds dashboard totals and daily charts together."""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal
from sqlalchemy import select, and_

from app.models.recharge import RechargeDeclaration
from app.models.supplier import PurchaseOrder, Supplier
from app.services.money_period import money_period
from app.services.wallet import flow_query, day, money
from app.services.procurement_payments import procurement_payment_rows


async def monthly_view(db, warehouses, month):
    start, end = money_period(month)
    ids = [w.id for w in warehouses]
    q = flow_query(db, ids)
    facts = (await db.execute(select(q).where(q.c.date >= start, q.c.date <= end,
        q.c.status == 'active', q.c.is_internal_transfer.is_(False)))).mappings().all()
    r = RechargeDeclaration
    declared = (await db.execute(select(r.currency, day(db,r.declare_date), r.amount, r.match_status).where(
        r.warehouse_id.in_(ids),r.is_voided.is_(False),day(db,r.declare_date) >= start,day(db,r.declare_date) <= end))).all()
    o = PurchaseOrder
    orders = (await db.execute(select(o.currency,day(db,o.created_at)).where(o.warehouse_id.in_(ids),
        day(db,o.created_at) >= start,day(db,o.created_at) <= end))).all()
    procurement = procurement_payment_rows(db,ids)
    suppliers = (await db.execute(select(procurement.c.currency,procurement.c.amount,Supplier.name).outerjoin(
        Supplier,and_(Supplier.id == procurement.c.supplier_id,Supplier.warehouse_id == procurement.c.warehouse_id)
        ).where(procurement.c.payment_date >= start,procurement.c.payment_date <= end))).all()
    suppliers = list(suppliers) + [(f['currency'],f['amount'],'垫款归还（未指定供应商）') for f in facts
        if f['source'] == 'cash_advance_repayment' and f['category_name'] == '采购' and f['type'] == 'expense']
    currencies = sorted({'THB','CNY'} | {f['currency'] for f in facts} | {c or 'THB' for c,*_ in declared})
    days = [(start + timedelta(days=i)).isoformat() for i in range((end-start).days+1)]
    sums = defaultdict(Decimal); counts = defaultdict(int); daily = defaultdict(Decimal)
    categories = defaultdict(Decimal); supplier_amounts = defaultdict(Decimal)
    for f in facts:
        cur,kind,value,d = f['currency'],f['type'],money(f['amount']),str(f['date'])
        sums[(kind,cur)] += value; counts[(kind,cur)] += 1; daily[(kind,cur,d)] += value
        if kind == 'income':
            source = 'incoming' if f['source'] == 'incoming' else 'other_income'
            sums[(source,cur)] += value; daily[(source,cur,d)] += value
        else:
            name = f['category_name'] or '未分类';categories[(cur,name)] += value
            if name != '采购':sums[('operating',cur)] += value
    for cur,d,value,status in declared:
        cur=cur or 'THB';sums[('declaration',cur)] += money(value);daily[('declaration',cur,str(d))] += money(value)
    for cur,d in orders:counts[('order',cur or 'THB',str(d))] += 1
    for cur,value,name in suppliers:
        cur=cur or 'THB';supplier_amounts[(cur,name or '未指定供应商')] += money(value);sums[('procurement',cur)] += money(value)
    def amounts(kind):return [{'currency':c,'amount':float(sums[(kind,c)])} for c in currencies]
    net = [{'currency':c,'amount':float(sums[('income',c)]-sums[('expense',c)])} for c in currencies]
    period = {'month':month,'start_date':str(start),'end_date':str(end),'timezone':'Asia/Bangkok'}
    income_expense = {c:[{'date':d,'month':month,'income':float(daily[('income',c,d)]),
        'expense':float(daily[('expense',c,d)])} for d in days] for c in currencies}
    funds = {c:[{'date':d,'incoming':float(daily[('incoming',c,d)]),
        'other_income':float(daily[('other_income',c,d)]),'recharge':float(daily[('declaration',c,d)])} for d in days] for c in currencies}
    def breakdown(values,c):return [{'name':name,'amount':float(value)} for (cur,name),value in sorted(values.items()) if cur==c and value != 0]
    from app.services.internal_transfers import transfer_summary
    transfers = await transfer_summary(db,ids,start,end)
    return {'period':period,'warehouses':[{'id':w.id,'name':w.name} for w in warehouses],
        'month_card':{'internal_transfers':transfers,'income':amounts('income'),'expense':amounts('expense'),'net':net,'profit':net,
            'operating_expense':amounts('operating'),'procurement_expense':amounts('procurement'),
            'income_count_by_currency':{c:counts[('income',c)] for c in currencies},
            'expense_count_by_currency':{c:counts[('expense',c)] for c in currencies}},
        'recharge_reconciliation':{'recharge':amounts('declaration'),'incoming':amounts('incoming'),
            'unmatched_count':sum(status=='unmatched' for _,_,_,status in declared)},
        'trends':{'period':period,'funds':funds,'income_expense':income_expense,
            'orders':{c:[{'date':d,'week_start':d,'count':counts[('order',c,d)]} for d in days] for c in currencies},
            'expense_categories':{c:breakdown(categories,c) for c in currencies},
            'procurement_suppliers':{c:breakdown(supplier_amounts,c) for c in currencies}}}
