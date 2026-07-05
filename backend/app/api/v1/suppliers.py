from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.supplier import Supplier
from app.models.user import User
from app.core.permissions import get_current_user, Role
from app.schemas.business import SupplierCreate, SupplierUpdate, SupplierResponse

router = APIRouter()

@router.get("")
async def list_suppliers(page: int = 1, page_size: int = 20, search: str = None,
                         current_user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(Supplier); count_q = select(func.count(Supplier.id))
    if search:
        query = query.where(Supplier.name.ilike(f"%{search}%")); count_q = count_q.where(Supplier.name.ilike(f"%{search}%"))
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(query.order_by(Supplier.created_at.desc()).offset((page-1)*page_size).limit(page_size))
    suppliers = result.scalars().all()
    return {"data": [{"id": s.id, "name": s.name, "contact_person": s.contact_person, "contact_info": s.contact_info,
                      "address": s.address, "payment_terms": s.payment_terms, "ai_evaluation": s.ai_evaluation,
                      "is_active": s.is_active} for s in suppliers],
            "total": total, "page": page, "page_size": page_size}

@router.post("")
async def create_supplier(req: SupplierCreate, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    s = Supplier(warehouse_id=current_user.warehouse_id, **req.model_dump())
    db.add(s); await db.flush(); return {"id": s.id, "message": "创建成功"}

@router.put("/{supplier_id}")
async def update_supplier(supplier_id: int, req: SupplierUpdate,
                          current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    s = result.scalar_one_or_none()
    if not s: raise HTTPException(404, "供应商不存在")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    await db.flush(); return {"message": "更新成功"}

@router.get("/{supplier_id}")
async def get_supplier(supplier_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    s = result.scalar_one_or_none()
    if not s: raise HTTPException(404, "供应商不存在")
    return {"id": s.id, "name": s.name, "contact_person": s.contact_person, "contact_info": s.contact_info,
            "address": s.address, "payment_terms": s.payment_terms, "ai_evaluation": s.ai_evaluation}

@router.get("/{supplier_id}/ai-evaluation")
async def ai_evaluate(supplier_id: int, current_user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role != Role.SUPER_ADMIN:
        raise HTTPException(403, "仅超级管理员可用")
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    s = result.scalar_one_or_none()
    if not s: raise HTTPException(404, "供应商不存在")
    # Try DeepSeek API if key configured
    from app.config import get_settings
    settings = get_settings()
    if settings.DEEPSEEK_API_KEY:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=settings.DEEPSEEK_API_KEY, base_url=settings.DEEPSEEK_BASE_URL)
            resp = client.chat.completions.create(model="deepseek-chat", messages=[{"role":"user",
                "content":f"评估供应商：{s.name}，联系方式：{s.contact_info or '无'}，地址：{s.address or '无'}。请从信誉、价格竞争力、交付及时性三个维度简要评估。"}])
            evaluation = {"result": resp.choices[0].message.content}
            s.ai_evaluation = evaluation
        except Exception as e:
            evaluation = {"error": str(e)}
    else:
        evaluation = {"result": "DeepSeek API Key 未配置，无法执行AI评估"}
    if not s.ai_evaluation:
        s.ai_evaluation = evaluation
    await db.flush()
    return evaluation
