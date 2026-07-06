from fastapi.responses import StreamingResponse
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from app.database import get_db
from app.models.payable import PayableBill, PayablePlan, PayableStatus, PlanStatus
from app.models.supplier import Supplier
from app.models.user import User
from app.core.permissions import get_current_user, Role
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter()

class BillCreate(BaseModel):
    supplier_id: int; bill_number: str; bill_date: str; due_date: str
    amount: float; confirmed_amount: Optional[float] = None
    currency: str = "THB"; remark: Optional[str] = None
    payment_commitment_days: Optional[int] = None
    detail: Optional[str] = None
    is_fund_linked: Optional[str] = None

class PlanCreate(BaseModel):
    plan_name: str; planned_date: str; bill_ids: List[int]; remark: Optional[str] = None

def get_wh(user: User) -> int:
    return user.warehouse_id or 1

@router.get("")
async def list_bills(
    page: int = 1, page_size: int = 20, supplier_id: int = None,
    status: str = None, month: str = None,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(PayableBill); count_q = select(func.count(PayableBill.id))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(PayableBill.warehouse_id == current_user.warehouse_id)
        count_q = count_q.where(PayableBill.warehouse_id == current_user.warehouse_id)
    if supplier_id:
        query = query.where(PayableBill.supplier_id == supplier_id)
        count_q = count_q.where(PayableBill.supplier_id == supplier_id)
    if status:
        query = query.where(PayableBill.status == status)
        count_q = count_q.where(PayableBill.status == status)
    if month:
        query = query.where(func.to_char(PayableBill.bill_date, 'YYYY-MM') == month)
        count_q = count_q.where(func.to_char(PayableBill.bill_date, 'YYYY-MM') == month)
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(query.order_by(PayableBill.due_date.asc()).offset((page-1)*page_size).limit(page_size))
    bills = result.scalars().all()
    sids = {b.supplier_id for b in bills}
    smap = {}
    if sids:
        sups = (await db.execute(select(Supplier).where(Supplier.id.in_(sids)))).scalars().all()
        smap = {s.id: s.name for s in sups}
    # 自动标记逾期（due_date < now 且未付）
    from sqlalchemy import update as sql_update
    import sqlalchemy
    expire_sql = (
        sql_update(PayableBill)
        .where(PayableBill.due_date < datetime.now())
        .where(PayableBill.status.in_([PayableStatus.PENDING.value, PayableStatus.PARTIALLY_PAID.value]))
        .values(status=PayableStatus.OVERDUE.value)
    )
    try:
        await db.execute(expire_sql)
        await db.flush()
    except: pass

    return {
        "data": [{
            "id": b.id, "warehouse_id": b.warehouse_id, "supplier_id": b.supplier_id,
            "supplier_name": smap.get(b.supplier_id, ""),
            "bill_number": b.bill_number,
            "bill_date": b.bill_date.isoformat() if b.bill_date else None,
            "due_date": b.due_date.isoformat() if b.due_date else None,
            "amount": b.amount, "confirmed_amount": b.confirmed_amount,
            "currency": b.currency, "paid_amount": b.paid_amount,
            "status": b.status, "is_duplicate_warned": b.is_duplicate_warned,
            "payment_commitment_days": b.payment_commitment_days,
            "payment_voucher": b.payment_voucher, "payment_method": b.payment_method, "bill_attachment": b.bill_attachment,
            "is_fund_linked": b.is_fund_linked, "detail": b.detail, "remark": b.remark,
        } for b in bills],
        "total": total, "page": page, "page_size": page_size,
    }

@router.post("")
async def create_bill(req: BillCreate, current_user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    # 重复检测
    existing = (await db.execute(
        select(PayableBill).where(
            PayableBill.warehouse_id == get_wh(current_user),
            PayableBill.bill_number == req.bill_number,
            PayableBill.supplier_id == req.supplier_id,
        )
    )).scalar_one_or_none()
    if existing and not existing.is_duplicate_warned:
        raise HTTPException(409, f"重复账单警告: 账单号 {req.bill_number} 已存在，请确认是否新账单")

    # 对账差异检测
    has_diff = False
    diff_note = None
    if req.confirmed_amount is not None and req.confirmed_amount != req.amount:
        has_diff = True
        diff_note = f"供应商确认金额 {req.confirmed_amount} 与仓库记录 {req.amount} 不一致"
    
    b = PayableBill(
        warehouse_id=get_wh(current_user), supplier_id=req.supplier_id,
        bill_number=req.bill_number,
        bill_date=datetime.fromisoformat(req.bill_date),
        due_date=datetime.fromisoformat(req.due_date),
        amount=req.amount, confirmed_amount=req.confirmed_amount,
        currency=req.currency, detail=req.detail, remark=req.remark,
        payment_commitment_days=req.payment_commitment_days,
        is_fund_linked=req.is_fund_linked,
        created_by=current_user.id,
    )
    db.add(b); await db.flush()
    return {"id": b.id, "message": "账单创建成功", "has_diff": has_diff, "diff_note": diff_note}

@router.post("/{bill_id}/upload-voucher")
async def upload_voucher(bill_id: int, file: UploadFile = File(...),
                         current_user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "无权限")
    result = await db.execute(select(PayableBill).where(PayableBill.id == bill_id))
    b = result.scalar_one_or_none()
    if not b: raise HTTPException(404, "账单不存在")
    import os, uuid
    upload_dir = "/app/uploads/payment_vouchers"
    os.makedirs(upload_dir, exist_ok=True)
    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "png"
    fname = f"{uuid.uuid4().hex}.{ext}"
    fpath = os.path.join(upload_dir, fname)
    content = await file.read()
    with open(fpath, "wb") as f: f.write(content)
    b.payment_voucher = f"/uploads/payment_vouchers/{fname}"
    await db.flush()
    return {"message": "凭证上传成功", "path": b.payment_voucher}

@router.post("/{bill_id}/upload-attachment")
async def upload_bill_attachment(bill_id: int, file: UploadFile = File(...),
                                 current_user: User = Depends(get_current_user),
                                 db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "无权限")
    result = await db.execute(select(PayableBill).where(PayableBill.id == bill_id))
    b = result.scalar_one_or_none()
    if not b: raise HTTPException(404, "账单不存在")
    import os, uuid
    upload_dir = "/app/uploads/bill_attachments"
    os.makedirs(upload_dir, exist_ok=True)
    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "pdf"
    fname = f"{uuid.uuid4().hex}.{ext}"
    fpath = os.path.join(upload_dir, fname)
    content = await file.read()
    with open(fpath, "wb") as f: f.write(content)
    b.bill_attachment = f"/uploads/bill_attachments/{fname}"
    await db.flush()
    return {"message": "账单附件上传成功", "path": b.bill_attachment}

@router.put("/{bill_id}/pay")
async def pay_bill(bill_id: int, paid_amount: float = None, payment_method: str = None,
                   current_user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    result = await db.execute(select(PayableBill).where(PayableBill.id == bill_id))
    b = result.scalar_one_or_none()
    if not b: raise HTTPException(404, "账单不存在")
    pay = paid_amount if paid_amount is not None else (b.amount - b.paid_amount)
    b.paid_amount += pay
    b.paid_at = datetime.now()
    if payment_method:
        b.payment_method = payment_method
    if b.paid_amount >= b.amount:
        b.status = PayableStatus.PAID.value
    else:
        b.status = PayableStatus.PARTIALLY_PAID.value
    # 清除逾期标记
    if b.status in (PayableStatus.PAID.value, PayableStatus.PARTIALLY_PAID.value) and b.status != PayableStatus.OVERDUE.value:
        pass
    await db.flush(); return {"message": "付款记录成功"}

# === Stats Dashboard ===
@router.get("/stats")
async def payable_stats(current_user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    from datetime import date
    from sqlalchemy import extract
    wh_id = current_user.warehouse_id
    today = date.today()

    def wh(q):
        return q.where(PayableBill.warehouse_id == wh_id)

    # Month totals
    month_cond = [extract("year", PayableBill.bill_date) == today.year, extract("month", PayableBill.bill_date) == today.month]
    month_total = float((await db.execute(wh(select(func.coalesce(func.sum(PayableBill.amount), 0))).where(*month_cond))).scalar() or 0)
    month_paid = float((await db.execute(wh(select(func.coalesce(func.sum(PayableBill.paid_amount), 0))).where(*month_cond))).scalar() or 0)
    month_unpaid = month_total - month_paid

    # Overdue
    overdue_total = float((await db.execute(wh(select(func.coalesce(func.sum(PayableBill.amount - PayableBill.paid_amount), 0)))
        .where(PayableBill.status == PayableStatus.OVERDUE.value))).scalar() or 0)

    # Supplier summary (month)
    sup_q = wh(select(PayableBill.supplier_id,
        func.count(PayableBill.id).label("count"),
        func.sum(PayableBill.amount).label("total"),
        func.sum(PayableBill.paid_amount).label("paid"))
        .where(*month_cond).group_by(PayableBill.supplier_id).order_by(func.sum(PayableBill.amount).desc()))
    sup_rows = (await db.execute(sup_q)).all()
    sids = [r.supplier_id for r in sup_rows]
    smap = {}
    if sids:
        sups = (await db.execute(select(Supplier).where(Supplier.id.in_(sids)))).scalars().all()
        smap = {s.id: s.name for s in sups}
    supplier_summary = [{
        "supplier_id": r.supplier_id, "supplier_name": smap.get(r.supplier_id, ""),
        "bill_count": r.count, "total_amount": float(r.total or 0),
        "paid_amount": float(r.paid or 0), "unpaid_amount": float((r.total or 0) - (r.paid or 0)),
    } for r in sup_rows]

    return {
        "month_total": month_total, "overdue_total": overdue_total,
        "month_paid": month_paid, "month_unpaid": month_unpaid,
        "supplier_summary": supplier_summary,
    }

# === Plans ===
@router.get("/plans")
async def list_plans(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(PayablePlan)
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(PayablePlan.warehouse_id == current_user.warehouse_id)
    result = await db.execute(query.order_by(PayablePlan.planned_date.desc()))
    plans = result.scalars().all()
    # 自动标记逾期（due_date < now 且未付）
    from sqlalchemy import update as sql_update
    import sqlalchemy
    expire_sql = (
        sql_update(PayableBill)
        .where(PayableBill.due_date < datetime.now())
        .where(PayableBill.status.in_([PayableStatus.PENDING.value, PayableStatus.PARTIALLY_PAID.value]))
        .values(status=PayableStatus.OVERDUE.value)
    )
    try:
        await db.execute(expire_sql)
        await db.flush()
    except: pass

    return {"data": [{"id": p.id, "plan_name": p.plan_name, "planned_date": p.planned_date.isoformat() if p.planned_date else None, "total_amount": p.total_amount, "status": p.status, "bill_ids": p.bill_ids, "remark": p.remark} for p in plans]}

@router.post("/plans")
async def create_plan(req: PlanCreate, current_user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    total = 0
    if req.bill_ids:
        bills = (await db.execute(select(PayableBill).where(PayableBill.id.in_(req.bill_ids)))).scalars().all()
        total = sum(b.amount - b.paid_amount for b in bills)
    p = PayablePlan(
        warehouse_id=get_wh(current_user), plan_name=req.plan_name,
        planned_date=datetime.fromisoformat(req.planned_date),
        total_amount=total, bill_ids=req.bill_ids, remark=req.remark,
        created_by=current_user.id,
    )
    db.add(p); await db.flush(); return {"id": p.id, "message": "付款计划创建成功"}

# === Cashflow ===
@router.get("/cashflow-prediction")
async def cashflow_prediction(current_user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(func.coalesce(func.sum(PayableBill.amount - PayableBill.paid_amount), 0))
    query = query.where(PayableBill.status.in_([PayableStatus.PENDING.value, PayableStatus.PARTIALLY_PAID.value]))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(PayableBill.warehouse_id == current_user.warehouse_id)
    total_pending = (await db.execute(query)).scalar() or 0
    return {"total_pending_payable": float(total_pending), "predicted_outflow": float(total_pending)}

# === Batch export ===
@router.get("/batch-export")
async def batch_export(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(PayableBill).where(PayableBill.status.in_([PayableStatus.PENDING.value, PayableStatus.PARTIALLY_PAID.value]))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(PayableBill.warehouse_id == current_user.warehouse_id)
    bills = (await db.execute(query.order_by(PayableBill.due_date))).scalars().all()
    sids = {b.supplier_id for b in bills}
    smap = {}
    if sids:
        sups = (await db.execute(select(Supplier).where(Supplier.id.in_(sids)))).scalars().all()
        smap = {s.id: {"name": s.name, "bank": s.contact_info} for s in sups}
    # 自动标记逾期（due_date < now 且未付）
    from sqlalchemy import update as sql_update
    import sqlalchemy
    expire_sql = (
        sql_update(PayableBill)
        .where(PayableBill.due_date < datetime.now())
        .where(PayableBill.status.in_([PayableStatus.PENDING.value, PayableStatus.PARTIALLY_PAID.value]))
        .values(status=PayableStatus.OVERDUE.value)
    )
    try:
        await db.execute(expire_sql)
        await db.flush()
    except: pass

    return {"data": [{"supplier": smap.get(b.supplier_id, {}).get("name", ""), "amount": b.amount - b.paid_amount, "currency": b.currency, "due_date": str(b.due_date), "bill_number": b.bill_number} for b in bills]}

@router.get("/supplier-statement")
async def supplier_statement(supplier_id: int = None, current_user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    """生成供应商对账单"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(PayableBill)
    if supplier_id: query = query.where(PayableBill.supplier_id == supplier_id)
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(PayableBill.warehouse_id == current_user.warehouse_id)
    result = await db.execute(query.order_by(PayableBill.due_date))
    bills = result.scalars().all()
    sids={b.supplier_id for b in bills}
    smap={}
    if sids:
        sups=(await db.execute(select(Supplier).where(Supplier.id.in_(sids)))).scalars().all()
        smap={s.id:{"name":s.name,"contact":s.contact_info} for s in sups}
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb=Workbook(); ws=wb.active; ws.title="供应商对账单"
    hf=PatternFill(start_color="2563EB",end_color="2563EB",fill_type="solid"); hfont=Font(bold=True,color="FFFFFF")
    for c,h in enumerate(["供应商","账单号","账单日期","到期日","金额","币种","已付","待付"],1):
        cell=ws.cell(row=1,column=c,value=h); cell.font=hfont; cell.fill=hf
    for r,b in enumerate(bills,2):
        vals=[smap.get(b.supplier_id,{}).get("name",""),b.bill_number,str(b.bill_date)[:10],str(b.due_date)[:10],b.amount,b.currency,b.paid_amount,b.amount-b.paid_amount]
        for c,v in enumerate(vals,1): ws.cell(row=r,column=c,value=str(v) if v is not None else "")
    import io; output=io.BytesIO(); wb.save(output); output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": "attachment; filename=supplier_statement.xlsx"})
