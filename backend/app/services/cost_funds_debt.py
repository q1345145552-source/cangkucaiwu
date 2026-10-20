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


def dates(start=None, end=None, *, month=None, year=None):
    from app.services.money_period import money_period
    today = thai_today()
    return money_period(month, start, end, year=year, default_start=today.replace(day=1), default_end=today)


from app.services.wallet import day, flow_query


def cost_query(db, warehouse_ids):
    """钱包支出的只读列表，精确关联已有支出，方便反查且避免旁路编辑付款。"""
    from app.models.expense_approval import ExpenseApproval
    q = flow_query(db, warehouse_ids)
    e, p, r, a, d, rp = ExpenseRecord, PayrollRecord, Reimbursement, EmployeeAdvance, ExpenseFundDisbursement, ReimbursementPayment
    linked_id = func.coalesce(e.id, q.c.id)
    linked_source = case((e.id.is_not(None), "expense"), else_=q.c.source)
    approval_link = select(ExpenseApproval.id).where(ExpenseApproval.warehouse_id == q.c.warehouse_id,
        ExpenseApproval.expense_record_id == e.id).exists()
    return select(linked_id.label("id"), linked_source.label("source"), linked_id.label("source_id"),
        q.c.source.label("wallet_source"), q.c.source_label, q.c.ref_no, q.c.status, q.c.account_name,
        q.c.warehouse_id, q.c.date, func.coalesce(q.c.category_id, e.category_id).label("category_id"), q.c.category_name,
        q.c.amount, q.c.currency, q.c.account_id, q.c.remark, e.voucher,
        literal("company_account").label("funding_source"), q.c.cash_advance_id,
        r.id.label("reimbursement_id"), p.id.label("payroll_record_id"),
        or_(q.c.source != "manual", p.id.is_not(None), a.id.is_not(None), approval_link).label("is_read_only"),
        a.id.label("employee_advance_id"), a.employee_id,
        d.id.label("fund_disbursement_id"), d.fund_id,
    ).outerjoin(rp, and_(rp.id == q.c.id, q.c.source == "reimbursement", rp.warehouse_id == q.c.warehouse_id)).outerjoin(
        d, and_(d.id == q.c.id, q.c.source == "expense_fund", q.c.ref_no.like("EFD-%"), d.warehouse_id == q.c.warehouse_id)).outerjoin(
        e, and_(e.warehouse_id == q.c.warehouse_id, or_(and_(q.c.source == "manual", e.id == q.c.id),
            and_(q.c.source == "reimbursement", e.id == rp.expense_record_id),
            and_(q.c.source == "expense_fund", e.id == d.expense_record_id)))).outerjoin(
        p, and_(p.expense_record_id == e.id, p.warehouse_id == q.c.warehouse_id)).outerjoin(
        r, and_(or_(r.expense_record_id == e.id, r.id == rp.reimbursement_id), r.warehouse_id == q.c.warehouse_id)).outerjoin(
        a, and_(a.expense_record_id == e.id, a.warehouse_id == q.c.warehouse_id)).where(
        q.c.type == "expense", q.c.status == "active", q.c.is_internal_transfer.is_(False)).subquery("cost_rows")


