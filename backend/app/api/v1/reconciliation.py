from fastapi.responses import StreamingResponse
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.core.timezone import thai_now, thai_today
from datetime import datetime, date, timedelta
from app.database import get_db
from app.models.recharge import RechargeDeclaration, IncomingFlow, ReconciliationResult, ReconciliationDeclaration, ReconMatchStatus, MatchStatus
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
    ed = (datetime.fromisoformat(end_date) if end_date else datetime(today.year, today.month, today.day)) + timedelta(days=1)

    decl_q = select(RechargeDeclaration).where(and_(
        RechargeDeclaration.warehouse_id.in_(scope),
        RechargeDeclaration.declare_date >= sd,
        RechargeDeclaration.declare_date < ed,
        RechargeDeclaration.match_status == MatchStatus.UNMATCHED,
        ~select(ReconciliationDeclaration.id).where(ReconciliationDeclaration.declaration_id == RechargeDeclaration.id, ReconciliationDeclaration.is_active.is_(True)).exists(),
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
        IncomingFlow.received_date < ed,
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

class ManualMatchInput(BaseModel):
    flow_id: int | None = Field(default=None, gt=0)
    declaration_ids: list[int] = Field(default_factory=list)
    handling_note: str = ""


@router.post("/manual-match")
async def manual_match(
    request: Request,
    declaration_id: int | None = Query(None), flow_id: int | None = Query(None),
    payload: ManualMatchInput | None = Body(None),
    handling_note: str = Query(""),
    current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reconciliation"].label)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.STAFF):
        raise HTTPException(403, "无权限")
    if payload is not None and payload.model_fields_set:
        if declaration_id is not None or flow_id is not None:
            raise HTTPException(400, "请勿同时提交单笔参数和多笔参数")
        flow_id = payload.flow_id
        declaration_ids = payload.declaration_ids
        handling_note = payload.handling_note
    else:
        declaration_ids = [declaration_id] if declaration_id is not None else []
    if not flow_id or not declaration_ids or any(i <= 0 for i in declaration_ids):
        raise HTTPException(400, "请选择一条流水和至少一条申报")
    if len(set(declaration_ids)) != len(declaration_ids):
        raise HTTPException(400, "申报编号不能重复")
    scope = [w.id for w in await warehouse_scope(db,current_user,request.headers.get('X-Warehouse-ID'))]
    # 与撤销保持同一锁顺序；申报按编号加锁，避免交叉选择死锁。
    flow = (await db.execute(select(IncomingFlow).where(IncomingFlow.id == flow_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    declarations = (await db.execute(select(RechargeDeclaration).where(RechargeDeclaration.id.in_(declaration_ids))
        .order_by(RechargeDeclaration.id).with_for_update().execution_options(populate_existing=True))).scalars().all()
    if not flow or len(declarations) != len(declaration_ids):
        raise HTTPException(404, "记录不存在")
    if flow.warehouse_id not in scope or any(d.warehouse_id != flow.warehouse_id for d in declarations):
        raise HTTPException(403, "只能匹配当前同一仓库的记录")
    if flow.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "只能匹配自己仓库的记录")
    linked = (await db.execute(select(ReconciliationDeclaration.id).where(
        ReconciliationDeclaration.declaration_id.in_(declaration_ids), ReconciliationDeclaration.is_active.is_(True)).limit(1))).first()
    if linked or any(d.match_status != MatchStatus.UNMATCHED for d in declarations) or flow.match_status != MatchStatus.UNMATCHED:
        raise HTTPException(400, "所选记录已被匹配")
    decl = next(d for d in declarations if d.id == declaration_ids[0])
    if any(d.customer_id != decl.customer_id for d in declarations):
        raise HTTPException(400, "只能合并同一个客户的申报")
    from app.services.flow_rules import currencies_match
    if any(not currencies_match(d.currency, flow.currency) for d in declarations):
        raise HTTPException(400, "币种不一致，不能合并匹配")
    declared_total = sum((Decimal(str(d.amount)) for d in declarations), Decimal("0"))
    flow_amount = Decimal(str(flow.amount))
    difference = abs(flow_amount - declared_total)
    tolerance = min(Decimal("50"), max(Decimal("20"), flow_amount * Decimal("0.005")))
    if difference > tolerance:
        raise HTTPException(400, f"差额 {difference:.2f} 超出容差 {tolerance:.2f}（超出 {difference - tolerance:.2f}）")
    customer = await db.get(Customer,decl.customer_id)
    if not customer or customer.warehouse_id != decl.warehouse_id: raise HTTPException(409,'申报客户归属异常，请先核对')
    original_customer_id=flow.customer_id
    await bind_receipt(db,customer,flow,current_user)
    rr = ReconciliationResult(
        warehouse_id=decl.warehouse_id,
        reconciliation_month=decl.declare_date.strftime("%Y-%m") if decl.declare_date else thai_now().strftime("%Y-%m"),
        declaration_id=decl.id, flow_id=flow.id,
        match_status=ReconMatchStatus.MANUAL_MATCHED,
        amount_diff=float(difference),
        handling_note=handling_note, confirmed_by=current_user.id, confirmed_at=thai_now(),
    )
    db.add(rr)
    for declaration in declarations:
        declaration.match_status = MatchStatus.MATCHED
    flow.match_status = MatchStatus.MATCHED
    await db.flush()
    for declaration in declarations:
        db.add(ReconciliationDeclaration(reconciliation_id=rr.id, declaration_id=declaration.id, amount=declaration.amount, is_active=True))
    await db.flush()
    from app.services.data_history import record_history
    await record_history(db,module='reconciliation',record_id=rr.id,operator=current_user,operation_type='match',
        before={'customer_id':original_customer_id},after={'flow_id':flow.id,'declaration_id':decl.id,'declaration_ids':declaration_ids,'customer_id':customer.id,'action':'人工确认匹配'},warehouse_id=flow.warehouse_id)
    return {'id':rr.id,'flow_id':flow.id,'declaration_id':decl.id,'declaration_ids':declaration_ids,
        'declaration_count':len(declarations),'decl_amount':float(declared_total),'amount_diff':float(difference),'tolerance':float(tolerance),'customer_id':customer.id,'customer_code':customer.customer_code,
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
    # 固定锁顺序：流水、匹配、明细、申报，串行化重复撤销及重新匹配。
    flow = (await db.execute(select(IncomingFlow).where(IncomingFlow.id==rr.flow_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none() if rr.flow_id else None
    rr = (await db.execute(select(ReconciliationResult).where(ReconciliationResult.id==record_id).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if rr is None or rr.match_status not in ('matched', 'manual_matched'):
        raise HTTPException(409, '匹配已撤销或状态不允许，请刷新列表')
    if rr.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "无权限")
    if flow and flow.warehouse_id!=rr.warehouse_id:
        raise HTTPException(403, '匹配中的到账归属异常，不能操作其他仓库')
    links = (await db.execute(select(ReconciliationDeclaration).where(
        ReconciliationDeclaration.reconciliation_id==rr.id, ReconciliationDeclaration.is_active.is_(True)
    ).order_by(ReconciliationDeclaration.declaration_id).with_for_update().execution_options(populate_existing=True))).scalars().all()
    if not links:
        raise HTTPException(409, '匹配缺少有效关联明细，请先核对迁移')
    declaration_ids = [link.declaration_id for link in links]
    declarations = (await db.execute(select(RechargeDeclaration).where(RechargeDeclaration.id.in_(declaration_ids))
        .order_by(RechargeDeclaration.id).with_for_update().execution_options(populate_existing=True))).scalars().all()
    if len(declarations)!=len(declaration_ids) or any(d.warehouse_id!=rr.warehouse_id for d in declarations):
        raise HTTPException(409, '匹配中的申报缺失或归属异常，请先核对')
    declaration = next((d for d in declarations if d.id==rr.declaration_id), None)
    if declaration is None or any(d.customer_id!=declaration.customer_id for d in declarations):
        raise HTTPException(409, '匹配中的申报客户不一致，请先核对')
    customer = await db.get(Customer, declaration.customer_id)
    if customer and customer.warehouse_id!=rr.warehouse_id:
        raise HTTPException(409, '匹配中的客户归属异常，请先核对')
    from app.services.data_history import record_history
    before = {'status':rr.match_status, 'flow_id':rr.flow_id, 'declaration_ids':declaration_ids,
              'customer_id':flow.customer_id if flow else None}
    restored_customer = False
    # 保持既有客户归属政策：只撤回本次新绑定，不退款、不撤回独立回款。
    if flow and customer:
        from app.models.data_change_history import DataChangeHistory
        from app.models.credit import CreditRepayment
        evidence = (await db.execute(select(DataChangeHistory).where(DataChangeHistory.module=='reconciliation',
            DataChangeHistory.record_id==rr.id, DataChangeHistory.operation_type=='match',
            DataChangeHistory.warehouse_id==rr.warehouse_id).order_by(DataChangeHistory.id.desc()))).scalars().first()
        independent = (await db.execute(select(CreditRepayment.id).where(CreditRepayment.incoming_flow_id==flow.id).limit(1))).scalar_one_or_none()
        other = (await db.execute(select(ReconciliationResult.id).where(ReconciliationResult.flow_id==flow.id,
            ReconciliationResult.id!=rr.id, ReconciliationResult.match_status.in_(('matched','manual_matched'))).limit(1))).scalar_one_or_none()
        if evidence and evidence.after_data.get('flow_id')==flow.id and evidence.before_data.get('customer_id') is None and not independent and not other:
            if flow.customer_id!=customer.id:
                raise HTTPException(409, '到账客户归属已变化，请先核对')
            flow.customer_id = None
            restored_customer = True
        else:
            await bind_receipt(db, customer, flow, current_user)
    for link in links:
        link.is_active = False
    for declaration in declarations:
        declaration.match_status = MatchStatus.UNMATCHED
    if flow:
        flow.match_status = MatchStatus.UNMATCHED
    rr.match_status = ReconMatchStatus.REVOKED
    await record_history(db,module='reconciliation',record_id=rr.id,operator=current_user,operation_type='unmatch',
        before=before,after={'status':'revoked','flow_id':rr.flow_id,'declaration_ids':declaration_ids,
        'customer_id':flow.customer_id if flow else None,'customer_binding_reverted':restored_customer,
        'action':'撤销匹配，保留匹配及关联历史，银行到账保留'},warehouse_id=rr.warehouse_id)
    await db.flush()
    return {'customer_binding_reverted':restored_customer,'declaration_ids':declaration_ids,'flow_id':rr.flow_id,
        "message":"已撤销匹配，客户归属和余额已恢复，银行到账保留" if restored_customer else "已解除申报匹配，独立客户归属保留，未退款"}

def _matched_time_text(value):
    if value is None:
        return "-"
    if not (value.hour or value.minute or value.second or value.microsecond):
        return value.strftime("%Y-%m-%d") + " 未记录时间"
    return value.strftime("%Y-%m-%d %H:%M")


def _matched_time_order(record, declarations, flows):
    declaration = declarations.get(record.declaration_id)
    flow = flows.get(record.flow_id)
    received = flow.received_date if flow else None
    declared = declaration.declare_date if declaration else None
    return (received or declared or datetime.min, record.id)


async def _matched_groups(db, records):
    groups = {}
    if records:
        links = (await db.execute(select(ReconciliationDeclaration).where(
            ReconciliationDeclaration.reconciliation_id.in_([r.id for r in records]),
            ReconciliationDeclaration.is_active.is_(True)
        ).order_by(ReconciliationDeclaration.id))).scalars().all()
        for link in links:
            groups.setdefault(link.reconciliation_id, []).append(link)
    return groups


def _group_amount(links, declaration):
    return float(sum((Decimal(str(link.amount)) for link in links), Decimal("0"))) if links else (declaration.amount if declaration else None)


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
    query = select(ReconciliationResult).where(ReconciliationResult.match_status.in_(("matched", "manual_matched"))); count_q = select(func.count(ReconciliationResult.id)).where(ReconciliationResult.match_status.in_(("matched", "manual_matched")))
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
    groups = await _matched_groups(db, all_records)
    decl_ids = {link.declaration_id for links in groups.values() for link in links} | {r.declaration_id for r in all_records if r.declaration_id}
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

    all_records.sort(key=lambda r: _matched_time_order(r, decl_map, flow_map), reverse=True)

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
        links = groups.get(r.id, [])
        ids = [link.declaration_id for link in links] or ([r.declaration_id] if r.declaration_id else [])
        items.append({
            "id": r.id, "warehouse_id": r.warehouse_id,
            "reconciliation_month": r.reconciliation_month,
            "declaration_id": r.declaration_id, "flow_id": r.flow_id,
            "declaration_ids": ids, "declaration_count": len(ids),
            "match_status": r.match_status or "",
            "amount_diff": r.amount_diff, "handling_note": r.handling_note,
            "customer_code": customer_code, "customer_name": customer_name,
            "declare_time": _matched_time_text(d.declare_date if d else None),
            "received_time": _matched_time_text(f.received_date if f else None),
            "decl_amount": _group_amount(links, d),
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
    query = select(ReconciliationResult).where(ReconciliationResult.match_status.in_(("matched", "manual_matched")))
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
    groups = await _matched_groups(db, records)
    decl_ids = {link.declaration_id for links in groups.values() for link in links} | {r.declaration_id for r in records if r.declaration_id}
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

    records.sort(key=lambda r: _matched_time_order(r, decl_map, flow_map), reverse=True)

    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook(); ws = wb.active; ws.title = "对账记录"
    hf = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    hfont = Font(bold=True, color="FFFFFF")
    headers = ["匹配时间", "客户编号", "客户名称", "申报金额", "申报币种", "流水付款方", "流水金额", "流水币种", "差额", "备注"]
    headers[3:3] = ["申报时间", "流水到账时间", "申报编号", "申报笔数"]
    ws.column_dimensions["D"].width = 26
    ws.column_dimensions["E"].width = 26
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
            _group_amount(groups.get(r.id, []), d_info),
            d_info.currency if d_info else "",
            f_info.payer_name if f_info else "",
            f_info.amount if f_info else "",
            f_info.currency if f_info else "",
            r.amount_diff or 0,
            r.handling_note or "",
        ]
        vals[3:3] = [
            _matched_time_text(d_info.declare_date if d_info else None),
            _matched_time_text(f_info.received_date if f_info else None),
            ";".join(str(link.declaration_id) for link in groups[r.id]) if groups.get(r.id) else str(r.declaration_id or ""),
            len(groups[r.id]) if groups.get(r.id) else (1 if r.declaration_id else 0),
        ]
        for c, v in enumerate(vals, 1):
            ws.cell(row=row_idx, column=c, value=str(v) if v is not None else "")
        row_idx += 1

    import io; output = io.BytesIO(); wb.save(output); output.seek(0)
    filename = f"reconciliation_{start_date or 'all'}_{end_date or 'all'}.xlsx"
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": f"attachment; filename={filename}"})
