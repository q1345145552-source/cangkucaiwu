from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.customer import PaymentAccount
from app.models.user import User
from app.core.permissions import get_current_user, Role
from app.schemas.business import PaymentAccountCreate

router = APIRouter()

@router.get("")
async def list_accounts(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(PaymentAccount)
    query = query.where(PaymentAccount.warehouse_id == current_user.warehouse_id)
    result = await db.execute(query.order_by(PaymentAccount.id))
    accs = result.scalars().all()
    return {"data": [{"id": a.id, "warehouse_id": a.warehouse_id, "account_name": a.account_name,
                      "account_type": a.account_type, "account_number": a.account_number,
                      "opening_balance": a.opening_balance} for a in accs]}

@router.post("")
async def create_account(req: PaymentAccountCreate, current_user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN,):
        raise HTTPException(403, "无权限")
    wh_id = current_user.warehouse_id
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
    a.account_name = req.account_name; a.account_type = req.account_type
    a.account_number = req.account_number; a.opening_balance = req.opening_balance
    await db.flush(); return {"message": "更新成功"}
