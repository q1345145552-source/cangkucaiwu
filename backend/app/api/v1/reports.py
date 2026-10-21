from app.core.retired_entries import require_operating_entries_enabled
from fastapi import APIRouter, Depends, HTTPException, Query, Request
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

from app.services.internal_transfers import transfer_summary, append_transfer_sheet
from app.services.report_scope import ReportScope, selected_report_scope, scoped_query, payable_query

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
    return {c:round(float(n),2) for c,n in out.items()}


def to_excel(headers, rows, sheet_name="Sheet1", transfers=None):
    wb = Workbook(); ws = wb.active; ws.title = sheet_name
    fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    fw = Font(bold=True, color="FFFFFF")
    for col, h in enumerate(headers, 1):
        c = ws.cell(row=1, column=col, value=h); c.font = fw; c.fill = fill; c.alignment = Alignment(horizontal="center")
    for r, row in enumerate(rows, 2):
        for c, val in enumerate(row, 1): ws.cell(row=r, column=c, value=val)
    if transfers is not None: append_transfer_sheet(wb, transfers)
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
    start_date: str = None, end_date: str = None,
    scope: ReportScope = Depends(selected_report_scope),
    current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reports"].label)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    from sqlalchemy import case
    from app.services.wallet import totals, grouped_totals
    async def preview(query, model, value, *, basis="period"):
        cur = func.coalesce(model.currency, "THB")
        rows = (await db.execute(query.with_only_columns(cur,func.sum(value),func.count(model.id))
            .group_by(cur).order_by(cur))).all()
        amounts = {c:round(float(n or 0),2) for c,n,count in rows}
        return {"preview_by_currency":amounts,
            "preview":next(iter(amounts.values())) if len(amounts)==1 else None if amounts else 0,
            "count":sum(count for c,n,count in rows),"period_basis":basis}
    previews = {}
    previews["recharge-summary"] = await preview(scoped_query(db,scope,RechargeDeclaration,RechargeDeclaration.declare_date),
        RechargeDeclaration,RechargeDeclaration.amount)
    previews["incoming-summary"] = await preview(scoped_query(db,scope,IncomingFlow,IncomingFlow.received_date),IncomingFlow,IncomingFlow.amount)
    summary = grouped_totals(await totals(db,scope.warehouse_ids,scope.start,scope.end))
    previews["income-expense"] = {**summary,"preview":summary["net"],"preview_by_currency":summary["net_by_currency"],"period_basis":"period"}
    # Same confirmed-order and payable-state filters as the detail's pending total.
    pending = case((PayableBill.status.in_(["pending","partially_paid","overdue"]),
        PayableBill.amount-func.coalesce(PayableBill.paid_amount,0)),else_=0)
    previews["payable"] = await preview(payable_query(db,scope),PayableBill,pending)
    previews["expense-fund"] = await preview(scoped_query(db,scope,ExpenseFund),ExpenseFund,
        case((ExpenseFund.status=="active",ExpenseFund.remaining_balance),else_=0),basis="current")
    previews["reimbursement"] = await preview(scoped_query(db,scope,Reimbursement,Reimbursement.submit_date),Reimbursement,Reimbursement.total_amount)
    # Current receivable positions retain the detail's customer set and existing formula.
    credit = await credit_report(current_user=current_user,db=db,scope=scope)
    amounts = credit["total_debt_by_currency"]
    previews["credit"] = {"preview_by_currency":amounts,"preview":credit["total_debt"],
        "count":len(credit["data"]),"period_basis":"current"}
    differences = await reconciliation_diff_report(current_user=current_user,db=db,scope=scope)
    previews["reconciliation-diff"] = {"preview_by_currency":differences["total_diff_by_currency"],
        "preview":differences["total_diff"],"count":differences["total_count"],"period_basis":"month"}
    return {"previews":previews,"start_date":str(scope.start),"end_date":str(scope.end),"warehouse_ids":scope.warehouse_ids}

