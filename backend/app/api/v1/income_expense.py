from app.services.balance_warning import saved_balance_warning
from app.services.payroll_expense import require_manual_expense
from app.services.reimbursement_payment import require_manual_reimbursement_expense
from app.services.employee_advance_expense import require_manual_advance_expense
from app.services.fund_disbursement import cost_record_filter, require_manual_disbursement_expense
from app.models.expense_fund import ExpenseFundDisbursement
from app.models.employee_advance import EmployeeAdvance
from app.models.reimbursement import Reimbursement
from app.models.payroll import PayrollRecord
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from typing import Optional, List, Literal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.timezone import thai_now, thai_today
from datetime import date, datetime, timedelta
from app.database import get_db
from app.models.income_expense import IncomeRecord, ExpenseRecord, IncomeExpenseCategory, IncomeExpenseType, CategoryStatus
from app.models.customer import Customer, PaymentAccount
from app.models.supplier import Supplier
from app.models.user import User
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role, check_staff_permission, check_staff_permission_any, require_non_labor
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.schemas.business import IncomeRecordCreate, ExpenseRecordCreate, CategoryCreate
from app.services.data_history import record_history
from app.services.money_period import money_period
from app.services.internal_transfers import selected_wallet_warehouses, transfer_summary, transfer_record_filters, append_transfer_sheet
from app.services import cost_identity as costs

async def validate_manual_money(db, wid, account_id, category_id, currency, kind, value):
    from app.services.wallet import lock_account
    from decimal import Decimal, InvalidOperation
    account=await lock_account(db, wid, account_id, currency)
    category = (await db.execute(select(IncomeExpenseCategory).where(IncomeExpenseCategory.id == category_id,
        IncomeExpenseCategory.warehouse_id == wid, IncomeExpenseCategory.type == kind))).scalar_one_or_none()
    if category is None: raise HTTPException(400, "收支分类不存在或不属于当前仓库")
    try:
        n = Decimal(str(value))
        if not n.is_finite() or n == 0 or abs(n) >= Decimal("1000000000000") or n != n.quantize(Decimal("0.01")): raise ValueError
    except (ValueError, InvalidOperation): raise HTTPException(400, "金额必须非零且最多两位小数")
    return account


OPERATING_NAMES = ["仓储费", "操作费", "增值服务费", "工资", "电费", "网费", "房租", "耗材", "物流运费", "快递费", "保险费", "税费"]

router = APIRouter()


# ==== Categories ====
@router.get("/categories")
async def list_categories(type: str = None, category_group: str = None, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db),
                          _perm=Depends(check_staff_permission_any("运营收支", "其他收支"))):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(IncomeExpenseCategory)
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(IncomeExpenseCategory.warehouse_id.in_(get_wh_ids(current_user)))
    if type:
        query = query.where(IncomeExpenseCategory.type == type)
    if category_group:
        query = query.where(IncomeExpenseCategory.category_group == category_group)
    result = await db.execute(query.order_by(IncomeExpenseCategory.sort_order))
    cats = result.scalars().all()
    return {"data": [{"id": c.id, "warehouse_id": c.warehouse_id, "type": c.type,
                      "name": c.name, "sort_order": c.sort_order, "status": c.status, "category_group": c.category_group} for c in cats]}

@router.post("/categories")
async def create_category(req: CategoryCreate, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db),
                          _perm=Depends(check_staff_permission_any("运营收支", "其他收支"))):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    # 自动归类：运营类 vs 其他
    from app.api.v1.income_expense import OPERATING_NAMES
    category_group = "operating" if req.name in OPERATING_NAMES else "other"
    c = IncomeExpenseCategory(warehouse_id=get_wh_id(current_user), category_group=category_group, **req.model_dump())
    db.add(c); await db.flush(); return {"id": c.id, "message": "创建成功"}

