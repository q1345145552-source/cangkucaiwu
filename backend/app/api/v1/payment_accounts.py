from app.core.round2_access import require_account_manager, mutation_scope, own_scope
from app.services.data_history import record_history
from fastapi.encoders import jsonable_encoder
from pydantic import ConfigDict
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.customer import PaymentAccount
from app.models.user import User
from app.core.timezone import thai_today
from app.core.permissions import check_staff_permission, check_staff_permission_any, get_wh_id, get_wh_ids, Role, require_non_labor
from app.schemas.business import PaymentAccountCreate as AccountFields

class PaymentAccountCreate(AccountFields):
    model_config = ConfigDict(extra="forbid")

def audit_fields(account):
    values = {key: getattr(account, key) for key in AccountFields.model_fields}
    for key in ("account_number", "account_holder", "remark"):
        values[key] = "[已隐藏]" if values[key] else None
    return jsonable_encoder(values)


from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.services.account_balances import current_account_balances
from app.core.account_nature import ACCOUNT_NATURES, ACCOUNT_NATURE_LABELS
from app.services.account_nature import owner_wallet_summary
from app.services.warehouse_summary import warehouse_scope
from app.models.cash_advance_repayment import CashAdvanceRepayment
from app.models.payroll import PayrollRecord
from app.models.income_expense import ExpenseRecord
from app.models.reimbursement_payment import ReimbursementPayment
from app.models.expense_fund import ExpenseFundDisbursement
from app.models.employee_advance import EmployeeAdvance

_PERMISSION = MENU_PERMISSIONS_BY_KEY["accounts"].label

router = APIRouter()

from datetime import date
from pydantic import BaseModel
from decimal import Decimal

class TransferRequest(BaseModel):
    from_account_id: int
    to_account_id: int
    amount: Decimal
    transfer_date: date
    request_key: str
    remark: str | None = None


@router.post("/transfers", dependencies=[Depends(require_non_labor), Depends(mutation_scope)])
async def create_transfer(req: TransferRequest, user=Depends(check_staff_permission_any(_PERMISSION, "运营收支")),
                          db: AsyncSession = Depends(get_db)):
    if user.role not in (Role.WAREHOUSE_ADMIN, Role.STAFF): raise HTTPException(403, "无权限")
    from app.models.wallet import AccountTransfer
    from app.services.wallet import positive_money
    from app.services.data_history import record_history
    wid = get_wh_id(user)
    if not wid: raise HTTPException(400, "请先选择仓库")
    value = positive_money(req.amount)
    if not req.request_key.strip() or len(req.request_key) > 64: raise HTTPException(400, "转账请求编号无效")
    def replay(old):
        if (old.warehouse_id, old.from_account_id, old.to_account_id, old.amount, old.transfer_date) != (wid, req.from_account_id, req.to_account_id, value, req.transfer_date):
            raise HTTPException(409, "转账请求已使用，请核对原记录")
        return {"id": old.id, "message": "内部转账已记录，不计收入支出"}
    old = (await db.execute(select(AccountTransfer).where(AccountTransfer.request_key == req.request_key))).scalar_one_or_none()
    if old:return replay(old)
    if req.from_account_id == req.to_account_id: raise HTTPException(400, "转出和转入账户不能相同")
    if req.transfer_date > thai_today(): raise HTTPException(400, "不能登记未来转账")
    accounts = (await db.execute(select(PaymentAccount).where(PaymentAccount.warehouse_id == wid,
        PaymentAccount.id.in_([req.from_account_id, req.to_account_id])).order_by(PaymentAccount.id).with_for_update())).scalars().all()
    if len(accounts) != 2: raise HTTPException(400, "账户不存在或不属于当前仓库")
    source = next(a for a in accounts if a.id == req.from_account_id)
    target = next(a for a in accounts if a.id == req.to_account_id)
    if any(a.status not in (None, "active") for a in accounts): raise HTTPException(400, "账户已停用")
    if (source.currency or "THB") != (target.currency or "THB"): raise HTTPException(400, "内部转账必须使用同币种账户")
    old = (await db.execute(select(AccountTransfer).where(AccountTransfer.request_key == req.request_key))).scalar_one_or_none()
    if old:return replay(old)
    if (await current_account_balances(db, [source]))[source.id] < value: raise HTTPException(400, "转出账户余额不足")
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    insert=sqlite_insert if db.bind.dialect.name=='sqlite' else pg_insert
    rid=(await db.execute(insert(AccountTransfer).values(warehouse_id=wid, from_account_id=source.id, to_account_id=target.id,
        amount=value, currency=source.currency or "THB", transfer_date=req.transfer_date,
        request_key=req.request_key, remark=req.remark, operator_id=user.id).on_conflict_do_nothing(
            index_elements=['request_key']).returning(AccountTransfer.id))).scalar_one_or_none()
    if rid is None:
        return replay((await db.execute(select(AccountTransfer).where(AccountTransfer.request_key==req.request_key))).scalar_one())
    row=await db.get(AccountTransfer,rid)
    await record_history(db, module="accounts", record_id=row.id, operator=user, operation_type="transfer",
        after={"from_account_id": source.id, "to_account_id": target.id, "amount": float(value), "currency": row.currency}, warehouse_id=wid)
    return {"id": row.id, "message": "内部转账已记录，不计收入支出"}


