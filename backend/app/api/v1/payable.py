from app.services import financial_authorization as duties
from app.core.round2_access import mutation_scope, own_scope
from fastapi.responses import StreamingResponse
from fastapi import Body, APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.timezone import thai_now, thai_today
from datetime import datetime, timedelta
from app.database import get_db
from app.models.payable import PayableBill, PayablePlan, PlanTemplate, PayableStatus, PlanStatus, MonthlyOrderVolume
from app.models.supplier import Supplier, SupplierCategory, PurchaseOrder
from app.models.user import User
from app.core.permissions import check_staff_permission, check_staff_permission_any, get_wh_id, get_wh_ids, Role, require_non_labor
from app.services.data_history import record_history
from pydantic import BaseModel
from typing import Optional, List

from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY

_PAYABLE_PERMISSION = MENU_PERMISSIONS_BY_KEY["payable"].label
_PLAN_PERMISSION = MENU_PERMISSIONS_BY_KEY["payment_plans"].label

from app.services.supplier_payable_read import current_supplier_warehouse, filtered_bills, supplier_totals, bill_detail, bill_link_warnings, bill_values, owned, checked_link
from app.services import payable_creation as creation
from app.services import purchase_matching as matching
from app.services import cost_identity as costs

router = APIRouter(dependencies=[Depends(mutation_scope)])

class BillCreate(BaseModel):
    supplier_id: int; bill_number: str; bill_date: str; due_date: str
    amount: float; confirmed_amount: Optional[float] = None
    currency: str = "THB"; remark: Optional[str] = None
    payment_commitment_days: Optional[int] = None
    detail: Optional[str] = None
    is_fund_linked: Optional[str] = None

class PlanCreate(BaseModel):
    plan_name: str; planned_date: str; bill_ids: List[int]; remark: Optional[str] = None
    save_as_template: bool = False; template_name: Optional[str] = None

@router.get("", dependencies=[Depends(require_non_labor)])
async def list_bills(
    page: int = 1, page_size: int = 20, supplier_id: int = None,
    status: str = None, month: str = None, start_date: str = None, end_date: str = None,
    source: str = None, purchase_order_number: str = None, currency: str = None, effective_only: bool = False,
    warehouse_id: int = Depends(current_supplier_warehouse),
    current_user: User = Depends(check_staff_permission_any(_PAYABLE_PERMISSION, _PLAN_PERMISSION)), db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query, _, _ = filtered_bills(db, warehouse_id, start_date=start_date, end_date=end_date, month=month,
        supplier_id=supplier_id, currency=currency, status=status, source=source,
        purchase_order_number=purchase_order_number, effective_only=effective_only)
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(query.order_by(PayableBill.due_date.asc()).offset((page-1)*page_size).limit(page_size))
    bills = result.scalars().all()
    sids = {b.supplier_id for b in bills}
    smap = {}
    if sids:
        sups = (await db.execute(select(Supplier).where(Supplier.id.in_(sids), Supplier.warehouse_id == warehouse_id))).scalars().all()
        smap = {s.id: s.name for s in sups}
    # 关联采购单号映射
    po_ids = {b.purchase_order_id for b in bills if b.purchase_order_id}
    po_map = {}
    if po_ids:
        pos = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id.in_(po_ids), PurchaseOrder.warehouse_id == warehouse_id))).scalars().all()
        po_map = {p.id: p.order_number for p in pos}
    link_warnings = await bill_link_warnings(db, bills, warehouse_id)
    # 自动标记逾期（due_date < now 且未付）
    from sqlalchemy import update as sql_update
    import sqlalchemy
    expire_sql = (
        sql_update(PayableBill)
        .where(PayableBill.due_date < thai_now())
        .where(PayableBill.status.in_([PayableStatus.PENDING.value, PayableStatus.PARTIALLY_PAID.value]))
        .values(status=PayableStatus.OVERDUE.value)
    )
    if current_user.role != Role.SUPER_ADMIN:
        expire_sql = expire_sql.where(PayableBill.warehouse_id == warehouse_id)
    try:
        await db.execute(expire_sql)
        await db.flush()
    except: pass

    return {
        "data": [{
            "id": b.id, "capabilities": await duties.bill_capabilities(db,current_user,b), "warehouse_id": b.warehouse_id, "supplier_id": b.supplier_id,
            "supplier_name": smap.get(b.supplier_id, ""),
            "bill_number": b.bill_number,
            "bill_date": b.bill_date.isoformat() if b.bill_date else None,
            "due_date": b.due_date.isoformat() if b.due_date else None,
            "amount": b.amount, "confirmed_amount": b.confirmed_amount,
            "currency": b.currency, "paid_amount": b.paid_amount,
            "remaining_amount": bill_values(b)['remaining_amount'], "payment_totals_unknown": b.paid_amount is None,
            "link_warning": link_warnings.get(b.id),
            "status": b.status, "is_duplicate_warned": b.is_duplicate_warned,
            "payment_commitment_days": b.payment_commitment_days,
            "payment_voucher": b.payment_voucher, "payment_method": b.payment_method, "bill_attachment": b.bill_attachment,
            "is_fund_linked": b.is_fund_linked, "detail": b.detail, "remark": b.remark,
            "diff_note": b.diff_note,
            "source": b.source or "manual", "purchase_order_id": b.purchase_order_id,
            "purchase_order_number": po_map.get(b.purchase_order_id, "") if b.purchase_order_id else "",
            "need_boss_confirm": b.need_boss_confirm,
        } for b in bills],
        "total": total, "page": page, "page_size": page_size,
    }

