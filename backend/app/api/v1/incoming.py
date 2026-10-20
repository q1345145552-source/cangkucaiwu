from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile
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

router = APIRouter()

@router.get("", dependencies=[Depends(require_non_labor)])
async def list_incoming(
    page: int = 1, page_size: int = 20, month: str = None, status: str = None,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission_any("到账流水", "账期管理")),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(IncomingFlow); count_q = select(func.count(IncomingFlow.id))
    query = query.where(IncomingFlow.warehouse_id.in_(get_wh_ids(current_user)))
    count_q = count_q.where(IncomingFlow.warehouse_id.in_(get_wh_ids(current_user)))
    if month:
        query = query.where(func.to_char(IncomingFlow.received_date, 'YYYY-MM') == month)
        count_q = count_q.where(func.to_char(IncomingFlow.received_date, 'YYYY-MM') == month)
    if status:
        query = query.where(IncomingFlow.match_status == status)
        count_q = count_q.where(IncomingFlow.match_status == status)
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(query.order_by(IncomingFlow.created_at.desc()).offset((page-1)*page_size).limit(page_size))
    records = result.scalars().all()
    user_ids = list(set(r.entrant_id for r in records if r.entrant_id))
    user_map = {}
    if user_ids:
        users = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        user_map = {u.id: u.display_name for u in users}
    return {"data": [incoming_dict(r, user_map.get(r.entrant_id, "")) for r in records],
        "total": total, "page": page, "page_size": page_size}

@router.post("")
async def create_incoming(req: IncomingCreate, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db),
                          _perm=Depends(check_staff_permission("到账流水"))):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "无法确定仓库")
    r, created = await create_once(db, req, wh_id, current_user)
    return {**incoming_dict(r), "created": created, "message": "录入成功" if created else "到账已保存，未重复录入"}


@router.get("/by-request/{request_key}", dependencies=[Depends(require_non_labor)])
async def lookup_incoming(request_key: str, current_user=Depends(check_staff_permission("到账流水")), db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    row = (await db.execute(select(IncomingFlow).where(IncomingFlow.warehouse_id == get_wh_id(current_user),
        IncomingFlow.request_key == request_key))).scalar_one_or_none()
    if row is None: raise HTTPException(404, "尚未找到本次到账")
    return incoming_dict(row)


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
async def batch_import(req: IncomingBatchImport, current_user: User = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db),
                       _perm=Depends(check_staff_permission("到账流水"))):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    wh_id = get_wh_id(current_user)
    if not wh_id: raise HTTPException(400, "请先选择仓库")
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
    import io; output = io.BytesIO(); wb.save(output); output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": "attachment; filename=incoming_template.xlsx"})
