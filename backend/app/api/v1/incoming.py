from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile, Request, Form
from fastapi.responses import FileResponse
from pydantic import ValidationError
import hashlib
import json
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from app.database import get_db
from app.models.recharge import IncomingFlow, CurrencyEnum, MatchStatus
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role, require_non_labor, check_staff_permission, check_staff_permission_any
from app.schemas.business import IncomingCreate, IncomingBatchImport
from app.services.incoming_receipts import create_once, incoming_dict, private_directory, screenshot_path
from app.services.customer_receivables import receipt_identity_query
from app.services.warehouse_summary import warehouse_scope
from app.models.customer import Customer

router = APIRouter()

@router.get("", dependencies=[Depends(require_non_labor)])
async def list_incoming(
    request: Request,
    eligible_for_customer_id: int = None, currency: str = None,
    page: int = 1, page_size: int = 20, month: str = None, status: str = None,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission_any("到账流水", "账期管理")),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    scope = [w.id for w in await warehouse_scope(db,current_user,request.headers.get('X-Warehouse-ID'))]
    identity = receipt_identity_query()
    query = select(IncomingFlow,identity.c.customer_id,identity.c.customer_count).outerjoin(identity,identity.c.flow_id == IncomingFlow.id)
    query = query.where(IncomingFlow.warehouse_id.in_(scope))
    if eligible_for_customer_id is not None:
        customer = await db.get(Customer,eligible_for_customer_id)
        if not customer or customer.warehouse_id not in scope: raise HTTPException(403,'只能筛选本仓客户的到账')
        from sqlalchemy import or_
        query = query.where(or_(identity.c.flow_id.is_(None),identity.c.customer_id == customer.id))
    if currency is not None: query = query.where(IncomingFlow.currency == currency)
    if month:
        query = query.where(func.to_char(IncomingFlow.received_date, 'YYYY-MM') == month)
    if status:
        query = query.where(IncomingFlow.match_status == status)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    result = await db.execute(query.order_by(IncomingFlow.created_at.desc()).offset((page-1)*page_size).limit(page_size))
    joined = result.all()
    records = [r[0] for r in joined]
    user_ids = list(set(r.entrant_id for r in records if r.entrant_id))
    user_map = {}
    if user_ids:
        users = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        user_map = {u.id: u.display_name for u in users}
    return {"data": [{**incoming_dict(r,user_map.get(r.entrant_id,"")),"resolved_customer_id":cid,
        "customer_identity_conflict":bool(count and cid is None)} for r,cid,count in joined],
        "total": total, "page": page, "page_size": page_size}

@router.post("")
async def create_incoming(req: IncomingCreate, request: Request, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db),
                          _perm=Depends(check_staff_permission("到账流水"))):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    scope = await warehouse_scope(db,current_user,request.headers.get('X-Warehouse-ID'))
    if len(scope) != 1: raise HTTPException(400,'请先选择一个仓库')
    wh_id = scope[0].id
    r, created = await create_once(db, req, wh_id, current_user)
    from app.services.incoming_suggestions import suggestions_for
    suggestions=(await suggestions_for(db,[r]))[r.id]
    return {**incoming_dict(r), "suggestions":suggestions,"created": created, "message": "录入成功" if created else "到账已保存，未重复录入"}