@router.post("")
async def create_bill(
    supplier_id: int = Form(...),
    bill_number: str = Form(...),
    bill_date: str = Form(...),
    due_date: str = Form(...),
    amount: float = Form(...),
    confirmed_amount: float = Form(None),
    currency: str = Form("THB"),
    remark: str = Form(None),
    payment_commitment_days: int = Form(None),
    detail: str = Form(None),
    is_fund_linked: str = Form(None),
    purchase_order_number: str = Form(None),
    request_key: str = Form(None),
    invoice_identity: str = Form(None),
    duplicate_confirmation: str = Form(None),
    matching_kind: str = Form(None),
    cost_confirmation: str = Form(None),
    file: UploadFile = File(...),
    current_user: User = Depends(check_staff_permission(_PAYABLE_PERMISSION)),
    db: AsyncSession = Depends(get_db),
    warehouse_id: int = Depends(current_supplier_warehouse),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    wh_id = warehouse_id
    request_key = creation.number(request_key, '请求编号', 100)
    creation.number(bill_number)
    bill_date_obj = creation.valid_date(bill_date, '账单日期')
    due_date_obj = creation.valid_date(due_date, '到期日期')
    creation.valid_amount(amount)
    if confirmed_amount is not None:
        import math
        if not math.isfinite(confirmed_amount) or confirmed_amount < 0:
            raise HTTPException(400, '供应商确认金额必须是非负有限数字')
    if not currency or len(currency) > 5:
        raise HTTPException(400, '请填写有效币种')
    identity, identity_key = creation.invoice_identity(invoice_identity,current_user)
    document_kind = matching.kind(matching_kind)
    await creation.creation_lock(db, warehouse_id)
    await owned(db, Supplier, supplier_id, warehouse_id, "供应商")
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")

    # 关联采购单校验：一张采购单只能生成一张账单
    purchase_order_id = None
    source = "manual"
    import hashlib
    content = await file.read()
    signature = creation.fingerprint({'supplier_id':supplier_id,'bill_number':bill_number,'bill_date':bill_date_obj,
        'due_date':due_date_obj,'amount':amount,'currency':currency,'confirmed_amount':confirmed_amount,
        'remark':remark,'payment_commitment_days':payment_commitment_days,'detail':detail,'is_fund_linked':is_fund_linked,
        'purchase_order_number':purchase_order_number,**({'matching_kind':document_kind} if document_kind!='unknown' else {}),
        'invoice_key':identity_key,'attachment_sha256':hashlib.sha256(content).hexdigest()})
    replay = await creation.creation_replay(db,warehouse_id,request_key,signature)
    if replay:
        return {'id':replay.id,'message':'该次登记已保存，未重复新增','replayed':True,
            'has_diff':replay.confirmed_amount is not None and replay.confirmed_amount != replay.amount,'diff_note':replay.diff_note}
    po = None
    if purchase_order_number and creation.normalized(purchase_order_number):
        po = await creation.purchase_by_number(db,warehouse_id,purchase_order_number)
        if po.supplier_id != supplier_id or po.currency != currency: raise HTTPException(400, "采购单的供应商或币种与账单不一致")
        if po.status != "confirmed": raise HTTPException(400, "仅已生效采购单可关联账单")
        if await creation.active_purchase_bill(db,po):
            raise HTTPException(409, '该采购单已生成有效应付，不能重复生成')
        purchase_order_id = po.id
        source = "purchase_order"

    # Validation, identity/duplicate checks and DB uniqueness are completed before writing the attachment.
    import os, uuid
    from app.services.image_utils import save_image
    ext = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "png"
    fname = f"{uuid.uuid4().hex}.{ext}"

    # 对账差异检测
    has_diff = False
    diff_note = None
    if confirmed_amount is not None and confirmed_amount != amount:
        has_diff = True
        diff_note = f"供应商确认金额 {confirmed_amount} 与仓库记录 {amount} 不一致"

    b = PayableBill(
        warehouse_id=wh_id, supplier_id=supplier_id,
        bill_number=bill_number,
        bill_date=bill_date_obj,
        due_date=due_date_obj,
        amount=amount, confirmed_amount=confirmed_amount, diff_note=diff_note,
        currency=currency, detail=detail, remark=remark,
        payment_commitment_days=payment_commitment_days,
        is_fund_linked=is_fund_linked,
        source=source, purchase_order_id=purchase_order_id,
        invoice_identity=identity, invoice_identity_key=identity_key, matching_kind=document_kind,
        create_request_key=request_key,create_request_fingerprint=signature,
        created_by=current_user.id,
    )
    await creation.register_bill(db,b,current_user,duplicate_confirmation,cost_confirmation)
    # 关联采购单：回写 payable_bill_id
    if purchase_order_id:
        if po:
            po.payable_bill_id = b.id
            await db.flush()
    result = save_image(content, "/app/uploads/bill_attachments", "/uploads/bill_attachments", fname)
    b.bill_attachment = b.voucher = result['path']
    await db.flush()
    return {"id": b.id, "message": "账单创建成功", "has_diff": has_diff, "diff_note": diff_note}

@router.post("/{bill_id}/upload-voucher")
async def upload_voucher(bill_id: int, file: UploadFile = File(...),
                         current_user: User = Depends(check_staff_permission(_PAYABLE_PERMISSION)),
                         db: AsyncSession = Depends(get_db), warehouse_id: int = Depends(current_supplier_warehouse)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    result = await db.execute(select(PayableBill).where(PayableBill.id == bill_id))
    b = result.scalar_one_or_none()
    if not b: raise HTTPException(404, "账单不存在")
    if current_user.role != Role.SUPER_ADMIN and b.warehouse_id != warehouse_id:
        raise HTTPException(403, "无权操作其他仓库的账单")
    import os, uuid
    from app.services.image_utils import save_image
    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "png"
    fname = f"{uuid.uuid4().hex}.{ext}"
    content = await file.read()
    result = save_image(content, "/app/uploads/payment_vouchers", "/uploads/payment_vouchers", fname)
    b.payment_voucher = result["path"]
    await db.flush()
    return {"message": "凭证上传成功", "path": b.payment_voucher}

@router.post("/{bill_id}/upload-attachment")
async def upload_bill_attachment(bill_id: int, file: UploadFile = File(...),
                                 current_user: User = Depends(check_staff_permission(_PAYABLE_PERMISSION)),
                                 db: AsyncSession = Depends(get_db), warehouse_id: int = Depends(current_supplier_warehouse)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    result = await db.execute(select(PayableBill).where(PayableBill.id == bill_id))
    b = result.scalar_one_or_none()
    if not b: raise HTTPException(404, "账单不存在")
    if current_user.role != Role.SUPER_ADMIN and b.warehouse_id != warehouse_id:
        raise HTTPException(403, "无权操作其他仓库的账单")
    import os, uuid
    from app.services.image_utils import save_image
    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "pdf"
    fname = f"{uuid.uuid4().hex}.{ext}"
    content = await file.read()
    result = save_image(content, "/app/uploads/bill_attachments", "/uploads/bill_attachments", fname)
    b.bill_attachment = result["path"]
    await db.flush()
    return {"message": "账单附件上传成功", "path": b.bill_attachment}

@router.put("/{bill_id}/pay")
async def pay_bill(bill_id: int, paid_amount: float = None, payment_method: str = None, account_id: int = None, request_key: str = None,
                   current_user: User = Depends(check_staff_permission(_PAYABLE_PERMISSION)),
                   db: AsyncSession = Depends(get_db), warehouse_id: int = Depends(current_supplier_warehouse)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.STAFF):
        raise HTTPException(403, "无权限")
    await matching.scope_lock(db,warehouse_id)
    b = (await db.execute(select(PayableBill).where(PayableBill.id == bill_id).with_for_update()
        .execution_options(populate_existing=True))).scalar_one_or_none()
    if not b: raise HTTPException(404, "账单不存在")
    if b.warehouse_id != warehouse_id: raise HTTPException(403, "无权操作其他仓库的账单")
    await bill_detail(db,b.id,warehouse_id)
    from app.services.payable_payment import record_payment
    from app.services.wallet import money
    row = await record_payment(db, b, paid_amount if paid_amount is not None else money(b.amount) - money(b.paid_amount),
        account_id, payment_method, current_user, request_key)
    return {"warning":getattr(row,"_balance_warning",None),"message": "付款记录成功", "payment_id": row.id, "amount": float(row.amount),
        "account_id": row.account_id, "paid_at": row.paid_at.isoformat()}

@router.put("/{bill_id}/confirm", dependencies=[Depends(require_non_labor)])
async def confirm_bill(bill_id: int, req: Optional[dict] = Body(None),
        current_user: User = Depends(check_staff_permission(_PAYABLE_PERMISSION)), db: AsyncSession = Depends(get_db),
        warehouse_id: int = Depends(current_supplier_warehouse)):
    if current_user.role != Role.WAREHOUSE_ADMIN:
        raise HTTPException(403, "只有仓库管理员可以确认")
    reason=(req or {}).get("reason")
    if not isinstance(reason,str) or not reason.strip() or len(reason)>1000:
        raise HTTPException(400,"请填写本次匹配复核原因（不超过1000字）")
    await matching.scope_lock(db,warehouse_id)
    b=(await db.execute(select(PayableBill).where(PayableBill.id==bill_id).with_for_update())).scalar_one_or_none()
    if b is None: raise HTTPException(404,"账单不存在")
    if b.warehouse_id!=warehouse_id: raise HTTPException(403,"无权操作其他仓库的账单")
    if b.status=='voided': raise HTTPException(400,"已作废账单不能复核")
    state=await matching.matching(db,b)
    if state['review_valid'] and b.match_review.get('reason')==reason:
        return {"message":"本次匹配已复核，未重复留痕","replayed":True,"review":b.match_review}
    old=b.match_review
    b.match_review={"reason":reason,"operator_id":current_user.id,"operator_name":current_user.display_name,
        "confirmed_at":thai_now().isoformat(),"snapshot_hash":state['snapshot_hash'],"snapshot":state['snapshot'],
        "result":{k:state[k] for k in ('status','kind','quantity_match','receipt_quantity_match','amount_match','notes')}}
    b.need_boss_confirm="false"
    await record_history(db,module='payable',record_id=b.id,operator=current_user,operation_type='match_confirm',
        before=old,after=b.match_review,warehouse_id=warehouse_id)
    await db.flush()
    return {"message":"匹配复核已留痕，后续变动须重新复核；付款仍按当前校验规则","review":b.match_review}

@router.put("/{bill_id}/void")
async def void_bill(bill_id: int, void_reason: str = None,
                    current_user: User = Depends(check_staff_permission(_PAYABLE_PERMISSION)),
                    db: AsyncSession = Depends(get_db), warehouse_id: int = Depends(current_supplier_warehouse)):
    """作废账单（留痕，不真删）。仅仓库管理员/主管可操作。"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role != Role.WAREHOUSE_ADMIN:
        raise HTTPException(403, "无权限")
    await costs.lock(db,warehouse_id)
    b = (await db.execute(select(PayableBill).where(PayableBill.id == bill_id).with_for_update())).scalar_one_or_none()
    if not b:
        raise HTTPException(404, "账单不存在")
    if current_user.role != Role.SUPER_ADMIN and b.warehouse_id != warehouse_id:
        raise HTTPException(403, "只能操作自己仓库的账单")
    if not void_reason or not str(void_reason).strip():
        raise HTTPException(400, "请填写作废原因")
    if b.status == PayableStatus.PAID.value:
        raise HTTPException(400, "已付款的账单不能作废")
    if b.status == PayableStatus.VOIDED.value:
        raise HTTPException(400, "该账单已作废")
    old_status = b.status
    reason = str(void_reason).strip()
    b.status = PayableStatus.VOIDED.value
    b.void_reason = reason
    b.voided_by = current_user.id
    b.voided_at = thai_now()
    await costs.sync(db,'payable',b,current_user,skip_suspicion=True)
    await db.flush()
    await record_history(db, module="payable", record_id=b.id, operator=current_user,
                         operation_type="void",
                         before={"status": old_status},
                         after={"status": PayableStatus.VOIDED.value, "void_reason": reason},
                         warehouse_id=b.warehouse_id)
    return {"message": "账单已作废"}

class BillUpdate(BaseModel):
    supplier_id: Optional[int] = None
    bill_number: Optional[str] = None
    currency: Optional[str] = None
    purchase_order_number: Optional[str] = None
    bill_date: Optional[str] = None
    due_date: Optional[str] = None
    amount: Optional[float] = None
    confirmed_amount: Optional[float] = None
    payment_commitment_days: Optional[int] = None
    detail: Optional[str] = None
    remark: Optional[str] = None
    diff_note: Optional[str] = None
    duplicate_confirmation: Optional[dict] = None
    matching_kind: Optional[str] = None
    cost_confirmation: Optional[dict] = None
    invoice_identity: Optional[dict] = None

@router.put("/{bill_id}")
async def update_bill(bill_id: int, req: BillUpdate,
                      current_user: User = Depends(check_staff_permission(_PAYABLE_PERMISSION)),
                      db: AsyncSession = Depends(get_db), warehouse_id: int = Depends(current_supplier_warehouse)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    await creation.creation_lock(db,warehouse_id)
    result = await db.execute(select(PayableBill).where(PayableBill.id == bill_id).with_for_update())
    b = result.scalar_one_or_none()
    if not b: raise HTTPException(404, "账单不存在")
    if current_user.role != Role.SUPER_ADMIN and b.warehouse_id != warehouse_id:
        raise HTTPException(403, "只能编辑自己仓库的账单")

    # 已付款账单只允许改 备注 和 差异处理说明
    provided = req.model_dump(exclude_none=True)
    if b.status == PayableStatus.PAID.value or (b.paid_amount or 0) > 0:
        disallowed = [k for k in provided.keys() if k not in ("remark", "diff_note", "cost_confirmation")]
        if disallowed:
            raise HTTPException(400, "已付款的账单只能修改备注")

    if req.matching_kind is not None: matching.kind(req.matching_kind)
    # 金额不能为 0 或负数
    if req.amount is not None: creation.valid_amount(req.amount)
    if req.bill_number is not None: creation.number(req.bill_number)
    if b.invoice_identity_key and req.supplier_id is not None and req.supplier_id != b.supplier_id:
        raise HTTPException(400,'已核实发票身份的账单不能直接更换供应商，请核对原单')

    # 日期格式校验
    bill_date_obj = None
    due_date_obj = None
    if req.bill_date is not None:
        try:
            bill_date_obj = datetime.fromisoformat(req.bill_date)
        except Exception:
            raise HTTPException(400, "账单日期格式不正确")
    if req.due_date is not None:
        try:
            due_date_obj = datetime.fromisoformat(req.due_date)
        except Exception:
            raise HTTPException(400, "到期日期格式不正确")

    await owned(db, Supplier, req.supplier_id if req.supplier_id is not None else b.supplier_id, warehouse_id, "供应商")
    if b.purchase_order_id:
        existing_po=await db.get(PurchaseOrder,b.purchase_order_id)
        if existing_po is None: raise HTTPException(409,"关联采购单缺失，请管理员核对")
        await checked_link(db,b,existing_po,warehouse_id)
    # 修改前快照（用于写修改日志，只记真正变化的字段）
    def _d(dt):
        return dt.strftime("%Y-%m-%d") if dt else None
    old_po = None
    if b.purchase_order_id:
        old_po = (await db.execute(
            select(PurchaseOrder).where(PurchaseOrder.id == b.purchase_order_id)
        )).scalar_one_or_none()
    before_map = {
        "supplier_id": b.supplier_id,
        "matching_kind": b.matching_kind,
        "bill_number": b.bill_number,
        "currency": b.currency,
        "purchase_order_number": old_po.order_number if old_po else None,
        "bill_date": _d(b.bill_date),
        "due_date": _d(b.due_date),
        "amount": b.amount,
        "confirmed_amount": b.confirmed_amount,
        "payment_commitment_days": b.payment_commitment_days,
        "detail": b.detail,
        "remark": b.remark,
        "diff_note": b.diff_note,
    }

    # 关联采购单号
    if req.purchase_order_number is not None:
        po_num = creation.normalized(req.purchase_order_number)
        if po_num:
            po = await creation.purchase_by_number(db,warehouse_id,po_num)
            if po.supplier_id != (req.supplier_id if req.supplier_id is not None else b.supplier_id) or po.currency != (req.currency or b.currency):
                raise HTTPException(400,"采购单的供应商或币种与账单不一致")
            if po.status != "confirmed": raise HTTPException(400,"仅已生效采购单可关联账单")
            existing_bill=await creation.active_purchase_bill(db,po,allow_bill_id=b.id)
            if existing_bill and existing_bill.id != b.id:
                raise HTTPException(409, '该采购单已生成有效应付，不能重复关联')
            # 更换采购单时，先解除旧采购单回写
            if b.purchase_order_id and b.purchase_order_id != po.id:
                old_po = (await db.execute(
                    select(PurchaseOrder).where(PurchaseOrder.id == b.purchase_order_id)
                )).scalar_one_or_none()
                if old_po and old_po.payable_bill_id == b.id:
                    old_po.payable_bill_id = None
            b.purchase_order_id = po.id
            b.source = "purchase_order"
            po.payable_bill_id = b.id
        else:
            # 清空关联
            if b.purchase_order_id:
                old_po = (await db.execute(
                    select(PurchaseOrder).where(PurchaseOrder.id == b.purchase_order_id)
                )).scalar_one_or_none()
                if old_po and old_po.payable_bill_id == b.id:
                    old_po.payable_bill_id = None
            b.purchase_order_id = None
            b.source = "manual"

    # 应用其余字段
    if req.matching_kind is not None: b.matching_kind=matching.kind(req.matching_kind)
    if 'invoice_identity' in req.model_fields_set:
        b.invoice_identity,b.invoice_identity_key=creation.invoice_identity(req.invoice_identity,current_user)
    if req.supplier_id is not None:
        b.supplier_id = req.supplier_id
    if req.bill_number is not None:
        b.bill_number = req.bill_number
    if req.currency is not None:
        b.currency = req.currency
    if bill_date_obj is not None:
        b.bill_date = bill_date_obj
    if due_date_obj is not None:
        b.due_date = due_date_obj
    if req.amount is not None:
        b.amount = req.amount
    if req.confirmed_amount is not None:
        b.confirmed_amount = req.confirmed_amount
    if req.payment_commitment_days is not None:
        b.payment_commitment_days = req.payment_commitment_days
    if req.detail is not None:
        b.detail = req.detail
    if req.remark is not None:
        b.remark = req.remark
    if req.diff_note is not None:
        b.diff_note = req.diff_note

    if any(k in provided for k in ('supplier_id','bill_number','amount','bill_date','currency','purchase_order_number')):
        with db.no_autoflush:
            confirmation = await creation.check_duplicates(db,b,current_user,req.duplicate_confirmation,exclude_id=b.id)
        if confirmation:
            b.duplicate_confirmation=confirmation
            await record_history(db,module='payable',record_id=b.id,operator=current_user,
                operation_type='duplicate_confirm',after=confirmation,warehouse_id=warehouse_id)

    # 修改后快照 + 只记真正变化的字段
    new_po = None
    if b.purchase_order_id:
        new_po = (await db.execute(
            select(PurchaseOrder).where(PurchaseOrder.id == b.purchase_order_id)
        )).scalar_one_or_none()
    after_map = {
        "supplier_id": b.supplier_id,
        "matching_kind": b.matching_kind,
        "bill_number": b.bill_number,
        "currency": b.currency,
        "purchase_order_number": new_po.order_number if new_po else None,
        "bill_date": _d(b.bill_date),
        "due_date": _d(b.due_date),
        "amount": b.amount,
        "confirmed_amount": b.confirmed_amount,
        "payment_commitment_days": b.payment_commitment_days,
        "detail": b.detail,
        "remark": b.remark,
        "diff_note": b.diff_note,
    }
    changed_before = {}
    changed_after = {}
    for k in before_map:
        if before_map[k] != after_map[k]:
            changed_before[k] = before_map[k]
            changed_after[k] = after_map[k]
    await db.flush()
    await matching.invalidate_review(db,b,current_user)
    await costs.sync(db,'payable',b,current_user,confirmation=req.cost_confirmation,
        identity=(b.invoice_identity,b.invoice_identity_key) if 'invoice_identity' in req.model_fields_set else costs.UNSET)
    # 与账单更新同事务写修改日志；没有字段变化则不写
    if changed_before:
        await record_history(db, module="payable", record_id=b.id, operator=current_user,
                             operation_type="edit", before=changed_before, after=changed_after,
                             warehouse_id=b.warehouse_id)
    if b.purchase_order_id:
        await checked_link(db,b,await db.get(PurchaseOrder,b.purchase_order_id),warehouse_id)
    return {"message": "账单更新成功", "has_diff": b.confirmed_amount is not None and b.confirmed_amount != b.amount}

# === Stats Dashboard ===
@router.get("/stats", dependencies=[Depends(require_non_labor)])
async def payable_stats(start_date: str = None, end_date: str = None, supplier_id: int = None,
                        currency: str = None, status: str = None, source: str = None,
                        purchase_order_number: str = None, all_dates: bool = False,
                        warehouse_id: int = Depends(current_supplier_warehouse),
                        current_user: User = Depends(check_staff_permission_any(_PAYABLE_PERMISSION, _PLAN_PERMISSION)),
                        db: AsyncSession = Depends(get_db)):
    today = thai_today()
    if start_date is None and end_date is None and not all_dates:
        start_date, end_date = str(today.replace(day=1)), str(today)
    return await supplier_totals(db, warehouse_id, start_date=start_date, end_date=end_date,
        supplier_id=supplier_id, currency=currency, status=status, source=source,
        purchase_order_number=purchase_order_number)


@router.get("/{bill_id}/detail", dependencies=[Depends(require_non_labor)])
async def get_bill_detail(bill_id: int, warehouse_id: int = Depends(current_supplier_warehouse),
        current_user: User = Depends(check_staff_permission_any(_PAYABLE_PERMISSION, _PLAN_PERMISSION)),
        db: AsyncSession = Depends(get_db)):
    return await bill_detail(db, bill_id, warehouse_id)


# === Plans ===
@router.get("/plans", dependencies=[Depends(require_non_labor)])
async def list_plans(current_user: User = Depends(check_staff_permission(_PLAN_PERMISSION)), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(PayablePlan)
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(PayablePlan.warehouse_id.in_(get_wh_ids(current_user)))
    result = await db.execute(query.order_by(PayablePlan.planned_date.desc()))
    plans = result.scalars().all()
    # 自动标记逾期（due_date < now 且未付）
    from sqlalchemy import update as sql_update
    import sqlalchemy
    expire_sql = (
        sql_update(PayableBill)
        .where(PayableBill.due_date < thai_now())
        .where(PayableBill.status.in_([PayableStatus.PENDING.value, PayableStatus.PARTIALLY_PAID.value]))
        .values(status=PayableStatus.OVERDUE.value)
    )
    if current_user.role != Role.SUPER_ADMIN:
        expire_sql = expire_sql.where(PayableBill.warehouse_id.in_(get_wh_ids(current_user)))
    try:
        await db.execute(expire_sql)
        await db.flush()
    except: pass

    return {"data": [{"id": p.id, "capabilities": await duties.plan_capabilities(db,current_user,p), "plan_name": p.plan_name, "planned_date": p.planned_date.isoformat() if p.planned_date else None, "total_amount": p.total_amount, "status": p.status, "bill_ids": p.bill_ids, "bill_attachment": p.bill_attachment, "remark": p.remark} for p in plans]}

@router.post("/plans", dependencies=[Depends(require_non_labor)])
async def create_plan(req: PlanCreate, current_user: User = Depends(check_staff_permission(_PLAN_PERMISSION)),
                      db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    duties.accountant(current_user)
    if not req.bill_ids or len(set(req.bill_ids)) != len(req.bill_ids):
        raise HTTPException(400, '请选择不重复的应付账单')
    wh_ids = get_wh_ids(current_user)
    total = 0
    if req.bill_ids:
        bills = (await db.execute(select(PayableBill).where(PayableBill.id.in_(req.bill_ids)))).scalars().all()
        # 校验所有账单都属于当前用户仓库，杜绝把他仓账单纳入计划
        if len(bills) != len(set(req.bill_ids)):
            raise HTTPException(400, "部分账单不存在")
        for b in bills:
            if b.warehouse_id not in wh_ids:
                raise HTTPException(403, "计划中包含非本仓库的账单")
        for bill in bills:
            own_scope(current_user,bill.warehouse_id)
            if bill.warehouse_id != get_wh_id(current_user):
                raise HTTPException(403,'计划中的账单必须全部属于当前仓库')
        # 统计口径：排除已作废账单，且排除未生效(待审批/已驳回)采购单对应的账单
        po_ids = {b.purchase_order_id for b in bills if b.purchase_order_id}
        non_confirmed_po_ids = set()
        if po_ids:
            non_confirmed_po_ids = {
                r[0] for r in (await db.execute(
                    select(PurchaseOrder.id).where(PurchaseOrder.id.in_(po_ids), PurchaseOrder.status != "confirmed")
                )).all()
            }
        total = sum((b.amount or 0) - (b.paid_amount or 0) for b in bills
                    if b.status != PayableStatus.VOIDED.value and b.purchase_order_id not in non_confirmed_po_ids)
    p = PayablePlan(
        warehouse_id=get_wh_id(current_user), plan_name=req.plan_name,
        planned_date=datetime.fromisoformat(req.planned_date),
        total_amount=total, bill_ids=req.bill_ids, remark=req.remark,
        created_by=current_user.id,
    )
    db.add(p); await db.flush()
    await duties.evidence(db,current_user,p,'plan_prepare',duties.payload(p,{'status'}))
    # Save as template if requested
    if req.save_as_template and req.bill_ids:
        tmpl = PlanTemplate(
            warehouse_id=get_wh_id(current_user),
            name=req.template_name or req.plan_name,
            bill_ids=req.bill_ids,
            created_by=current_user.id,
        )
        db.add(tmpl)
    return {"id": p.id, "message": "付款计划创建成功"}

# === Cashflow ===
@router.get("/cashflow-prediction")
async def cashflow_prediction(current_user: User = Depends(check_staff_permission(_PLAN_PERMISSION)),
                              db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(func.coalesce(func.sum(PayableBill.amount - PayableBill.paid_amount), 0))
    query = query.outerjoin(PurchaseOrder, PayableBill.purchase_order_id == PurchaseOrder.id)
    query = query.where(PayableBill.status.in_([PayableStatus.PENDING.value, PayableStatus.PARTIALLY_PAID.value]),
                        (PayableBill.purchase_order_id.is_(None)) | (PurchaseOrder.status == "confirmed"))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(PayableBill.warehouse_id.in_(get_wh_ids(current_user)))
    total_pending = (await db.execute(query)).scalar() or 0
    return {"total_pending_payable": float(total_pending), "predicted_outflow": float(total_pending)}

# === Batch export ===
@router.get("/batch-export", dependencies=[Depends(require_non_labor)])
async def batch_export(supplier_id: int = None, start_date: str = None, end_date: str = None,
                       status: str = None, bill_ids: str = None,
                       current_user: User = Depends(check_staff_permission(_PAYABLE_PERMISSION)), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(PayableBill)
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(PayableBill.warehouse_id.in_(get_wh_ids(current_user)))
    # If specific bill IDs are provided, filter by them
    if bill_ids:
        ids = [int(x.strip()) for x in bill_ids.split(",") if x.strip().isdigit()]
        if ids:
            query = query.where(PayableBill.id.in_(ids))
    else:
        # Otherwise apply status filter (default: pending + partially_paid)
        if status:
            query = query.where(PayableBill.status == status)
        else:
            query = query.where(PayableBill.status.in_([PayableStatus.PENDING.value, PayableStatus.PARTIALLY_PAID.value, PayableStatus.OVERDUE.value]))
    if supplier_id:
        query = query.where(PayableBill.supplier_id == supplier_id)
    if start_date:
        query = query.where(PayableBill.due_date >= datetime.fromisoformat(start_date))
    if end_date:
        query = query.where(PayableBill.due_date < datetime.fromisoformat(end_date) + timedelta(days=1))
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
        .where(PayableBill.due_date < thai_now())
        .where(PayableBill.status.in_([PayableStatus.PENDING.value, PayableStatus.PARTIALLY_PAID.value]))
        .values(status=PayableStatus.OVERDUE.value)
    )
    if current_user.role != Role.SUPER_ADMIN:
        expire_sql = expire_sql.where(PayableBill.warehouse_id.in_(get_wh_ids(current_user)))
    try:
        await db.execute(expire_sql)
        await db.flush()
    except: pass

    return {"data": [{"bill_id": b.id, "supplier": smap.get(b.supplier_id, {}).get("name", ""), "amount": b.amount, "paid_amount": b.paid_amount, "unpaid": b.amount - b.paid_amount, "currency": b.currency, "due_date": str(b.due_date), "bill_number": b.bill_number, "status": b.status} for b in bills]}

@router.get("/supplier-statement")
async def supplier_statement(supplier_id: int = None, current_user: User = Depends(check_staff_permission(_PAYABLE_PERMISSION)),
                              db: AsyncSession = Depends(get_db)):
    """生成供应商对账单"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(PayableBill)
    if supplier_id: query = query.where(PayableBill.supplier_id == supplier_id)
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(PayableBill.warehouse_id.in_(get_wh_ids(current_user)))
    query = query.where(PayableBill.status != PayableStatus.VOIDED.value)
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


# === Plan Templates ===
@router.get("/plan-templates")
async def list_templates(current_user: User = Depends(check_staff_permission(_PLAN_PERMISSION)), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(PlanTemplate)
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(PlanTemplate.warehouse_id.in_(get_wh_ids(current_user)))
    result = await db.execute(query.order_by(PlanTemplate.created_at.desc()))
    return {"data": [{"id": t.id, "name": t.name, "bill_ids": t.bill_ids} for t in result.scalars().all()]}

@router.delete("/plan-templates/{template_id}", dependencies=[Depends(require_non_labor)])
async def delete_template(template_id: int, current_user: User = Depends(check_staff_permission(_PLAN_PERMISSION)), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PlanTemplate).where(PlanTemplate.id == template_id))
    t = result.scalar_one_or_none()
    if not t: raise HTTPException(404, "模板不存在")
    if current_user.role != Role.SUPER_ADMIN and t.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "无权限")
    await db.delete(t); await db.flush()
    return {"message": "模板已删除"}

# === Timeline ===
@router.get("/timeline")
async def payable_timeline(current_user: User = Depends(check_staff_permission(_PLAN_PERMISSION)), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    from datetime import date, timedelta
    today = thai_today()
    monday = today - timedelta(days=today.weekday())
    weeks = []
    for w in range(4):
        start = monday + timedelta(weeks=w)
        end = start + timedelta(days=6)
        label = "本周" if w == 0 else "下周" if w == 1 else f"第{w+1}周"
        q = select(func.coalesce(func.sum(PayableBill.amount - PayableBill.paid_amount), 0)).where(
            PayableBill.due_date >= start, PayableBill.due_date <= end,
            PayableBill.status.in_([PayableStatus.PENDING.value, PayableStatus.PARTIALLY_PAID.value])
        )
        if current_user.role != Role.SUPER_ADMIN:
            q = q.where(PayableBill.warehouse_id.in_(get_wh_ids(current_user)))
        total = float((await db.execute(q)).scalar() or 0)
        weeks.append({"label": label, "start": start.isoformat(), "end": end.isoformat(), "total": total})
    return {"data": weeks}

# === Execute Plan ===
@router.put("/plans/{plan_id}/execute", dependencies=[Depends(require_non_labor)])
async def execute_plan(plan_id: int, account_id: int = None, current_user: User = Depends(check_staff_permission(_PLAN_PERMISSION)), db: AsyncSession = Depends(get_db), warehouse_id: int = Depends(current_supplier_warehouse)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    duties.accountant(current_user)
    await matching.scope_lock(db,warehouse_id)
    result = await db.execute(select(PayablePlan).where(PayablePlan.id == plan_id).with_for_update())
    p = result.scalar_one_or_none()
    if not p: raise HTTPException(404, "计划不存在")
    if current_user.role != Role.SUPER_ADMIN and p.warehouse_id != warehouse_id:
        raise HTTPException(403, "无权限")
    if p.status != PlanStatus.PENDING.value:
        raise HTTPException(400, "该计划已执行或已取消")
    await duties.proof(db,p,'plan_prepare',duties.payload(p,{'status'}))
    from app.services.wallet import money
    if not p.bill_ids or len(set(p.bill_ids)) != len(p.bill_ids):
        raise HTTPException(409,'付款计划账单无效')
    bills=(await db.execute(select(PayableBill).where(PayableBill.id.in_(p.bill_ids)).order_by(PayableBill.id).with_for_update())).scalars().all()
    if len(bills)!=len(p.bill_ids):raise HTTPException(409,'计划中包含不存在的账单')
    for bill in bills:
        if bill.warehouse_id!=warehouse_id:raise HTTPException(403,'计划中包含外仓账单')
        if bill.status in ('paid','voided'):raise HTTPException(409,'计划中包含已付或作废账单')
        await duties.execute_bill(db,current_user,bill)
    if len({b.currency or 'THB' for b in bills})!=1:
        raise HTTPException(409,'同一执行批次不能混合币种')
    if sum(money(b.amount)-money(b.paid_amount) for b in bills)!=money(p.total_amount):
        raise HTTPException(409,'计划金额已失效，请按当前剩余应付重新生成计划')
    warnings=[]
    paid_count=0
    from app.services.payable_payment import record_payment
    for bill in bills:
        await bill_detail(db,bill.id,warehouse_id)
        payment=await record_payment(db,bill,money(bill.amount)-money(bill.paid_amount),account_id,
            bill.payment_method or '银行转账',current_user)
        if getattr(payment,'_balance_warning',None): warnings.append(payment._balance_warning)
        paid_count+=1
    p.status = PlanStatus.EXECUTED.value
    await db.flush()
    return {"warning":warnings[0] if warnings else None,"warnings":warnings,"message": f"计划执行成功，已结算 {paid_count} 笔账单"}

# === Plan Detail ===
@router.get("/plans/{plan_id}/detail")
async def plan_detail(plan_id: int, current_user: User = Depends(check_staff_permission(_PLAN_PERMISSION)), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PayablePlan).where(PayablePlan.id == plan_id))
    p = result.scalar_one_or_none()
    if not p: raise HTTPException(404, "计划不存在")
    if current_user.role != Role.SUPER_ADMIN and p.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "无权查看其他仓库的付款计划")
    bills_data = []
    if p.bill_ids:
        bills = (await db.execute(select(PayableBill).where(PayableBill.id.in_(p.bill_ids)))).scalars().all()
        sids = {b.supplier_id for b in bills}
        smap = {}
        if sids:
            sups = (await db.execute(select(Supplier).where(Supplier.id.in_(sids)))).scalars().all()
            smap = {s.id: s.name for s in sups}
        bills_data = [{
            "id": b.id, "supplier_name": smap.get(b.supplier_id, ""),
            "bill_number": b.bill_number, "amount": b.amount, "currency": b.currency or "THB",
            "due_date": b.due_date.isoformat() if b.due_date else None,
            "status": b.status, "paid_amount": b.paid_amount,
        } for b in bills]
    return {
        "plan": {"id": p.id, "capabilities": await duties.plan_capabilities(db,current_user,p), "plan_name": p.plan_name, "planned_date": p.planned_date.isoformat() if p.planned_date else None, "total_amount": p.total_amount, "status": p.status, "bill_attachment": p.bill_attachment, "remark": p.remark},
        "bills": bills_data,
        "bill_count": len(bills_data),
    }


@router.post("/plans/{plan_id}/upload-attachment")
async def upload_plan_attachment(plan_id: int, file: UploadFile = File(...),
                                 current_user: User = Depends(check_staff_permission(_PLAN_PERMISSION)),
                                 db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    p = (await db.execute(select(PayablePlan).where(PayablePlan.id == plan_id))).scalar_one_or_none()
    if not p:
        raise HTTPException(404, "付款计划不存在")
    if current_user.role != Role.SUPER_ADMIN and p.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "无权操作其他仓库的付款计划")
    import uuid
    from app.services.image_utils import save_image
    ext = file.filename.split(".")[-1] if file.filename and "." in file.filename else "bin"
    fname = f"{uuid.uuid4().hex}.{ext}"
    content = await file.read()
    result = save_image(content, "/app/uploads/plan_attachments", "/uploads/plan_attachments", fname)
    p.bill_attachment = result["path"]
    await db.flush()
    return {"message": "附件上传成功", "path": p.bill_attachment}


# === Export Plan ===
@router.get("/plans/export")
async def export_plans(plan_id: int = None, current_user: User = Depends(check_staff_permission(_PLAN_PERMISSION)), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    query = select(PayablePlan)
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(PayablePlan.warehouse_id.in_(get_wh_ids(current_user)))
    if plan_id:
        query = query.where(PayablePlan.id == plan_id)
    plans = (await db.execute(query)).scalars().all()

    wb = Workbook(); ws = wb.active; ws.title = "付款计划导出"
    hf = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    hfont = Font(bold=True, color="FFFFFF")
    for c, h in enumerate(["计划名称", "计划日期", "总金额", "状态", "关联账单数"], 1):
        cell = ws.cell(row=1, column=c, value=h); cell.font = hfont; cell.fill = hf
    for r, p in enumerate(plans, 2):
        vals = [p.plan_name, str(p.planned_date)[:10] if p.planned_date else "", p.total_amount, p.status, len(p.bill_ids or [])]
        for c, v in enumerate(vals, 1): ws.cell(row=r, column=c, value=str(v) if v is not None else "")
    import io; output = io.BytesIO(); wb.save(output); output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": "attachment; filename=payment_plans.xlsx"})


# === Monthly Order Volume ===
class MonthOrderReq(BaseModel):
    month: str; order_count: int

@router.get("/monthly-order")
async def get_monthly_order(
    start_month: str = None, end_month: str = None,
    current_user: User = Depends(check_staff_permission(_PAYABLE_PERMISSION)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(MonthlyOrderVolume).where(MonthlyOrderVolume.warehouse_id.in_(get_wh_ids(current_user)))
    if start_month:
        query = query.where(MonthlyOrderVolume.month >= start_month)
    if end_month:
        query = query.where(MonthlyOrderVolume.month <= end_month)
    result = await db.execute(query.order_by(MonthlyOrderVolume.month))
    return {"data": [{"month": r.month, "order_count": r.order_count} for r in result.scalars().all()]}

@router.post("/monthly-order")
async def save_monthly_order(
    req: MonthOrderReq, current_user: User = Depends(check_staff_permission(_PAYABLE_PERMISSION)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    # Upsert
    existing = (await db.execute(
        select(MonthlyOrderVolume).where(
            MonthlyOrderVolume.warehouse_id.in_(get_wh_ids(current_user)),
            MonthlyOrderVolume.month == req.month,
        )
    )).scalar_one_or_none()
    if existing:
        existing.order_count = req.order_count
        existing.updated_by = current_user.id
    else:
        r = MonthlyOrderVolume(
            warehouse_id=get_wh_id(current_user), month=req.month,
            order_count=req.order_count, updated_by=current_user.id,
        )
        db.add(r)
    await db.flush()
    return {"message": "保存成功"}

# === Trend Data ===
@router.get("/trend")
async def payable_trend(
    months: int = 6,
    current_user: User = Depends(check_staff_permission(_PAYABLE_PERMISSION)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    from datetime import date, timedelta
    import calendar

    # Find consumable category id
    cat_result = await db.execute(select(SupplierCategory).where(SupplierCategory.name == "耗材商"))
    cat = cat_result.scalar_one_or_none()
    con_supplier_ids = []
    if cat:
        sup_result = await db.execute(select(Supplier.id).where(Supplier.category_id == cat.id))
        con_supplier_ids = [r[0] for r in sup_result.all()]

    today = thai_today()
    months_list = []
    for i in range(months - 1, -1, -1):
        m = today.month - i; y = today.year
        if m <= 0: m += 12; y -= 1
        months_list.append(f"{y}-{m:02d}")

    # Monthly order volumes
    order_q = select(MonthlyOrderVolume).where(
        MonthlyOrderVolume.warehouse_id.in_(get_wh_ids(current_user)),
        MonthlyOrderVolume.month.in_(months_list),
    )
    order_rows = (await db.execute(order_q)).scalars().all()
    order_map = {r.month: r.order_count for r in order_rows}

    # Monthly consumable spending
    spending_map = {}
    for month in months_list:
        m_start = datetime.fromisoformat(f"{month}-01")
        last_day = calendar.monthrange(int(month[:4]), int(month[5:]))[1]
        m_end = datetime.fromisoformat(f"{month}-{last_day:02d}") + timedelta(days=1) - timedelta(microseconds=1)
        q = select(func.coalesce(func.sum(PayableBill.amount), 0)).outerjoin(
            PurchaseOrder, PayableBill.purchase_order_id == PurchaseOrder.id
        ).where(
            PayableBill.warehouse_id.in_(get_wh_ids(current_user)),
            PayableBill.status != PayableStatus.VOIDED.value,
            PayableBill.bill_date >= m_start,
            PayableBill.bill_date <= m_end,
            (PayableBill.purchase_order_id.is_(None)) | (PurchaseOrder.status == "confirmed"),
        )
        if con_supplier_ids:
            q = q.where(PayableBill.supplier_id.in_(con_supplier_ids))
        total = float((await db.execute(q)).scalar() or 0)
        spending_map[month] = total

    # Build response
    data = []
    prev_order = None; prev_spending = None
    warnings = []
    for i, month in enumerate(months_list):
        order = order_map.get(month, 0)
        spending = spending_map.get(month, 0)
        data.append({"month": month, "order_count": order, "consumable_spending": spending})
        # Check anomaly: order flat/down but spending up > 20%
        if i > 0 and prev_order is not None and prev_spending is not None:
            if order <= prev_order and spending > prev_spending * 1.2:
                warnings.append(f"{month}: 订单量持平或下降，但耗材支出上涨超20%")
        prev_order = order; prev_spending = spending

    return {"data": data, "warnings": warnings}


@router.post("/{bill_id}/verify-payment")
async def verify_bill_payment(bill_id: int, current_user: User = Depends(check_staff_permission(_PAYABLE_PERMISSION)), db: AsyncSession = Depends(get_db), warehouse_id: int = Depends(current_supplier_warehouse)):
    duties.accountant(current_user)
    await matching.scope_lock(db,warehouse_id)
    bill=(await db.execute(select(PayableBill).where(PayableBill.id==bill_id,PayableBill.warehouse_id==warehouse_id).with_for_update())).scalar_one_or_none()
    if bill is None:raise HTTPException(404,'应付不存在或不属于当前仓库')
    if bill.status in ('paid','voided'):raise HTTPException(409,'该账单不能核验')
    await duties.independent(db,current_user,bill.created_by)
    await duties.evidence(db,current_user,bill,'bill_verify',await duties.bill_payload(db,bill))
    return {'message':'应付已核验，采购/匹配确认不等于资金批准'}

@router.post("/{bill_id}/approve-payment")
async def approve_bill_payment(bill_id: int, current_user: User = Depends(check_staff_permission(_PAYABLE_PERMISSION)), db: AsyncSession = Depends(get_db), warehouse_id: int = Depends(current_supplier_warehouse)):
    duties.approver(current_user)
    await matching.scope_lock(db,warehouse_id)
    bill=(await db.execute(select(PayableBill).where(PayableBill.id==bill_id,PayableBill.warehouse_id==warehouse_id).with_for_update())).scalar_one_or_none()
    if bill is None:raise HTTPException(404,'应付不存在或不属于当前仓库')
    if bill.status in ('paid','voided'):raise HTTPException(409,'该账单不能批准')
    await duties.independent(db,current_user,bill.created_by)
    value=await duties.bill_payload(db,bill)
    await duties.proof(db,bill,'bill_verify',value)
    await duties.evidence(db,current_user,bill,'bill_approve',value)
    return {'message':'资金已批准，等待独立财务执行；未付款'}