@router.get("", dependencies=[Depends(require_non_labor)])
async def list_accounts(request: Request, current_user: User = Depends(check_staff_permission_any(
        _PERMISSION,
        MENU_PERMISSIONS_BY_KEY["payroll"].label,
        MENU_PERMISSIONS_BY_KEY["payable"].label,
        MENU_PERMISSIONS_BY_KEY["payment_plans"].label,
        MENU_PERMISSIONS_BY_KEY["incoming"].label, MENU_PERMISSIONS_BY_KEY["credit"].label,
        MENU_PERMISSIONS_BY_KEY["expense_approval"].label,
        MENU_PERMISSIONS_BY_KEY["operating"].label,
        MENU_PERMISSIONS_BY_KEY["other_income_expense"].label,
    )), db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    scope = [w.id for w in await warehouse_scope(db, current_user, request.headers.get("X-Warehouse-ID"))]
    query = select(PaymentAccount).where(PaymentAccount.warehouse_id.in_(scope))
    result = await db.execute(query.order_by(PaymentAccount.id))
    accs = result.scalars().all()
    balances = await current_account_balances(db, accs)
    return {"data": [{"id": a.id, "warehouse_id": a.warehouse_id, "account_name": a.account_name,
                      "account_type": a.account_type, "account_number": a.account_number,
                      "account_nature": a.account_nature, "account_nature_label": ACCOUNT_NATURE_LABELS.get(a.account_nature),
                      "belongs_to_owner_wallet": True if a.account_nature in ACCOUNT_NATURE_LABELS else None,
                      "opening_balance": a.opening_balance, "opening_balance_date": a.opening_balance_date.isoformat() if a.opening_balance_date else None, "current_balance": float(balances[a.id]), "bank_name": a.bank_name,
                      "branch_name": a.branch_name, "account_holder": a.account_holder,
                      "currency": a.currency or "THB", "status": a.status or "active",
                      "remark": a.remark} for a in accs],
        "nature_options": ACCOUNT_NATURES, "warehouse_ids": scope,
        "wallet_balances_by_currency": owner_wallet_summary(accs, balances)}

@router.post("", dependencies=[Depends(mutation_scope)])
async def create_account(request: Request, req: PaymentAccountCreate, current_user: User = Depends(check_staff_permission(_PERMISSION)),
                         db: AsyncSession = Depends(get_db)):
    require_account_manager(current_user)
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "无法确定仓库")
    own_scope(current_user, wh_id)
    request.state.audit_warehouse_id = wh_id
    values = req.model_dump()
    if req.account_type=='cash' and not req.account_number.strip():values['account_number']='-'
    values["opening_balance_date"] = req.opening_balance_date or thai_today().replace(day=1)
    a = PaymentAccount(warehouse_id=wh_id, **values)
    db.add(a)
    await db.flush()
    await record_history(db, module="accounts", record_id=a.id, operator=current_user, operation_type="create", after=audit_fields(a), warehouse_id=a.warehouse_id)
    return {"id": a.id, "message": "创建成功"}

