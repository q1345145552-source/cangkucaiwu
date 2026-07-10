from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
import os, uuid
from app.database import get_db
from app.models.expense_fund import ExpenseFund, ExpenseFundItem, FundStatus, ReviewStatus, SystemSetting, FundRechargeRequest
from app.models.user import User
from app.models.reimbursement import Reimbursement, ReimbStatus
from app.models.warehouse import Warehouse
from app.core.permissions import get_current_user, get_wh_id, Role
from pydantic import BaseModel
from typing import Optional, List

router = APIRouter()

async def get_setting(db: AsyncSession, warehouse_id: int, key: str, default: str = "5000"):
    r = (await db.execute(select(SystemSetting).where(
        SystemSetting.warehouse_id == warehouse_id, SystemSetting.key == key
    ))).scalar_one_or_none()
    return r.value if r else default

async def ensure_account(db: AsyncSession, warehouse_id: int, employee_id: int, user_id: int) -> ExpenseFund:
    """确保员工有账户，没有则创建"""
    r = (await db.execute(select(ExpenseFund).where(
        ExpenseFund.warehouse_id == warehouse_id,
        ExpenseFund.employee_id == employee_id,
    ))).scalar_one_or_none()
    if not r:
        fund_limit = float(await get_setting(db, warehouse_id, "fund_limit", "5000"))
        alert = float(await get_setting(db, warehouse_id, "fund_alert_threshold", "500"))
        r = ExpenseFund(
            warehouse_id=warehouse_id, employee_id=employee_id,
            receive_date=datetime.utcnow(), amount=0, purpose="",
            remaining_balance=0, fund_limit=fund_limit, alert_threshold=alert,
            status=FundStatus.ACTIVE.value,
        )
        db.add(r)
        await db.flush()
    return r


# ==== Pydantic models ====
class TopUpReq(BaseModel):
    amount: float
    receive_date: str = None

class FundItemCreate(BaseModel):
    expense_date: str; category: str; amount: float; description: str
    currency: str = "THB"
    receipt: Optional[str] = None

class BatchReviewReq(BaseModel):
    item_ids: List[int]
    action: str  # approve / reject
    remark: Optional[str] = None

class SettingsUpdate(BaseModel):
    key: str; value: str

class RechargeRequestCreate(BaseModel):
    amount: float
    reason: str = ""

class RechargeRequestReview(BaseModel):
    request_id: int
    action: str  # approve / reject
    remark: str = ""

class CreateAccountReq(BaseModel):
    employee_id: int
    fund_limit: Optional[float] = None