# ==== Income ====
@router.get("/income")
async def list_income(
    page: int = 1, page_size: int = 20, month: str = None, year: str = None,
    start_date: str = None, end_date: str = None,
    account_id: int = None, customer_id: int = None,
    category_id: int = None,
    category_group: str = None,
    currency: str = None,
    search: str = None,
    source: str = None,
    selected_ids: list[int] = Depends(selected_wallet_warehouses),
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission_any("运营收支", "其他收支")),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    from app.services.money_records import records,record_period
    start, end = record_period(start_date,end_date,month=month,year=year)
    return await records(db,selected_ids,'income',start,end,page=max(page,1),page_size=min(max(page_size,1),200),
        account_id=account_id,customer_id=customer_id,category_id=category_id,category_group=category_group,
        currency=currency,search=search,source=source)

@router.post("/income")
async def create_income(req: IncomeRecordCreate, current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db),
                        _perm=Depends(check_staff_permission_any("运营收支", "其他收支"))):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    try:when=datetime.fromisoformat(req.income_date)
    except ValueError:raise HTTPException(400,'收款日期格式错误')
    values=dict(
        warehouse_id=get_wh_id(current_user), category_id=req.category_id,
        account_id=req.account_id, customer_id=req.customer_id,
        amount=req.amount, currency=req.currency,
        income_date=when,
        voucher=req.voucher, remark=req.remark, confirmed_by=current_user.id,
    )
    from app.services.manual_wallet import prepare,insert_once,lookup
    old=await lookup(db,'income',values,req.request_key)
    if old:return {'id':old.id,'created':False,'message':'收款记录已保存，请勿重复录入'}
    account=await validate_manual_money(db, get_wh_id(current_user), req.account_id, req.category_id, req.currency, "income", req.amount)
    old,fingerprint,_warning=await prepare(db,'income',values,req.request_key,account=account)
    if old:return {'id':old.id,'created':False,'message':'收款记录已保存，请勿重复录入'}
    r,created=await insert_once(db,'income',values,req.request_key,fingerprint)
    return {'id':r.id,'created':created,'message':'收款记录创建成功' if created else '收款记录已保存，请勿重复录入'}

