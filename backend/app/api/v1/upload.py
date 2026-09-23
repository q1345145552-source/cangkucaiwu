"""通用文件上传 + 充值截图上传"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import os, uuid
from app.core.timezone import thai_now, thai_today
from datetime import datetime
from app.database import get_db
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids

router = APIRouter()

UPLOAD_DIR = "/app/uploads"

def get_upload_path(user, subdir: str = "") -> str:
    today = thai_now().strftime("%Y-%m-%d")
    wh = user.warehouse_id or 0
    return os.path.join(subdir, str(wh), today)

@router.post("")
async def upload_file(
    file: UploadFile = File(...),
    current_user = Depends(get_current_user),
):
    """通用文件上传，返回文件路径，支持 png/jpg/jpeg/webp/pdf，最大10MB"""
    ext = file.filename.split(".")[-1].lower() if file.filename else ""
    if ext not in ("png", "jpg", "jpeg", "webp", "pdf"):
        raise HTTPException(400, "仅支持 png/jpg/jpeg/webp/pdf 格式")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件大小不能超过10MB")

    # Build path: uploads/warehouse_id/date/uuid.ext（压缩 + 缩略图）
    from app.services.image_utils import save_image
    today = thai_now().strftime("%Y-%m-%d")
    wh_id = str(get_wh_id(current_user) or 0)
    abs_subdir = os.path.join(UPLOAD_DIR, wh_id, today)
    rel_subdir = f"uploads/{wh_id}/{today}"
    fname = f"{uuid.uuid4().hex}.{ext}"
    result = save_image(content, abs_subdir, rel_subdir, fname)
    return {"path": result["path"], "thumb_path": result["thumb_path"], "filename": file.filename, "size": result["size"]}

@router.post("/recharge-screenshot")
async def upload_recharge_screenshot(
    recharge_id: int = Form(...),
    file: UploadFile = File(...),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传充值申报截图并关联到申报记录"""
    from app.models.recharge import RechargeDeclaration
    result = await db.execute(select(RechargeDeclaration).where(RechargeDeclaration.id == recharge_id))
    rec = result.scalar_one_or_none()
    if not rec: raise HTTPException(404, "充值申报不存在")
    if rec.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "只能给自己仓库的申报上传截图")

    ext = file.filename.split(".")[-1].lower() if file.filename else ""
    if ext not in ("png", "jpg", "jpeg", "webp"):
        raise HTTPException(400, "仅支持图片格式 png/jpg/jpeg/webp")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件不能超过10MB")
    from app.services.image_utils import is_image
    if not is_image(content):
        raise HTTPException(400, "文件不是有效的图片，请重新选择")

    from app.services.image_utils import save_image
    today = thai_now().strftime("%Y-%m-%d")
    wh_id = str(rec.warehouse_id)
    abs_subdir = os.path.join(UPLOAD_DIR, wh_id, today, "recharge")
    rel_subdir = f"uploads/{wh_id}/{today}/recharge"
    fname = f"{uuid.uuid4().hex}.{ext}"
    result = save_image(content, abs_subdir, rel_subdir, fname)
    rec.screenshot = result["path"]
    await db.flush()
    return {"path": result["path"], "thumb_path": result["thumb_path"], "message": "截图上传成功"}
