from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.supplier import Supplier, SupplierCategory, SupplierProduct
from app.models.user import User
from app.core.permissions import get_current_user, Role
from app.schemas.business import SupplierCreate, SupplierUpdate, SupplierResponse, SupplierProductCreate

router = APIRouter()

# ─── Category CRUD ────────────────────────────────
@router.get("/categories")
async def list_categories(current_user = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    cats = (await db.execute(select(SupplierCategory).where(SupplierCategory.is_active == "true").order_by(SupplierCategory.sort_order))).scalars().all()
    return {"data": [{"id": c.id, "name": c.name} for c in cats]}

@router.post("/categories")
async def create_category(name: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "无权限")
    c = SupplierCategory(name=name)
    db.add(c); await db.flush()
    return {"id": c.id, "name": c.name, "message": "创建成功"}

# ─── Product CRUD ─────────────────────────────────
@router.get("/{supplier_id}/products")
async def list_products(supplier_id: int, current_user = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    prods = (await db.execute(select(SupplierProduct).where(SupplierProduct.supplier_id == supplier_id).order_by(SupplierProduct.created_at.desc()))).scalars().all()
    return {"data": [{"id": p.id, "product_name": p.product_name, "spec": p.spec, "unit_price": p.unit_price, "unit": p.unit, "remark": p.remark} for p in prods]}

@router.post("/{supplier_id}/products")
async def add_product(supplier_id: int, req: SupplierProductCreate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "无权限")
    p = SupplierProduct(supplier_id=supplier_id, **req.model_dump())
    db.add(p); await db.flush()
    return {"id": p.id, "message": "添加成功"}

@router.delete("/{supplier_id}/products/{product_id}")
async def delete_product(supplier_id: int, product_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "无权限")
    p = (await db.execute(select(SupplierProduct).where(SupplierProduct.id == product_id, SupplierProduct.supplier_id == supplier_id))).scalar_one_or_none()
    if not p: raise HTTPException(404, "产品不存在")
    await db.delete(p); await db.flush()
    return {"message": "删除成功"}

# ─── Price Comparison ─────────────────────────────
@router.get("/compare-prices")
async def compare_prices(product_name: str = None, spec: str = None, category_id: int = None,
                          current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """按产品名称/规格对比同类别供应商报价"""
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.STAFF):
        raise HTTPException(403, "无权限")
    q = select(SupplierProduct).join(Supplier, SupplierProduct.supplier_id == Supplier.id).where(Supplier.is_active == "true")
    if product_name:
        q = q.where(SupplierProduct.product_name.ilike(f"%{product_name}%"))
    if spec:
        q = q.where(SupplierProduct.spec.ilike(f"%{spec}%"))
    if category_id:
        q = q.where(Supplier.category_id == category_id)
    if current_user.role != Role.SUPER_ADMIN:
        q = q.where(Supplier.warehouse_id == current_user.warehouse_id)
    prods = (await db.execute(q.order_by(SupplierProduct.unit_price.asc()))).scalars().all()
    sids = list({p.supplier_id for p in prods})
    smap = {}
    if sids:
        sups = (await db.execute(select(Supplier).where(Supplier.id.in_(sids)))).scalars().all()
        smap = {s.id: s for s in sups}
    result = []
    for p in prods:
        s = smap.get(p.supplier_id)
        cat_name = ""
        if s and s.category_id:
            cat = (await db.execute(select(SupplierCategory).where(SupplierCategory.id == s.category_id))).scalar_one_or_none()
            if cat: cat_name = cat.name
        result.append({
            "product_id": p.id,
            "supplier_id": p.supplier_id,
            "supplier_name": s.name if s else "",
            "category_name": cat_name,
            "product_name": p.product_name,
            "spec": p.spec,
            "unit_price": p.unit_price,
            "unit": p.unit,
            "remark": p.remark,
        })
    return {"data": result, "total": len(result)}

# ─── AI Price Analysis ────────────────────────────
@router.post("/ai-compare")
async def ai_compare(data: dict, current_user: User = Depends(get_current_user)):
    """data = {"product_name": "...", "spec": "...", "category_id": 1}"""
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "无权限")
    from app.config import get_settings
    settings = get_settings()
    if not settings.DEEPSEEK_API_KEY:
        return {"result": "DeepSeek API Key 未配置，无法执行AI比价分析"}
    # Build comparison data
    compare_data = data.get("compare_data", [])
    if not compare_data:
        return {"result": "无比价数据，请先执行比价查询"}
    rows_text = "\n".join([f"- {r['supplier_name']}: {r['product_name']} {r['spec'] or ''} 单价{r['unit_price']}{r.get('unit','个')}" for r in compare_data])
    prompt = f"""请对以下供应商报价进行比价分析：
{rows_text}

请从以下维度分析：
1. 价格排名：从低到高列出各供应商
2. 性价比评估：综合考虑价格和已知信息
3. 推荐结论：建议选择哪家供应商及理由"""

    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.DEEPSEEK_API_KEY, base_url=settings.DEEPSEEK_BASE_URL)
        resp = client.chat.completions.create(model="deepseek-chat", messages=[{"role":"user","content": prompt}])
        return {"result": resp.choices[0].message.content}
    except Exception as e:
        return {"result": f"AI分析失败: {str(e)}"}

