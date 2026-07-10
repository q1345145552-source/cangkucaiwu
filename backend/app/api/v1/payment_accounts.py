from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.customer import PaymentAccount
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role
from app.schemas.business import PaymentAccountCreate

router = APIRouter()

@router.get("")
async def list_accounts(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(PaymentAccount)
    query = query.where(PaymentAccount.warehouse_id.in_(get_wh_ids(current_user)))
    result = await db.execute(query.order_by(PaymentAccount.id))
    accs = result.scalars().all()
    return {"data": [{"id": a.id, "warehouse_id": a.warehouse_id, "account_name": a.account_name,
                      "account_type": a.account_type, "account_number": a.account_number,
                      "opening_balance": a.opening_balance, "bank_name": a.bank_name,
                      "branch_name": a.branch_name, "account_holder": a.account_holder,
                      "currency": a.currency or "THB", "status": a.status or "active",
                      "remark": a.remark} for a in accs]}

@router.post("")
async def create_account(req: PaymentAccountCreate, current_user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "无权限")
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "无法确定仓库")
    a = PaymentAccount(warehouse_id=wh_id, **req.model_dump())
    db.add(a); await db.flush(); return {"id": a.id, "message": "创建成功"}

@router.put("/{account_id}")
async def update_account(account_id: int, req: PaymentAccountCreate,
                         current_user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    result = await db.execute(select(PaymentAccount).where(PaymentAccount.id == account_id))
    a = result.scalar_one_or_none()
    if not a: raise HTTPException(404, "账户不存在")
    if current_user.role != Role.SUPER_ADMIN and a.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "只能修改自己仓库的账户")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    await db.flush(); return {"message": "更新成功"}

@router.put("/{account_id}/toggle-status")
async def toggle_account_status(account_id: int, current_user: User = Depends(get_current_user),
                                db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    result = await db.execute(select(PaymentAccount).where(PaymentAccount.id == account_id))
    a = result.scalar_one_or_none()
    if not a: raise HTTPException(404, "账户不存在")
    a.status = "inactive" if a.status == "active" else "active"
    await db.flush(); return {"message": "状态已切换", "status": a.status}

@router.delete("/{account_id}")
async def delete_account(account_id: int, current_user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    result = await db.execute(select(PaymentAccount).where(PaymentAccount.id == account_id))
    a = result.scalar_one_or_none()
    if not a: raise HTTPException(404, "账户不存在")
    if current_user.role != Role.SUPER_ADMIN and a.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "只能删除自己仓库的账户")
    await db.delete(a); await db.flush(); return {"message": "删除成功"}
