from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.timezone import thai_now, thai_today
from datetime import datetime, timedelta
from app.database import get_db
from app.models.recharge import RechargeDeclaration, IncomingFlow, ReconciliationResult
from app.models.income_expense import IncomeRecord, ExpenseRecord
from app.services.fund_disbursement import cost_record_filter
from app.models.expense_fund import ExpenseFund
from app.models.reimbursement import Reimbursement
from app.models.payable import PayableBill
from app.models.supplier import PurchaseOrder
from app.models.credit import CreditCustomer
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role, check_staff_permission, require_non_labor
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
import io
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill

router = APIRouter()

STATUS_LABELS = {
    "pending": "待处理", "matched": "已匹配", "unmatched": "未匹配",
    "paid": "已付款", "active": "正常", "approved": "已通过",
    "rejected": "已驳回", "partially_approved": "部分通过",
    "fund_linked": "转入备用金审核", "partially_paid": "部分付款",
    "overdue": "逾期", "paused": "暂停", "cancelled": "已取消",
    "settled": "已结清",
}

def _(s): return STATUS_LABELS.get(s, s)

# Map Chinese sheet names to safe English filenames
_FILENAME_MAP = {
    "充值汇总": "recharge_summary", "到账汇总": "incoming_summary",
    "收支报表": "income_expense", "应付报表": "payable",
    "备用金报表": "expense_fund", "报销报表": "reimbursement",
    "账期报表": "credit", "对账差异": "reconciliation_diff",
}


def _date_cond(col, start_date: str = None, end_date: str = None):
    """返回 [start_date, end_date) 的日期过滤条件列表（结束日期当天完整包含）。"""
    conds = []
    if start_date:
        conds.append(col >= datetime.strptime(start_date, "%Y-%m-%d"))
    if end_date:
        conds.append(col < datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1))
    return conds


def _apply_date(query, col, start_date, end_date):
    for c in _date_cond(col, start_date, end_date):
        query = query.where(c)
    return query


def _sum_by_currency(rows, attr: str = "amount"):
    """按币种汇总 rows 的 attr 字段（币种缺省按 THB）。"""
    out: dict = {}
    for r in rows:
        c = getattr(r, "currency", None) or "THB"
        out[c] = out.get(c, 0) + (getattr(r, attr, 0) or 0)
    return out


def to_excel(headers, rows, sheet_name="Sheet1"):
    wb = Workbook(); ws = wb.active; ws.title = sheet_name
    fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    fw = Font(bold=True, color="FFFFFF")
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=col, value=h); c.font = fw; c.fill = fill; c.alignment = Alignment(horizontal="center")
    for r, row in enumerate(rows, 2):
        for c, val in enumerate(row, 1): ws.cell(row=r, column=c, value=val)
    output = io.BytesIO(); wb.save(output); output.seek(0)
    safe_name = _FILENAME_MAP.get(sheet_name, sheet_name.replace(" ", "_"))
    filename = f"{safe_name}_{thai_now().strftime('%Y%m%d')}.xlsx"
    # Use RFC 5987 encoding for safe filename delivery
    from urllib.parse import quote
    encoded = quote(filename)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"})



