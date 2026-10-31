from app.core.round5_access import own_read_ids
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from datetime import datetime
from app.database import get_db
from app.models.recharge import ReconciliationResult, ReconciliationDeclaration, RechargeDeclaration, CurrencyEnum, MatchStatus
from app.models.customer import Customer
from app.models.warehouse import Warehouse
from app.models.user import User
from app.core.permissions import check_staff_permission, get_wh_id, get_wh_ids, Role, require_non_labor
from app.schemas.business import RechargeCreate
from app.services.data_history import record_history
from app.core.timezone import thai_now

from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY

_PERMISSION = MENU_PERMISSIONS_BY_KEY["recharge"].label

router = APIRouter()


class RechargeVoid(BaseModel):
    reason: str = Field(..., max_length=500)


def _void_info(record):
    return {"is_voided": record.is_voided,
            "voided_at": record.voided_at.isoformat() if record.voided_at else None,
            "voided_by": record.voided_by, "void_reason": record.void_reason}

def _manual_time(value: str) -> datetime:
    from app.core.timezone import thai_now, THAI_TZ
    import re
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2})?)?", value or ""):
        raise HTTPException(400, "请填写完整日期和时间，不能只填时分")
    try:
        when = datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(400, "日期或时间格式不正确")
    if when.tzinfo is not None:
        when = when.astimezone(THAI_TZ).replace(tzinfo=None)
    if when < datetime(2020, 1, 1):
        raise HTTPException(400, "时间不能早于2020年")
    if when.replace(second=0, microsecond=0) > thai_now().replace(tzinfo=None, second=0, microsecond=0):
        raise HTTPException(400, "不能选择未来时间，最多到当前这一分钟")
    return when


def _time_info(value):
    has_time = bool(value and (value.hour or value.minute or value.second or value.microsecond))
    return {"has_time": has_time, "time_note": "" if has_time else "未记录时间"}



async def _check_customer_warehouse(db: AsyncSession, customer_id: int, warehouse_id: int):
    customer_wh = (await db.execute(
        select(Customer.warehouse_id).where(Customer.id == customer_id)
    )).scalar_one_or_none()
    if customer_wh is None:
        raise HTTPException(400, "客户不存在")
    if customer_wh != warehouse_id:
        raise HTTPException(403, "只能使用申报所属仓库的客户")


