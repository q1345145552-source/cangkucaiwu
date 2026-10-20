"""Legacy money-page reads over the existing company wallet; no parallel ledger or writes."""
from sqlalchemy import Integer, and_, case, cast, func, literal, or_, select

from app.models.customer import Customer
from app.models.credit import CreditCustomer, CreditRepayment
from app.models.income_expense import IncomeRecord, ExpenseRecord, IncomeExpenseCategory
from app.models.recharge import IncomingFlow, RechargeDeclaration, ReconciliationResult
from app.models.supplier import Supplier
from app.services.cost_funds_debt import cost_query, money
from app.services.wallet import flow_query, grouped_totals
from app.services.customer_receivables import receipt_identity_query

BASIS = '公司钱包实际收付；不含内部转账，到账只计一次，备用金拨付及垫款归还按原钱包规则统计'
SOURCE_LINKS = {'incoming':'/incoming', 'payable':'/payable', 'cash_advance_repayment':'/cash-advances',
    'expense_fund':'/expense-fund', 'reimbursement':'/reimbursement'}


def record_period(start_date=None,end_date=None,*,month=None,year=None):
    from app.services.cost_funds_debt import dates
    return dates(start_date,end_date,month=month,year=year)


def record_query(db, warehouse_ids, kind):
    if kind == 'income':
        q = flow_query(db, warehouse_ids)
        i, incoming = IncomeRecord, IncomingFlow
        identity = receipt_identity_query()
        receipt_customer = select(identity.c.customer_id).where(identity.c.flow_id == q.c.id,
            identity.c.warehouse_id == q.c.warehouse_id).correlate(q).scalar_subquery()
        customer = func.coalesce(i.customer_id,case((q.c.source == 'incoming',receipt_customer)))
        rows = select(q, q.c.id.label('source_id'), i.voucher,
            func.coalesce(i.income_date,incoming.received_date).label('record_timestamp'),
            customer.label('customer_id'), cast(literal(None),Integer).label('supplier_id'),
            (q.c.source != 'manual').label('is_read_only'),
            case((q.c.source == 'incoming', '到账收入'), else_=q.c.category_name).label('record_category'),
            func.coalesce(Customer.company_name, incoming.payer_name, '').label('customer_name'),
            literal('').label('supplier_name')).outerjoin(i,and_(q.c.source == 'manual', i.id == q.c.id,
                i.warehouse_id == q.c.warehouse_id)).outerjoin(incoming,and_(q.c.source == 'incoming',
                incoming.id == q.c.id,incoming.warehouse_id == q.c.warehouse_id)).outerjoin(Customer,
                and_(Customer.id == customer, Customer.warehouse_id == q.c.warehouse_id)).where(
            q.c.type == 'income',q.c.status == 'active',q.c.is_internal_transfer.is_(False)).subquery('money_income')
    else:
        q = cost_query(db, warehouse_ids)
        rows = select(q, cast(literal(None),Integer).label('customer_id'), ExpenseRecord.supplier_id,
            literal('').label('customer_name'), func.coalesce(Supplier.name,'').label('supplier_name'),
            q.c.category_name.label('record_category')).outerjoin(ExpenseRecord,and_(q.c.source == 'expense',
                q.c.id == ExpenseRecord.id, ExpenseRecord.warehouse_id == q.c.warehouse_id)).outerjoin(Supplier,
                and_(Supplier.id == ExpenseRecord.supplier_id,Supplier.warehouse_id == q.c.warehouse_id)).subquery('money_expense')
    c = IncomeExpenseCategory
    # Existing category IDs only apply to their own warehouse; uncategorised business flows stay visible.
    return select(rows,func.coalesce(c.category_group,'operating').label('category_group'),
        case((rows.c.record_category.in_(['其他支出','未分类']),func.coalesce(c.name,rows.c.record_category)),
            else_=rows.c.record_category).label('display_category')).outerjoin(c,and_(
                c.id == rows.c.category_id,c.warehouse_id == rows.c.warehouse_id)).subquery('money_records_'+kind)


def record_filters(q,start,end,*,account_id=None,customer_id=None,supplier_id=None,category_id=None,
                   category_group=None,currency=None,source=None,search=None,cost_category=None):
    filters=[q.c.date >= start,q.c.date <= end]
    if account_id is not None: filters.append(q.c.account_id == account_id)
    if customer_id is not None: filters.append(q.c.customer_id == customer_id)
    if supplier_id is not None: filters.append(q.c.supplier_id == supplier_id)
    if category_id is not None:
        c=IncomeExpenseCategory
        name=select(case((c.name == '采购','手工采购'),(c.name == '工资','员工工资'),else_=c.name)).where(
            c.id == category_id,c.warehouse_id == q.c.warehouse_id).scalar_subquery()
        filters.append(or_(q.c.category_id == category_id,q.c.display_category == name))
    if category_group: filters.append(q.c.category_group == category_group)
    if currency: filters.append(q.c.currency == currency)
    if source: filters.append((q.c.wallet_source if 'wallet_source' in q.c else q.c.source) == source)
    if cost_category: filters.append(q.c.display_category == cost_category)
    if search:
        term='%'+search+'%'
        filters.append(or_(*[q.c[k].ilike(term) for k in ('remark','customer_name','supplier_name',
            'source_label','ref_no','account_name' if 'account_name' in q.c else 'display_category')]))
    return filters


def serialize(row,kind):
    r=dict(row)
    source=r.get('wallet_source',r['source'])
    r.update(id=r['id'] if r['source'] in ('manual','expense') else f"{source}-{r['id']}",
        amount=float(money(r['amount'])),date=str(r['date']),category_name=r['display_category'],
        is_read_only=bool(r['is_read_only']),source_link=SOURCE_LINKS.get(source,''))
    r[kind+'_date']=r['record_timestamp'].isoformat() if kind == 'income' and r.get('record_timestamp') else r['date']
    return r


async def records(db,warehouse_ids,kind,start,end,*,page=1,page_size=20,export=False,**options):
    q=record_query(db,warehouse_ids,kind);filters=record_filters(q,start,end,**options)
    total=(await db.execute(select(func.count()).select_from(q).where(*filters))).scalar_one()
    amounts={c:float(money(n)) for c,n in (await db.execute(select(q.c.currency,func.sum(q.c.amount)).where(
        *filters).group_by(q.c.currency))).all()}
    statement=select(q).where(*filters).order_by(q.c.date.desc(),q.c.source,q.c.source_id.desc())
    if not export: statement=statement.offset((page-1)*page_size).limit(page_size)
    data=[serialize(r,kind) for r in (await db.execute(statement)).mappings()]
    return {'data':data,'total':total,'page':page,'page_size':page_size,'totals_by_currency':amounts,
        'scope':'company_wallet','cost_basis':BASIS}


async def summary(db,warehouse_ids,start,end,**options):
    totals=[]
    for kind in ('income','expense'):
        q=record_query(db,warehouse_ids,kind);filters=record_filters(q,start,end,**options)
        totals += [(c,kind,n) for c,n in (await db.execute(select(q.c.currency,func.sum(q.c.amount)).where(
            *filters).group_by(q.c.currency))).all()]
    return {'start_date':str(start),'end_date':str(end),**grouped_totals(totals),'scope':'company_wallet','basis':BASIS}
