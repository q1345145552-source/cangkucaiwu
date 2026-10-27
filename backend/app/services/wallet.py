"""唯一钱包收付投影：按实际收付日、仓库、币种汇总，同笔资金只计一次。"""
from datetime import date
from decimal import Decimal, InvalidOperation
from fastapi import HTTPException
from sqlalchemy import Date, Integer, Numeric, String, and_, case, cast, func, literal, or_, select, type_coerce, union_all
from app.models.payroll import PayrollRecord
from app.models import (IncomeRecord, ExpenseRecord, IncomeExpenseCategory, IncomingFlow,
    Reimbursement, ReimbursementPayment, CashAdvance, CashAdvanceRepayment,
    EmployeeAdvance, ExpenseFund, ExpenseFundDisbursement, ExpenseApproval,
    PayableBill, PayablePayment, AccountTransfer, PaymentAccount)


def money(value):
    return Decimal(str(value or 0)).quantize(Decimal('0.01'))


def positive_money(value):
    try:
        n = Decimal(str(value))
        if not n.is_finite() or n <= 0 or n != money(n) or n >= Decimal('1000000000000'):
            raise ValueError
        return n
    except (ValueError, InvalidOperation):
        raise HTTPException(400, '金额必须大于0，且最多两位小数')


def day(db, column):
    if db.bind.dialect.name == 'postgresql' and getattr(column.type, 'timezone', False):
        return type_coerce(func.date(func.timezone('Asia/Bangkok', column)), Date)
    return type_coerce(func.date(column), Date)


def procurement_rows(db, warehouse_ids):
    p, b = PayablePayment, PayableBill
    recorded = select(p.id.label('payment_id'), b.id.label('bill_id'), b.warehouse_id,
        b.bill_number, b.supplier_id, day(db, p.paid_at).label('payment_date'),
        p.amount.label('amount'), p.currency, p.account_id).join(b, and_(b.id == p.bill_id,
        b.warehouse_id == p.warehouse_id)).where(p.warehouse_id.in_(warehouse_ids))
    # 旧累计额只能保留最后已知日期；不伪造逐笔历史，第一次新付款前锁定快照。
    old_amount = func.coalesce(b.legacy_paid_amount, b.paid_amount, 0)
    old_date = case((b.legacy_paid_amount.is_not(None), b.legacy_paid_at), else_=b.paid_at)
    legacy = select((-b.id).label('payment_id'), b.id.label('bill_id'), b.warehouse_id,
        b.bill_number, b.supplier_id, day(db, old_date).label('payment_date'),
        cast(old_amount, Numeric(18, 2)).label('amount'), func.coalesce(b.currency, 'THB'), literal(None)).where(
        b.warehouse_id.in_(warehouse_ids), old_amount > 0)
    # 作废只免除未付余额，已经付出去的款项仍然保留。
    return union_all(recorded, legacy).subquery('procurement_payments')