# ==== Income Edit / Delete ====
@router.put("/income/{income_id}", dependencies=[Depends(require_non_labor)])
async def update_income(income_id: int, req: IncomeRecordCreate, current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db),
                        _perm=Depends(check_staff_permission("其他收支"))):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    r = (await db.execute(select(IncomeRecord).where(IncomeRecord.id == income_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "记录不存在")
    if current_user.role != Role.SUPER_ADMIN and r.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "无权限")
    await validate_manual_money(db, r.warehouse_id, req.account_id, req.category_id, req.currency, "income", req.amount)
    r.category_id = req.category_id
    r.account_id = req.account_id
    r.amount = req.amount
    r.currency = req.currency
    r.income_date = datetime.fromisoformat(req.income_date)
    r.remark = req.remark
    await db.flush()
    return {"message": "更新成功"}

@router.delete("/income/{income_id}", dependencies=[Depends(require_non_labor)])
async def delete_income(income_id: int, current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db),
                        _perm=Depends(check_staff_permission("其他收支"))):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    r = (await db.execute(select(IncomeRecord).where(IncomeRecord.id == income_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "记录不存在")
    if current_user.role != Role.SUPER_ADMIN and r.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "无权限")
    await db.delete(r)
    await db.flush()
    return {"message": "删除成功"}


# ==== Expense ====
@router.get("/expense", dependencies=[Depends(require_non_labor)])
async def list_expense(
    page: int = 1, page_size: int = 20, month: str = None, year: str = None,
    category_id: int = None, account_id: int = None,
    start_date: str = None, end_date: str = None,
    category_group: str = None,
    currency: str = None,
    customer_id: int = None, supplier_id: int = None, source: str = None, search: str = None,
    cost_view: Literal["records", "unified"] = "records", cost_category: str | None = None,
    selected_ids: list[int] = Depends(selected_wallet_warehouses),
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("运营收支")),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    from app.services.money_records import records,record_period
    start, end = record_period(start_date,end_date,month=month,year=year)
    return await records(db,selected_ids,'expense',start,end,page=max(page,1),page_size=min(max(page_size,1),200),
        category_id=category_id,category_group=category_group,cost_category=cost_category,account_id=account_id,
        customer_id=customer_id,supplier_id=supplier_id,currency=currency,source=source,search=search)

@router.get("/expense/export", dependencies=[Depends(require_non_labor)])
async def export_expense(month: str = None, year: str = None, start_date: str = None, end_date: str = None,
                         category_id: int = None, category_group: str = None, cost_category: str = None,
                         account_id: int = None, customer_id: int = None, supplier_id: int = None,
                         currency: str = None, source: str = None, search: str = None,
                         selected_ids: list[int] = Depends(selected_wallet_warehouses),
                         current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
                         _perm=Depends(check_staff_permission("运营收支"))):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    from app.services.money_records import record_period
    start,end=record_period(start_date,end_date,month=month,year=year)
    return await export_money_records(db,selected_ids,'expense',start,end,category_id=category_id,
        category_group=category_group,cost_category=cost_category,account_id=account_id,customer_id=customer_id,
        supplier_id=supplier_id,currency=currency,source=source,search=search)

@router.post("/expense")
async def create_expense(
    category_id: int = Form(...),
    account_id: int = Form(...),
    amount: float = Form(...),
    currency: str = Form("THB"),
    expense_date: str = Form(...),
    supplier_id: Optional[int] = Form(None),
    remark: Optional[str] = Form(None),
    request_key: Optional[str] = Form(None),
    invoice_identity: Optional[str] = Form(None),
    cost_confirmation: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("运营收支")),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")

    wh_id = get_wh_id(current_user)

    try:when=datetime.fromisoformat(expense_date)
    except ValueError:raise HTTPException(400,'付款日期格式错误')
    values=dict(warehouse_id=wh_id,category_id=category_id,account_id=account_id,supplier_id=supplier_id,
        amount=amount,currency=currency,expense_date=when,remark=remark,approved_by=current_user.id)
    costs.number(request_key,'登记请求编号',100)
    await costs.lock(db,wh_id)
    identity=costs.parse_identity(invoice_identity,current_user)
    import hashlib
    attachments=[]
    for attachment in files or []:
        if attachment and attachment.filename:
            attachments.append(hashlib.sha256(await attachment.read()).hexdigest());await attachment.seek(0)
    signature=costs.fingerprint({**values,'invoice_key':identity[1],'attachments':attachments})
    previous=await costs.replay(db,'expense',wh_id,request_key,signature)
    if previous:return {'warning':await saved_balance_warning(db,module='expense',record_id=previous.id),'id':previous.id,'created':False,'message':'付款记录已保存，请勿重复录入','voucher':previous.voucher,**await costs.metadata_for(db,previous)}
    from app.services.balance_warning import record_balance_warning
    from app.services.manual_wallet import prepare,insert_once,lookup
    old=await lookup(db,'expense',values,request_key)
    if old:return {'warning':await saved_balance_warning(db,module='expense',record_id=old.id),'id':old.id,'created':False,'message':'付款记录已保存，请勿重复录入','voucher':old.voucher}
    account=await validate_manual_money(db, wh_id, account_id, category_id, currency, "expense", amount)
    old,fingerprint,warning=await prepare(db,'expense',values,request_key,account=account)
    if old:return {'warning':await saved_balance_warning(db,module='expense',record_id=old.id),'id':old.id,'created':False,'message':'付款记录已保存，请勿重复录入','voucher':old.voucher}
    # 凭证图片（可选，可多张）：保存到 uploads 目录，路径以 JSON 数组写入 voucher 字段
    import os, uuid, json
    from app.services.image_utils import save_image
    UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")
    today_str = thai_now().strftime("%Y-%m-%d")
    voucher_paths: list = []
    if files:
        abs_subdir = os.path.join(UPLOAD_DIR, str(wh_id), today_str, "expense_vouchers")
        rel_subdir = f"uploads/{wh_id}/{today_str}/expense_vouchers"
        for file in files:
            if file is None or not file.filename:
                continue
            ext = file.filename.split(".")[-1].lower() if file.filename else ""
            if ext not in ("png", "jpg", "jpeg", "webp"):
                raise HTTPException(400, "凭证仅支持图片格式 png/jpg/jpeg/webp")
            content = await file.read()
            if len(content) > 10 * 1024 * 1024:
                raise HTTPException(400, "单张凭证图片不能超过10MB")
            from app.services.image_utils import is_image
            if not is_image(content):
                raise HTTPException(400, "文件不是有效的图片，请重新选择")
            fname = f"{uuid.uuid4().hex}.{ext}"
            result = save_image(content, abs_subdir, rel_subdir, fname)
            voucher_paths.append(result["path"])

    voucher_field = json.dumps(voucher_paths, ensure_ascii=False) if voucher_paths else None

    r,created=await insert_once(db,'expense',{**values,'voucher':voucher_field},request_key,fingerprint)
    root=await costs.sync(db,'expense',r,current_user,supplier=supplier_id,identity=identity,
        confirmation=cost_confirmation,key=request_key,signature=signature)
    if created:await record_history(db, module="expense", record_id=r.id, operator=current_user,
                          operation_type="create", after={
                              "amount": amount, "currency": currency,
                              "expense_date": expense_date, "category_id": category_id,
                              "account_id": account_id, "remark": remark, "voucher": voucher_field,
                          }, warehouse_id=wh_id)
    if created:await record_balance_warning(db,warning,current_user,module='expense',record_id=r.id,warehouse_id=wh_id)
    else:warning=await saved_balance_warning(db,module='expense',record_id=r.id)
    return {'warning':warning,"id": r.id, "created":created,"message": "付款记录创建成功" if created else '付款记录已保存，请勿重复录入', "voucher": r.voucher,**costs.metadata(root)}

@router.put("/expense/{expense_id}")
async def update_expense(
    expense_id: int,
    category_id: int = Form(...),
    account_id: int = Form(...),
    amount: float = Form(...),
    currency: str = Form("THB"),
    expense_date: str = Form(...),
    supplier_id: Optional[int] = Form(None),
    remark: Optional[str] = Form(None),
    delete_vouchers: Optional[str] = Form(None),  # JSON 数组字符串：要删除的凭证路径
    invoice_identity: Optional[str] = Form(None),
    cost_confirmation: Optional[str] = Form(None),
    files: Optional[List[UploadFile]] = File(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("运营收支")),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")

    await costs.lock(db,get_wh_id(current_user))
    r = (await db.execute(select(ExpenseRecord).where(ExpenseRecord.id == expense_id).with_for_update())).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "记录不存在")
    if current_user.role != Role.SUPER_ADMIN and r.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "无权限")

    await require_manual_expense(db, expense_id)
    await require_manual_reimbursement_expense(db, expense_id)
    await require_manual_advance_expense(db, expense_id)
    await require_manual_disbursement_expense(db, expense_id)

    await validate_manual_money(db, r.warehouse_id, account_id, category_id, currency, "expense", amount)
    before = {
        "amount": r.amount, "currency": r.currency,
        "expense_date": r.expense_date.isoformat() if r.expense_date else None,
        "category_id": r.category_id, "account_id": r.account_id,
        "supplier_id": r.supplier_id, "remark": r.remark, "voucher": r.voucher,
    }

    import os, uuid, json
    UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")
    today_str = thai_now().strftime("%Y-%m-%d")

    # 解析当前凭证（兼容旧单路径字符串 + 新 JSON 数组）
    def _parse(v):
        if not v:
            return []
        s = v.strip() if isinstance(v, str) else ""
        if not s:
            return []
        if s.startswith("["):
            try:
                a = json.loads(s)
                return [x for x in a if x] if isinstance(a, list) else [s]
            except Exception:
                return [s]
        return [s]

    vouchers = _parse(r.voucher)

    # 删除指定凭证
    if delete_vouchers:
        try:
            del_list = json.loads(delete_vouchers)
            if not isinstance(del_list, list):
                del_list = [delete_vouchers]
        except Exception:
            del_list = [delete_vouchers]
        del_set = set(del_list)
        vouchers = [p for p in vouchers if p not in del_set]
        # Retain original evidence on disk. A later identity rejection/rollback must not
        # erase an old attachment; the edit history preserves the previous references.

    # 追加新凭证
    if files:
        from app.services.image_utils import save_image
        abs_subdir = os.path.join(UPLOAD_DIR, str(r.warehouse_id), today_str, "expense_vouchers")
        rel_subdir = f"uploads/{r.warehouse_id}/{today_str}/expense_vouchers"
        for file in files:
            if file is None or not file.filename:
                continue
            ext = file.filename.split(".")[-1].lower() if file.filename else ""
            if ext not in ("png", "jpg", "jpeg", "webp"):
                raise HTTPException(400, "凭证仅支持图片格式 png/jpg/jpeg/webp")
            content = await file.read()
            if len(content) > 10 * 1024 * 1024:
                raise HTTPException(400, "单张凭证图片不能超过10MB")
            from app.services.image_utils import is_image
            if not is_image(content):
                raise HTTPException(400, "文件不是有效的图片，请重新选择")
            fname = f"{uuid.uuid4().hex}.{ext}"
            result = save_image(content, abs_subdir, rel_subdir, fname)
            vouchers.append(result["path"])

    # 更新字段
    r.category_id = category_id
    r.account_id = account_id
    r.amount = amount
    r.currency = currency
    r.expense_date = datetime.fromisoformat(expense_date)
    if supplier_id is not None:
        r.supplier_id = supplier_id
    r.remark = remark
    r.voucher = json.dumps(vouchers, ensure_ascii=False) if vouchers else None
    await costs.sync(db,'expense',r,current_user,supplier=r.supplier_id,
        identity=costs.parse_identity(invoice_identity,current_user) if invoice_identity is not None else costs.UNSET,
        confirmation=cost_confirmation)

    await db.flush()
    await record_history(db, module="expense", record_id=r.id, operator=current_user,
                          operation_type="edit", before=before, after={
                              "amount": amount, "currency": currency,
                              "expense_date": expense_date, "category_id": category_id,
                              "account_id": account_id, "supplier_id": r.supplier_id,
                              "remark": remark, "voucher": r.voucher,
                          }, warehouse_id=r.warehouse_id)
    return {"message": "更新成功", "voucher": r.voucher}