# ===== 1. 充值汇总 =====
@router.get("/recharge-summary")
async def recharge_summary(start_date: str = None, end_date: str = None, warehouse_id: int = None, format: str = "json",
                            scope: ReportScope = Depends(selected_report_scope),
                            current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reports"].label)), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    wh_ids = scope.warehouse_ids
    query = scoped_query(db,scope,RechargeDeclaration,RechargeDeclaration.declare_date)
    result = await db.execute(query.order_by(RechargeDeclaration.declare_date.desc()))
    records = result.scalars().all()
    data = [{"日期": r.declare_date.strftime("%Y-%m-%d") if r.declare_date else "", "金额": r.amount, "币种": r.currency, "状态": _(r.match_status)} for r in records]
    headers = ["日期","金额","币种","状态"]
    if format == "excel": return to_excel(headers, [[r[h] for h in headers] for r in data], "充值汇总")
    return {"data": data, "total_amount_by_currency": _sum_by_currency(records), "total_count": len(records)}

# ===== 2. 到账汇总 =====
@router.get("/incoming-summary")
async def incoming_summary(start_date: str = None, end_date: str = None, warehouse_id: int = None, format: str = "json",
                            scope: ReportScope = Depends(selected_report_scope),
                            current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reports"].label)), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    wh_ids = scope.warehouse_ids
    query = scoped_query(db,scope,IncomingFlow,IncomingFlow.received_date)
    result = await db.execute(query.order_by(IncomingFlow.received_date.desc()))
    records = result.scalars().all()
    data = [{"日期": r.received_date.strftime("%Y-%m-%d") if r.received_date else "", "金额": r.amount, "币种": r.currency, "付款方": r.payer_name or ""} for r in records]
    headers = ["日期","金额","币种","付款方"]
    if format == "excel": return to_excel(headers, [[r[h] for h in headers] for r in data], "到账汇总")
    return {"data": data, "total_amount_by_currency": _sum_by_currency(records), "total_count": len(records)}

# ===== 3. 收支报表 =====
@router.get("/income-expense", dependencies=[Depends(require_non_labor)])
async def income_expense_report(start_date: str = None, end_date: str = None, warehouse_id: int = None, format: str = "json",
                                 month: str = None, year: str = None, request: Request = None,
                                 scope: ReportScope = Depends(selected_report_scope),
                                 current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reports"].label)), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    wh_ids = scope.warehouse_ids
    from app.services.wallet import flow_query, grouped_totals
    start, end = scope.start, scope.end
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
    transfers = await transfer_summary(db, wh_ids, start, end)
    if format == "excel": return to_excel(headers, [[r[h] for h in headers] for r in data], "收支报表", transfers=transfers)
    return {"data": data, "internal_transfers": transfers, **result, "total_income_by_currency": result["income_by_currency"],
        "total_expense_by_currency": result["expense_by_currency"],
        "recharge_income_by_currency": dict(received), "other_income_by_currency": dict(other)}

# ===== 4. 应付报表 =====
@router.get("/payable")
async def payable_report(start_date: str = None, end_date: str = None, warehouse_id: int = None, format: str = "json",
                          scope: ReportScope = Depends(selected_report_scope),
                          current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reports"].label)), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    wh_ids = scope.warehouse_ids
    query = payable_query(db,scope)
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
                               scope: ReportScope = Depends(selected_report_scope),
                               current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reports"].label)), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    wh_ids = scope.warehouse_ids
    query = scoped_query(db,scope,ExpenseFund)
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
                                scope: ReportScope = Depends(selected_report_scope),
                                current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reports"].label)), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    wh_ids = scope.warehouse_ids
    query = scoped_query(db,scope,Reimbursement,Reimbursement.submit_date)
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
                         scope: ReportScope = Depends(selected_report_scope),
                         current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reports"].label)), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    wh_ids = scope.warehouse_ids
    query = scoped_query(db,scope,CreditCustomer)
    result = await db.execute(query.order_by(CreditCustomer.created_at.desc()))
    credits = result.scalars().all()
    from app.services.customer_receivables import positions
    from app.models.customer import Customer
    balances = await positions(db,wh_ids,[c.customer_id for c in credits])
    customers = {c.id:c for c in (await db.execute(select(Customer).where(Customer.id.in_({r.customer_id for r in credits})))).scalars()}
    data=[]
    for c in credits:
        cur = c.currency or (customers[c.customer_id].default_currency if c.customer_id in customers else None) or 'THB'
        debt=balances.get(c.customer_id,{}).get(cur,{}).get('outstanding',0)
        data.append({'客户编号':c.customer_id,'币种':cur,'额度':c.credit_limit or 0,'欠款':debt,
            '逾期天数':c.overdue_days or 0,'状态':_(c.status)})
    debt_by_currency={}
    for groups in balances.values():
        for cur,group in groups.items(): debt_by_currency[cur]=round(debt_by_currency.get(cur,0)+group['outstanding'],2)
    total_debt = next(iter(debt_by_currency.values())) if len(debt_by_currency)==1 else None if debt_by_currency else 0
    overdue_count = sum(1 for c in credits if (c.overdue_days or 0) > 0)
    headers = ["客户编号","币种","额度","欠款","逾期天数","状态"]
    if format == "excel": return to_excel(headers, [[r[h] for h in headers] for r in data], "账期报表")
    return {"data": data, "total_debt_by_currency":debt_by_currency,"total_debt": total_debt, "overdue_count": overdue_count}

# ===== 8. 对账差异 =====
@router.get("/reconciliation-diff")
async def reconciliation_diff_report(start_date: str = None, end_date: str = None, warehouse_id: int = None, format: str = "json",
                                      scope: ReportScope = Depends(selected_report_scope),
                                      current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reports"].label)), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    from sqlalchemy import and_, case
    r,f,d = ReconciliationResult,IncomingFlow,RechargeDeclaration
    cur = case((and_(f.currency.is_not(None),d.currency.is_not(None),f.currency!=d.currency),"UNKNOWN"),
        else_=func.coalesce(f.currency,d.currency,"UNKNOWN"))
    query = (scoped_query(db,scope,r)
        .outerjoin(f,and_(f.id==r.flow_id,f.warehouse_id==r.warehouse_id))
        .outerjoin(d,and_(d.id==r.declaration_id,d.warehouse_id==r.warehouse_id)))
    query = query.where(r.reconciliation_month>=scope.start.strftime("%Y-%m"),r.reconciliation_month<=scope.end.strftime("%Y-%m"))
    records = (await db.execute(query.add_columns(cur.label("currency")).order_by(r.id))).all()
    data = [{"月份":item.reconciliation_month or "","状态":_(item.match_status),"差额":item.amount_diff or 0,
        "币种":currency,"处理说明":item.handling_note or ""} for item,currency in records]
    amounts={}
    for item,currency in records:amounts[currency]=round(amounts.get(currency,0)+abs(item.amount_diff or 0),2)
    total_diff=next(iter(amounts.values())) if len(amounts)==1 else None if amounts else 0
    headers = ["月份","状态","差额","币种","处理说明"]
    if format=="excel":return to_excel(headers,[[row[h] for h in headers] for row in data],"对账差异")
    return {"data":data,"diff_count":sum(1 for item,c in records if item.amount_diff),
        "total_diff":total_diff,"total_diff_by_currency":amounts,"total_count":len(records)}


@router.get("/operations", dependencies=[Depends(require_operating_entries_enabled)])
async def operating_report(request: Request, month: str = None, start_date: str = None, end_date: str = None,
    customer_id: int = None, currency: str = None, warehouse_id: int = None,
    shipment_page: int = Query(1,ge=1), cost_page: int = Query(1,ge=1), page_size: int = Query(20,ge=1,le=200),
    current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reports"].label)), db: AsyncSession = Depends(get_db)):
    from app.services.money_period import money_period
    from app.services.warehouse_summary import warehouse_scope
    from app.services.operating_report import report
    if currency not in (None,'THB','CNY'):raise HTTPException(400,'不支持的币种')
    scope=await warehouse_scope(db,current_user,request.headers.get('X-Warehouse-ID'),warehouse_id=warehouse_id)
    today=thai_today()
    from calendar import monthrange
    start,end=money_period(month,start_date,end_date,default_start=today.replace(day=1),
        default_end=today.replace(day=monthrange(today.year,today.month)[1]))
    return await report(db,[w.id for w in scope],start,end,customer_id=customer_id,currency=currency,
        shipment_page=shipment_page,cost_page=cost_page,page_size=page_size)
