"""成本/公司资金/垫款欠款的只读投影。虚拟明细不写入任何业务表。"""
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import Date, Numeric, String, and_, case, cast, func, literal, or_, select, type_coerce, union_all

from app.core.timezone import thai_today
from app.models.cash_advance import CashAdvance
from app.models.cash_advance_repayment import CashAdvanceRepayment
from app.models.customer import PaymentAccount
from app.models.employee_advance import EmployeeAdvance
from app.models.expense_fund import ExpenseFund, ExpenseFundItem, ExpenseFundDisbursement
from app.services.fund_disbursement import cost_record_filter
from app.services.procurement_payments import procurement_payment_rows
from app.models.income_expense import ExpenseRecord, IncomeExpenseCategory, IncomeRecord
from app.models.payable import PayableBill
from app.models.payroll import PayrollRecord
from app.models.recharge import IncomingFlow
from app.models.reimbursement import Reimbursement
from app.models.reimbursement_payment import ReimbursementPayment

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value):
    return Decimal(str(value or 0)).quantize(CENT)


def dates(start=None, end=None):
    today = thai_today()
    try:
        start = date.fromisoformat(str(start)) if start else today.replace(day=1)
        end = date.fromisoformat(str(end)) if end else today
    except ValueError:
        raise HTTPException(400, "日期格式错误，应为 YYYY-MM-DD")
    if start > end:
        raise HTTPException(400, "开始日期不能晚于结束日期")
    return start, end


def day(db, column):
    # 有时区的付款时间按仓库业务时区取日；业务日期/无时区作息原样取日。
    if db.bind.dialect.name == "postgresql" and getattr(column.type, "timezone", False):
        return type_coerce(func.date(func.timezone("Asia/Bangkok", column)), Date)
    return type_coerce(func.date(column), Date)


def amount(column):
    return cast(column, Numeric(18, 2))


def currency(column):
    return func.coalesce(column, "THB")


def cost_query(db, warehouse_ids):
    e, c, p, r, a, d = ExpenseRecord, IncomeExpenseCategory, PayrollRecord, Reimbursement, EmployeeAdvance, ExpenseFundDisbursement
    category = case((or_(c.name.in_(["员工工资", "工资"]), p.id.is_not(None)), "员工工资"),
        (c.name == "采购", "手工采购"), else_=c.name)
    source = case((or_(r.cash_advance_id.is_not(None), p.cash_advance_id.is_not(None)), "cash_advance"),
        (a.source == "fund", "expense_fund"),
        (e.account_id.is_not(None), "company_account"), else_="unknown")
    records = select(
        e.id.label("id"), literal("expense").label("source"), e.id.label("source_id"),
        e.warehouse_id.label("warehouse_id"), day(db, e.expense_date).label("date"),
        e.category_id.label("category_id"), category.label("category_name"),
        amount(e.amount).label("amount"), currency(e.currency).label("currency"),
        e.account_id.label("account_id"), e.remark.label("remark"), e.voucher.label("voucher"),
        source.label("funding_source"), func.coalesce(r.cash_advance_id, p.cash_advance_id).label("cash_advance_id"),
        r.id.label("reimbursement_id"), p.id.label("payroll_record_id"), or_(a.id.is_not(None), d.id.is_not(None)).label("is_read_only"),
        a.id.label("employee_advance_id"), a.employee_id.label("employee_id"),
        d.id.label("fund_disbursement_id"), d.fund_id.label("fund_id"),
    ).join(c, and_(c.id == e.category_id, c.warehouse_id == e.warehouse_id)).outerjoin(
        p, and_(p.expense_record_id == e.id, p.warehouse_id == e.warehouse_id),
    ).outerjoin(r, and_(r.expense_record_id == e.id, r.warehouse_id == e.warehouse_id)).outerjoin(
        a, and_(a.expense_record_id == e.id, a.warehouse_id == e.warehouse_id)).outerjoin(
        d, and_(d.expense_record_id == e.id, d.warehouse_id == e.warehouse_id)).where(
        e.warehouse_id.in_(warehouse_ids), c.type == "expense", c.category_group == "operating", cost_record_filter(e))
    f, i = ExpenseFund, ExpenseFundItem
    funds = select(
        (-i.id).label("id"), literal("fund_item").label("source"), i.id.label("source_id"), f.warehouse_id,
        day(db, i.expense_date), literal(None), literal("备用金开销"), amount(i.amount), currency(i.currency),
        literal(None), i.description, i.receipt, literal("expense_fund"), literal(None),
        literal(None), literal(None), literal(True), literal(None), literal(None), literal(None), literal(None),
    ).join(f, f.id == i.fund_id).where(f.warehouse_id.in_(warehouse_ids), i.review_status == "approved", i.cost_record_only.is_(False),
        # 新预支只在审批通过后由 ExpenseRecord 计一次；旧备用金记录原样保留。
        ~select(a.id).where(a.fund_item_id == i.id, a.expense_tracking_enabled.is_(True),
            a.warehouse_id == f.warehouse_id).exists())
    paid = procurement_payment_rows(db, warehouse_ids)
    purchases = select(
        paid.c.bill_id, literal("payable"), paid.c.bill_id, paid.c.warehouse_id,
        paid.c.payment_date, literal(None), literal("采购"), paid.c.amount, paid.c.currency,
        literal(None), paid.c.bill_number, literal(None), literal("company_account"), literal(None),
        literal(None), literal(None), literal(True), literal(None), literal(None), literal(None), literal(None),
    )
    return union_all(records, funds, purchases).subquery("cost_rows")