@router.delete("/expense/{expense_id}")
async def delete_expense(
    expense_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("运营收支")),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")

    await costs.lock(db,get_wh_id(current_user))
    r = (await db.execute(select(ExpenseRecord).where(ExpenseRecord.id == expense_id).with_for_update())).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "记录不存在")
    if current_user.role != Role.SUPER_ADMIN and r.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "无权限")

    wh_id = r.warehouse_id
    await require_manual_expense(db, expense_id)
    await require_manual_reimbursement_expense(db, expense_id)
    await require_manual_advance_expense(db, expense_id)
    await require_manual_disbursement_expense(db, expense_id)

    before = {
        "amount": r.amount, "currency": r.currency,
        "expense_date": r.expense_date.isoformat() if r.expense_date else None,
        "category_id": r.category_id, "account_id": r.account_id,
        "supplier_id": r.supplier_id, "remark": r.remark, "voucher": r.voucher,
    }
    await costs.deleted(db,'expense',r,current_user)
    await db.delete(r)
    await db.flush()
    await record_history(db, module="expense", record_id=expense_id, operator=current_user,
                          operation_type="delete", before=before, warehouse_id=wh_id)
    return {"message": "删除成功"}

# ==== Ledger ====
@router.get("/ledger", dependencies=[Depends(require_non_labor)])
async def ledger(
    page: int = 1, page_size: int = 30,
    start_date: str = None,
    end_date: str = None,
    month: str = None, year: str = None,
    source: str = None,
    flow_type: str = None,
    flow_scope: Literal["all", "company"] = "all", account_id: int | None = None,
    currency: Literal["THB", "CNY"] | None = None, unassigned: bool = False,
    selected_ids: list[int] = Depends(selected_wallet_warehouses),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["ledger"].label)),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    from app.services import cost_funds_debt as projection
    from datetime import date
    wid = get_wh_id(current_user)
    if getattr(current_user, "_all_warehouses", False) or wid is None:
        raise HTTPException(400, "请先选择一个仓库")
    start, end = money_period(month, start_date, end_date, year=year, default_start=date(1900,1,1), default_end=date.max)
    result = await projection.flow_list(db, selected_ids, start, end,
        page=max(page, 1), page_size=min(max(page_size, 1), 100000), account_id=account_id,
        currency_code=currency, source=source, flow_type=flow_type, unassigned=unassigned)
    result.update(card_income=result["total_income"], card_expense=result["total_expense"], card_net=result["net"])
    return result