# ==== Account Overview ====
@router.post("/accounts")
async def create_account(
    req: CreateAccountReq,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """手动为指定员工创建备用金账户"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    wh_id = get_wh_id(current_user)
    # 验证员工属于本仓库
    emp = (await db.execute(select(User).where(User.id == req.employee_id, User.warehouse_id.in_(get_wh_ids(current_user))))).scalar_one_or_none()
    if not emp:
        raise HTTPException(404, "无此员工")
    # 检查是否已有活跃账户
    existing = (await db.execute(select(ExpenseFund).where(
        ExpenseFund.warehouse_id.in_(get_wh_ids(current_user)),
        ExpenseFund.employee_id == req.employee_id,
        ExpenseFund.status == FundStatus.ACTIVE.value,
    ))).scalar_one_or_none()
    if existing:
        raise HTTPException(400, "该员工已有备用金账户")
    fund_limit = req.fund_limit or float(await get_setting(db, wh_id, "fund_limit", "5000"))
    alert = float(await get_setting(db, wh_id, "fund_alert_threshold", "500"))
    account = ExpenseFund(
        warehouse_id=wh_id, employee_id=req.employee_id,
        receive_date=datetime.utcnow(), amount=0, purpose="",
        remaining_balance=0, fund_limit=fund_limit, alert_threshold=alert,
        status=FundStatus.ACTIVE.value,
    )
    db.add(account)
    await db.flush()
    return {"id": account.id, "message": "备用金账户创建成功"}

@router.get("/employees")
async def list_employees(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出本仓库所有非超管员工"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    wh_id = get_wh_id(current_user)
    employees = (await db.execute(select(User).where(
        User.warehouse_id.in_(get_wh_ids(current_user)),
        User.role != Role.SUPER_ADMIN,
    ))).scalars().all()
    # 获取已有账户的员工
    accounts = (await db.execute(select(ExpenseFund).where(
        ExpenseFund.warehouse_id.in_(get_wh_ids(current_user)),
        ExpenseFund.status == FundStatus.ACTIVE.value,
    ))).scalars().all()
    acct_emp_ids = {a.employee_id for a in accounts}
    return {"data": [{"id": e.id, "display_name": e.display_name, "role": e.role,
                      "has_account": e.id in acct_emp_ids} for e in employees]}

@router.get("/accounts")
async def list_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出本仓库所有员工的备用金账户（含余额）"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    wh_id = get_wh_id(current_user)
    # 列出所有活跃账户（排除超级管理员）
    accounts = (await db.execute(
        select(ExpenseFund).join(User, ExpenseFund.employee_id == User.id).where(
            ExpenseFund.warehouse_id.in_(get_wh_ids(current_user)),
            ExpenseFund.status == FundStatus.ACTIVE.value,
            User.role != Role.SUPER_ADMIN,
        )
    )).scalars().all()
    uids = {a.employee_id for a in accounts}
    umap = {}
    if uids:
        users = (await db.execute(select(User).where(User.id.in_(uids)))).scalars().all()
        umap = {u.id: u.display_name for u in users}

    result = []
    for a in accounts:
        # Count spent amount
        spent_q = select(func.coalesce(func.sum(ExpenseFundItem.amount), 0)).where(
            ExpenseFundItem.fund_id == a.id,
            ExpenseFundItem.review_status == ReviewStatus.PENDING.value,
        )
        spent = float((await db.execute(spent_q)).scalar() or 0)
        result.append({
            "id": a.id, "employee_id": a.employee_id,
            "employee_name": umap.get(a.employee_id, ""),
            "total_topped_up": a.amount or 0,
            "current_balance": (a.remaining_balance or 0),
            "total_spent": spent,
            "available": max(0, (a.remaining_balance or 0) - spent),
            "fund_limit": a.fund_limit or 5000,
            "alert_threshold": a.alert_threshold or 500,
            "is_low": (a.remaining_balance or 0) <= (a.alert_threshold or 500),
        })
    return {"data": result}


# ==== Top Up (充值) ====
@router.post("/accounts/{account_id}/topup")
async def topup_account(
    account_id: int, req: TopUpReq,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """给备用金账户充值，余额不能超过上限"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")

    account = (await db.execute(select(ExpenseFund).where(ExpenseFund.id == account_id))).scalar_one_or_none()
    if not account:
        raise HTTPException(404, "账户不存在")

    new_balance = (account.remaining_balance or 0) + req.amount
    limit = account.fund_limit or 5000
    if new_balance > limit:
        raise HTTPException(400, f"超出账户上限（{limit:,.0f}），当前余额 {account.remaining_balance:,.0f}，最多可充 {limit - (account.remaining_balance or 0):,.0f}")

    account.remaining_balance = new_balance
    account.amount = (account.amount or 0) + req.amount  # 累计充值总额
    if req.receive_date:
        account.receive_date = datetime.fromisoformat(req.receive_date)
    await db.flush()

    return {
        "message": f"充值成功",
        "new_balance": account.remaining_balance,
        "total_topped_up": account.amount,
    }


# ==== Items (开销) ====
@router.get("/accounts/{account_id}/items")
async def list_items(
    account_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出一个账户下所有开销"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    result = await db.execute(select(ExpenseFundItem).where(
        ExpenseFundItem.fund_id == account_id,
    ).order_by(ExpenseFundItem.expense_date.desc()))
    items = result.scalars().all()
    return {"data": [{
        "id": i.id, "fund_id": i.fund_id,
        "expense_date": i.expense_date.isoformat() if i.expense_date else None,
        "category": i.category, "amount": i.amount, "currency": i.currency or "THB",
        "description": i.description, "receipt": i.receipt,
        "review_status": i.review_status,
        "review_remark": i.review_remark, "review_action": i.review_action,
    } for i in items]}