def flow_query(db, warehouse_ids):
    def row(model, date_col, value, currency_col, kind, source, label, *, account=None,
            status=None, reference='', remark=None, category=None, category_id=None,
            internal=False, cash_advance_id=None):
        def col(v, default=None): return v if v is not None else literal(default)
        return select(model.id.label('id'), model.warehouse_id.label('warehouse_id'),
            day(db, date_col).label('date'), cast(value, Numeric(18, 2)).label('amount'),
            func.coalesce(currency_col, 'THB').label('currency'), literal(kind).label('type'),
            literal(source).label('source'), literal(label).label('source_label'),
            cast(col(account), Integer).label('account_id'), col(status, 'active').label('status'),
            (literal(reference) + cast(model.id, String)).label('ref_no'), col(remark, '').label('remark'),
            col(category, '其他支出').label('category_name'), cast(col(category_id), Integer).label('category_id'),
            literal(internal).label('is_internal_transfer'), cast(col(cash_advance_id), Integer).label('cash_advance_id'),
        ).where(model.warehouse_id.in_(warehouse_ids))
    i, e, c = IncomeRecord, ExpenseRecord, IncomeExpenseCategory
    incomes = row(i, i.income_date, i.amount, i.currency, 'income', 'manual', '手工收入',
        account=i.account_id, reference='IN-', remark=i.remark, category_id=i.category_id)
    p, r, a, d = PayrollRecord, Reimbursement, EmployeeAdvance, ExpenseFundDisbursement
    expenses = row(e, e.expense_date, e.amount, e.currency, 'expense', 'manual', '公司账户支出',
        account=e.account_id, reference='EX-', remark=e.remark, category_id=e.category_id,
        category=case((c.name == '采购', '手工采购'), (c.name == '工资', '员工工资'), else_=c.name),
    ).join(c, and_(c.id == e.category_id, c.warehouse_id == e.warehouse_id)).where(
        ~select(r.id).where(r.expense_record_id == e.id, r.warehouse_id == e.warehouse_id).exists(),
        ~select(p.id).where(p.expense_record_id == e.id, p.warehouse_id == e.warehouse_id,
            or_(p.cash_advance_id.is_not(None), p.disbursed.is_not(True), p.voided.is_(True))).exists(),
        ~select(a.id).where(a.expense_record_id == e.id, a.warehouse_id == e.warehouse_id,
            or_(a.source == 'fund', a.funding_source.in_(['cash_advance', 'expense_fund']),
                a.approval_status != 'approved', ~a.not_voided())).exists(),
        ~select(d.id).where(d.expense_record_id == e.id, d.warehouse_id == e.warehouse_id).exists(),
        # 旧费用审批无关联编号时，仅按原程序写入的精确编号前缀排除备用金重复支出。
        ~select(ExpenseApproval.id).where(ExpenseApproval.warehouse_id == e.warehouse_id,
            ExpenseApproval.fund_source == 'fund', or_(ExpenseApproval.expense_record_id == e.id,
            e.remark == literal('[费用审批#') + cast(ExpenseApproval.id, String) + literal('] ') + ExpenseApproval.purpose)).exists())
    rp = ReimbursementPayment
    reimbursements = row(rp, rp.paid_at, rp.amount, rp.currency, 'expense', 'reimbursement', '报销付款',
        account=rp.payment_account_id, status=rp.status, reference='RB-P-', category=literal('报销'),
        remark=case((rp.status == 'revoked', literal('报销付款 #') + cast(rp.reimbursement_id, String) + literal('；已冲销：') + func.coalesce(rp.revoke_reason, '')), else_=literal('报销付款 #') + cast(rp.reimbursement_id, String))).where(rp.funding_source == 'company_account')
    cr, ca = CashAdvanceRepayment, CashAdvance
    returns = row(cr, cr.repayment_date, cr.amount, cr.currency, 'expense', 'cash_advance_repayment', '垫款归还',
        account=cr.account_id, status=cr.status, reference='CAR-', cash_advance_id=cr.cash_advance_id,
        category=case((ca.purpose == 'salary', '员工工资'), (ca.purpose == 'purchase', '采购'),
            (ca.purpose == 'expense', '费用'), else_='其他支出'),
        remark=case((cr.status == 'revoked', literal('归还垫款 #') + cast(cr.cash_advance_id, String) + literal('；已冲销：') + func.coalesce(cr.revoke_reason, '')), else_=literal('归还垫款 #') + cast(cr.cash_advance_id, String))).join(ca, and_(ca.id == cr.cash_advance_id,
            ca.warehouse_id == cr.warehouse_id))
    incoming = row(IncomingFlow, IncomingFlow.received_date, IncomingFlow.amount, IncomingFlow.currency,
        'income', 'incoming', '到账流水', account=IncomingFlow.account_id, reference='FL-', remark=IncomingFlow.remark)
    legacy_reimb = row(r, r.paid_at, r.total_amount, r.currency, 'expense', 'reimbursement', '历史报销（未指定账户）',
        reference='RB-', category=literal('报销')).where(r.status == 'paid', r.funding_source.is_(None),
        or_(r.is_fund_linked.is_(None), r.is_fund_linked != '1'))
    paid = procurement_rows(db, warehouse_ids)
    purchases = select(paid.c.payment_id.label('id'), paid.c.warehouse_id, paid.c.payment_date.label('date'),
        paid.c.amount, paid.c.currency, literal('expense'), literal('payable'), literal('采购付款'),
        paid.c.account_id, literal('active'), literal('PB-') + cast(paid.c.bill_id, String),
        paid.c.bill_number, literal('采购'), literal(None), literal(False), literal(None))
    already = select(func.coalesce(func.sum(d.amount), 0)).where(d.fund_id == ExpenseFund.id).scalar_subquery()
    legacy_fund = row(ExpenseFund, ExpenseFund.receive_date, ExpenseFund.amount - already, ExpenseFund.currency,
        'expense', 'expense_fund', '历史备用金拨付（未指定账户）', reference='EF-', category=literal('备用金拨付'),
        remark=ExpenseFund.purpose).where(ExpenseFund.amount - already > 0)
    disbursements = row(d, d.disbursed_date, d.amount, d.currency, 'expense', 'expense_fund', '备用金拨付',
        account=d.payment_account_id, reference='EFD-', category=literal('备用金拨付'), remark=d.remark)
    t = AccountTransfer
    transfers = [row(t, t.transfer_date, t.amount, t.currency, kind, 'transfer', label, account=account,
        reference=ref, remark=t.remark, internal=True) for kind, label, account, ref in (
            ('income', '内部转入', t.to_account_id, 'TR-IN-'), ('expense', '内部转出', t.from_account_id, 'TR-OUT-'))]
    raw = union_all(incomes, expenses, reimbursements, returns, incoming, legacy_reimb, purchases,
        legacy_fund, disbursements, *transfers).subquery('raw_wallet_flows')
    valid = and_(PaymentAccount.id.is_not(None), PaymentAccount.warehouse_id == raw.c.warehouse_id,
        func.coalesce(PaymentAccount.currency, 'THB') == raw.c.currency)
    columns = [case((valid, col), else_=None).label('account_id') if col.name == 'account_id' else col for col in raw.c]
    return select(*columns, case((valid, PaymentAccount.account_name), else_='未指定账户').label('account_name'),
        literal(False).label('is_non_cost_flow')).outerjoin(PaymentAccount,
        PaymentAccount.id == raw.c.account_id).subquery('company_flows')


