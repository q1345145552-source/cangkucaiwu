from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from app.database import get_db
from app.models.recharge import RechargeDeclaration, IncomingFlow, ReconciliationResult
from app.models.income_expense import IncomeRecord, ExpenseRecord
from app.models.expense_fund import ExpenseFund
from app.models.reimbursement import Reimbursement
from app.models.payable import PayableBill
from app.models.credit import CreditCustomer
from app.models.user import User
from app.core.permissions import get_current_user, Role
import io
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill

router = APIRouter()

def get_wh_filter(user: User):
    if user.role == Role.SUPER_ADMIN:
        return None
    return user.warehouse_id

def to_excel(headers, rows, sheet_name="Sheet1"):
    wb = Workbook()
    ws = wb.active; ws.title = sheet_name
    header_font = Font(bold=True)
    header_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    header_font_white = Font(bold=True, color="FFFFFF")
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font_white; cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    for r, row in enumerate(rows, 2):
        for c, val in enumerate(row, 1):
            ws.cell(row=r, column=c, value=val)
    output = io.BytesIO()
    wb.save(output); output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": f"attachment; filename={sheet_name}_{datetime.now().strftime('%Y%m%d')}.xlsx"})

@router.get("/recharge-summary")
async def recharge_summary(month: str = None, warehouse_id: int = None, format: str = "json",
                            current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = select(RechargeDeclaration)
    wh = get_wh_filter(current_user)
    if wh: query = query.where(RechargeDeclaration.warehouse_id == wh)
    if month: query = query.where(func.to_char(RechargeDeclaration.declare_date, 'YYYY-MM') == month)
    if warehouse_id: query = query.where(RechargeDeclaration.warehouse_id == warehouse_id)
    result = await db.execute(query.order_by(RechargeDeclaration.declare_date.desc()))
    records = result.scalars().all()
    data = [{"id": r.id, "date": str(r.declare_date), "amount": r.amount, "currency": r.currency, "status": r.match_status} for r in records]
    if format == "excel":
        return to_excel(["ID", "日期", "金额", "币种", "状态"], [[r["id"], r["date"], r["amount"], r["currency"], r["status"]] for r in data], "充值汇总")
    return {"data": data, "total_amount": sum(r["amount"] for r in data)}

@router.get("/incoming-summary")
async def incoming_summary(month: str = None, warehouse_id: int = None, format: str = "json",
                            current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = select(IncomingFlow)
    wh = get_wh_filter(current_user)
    if wh: query = query.where(IncomingFlow.warehouse_id == wh)
    if month: query = query.where(func.to_char(IncomingFlow.received_date, 'YYYY-MM') == month)
    if warehouse_id: query = query.where(IncomingFlow.warehouse_id == warehouse_id)
    result = await db.execute(query.order_by(IncomingFlow.received_date.desc()))
    records = result.scalars().all()
    data = [{"id": r.id, "date": str(r.received_date), "amount": r.amount, "currency": r.currency, "payer": r.payer_name} for r in records]
    if format == "excel":
        return to_excel(["ID", "日期", "金额", "币种", "付款方"], [[r["id"], r["date"], r["amount"], r["currency"], r["payer"]] for r in data], "到账汇总")
    return {"data": data, "total_amount": sum(r["amount"] for r in data)}

@router.get("/income-expense")
async def income_expense_report(month: str = None, warehouse_id: int = None, format: str = "json",
                                 current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    wh = get_wh_filter(current_user)
    iq = select(IncomeRecord); eq = select(ExpenseRecord)
    if wh: iq = iq.where(IncomeRecord.warehouse_id == wh); eq = eq.where(ExpenseRecord.warehouse_id == wh)
    if month: iq = iq.where(func.to_char(IncomeRecord.income_date, 'YYYY-MM') == month); eq = eq.where(func.to_char(ExpenseRecord.expense_date, 'YYYY-MM') == month)
    if warehouse_id: iq = iq.where(IncomeRecord.warehouse_id == warehouse_id); eq = eq.where(ExpenseRecord.warehouse_id == warehouse_id)
    incomes = (await db.execute(iq)).scalars().all()
    expenses = (await db.execute(eq)).scalars().all()
    total_in = sum(r.amount for r in incomes)
    total_out = sum(r.amount for r in expenses)
    data = [{"type": "income", "date": str(r.income_date), "amount": r.amount, "currency": r.currency, "remark": r.remark} for r in incomes] + \
           [{"type": "expense", "date": str(r.expense_date), "amount": r.amount, "currency": r.currency, "remark": r.remark} for r in expenses]
    data.sort(key=lambda x: x["date"], reverse=True)
    if format == "excel":
        return to_excel(["类型", "日期", "金额", "币种", "备注"], [[r["type"], r["date"], r["amount"], r["currency"], r["remark"]] for r in data], "收支报表")
    return {"data": data, "total_income": float(total_in), "total_expense": float(total_out), "net": float(total_in - total_out)}

@router.get("/payable")
async def payable_report(month: str = None, warehouse_id: int = None, format: str = "json",
                         current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = select(PayableBill)
    wh = get_wh_filter(current_user)
    if wh: query = query.where(PayableBill.warehouse_id == wh)
    if month: query = query.where(func.to_char(PayableBill.bill_date, 'YYYY-MM') == month)
    if warehouse_id: query = query.where(PayableBill.warehouse_id == warehouse_id)
    result = await db.execute(query.order_by(PayableBill.due_date))
    bills = result.scalars().all()
    data = [{"bill_number": b.bill_number, "due_date": str(b.due_date), "amount": b.amount,
             "paid": b.paid_amount, "status": b.status} for b in bills]
    if format == "excel":
        return to_excel(["账单号", "到期日", "金额", "已付", "状态"], [[r[k] for k in ["bill_number","due_date","amount","paid","status"]] for r in data], "应付报表")
    return {"data": data, "total_pending": sum(b.amount - b.paid_amount for b in bills)}

@router.get("/expense-fund")
async def expense_fund_report(warehouse_id: int = None, format: str = "json",
                               current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = select(ExpenseFund)
    wh = get_wh_filter(current_user)
    if wh: query = query.where(ExpenseFund.warehouse_id == wh)
    if warehouse_id: query = query.where(ExpenseFund.warehouse_id == warehouse_id)
    result = await db.execute(query.order_by(ExpenseFund.created_at.desc()))
    funds = result.scalars().all()
    data = [{"purpose": f.purpose, "amount": f.amount, "remaining": f.remaining_balance, "status": f.status} for f in funds]
    if format == "excel":
        return to_excel(["用途", "金额", "余额", "状态"], [[r[k] for k in ["purpose","amount","remaining","status"]] for r in data], "备用金报表")
    return {"data": data}

@router.get("/reimbursement")
async def reimbursement_report(month: str = None, warehouse_id: int = None, format: str = "json",
                                current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = select(Reimbursement)
    wh = get_wh_filter(current_user)
    if wh: query = query.where(Reimbursement.warehouse_id == wh)
    if month: query = query.where(func.to_char(Reimbursement.submit_date, 'YYYY-MM') == month)
    if warehouse_id: query = query.where(Reimbursement.warehouse_id == warehouse_id)
    result = await db.execute(query.order_by(Reimbursement.submit_date.desc()))
    reimbs = result.scalars().all()
    data = [{"submit_date": str(r.submit_date), "total_amount": r.total_amount, "currency": r.currency, "status": r.status} for r in reimbs]
    if format == "excel":
        return to_excel(["日期", "金额", "币种", "状态"], [[r[k] for k in ["submit_date","total_amount","currency","status"]] for r in data], "报销报表")
    return {"data": data, "total": sum(r["total_amount"] for r in data)}

@router.get("/credit")
async def credit_report(warehouse_id: int = None, format: str = "json",
                         current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = select(CreditCustomer)
    wh = get_wh_filter(current_user)
    if wh: query = query.where(CreditCustomer.warehouse_id == wh)
    if warehouse_id: query = query.where(CreditCustomer.warehouse_id == warehouse_id)
    result = await db.execute(query.order_by(CreditCustomer.created_at.desc()))
    credits = result.scalars().all()
    data = [{"credit_limit": c.credit_limit, "current_debt": c.current_debt,
             "overdue_days": c.overdue_days, "status": c.status} for c in credits]
    if format == "excel":
        return to_excel(["额度", "欠款", "逾期天数", "状态"], [[r[k] for k in ["credit_limit","current_debt","overdue_days","status"]] for r in data], "账期报表")
    return {"data": data, "total_debt": sum(c.current_debt or 0 for c in credits)}

@router.get("/reconciliation-diff")
async def reconciliation_diff_report(month: str, warehouse_id: int = None, format: str = "json",
                                      current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = select(ReconciliationResult).where(ReconciliationResult.reconciliation_month == month)
    if warehouse_id: query = query.where(ReconciliationResult.warehouse_id == warehouse_id)
    result = await db.execute(query.order_by(ReconciliationResult.id))
    records = result.scalars().all()
    data = [{"month": r.reconciliation_month, "match_status": r.match_status,
             "amount_diff": r.amount_diff, "handling_note": r.handling_note} for r in records]
    if format == "excel":
        return to_excel(["月份", "状态", "差额", "处理说明"], [[r["month"], r["match_status"], r["amount_diff"], r["handling_note"]] for r in data], "对账差异")
    return {"data": data}