def cost_filters(q, start, end, *, category_id=None, cost_category=None, account_id=None, currency_code=None):
    filters = [q.c.date >= start, q.c.date <= end]
    if category_id: filters.append(q.c.category_id == category_id)
    if cost_category: filters.append(q.c.category_name == cost_category)
    if account_id: filters.append(q.c.account_id == account_id)
    if currency_code: filters.append(q.c.currency == currency_code)
    return filters


async def cost_totals(db, q, filters):
    return {c: float(money(a)) for c, a in (await db.execute(select(
        q.c.currency, func.sum(q.c.amount)).where(*filters).group_by(q.c.currency))).all()}


async def cost_list(db, warehouse_ids, start, end, *, page=1, page_size=25, category_id=None, cost_category=None, account_id=None, currency_code=None):
    q = cost_query(db, warehouse_ids)
    filters = cost_filters(q, start, end, category_id=category_id, cost_category=cost_category, account_id=account_id, currency_code=currency_code)
    total = (await db.execute(select(func.count()).select_from(q).where(*filters))).scalar_one()
    rows = (await db.execute(select(q).where(*filters).order_by(q.c.date.desc(), q.c.source, q.c.source_id.desc())
        .offset((page - 1) * page_size).limit(page_size))).mappings().all()
    accounts = {a.id: a.account_name for a in (await db.execute(select(PaymentAccount).where(PaymentAccount.warehouse_id.in_(warehouse_ids)))).scalars()}
    data = [{**dict(r), "id": f"payable-{r['source_id']}" if r["source"] == "payable" else r["id"],
        "amount": float(r["amount"]), "expense_date": str(r["date"]),
        "date": str(r["date"]), "account_name": accounts.get(r["account_id"], "付款账户未记录" if r["source"] == "payable" else "备用金" if r["source"] == "fund_item" else "不使用公司账户"),
        "is_read_only": bool(r["is_read_only"])} for r in rows]
    return {"data": data, "total": total, "page": page, "page_size": page_size,
        "totals_by_currency": await cost_totals(db, q, filters), "cost_basis": "运营支出、应付实付及保留的历史备用金开销；手工采购单列，新开销只记台账"}