async def totals(db, warehouse_ids, start, end):
    q = flow_query(db, warehouse_ids)
    return (await db.execute(select(q.c.currency, q.c.type, func.sum(q.c.amount)).where(
        q.c.date >= start, q.c.date <= end, q.c.status == 'active', q.c.is_internal_transfer.is_(False)
    ).group_by(q.c.currency, q.c.type))).all()


async def _checked_account(db, warehouse_id, account_id, currency, *, lock):
    if not account_id: raise HTTPException(400, '请选择付款或收款账户')
    query = select(PaymentAccount).where(PaymentAccount.id == account_id,
        PaymentAccount.warehouse_id == warehouse_id).order_by(PaymentAccount.id)
    if lock: query = query.with_for_update()
    account = (await db.execute(query.execution_options(populate_existing=True))).scalar_one_or_none()
    if account is None: raise HTTPException(400, '账户不存在或不属于当前仓库')
    if account.status not in (None, 'active'): raise HTTPException(400, '账户已停用')
    if (account.currency or 'THB') != currency: raise HTTPException(400, '账户币种不一致')
    return account


async def lock_account(db, warehouse_id, account_id, currency):
    return await _checked_account(db, warehouse_id, account_id, currency, lock=True)


async def read_account(db, warehouse_id, account_id, currency):
    """Same account eligibility checks, without write locks for read-only previews."""
    return await _checked_account(db, warehouse_id, account_id, currency, lock=False)


def grouped_totals(rows):
    inc, exp = {}, {}
    for cur, kind, value in rows:
        (inc if kind == 'income' else exp)[cur] = float(money(value))
    currencies = set(inc) | set(exp)
    single = next(iter(currencies)) if len(currencies) == 1 else None
    ti, te = (inc.get(single, 0), exp.get(single, 0)) if single else ((0, 0) if not currencies else (None, None))
    return {'income_by_currency': inc, 'expense_by_currency': exp,
        'net_by_currency': {c: float(money(inc.get(c, 0)) - money(exp.get(c, 0))) for c in currencies},
        'total_income': ti, 'total_expense': te, 'net': ti - te if ti is not None else None}