@router.get("/by-request/{request_key}", dependencies=[Depends(require_non_labor)])
async def lookup_incoming(request_key: str, current_user=Depends(check_staff_permission("到账流水")), db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    row = (await db.execute(select(IncomingFlow).where(IncomingFlow.warehouse_id == get_wh_id(current_user),
        IncomingFlow.request_key == request_key))).scalar_one_or_none()
    if row is None: raise HTTPException(404, "尚未找到本次到账")
    from app.services.incoming_suggestions import suggestions_for
    return {**incoming_dict(row),"suggestions":(await suggestions_for(db,[row]))[row.id]}


async def _own_incoming(db, incoming_id, user, *, lock=False):
    if user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    query = select(IncomingFlow).where(IncomingFlow.id == incoming_id)
    if lock: query = query.with_for_update().execution_options(populate_existing=True)
    row = (await db.execute(query)).scalar_one_or_none()
    if row is None: raise HTTPException(404, "到账记录不存在")
    if row.warehouse_id not in get_wh_ids(user): raise HTTPException(403, "只能访问自己仓库的到账及截图")
    return row


@router.post("/{incoming_id}/screenshot", dependencies=[Depends(require_non_labor)])
async def upload_incoming_screenshot(incoming_id: int, file: UploadFile = File(...),
    current_user=Depends(check_staff_permission("到账流水")), db: AsyncSession = Depends(get_db)):
    row = await _own_incoming(db, incoming_id, current_user, lock=True)
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ("png", "jpg", "jpeg", "webp"): raise HTTPException(400, "截图仅支持 png/jpg/jpeg/webp")
    content = await file.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024: raise HTTPException(400, "截图不能超过10MB")
    from app.services.image_utils import is_image, save_image
    if not is_image(content): raise HTTPException(400, "截图不是有效图片，请重新选择")
    directory, name, old = private_directory(), uuid.uuid4().hex, row.screenshot
    try:
        result = save_image(content, str(directory), "", f"{name}.{ext}")
        row.screenshot = result["path"].rsplit("/", 1)[-1]
        await db.commit()
    except Exception:
        await db.rollback()
        for path in directory.glob(f"{name}*"):
            path.unlink(missing_ok=True)
        raise HTTPException(500, "截图保存失败；到账已入账，请仅补传截图")
    if old:
        try:
            old_path = screenshot_path(old)
            old_path.unlink(missing_ok=True)
            old_path.with_name(old_path.stem + "_thumb.jpg").unlink(missing_ok=True)
        except (OSError, HTTPException):
            pass
    return {"id": row.id, "has_screenshot": True, "message": "截图已保存，到账金额未改变"}


@router.get("/{incoming_id}/screenshot", dependencies=[Depends(require_non_labor)])
async def read_incoming_screenshot(incoming_id: int,
    current_user=Depends(check_staff_permission_any("到账流水", "账期管理")), db: AsyncSession = Depends(get_db)):
    row = await _own_incoming(db, incoming_id, current_user)
    path = screenshot_path(row.screenshot)
    if not path.is_file(): raise HTTPException(404, "到账截图不存在")
    return FileResponse(path, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})

