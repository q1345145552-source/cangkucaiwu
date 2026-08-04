"""通用文件上传 + 充值截图上传"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import os, uuid
from app.core.timezone import thai_now, thai_today
from datetime import datetime
from app.database import get_db
from app.core.permissions import get_current_user, get_wh_id

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
    """通用文件上传，返回文件路径，支持 png/jpg/pdf，最大10MB"""
    ext = file.filename.split(".")[-1].lower() if file.filename else ""
    if ext not in ("png", "jpg", "jpeg", "pdf"):
        raise HTTPException(400, "仅支持 png/jpg/pdf 格式")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件大小不能超过10MB")

    # Build path: uploads/warehouse_id/date/uuid.ext
    today = thai_now().strftime("%Y-%m-%d")
    wh_id = str(get_wh_id(current_user) or 0)
    subdir = os.path.join(UPLOAD_DIR, wh_id, today)
    os.makedirs(subdir, exist_ok=True)
    fname = f"{uuid.uuid4().hex}.{ext}"
    fpath = os.path.join(subdir, fname)
    with open(fpath, "wb") as f:
        f.write(content)
    rel_path = f"uploads/{wh_id}/{today}/{fname}"
    return {"path": rel_path, "filename": file.filename, "size": len(content)}

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

    ext = file.filename.split(".")[-1].lower() if file.filename else ""
    if ext not in ("png", "jpg", "jpeg"):
        raise HTTPException(400, "仅支持图片格式")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(400, "文件不能超过10MB")

    today = thai_now().strftime("%Y-%m-%d")
    wh_id = str(rec.warehouse_id)
    subdir = os.path.join(UPLOAD_DIR, wh_id, today, "recharge")
    os.makedirs(subdir, exist_ok=True)
    fname = f"{uuid.uuid4().hex}.{ext}"
    fpath = os.path.join(subdir, fname)
    with open(fpath, "wb") as f:
        f.write(content)
    rel_path = f"uploads/{wh_id}/{today}/recharge/{fname}"
    rec.screenshot = rel_path
    await db.flush()
    return {"path": rel_path, "message": "截图上传成功"}