@router.get("")
async def list_recharges(
    page: int = 1, page_size: int = 20, month: str = None,
    customer_id: int = None, status: str = None, search: str = None,
    current_user: User = Depends(check_staff_permission(_PERMISSION)),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(RechargeDeclaration); count_q = select(func.count(RechargeDeclaration.id))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(RechargeDeclaration.warehouse_id.in_(get_wh_ids(current_user)))
        count_q = count_q.where(RechargeDeclaration.warehouse_id.in_(get_wh_ids(current_user)))
    if current_user.role == Role.SUPERVISOR:
        own_filter = RechargeDeclaration.declarer_id.in_(await own_read_ids(db,current_user))
        query = query.where(own_filter)
        count_q = count_q.where(own_filter)
    if month:
        query = query.where(func.to_char(RechargeDeclaration.declare_date, 'YYYY-MM') == month)
        count_q = count_q.where(func.to_char(RechargeDeclaration.declare_date, 'YYYY-MM') == month)
    if customer_id:
        query = query.where(RechargeDeclaration.customer_id == customer_id)
        count_q = count_q.where(RechargeDeclaration.customer_id == customer_id)
    void_filter = RechargeDeclaration.is_voided.is_(True) if status == "voided" else RechargeDeclaration.is_voided.is_(False)
    query = query.where(void_filter)
    count_q = count_q.where(void_filter)
    if status and status != "voided":
        query = query.where(RechargeDeclaration.match_status == status)
        count_q = count_q.where(RechargeDeclaration.match_status == status)
    if search and search.strip():
        term = search.strip()
        matching_customers = select(Customer.id).where(Customer.company_name.icontains(term, autoescape=True))
        condition = or_(RechargeDeclaration.customer_id.in_(matching_customers),
                        RechargeDeclaration.transaction_no.icontains(term, autoescape=True),
                        RechargeDeclaration.remark.icontains(term, autoescape=True))
        query = query.where(condition)
        count_q = count_q.where(condition)
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(query.order_by(RechargeDeclaration.created_at.desc()).offset((page-1)*page_size).limit(page_size))
    records = result.scalars().all()

    customer_ids = list(set(r.customer_id for r in records if r.customer_id))
    cust_map = {}
    if customer_ids:
        custs = (await db.execute(select(Customer).where(Customer.id.in_(customer_ids)))).scalars().all()
        cust_map = {c.id: c.company_name for c in custs}

    user_ids = list(set(r.declarer_id for r in records if r.declarer_id))
    user_map = {}
    if user_ids:
        users = (await db.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        user_map = {u.id: u.display_name for u in users}

    return {"data": [{
        "id": r.id, "warehouse_id": r.warehouse_id, "customer_id": r.customer_id,
        "customer_name": cust_map.get(r.customer_id, ""),
        "declare_date": r.declare_date.isoformat() if r.declare_date else None,
        **_time_info(r.declare_date),
        "amount": r.amount, "currency": r.currency or "THB",
        "payment_method": r.payment_method, "payment_time": r.payment_time.isoformat() if r.payment_time else None,
        "transaction_no": r.transaction_no, "account_tail": r.account_tail,
        "screenshot": r.screenshot, "remark": r.remark,
        "match_status": r.match_status or "unmatched",
        **_void_info(r),
        "declarer_name": user_map.get(r.declarer_id, ""),
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in records], "total": total, "page": page, "page_size": page_size}

@router.post("", dependencies=[Depends(require_non_labor)])
async def create_recharge(req: RechargeCreate, current_user: User = Depends(check_staff_permission(_PERMISSION)),
                          db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    wh_id = get_wh_id(current_user)
    if current_user.role == Role.SUPER_ADMIN:
        cust = (await db.execute(select(Customer).where(Customer.id == req.customer_id))).scalar_one_or_none()
        if not cust: raise HTTPException(400, "客户不存在")
        wh_id = cust.warehouse_id
    if not wh_id: raise HTTPException(400, "无法确定仓库")
    await _check_customer_warehouse(db, req.customer_id, wh_id)

    r = RechargeDeclaration(
        warehouse_id=wh_id, customer_id=req.customer_id,
        declare_date=_manual_time(req.declare_date),
        amount=req.amount, currency=req.currency,
        payment_method=req.payment_method,
        payment_time=datetime.fromisoformat(req.payment_time) if req.payment_time else None,
        transaction_no=req.transaction_no, account_tail=req.account_tail,
        screenshot=req.screenshot, remark=req.remark,
        declarer_id=current_user.id,
    )
    db.add(r); await db.flush()
    await record_history(db, module="recharge", record_id=r.id, operator=current_user,
                          operation_type="create", after={
                              "amount": req.amount, "currency": req.currency,
                              "declare_date": req.declare_date, "customer_id": req.customer_id,
                              "payment_method": req.payment_method, "remark": req.remark,
                          }, warehouse_id=wh_id)
    return {"id": r.id, "message": "申报成功", "declare_date": r.declare_date.isoformat(), **_time_info(r.declare_date)}


@router.get("/{recharge_id}")
async def get_recharge(recharge_id: int, current_user: User = Depends(check_staff_permission(_PERMISSION)), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RechargeDeclaration).where(RechargeDeclaration.id == recharge_id))
    r = result.scalar_one_or_none()
    if not r: raise HTTPException(404, "不存在")
    if current_user.role != Role.SUPER_ADMIN and r.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "无权查看其他仓库的充值申报")
    if current_user.role == Role.SUPERVISOR and r.declarer_id not in await own_read_ids(db,current_user):
        raise HTTPException(403, '只能查看本人充值申报')
    return {"id": r.id, "amount": r.amount, "currency": r.currency, "declare_date": str(r.declare_date), **_time_info(r.declare_date), "match_status": r.match_status, "remark": r.remark, **_void_info(r)}

@router.put("/{recharge_id}")
async def edit_recharge(recharge_id: int, req: RechargeCreate,
                        current_user: User = Depends(check_staff_permission(_PERMISSION)),
                        db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    result = await db.execute(select(RechargeDeclaration).where(RechargeDeclaration.id == recharge_id).with_for_update().execution_options(populate_existing=True))
    r = result.scalar_one_or_none()
    if not r: raise HTTPException(404, "不存在")
    if r.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "只能操作自己仓库的数据")
    if r.is_voided:
        raise HTTPException(400, "该申报已作废，不能修改")
    if req.customer_id:
        await _check_customer_warehouse(db, req.customer_id, r.warehouse_id)
    linked = (await db.execute(select(ReconciliationDeclaration.id).where(ReconciliationDeclaration.declaration_id==r.id, ReconciliationDeclaration.is_active.is_(True)).limit(1))).first()
    if linked and (req.customer_id!=r.customer_id or req.currency!=r.currency or req.amount!=r.amount):
        raise HTTPException(400,'已关联到账的申报不能修改客户、币种或金额，请先核对')
    before = {
        "amount": r.amount, "currency": r.currency,
        "declare_date": r.declare_date.isoformat() if r.declare_date else None,
        "remark": r.remark, "payment_method": r.payment_method, "customer_id": r.customer_id,
    }
    declare_date = _manual_time(req.declare_date)
    r.amount = req.amount; r.currency = req.currency
    r.declare_date = declare_date
    r.remark = req.remark; r.payment_method = req.payment_method
    if req.customer_id:
        r.customer_id = req.customer_id
    await db.flush()
    await record_history(db, module="recharge", record_id=r.id, operator=current_user,
                          operation_type="edit", before=before, after={
                              "amount": req.amount, "currency": req.currency,
                              "declare_date": req.declare_date, "remark": req.remark,
                              "payment_method": req.payment_method, "customer_id": r.customer_id,
                          }, warehouse_id=r.warehouse_id)
    return {"message": "更新成功", "declare_date": r.declare_date.isoformat(), **_time_info(r.declare_date)}

@router.delete("/{recharge_id}")
async def delete_recharge(recharge_id: int,
                          req: RechargeVoid | None = Body(None),
                          current_user: User = Depends(check_staff_permission(_PERMISSION)),
                          db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    result = await db.execute(select(RechargeDeclaration).where(RechargeDeclaration.id == recharge_id).with_for_update().execution_options(populate_existing=True))
    r = result.scalar_one_or_none()
    if not r: raise HTTPException(404, "不存在")
    if r.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "只能操作自己仓库的数据")
    if r.is_voided:
        raise HTTPException(400, "该申报已作废，不能重复作废")
    if not req or not req.reason.strip():
        raise HTTPException(400, "只允许作废，不许硬删，请填写作废原因")
    if r.match_status not in (None, MatchStatus.UNMATCHED) or (await db.execute(select(ReconciliationDeclaration.id).where(ReconciliationDeclaration.declaration_id==r.id, ReconciliationDeclaration.is_active.is_(True)).limit(1))).first():
        raise HTTPException(400, "请先撤销匹配再作废")
    wh_id = r.warehouse_id
    before = {
        "amount": r.amount, "currency": r.currency,
        "declare_date": r.declare_date.isoformat() if r.declare_date else None,
        "remark": r.remark, "payment_method": r.payment_method, "customer_id": r.customer_id,
        "is_voided": False, "match_status": r.match_status, "void_reason": r.void_reason,
    }
    r.is_voided = True
    r.voided_at = thai_now()
    r.voided_by = current_user.id
    r.void_reason = req.reason.strip()
    # Existing reconciliation reads and write guards only accept "unmatched".
    # Mark this declaration terminal without changing the matching code or any flow.
    r.match_status = "voided"
    await db.flush()
    await record_history(db, module="recharge", record_id=recharge_id, operator=current_user,
                          operation_type="void", before=before, after={
                              **before, **_void_info(r), "match_status": r.match_status,
                              "voided_by_name": current_user.display_name or current_user.username,
                          }, warehouse_id=wh_id)
    return {"id": r.id, "message": "申报已作废，记录保留，不再计入申报汇总和对账", "match_status": r.match_status, **_void_info(r)}