def cost_filters(q, start, end, *, category_id=None, cost_category=None, account_id=None, currency_code=None):
    filters = [q.c.date >= start, q.c.date <= end]
    if category_id:
        category = IncomeExpenseCategory
        name = select(case((category.name == "采购", "手工采购"), (category.name == "工资", "员工工资"),
            else_=category.name)).where(category.id == category_id, category.warehouse_id == q.c.warehouse_id).scalar_subquery()
        filters.append(or_(q.c.category_id == category_id, q.c.category_name == name))
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
    data = [{**dict(r), "id": r["id"] if r["source"] == "expense" else f"{r['source']}-{r['id']}",
        "amount": float(r["amount"]), "expense_date": str(r["date"]),
        "date": str(r["date"]), "account_name": accounts.get(r["account_id"], "付款账户未记录" if r["source"] == "payable" else "备用金" if r["source"] == "fund_item" else "不使用公司账户"),
        "is_read_only": bool(r["is_read_only"])} for r in rows]
    return {"data": data, "total": total, "page": page, "page_size": page_size,
        "totals_by_currency": await cost_totals(db, q, filters), "cost_basis": "按实际收付日期统计公司支出；垫款归还才计支出，备用金拨付只计一次，内部转账不计收支"}



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
        *filters, q.c.status == "active", literal(True) if account_id is not None else q.c.is_internal_transfer.is_(False)).group_by(q.c.currency, q.c.type))).all()
    inc = {c: float(money(a)) for c, kind, a in totals if kind == "income"}
    exp = {c: float(money(a)) for c, kind, a in totals if kind == "expense"}
    single = currency_code or (next(iter(set(inc) | set(exp))) if len(set(inc) | set(exp)) == 1 else None)
    total_income, total_expense = (inc.get(single, 0), exp.get(single, 0)) if single or not (inc or exp) else (None, None)
    # 无单一币种时不提供混币种金额；指定币种下保留原流水页净额颜色。
    return {"data": data, "total": total, "page": page, "page_size": page_size,
        "income_by_currency": inc, "expense_by_currency": exp, "total_income": total_income,
        "total_expense": total_expense, "net": total_income - total_expense if total_income is not None else None, "flow_scope": "company"}


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
    from app.services.account_balances import balances_at
    opening_balances = await balances_at(db, accounts, start)
    anchor = thai_today().replace(day=1)
    period = defaultdict(lambda: {"income": ZERO, "expense": ZERO})
    for aid, cur, kind, value in known: period[(aid, cur)][kind] += money(value)
    loans = (await db.execute(select(CashAdvance).where(CashAdvance.warehouse_id.in_(warehouse_ids),
        CashAdvance.advance_date >= start, CashAdvance.advance_date <= end, CashAdvance.status.in_(["confirmed", "repaid"])))) .scalars().all()
    used = (await db.execute(select(costs).where(*cf, costs.c.funding_source.in_(["cash_advance", "expense_fund"])).order_by(costs.c.date, costs.c.source_id))).mappings().all()
    currencies = sorted({"THB", "CNY"} | {c for c, *_ in cost_groups} | {c for _, c, *_ in known} | {a.currency or "THB" for a in accounts} | {r.currency for r in loans})
    blocks = []
    for cur in currencies:
        categories = {name: {"name": name, "count": count, "amount": float(money(value))} for c, name, count, value in cost_groups if c == cur}
        for name in ("员工工资", "报销", "采购", "备用金拨付"): categories.setdefault(name, {"name": name, "count": 0, "amount": 0.0})
        ordered = [categories.pop(name) for name in ("员工工资", "报销", "采购", "备用金拨付")]
        ordered += [categories[k] for k in sorted(categories)]
        cost_total = sum((money(r["amount"]) for r in ordered), ZERO)
        account_rows = []
        for a in accounts:
            if (a.currency or "THB") != cur: continue
            opening = opening_balances[a.id]
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
        outgoing = money((await db.execute(select(func.coalesce(func.sum(flows.c.amount), 0)).where(
            *ff, flows.c.currency == cur, flows.c.type == "expense", flows.c.status == "active",
            flows.c.is_internal_transfer.is_(False)))).scalar_one())
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
            "采购按逐笔实际付款日统计，作废未付余额不抹掉已付款；原手工采购另列，不按金额猜测关联。",
            "新付款逐笔保存；旧累计额冻结在原最后付款日，历史缺失的逐笔日期和账户不猜补。",
            "备用金在拨付时计一次支出，后续开销和备用金报销仅记录使用；原记录保留，不重复合计。",
            "收入只认实际到账和收款；垫款业务不先记公司支出，归还垫款当天按用途记支出。内部转账只影响各账户余额，不计公司收入支出。",
            "账户按保存的期初日期与同一套有效流水推算；旧累计付款和未指定账户单列，历史余额仍需结合银行账单核对。",
            "欠款按所选日期范围内已确认垫款的当前已还/未还统计，包含已归还单，不是历史时点快照。",
            "未指定账户的历史收付单列，不猜测账户；新备用金逐笔记拨付，旧累计金额扣除新拨付后按原历史口径保留。"],
        "undated_flows": [{"currency": c, "source": source, "count": count, "amount": float(money(value))} for c, source, count, value in undated]}