def flow_query(db, warehouse_ids):
    """公司真实收付视图：申报不作到账、备用金开销不作公司二次付款。"""
    def row(model, date_col, value, currency_col, kind, source, label, *, account=None, account_name=None,
            status=None, non_cost=False, reference=None, remark=None):
        return select(model.id.label("id"), day(db, date_col).label("date"), amount(value).label("amount"),
            currency(currency_col).label("currency"), literal(kind).label("type"), literal(source).label("source"),
            literal(label).label("source_label"), (account if account is not None else literal(None)).label("account_id"),
            (account_name if account_name is not None else literal(None)).label("account_name"),
            (status if status is not None else literal("active")).label("status"), literal(non_cost).label("is_non_cost_flow"),
            (literal(reference) + cast(model.id, String)).label("ref_no"),
            (remark if remark is not None else literal("")).label("remark"),
        ).where(model.warehouse_id.in_(warehouse_ids))
    ir, er, r, p = IncomeRecord, ExpenseRecord, Reimbursement, PayrollRecord
    incomes = row(ir, ir.income_date, ir.amount, ir.currency, "income", "manual", "手工收入",
        account=ir.account_id, reference="IN-", remark=ir.remark)
    expenses = row(er, er.expense_date, er.amount, er.currency, "expense", "manual", "公司账户支出",
        account=er.account_id, reference="EX-", remark=er.remark).outerjoin(
        r, and_(r.expense_record_id == er.id, r.warehouse_id == er.warehouse_id),
    ).outerjoin(p, and_(p.expense_record_id == er.id, p.warehouse_id == er.warehouse_id)).where(
        r.id.is_(None), or_(p.id.is_(None), and_(p.cash_advance_id.is_(None), p.disbursed.is_(True), p.voided.is_not(True))),
        ~select(EmployeeAdvance.id).where(EmployeeAdvance.expense_record_id == er.id,
            EmployeeAdvance.source == "fund").exists(),
        ~select(ExpenseFundDisbursement.id).where(ExpenseFundDisbursement.expense_record_id == er.id).exists())
    rp, cr = ReimbursementPayment, CashAdvanceRepayment
    reimbursements = row(rp, rp.paid_at, rp.amount, rp.currency, "expense", "reimbursement", "报销付款",
        account=rp.payment_account_id, account_name=rp.account_name, status=rp.status, reference="RB-P-",
        remark=literal("报销付款 #") + cast(rp.reimbursement_id, String)).where(rp.funding_source == "company_account")
    returns = row(cr, cr.repayment_date, cr.amount, cr.currency, "expense", "cash_advance_repayment", "垫款归还",
        account=cr.account_id, account_name=cr.account_name, status=cr.status, non_cost=True, reference="CAR-",
        remark=literal("归还垫款 #") + cast(cr.cash_advance_id, String))
    incoming = row(IncomingFlow, IncomingFlow.received_date, IncomingFlow.amount, IncomingFlow.currency,
        "income", "incoming", "到账流水（未指定账户）", reference="FL-", remark=IncomingFlow.remark)
    legacy = row(r, r.paid_at, r.total_amount, r.currency, "expense", "reimbursement", "历史报销（未指定账户）",
        reference="RB-", remark=literal("历史已付款，未推断账户")).where(
        r.status == "paid", r.funding_source.is_(None), or_(r.is_fund_linked.is_(None), r.is_fund_linked != "1"))
    payable = row(PayableBill, PayableBill.paid_at, PayableBill.paid_amount, PayableBill.currency,
        "expense", "payable", "应付付款（未指定账户）", reference="PB-", remark=PayableBill.bill_number).where(PayableBill.paid_amount > 0)
    already = select(func.coalesce(func.sum(ExpenseFundDisbursement.amount), 0)).where(
        ExpenseFundDisbursement.fund_id == ExpenseFund.id).scalar_subquery()
    old_amount = ExpenseFund.amount - already
    fund = row(ExpenseFund, ExpenseFund.receive_date, old_amount, ExpenseFund.currency,
        "expense", "expense_fund", "备用金领用（未指定账户）", non_cost=True, reference="EF-", remark=ExpenseFund.purpose).where(old_amount > 0)
    d = ExpenseFundDisbursement
    disbursements = row(d, d.disbursed_date, d.amount, d.currency, "expense", "expense_fund", "备用金拨付",
        account=d.payment_account_id, account_name=d.account_name, reference="EFD-", remark=d.remark)
    raw = union_all(incomes, expenses, reimbursements, returns, incoming, legacy, payable, fund, disbursements).subquery("raw_company_flows")
    a = PaymentAccount
    valid = and_(a.id.is_not(None), a.warehouse_id.in_(warehouse_ids), currency(a.currency) == raw.c.currency)
    # 无账户、旧错误账户或跨币种账户记录不能被悄悄分摊进真实账户。
    columns = []
    for col in raw.c:
        if col.name == "account_id": columns.append(case((valid, raw.c.account_id), else_=None).label("account_id"))
        elif col.name == "account_name": columns.append(case((valid, a.account_name), else_="未指定账户").label("account_name"))
        else: columns.append(col)
    return select(*columns).outerjoin(a, a.id == raw.c.account_id).subquery("company_flows")


