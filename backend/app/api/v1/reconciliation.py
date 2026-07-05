from fastapi.responses import StreamingResponse
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.database import get_db
from app.models.recharge import RechargeDeclaration, IncomingFlow, ReconciliationResult, ReconMatchStatus, MatchStatus
from app.models.customer import Customer
from app.models.user import User
from app.core.permissions import get_current_user, Role
from app.schemas.business import ReconciliationRequest, ManualMatchRequest, UnmatchRequest

router = APIRouter()

@router.post("/run")
async def run_reconciliation(req: ReconciliationRequest, current_user: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    if current_user.role != Role.SUPER_ADMIN:
        raise HTTPException(403, "仅超级管理员可操作")

    # Get unmatched declarations for the month
    decls = (await db.execute(
        select(RechargeDeclaration).where(
            and_(
                RechargeDeclaration.warehouse_id == req.warehouse_id,
                func.to_char(RechargeDeclaration.declare_date, 'YYYY-MM') == req.month,
                RechargeDeclaration.match_status == MatchStatus.UNMATCHED,
            )
        )
    )).scalars().all()

    # Get unmatched flows for the month
    flows = (await db.execute(
        select(IncomingFlow).where(
            and_(
                IncomingFlow.warehouse_id == req.warehouse_id,
                func.to_char(IncomingFlow.received_date, 'YYYY-MM') == req.month,
                IncomingFlow.match_status == MatchStatus.UNMATCHED,
            )
        )
    )).scalars().all()

    # Auto match: same amount + same currency
    matched = 0; unmatched_decls = []; unmatched_flows = []
    flow_by_key = {}
    for f in flows:
        key = (f.amount, f.currency or "THB")
        if key not in flow_by_key:
            flow_by_key[key] = []
        flow_by_key[key].append(f)

    used_flows = set()
    for d in decls:
        key = (d.amount, d.currency or "THB")
        candidates = [f for f in flow_by_key.get(key, []) if f.id not in used_flows]
        if candidates:
            f = candidates[0]; used_flows.add(f.id)
            # Create reconciliation result
            rr = ReconciliationResult(
                warehouse_id=req.warehouse_id, reconciliation_month=req.month,
                declaration_id=d.id, flow_id=f.id,
                match_status=ReconMatchStatus.MATCHED, amount_diff=0,
                confirmed_by=current_user.id,
            )
            db.add(rr)
            d.match_status = MatchStatus.MATCHED; f.match_status = MatchStatus.MATCHED
            matched += 1
        else:
            unmatched_decls.append(d)

    for f in flows:
        if f.id not in used_flows:
            unmatched_flows.append(f)

    await db.flush()
    return {
        "matched": matched,
        "unmatched_declarations": len(unmatched_decls),
        "unmatched_flows": len(unmatched_flows),
        "total_declarations": len(decls),
        "total_flows": len(flows),
    }

@router.get("/results")
async def list_results(month: str, warehouse_id: int = None,
                       match_status: str = None, page: int = 1, page_size: int = 20,
                       current_user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(ReconciliationResult); count_q = select(func.count(ReconciliationResult.id))
    query = query.where(ReconciliationResult.reconciliation_month == month)
    count_q = count_q.where(ReconciliationResult.reconciliation_month == month)

    # Data isolation: non-super-admin can only see their own warehouse
    if current_user.role != Role.SUPER_ADMIN:
        if warehouse_id and warehouse_id != current_user.warehouse_id:
            raise HTTPException(403, "无权查看其他仓库的对账结果")
        query = query.where(ReconciliationResult.warehouse_id == current_user.warehouse_id)
        count_q = count_q.where(ReconciliationResult.warehouse_id == current_user.warehouse_id)
    elif warehouse_id:
        query = query.where(ReconciliationResult.warehouse_id == warehouse_id)
        count_q = count_q.where(ReconciliationResult.warehouse_id == warehouse_id)

    if match_status:
        query = query.where(ReconciliationResult.match_status == match_status)
        count_q = count_q.where(ReconciliationResult.match_status == match_status)
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(query.order_by(ReconciliationResult.id).offset((page-1)*page_size).limit(page_size))
    records = result.scalars().all()

    # Prefetch related data
    decl_ids = [r.declaration_id for r in records if r.declaration_id]
    flow_ids = [r.flow_id for r in records if r.flow_id]
    decl_map = {}; flow_map = {}; decl_customer_map = {}
    if decl_ids:
        decls = (await db.execute(select(RechargeDeclaration).where(RechargeDeclaration.id.in_(decl_ids)))).scalars().all()
        decl_map = {d.id: {"amount": d.amount, "currency": d.currency or "", "declare_date": str(d.declare_date)} for d in decls}

        # Build customer_name mapping through declarations
        cust_ids = [d.customer_id for d in decls if d.customer_id]
        customer_map = {}
        if cust_ids:
            customers = (await db.execute(select(Customer).where(Customer.id.in_(cust_ids)))).scalars().all()
            customer_map = {c.id: c.company_name for c in customers}
        for d in decls:
            decl_customer_map[d.id] = customer_map.get(d.customer_id, "")

    if flow_ids:
        fls = (await db.execute(select(IncomingFlow).where(IncomingFlow.id.in_(flow_ids)))).scalars().all()
        flow_map = {f.id: {"amount": f.amount, "currency": f.currency or "", "received_date": str(f.received_date)} for f in fls}

    return {"data": [{
        "id": r.id, "warehouse_id": r.warehouse_id, "reconciliation_month": r.reconciliation_month,
        "declaration_id": r.declaration_id, "flow_id": r.flow_id,
        "match_status": r.match_status or "",
        "amount_diff": r.amount_diff, "handling_note": r.handling_note,
        "customer_name": decl_customer_map.get(r.declaration_id, ""),
        "declaration": decl_map.get(r.declaration_id),
        "flow": flow_map.get(r.flow_id),
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in records], "total": total, "page": page, "page_size": page_size}

@router.post("/manual-match")
async def manual_match(req: ManualMatchRequest, current_user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db)):
    if current_user.role != Role.SUPER_ADMIN:
        raise HTTPException(403, "仅超级管理员可操作")
    decl = (await db.execute(select(RechargeDeclaration).where(RechargeDeclaration.id == req.declaration_id))).scalar_one_or_none()
    flow = (await db.execute(select(IncomingFlow).where(IncomingFlow.id == req.flow_id))).scalar_one_or_none()
    if not decl or not flow:
        raise HTTPException(404, "记录不存在")
    rr = ReconciliationResult(
        warehouse_id=decl.warehouse_id,
        reconciliation_month=flow.received_date.strftime("%Y-%m"),
        declaration_id=decl.id, flow_id=flow.id,
        match_status=ReconMatchStatus.MANUAL_MATCHED,
        amount_diff=abs(decl.amount - flow.amount),
        handling_note=req.handling_note, confirmed_by=current_user.id,
    )
    db.add(rr)
    decl.match_status = MatchStatus.MATCHED; flow.match_status = MatchStatus.MATCHED
    await db.flush(); return {"message": "手动匹配成功"}

@router.post("/unmatch")
async def unmatch_record(req: UnmatchRequest, current_user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    if current_user.role != Role.SUPER_ADMIN:
        raise HTTPException(403, "仅超级管理员可操作")
    rr = (await db.execute(select(ReconciliationResult).where(ReconciliationResult.id == req.record_id))).scalar_one_or_none()
    if not rr: raise HTTPException(404, "记录不存在")
    if rr.declaration_id:
        d = (await db.execute(select(RechargeDeclaration).where(RechargeDeclaration.id == rr.declaration_id))).scalar_one_or_none()
        if d: d.match_status = MatchStatus.UNMATCHED
    if rr.flow_id:
        f = (await db.execute(select(IncomingFlow).where(IncomingFlow.id == rr.flow_id))).scalar_one_or_none()
        if f: f.match_status = MatchStatus.UNMATCHED
    await db.delete(rr); await db.flush(); return {"message": "已解除匹配"}

@router.get("/export")
async def export_reconciliation(month: str, warehouse_id: int = None,
                                 current_user: User = Depends(get_current_user),
                                 db: AsyncSession = Depends(get_db)):
    """导出对账报表为Excel"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(ReconciliationResult).where(ReconciliationResult.reconciliation_month == month)

    # Data isolation: non-super-admin can only export their own warehouse
    if current_user.role != Role.SUPER_ADMIN:
        if warehouse_id and warehouse_id != current_user.warehouse_id:
            raise HTTPException(403, "无权导出其他仓库的对账报表")
        query = query.where(ReconciliationResult.warehouse_id == current_user.warehouse_id)
    elif warehouse_id:
        query = query.where(ReconciliationResult.warehouse_id == warehouse_id)

    result = await db.execute(query.order_by(ReconciliationResult.id))
    records = result.scalars().all()
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    wb = Workbook(); ws = wb.active; ws.title = "对账报表"
    hf = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid"); hfont = Font(bold=True, color="FFFFFF")
    headers = ["ID","仓库","月份","申报ID","流水ID","状态","差异","处理说明","确认人","时间"]
    for c,h in enumerate(headers,1): cell=ws.cell(row=1,column=c,value=h); cell.font=hfont; cell.fill=hf
    for r,rec in enumerate(records,2):
        vals=[rec.id,rec.warehouse_id,rec.reconciliation_month,rec.declaration_id,rec.flow_id,rec.match_status,rec.amount_diff,rec.handling_note,rec.confirmed_by,str(rec.created_at)[:19]]
        for c,v in enumerate(vals,1): ws.cell(row=r,column=c,value=str(v) if v else "")
    import io; output=io.BytesIO(); wb.save(output); output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": f"attachment; filename=reconciliation_{month}.xlsx"})
