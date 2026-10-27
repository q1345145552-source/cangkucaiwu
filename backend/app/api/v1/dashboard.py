from app.core.round5_access import financial_reader, has_menu
from fastapi import APIRouter, Depends, HTTPException, Response, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.recharge import RechargeDeclaration, MatchStatus
from app.models.recharge import IncomingFlow
from app.models.market import MarketItem
from app.models.group_order import GroupOrder, GroupOrderStatus
from app.models.expense_fund import ExpenseFundItem, ExpenseFund, ReviewStatus
from app.models.expense_approval import ExpenseApproval
from app.models.reimbursement import Reimbursement, ReimbStatus
from app.models.warehouse import Warehouse
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role, require_non_labor
from app.core.timezone import thai_now, thai_today
from app.services.procurement_payments import procurement_payment_rows, procurement_payment_totals
from datetime import datetime, date, timedelta

router = APIRouter()

def _wh_filter(query, model, current_user):
    if current_user.role != Role.SUPER_ADMIN:
        return query.where(model.warehouse_id.in_(get_wh_ids(current_user)))
    return query

@router.get("/stats", dependencies=[Depends(require_non_labor)])
async def dashboard_stats(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if not financial_reader(current_user,'reports'):
        from app.models.employee import Employee
        from app.models.attendance import LeaveRequest
        scope = get_wh_ids(current_user)
        can_people = has_menu(current_user,'employees') or has_menu(current_user,'attendance')
        count = (await db.execute(select(func.count(Employee.id)).where(Employee.warehouse_id.in_(scope),Employee.is_deleted == False,Employee.status != 'resigned'))).scalar() if can_people else None
        return {"scope":"onsite","employee_count":count}
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

@router.get("/pending-tasks", dependencies=[Depends(require_non_labor)])
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

    return {"data": [task for task in tasks if has_menu(current_user,task["type"])]}

@router.get("/warehouse-summary", dependencies=[Depends(require_non_labor)])
async def warehouse_summary(request: Request, warehouse_id: int | None = None,
                            warehouse_ids: list[int] | None = Query(None),
                            start_date: str | None = None, end_date: str | None = None,
                            month: str | None = None,
                            current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权访问")
    from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
    if current_user.role in (Role.SUPERVISOR, Role.STAFF) and MENU_PERMISSIONS_BY_KEY['reports'].label not in (current_user.extra_permissions or []):
        raise HTTPException(403, "无此操作权限，需要: 报表中心")
    from app.services.warehouse_summary import warehouse_scope, summarize
    warehouses = await warehouse_scope(db, current_user, request.headers.get('X-Warehouse-ID'), warehouse_id, warehouse_ids)
    return await summarize(db, warehouses, start_date, end_date, month)


def _merge_currency(*lists):
    """把 [(currency, amount), ...] 多组按币种合并，不跨币种相加。"""
    d: dict[str, float] = {}
    for lst in lists:
        for c, amt in lst:
            c = c or "THB"
            d[c] = d.get(c, 0) + float(amt or 0)
    return [{"currency": c, "amount": round(v, 2)} for c, v in sorted(d.items())]


async def _selected_dashboard(request, user, db, month):
    from app.services.warehouse_summary import warehouse_scope
    from app.services.dashboard_period import monthly_view
    warehouses = await warehouse_scope(db, user, request.headers.get('X-Warehouse-ID'))
    if not warehouses:raise HTTPException(400, "请先选择启用且有权访问的仓库")
    selected = month if month is not None else thai_today().strftime('%Y-%m')
    return await monthly_view(db, warehouses, selected)


@router.get("/trends")
async def dashboard_trends(request: Request, month: str | None = None,
                           current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    return (await _selected_dashboard(request,current_user,db,month))['trends']


@router.get("/cockpit")
async def dashboard_cockpit(request: Request, month: str | None = None,
                            current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """老板驾驶舱：钱 + 人 + 待办，全部按当前选中仓库统计，按币种分组。"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")

    view = await _selected_dashboard(request,current_user,db,month)
    wh_ids = [w['id'] for w in view['warehouses']]
    from app.services.wallet import day

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
    month_start = date.fromisoformat(view['period']['start_date'])
    month_end = date.fromisoformat(view['period']['end_date'])
    month_str = view['period']['month']
    procurement_paid_rows = [(r['currency'],r['amount']) for r in view['month_card']['procurement_expense']]

    # 复用客户事实：只合计各客户尚欠，不拿其他客户的预收冲抵。
    from app.services.customer_receivables import customer_credit_totals
    receivable = _merge_currency(list((await customer_credit_totals(db,wh_ids)).items()))

    # 待付（应付未付 = amount - paid_amount）
    payable_rows = (await db.execute(
        select(PayableBill.currency, func.coalesce(func.sum(PayableBill.amount - func.coalesce(PayableBill.paid_amount, 0)), 0))
        .outerjoin(PurchaseOrder, PayableBill.purchase_order_id == PurchaseOrder.id)
        .where(PayableBill.warehouse_id.in_(wh_ids), PayableBill.status != "paid", PayableBill.status != "voided",
               (PayableBill.purchase_order_id.is_(None)) | (PurchaseOrder.status == "confirmed"))
        .group_by(PayableBill.currency)
    )).all()
    payable = _merge_currency(payable_rows)

    # 逾期未付
    overdue_rows = (await db.execute(
        select(PayableBill.currency, func.coalesce(func.sum(PayableBill.amount - func.coalesce(PayableBill.paid_amount, 0)), 0))
        .outerjoin(PurchaseOrder, PayableBill.purchase_order_id == PurchaseOrder.id)
        .where(PayableBill.warehouse_id.in_(wh_ids), PayableBill.status != "paid", PayableBill.status != "voided", func.date(PayableBill.due_date) < today,
               (PayableBill.purchase_order_id.is_(None)) | (PurchaseOrder.status == "confirmed"))
        .group_by(PayableBill.currency)
    )).all()
    overdue_payable = _merge_currency(overdue_rows)

    # 账户余额
    from app.services.account_balances import current_account_balances
    payaccts = (await db.execute(select(PaymentAccount).where(
        PaymentAccount.warehouse_id.in_(wh_ids), PaymentAccount.status == "active",
    ))).scalars().all()
    payacct_balances = await current_account_balances(db, payaccts)
    payacct_totals = {}
    for account in payaccts:
        currency = account.currency or "THB"
        payacct_totals[currency] = payacct_totals.get(currency, 0) + payacct_balances[account.id]
    payacct_rows = list(payacct_totals.items())
    fund_rows = (await db.execute(
        select(ExpenseFund.currency, func.coalesce(func.sum(ExpenseFund.remaining_balance), 0))
        .where(ExpenseFund.warehouse_id.in_(wh_ids), ExpenseFund.status == "active")
        .group_by(ExpenseFund.currency)
    )).all()

    # 本月采购异常
    price_anomaly = (await db.execute(
        select(func.count(ProcurementPriceAnomaly.id))
        .where(ProcurementPriceAnomaly.warehouse_id.in_(wh_ids),
               day(db,ProcurementPriceAnomaly.created_at) >= month_start,
               day(db,ProcurementPriceAnomaly.created_at) <= month_end)
    )).scalar() or 0
    non_lowest = (await db.execute(
        select(func.count(ProcurementNonLowestRecord.id))
        .where(ProcurementNonLowestRecord.warehouse_id.in_(wh_ids),
               day(db,ProcurementNonLowestRecord.created_at) >= month_start,
               day(db,ProcurementNonLowestRecord.created_at) <= month_end)
    )).scalar() or 0

    # ── 人 ──
    # 今日出勤
    expected = (await db.execute(
        select(func.count(Employee.id)).where(
            Employee.warehouse_id.in_(wh_ids),
            Employee.status != "resigned",
            Employee.is_deleted == False,
        )
    )).scalar() or 0
    present = (await db.execute(
        select(func.count(func.distinct(ClockInRecord.user_id))).where(
            ClockInRecord.warehouse_id.in_(wh_ids),
            ClockInRecord.clock_date == today,
        )
    )).scalar() or 0
    absent = (await db.execute(
        select(func.count(Absence.id)).where(
            Absence.warehouse_id.in_(wh_ids),
            Absence.absence_date == today,
        )
    )).scalar() or 0

    # Reuse the existing period calculation, clipped to this calendar month.
    # Its weekly caller's full-week convention must not spill into another selected month.
    from app.api.v1.efficiency import _compute_week
    efficiency_by_warehouse = []
    for wh in view['warehouses']:
        item = {'warehouse_id':wh['id'],'warehouse_name':wh['name']}
        try:
            async with db.begin_nested():
                em = await _compute_week(db,wh['id'],month_start,month_end,include_employees=False)
                item.update({key:em[key] for key in ('person_times','order_count','efficiency','standard','below_standard')})
        except Exception:
            item['error'] = '人效加载失败，未将异常当作零'
        efficiency_by_warehouse.append(item)
    efficiency = efficiency_by_warehouse[0] if len(efficiency_by_warehouse)==1 and 'error' not in efficiency_by_warehouse[0] else None

    # 待办数量
    leave_pending = (await db.execute(
        select(func.count(LeaveRequest.id)).where(
            LeaveRequest.warehouse_id.in_(wh_ids), LeaveRequest.status == "pending"
        )
    )).scalar() or 0
    overtime_pending = (await db.execute(
        select(func.count(OvertimeTask.id)).where(
            OvertimeTask.warehouse_id.in_(wh_ids), OvertimeTask.status == "pending"
        )
    )).scalar() or 0
    ef_pending = (await db.execute(
        select(func.count(ExpenseFundItem.id)).join(
            ExpenseFund, ExpenseFundItem.fund_id == ExpenseFund.id
        ).where(
            ExpenseFundItem.review_status == ReviewStatus.PENDING.value,
            ExpenseFund.warehouse_id.in_(wh_ids),
        )
    )).scalar() or 0
    rb_pending = (await db.execute(
        select(func.count(Reimbursement.id)).where(
            Reimbursement.warehouse_id.in_(wh_ids), Reimbursement.status == ReimbStatus.PENDING.value
        )
    )).scalar() or 0
    market_pending = (await db.execute(
        select(func.count(MarketItem.id)).where(
            MarketItem.warehouse_id.in_(wh_ids), MarketItem.status == "pending"
        )
    )).scalar() or 0
    group_pending = (await db.execute(
        select(func.count(GroupOrder.id)).where(
            GroupOrder.warehouse_id.in_(wh_ids), GroupOrder.status == GroupOrderStatus.OPEN.value
        )
    )).scalar() or 0
    expense_approval_pending = 0
    if current_user.role == Role.WAREHOUSE_ADMIN:
        expense_approval_pending = (await db.execute(
            select(func.count(ExpenseApproval.id)).where(
                ExpenseApproval.warehouse_id.in_(wh_ids), ExpenseApproval.status == "pending"
            )
        )).scalar() or 0

    # ── 待办列表 ──
    todos = []

    # 采购审批待办（超门槛 → status=pending）
    po_rows = (await db.execute(
        select(PurchaseOrder.id, PurchaseOrder.order_number, PurchaseOrder.total_amount)
        .where(PurchaseOrder.warehouse_id.in_(wh_ids), PurchaseOrder.status == "pending")
        .order_by(PurchaseOrder.created_at.desc()).limit(20)
    )).all()
    for pid, order_no, total in po_rows:
        todos.append({"type": "purchase_approval", "description": f"采购单 {order_no} 待审批",
                      "link": "/suppliers", "id": pid})

    # 账单待确认（收货有差异）
    bill_rows = (await db.execute(
        select(PayableBill.id, PayableBill.bill_number, PayableBill.amount, PayableBill.confirmed_amount)
        .where(PayableBill.warehouse_id.in_(wh_ids),
               PayableBill.status != "voided",
               ((PayableBill.need_boss_confirm == "true") | ((PayableBill.confirmed_amount.isnot(None)) & (PayableBill.confirmed_amount != PayableBill.amount))))
        .order_by(PayableBill.created_at.desc()).limit(20)
    )).all()
    for bid, bill_no, amount, confirmed in bill_rows:
        todos.append({"type": "bill_confirm", "description": f"账单 {bill_no} 收货有差异待确认", "link": "/payable", "id": bid})

    # 请假待审批（只认在职员工）
    leave_rows = (await db.execute(
        select(LeaveRequest.id, Employee.name)
        .join(Employee, LeaveRequest.employee_id == Employee.id)
        .where(
            LeaveRequest.warehouse_id.in_(wh_ids),
            LeaveRequest.status == "pending",
            Employee.is_deleted == False,
            Employee.status != "resigned",
        )
        .order_by(LeaveRequest.created_at.desc()).limit(20)
    )).all()
    for lid, ename in leave_rows:
        todos.append({"type": "leave", "description": f"{ename} 的请假申请待审批", "link": "/attendance", "id": lid})

    # 加班待确认
    ot_rows = (await db.execute(
        select(OvertimeTask.id, OvertimeTask.date)
        .where(OvertimeTask.warehouse_id.in_(wh_ids), OvertimeTask.status == "pending")
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
               ExpenseFund.warehouse_id.in_(wh_ids))
        .order_by(ExpenseFundItem.created_at.desc()).limit(20)
    )).all()
    for iid, uname in ef_rows:
        todos.append({"type": "expense_fund", "description": f"{uname} 的备用金开销待审核", "link": "/expense-fund", "id": iid})

    # 报销单待审批
    rb_rows = (await db.execute(
        select(Reimbursement.id, User.display_name)
        .join(User, Reimbursement.employee_id == User.id)
        .where(Reimbursement.warehouse_id.in_(wh_ids), Reimbursement.status == ReimbStatus.PENDING.value)
        .order_by(Reimbursement.created_at.desc()).limit(20)
    )).all()
    for rid, uname in rb_rows:
        todos.append({"type": "reimbursement", "description": f"{uname} 的报销单待审批", "link": "/reimbursement", "id": rid})

    # 商品上架待审核
    m_rows = (await db.execute(
        select(MarketItem.id, MarketItem.name, User.display_name)
        .join(User, MarketItem.uploader_id == User.id)
        .where(MarketItem.warehouse_id.in_(wh_ids), MarketItem.status == "pending")
        .order_by(MarketItem.created_at.desc()).limit(20)
    )).all()
    for mid, mname, uname in m_rows:
        todos.append({"type": "market", "description": f"{uname} 上架的 {mname} 待审核", "link": "/market", "id": mid})

    # 待拼单
    g_rows = (await db.execute(
        select(GroupOrder.id, GroupOrder.item_name)
        .where(GroupOrder.warehouse_id.in_(wh_ids), GroupOrder.status == GroupOrderStatus.OPEN.value)
        .order_by(GroupOrder.created_at.desc()).limit(20)
    )).all()
    for gid, gname in g_rows:
        todos.append({"type": "group_order", "description": f"待拼单：{gname}", "link": "/group-order", "id": gid})

    # 费用待审批（仅仓库管理员可见）
    if current_user.role == Role.WAREHOUSE_ADMIN:
        ea_rows = (await db.execute(
            select(ExpenseApproval.id, User.display_name)
            .join(User, ExpenseApproval.applicant_id == User.id)
            .where(ExpenseApproval.warehouse_id.in_(wh_ids), ExpenseApproval.status == "pending")
            .order_by(ExpenseApproval.created_at.desc()).limit(20)
        )).all()
        for aid, aname in ea_rows:
            todos.append({"type": "expense_approval", "description": f"{aname} 的费用申请待审批", "link": "/expense-approvals", "id": aid})

    return {
        "period": view["period"], "warehouses":view["warehouses"], "trends":view["trends"],
        "realtime_at":thai_now().isoformat(),
        "finance": {
            "month": view['month_card'],
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
                "expense": _merge_currency(procurement_paid_rows),
                "price_anomaly_count": price_anomaly,
                "non_lowest_count": non_lowest,
            },
            "recharge_reconciliation": view['recharge_reconciliation'],
        },
        "people": {
            "attendance": {"expected": expected, "present": present, "absent": absent},
            "efficiency": efficiency,
            "efficiency_by_warehouse": efficiency_by_warehouse,
            "todos": {
                "leave_pending": leave_pending,
                "overtime_pending": overtime_pending,
                "expense_fund_pending": ef_pending,
                "reimbursement_pending": rb_pending,
                "market_pending": market_pending,
                "group_order_pending": group_pending,
                "expense_approval_pending": expense_approval_pending,
            },
        },
        "todos": todos,
    }


@router.get("/boss-todos")
async def boss_todos(request: Request, response: Response, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models.employee import Employee
    from app.models.employee_advance import EmployeeAdvance, AdvanceApprovalStatus
    from app.models.overtime import OvertimeTask, OvertimeAssignment
    from app.services.boss_todos import pending_overtime_task, pending_overtime_assignment

    response.headers["Cache-Control"] = "no-store"
    empty = {"advances": {"count": 0, "items": []}, "overtime": {"count": 0, "items": []}}
    if current_user.role == Role.SUPER_ADMIN:
        return empty
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无此操作权限")
    from app.services.warehouse_summary import warehouse_scope
    wh_ids = [w.id for w in await warehouse_scope(db,current_user,request.headers.get('X-Warehouse-ID'))]
    if not wh_ids:
        return empty
    advance_rows = (await db.execute(select(EmployeeAdvance, Employee.name).join(
        Employee, Employee.id == EmployeeAdvance.employee_id,
    ).where(EmployeeAdvance.warehouse_id.in_(wh_ids), Employee.warehouse_id == EmployeeAdvance.warehouse_id,
        EmployeeAdvance.approval_status == AdvanceApprovalStatus.PENDING.value,
        EmployeeAdvance.not_voided(),
    ).order_by(EmployeeAdvance.advance_date, EmployeeAdvance.id))).all()
    if not financial_reader(current_user,'employee_advances'): advance_rows = []
    advances = [{"id": a.id, "warehouse_id": a.warehouse_id, "employee_id": a.employee_id,
                 "employee_name": name, "amount": a.amount, "currency": a.currency or "THB",
                 "date": a.advance_date.isoformat()} for a, name in advance_rows]
    overtime_rows = (await db.execute(select(OvertimeAssignment, OvertimeTask, Employee.name).join(
        OvertimeTask, OvertimeTask.id == OvertimeAssignment.overtime_id,
    ).join(Employee, Employee.id == OvertimeAssignment.employee_id).where(
        OvertimeTask.warehouse_id.in_(wh_ids), Employee.warehouse_id == OvertimeTask.warehouse_id,
        pending_overtime_task(), pending_overtime_assignment(),
    ).order_by(OvertimeTask.date, OvertimeAssignment.id))).all()
    if not (current_user.role == Role.WAREHOUSE_ADMIN or (current_user.role == Role.SUPERVISOR and has_menu(current_user,'overtime'))): overtime_rows = []
    overtime_items = [{"id": a.id, "task_id": task.id, "warehouse_id": task.warehouse_id,
                       "employee_id": a.employee_id, "employee_name": name, "date": task.date.isoformat(),
                       "planned_hours": task.hours, "has_dispute": bool(a.has_dispute)} for a, task, name in overtime_rows]
    return {"advances": {"count": len(advances), "items": advances},
            "overtime": {"count": len(overtime_items), "items": overtime_items}}
