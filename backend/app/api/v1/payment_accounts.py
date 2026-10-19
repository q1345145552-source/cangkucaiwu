from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.customer import PaymentAccount
from app.models.user import User
from app.core.permissions import check_staff_permission, check_staff_permission_any, get_wh_id, get_wh_ids, Role, require_non_labor
from app.schemas.business import PaymentAccountCreate

from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.services.account_balances import current_account_balances
from app.models.cash_advance_repayment import CashAdvanceRepayment
from app.models.payroll import PayrollRecord
from app.models.income_expense import ExpenseRecord
from app.models.reimbursement_payment import ReimbursementPayment
from app.models.expense_fund import ExpenseFundDisbursement
from app.models.employee_advance import EmployeeAdvance

_PERMISSION = MENU_PERMISSIONS_BY_KEY["accounts"].label

router = APIRouter()

@router.get("")
async def list_accounts(current_user: User = Depends(check_staff_permission_any(
        _PERMISSION,
        MENU_PERMISSIONS_BY_KEY["payroll"].label,
        MENU_PERMISSIONS_BY_KEY["operating"].label,
        MENU_PERMISSIONS_BY_KEY["other_income_expense"].label,
    )), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(PaymentAccount)
    query = query.where(PaymentAccount.warehouse_id.in_(get_wh_ids(current_user)))
    result = await db.execute(query.order_by(PaymentAccount.id))
    accs = result.scalars().all()
    balances = await current_account_balances(db, accs)
    return {"data": [{"id": a.id, "warehouse_id": a.warehouse_id, "account_name": a.account_name,
                      "account_type": a.account_type, "account_number": a.account_number,
                      "opening_balance": a.opening_balance, "current_balance": float(balances[a.id]), "bank_name": a.bank_name,
                      "branch_name": a.branch_name, "account_holder": a.account_holder,
                      "currency": a.currency or "THB", "status": a.status or "active",
                      "remark": a.remark} for a in accs]}

@router.post("")
async def create_account(req: PaymentAccountCreate, current_user: User = Depends(check_staff_permission(_PERMISSION)),
                         db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "无法确定仓库")
    a = PaymentAccount(warehouse_id=wh_id, **req.model_dump())
    db.add(a); await db.flush(); return {"id": a.id, "message": "创建成功"}

@router.put("/{account_id}", dependencies=[Depends(require_non_labor)])
async def update_account(account_id: int, req: PaymentAccountCreate,
                         current_user: User = Depends(check_staff_permission(_PERMISSION)),
                         db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    result = await db.execute(select(PaymentAccount).where(PaymentAccount.id == account_id).with_for_update())
    a = result.scalar_one_or_none()
    if not a: raise HTTPException(404, "账户不存在")
    if current_user.role != Role.SUPER_ADMIN and a.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "只能修改自己仓库的账户")
    if req.currency.upper() != (a.currency or "THB").upper():
        if (await db.execute(select(EmployeeAdvance.id).where(
            EmployeeAdvance.payment_account_id == a.id,
        ).limit(1))).first():
            raise HTTPException(400, "该账户有关联员工预支记录，不能修改币种")
        active_repayment = (await db.execute(select(CashAdvanceRepayment.id).where(
            CashAdvanceRepayment.account_id == a.id, CashAdvanceRepayment.status == "active",
        ).limit(1))).first()
        if active_repayment:
            raise HTTPException(400, "该账户有有效垫款归还记录，不能修改币种")
        paid_payroll = (await db.execute(select(PayrollRecord.id).join(
            ExpenseRecord, PayrollRecord.expense_record_id == ExpenseRecord.id,
        ).where(ExpenseRecord.account_id == a.id, PayrollRecord.disbursed.is_(True),
            PayrollRecord.cash_advance_id.is_(None), PayrollRecord.voided.is_not(True),
        ).limit(1))).first()
        if paid_payroll:
            raise HTTPException(400, "该账户有已发放工资，不能修改币种")
        if (await db.execute(select(ReimbursementPayment.id).where(
            ReimbursementPayment.payment_account_id == a.id, ReimbursementPayment.status == "active",
        ).limit(1))).first():
            raise HTTPException(400, "该账户有有效报销付款记录，不能修改币种")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    await db.flush(); return {"message": "更新成功"}

@router.put("/{account_id}/toggle-status", dependencies=[Depends(require_non_labor)])
async def toggle_account_status(account_id: int, current_user: User = Depends(check_staff_permission(_PERMISSION)),
                                db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    result = await db.execute(select(PaymentAccount).where(PaymentAccount.id == account_id))
    a = result.scalar_one_or_none()
    if not a: raise HTTPException(404, "账户不存在")
    if current_user.role != Role.SUPER_ADMIN and a.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "只能操作自己仓库的账户")
    a.status = "inactive" if a.status == "active" else "active"
    await db.flush(); return {"message": "状态已切换", "status": a.status}

@router.delete("/{account_id}")
async def delete_account(account_id: int, current_user: User = Depends(check_staff_permission(_PERMISSION)),
                         db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    result = await db.execute(select(PaymentAccount).where(PaymentAccount.id == account_id))
    a = result.scalar_one_or_none()
    if not a: raise HTTPException(404, "账户不存在")
    if current_user.role != Role.SUPER_ADMIN and a.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "只能删除自己仓库的账户")
    if (await db.execute(select(EmployeeAdvance.id).where(EmployeeAdvance.payment_account_id == a.id).limit(1))).first():
        raise HTTPException(400, "该账户有关联员工预支记录，不能删除，请停用")
    if (await db.execute(select(CashAdvanceRepayment.id).where(CashAdvanceRepayment.account_id == a.id).limit(1))).first():
        raise HTTPException(400, "该账户有关联的垫款归还记录，不能删除，请停用")
    if (await db.execute(select(ReimbursementPayment.id).where(ReimbursementPayment.payment_account_id == a.id).limit(1))).first():
        raise HTTPException(400, "该账户有关联报销付款记录，不能删除，请停用")
    if (await db.execute(select(ExpenseFundDisbursement.id).where(ExpenseFundDisbursement.payment_account_id == a.id).limit(1))).first():
        raise HTTPException(400, "该账户有关联备用金拨付记录，不能删除，请停用")
    await db.delete(a); await db.flush(); return {"message": "删除成功"}