# ===== 0. 报表预览（所有卡片一次性返回） =====
@router.get("/previews", dependencies=[Depends(require_non_labor)])
async def report_previews(
    start_date: str = None,
    end_date: str = None,
    current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reports"].label)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    wh_ids = get_wh_ids(current_user)

    previews = {}

    # 1. 充值汇总
    q = select(func.coalesce(func.sum(RechargeDeclaration.amount), 0), func.count(RechargeDeclaration.id))
    q = q.where(RechargeDeclaration.warehouse_id.in_(wh_ids))
    q = _apply_date(q, RechargeDeclaration.declare_date, start_date, end_date)
    total_amt, count = (await db.execute(q)).first()
    previews["recharge-summary"] = {"preview": float(total_amt or 0), "count": count or 0}

    # 2. 到账汇总
    q = select(func.coalesce(func.sum(IncomingFlow.amount), 0), func.count(IncomingFlow.id))
    q = q.where(IncomingFlow.warehouse_id.in_(wh_ids))
    q = _apply_date(q, IncomingFlow.received_date, start_date, end_date)
    total_amt, count = (await db.execute(q)).first()
    previews["incoming-summary"] = {"preview": float(total_amt or 0), "count": count or 0}

    # 收支预览与详情共用真实收付口径，不混加币种。
    from app.services.wallet import totals, grouped_totals
    from app.services.cost_funds_debt import dates
    start, end = dates(start_date or "1900-01-01", end_date or "9999-12-31")
    summary = grouped_totals(await totals(db, wh_ids, start, end))
    previews["income-expense"] = {**summary, "preview": summary["net"],
        "preview_by_currency": summary["net_by_currency"]}
    # 4. 应付报表
    q = select(func.coalesce(func.sum(PayableBill.amount - func.coalesce(PayableBill.paid_amount, 0)), 0), func.count(PayableBill.id))
    q = q.outerjoin(PurchaseOrder, PayableBill.purchase_order_id == PurchaseOrder.id)
    q = q.where(PayableBill.warehouse_id.in_(wh_ids), PayableBill.status != "voided",
                (PayableBill.purchase_order_id.is_(None)) | (PurchaseOrder.status == "confirmed"))
    q = _apply_date(q, PayableBill.due_date, start_date, end_date)
    pending, count = (await db.execute(q)).first()
    previews["payable"] = {"preview": float(pending or 0), "count": count or 0}

    # 5. 备用金报表（当前状态，不按时间）
    q = select(func.coalesce(func.sum(ExpenseFund.remaining_balance), 0), func.count(ExpenseFund.id))
    q = q.where(ExpenseFund.warehouse_id.in_(wh_ids))
    q = q.where(ExpenseFund.status == "active")
    in_transit, count = (await db.execute(q)).first()
    previews["expense-fund"] = {"preview": float(in_transit or 0), "count": count or 0}

    # 6. 报销报表
    q = select(func.coalesce(func.sum(Reimbursement.total_amount), 0), func.count(Reimbursement.id))
    q = q.where(Reimbursement.warehouse_id.in_(wh_ids))
    q = _apply_date(q, Reimbursement.submit_date, start_date, end_date)
    total_amt, count = (await db.execute(q)).first()
    previews["reimbursement"] = {"preview": float(total_amt or 0), "count": count or 0}

    # 7. 账期报表（当前状态，不按时间）
    q = select(func.coalesce(func.sum(CreditCustomer.current_debt), 0), func.count(CreditCustomer.id))
    q = q.where(CreditCustomer.warehouse_id.in_(wh_ids))
    total_debt, count = (await db.execute(q)).first()
    previews["credit"] = {"preview": float(total_debt or 0), "count": count or 0}

    # 8. 对账差异（按月份字符串范围）
    q = select(func.coalesce(func.sum(func.abs(ReconciliationResult.amount_diff)), 0), func.count(ReconciliationResult.id))
    q = q.where(ReconciliationResult.warehouse_id.in_(wh_ids))
    if start_date: q = q.where(ReconciliationResult.reconciliation_month >= start_date[:7])
    if end_date: q = q.where(ReconciliationResult.reconciliation_month <= end_date[:7])
    total_diff, count = (await db.execute(q)).first()
    previews["reconciliation-diff"] = {"preview": float(total_diff or 0), "count": count or 0}

    preview_models = {
        "recharge-summary": (RechargeDeclaration, RechargeDeclaration.amount, RechargeDeclaration.currency, RechargeDeclaration.declare_date, []),
        "incoming-summary": (IncomingFlow, IncomingFlow.amount, IncomingFlow.currency, IncomingFlow.received_date, []),
        "payable": (PayableBill, PayableBill.amount - func.coalesce(PayableBill.paid_amount, 0), PayableBill.currency, PayableBill.due_date, [PayableBill.status != "voided"]),
        "expense-fund": (ExpenseFund, ExpenseFund.remaining_balance, ExpenseFund.currency, None, [ExpenseFund.status == "active"]),
        "reimbursement": (Reimbursement, Reimbursement.total_amount, Reimbursement.currency, Reimbursement.submit_date, []),
    }
    for key, (model, value, cur, date_col, extra) in preview_models.items():
        query = select(cur, func.sum(value)).where(model.warehouse_id.in_(wh_ids), *extra).group_by(cur)
        if date_col is not None: query = _apply_date(query, date_col, start_date, end_date)
        amounts = {c or "THB": round(float(n or 0), 2) for c, n in (await db.execute(query)).all()}
        previews[key]["preview_by_currency"] = amounts
        previews[key]["preview"] = next(iter(amounts.values())) if len(amounts) == 1 else 0 if not amounts else None
    from app.models.customer import Customer
    credit_amounts = {c or "THB": round(float(n or 0), 2) for c,n in (await db.execute(select(
        Customer.default_currency, func.sum(CreditCustomer.current_debt)).join(Customer, Customer.id == CreditCustomer.customer_id).where(
        CreditCustomer.warehouse_id.in_(wh_ids)).group_by(Customer.default_currency))).all()}
    previews["credit"]["preview_by_currency"] = credit_amounts
    previews["credit"]["preview"] = next(iter(credit_amounts.values())) if len(credit_amounts) == 1 else None if credit_amounts else 0
    return {"previews": previews, "start_date": start_date, "end_date": end_date}

# ===== 1. 充值汇总 =====
@router.get("/recharge-summary")
async def recharge_summary(start_date: str = None, end_date: str = None, warehouse_id: int = None, format: str = "json",
                            current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reports"].label)), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(RechargeDeclaration)
    wh_ids = get_wh_ids(current_user)
    query = query.where(RechargeDeclaration.warehouse_id.in_(wh_ids))
    query = _apply_date(query, RechargeDeclaration.declare_date, start_date, end_date)
    if warehouse_id: query = query.where(RechargeDeclaration.warehouse_id == warehouse_id)
    result = await db.execute(query.order_by(RechargeDeclaration.declare_date.desc()))
    records = result.scalars().all()
    data = [{"日期": r.declare_date.strftime("%Y-%m-%d") if r.declare_date else "", "金额": r.amount, "币种": r.currency, "状态": _(r.match_status)} for r in records]
    headers = ["日期","金额","币种","状态"]
    if format == "excel": return to_excel(headers, [[r[h] for h in headers] for r in data], "充值汇总")
    return {"data": data, "total_amount_by_currency": _sum_by_currency(records), "total_count": len(records)}

# ===== 2. 到账汇总 =====
@router.get("/incoming-summary")
async def incoming_summary(start_date: str = None, end_date: str = None, warehouse_id: int = None, format: str = "json",
                            current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reports"].label)), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(IncomingFlow)
    wh_ids = get_wh_ids(current_user)
    query = query.where(IncomingFlow.warehouse_id.in_(wh_ids))
    query = _apply_date(query, IncomingFlow.received_date, start_date, end_date)
    if warehouse_id: query = query.where(IncomingFlow.warehouse_id == warehouse_id)
    result = await db.execute(query.order_by(IncomingFlow.received_date.desc()))
    records = result.scalars().all()
    data = [{"日期": r.received_date.strftime("%Y-%m-%d") if r.received_date else "", "金额": r.amount, "币种": r.currency, "付款方": r.payer_name or ""} for r in records]
    headers = ["日期","金额","币种","付款方"]
    if format == "excel": return to_excel(headers, [[r[h] for h in headers] for r in data], "到账汇总")
    return {"data": data, "total_amount_by_currency": _sum_by_currency(records), "total_count": len(records)}

# ===== 3. 收支报表 =====
@router.get("/income-expense", dependencies=[Depends(require_non_labor)])
async def income_expense_report(start_date: str = None, end_date: str = None, warehouse_id: int = None, format: str = "json",
                                 current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reports"].label)), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    wh_ids = get_wh_ids(current_user)
    from app.services.wallet import flow_query, grouped_totals
    from app.services.cost_funds_debt import dates
    wh_ids = [warehouse_id] if warehouse_id in wh_ids else wh_ids
    if warehouse_id and warehouse_id not in get_wh_ids(current_user): raise HTTPException(403, "无权访问其他仓库")
    start, end = dates(start_date or "1900-01-01", end_date or "9999-12-31")
    q = flow_query(db, wh_ids)
    rows = (await db.execute(select(q).where(q.c.date >= start, q.c.date <= end,
        q.c.status == "active", q.c.is_internal_transfer.is_(False)).order_by(q.c.date.desc()))).mappings().all()
    data = [{"类型": "收入" if r["type"] == "income" else "支出", "日期": str(r["date"]),
        "金额": float(r["amount"]), "币种": r["currency"], "备注": r["remark"] or r["source_label"]} for r in rows]
    from collections import defaultdict
    totals = defaultdict(float)
    received, other = defaultdict(float), defaultdict(float)
    for r in rows:
        totals[(r["currency"], r["type"])] += float(r["amount"])
        if r["type"] == "income":
            (received if r["source"] == "incoming" else other)[r["currency"]] += float(r["amount"])
    result = grouped_totals([(c, kind, n) for (c, kind), n in totals.items()])
    headers = ["类型", "日期", "金额", "币种", "备注"]
    if format == "excel": return to_excel(headers, [[r[h] for h in headers] for r in data], "收支报表")
    return {"data": data, **result, "total_income_by_currency": result["income_by_currency"],
        "total_expense_by_currency": result["expense_by_currency"],
        "recharge_income_by_currency": dict(received), "other_income_by_currency": dict(other)}

# ===== 4. 应付报表 =====
@router.get("/payable")
async def payable_report(start_date: str = None, end_date: str = None, warehouse_id: int = None, format: str = "json",
                          current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reports"].label)), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(PayableBill)
    wh_ids = get_wh_ids(current_user)
    query = query.outerjoin(PurchaseOrder, PayableBill.purchase_order_id == PurchaseOrder.id)
    query = query.where(PayableBill.warehouse_id.in_(wh_ids), PayableBill.status != "voided",
                        (PayableBill.purchase_order_id.is_(None)) | (PurchaseOrder.status == "confirmed"))
    query = _apply_date(query, PayableBill.due_date, start_date, end_date)
    if warehouse_id: query = query.where(PayableBill.warehouse_id == warehouse_id)
    result = await db.execute(query.order_by(PayableBill.due_date))
    bills = result.scalars().all()
    data = [{"账单号": b.bill_number or "", "到期日": b.due_date.strftime("%Y-%m-%d") if b.due_date else "", "金额": b.amount or 0,
             "已付": b.paid_amount or 0, "币种": b.currency or "THB", "状态": _(b.status)} for b in bills]
    pending_total_by_currency: dict = {}
    for b in bills:
        if b.status in ("pending", "partially_paid", "overdue"):
            c = b.currency or "THB"
            pending_total_by_currency[c] = pending_total_by_currency.get(c, 0) + (b.amount - (b.paid_amount or 0))
    overdue_count = sum(1 for b in bills if b.status == "overdue")
    headers = ["账单号","到期日","金额","已付","币种","状态"]
    if format == "excel": return to_excel(headers, [[r[h] for h in headers] for r in data], "应付报表")
    return {"data": data, "total_pending_by_currency": pending_total_by_currency, "overdue_count": overdue_count, "total_count": len(bills)}

# ===== 5. 备用金报表（当前状态，不按时间） =====
@router.get("/expense-fund")
async def expense_fund_report(warehouse_id: int = None, format: str = "json",
                               current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reports"].label)), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(ExpenseFund)
    wh_ids = get_wh_ids(current_user)
    query = query.where(ExpenseFund.warehouse_id.in_(wh_ids))
    if warehouse_id: query = query.where(ExpenseFund.warehouse_id == warehouse_id)
    result = await db.execute(query.order_by(ExpenseFund.created_at.desc()))
    funds = result.scalars().all()
    data = [{"用途": f.purpose or "", "金额": f.amount or 0, "余额": f.remaining_balance or 0, "币种": f.currency or "THB", "状态": _(f.status)} for f in funds]
    in_transit_by_currency: dict = {}
    for f in funds:
        if f.status == "active":
            c = f.currency or "THB"
            in_transit_by_currency[c] = in_transit_by_currency.get(c, 0) + (f.remaining_balance or 0)
    headers = ["用途","金额","余额","币种","状态"]
    if format == "excel": return to_excel(headers, [[r[h] for h in headers] for r in data], "备用金报表")
    return {"data": data, "in_transit_total_by_currency": in_transit_by_currency, "total_count": len(funds)}

# ===== 6. 报销报表 =====
@router.get("/reimbursement")
async def reimbursement_report(start_date: str = None, end_date: str = None, warehouse_id: int = None, format: str = "json",
                                current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reports"].label)), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(Reimbursement)
    wh_ids = get_wh_ids(current_user)
    query = query.where(Reimbursement.warehouse_id.in_(wh_ids))
    query = _apply_date(query, Reimbursement.submit_date, start_date, end_date)
    if warehouse_id: query = query.where(Reimbursement.warehouse_id == warehouse_id)
    result = await db.execute(query.order_by(Reimbursement.submit_date.desc()))
    reimbs = result.scalars().all()
    data = [{"日期": r.submit_date.strftime("%Y-%m-%d") if r.submit_date else "", "金额": r.total_amount or 0,
             "币种": r.currency or "THB", "状态": _(r.status)} for r in reimbs]
    headers = ["日期","金额","币种","状态"]
    if format == "excel": return to_excel(headers, [[r[h] for h in headers] for r in data], "报销报表")
    return {"data": data, "total_amount_by_currency": _sum_by_currency(reimbs, "total_amount"), "total_count": len(reimbs)}

# ===== 7. 账期报表（当前状态，不按时间） =====
@router.get("/credit")
async def credit_report(warehouse_id: int = None, format: str = "json",
                         current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reports"].label)), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(CreditCustomer)
    wh_ids = get_wh_ids(current_user)
    query = query.where(CreditCustomer.warehouse_id.in_(wh_ids))
    if warehouse_id: query = query.where(CreditCustomer.warehouse_id == warehouse_id)
    result = await db.execute(query.order_by(CreditCustomer.created_at.desc()))
    credits = result.scalars().all()
    data = [{"额度": c.credit_limit or 0, "欠款": c.current_debt or 0,
             "逾期天数": c.overdue_days or 0, "状态": _(c.status)} for c in credits]
    total_debt = sum(c.current_debt or 0 for c in credits)
    overdue_count = sum(1 for c in credits if (c.overdue_days or 0) > 0)
    headers = ["额度","欠款","逾期天数","状态"]
    if format == "excel": return to_excel(headers, [[r[h] for h in headers] for r in data], "账期报表")
    return {"data": data, "total_debt": total_debt, "overdue_count": overdue_count}

# ===== 8. 对账差异 =====
@router.get("/reconciliation-diff")
async def reconciliation_diff_report(start_date: str = None, end_date: str = None, warehouse_id: int = None, format: str = "json",
                                      current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reports"].label)), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    wh_ids = get_wh_ids(current_user)
    query = select(ReconciliationResult)
    if start_date: query = query.where(ReconciliationResult.reconciliation_month >= start_date[:7])
    if end_date: query = query.where(ReconciliationResult.reconciliation_month <= end_date[:7])
    query = query.where(ReconciliationResult.warehouse_id.in_(wh_ids))
    if warehouse_id: query = query.where(ReconciliationResult.warehouse_id == warehouse_id)
    result = await db.execute(query.order_by(ReconciliationResult.id))
    records = result.scalars().all()
    data = [{"月份": r.reconciliation_month or "", "状态": _(r.match_status), "差额": r.amount_diff or 0, "处理说明": r.handling_note or ""} for r in records]
    diff_count = sum(1 for r in records if (r.amount_diff or 0) != 0)
    total_diff = sum(abs(r.amount_diff or 0) for r in records)
    headers = ["月份","状态","差额","处理说明"]
    if format == "excel": return to_excel(headers, [[r[h] for h in headers] for r in data], "对账差异")
    return {"data": data, "diff_count": diff_count, "total_diff": total_diff}