# ─── Supplier CRUD ────────────────────────────────
@router.get("")
async def list_suppliers(page: int = 1, page_size: int = 20, search: str = None,
                         category_id: int = None,
                         current_user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(Supplier); count_q = select(func.count(Supplier.id))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(Supplier.warehouse_id == current_user.warehouse_id)
        count_q = count_q.where(Supplier.warehouse_id == current_user.warehouse_id)
    if search:
        query = query.where(Supplier.name.ilike(f"%{search}%")); count_q = count_q.where(Supplier.name.ilike(f"%{search}%"))
    if category_id:
        query = query.where(Supplier.category_id == category_id)
        count_q = count_q.where(Supplier.category_id == category_id)
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(query.order_by(Supplier.created_at.desc()).offset((page-1)*page_size).limit(page_size))
    suppliers = result.scalars().all()
    # resolve category names
    cat_ids = {s.category_id for s in suppliers if s.category_id}
    cat_map = {}
    if cat_ids:
        cats = (await db.execute(select(SupplierCategory).where(SupplierCategory.id.in_(cat_ids)))).scalars().all()
        cat_map = {c.id: c.name for c in cats}
    return {"data": [{"id": s.id, "name": s.name, "contact_person": s.contact_person, "contact_info": s.contact_info,
                      "address": s.address, "payment_terms": s.payment_terms,
                      "cooperation_content": s.cooperation_content,
                      "settlement_cycle": s.settlement_cycle,
                      "history_notes": s.history_notes,
                      "ai_evaluation": s.ai_evaluation,
                      "category_id": s.category_id,
                      "category_name": cat_map.get(s.category_id, ""),
                      "is_active": s.is_active} for s in suppliers],
            "total": total, "page": page, "page_size": page_size}

@router.post("")
async def create_supplier(req: SupplierCreate, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    d = req.model_dump()
    s = Supplier(warehouse_id=current_user.warehouse_id, **d)
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
    if current_user.role != Role.SUPER_ADMIN and s.warehouse_id != current_user.warehouse_id:
        raise HTTPException(403, "只能修改自己仓库的供应商")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    await db.flush(); return {"message": "更新成功"}

@router.get("/procurement-summary")
async def procurement_summary(current_user: User = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    from app.models.payable import PayableBill
    from app.models.warehouse import Warehouse
    sq = select(Supplier)
    if current_user.role != Role.SUPER_ADMIN:
        sq = sq.where(Supplier.warehouse_id == current_user.warehouse_id)
    suppliers = (await db.execute(sq)).scalars().all()
    result = []
    for s in suppliers:
        bq = (
            select(PayableBill.warehouse_id, func.sum(PayableBill.amount).label("total"))
            .where(PayableBill.supplier_id == s.id)
            .group_by(PayableBill.warehouse_id)
        )
        if current_user.role != Role.SUPER_ADMIN:
            bq = bq.where(PayableBill.warehouse_id == current_user.warehouse_id)
        bill_rows = (await db.execute(bq)).all()
        wids = [r.warehouse_id for r in bill_rows]
        wh_map = {}
        if wids:
            whs = (await db.execute(select(Warehouse).where(Warehouse.id.in_(wids)))).scalars().all()
            wh_map = {w.id: w.name for w in whs}
        warehouses = [{"warehouse_id": r.warehouse_id, "warehouse_name": wh_map.get(r.warehouse_id, ""), "total_amount": float(r.total or 0)} for r in bill_rows]
        if warehouses:
            result.append({
                "supplier_id": s.id, "supplier_name": s.name,
                "warehouses": warehouses,
                "grand_total": sum(w["total_amount"] for w in warehouses),
            })
    return {"data": result}

@router.get("/{supplier_id}")
async def get_supplier(supplier_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    s = result.scalar_one_or_none()
    if not s: raise HTTPException(404, "供应商不存在")
    if current_user.role != Role.SUPER_ADMIN and s.warehouse_id != current_user.warehouse_id:
        raise HTTPException(403, "只能查看自己仓库的供应商")
    cat_name = ""
    if s.category_id:
        cat = (await db.execute(select(SupplierCategory).where(SupplierCategory.id == s.category_id))).scalar_one_or_none()
        if cat: cat_name = cat.name
    return {"id": s.id, "name": s.name, "contact_person": s.contact_person, "contact_info": s.contact_info,
            "address": s.address, "payment_terms": s.payment_terms,
            "cooperation_content": s.cooperation_content,
            "settlement_cycle": s.settlement_cycle,
            "history_notes": s.history_notes,
            "ai_evaluation": s.ai_evaluation,
            "category_id": s.category_id, "category_name": cat_name}

@router.get("/{supplier_id}/ai-evaluation")
async def ai_evaluate(supplier_id: int, current_user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    if current_user.role != Role.SUPER_ADMIN:
        raise HTTPException(403, "仅超级管理员可用")
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    s = result.scalar_one_or_none()
    if not s: raise HTTPException(404, "供应商不存在")
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