@router.put("/{account_id}", dependencies=[Depends(require_non_labor), Depends(mutation_scope)])
async def update_account(request: Request, account_id: int, req: PaymentAccountCreate,
                         current_user: User = Depends(check_staff_permission(_PERMISSION)),
                         db: AsyncSession = Depends(get_db)):
    require_account_manager(current_user)
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    result = await db.execute(select(PaymentAccount).where(PaymentAccount.id == account_id).with_for_update())
    a = result.scalar_one_or_none()
    if not a: raise HTTPException(404, "账户不存在")
    own_scope(current_user, a.warehouse_id)
    request.state.audit_warehouse_id = a.warehouse_id
    before_values = {key: getattr(a, key) for key in AccountFields.model_fields}
    before = audit_fields(a)
    if current_user.role != Role.SUPER_ADMIN and a.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "只能修改自己仓库的账户")
    if req.currency.upper() != (a.currency or "THB").upper():
        from app.services.wallet import flow_query
        flows = flow_query(db, [a.warehouse_id])
        if (await db.execute(select(flows.c.id).where(flows.c.account_id == a.id).limit(1))).first():
            raise HTTPException(400, "该账户已有资金记录，不能修改币种")
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
    if req.opening_balance_date is None:
        req.opening_balance_date = a.opening_balance_date or thai_today().replace(day=1)
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(a, k, v)
    after = audit_fields(a)
    changed = {key for key in req.model_fields_set if before_values[key] != getattr(a, key)}
    await record_history(db, module="accounts", record_id=a.id, operator=current_user, operation_type="edit", before={k: before[k] for k in changed}, after={k: after[k] for k in changed}, warehouse_id=a.warehouse_id)
    await db.flush(); return {"message": "更新成功"}

@router.put("/{account_id}/toggle-status", dependencies=[Depends(require_non_labor), Depends(mutation_scope)])
async def toggle_account_status(request: Request, account_id: int, current_user: User = Depends(check_staff_permission(_PERMISSION)),
                                db: AsyncSession = Depends(get_db)):
    require_account_manager(current_user)
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    result = await db.execute(select(PaymentAccount).where(PaymentAccount.id == account_id).with_for_update())
    a = result.scalar_one_or_none()
    if not a: raise HTTPException(404, "账户不存在")
    own_scope(current_user, a.warehouse_id)
    request.state.audit_warehouse_id = a.warehouse_id
    before = audit_fields(a)
    if current_user.role != Role.SUPER_ADMIN and a.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "只能操作自己仓库的账户")
    a.status = "inactive" if a.status == "active" else "active"
    await record_history(db, module="accounts", record_id=a.id, operator=current_user, operation_type="edit", before={"status": before["status"]}, after={"status": a.status}, warehouse_id=a.warehouse_id)
    await db.flush(); return {"message": "状态已切换", "status": a.status}

@router.delete("/{account_id}", dependencies=[Depends(mutation_scope)])
async def delete_account(request: Request, account_id: int, current_user: User = Depends(check_staff_permission(_PERMISSION)),
                         db: AsyncSession = Depends(get_db)):
    require_account_manager(current_user)
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    result = await db.execute(select(PaymentAccount).where(PaymentAccount.id == account_id).with_for_update())
    a = result.scalar_one_or_none()
    if not a: raise HTTPException(404, "账户不存在")
    own_scope(current_user, a.warehouse_id)
    request.state.audit_warehouse_id = a.warehouse_id
    before = audit_fields(a)
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
    from app.services.wallet import flow_query
    flows = flow_query(db, [a.warehouse_id])
    if (await db.execute(select(flows.c.id).where(flows.c.account_id == a.id).limit(1))).first():
        raise HTTPException(400, "该账户已有资金记录，不能删除，请停用")
    await record_history(db, module="accounts", record_id=a.id, operator=current_user, operation_type="delete", before=before, warehouse_id=a.warehouse_id)
    await db.delete(a); await db.flush(); return {"message": "删除成功"}
