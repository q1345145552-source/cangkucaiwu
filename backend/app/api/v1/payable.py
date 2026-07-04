from fastapi.responses import StreamingResponse
from fastapi import APIRouter, Depends, HTTPException, Query
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
    amount: float; currency: str = "THB"; remark: Optional[str] = None

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
    return {"data": [{
        "id": b.id, "warehouse_id": b.warehouse_id, "supplier_id": b.supplier_id,
        "supplier_name": smap.get(b.supplier_id, ""),
        "bill_number": b.bill_number,
        "bill_date": b.bill_date.isoformat() if b.bill_date else None,
        "due_date": b.due_date.isoformat() if b.due_date else None,
        "amount": b.amount, "currency": b.currency, "paid_amount": b.paid_amount,
        "status": b.status, "remark": b.remark,
    } for b in bills], "total": total, "page": page, "page_size": page_size}

@router.post("")
async def create_bill(req: BillCreate, current_user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    b = PayableBill(
        warehouse_id=get_wh(current_user), supplier_id=req.supplier_id,
        bill_number=req.bill_number,
        bill_date=datetime.fromisoformat(req.bill_date),
        due_date=datetime.fromisoformat(req.due_date),
        amount=req.amount, currency=req.currency, remark=req.remark,
        created_by=current_user.id,
    )
    db.add(b); await db.flush(); return {"id": b.id, "message": "账单创建成功"}

@router.put("/{bill_id}/pay")
async def pay_bill(bill_id: int, paid_amount: float = None,
                   current_user: User = Depends(get_current_user),
                   db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    result = await db.execute(select(PayableBill).where(PayableBill.id == bill_id))
    b = result.scalar_one_or_none()
    if not b: raise HTTPException(404, "账单不存在")
    pay = paid_amount if paid_amount is not None else b.amount
    b.paid_amount += pay
    b.paid_at = datetime.now()
    b.status = PayableStatus.PAID.value if b.paid_amount >= b.amount else PayableStatus.PARTIALLY_PAID.value
    await db.flush(); return {"message": "付款记录成功"}

# === Plans ===
@router.get("/plans")
async def list_plans(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = select(PayablePlan)
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(PayablePlan.warehouse_id == current_user.warehouse_id)
    result = await db.execute(query.order_by(PayablePlan.planned_date.desc()))
    plans = result.scalars().all()
    return {"data": [{"id": p.id, "plan_name": p.plan_name,
                      "planned_date": p.planned_date.isoformat() if p.planned_date else None,
                      "total_amount": p.total_amount, "status": p.status,
                      "bill_ids": p.bill_ids, "remark": p.remark} for p in plans]}

@router.post("/plans")
async def create_plan(req: PlanCreate, current_user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
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
    query = select(func.coalesce(func.sum(PayableBill.amount - PayableBill.paid_amount), 0))
    query = query.where(PayableBill.status.in_([PayableStatus.PENDING.value, PayableStatus.PARTIALLY_PAID.value]))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(PayableBill.warehouse_id == current_user.warehouse_id)
    total_pending = (await db.execute(query)).scalar() or 0
    return {"total_pending_payable": float(total_pending), "predicted_outflow": float(total_pending)}

# === Batch export ===
@router.get("/batch-export")
async def batch_export(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = select(PayableBill).where(PayableBill.status.in_([PayableStatus.PENDING.value, PayableStatus.PARTIALLY_PAID.value]))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(PayableBill.warehouse_id == current_user.warehouse_id)
    bills = (await db.execute(query.order_by(PayableBill.due_date))).scalars().all()
    sids = {b.supplier_id for b in bills}
    smap = {}
    if sids:
        sups = (await db.execute(select(Supplier).where(Supplier.id.in_(sids)))).scalars().all()
        smap = {s.id: {"name": s.name, "bank": s.contact_info} for s in sups}
    return {"data": [{"supplier": smap.get(b.supplier_id, {}).get("name", ""),
                      "amount": b.amount - b.paid_amount, "currency": b.currency,
                      "due_date": str(b.due_date), "bill_number": b.bill_number} for b in bills]}

@router.get("/supplier-statement")
async def supplier_statement(supplier_id: int = None, current_user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    """生成供应商对账单"""
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