def flow_filters(q, start, end, *, account_id=None, currency_code=None, source=None, flow_type=None, unassigned=False):
    filters = [q.c.date >= start, q.c.date <= end]
    if account_id is not None: filters.append(q.c.account_id == account_id)
    if unassigned: filters.append(q.c.account_id.is_(None))
    if currency_code: filters.append(q.c.currency == currency_code)
    if source: filters.append(q.c.source == source)
    if flow_type: filters.append(q.c.type == flow_type)
    return filters


async def flow_list(db, warehouse_ids, start, end, *, page=1, page_size=30, account_id=None, currency_code=None, source=None, flow_type=None, unassigned=False):
    q = flow_query(db, warehouse_ids)
    filters = flow_filters(q, start, end, account_id=account_id, currency_code=currency_code, source=source, flow_type=flow_type, unassigned=unassigned)
    total = (await db.execute(select(func.count()).select_from(q).where(*filters))).scalar_one()
    rows = (await db.execute(select(q).where(*filters).order_by(q.c.date.desc(), q.c.source, q.c.id.desc())
        .offset((page - 1) * page_size).limit(page_size))).mappings().all()
    accounts = {a.id: a.account_name for a in (await db.execute(select(PaymentAccount).where(PaymentAccount.warehouse_id.in_(warehouse_ids)))).scalars()}
    data = [{**dict(r), "date": str(r["date"]), "amount": float(r["amount"]), "status_label": "已冲销" if r["status"] == "revoked" else "有效",
        "account_name": accounts.get(r["account_id"], r["account_name"] or "未指定账户")} for r in rows]
    totals = (await db.execute(select(q.c.currency, q.c.type, func.sum(q.c.amount)).where(
        *filters, q.c.status == "active").group_by(q.c.currency, q.c.type))).all()
    inc = {c: float(money(a)) for c, kind, a in totals if kind == "income"}
    exp = {c: float(money(a)) for c, kind, a in totals if kind == "expense"}
    single = currency_code or (next(iter(set(inc) | set(exp))) if len(set(inc) | set(exp)) == 1 else None)
    total_income, total_expense = (inc.get(single, 0), exp.get(single, 0)) if single else (None, None)
    # 无单一币种时不提供混币种金额；指定币种下保留原流水页净额颜色。
    return {"data": data, "total": total, "page": page, "page_size": page_size,
        "income_by_currency": inc, "expense_by_currency": exp, "total_income": total_income,
        "total_expense": total_expense, "net": total_income - total_expense if single else None, "flow_scope": "company"}