# ==== Ledger Export ====
@router.get("/ledger/export", dependencies=[Depends(require_non_labor)])
async def ledger_export(
    start_date: str = None, end_date: str = None, source: str = None, flow_type: str = None,
    month: str = None, year: str = None,
    account_id: int | None = None, currency: Literal["THB", "CNY"] | None = None, unassigned: bool = False,
    selected_ids: list[int] = Depends(selected_wallet_warehouses),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["ledger"].label)),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    # Reuse same aggregation logic
    r = await ledger(page=1, page_size=99999, start_date=start_date, end_date=end_date, month=month, year=year, source=source, flow_type=flow_type, flow_scope="company", account_id=account_id, currency=currency, unassigned=unassigned, current_user=current_user, db=db, selected_ids=selected_ids)
    data = r.get("data", [])

    wb = __import__('openpyxl').Workbook()
    ws = wb.active; ws.title = "资金流水"
    hf = __import__('openpyxl').styles.PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    hfont = __import__('openpyxl').styles.Font(bold=True, color="FFFFFF")
    headers = ["日期", "金额", "币种", "类型", "来源模块", "说明", "关联单号"]
    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=c, value=h); cell.font = hfont; cell.fill = hf
    for i, row in enumerate(data, 2):
        type_label = "收入" if row.get("type") == "income" else "支出"
        vals = [
            row.get("date", ""), row.get("amount", 0), row.get("currency", ""),
            type_label, row.get("source_label", ""), row.get("remark", ""), row.get("ref_no", ""),
        ]
        for c, v in enumerate(vals, 1):
            ws.cell(row=i, column=c, value=str(v) if v is not None else "")
    append_transfer_sheet(wb, r["internal_transfers"])
    output = __import__('io').BytesIO(); wb.save(output); output.seek(0)
    filename = f"ledger_{start_date or 'all'}_{end_date or 'all'}.xlsx"
    return __import__('fastapi').responses.StreamingResponse(
        output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ==== Income Export ====
@router.get("/income/export")
async def export_income(
    month: str = None,
    year: str = None,
    category_group: str = None,
    currency: str = None,
    search: str = None,
    category_id: int = None,
    account_id: int = None, customer_id: int = None, source: str = None,
    start_date: str = None,
    end_date: str = None,
    selected_ids: list[int] = Depends(selected_wallet_warehouses),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission_any("运营收支", "其他收支")),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    from app.services.money_records import record_period
    start, end = record_period(start_date,end_date,month=month,year=year)
    return await export_money_records(db,selected_ids,'income',start,end,category_group=category_group,
        category_id=category_id,account_id=account_id,customer_id=customer_id,currency=currency,source=source,search=search)


async def export_money_records(db,warehouse_ids,kind,start,end,**filters):
    from app.services.money_records import records
    from fastapi.responses import StreamingResponse
    import openpyxl
    from io import BytesIO
    result=await records(db,warehouse_ids,kind,start,end,export=True,**filters)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = ("其他收入" if filters.get('category_group') == 'other' else "公司钱包收入") if kind == 'income' else "公司钱包支出"
    ws.append(["日期", "分类", "物品说明", "金额", "币种", "账户", "来源", "关联单号", "对象"])
    for r in result['data']:
        ws.append([r['date'],r['category_name'],r['remark'] or '',r['amount'],r['currency'],r.get('account_name',''),
            r['source_label'],r['ref_no'],r.get('customer_name') or r.get('supplier_name') or ''])
    transfers = await transfer_summary(db,warehouse_ids,start,end,**transfer_record_filters(filters))
    append_transfer_sheet(wb, transfers)
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": f"attachment; filename={'other_income' if kind == 'income' else 'wallet_expense'}.xlsx"})

# ==== Monthly Summary ====
@router.get("/monthly-summary", dependencies=[Depends(require_non_labor)])
async def monthly_summary(start_date: str = None, end_date: str = None, category_group: str = None,
                          month: str = None, year: str = None,
                          account_id: int = None, customer_id: int = None, supplier_id: int = None,
                          category_id: int = None, currency: str = None, source: str = None, search: str = None,
                          cost_category: str = None,
                          selected_ids: list[int] = Depends(selected_wallet_warehouses),
                         current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db),
                          _perm=Depends(check_staff_permission_any("运营收支", "其他收支"))):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    from app.services.money_records import summary
    from app.services.cost_funds_debt import dates
    start, end = dates(start_date, end_date, month=month, year=year)
    return await summary(db,selected_ids,start,end,category_group=category_group,
        category_id=category_id,account_id=account_id,customer_id=customer_id,supplier_id=supplier_id,
        currency=currency,source=source,search=search,cost_category=cost_category)
