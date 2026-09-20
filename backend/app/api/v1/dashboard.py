from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.recharge import RechargeDeclaration, MatchStatus
from app.models.recharge import IncomingFlow
from app.models.market import MarketItem
from app.models.group_order import GroupOrder, GroupOrderStatus
from app.models.expense_fund import ExpenseFundItem, ExpenseFund, ReviewStatus
from app.models.reimbursement import Reimbursement, ReimbStatus
from app.models.warehouse import Warehouse
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role
from app.core.timezone import thai_now, thai_today
from datetime import datetime, date, timedelta

router = APIRouter()

def _wh_filter(query, model, current_user):
    if current_user.role != Role.SUPER_ADMIN:
        return query.where(model.warehouse_id.in_(get_wh_ids(current_user)))
    return query

@router.get("/stats")
async def dashboard_stats(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    # Total recharge this month
    rq = select(func.coalesce(func.sum(RechargeDeclaration.amount), 0)).where(
        func.to_char(RechargeDeclaration.declare_date, 'YYYY-MM') == func.to_char(func.now(), 'YYYY-MM')
    )
    rq = _wh_filter(rq, RechargeDeclaration, current_user)
    total_recharge = (await db.execute(rq)).scalar() or 0

    # Total incoming this month
    iq = select(func.coalesce(func.sum(IncomingFlow.amount), 0)).where(
        func.to_char(IncomingFlow.received_date, 'YYYY-MM') == func.to_char(func.now(), 'YYYY-MM')
    )
    iq = _wh_filter(iq, IncomingFlow, current_user)
    total_incoming = (await db.execute(iq)).scalar() or 0

    # Unmatched recharges
    uq = select(func.count(RechargeDeclaration.id)).where(RechargeDeclaration.match_status == 'unmatched')
    uq = _wh_filter(uq, RechargeDeclaration, current_user)
    unmatched = (await db.execute(uq)).scalar() or 0

    # Pending market items
    mq = select(func.count(MarketItem.id)).where(MarketItem.status == 'pending')
    mq = _wh_filter(mq, MarketItem, current_user)
    pending_market = (await db.execute(mq)).scalar() or 0

    # Pending group orders
    gq = select(func.count(GroupOrder.id)).where(GroupOrder.status == 'open')
    pending_group = (await db.execute(gq)).scalar() or 0

    # Pending expense fund item reviews (join through ExpenseFund for warehouse filter)
    efq = select(func.count(ExpenseFundItem.id)).join(
        ExpenseFund, ExpenseFundItem.fund_id == ExpenseFund.id
    ).where(ExpenseFundItem.review_status == ReviewStatus.PENDING.value)
    if current_user.role != Role.SUPER_ADMIN:
        efq = efq.where(ExpenseFund.warehouse_id.in_(get_wh_ids(current_user)))
    pending_expense_fund = (await db.execute(efq)).scalar() or 0

    # Pending reimbursement approvals
    rbq = select(func.count(Reimbursement.id)).where(Reimbursement.status == ReimbStatus.PENDING.value)
    rbq = _wh_filter(rbq, Reimbursement, current_user)
    pending_reimbursement = (await db.execute(rbq)).scalar() or 0

    return {
        "total_recharge_month": float(total_recharge),
        "total_incoming_month": float(total_incoming),
        "unmatched_count": unmatched,
        "pending_market_review": pending_market,
        "pending_group_orders": pending_group,
        "pending_expense_fund_reviews": pending_expense_fund,
        "pending_reimbursements": pending_reimbursement,
    }

@router.get("/pending-tasks")
async def pending_tasks(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    tasks = []

    # 1. Pending expense fund item reviews
    efq = select(ExpenseFundItem, ExpenseFund, User).join(
        ExpenseFund, ExpenseFundItem.fund_id == ExpenseFund.id
    ).join(
        User, ExpenseFund.employee_id == User.id
    ).where(ExpenseFundItem.review_status == ReviewStatus.PENDING.value)
    if current_user.role != Role.SUPER_ADMIN:
        efq = efq.where(ExpenseFund.warehouse_id.in_(get_wh_ids(current_user)))
    efq = efq.order_by(ExpenseFundItem.created_at.desc()).limit(20)
    ef_result = (await db.execute(efq)).all()
    for item, fund, emp in ef_result:
        tasks.append({
            "type": "expense_fund",
            "description": f"{emp.display_name} 的备用金开销待审核",
            "link": "/expense-fund",
            "id": item.id,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        })

    # 2. Pending reimbursements
    rbq = select(Reimbursement, User).join(
        User, Reimbursement.employee_id == User.id
    ).where(Reimbursement.status == ReimbStatus.PENDING.value)
    rbq = _wh_filter(rbq, Reimbursement, current_user)
    rbq = rbq.order_by(Reimbursement.created_at.desc()).limit(20)
    rb_result = (await db.execute(rbq)).all()
    for reim, emp in rb_result:
        tasks.append({
            "type": "reimbursement",
            "description": f"{emp.display_name} 的报销单待审批",
            "link": "/reimbursement",
            "id": reim.id,
            "created_at": reim.created_at.isoformat() if reim.created_at else None,
        })

    # 3. Pending market items
    mq = select(MarketItem, User).join(
        User, MarketItem.uploader_id == User.id
    ).where(MarketItem.status == 'pending')
    mq = _wh_filter(mq, MarketItem, current_user)
    mq = mq.order_by(MarketItem.created_at.desc()).limit(20)
    m_result = (await db.execute(mq)).all()
    for item, uploader in m_result:
        tasks.append({
            "type": "market",
            "description": f"{uploader.display_name} 上架的 {item.name} 待审核",
            "link": "/market",
            "id": item.id,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        })

    # Sort all tasks by created_at desc, cap at 20
    tasks.sort(key=lambda t: t["created_at"] or "", reverse=True)
    for t in tasks: del t["created_at"]
    tasks = tasks[:20]

    return {"data": tasks}

@router.get("/warehouse-summary")
async def warehouse_summary(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role != Role.SUPER_ADMIN:
        wh = current_user.warehouse
        if not wh:
            return {"data": []}
        rq = (await db.execute(select(func.sum(RechargeDeclaration.amount)).where(RechargeDeclaration.warehouse_id == wh.id))).scalar() or 0
        iq = (await db.execute(select(func.sum(IncomingFlow.amount)).where(IncomingFlow.warehouse_id == wh.id))).scalar() or 0
        uq = (await db.execute(select(func.count(RechargeDeclaration.id)).where(
            RechargeDeclaration.warehouse_id == wh.id, RechargeDeclaration.match_status == 'unmatched'))).scalar() or 0
        return {"data": [{"warehouse_id": wh.id, "warehouse_name": wh.name, "recharge_total": float(rq), "incoming_total": float(iq), "unmatched_count": uq}]}

    warehouses = (await db.execute(select(Warehouse).where(Warehouse.is_active == True))).scalars().all()
    result = []
    for wh in warehouses:
        rq = (await db.execute(select(func.sum(RechargeDeclaration.amount)).where(RechargeDeclaration.warehouse_id == wh.id))).scalar() or 0
        iq = (await db.execute(select(func.sum(IncomingFlow.amount)).where(IncomingFlow.warehouse_id == wh.id))).scalar() or 0
        uq = (await db.execute(select(func.count(RechargeDeclaration.id)).where(
            RechargeDeclaration.warehouse_id == wh.id, RechargeDeclaration.match_status == 'unmatched'))).scalar() or 0
        result.append({"warehouse_id": wh.id, "warehouse_name": wh.name, "recharge_total": float(rq), "incoming_total": float(iq), "unmatched_count": uq})
    return {"data": result}


def _merge_currency(*lists):
    """把 [(currency, amount), ...] 多组按币种合并，不跨币种相加。"""
    d: dict[str, float] = {}
    for lst in lists:
        for c, amt in lst:
            c = c or "THB"
            d[c] = d.get(c, 0) + float(amt or 0)
    return [{"currency": c, "amount": round(v, 2)} for c, v in sorted(d.items())]


@router.get("/trends")
async def dashboard_trends(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """三个趋势图数据：资金(30天)、收支(6月)、订单(8周)，按币种分组，按当前仓库统计。"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")

    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    from app.models.income_expense import IncomeRecord, ExpenseRecord, IncomeExpenseCategory
    from app.models.payable import PayableBill
    from app.models.supplier import PurchaseOrder, Supplier

    today = thai_today()
    currencies = ["THB", "CNY"]

    # ── 资金趋势：最近30天（Python 聚合，按币种） ──
    start_30 = today - timedelta(days=29)
    day_end = today + timedelta(days=1)
    recharge_rows = (await db.execute(
        select(RechargeDeclaration.currency, RechargeDeclaration.declare_date, RechargeDeclaration.amount)
        .where(RechargeDeclaration.warehouse_id == wh_id,
               RechargeDeclaration.declare_date >= datetime.combine(start_30, datetime.min.time()),
               RechargeDeclaration.declare_date < datetime.combine(day_end, datetime.min.time()))
    )).all()
    incoming_rows = (await db.execute(
        select(IncomingFlow.currency, IncomingFlow.received_date, IncomingFlow.amount)
        .where(IncomingFlow.warehouse_id == wh_id,
               IncomingFlow.received_date >= datetime.combine(start_30, datetime.min.time()),
               IncomingFlow.received_date < datetime.combine(day_end, datetime.min.time()))
    )).all()

    def _date_str(dt):
        return dt.date().isoformat() if hasattr(dt, "date") else str(dt)[:10]

    def _funds_series(cur):
        rc = {}
        for c, dt, amt in recharge_rows:
            if (c or "THB") == cur:
                k = _date_str(dt)
                rc[k] = rc.get(k, 0) + float(amt or 0)
        ic = {}
        for c, dt, amt in incoming_rows:
            if (c or "THB") == cur:
                k = _date_str(dt)
                ic[k] = ic.get(k, 0) + float(amt or 0)
        series = []
        for i in range(30):
            d = start_30 + timedelta(days=i)
            ds = d.isoformat()
            series.append({"date": ds, "recharge": round(rc.get(ds, 0), 2), "incoming": round(ic.get(ds, 0), 2)})
        return series

    funds = {c: _funds_series(c) for c in currencies}

    # ── 收支趋势：最近6个月（Python 聚合） ──
    month_starts = []
    ym = today.replace(day=1)
    for _ in range(6):
        month_starts.append(ym)
        ym = (ym - timedelta(days=1)).replace(day=1)
    month_starts.reverse()
    month_labels = [m.strftime("%Y-%m") for m in month_starts]
    min_month = month_starts[0]
    max_month_end = (month_starts[-1].replace(day=28) + timedelta(days=10)).replace(day=1)

    def _month_key(dt):
        d = dt.date() if hasattr(dt, "date") else dt
        return d.strftime("%Y-%m")

    income_rec_rows = (await db.execute(
        select(IncomeRecord.currency, IncomeRecord.income_date, IncomeRecord.amount)
        .where(IncomeRecord.warehouse_id == wh_id,
               IncomeRecord.income_date >= datetime.combine(min_month, datetime.min.time()),
               IncomeRecord.income_date < datetime.combine(max_month_end, datetime.min.time()))
    )).all()
    recharge_month_rows = (await db.execute(
        select(RechargeDeclaration.currency, RechargeDeclaration.declare_date, RechargeDeclaration.amount)
        .where(RechargeDeclaration.warehouse_id == wh_id,
               RechargeDeclaration.declare_date >= datetime.combine(min_month, datetime.min.time()),
               RechargeDeclaration.declare_date < datetime.combine(max_month_end, datetime.min.time()))
    )).all()
    expense_rec_rows = (await db.execute(
        select(ExpenseRecord.currency, ExpenseRecord.expense_date, ExpenseRecord.amount)
        .where(ExpenseRecord.warehouse_id == wh_id,
               ExpenseRecord.expense_date >= datetime.combine(min_month, datetime.min.time()),
               ExpenseRecord.expense_date < datetime.combine(max_month_end, datetime.min.time()))
    )).all()
    bill_month_rows = (await db.execute(
        select(PayableBill.currency, PayableBill.bill_date, PayableBill.amount)
        .where(PayableBill.warehouse_id == wh_id,
               PayableBill.bill_date >= datetime.combine(min_month, datetime.min.time()),
               PayableBill.bill_date < datetime.combine(max_month_end, datetime.min.time()))
    )).all()

    def _ie_series(cur):
        inc = {}
        for c, dt, amt in list(income_rec_rows) + list(recharge_month_rows):
            if (c or "THB") == cur:
                k = _month_key(dt)
                inc[k] = inc.get(k, 0) + float(amt or 0)
        exp = {}
        for c, dt, amt in list(expense_rec_rows) + list(bill_month_rows):
            if (c or "THB") == cur:
                k = _month_key(dt)
                exp[k] = exp.get(k, 0) + float(amt or 0)
        series = []
        for m in month_labels:
            series.append({"month": m, "income": round(inc.get(m, 0), 2), "expense": round(exp.get(m, 0), 2)})
        return series

    income_expense = {c: _ie_series(c) for c in currencies}

    # ── 订单趋势：最近8周（采购单数量，Python 分桶） ──
    this_monday = today - timedelta(days=today.weekday())
    week_starts = [this_monday - timedelta(weeks=i) for i in range(7, -1, -1)]
    from app.core.timezone import THAI_TZ
    po_rows = (await db.execute(
        select(PurchaseOrder.currency, PurchaseOrder.created_at)
        .where(PurchaseOrder.warehouse_id == wh_id,
               PurchaseOrder.created_at >= datetime.combine(week_starts[0], datetime.min.time()))
    )).all()

    def _week_key(dt):
        if dt is None:
            return None
        d = dt
        if getattr(d, "tzinfo", None) is not None:
            d = d.astimezone(THAI_TZ).replace(tzinfo=None)
        d = d.date() if hasattr(d, "date") else d
        return d - timedelta(days=d.weekday())

    def _orders_series(cur):
        cnt = {}
        for c, dt in po_rows:
            if (c or "THB") == cur:
                wk = _week_key(dt)
                if wk is not None:
                    cnt[str(wk)] = cnt.get(str(wk), 0) + 1
        series = []
        for ws in week_starts:
            series.append({"week_start": ws.isoformat(), "count": cnt.get(str(ws), 0)})
        return series

    orders = {c: _orders_series(c) for c in currencies}

    # ── 两个占比环形图数据 ──
    month_start = today.replace(day=1)
    if today.month == 12:
        next_month = today.replace(year=today.year + 1, month=1, day=1)
    else:
        next_month = today.replace(month=today.month + 1, day=1)

    cat_rows = (await db.execute(
        select(ExpenseRecord.currency, ExpenseRecord.amount, IncomeExpenseCategory.name)
        .join(IncomeExpenseCategory, ExpenseRecord.category_id == IncomeExpenseCategory.id)
        .where(ExpenseRecord.warehouse_id == wh_id,
               ExpenseRecord.expense_date >= datetime.combine(month_start, datetime.min.time()),
               ExpenseRecord.expense_date < datetime.combine(next_month, datetime.min.time()))
    )).all()
    sup_rows = (await db.execute(
        select(PayableBill.currency, PayableBill.amount, Supplier.name)
        .join(Supplier, PayableBill.supplier_id == Supplier.id)
        .where(PayableBill.warehouse_id == wh_id,
               PayableBill.bill_date >= datetime.combine(month_start, datetime.min.time()),
               PayableBill.bill_date < datetime.combine(next_month, datetime.min.time()))
    )).all()

    def _group_by_name(rows, cur):
        d = {}
        for c, amt, name in rows:
            if (c or "THB") == cur:
                nm = name or "未分类"
                d[nm] = d.get(nm, 0) + float(amt or 0)
        return [{"name": n, "amount": round(v, 2)} for n, v in sorted(d.items(), key=lambda x: -x[1])]

    expense_categories = {c: _group_by_name(cat_rows, c) for c in currencies}
    procurement_suppliers = {c: _group_by_name(sup_rows, c) for c in currencies}

    return {
        "funds": funds,
        "income_expense": income_expense,
        "orders": orders,
        "expense_categories": expense_categories,
        "procurement_suppliers": procurement_suppliers,
    }


@router.get("/cockpit")
async def dashboard_cockpit(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """老板驾驶舱：钱 + 人 + 待办，全部按当前选中仓库统计，按币种分组。"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")

    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    from app.models.income_expense import ExpenseRecord
    from app.models.payable import PayableBill
    from app.models.credit import CreditCustomer
    from app.models.customer import Customer, PaymentAccount
    from app.models.employee import Employee
    from app.models.clock_in_records import ClockInRecord
    from app.models.attendance import LeaveRequest, Absence
    from app.models.overtime import OvertimeTask
    from app.models.supplier import PurchaseOrder, ProcurementPriceAnomaly, ProcurementNonLowestRecord

    today = thai_today()
    month_start = today.replace(day=1)
    if today.month == 12:
        next_month = today.replace(year=today.year + 1, month=1, day=1)
    else:
        next_month = today.replace(month=today.month + 1, day=1)
    month_str = today.strftime("%Y-%m")

    # ── 钱 ──
    # 本月收入（客户充值合计）
    income_rows = (await db.execute(
        select(RechargeDeclaration.currency, func.coalesce(func.sum(RechargeDeclaration.amount), 0))
        .where(RechargeDeclaration.warehouse_id == wh_id,
               RechargeDeclaration.declare_date >= month_start,
               RechargeDeclaration.declare_date < next_month)
        .group_by(RechargeDeclaration.currency)
    )).all()
    # 本月到账合计
    incoming_rows = (await db.execute(
        select(IncomingFlow.currency, func.coalesce(func.sum(IncomingFlow.amount), 0))
        .where(IncomingFlow.warehouse_id == wh_id,
               IncomingFlow.received_date >= month_start,
               IncomingFlow.received_date < next_month)
        .group_by(IncomingFlow.currency)
    )).all()
    # 未对账笔数
    unmatched_recharge = (await db.execute(
        select(func.count(RechargeDeclaration.id)).where(
            RechargeDeclaration.warehouse_id == wh_id,
            RechargeDeclaration.match_status == MatchStatus.UNMATCHED.value,
        )
    )).scalar() or 0
    # 运营支出
    op_rows = (await db.execute(
        select(ExpenseRecord.currency, func.coalesce(func.sum(ExpenseRecord.amount), 0))
        .where(ExpenseRecord.warehouse_id == wh_id,
               ExpenseRecord.expense_date >= month_start,
               ExpenseRecord.expense_date < next_month)
        .group_by(ExpenseRecord.currency)
    )).all()
    # 采购支出（应付账单本月）
    proc_rows = (await db.execute(
        select(PayableBill.currency, func.coalesce(func.sum(PayableBill.amount), 0))
        .where(PayableBill.warehouse_id == wh_id,
               PayableBill.bill_date >= month_start,
               PayableBill.bill_date < next_month)
        .group_by(PayableBill.currency)
    )).all()

    expense_rows = _merge_currency(op_rows, proc_rows)
    income_list = _merge_currency(income_rows)
    expense_list = expense_rows
    # 盈亏 = 收入 - 支出（按币种）
    inc_map = {x["currency"]: x["amount"] for x in income_list}
    exp_map = {x["currency"]: x["amount"] for x in expense_list}
    all_cur = set(inc_map) | set(exp_map)
    profit_list = [{"currency": c, "amount": round(inc_map.get(c, 0) - exp_map.get(c, 0), 2)} for c in sorted(all_cur)]

    # 待收（账期客户欠款）按客户默认币种
    recv_rows = (await db.execute(
        select(Customer.default_currency, func.coalesce(func.sum(CreditCustomer.current_debt), 0))
        .join(Customer, CreditCustomer.customer_id == Customer.id)
        .where(CreditCustomer.warehouse_id == wh_id, CreditCustomer.current_debt.isnot(None))
        .group_by(Customer.default_currency)
    )).all()
    receivable = _merge_currency(recv_rows)

    # 待付（应付未付 = amount - paid_amount）
    payable_rows = (await db.execute(
        select(PayableBill.currency, func.coalesce(func.sum(PayableBill.amount - func.coalesce(PayableBill.paid_amount, 0)), 0))
        .where(PayableBill.warehouse_id == wh_id, PayableBill.status != "paid")
        .group_by(PayableBill.currency)
    )).all()
    payable = _merge_currency(payable_rows)

    # 逾期未付
    overdue_rows = (await db.execute(
        select(PayableBill.currency, func.coalesce(func.sum(PayableBill.amount - func.coalesce(PayableBill.paid_amount, 0)), 0))
        .where(PayableBill.warehouse_id == wh_id, PayableBill.status != "paid", func.date(PayableBill.due_date) < today)
        .group_by(PayableBill.currency)
    )).all()
    overdue_payable = _merge_currency(overdue_rows)

    # 账户余额
    payacct_rows = (await db.execute(
        select(PaymentAccount.currency, func.coalesce(func.sum(PaymentAccount.opening_balance), 0))
        .where(PaymentAccount.warehouse_id == wh_id, PaymentAccount.status == "active")
        .group_by(PaymentAccount.currency)
    )).all()
    fund_rows = (await db.execute(
        select(ExpenseFund.currency, func.coalesce(func.sum(ExpenseFund.remaining_balance), 0))
        .where(ExpenseFund.warehouse_id == wh_id, ExpenseFund.status == "active")
        .group_by(ExpenseFund.currency)
    )).all()

    # 本月采购异常
    price_anomaly = (await db.execute(
        select(func.count(ProcurementPriceAnomaly.id))
        .where(ProcurementPriceAnomaly.warehouse_id == wh_id,
               ProcurementPriceAnomaly.created_at >= month_start,
               ProcurementPriceAnomaly.created_at < next_month)
    )).scalar() or 0
    non_lowest = (await db.execute(
        select(func.count(ProcurementNonLowestRecord.id))
        .where(ProcurementNonLowestRecord.warehouse_id == wh_id,
               ProcurementNonLowestRecord.created_at >= month_start,
               ProcurementNonLowestRecord.created_at < next_month)
    )).scalar() or 0

    # ── 人 ──
    # 今日出勤
    expected = (await db.execute(
        select(func.count(Employee.id)).where(
            Employee.warehouse_id == wh_id,
            Employee.status != "resigned",
            Employee.is_deleted == False,
        )
    )).scalar() or 0
    present = (await db.execute(
        select(func.count(func.distinct(ClockInRecord.user_id))).where(
            ClockInRecord.warehouse_id == wh_id,
            ClockInRecord.clock_date == today,
        )
    )).scalar() or 0
    absent = (await db.execute(
        select(func.count(Absence.id)).where(
            Absence.warehouse_id == wh_id,
            Absence.absence_date == today,
        )
    )).scalar() or 0

    # 本月人效（复用效率模块月汇总；用 savepoint 隔离，失败不影响其余统计）
    efficiency = None
    try:
        from app.api.v1.efficiency import _aggregate_month
        async with db.begin_nested():
            em = await _aggregate_month(db, wh_id, month_str)
            efficiency = {
                "person_times": em.get("person_times", 0),
                "order_count": em.get("order_count", 0),
                "efficiency": em.get("efficiency", 0),
                "standard": em.get("standard", 0),
                "below_standard": bool(em.get("below_standard", False)),
            }
    except Exception:
        efficiency = {"person_times": 0, "order_count": 0, "efficiency": 0, "standard": 0, "below_standard": False}

    # 待办数量
    leave_pending = (await db.execute(
        select(func.count(LeaveRequest.id)).where(
            LeaveRequest.warehouse_id == wh_id, LeaveRequest.status == "pending"
        )
    )).scalar() or 0
    overtime_pending = (await db.execute(
        select(func.count(OvertimeTask.id)).where(
            OvertimeTask.warehouse_id == wh_id, OvertimeTask.status == "pending"
        )
    )).scalar() or 0
    ef_pending = (await db.execute(
        select(func.count(ExpenseFundItem.id)).join(
            ExpenseFund, ExpenseFundItem.fund_id == ExpenseFund.id
        ).where(
            ExpenseFundItem.review_status == ReviewStatus.PENDING.value,
            ExpenseFund.warehouse_id == wh_id,
        )
    )).scalar() or 0
    rb_pending = (await db.execute(
        select(func.count(Reimbursement.id)).where(
            Reimbursement.warehouse_id == wh_id, Reimbursement.status == ReimbStatus.PENDING.value
        )
    )).scalar() or 0
    market_pending = (await db.execute(
        select(func.count(MarketItem.id)).where(
            MarketItem.warehouse_id == wh_id, MarketItem.status == "pending"
        )
    )).scalar() or 0
    group_pending = (await db.execute(
        select(func.count(GroupOrder.id)).where(
            GroupOrder.warehouse_id == wh_id, GroupOrder.status == GroupOrderStatus.OPEN.value
        )
    )).scalar() or 0

    # ── 待办列表 ──
    todos = []

    # 采购审批待办（超门槛 → status=pending）
    po_rows = (await db.execute(
        select(PurchaseOrder.id, PurchaseOrder.order_number, PurchaseOrder.total_amount)
        .where(PurchaseOrder.warehouse_id == wh_id, PurchaseOrder.status == "pending")
        .order_by(PurchaseOrder.created_at.desc()).limit(20)
    )).all()
    for pid, order_no, total in po_rows:
        todos.append({"type": "purchase_approval", "description": f"采购单 {order_no} 待审批",
                      "link": "/suppliers", "id": pid})

    # 账单待确认（收货有差异）
    bill_rows = (await db.execute(
        select(PayableBill.id, PayableBill.bill_number, PayableBill.amount, PayableBill.confirmed_amount)
        .where(PayableBill.warehouse_id == wh_id,
               ((PayableBill.need_boss_confirm == "true") | ((PayableBill.confirmed_amount.isnot(None)) & (PayableBill.confirmed_amount != PayableBill.amount))))
        .order_by(PayableBill.created_at.desc()).limit(20)
    )).all()
    for bid, bill_no, amount, confirmed in bill_rows:
        todos.append({"type": "bill_confirm", "description": f"账单 {bill_no} 收货有差异待确认", "link": "/payable", "id": bid})

    # 请假待审批
    leave_rows = (await db.execute(
        select(LeaveRequest.id, Employee.name)
        .join(Employee, LeaveRequest.employee_id == Employee.id)
        .where(LeaveRequest.warehouse_id == wh_id, LeaveRequest.status == "pending")
        .order_by(LeaveRequest.created_at.desc()).limit(20)
    )).all()
    for lid, ename in leave_rows:
        todos.append({"type": "leave", "description": f"{ename} 的请假申请待审批", "link": "/attendance", "id": lid})

    # 加班待确认
    ot_rows = (await db.execute(
        select(OvertimeTask.id, OvertimeTask.date)
        .where(OvertimeTask.warehouse_id == wh_id, OvertimeTask.status == "pending")
        .order_by(OvertimeTask.created_at.desc()).limit(20)
    )).all()
    for oid, odate in ot_rows:
        todos.append({"type": "overtime", "description": f"{odate} 的加班任务待确认", "link": "/overtime", "id": oid})

    # 备用金开销待审核
    ef_rows = (await db.execute(
        select(ExpenseFundItem.id, User.display_name)
        .join(ExpenseFund, ExpenseFundItem.fund_id == ExpenseFund.id)
        .join(User, ExpenseFund.employee_id == User.id)
        .where(ExpenseFundItem.review_status == ReviewStatus.PENDING.value,
               ExpenseFund.warehouse_id == wh_id)
        .order_by(ExpenseFundItem.created_at.desc()).limit(20)
    )).all()
    for iid, uname in ef_rows:
        todos.append({"type": "expense_fund", "description": f"{uname} 的备用金开销待审核", "link": "/expense-fund", "id": iid})

    # 报销单待审批
    rb_rows = (await db.execute(
        select(Reimbursement.id, User.display_name)
        .join(User, Reimbursement.employee_id == User.id)
        .where(Reimbursement.warehouse_id == wh_id, Reimbursement.status == ReimbStatus.PENDING.value)
        .order_by(Reimbursement.created_at.desc()).limit(20)
    )).all()
    for rid, uname in rb_rows:
        todos.append({"type": "reimbursement", "description": f"{uname} 的报销单待审批", "link": "/reimbursement", "id": rid})

    # 商品上架待审核
    m_rows = (await db.execute(
        select(MarketItem.id, MarketItem.name, User.display_name)
        .join(User, MarketItem.uploader_id == User.id)
        .where(MarketItem.warehouse_id == wh_id, MarketItem.status == "pending")
        .order_by(MarketItem.created_at.desc()).limit(20)
    )).all()
    for mid, mname, uname in m_rows:
        todos.append({"type": "market", "description": f"{uname} 上架的 {mname} 待审核", "link": "/market", "id": mid})

    # 待拼单
    g_rows = (await db.execute(
        select(GroupOrder.id, GroupOrder.item_name)
        .where(GroupOrder.warehouse_id == wh_id, GroupOrder.status == GroupOrderStatus.OPEN.value)
        .order_by(GroupOrder.created_at.desc()).limit(20)
    )).all()
    for gid, gname in g_rows:
        todos.append({"type": "group_order", "description": f"待拼单：{gname}", "link": "/group-order", "id": gid})

    return {
        "finance": {
            "month": {
                "income": income_list,
                "operating_expense": _merge_currency(op_rows),
                "procurement_expense": _merge_currency(proc_rows),
                "expense": expense_list,
                "profit": profit_list,
            },
            "receivable_payable": {
                "receivable": receivable,
                "payable": payable,
                "overdue_payable": overdue_payable,
            },
            "balances": {
                "payment_accounts": _merge_currency(payacct_rows),
                "expense_funds": _merge_currency(fund_rows),
            },
            "procurement": {
                "expense": _merge_currency(proc_rows),
                "price_anomaly_count": price_anomaly,
                "non_lowest_count": non_lowest,
            },
            "recharge_reconciliation": {
                "recharge": _merge_currency(income_rows),
                "incoming": _merge_currency(incoming_rows),
                "unmatched_count": unmatched_recharge,
            },
        },
        "people": {
            "attendance": {"expected": expected, "present": present, "absent": absent},
            "efficiency": efficiency,
            "todos": {
                "leave_pending": leave_pending,
                "overtime_pending": overtime_pending,
                "expense_fund_pending": ef_pending,
                "reimbursement_pending": rb_pending,
                "market_pending": market_pending,
                "group_order_pending": group_pending,
            },
        },
        "todos": todos,
    }