@router.post("/batch-import")
async def batch_import(req: IncomingBatchImport, request: Request, current_user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db),
                       _perm=Depends(check_staff_permission("到账流水"))):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    scope = await warehouse_scope(db,current_user,request.headers.get('X-Warehouse-ID'))
    if len(scope) != 1: raise HTTPException(400,'请先选择一个仓库')
    wh_id = scope[0].id
    if not 1 <= len(req.records) <= 500: raise HTTPException(400,"每批必须包含1至500条到账")
    imported, existing = 0, 0
    context_hash = hashlib.sha256(json.dumps(req.records, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    for index, rec in enumerate(req.records):
        if rec.get("warehouse_id", wh_id) != wh_id: raise HTTPException(403, "不能导入其他仓库的到账")
        key = hashlib.sha256(f"batch:{req.request_key}:{index}".encode()).hexdigest()
        try: item = IncomingCreate(**{**rec, "request_key": key})
        except ValidationError: raise HTTPException(400, f"第{index + 1}条到账字段不完整或格式错误")
        _, created = await create_once(db, item, wh_id, current_user, context_hash=context_hash)
        imported += int(created)
        existing += int(not created)
    return {"imported": imported, "existing": existing, "message": f"成功导入{imported}条，已有{existing}条未重复录入"}

@router.post("/import-excel")
async def import_excel(request: Request, file: UploadFile = File(...), mode: str = Form("preview"),
    preview_version: str = Form(None), request_key: str = Form(None),
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("到账流水"))):
    from app.services.excel_import import read_upload
    from app.services.incoming_import import preview
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF): raise HTTPException(403, "无权限")
    scope = await warehouse_scope(db,current_user,request.headers.get('X-Warehouse-ID'))
    if len(scope) != 1: raise HTTPException(400,'请先选择一个仓库')
    content = await read_upload(file)
    if mode not in ('preview','confirm'): raise HTTPException(400,'请先预览，再明确确认')
    if mode == 'confirm':
        from app.services import sku_catalog as catalog
        from app.services.payable_creation import fingerprint
        from app.models import ProductImportOperation
        await catalog.lock(db,scope[0].id)
        key = 'incoming:' + catalog.label(request_key,'请求编号',64)
        signature = fingerprint({'content':hashlib.sha256(content).hexdigest(),'version':preview_version,'operator_id':current_user.id})
        old = (await db.execute(select(ProductImportOperation).where(ProductImportOperation.warehouse_id==scope[0].id,ProductImportOperation.request_key==key))).scalar_one_or_none()
        if old:
            if old.request_fingerprint != signature: raise HTTPException(409,'原请求内容不同，请核对已保存记录')
            return {**old.result,'replayed':True}
    current = await preview(db,scope[0].id,content,current_user)
    if mode == 'preview': return current
    records = [{k:v for k,v in row.items() if k != 'row_number'} for row in current['rows']]
    if not current['valid']: raise HTTPException(422,{'code':'excel_import_not_saved','not_created':True,'request_key':request_key,'message':'校验失败，整批未保存','errors':current['errors'],'preview':current})
    if preview_version != current['preview_version']: raise HTTPException(409,{'code':'excel_import_not_saved','not_created':True,'request_key':request_key,'message':'原请求未保存，预览已变更，请重新核对并确认；沿用原请求编号','preview':current})
    try: batch = IncomingBatchImport(request_key=request_key,records=records)
    except ValidationError: raise HTTPException(400,'缺少有效的原请求编号')
    # Lock all explicitly provided accounts in stable order before any receipt INSERT.
    # Replay above deliberately precedes eligibility checks for already committed requests.
    from app.services.wallet import lock_account
    for account_id, currency in sorted({(r['account_id'],r['currency']) for r in records}):
        await lock_account(db,scope[0].id,account_id,currency)
    result = await batch_import(batch,request,current_user,db,_perm)
    result = {**result,'id':request_key,'mode':'confirmed','errors':[]}
    db.add(ProductImportOperation(warehouse_id=scope[0].id,request_key=key,request_fingerprint=signature,result=result,operator_id=current_user.id))
    await db.flush()
    return result

@router.get("/template")
async def download_template(current_user: User = Depends(get_current_user),
                            _perm=Depends(check_staff_permission("到账流水"))):
    """下载到账流水导入模板"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from fastapi.responses import StreamingResponse
    wb = Workbook(); ws = wb.active; ws.title = "到账流水导入模板"
    hf = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    hfont = Font(bold=True, color="FFFFFF")
    headers = ["到账日期", "金额", "币种", "付款方", "付款方式", "备注", "收款账户编号"]
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=c, value=h); cell.font = hfont; cell.fill = hf
    # Example row
    example = ["2026-07-01", 5000, "THB", "示例客户", "银行转账", "示例备注", "请填写本仓同币种账户编号"]
    ef = Font(italic=True, color="999999")
    for c, v in enumerate(example, 1):
        cell = ws.cell(row=2, column=c, value=v); cell.font = ef
    ws.column_dimensions['A'].width = 14
    ws.column_dimensions['B'].width = 12
    ws.column_dimensions['C'].width = 8
    ws.column_dimensions['D'].width = 20
    ws.column_dimensions['E'].width = 12
    ws.column_dimensions['F'].width = 20
    notes=wb.create_sheet("填写说明")
    notes.append(["仅.xlsx；.xls请另存为.xlsx，不能只改扩展名。最多500行、20列、2MB，不接受公式。删除示例行后填写；到账日期、金额、币种、收款账户编号必填，账户必须是本仓可用同币种账户，请在账户管理核对编号。先预览，再明确确认；错误行整批不保存。结果不明时使用原文件原请求重试，另一笔合法到账请发起新请求。"] )
    notes.column_dimensions["A"].width=110
    import io; output = io.BytesIO(); wb.save(output); output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": "attachment; filename=incoming_template.xlsx"})
