from fastapi.responses import StreamingResponse
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.core.timezone import thai_now, thai_today
from datetime import datetime, date, timedelta
from app.database import get_db
from app.models.recharge import RechargeDeclaration, IncomingFlow, ReconciliationResult, ReconMatchStatus, MatchStatus
from app.models.customer import Customer
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role, check_staff_permission, require_non_labor
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY

from app.services.warehouse_summary import warehouse_scope
from app.services.customer_receivables import bind_receipt

router = APIRouter()

@router.get("/unmatched")
async def get_unmatched(
    request: Request,
    start_date: str = None, end_date: str = None,
    warehouse_id: int = None,
    current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reconciliation"].label)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    scope=[w.id for w in await warehouse_scope(db,current_user,request.headers.get('X-Warehouse-ID'))]
    if warehouse_id and warehouse_id not in scope:raise HTTPException(403,'无权查看其他仓库')
    if warehouse_id:scope=[warehouse_id]
    today = thai_today()
    sd = datetime.fromisoformat(start_date) if start_date else datetime(today.year, today.month, 1)
    ed = datetime.fromisoformat(end_date) if end_date else datetime(today.year, today.month, today.day) + timedelta(days=1) - timedelta(microseconds=1)

    decl_q = select(RechargeDeclaration).where(and_(
        RechargeDeclaration.warehouse_id.in_(scope),
        RechargeDeclaration.declare_date >= sd,
        RechargeDeclaration.declare_date <= ed,
        RechargeDeclaration.match_status == MatchStatus.UNMATCHED,
        RechargeDeclaration.screenshot.isnot(None),
    )).order_by(RechargeDeclaration.declare_date.desc())
    decls = (await db.execute(decl_q)).scalars().all()
    cust_ids = {d.customer_id for d in decls}
    cust_map = {}
    if cust_ids:
        custs = (await db.execute(select(Customer).where(Customer.id.in_(cust_ids)))).scalars().all()
        cust_map = {c.id: c for c in custs}
    declarations = [{
        "id": d.id, "customer_id": d.customer_id,
        "customer_name": cust_map[d.customer_id].company_name if d.customer_id in cust_map else "",
        "customer_code": cust_map[d.customer_id].customer_code if d.customer_id in cust_map else "",
        "declare_date": d.declare_date.isoformat() if d.declare_date else None,
        "amount": d.amount, "currency": d.currency or "THB",
        "screenshot": d.screenshot,
        "payment_method": d.payment_method,
    } for d in decls]

    flow_q = select(IncomingFlow).where(and_(
        IncomingFlow.warehouse_id.in_(scope),
        IncomingFlow.received_date >= sd,
        IncomingFlow.received_date <= ed,
        IncomingFlow.match_status == MatchStatus.UNMATCHED,
    )).order_by(IncomingFlow.received_date.desc())
    flows = (await db.execute(flow_q)).scalars().all()
    from app.services.incoming_suggestions import suggestions_for
    suggestions=await suggestions_for(db,flows)
    incoming = [{
        "id": f.id, "payer_name": f.payer_name,"suggestions":suggestions[f.id],
        "received_date": f.received_date.isoformat() if f.received_date else None,
        "amount": f.amount, "currency": f.currency or "THB",
        "payment_method": f.payment_method,
    } for f in flows]
    return {"declarations": declarations, "incoming": incoming}

@router.post("/manual-match")
async def manual_match(
    request: Request,
    declaration_id: int = Query(...), flow_id: int = Query(...),
    handling_note: str = Query(""),
    current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reconciliation"].label)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    scope = [w.id for w in await warehouse_scope(db,current_user,request.headers.get('X-Warehouse-ID'))]
    flow = (await db.execute(select(IncomingFlow).where(IncomingFlow.id == flow_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    decl = (await db.execute(select(RechargeDeclaration).where(RechargeDeclaration.id == declaration_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if not decl or not flow: raise HTTPException(404, "记录不存在")
    if decl.warehouse_id != flow.warehouse_id or decl.warehouse_id not in scope:
        raise HTTPException(403,'只能匹配当前同一仓库的记录')
    if decl.match_status != MatchStatus.UNMATCHED or flow.match_status != MatchStatus.UNMATCHED:
        raise HTTPException(400, "所选记录已被匹配")
    if current_user.role != Role.SUPER_ADMIN:
        if decl.warehouse_id not in get_wh_ids(current_user) or flow.warehouse_id not in get_wh_ids(current_user):
            raise HTTPException(403, "只能匹配自己仓库的记录")
    # 币种一致性校验：不同币种的申报与流水不能直接匹配（金额差无意义）
    from app.services.flow_rules import currencies_match
    if not currencies_match(decl.currency, flow.currency):
        raise HTTPException(400, f"币种不一致（申报 {decl.currency or 'THB'} / 流水 {flow.currency or 'THB'}），不能匹配")
    customer = await db.get(Customer,decl.customer_id)
    if not customer or customer.warehouse_id != decl.warehouse_id: raise HTTPException(409,'申报客户归属异常，请先核对')
    original_customer_id=flow.customer_id
    await bind_receipt(db,customer,flow,current_user)
    rr = ReconciliationResult(
        warehouse_id=decl.warehouse_id,
        reconciliation_month=decl.declare_date.strftime("%Y-%m") if decl.declare_date else thai_now().strftime("%Y-%m"),
        declaration_id=decl.id, flow_id=flow.id,
        match_status=ReconMatchStatus.MANUAL_MATCHED,
        amount_diff=abs(decl.amount - flow.amount),
        handling_note=handling_note, confirmed_by=current_user.id, confirmed_at=thai_now(),
    )
    db.add(rr); decl.match_status = MatchStatus.MATCHED; flow.match_status = MatchStatus.MATCHED
    await db.flush()
    from app.services.data_history import record_history
    await record_history(db,module='reconciliation',record_id=rr.id,operator=current_user,operation_type='match',
        before={'customer_id':original_customer_id},after={'flow_id':flow.id,'declaration_id':decl.id,'customer_id':customer.id,'action':'人工确认匹配'},warehouse_id=flow.warehouse_id)
    return {'id':rr.id,'flow_id':flow.id,'declaration_id':decl.id,'customer_id':customer.id,'customer_code':customer.customer_code,
        'amount':flow.amount,'currency':flow.currency,'message':f'已匹配到 {customer.customer_code} 的 {flow.amount:,.2f} {flow.currency or "THB"}'}

@router.post("/unmatch", dependencies=[Depends(require_non_labor)])
async def unmatch_record(
    request: Request,
    record_id: int = Query(...),
    current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reconciliation"].label)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    rr = (await db.execute(select(ReconciliationResult).where(ReconciliationResult.id == record_id))).scalar_one_or_none()
    if not rr: raise HTTPException(404, "记录不存在")
    scope = [w.id for w in await warehouse_scope(db,current_user,request.headers.get('X-Warehouse-ID'))]
    if rr.warehouse_id not in scope: raise HTTPException(403,'只能操作当前仓库的匹配')
    # 撤销只恢复本次匹配前归属；保留独立账期回款与历史既有归属，不退银行款。
    restored_customer=False
    if rr.flow_id:
        flow = (await db.execute(select(IncomingFlow).where(IncomingFlow.id==rr.flow_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        rr=(await db.execute(select(ReconciliationResult).where(ReconciliationResult.id==record_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
        if rr is None:raise HTTPException(409,'匹配已撤销，请刷新列表')
        declaration = (await db.execute(select(RechargeDeclaration).where(RechargeDeclaration.id==rr.declaration_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none() if rr.declaration_id else None
        customer = await db.get(Customer,declaration.customer_id) if declaration else None
        if flow and flow.warehouse_id != rr.warehouse_id: raise HTTPException(403,'匹配中的到账归属异常，不能操作其他仓库')
        if declaration and declaration.warehouse_id != rr.warehouse_id: raise HTTPException(403,'匹配中的申报归属异常，不能操作其他仓库')
        if customer and customer.warehouse_id != rr.warehouse_id: raise HTTPException(409,'匹配中的客户归属异常，请先核对')
        if flow and customer and flow.warehouse_id==rr.warehouse_id and customer.warehouse_id==rr.warehouse_id:
            from app.models.data_change_history import DataChangeHistory
            from app.models.credit import CreditRepayment
            evidence=(await db.execute(select(DataChangeHistory).where(DataChangeHistory.module=='reconciliation',DataChangeHistory.record_id==rr.id,
                DataChangeHistory.operation_type=='match',DataChangeHistory.warehouse_id==rr.warehouse_id).order_by(DataChangeHistory.id.desc()))).scalars().first()
            independent=(await db.execute(select(CreditRepayment.id).where(CreditRepayment.incoming_flow_id==flow.id).limit(1))).scalar_one_or_none()
            other=(await db.execute(select(ReconciliationResult.id).where(ReconciliationResult.flow_id==flow.id,ReconciliationResult.id!=rr.id,
                ReconciliationResult.match_status.in_(('matched','manual_matched'))).limit(1))).scalar_one_or_none()
            if evidence and evidence.after_data.get('flow_id')==flow.id and evidence.before_data.get('customer_id') is None and not independent and not other:
                if flow.customer_id!=customer.id:raise HTTPException(409,'到账客户归属已变化，请先核对')
                flow.customer_id=None;restored_customer=True
                from app.services.data_history import record_history
                await record_history(db,module='reconciliation',record_id=rr.id,operator=current_user,operation_type='unmatch',
                    before={'flow_id':flow.id,'customer_id':customer.id},after={'flow_id':flow.id,'customer_id':None,'action':'撤销本次匹配归属，银行到账保留'},warehouse_id=rr.warehouse_id)
            else:await bind_receipt(db,customer,flow,current_user)
    if current_user.role != Role.SUPER_ADMIN and rr.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "无权限")
    if rr.declaration_id:
        d = (await db.execute(select(RechargeDeclaration).where(RechargeDeclaration.id == rr.declaration_id))).scalar_one_or_none()
        if d: d.match_status = MatchStatus.UNMATCHED
    if rr.flow_id:
        f = (await db.execute(select(IncomingFlow).where(IncomingFlow.id == rr.flow_id))).scalar_one_or_none()
        if f: f.match_status = MatchStatus.UNMATCHED
    await db.delete(rr); await db.flush(); return {'customer_binding_reverted':restored_customer,"message": "已撤销匹配，客户归属和余额已恢复，银行到账保留" if restored_customer else "已解除申报匹配，独立客户归属保留，未退款"}

@router.get("/results")
async def list_results(
    start_date: str = None, end_date: str = None,
    warehouse_id: int = None,
    search: str = None, search_code: str = None,
    page: int = 1, page_size: int = 50,
    current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reconciliation"].label)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(ReconciliationResult); count_q = select(func.count(ReconciliationResult.id))
    if current_user.role != Role.SUPER_ADMIN:
        if warehouse_id and warehouse_id != get_wh_id(current_user):
            raise HTTPException(403, "无权查看其他仓库")
        query = query.where(ReconciliationResult.warehouse_id.in_(get_wh_ids(current_user)))
        count_q = count_q.where(ReconciliationResult.warehouse_id.in_(get_wh_ids(current_user)))
    elif warehouse_id:
        query = query.where(ReconciliationResult.warehouse_id == warehouse_id)
        count_q = count_q.where(ReconciliationResult.warehouse_id == warehouse_id)
    if start_date:
        query = query.where(ReconciliationResult.created_at >= datetime.fromisoformat(start_date))
        count_q = count_q.where(ReconciliationResult.created_at >= datetime.fromisoformat(start_date))
    if end_date:
        edt = datetime.fromisoformat(end_date) + timedelta(days=1) - timedelta(microseconds=1)
        query = query.where(ReconciliationResult.created_at <= edt)
        count_q = count_q.where(ReconciliationResult.created_at <= edt)

    # Fetch all matched records for the time range (may need filtering by customer later)
    all_records = (await db.execute(query.order_by(ReconciliationResult.created_at.desc()))).scalars().all()

    # Fetch related data
    decl_ids = [r.declaration_id for r in all_records if r.declaration_id]
    flow_ids = [r.flow_id for r in all_records if r.flow_id]
    decl_map = {}; flow_map = {}; cust_map = {}
    if decl_ids:
        decls = (await db.execute(select(RechargeDeclaration).where(RechargeDeclaration.id.in_(decl_ids)))).scalars().all()
        decl_map = {d.id: d for d in decls}
        cust_ids = {d.customer_id for d in decls}
        if cust_ids:
            custs = (await db.execute(select(Customer).where(Customer.id.in_(cust_ids)))).scalars().all()
            cust_map = {c.id: c for c in custs}
    if flow_ids:
        flows = (await db.execute(select(IncomingFlow).where(IncomingFlow.id.in_(flow_ids)))).scalars().all()
        flow_map = {f.id: f for f in flows}

    # Build result items
    items = []
    for r in all_records:
        d = decl_map.get(r.declaration_id)
        cid = d.customer_id if d else None
        c = cust_map.get(cid)
        customer_name = c.company_name if c else ""
        customer_code = c.customer_code if c else ""
        # Apply search filter
        if search and search not in customer_name:
            continue
        if search_code and search_code not in customer_code:
            continue
        f = flow_map.get(r.flow_id)
        items.append({
            "id": r.id, "warehouse_id": r.warehouse_id,
            "reconciliation_month": r.reconciliation_month,
            "declaration_id": r.declaration_id, "flow_id": r.flow_id,
            "match_status": r.match_status or "",
            "amount_diff": r.amount_diff, "handling_note": r.handling_note,
            "customer_code": customer_code, "customer_name": customer_name,
            "decl_amount": d.amount if d else None,
            "decl_currency": d.currency if d else None,
            "flow_payer": f.payer_name if f else "",
            "flow_amount": f.amount if f else None,
            "flow_currency": f.currency if f else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    total = len(items)
    # Compute total matched amounts by currency
    total_matched_decl_by_currency: dict = {}
    total_matched_flow_by_currency: dict = {}
    for it in items:
        dc = it.get("decl_currency") or "THB"
        fc = it.get("flow_currency") or "THB"
        total_matched_decl_by_currency[dc] = total_matched_decl_by_currency.get(dc, 0) + (it.get("decl_amount") or 0)
        total_matched_flow_by_currency[fc] = total_matched_flow_by_currency.get(fc, 0) + (it.get("flow_amount") or 0)
    # Apply pagination after filtering
    start_idx = (page - 1) * page_size
    paged = items[start_idx:start_idx + page_size]
    return {"data": paged, "total": total, "page": page, "page_size": page_size,
            "total_matched_decl_by_currency": total_matched_decl_by_currency,
            "total_matched_flow_by_currency": total_matched_flow_by_currency}

@router.get("/export")
async def export_reconciliation(
    start_date: str = None, end_date: str = None,
    warehouse_id: int = None,
    search: str = None, search_code: str = None,
    current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reconciliation"].label)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(ReconciliationResult)
    if current_user.role != Role.SUPER_ADMIN:
        if warehouse_id and warehouse_id != get_wh_id(current_user):
            raise HTTPException(403, "无权导出其他仓库")
        query = query.where(ReconciliationResult.warehouse_id.in_(get_wh_ids(current_user)))
    elif warehouse_id:
        query = query.where(ReconciliationResult.warehouse_id == warehouse_id)
    if start_date:
        query = query.where(ReconciliationResult.created_at >= datetime.fromisoformat(start_date))
    if end_date:
        edt = datetime.fromisoformat(end_date) + timedelta(days=1) - timedelta(microseconds=1)
        query = query.where(ReconciliationResult.created_at <= edt)

    records = (await db.execute(query.order_by(ReconciliationResult.created_at.desc()))).scalars().all()
    decl_ids = [r.declaration_id for r in records if r.declaration_id]
    flow_ids = [r.flow_id for r in records if r.flow_id]
    decl_map = {}; flow_map = {}; cust_map = {}
    if decl_ids:
        decls = (await db.execute(select(RechargeDeclaration).where(RechargeDeclaration.id.in_(decl_ids)))).scalars().all()
        decl_map = {d.id: d for d in decls}
        cust_ids = {d.customer_id for d in decls}
        if cust_ids:
            custs = (await db.execute(select(Customer).where(Customer.id.in_(cust_ids)))).scalars().all()
            cust_map = {c.id: c for c in custs}
    if flow_ids:
        flows = (await db.execute(select(IncomingFlow).where(IncomingFlow.id.in_(flow_ids)))).scalars().all()
        flow_map = {f.id: f for f in flows}

    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook(); ws = wb.active; ws.title = "对账记录"
    hf = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    hfont = Font(bold=True, color="FFFFFF")
    headers = ["匹配时间", "客户编号", "客户名称", "申报金额", "申报币种", "流水付款方", "流水金额", "流水币种", "差额", "备注"]
    for idx, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=idx, value=h); cell.font = hfont; cell.fill = hf

    row_idx = 2
    for r in records:
        d_info = decl_map.get(r.declaration_id)
        c_info = cust_map.get(d_info.customer_id) if d_info else None
        # Apply search filter for export too
        if search and c_info:
            if search not in c_info.company_name: continue
        if search_code and c_info:
            if search_code not in (c_info.customer_code or ""): continue

        f_info = flow_map.get(r.flow_id)
        vals = [
            str(r.created_at)[:19] if r.created_at else "",
            c_info.customer_code if c_info else "",
            c_info.company_name if c_info else "",
            d_info.amount if d_info else "",
            d_info.currency if d_info else "",
            f_info.payer_name if f_info else "",
            f_info.amount if f_info else "",
            f_info.currency if f_info else "",
            r.amount_diff or 0,
            r.handling_note or "",
        ]
        for c, v in enumerate(vals, 1):
            ws.cell(row=row_idx, column=c, value=str(v) if v is not None else "")
        row_idx += 1

    import io; output = io.BytesIO(); wb.save(output); output.seek(0)
    filename = f"reconciliation_{start_date or 'all'}_{end_date or 'all'}.xlsx"
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": f"attachment; filename={filename}"})