@router.post("/accounts/{account_id}/items")
async def add_item(
    account_id: int, req: FundItemCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """添加开销记录"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")

    account = (await db.execute(select(ExpenseFund).where(ExpenseFund.id == account_id))).scalar_one_or_none()
    if not account:
        raise HTTPException(404, "账户不存在")

    i = ExpenseFundItem(
        fund_id=account_id, expense_date=datetime.fromisoformat(req.expense_date),
        category=req.category, amount=req.amount, currency=req.currency or "THB",
        description=req.description, receipt=req.receipt,
    )
    db.add(i)
    await db.flush()
    return {"id": i.id, "message": "开销记录添加成功"}


# ==== Upload Receipt ====
@router.post("/accounts/{account_id}/items/{item_id}/upload-receipt")
async def upload_receipt(
    account_id: int, item_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
):
    item = (await db.execute(select(ExpenseFundItem).where(
        ExpenseFundItem.id == item_id, ExpenseFundItem.fund_id == account_id
    ))).scalar_one_or_none()
    if not item:
        raise HTTPException(404, "开销记录不存在")
    upload_dir = "uploads/fund_receipts"
    os.makedirs(upload_dir, exist_ok=True)
    ext = file.filename.rsplit(".", 1)[-1] if "." in (file.filename or "") else "jpg"
    filename = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(upload_dir, filename), "wb") as f:
        f.write(await file.read())
    item.receipt = f"/uploads/fund_receipts/{filename}"
    await db.flush()
    return {"message": "凭证上传成功", "receipt": item.receipt}


# ==== Review (审核) ====
@router.get("/review/pending")
async def list_pending_reviews(
    page: int = 1, page_size: int = 100,
    employee_id: int = Query(None),
    start_date: str = Query(None),
    end_date: str = Query(None),
    currency: str = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.STAFF):
        raise HTTPException(403, "无审核权限")
    wh_id = get_wh_id(current_user)

    filters = [
        ExpenseFund.warehouse_id.in_(get_wh_ids(current_user)),
        ExpenseFundItem.review_status == ReviewStatus.PENDING.value,
    ]
    if employee_id:
        filters.append(ExpenseFund.employee_id == employee_id)
    if start_date:
        filters.append(ExpenseFundItem.expense_date >= datetime.strptime(start_date, "%Y-%m-%d"))
    if end_date:
        filters.append(ExpenseFundItem.expense_date <= datetime.strptime(end_date, "%Y-%m-%d"))
    if currency:
        filters.append(ExpenseFundItem.currency == currency)

    q = (select(ExpenseFundItem)
         .join(ExpenseFund, ExpenseFundItem.fund_id == ExpenseFund.id)
         .where(*filters)
         .order_by(ExpenseFundItem.expense_date.desc())
         .offset((page-1)*page_size).limit(page_size))
    items = (await db.execute(q)).scalars().all()
    total_q = (select(func.count(ExpenseFundItem.id))
               .join(ExpenseFund, ExpenseFundItem.fund_id == ExpenseFund.id)
               .where(*filters))
    total = (await db.execute(total_q)).scalar()

    fund_ids = {i.fund_id for i in items}
    funds_map, emp_map, wh_map = {}, {}, {}
    if fund_ids:
        funds = (await db.execute(select(ExpenseFund).where(ExpenseFund.id.in_(fund_ids)))).scalars().all()
        funds_map = {f.id: f for f in funds}
        eids = {f.employee_id for f in funds}
        wids = {f.warehouse_id for f in funds}
        if eids:
            users = (await db.execute(select(User).where(User.id.in_(eids)))).scalars().all()
            emp_map = {u.id: u.display_name for u in users}
        if wids:
            whs = (await db.execute(select(Warehouse).where(Warehouse.id.in_(wids)))).scalars().all()
            wh_map = {w.id: w.name for w in whs}

    return {"data": [{
        "id": i.id, "fund_id": i.fund_id,
        "employee_id": funds_map.get(i.fund_id, ExpenseFund()).employee_id,
        "employee_name": emp_map.get(funds_map.get(i.fund_id, ExpenseFund()).employee_id, ""),
        "warehouse_name": wh_map.get(funds_map.get(i.fund_id, ExpenseFund()).warehouse_id, ""),
        "fund_limit": funds_map.get(i.fund_id, ExpenseFund()).fund_limit or 5000,
        "receive_date": funds_map.get(i.fund_id, ExpenseFund()).receive_date.isoformat() if funds_map.get(i.fund_id) and funds_map[i.fund_id].receive_date else None,
        "expense_date": i.expense_date.isoformat() if i.expense_date else None,
        "category": i.category, "amount": i.amount, "currency": i.currency or "THB",
        "description": i.description, "receipt": i.receipt,
        "review_status": i.review_status, "review_remark": i.review_remark,
    } for i in items], "total": total, "page": page, "page_size": page_size}

@router.post("/review/batch")
async def batch_review(
    req: BatchReviewReq,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role == Role.STAFF and "备用金管理" not in (current_user.extra_permissions or []):
        raise HTTPException(403, "无审批备用金权限")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.STAFF):
        raise HTTPException(403, "无审核权限")

    new_status = "approved" if req.action == "approve" else "rejected"

    for item_id in req.item_ids:
        item = (await db.execute(select(ExpenseFundItem).where(ExpenseFundItem.id == item_id))).scalar_one_or_none()
        if not item: continue
        item.review_status = new_status
        item.review_remark = req.remark

        # Sync with linked reimbursement
        if item.category == "报销":
            reimb = (await db.execute(select(Reimbursement).where(
                Reimbursement.fund_item_id == item_id,
                Reimbursement.is_fund_linked == "1",
            ))).scalar_one_or_none()
            if reimb:
                if req.action == "approve":
                    reimb.status = ReimbStatus.PAID.value
                    reimb.paid_at = datetime.utcnow()
                elif req.action == "reject":
                    # Restore balance and unlock reimbursement
                    fund = (await db.execute(select(ExpenseFund).where(ExpenseFund.id == item.fund_id))).scalar_one_or_none()
                    if fund:
                        fund.remaining_balance = (fund.remaining_balance or 0) + item.amount
                    reimb.status = ReimbStatus.PENDING.value
                    reimb.is_fund_linked = "0"

    await db.flush()

    labels = {"approve": "通过", "reject": "驳回"}
    return {"message": f"已{labels.get(req.action, req.action)}{len(req.item_ids)}条记录"}


# ==== Recharge Requests (申请-审核模式) ====
@router.post("/recharge/request")
async def submit_recharge_request(
    req: RechargeRequestCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """财务提交充值申请"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.STAFF):
        raise HTTPException(403, "无权限")
    if req.amount <= 0:
        raise HTTPException(400, "充值金额必须大于0")

    wh_id = get_wh_id(current_user)

    # Find or create the fund account for this user
    fund = await ensure_account(db, wh_id, current_user.id, current_user.id)

    rr = FundRechargeRequest(
        fund_id=fund.id,
        warehouse_id=wh_id,
        applicant_id=current_user.id,
        amount=req.amount,
        reason=req.reason,
        status="pending",
    )
    db.add(rr)
    await db.flush()
    return {"id": rr.id, "message": "充值申请已提交，等待管理员审核"}

@router.get("/recharge/requests")
async def list_recharge_requests(
    page: int = 1, page_size: int = 50,
    status: str = None,
    applicant_id: int = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """列出充值申请列表 - 管理员看本仓库所有，财务看自己的"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")

    wh_id = get_wh_id(current_user)

    query = select(FundRechargeRequest, ExpenseFund, User, Warehouse).join(
        ExpenseFund, FundRechargeRequest.fund_id == ExpenseFund.id
    ).join(User, FundRechargeRequest.applicant_id == User.id).join(
        Warehouse, FundRechargeRequest.warehouse_id == Warehouse.id
    ).where(FundRechargeRequest.warehouse_id.in_(get_wh_ids(current_user)))

    if current_user.role == Role.STAFF:
        query = query.where(FundRechargeRequest.applicant_id == current_user.id)

    if status:
        query = query.where(FundRechargeRequest.status == status)
    if applicant_id:
        query = query.where(FundRechargeRequest.applicant_id == applicant_id)

    count_q = select(func.count(FundRechargeRequest.id)).where(FundRechargeRequest.warehouse_id.in_(get_wh_ids(current_user)))
    if current_user.role == Role.STAFF:
        count_q = count_q.where(FundRechargeRequest.applicant_id == current_user.id)
    if status:
        count_q = count_q.where(FundRechargeRequest.status == status)
    if applicant_id:
        count_q = count_q.where(FundRechargeRequest.applicant_id == applicant_id)

    total = (await db.execute(count_q)).scalar()
    rows = (await db.execute(query.order_by(FundRechargeRequest.created_at.desc()).offset((page-1)*page_size).limit(page_size))).all()

    result = []
    for rr, fund, applicant, wh in rows:
        result.append({
            "id": rr.id, "fund_id": rr.fund_id, "warehouse_id": rr.warehouse_id,
            "warehouse_name": wh.name,
            "applicant_id": rr.applicant_id, "applicant_name": applicant.display_name,
            "amount": rr.amount, "reason": rr.reason or "", "status": rr.status,
            "current_balance": fund.remaining_balance,
            "fund_limit": fund.fund_limit,
            "review_remark": rr.review_remark or "",
            "reviewer_id": rr.reviewer_id,
            "reviewed_at": rr.reviewed_at.isoformat() if rr.reviewed_at else None,
            "created_at": rr.created_at.isoformat() if rr.created_at else None,
        })

    return {"data": result, "total": total, "page": page, "page_size": page_size}

@router.post("/recharge/review")
async def review_recharge_request(
    req: RechargeRequestReview,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """管理员审核充值申请"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role != Role.WAREHOUSE_ADMIN:
        raise HTTPException(403, "只有仓库管理员可以审核充值申请")

    rr = (await db.execute(select(FundRechargeRequest).where(FundRechargeRequest.id == req.request_id))).scalar_one_or_none()
    if not rr:
        raise HTTPException(404, "申请不存在")
    if rr.status != "pending":
        raise HTTPException(400, "该申请已处理")

    wh_id = get_wh_id(current_user)
    if rr.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "无权审核其他仓库的申请")

    if req.action == "approve":
        rr.status = "approved"
        rr.reviewer_id = current_user.id
        rr.review_remark = ""
        rr.reviewed_at = datetime.utcnow()

        # Increase the fund balance
        fund = (await db.execute(select(ExpenseFund).where(ExpenseFund.id == rr.fund_id))).scalar_one_or_none()
        if fund:
            fund.remaining_balance = (fund.remaining_balance or 0) + rr.amount
            fund.amount = (fund.amount or 0) + rr.amount

        await db.flush()
        return {"message": "充值申请已通过，余额已更新"}

    elif req.action == "reject":
        rr.status = "rejected"
        rr.reviewer_id = current_user.id
        rr.review_remark = req.remark or "已驳回"
        rr.reviewed_at = datetime.utcnow()

        await db.flush()
        return {"message": "充值申请已驳回"}

    else:
        raise HTTPException(400, "无效操作，请选择通过或驳回")

# ==== System Settings ====
@router.get("/settings")
async def fund_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    wh_id = get_wh_id(current_user)
    fund_limit = await get_setting(db, wh_id, "fund_limit", "5000")
    alert_threshold = await get_setting(db, wh_id, "fund_alert_threshold", "500")
    return {"fund_limit": float(fund_limit), "fund_alert_threshold": float(alert_threshold)}

@router.post("/settings")
async def update_settings(
    req: SettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    wh_id = get_wh_id(current_user)
    existing = (await db.execute(select(SystemSetting).where(
        SystemSetting.warehouse_id.in_(get_wh_ids(current_user)), SystemSetting.key == req.key
    ))).scalar_one_or_none()
    if existing:
        existing.value = req.value
        existing.updated_by = current_user.id
    else:
        s = SystemSetting(warehouse_id=wh_id, key=req.key, value=req.value, updated_by=current_user.id)
        db.add(s)
    await db.flush()
    return {"message": "设置已保存"}


# ==== Legacy passthrough (dashboard/alert still use) ====
@router.get("/balance")
async def balance_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await list_accounts(current_user=current_user, db=db)

@router.get("/alert")
async def alert_list(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    wh_id = get_wh_id(current_user)
    query = select(ExpenseFund).where(
        ExpenseFund.warehouse_id.in_(get_wh_ids(current_user)),
        ExpenseFund.status == FundStatus.ACTIVE.value,
        ExpenseFund.remaining_balance <= ExpenseFund.alert_threshold,
    )
    funds = (await db.execute(query)).scalars().all()
    uids = {f.employee_id for f in funds}
    umap = {}
    if uids:
        users = (await db.execute(select(User).where(User.id.in_(uids)))).scalars().all()
        umap = {u.id: u.display_name for u in users}
    return {"data": [{"employee_name": umap.get(f.employee_id, ""),
                      "remaining_balance": f.remaining_balance, "threshold": f.alert_threshold,
                      "fund_id": f.id} for f in funds]}
