"""独立经营观察：发货事实与钱包分开，成本归期不明时不计算利润。

只读已有来源；不将付款日、单据提交日或资金调拨认定为经营成本归期。
"""
from datetime import date
from fastapi import HTTPException
from sqlalchemy import select, and_, or_
from app.models import Customer, ExpenseRecord, IncomeExpenseCategory, ExpenseApproval, ExpenseFundDisbursement, EmployeeAdvance
from app.models.payroll import PayrollRecord
from app.models.reimbursement import Reimbursement
from app.models.payable import PayableBill
from app.models.expense_fund import ExpenseFund, ExpenseFundItem
from app.services.customer_receivables import positions, legacy_review
from app.services.wallet import money, day, totals, grouped_totals

GAPS = [
    '尚未建立完整的经营成本所属期间和完整性确认，缺成本不等于成本为零。',
    '采购账单日期、报销提交日、开销登记日和付款日不能直接证明成本属于哪一批发货。',
    '工资有结算期间，但净实发包含预发抵扣影响，不能直接当作完整工资成本，也不能擅自按客户或跨月分摊。',
    '垫款登记、归还、备用金拨付和预支属于资金安排，不在这里再加一笔经营成本；原业务单据只展示一次。',
]


async def cost_references(db, warehouse_ids, start, end, currency=None):
    """按已有单据的参考日期列出待归集线索；这些日期不是已确认成本归期。"""
    rows=[]
    def add(source, row, when, value, cur, status, basis, link, **extra):
        if currency and cur != currency:return
        rows.append({'source':source,'source_id':row.id,'warehouse_id':row.warehouse_id,
            'reference_date':str(when) if when else None,'nominal_amount':float(money(value)),
            'currency':cur,'status':status,'date_basis':basis,'cost_period_confirmed':False,
            'cost_amount':None,'source_link':link,**extra})
    p=PayrollRecord
    payroll=(await db.execute(select(p).where(p.warehouse_id.in_(warehouse_ids),p.status=='confirmed',p.voided.is_not(True),
        or_(and_(p.period>=start.strftime('%Y-%m'),p.period<=end.strftime('%Y-%m')),
            and_(p.settle_start_date<=end,p.settle_end_date>=start))))).scalars().all()
    for r in payroll:
        when=r.settle_end_date
        if not when:
            try:when=date.fromisoformat(r.period+'-01')
            except ValueError:when=None
        add('payroll',r,when,r.net_pay,'THB','confirmed',
            '结算期间线索，金额为原净实发，不是已归集经营成本；不自动跨月分摊','/payroll',
            salary_period=r.period,settle_start_date=str(r.settle_start_date) if r.settle_start_date else None,
            settle_end_date=str(r.settle_end_date) if r.settle_end_date else None,
            advance_deduction=r.advance_deduction, cash_advance_id=r.cash_advance_id)
    reimbursement=Reimbursement
    reimbursements=(await db.execute(select(reimbursement).where(reimbursement.warehouse_id.in_(warehouse_ids),
        reimbursement.status.in_(['approved','partially_approved','paid','fund_linked']),day(db,reimbursement.submit_date)>=start,day(db,reimbursement.submit_date)<=end))).scalars().all()
    for r in reimbursements:add('reimbursement',r,r.submit_date.date(),r.total_amount,r.currency or 'THB',r.status,
        '报销提交日期，金额为原申报额；部分通过不表示全额成本已确认','/reimbursement',funding_source=r.funding_source,cash_advance_id=r.cash_advance_id)
    b=PayableBill
    bills=(await db.execute(select(b).where(b.warehouse_id.in_(warehouse_ids),b.status!='voided',
        day(db,b.bill_date)>=start,day(db,b.bill_date)<=end))).scalars().all()
    for r in bills:add('payable',r,r.bill_date.date(),r.amount,r.currency or 'THB',r.status,
        '账单日期，仅作采购单据线索，非成本所属日或实际付款日','/payable',ref_no=r.bill_number)
    a=ExpenseApproval
    approvals=(await db.execute(select(a).where(a.warehouse_id.in_(warehouse_ids),a.status.in_(['approved','paid','completed']),
        a.expense_date>=start,a.expense_date<=end))).scalars().all()
    for r in approvals:add('expense_approval',r,r.expense_date,r.amount,r.currency or 'THB',r.status,
        '费用登记日期，审批或付款状态不等于成本期间已归集','/expense-approvals',funding_source=r.fund_source)
    item,fund=ExpenseFundItem,ExpenseFund
    items=(await db.execute(select(item,fund.warehouse_id).join(fund,fund.id==item.fund_id).where(
        fund.warehouse_id.in_(warehouse_ids),item.review_status=='approved',item.not_voided(),
        day(db,item.expense_date)>=start,day(db,item.expense_date)<=end,
        ~select(a.id).where(a.fund_item_id==item.id,a.warehouse_id==fund.warehouse_id).exists(),
        ~select(Reimbursement.id).where(Reimbursement.fund_item_id==item.id,Reimbursement.warehouse_id==fund.warehouse_id).exists(),
        ~select(EmployeeAdvance.id).where(EmployeeAdvance.fund_item_id==item.id,EmployeeAdvance.warehouse_id==fund.warehouse_id).exists()))).all()
    for row,wid in items:
        # The warehouse comes from the validated parent, never an assumed employee/account name.
        rows.append({'source':'fund_item','source_id':row.id,'warehouse_id':wid,'reference_date':str(row.expense_date.date()),
            'nominal_amount':float(money(row.amount)),'currency':row.currency or 'THB','status':row.review_status,
            'date_basis':'备用金开销登记日，不再叠加拨付金额，也不自动认作成本期间',
            'cost_period_confirmed':False,'cost_amount':None,'source_link':'/expense-fund','fund_id':row.fund_id})
    e,c=ExpenseRecord,IncomeExpenseCategory
    manual=(await db.execute(select(e,c.name).join(c,and_(c.id==e.category_id,c.warehouse_id==e.warehouse_id)).where(
        e.warehouse_id.in_(warehouse_ids),day(db,e.expense_date)>=start,day(db,e.expense_date)<=end,
        ~select(p.id).where(p.expense_record_id==e.id,p.warehouse_id==e.warehouse_id).exists(),
        ~select(Reimbursement.id).where(Reimbursement.expense_record_id==e.id,Reimbursement.warehouse_id==e.warehouse_id).exists(),
        ~select(a.id).where(a.expense_record_id==e.id,a.warehouse_id==e.warehouse_id).exists(),
        ~select(ExpenseFundDisbursement.id).where(ExpenseFundDisbursement.expense_record_id==e.id,ExpenseFundDisbursement.warehouse_id==e.warehouse_id).exists(),
        ~select(EmployeeAdvance.id).where(EmployeeAdvance.expense_record_id==e.id,EmployeeAdvance.warehouse_id==e.warehouse_id).exists()))).all()
    for r,name in manual:add('manual_expense',r,r.expense_date.date(),r.amount,r.currency or 'THB','period_unverified',
        '手工支出日期，仅证明支出登记，缺经营成本归期及完整性确认','/operating',category_name=name)
    return sorted([r for r in rows if not currency or r['currency']==currency],key=lambda r:(r['reference_date'] or '',r['source'],r['source_id']),reverse=True)