async def advance_list(db, warehouse_ids, start, end, *, page=1, page_size=20, payer_id=None, payer_name=None, currency_code=None):
    filters = [CashAdvance.warehouse_id.in_(warehouse_ids), CashAdvance.advance_date >= start,
        CashAdvance.advance_date <= end, CashAdvance.status.in_(["confirmed", "repaid"])]
    if payer_id is not None: filters.append(CashAdvance.payer_id == payer_id)
    if payer_name is not None: filters.extend([CashAdvance.payer_id.is_(None), CashAdvance.payer_name == payer_name])
    if currency_code: filters.append(CashAdvance.currency == currency_code)
    total = (await db.execute(select(func.count()).select_from(CashAdvance).where(*filters))).scalar_one()
    rows = (await db.execute(select(CashAdvance).where(*filters).order_by(CashAdvance.advance_date.desc(), CashAdvance.id.desc())
        .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    from app.services.cash_advance_payroll import payroll_usage_totals, usage_amounts
    from app.services.cash_advance_usage import reimbursement_usage_totals
    wages = await payroll_usage_totals(db, rows)
    expenses = await reimbursement_usage_totals(db, rows)
    return {"data": [{**usage_amounts(r, wages[r.id], expenses[r.id]), "id": r.id, "payer_id": r.payer_id, "payer_name": r.payer_name,
        "advance_date": r.advance_date.isoformat(), "amount": float(r.amount), "currency": r.currency,
        "purpose_label": {"salary": "工资", "purchase": "采购", "expense": "费用", "other": "其他"}[r.purpose],
        "status": r.status, "status_label": "已归还" if r.status == "repaid" else "部分归还" if r.repaid_amount else "已确认",
        "repaid_amount": float(r.repaid_amount), "outstanding_amount": float(r.amount - r.repaid_amount),
        "description": r.description, "voucher_path": r.voucher_path, "reject_reason": r.reject_reason,
        "is_read_only": True} for r in rows], "total": total, "page": page, "page_size": page_size}


async def report(db, warehouse_ids, start, end):
    costs, flows = cost_query(db, warehouse_ids), flow_query(db, warehouse_ids)
    cf, ff = cost_filters(costs, start, end), flow_filters(flows, start, end)
    cost_groups = (await db.execute(select(costs.c.currency, costs.c.category_name, func.count(), func.sum(costs.c.amount))
        .where(*cf).group_by(costs.c.currency, costs.c.category_name))).all()
    known = (await db.execute(select(flows.c.account_id, flows.c.currency, flows.c.type, func.sum(flows.c.amount))
        .where(*ff, flows.c.status == "active").group_by(flows.c.account_id, flows.c.currency, flows.c.type))).all()
    accounts = (await db.execute(select(PaymentAccount).where(PaymentAccount.warehouse_id.in_(warehouse_ids)).order_by(PaymentAccount.id))).scalars().all()
    # “月初余额”没有历史快照，明确以当前月初的登记数为基准，按同一流水前推/回推。
    anchor = thai_today().replace(day=1)
    low, high = min(start, anchor), max(start, anchor)
    before = (await db.execute(select(flows.c.account_id, flows.c.currency, flows.c.type, func.sum(flows.c.amount)).where(
        flows.c.date >= low, flows.c.date < high, flows.c.status == "active",
    ).group_by(flows.c.account_id, flows.c.currency, flows.c.type))).all() if low < high else []
    prior_net = defaultdict(lambda: ZERO)
    for aid, cur, kind, value in before: prior_net[(aid, cur)] += money(value) * (1 if kind == "income" else -1)
    period = defaultdict(lambda: {"income": ZERO, "expense": ZERO})
    for aid, cur, kind, value in known: period[(aid, cur)][kind] += money(value)
    loans = (await db.execute(select(CashAdvance).where(CashAdvance.warehouse_id.in_(warehouse_ids),
        CashAdvance.advance_date >= start, CashAdvance.advance_date <= end, CashAdvance.status.in_(["confirmed", "repaid"])))) .scalars().all()
    used = (await db.execute(select(costs).where(*cf, costs.c.funding_source.in_(["cash_advance", "expense_fund"])).order_by(costs.c.date, costs.c.source_id))).mappings().all()
    currencies = sorted({"THB", "CNY"} | {c for c, *_ in cost_groups} | {c for _, c, *_ in known} | {a.currency or "THB" for a in accounts} | {r.currency for r in loans})
    blocks = []
    for cur in currencies:
        categories = {name: {"name": name, "count": count, "amount": float(money(value))} for c, name, count, value in cost_groups if c == cur}
        for name in ("员工工资", "报销", "采购", "备用金开销"): categories.setdefault(name, {"name": name, "count": 0, "amount": 0.0})
        ordered = [categories.pop(name) for name in ("员工工资", "报销", "采购", "备用金开销")]
        ordered += [categories[k] for k in sorted(categories)]
        cost_total = sum((money(r["amount"]) for r in ordered), ZERO)
        account_rows = []
        for a in accounts:
            if (a.currency or "THB") != cur: continue
            opening = money(a.opening_balance) + prior_net[(a.id, cur)] * (1 if start >= anchor else -1)
            movements = period[(a.id, cur)]
            account_rows.append({"account_id": a.id, "account_name": a.account_name, "opening_balance": float(opening),
                "inflow": float(movements["income"]), "outflow": float(movements["expense"]),
                "closing_balance": float(opening + movements["income"] - movements["expense"]), "status": a.status or "active"})
        unmapped = period[(None, cur)]
        unassigned = {"inflow": float(unmapped["income"]), "outflow": float(unmapped["expense"])}
        people = {}
        for r in loans:
            if r.currency != cur: continue
            key = f"user:{r.payer_id}" if r.payer_id is not None else f"name:{r.payer_name}"
            g = people.setdefault(key, {"key": key, "payer_id": r.payer_id, "payer_name": r.payer_name,
                "amount": ZERO, "repaid_amount": ZERO, "outstanding_amount": ZERO, "count": 0})
            g["amount"] += r.amount; g["repaid_amount"] += r.repaid_amount; g["outstanding_amount"] += r.amount - r.repaid_amount; g["count"] += 1
        debt_rows = [{**r, **{k: float(r[k]) for k in ("amount", "repaid_amount", "outstanding_amount")}} for r in people.values()]
        details = [{**dict(r), "amount": float(r["amount"]), "date": str(r["date"])} for r in used if r["currency"] == cur]
        advance_used = sum((money(r["amount"]) for r in details if r["funding_source"] == "cash_advance"), ZERO)
        fund_used = sum((money(r["amount"]) for r in details if r["funding_source"] == "expense_fund"), ZERO)
        outgoing = sum((v["expense"] for (aid, c), v in period.items() if c == cur), ZERO)
        non_costs = (await db.execute(select(flows.c.source_label, func.count(), func.sum(flows.c.amount)).where(
            *ff, flows.c.currency == cur, flows.c.status == "active", flows.c.type == "expense", flows.c.is_non_cost_flow.is_(True),
        ).group_by(flows.c.source_label))).all()
        difference = cost_total - outgoing
        residual = difference - advance_used - fund_used
        blocks.append({"currency": cur, "symbol": "¥" if cur == "CNY" else "฿", "costs": {"data": ordered,
            "count": sum(r["count"] for r in ordered), "total": float(cost_total)},
            "funds": {"data": account_rows, "total": {k: float(sum((money(r[k]) for r in account_rows), ZERO)) for k in ("opening_balance", "inflow", "outflow", "closing_balance")}, "unassigned": unassigned},
            "debt": {"data": debt_rows, "total": {k: float(sum((money(r[k]) for r in debt_rows), ZERO)) for k in ("amount", "repaid_amount", "outstanding_amount")}},
            "reconciliation": {"cost_total": float(cost_total), "company_outflow": float(outgoing), "difference": float(difference),
                "cash_advance_cost": float(advance_used), "expense_fund_cost": float(fund_used), "non_company_cost": float(advance_used + fund_used),
                "unreconciled_difference": float(residual), "balanced": residual == ZERO,
                "non_cost_outflows": [{"name": name, "count": count, "amount": float(money(value))} for name, count, value in non_costs],
                "details": details, "detail_count": len(details)}})
    undated = (await db.execute(select(flows.c.currency, flows.c.source_label, func.count(), func.sum(flows.c.amount))
        .where(flows.c.date.is_(None), flows.c.status == "active").group_by(flows.c.currency, flows.c.source_label))).all()
    return {"start_date": start.isoformat(), "end_date": end.isoformat(), "warehouse_ids": warehouse_ids, "currencies": blocks,
        "balance_anchor_date": anchor.isoformat(), "notes": [
            "采购按应付账单的付款日期和已付金额统计，排除作废及未付款；原采购类运营支出单列手工采购，不按名称或金额推断关联。",
            "应付账单只存累计已付和最后付款时间，跨月分次付款缺少逐笔日期/金额，当前口径无法还原每次付款所属月份。",
            "新备用金在拨付时计成本，后续开销只记台账；保留已按旧口径计入的历史备用金开销，不回填旧拨付。",
            "公司资金流水不含充值申报（申报不等于到账）、垫款付款或备用金二次开销；归还垫款和领用备用金计真实流出，另列差异解释。",
            "期初按当前月初登记余额及现存有效流水前推/回推；系统没有历史月初余额快照，历史余额请结合银行账单核对。",
            "欠款按所选日期范围内已确认垫款的当前已还/未还统计，包含已归还单，不是历史时点快照。",
            "未指定账户的历史收付单列，不猜测账户；新备用金逐笔记拨付，旧累计金额扣除新拨付后按原历史口径保留。"],
        "undated_flows": [{"currency": c, "source": source, "count": count, "amount": float(money(value))} for c, source, count, value in undated]}