# ==== Operating Dashboard ====
@router.get("/operating-dashboard", dependencies=[Depends(require_non_labor)])
async def operating_dashboard(
    start_date: str = None,
    end_date: str = None,
    month: str = None, year: str = None,
    selected_ids: list[int] = Depends(selected_wallet_warehouses),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("运营收支")),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    from datetime import date, timedelta
    import calendar

    today = thai_today()

    start, end = money_period(month, start_date, end_date, year=year,
        default_start=today.replace(day=1), default_end=today)

    wh_ids = selected_ids
    from app.services.wallet import flow_query, grouped_totals
    from collections import defaultdict
    q = flow_query(db, wh_ids)
    rows = (await db.execute(select(q.c.date, q.c.currency, q.c.type, q.c.amount).where(
        q.c.date >= start, q.c.date <= end, q.c.status == "active", q.c.is_internal_transfer.is_(False)))).all()
    granularity = "day" if (end - start).days <= 31 else "month"
    grouped = defaultdict(lambda: defaultdict(float))
    total = defaultdict(float)
    for day, cur, kind, value in rows:
        label = day.isoformat() if granularity == "day" else day.strftime("%Y-%m")
        grouped[label][(cur, kind)] += float(value)
        total[(cur, kind)] += float(value)
    data, cursor = [], start
    while cursor <= end:
        label = cursor.isoformat() if granularity == "day" else cursor.strftime("%Y-%m")
        block = grouped_totals([(cur, kind, n) for (cur, kind), n in grouped[label].items()])
        data.append({"label": label, "recharge_income": block["total_income"],
            "operating_expense": block["total_expense"], **block})
        cursor = cursor + timedelta(days=1) if granularity == "day" else (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    result = grouped_totals([(cur, kind, n) for (cur, kind), n in total.items()])
    transfers = await transfer_summary(db, wh_ids, start, end)
    return {"internal_transfers": transfers, "data": data, "granularity": granularity, "start_date": start.isoformat(), "end_date": end.isoformat(),
        **result, "total_net": result["net"]}