async def report(db, warehouse_ids, start, end, *, customer_id=None, currency=None, shipment_page=1, cost_page=1, page_size=20):
    customers=(await db.execute(select(Customer).where(Customer.warehouse_id.in_(warehouse_ids)).order_by(Customer.id))).scalars().all()
    if customer_id is not None and customer_id not in {c.id for c in customers}:raise HTTPException(403,'无权查看所选客户')
    ids=[customer_id] if customer_id is not None else [c.id for c in customers]
    balances=await positions(db,warehouse_ids,ids,start_date=start,end_date=end,sources=True)
    reviews=await legacy_review(db,warehouse_ids,ids)
    names={c.id:c.company_name for c in customers}
    all_events=[{**e,'customer_id':cid,'customer_name':names.get(cid,'')} for cid,groups in balances.items() for cur,p in groups.items()
        if not currency or cur==currency for e in p['events']]
    shipments=sorted([e for e in all_events if e['source']=='shipment'],key=lambda e:(e['date'],e['source_id']),reverse=True)
    refs=await cost_references(db,warehouse_ids,start,end,currency) if customer_id is None else []
    wallet_rows=await totals(db,warehouse_ids,start,end) if customer_id is None else []
    wallet=grouped_totals([r for r in wallet_rows if not currency or r[0]==currency]) if customer_id is None else None
    currencies=sorted({currency} if currency else {'THB','CNY'}|{cur for groups in balances.values() for cur in groups}|{r['currency'] for r in refs})
    blocks=[]
    for cur in currencies:
        events=[e for e in all_events if e['currency']==cur]
        own_ship=[e for e in events if e['source']=='shipment'];received=[e for e in events if e['source']=='incoming']
        groups=[g[cur] for g in balances.values() if cur in g]
        daily={}
        for e in events:
            d=daily.setdefault(e['date'],{'date':e['date'],'shipment_income':money(0),'actual_receipts':money(0)})
            d['shipment_income' if e['source']=='shipment' else 'actual_receipts']+=money(e['amount'])
        blocks.append({'currency':cur,'shipment_income':float(sum((money(e['amount']) for e in own_ship),money(0))),
            'shipment_records':len(own_ship),'order_count':sum(e['order_count'] or 0 for e in own_ship),
            'unknown_order_count_records':sum(e['order_count'] is None for e in own_ship),
            'actual_receipts':float(sum((money(e['amount']) for e in received),money(0))),
            'receivable_asof':float(sum((money(p['outstanding']) for p in groups),money(0))),
            'prepayment_asof':float(sum((money(p['prepayment']) for p in groups),money(0))),
            'attributed_cost_total':None,'operating_profit':None,'profit_computable':False,
            'profit_reason':'经营成本归期和完整性未确认；不能把付款或缺失记录当作完整成本。',
            'daily':[{**r,'shipment_income':float(r['shipment_income']),'actual_receipts':float(r['actual_receipts'])} for _,r in sorted(daily.items())]})
    def page(rows,n):return {'data':rows[(n-1)*page_size:n*page_size],'total':len(rows),'page':n,'page_size':page_size}
    return {'start_date':str(start),'end_date':str(end),'warehouse_ids':warehouse_ids,'customer_id':customer_id,
        'currency':currency,'currencies':blocks,'shipments':page(shipments,shipment_page),'cost_references':page(refs,cost_page),
        'customer_options':[{'id':c.id,'warehouse_id':c.warehouse_id,'name':c.company_name} for c in customers],
        'review_items':[{'customer_id':cid,**r} for cid,items in reviews.items() for r in items if not currency or r.get('currency')==currency],
        'wallet':wallet,'wallet_scope_note':'公司钱包按实际收付；不与发货金额相减计算利润。' if wallet is not None else '成本及支出未建立客户分摊，本次客户筛选不展示仓库钱包合计；实际到账按明确客户来源显示。',
        'cost_gaps':GAPS+(['成本单据没有可靠客户归属，未按客户名字或收入比例分摊。'] if customer_id is not None else []),
        'basis':'发货金额按有效发货业务日期统计；实收复用唯一到账来源；应收预收截至所选结束日；成本未归期，利润暂不可计算。',
        'reference_basis':'待归集单据按各自参考日期列出，工资按结算期相交筛选；不代表全部已发生成本，金额不可相加当作成本。',
        'cost_completeness_confirmed':False}
