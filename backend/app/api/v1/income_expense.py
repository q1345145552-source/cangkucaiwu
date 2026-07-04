from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from app.database import get_db
from app.models.income_expense import IncomeRecord, ExpenseRecord, IncomeExpenseCategory, IncomeExpenseType, CategoryStatus
from app.models.customer import Customer, PaymentAccount
from app.models.supplier import Supplier
from app.models.user import User
from app.core.permissions import get_current_user, Role
from app.schemas.business import IncomeRecordCreate, ExpenseRecordCreate, CategoryCreate

router = APIRouter()

def get_wh_id(user: User) -> int:
    return user.warehouse_id if user.warehouse_id else 1

# ==== Categories ====
@router.get("/categories")
async def list_categories(type: str = None, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    query = select(IncomeExpenseCategory)
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(IncomeExpenseCategory.warehouse_id == current_user.warehouse_id)
    if type:
        query = query.where(IncomeExpenseCategory.type == type)
    result = await db.execute(query.order_by(IncomeExpenseCategory.sort_order))
    cats = result.scalars().all()
    return {"data": [{"id": c.id, "warehouse_id": c.warehouse_id, "type": c.type,
                      "name": c.name, "sort_order": c.sort_order, "status": c.status} for c in cats]}

@router.post("/categories")
async def create_category(req: CategoryCreate, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    c = IncomeExpenseCategory(warehouse_id=get_wh_id(current_user), **req.model_dump())
    db.add(c); await db.flush(); return {"id": c.id, "message": "创建成功"}

# ==== Income ====
@router.get("/income")
async def list_income(
    page: int = 1, page_size: int = 20, month: str = None,
    account_id: int = None, customer_id: int = None,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    query = select(IncomeRecord); count_q = select(func.count(IncomeRecord.id))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(IncomeRecord.warehouse_id == current_user.warehouse_id)
        count_q = count_q.where(IncomeRecord.warehouse_id == current_user.warehouse_id)
    if month:
        query = query.where(func.to_char(IncomeRecord.income_date, 'YYYY-MM') == month)
        count_q = count_q.where(func.to_char(IncomeRecord.income_date, 'YYYY-MM') == month)
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(query.order_by(IncomeRecord.income_date.desc()).offset((page-1)*page_size).limit(page_size))
    records = result.scalars().all()

    cat_ids = {r.category_id for r in records}
    acc_ids = {r.account_id for r in records}
    cust_ids = {r.customer_id for r in records if r.customer_id}
    cat_map = {}; acc_map = {}; cust_map = {}
    if cat_ids:
        cats = (await db.execute(select(IncomeExpenseCategory).where(IncomeExpenseCategory.id.in_(cat_ids)))).scalars().all()
        cat_map = {c.id: c.name for c in cats}
    if acc_ids:
        accs = (await db.execute(select(PaymentAccount).where(PaymentAccount.id.in_(acc_ids)))).scalars().all()
        acc_map = {a.id: a.account_name for a in accs}
    if cust_ids:
        custs = (await db.execute(select(Customer).where(Customer.id.in_(cust_ids)))).scalars().all()
        cust_map = {c.id: c.company_name for c in custs}

    return {"data": [{
        "id": r.id, "warehouse_id": r.warehouse_id, "category_id": r.category_id,
        "account_id": r.account_id, "customer_id": r.customer_id,
        "amount": r.amount, "currency": r.currency,
        "income_date": r.income_date.isoformat() if r.income_date else None,
        "voucher": r.voucher, "remark": r.remark,
        "category_name": cat_map.get(r.category_id, ""),
        "account_name": acc_map.get(r.account_id, ""),
        "customer_name": cust_map.get(r.customer_id, ""),
    } for r in records], "total": total, "page": page, "page_size": page_size}

@router.post("/income")
async def create_income(req: IncomeRecordCreate, current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    r = IncomeRecord(
        warehouse_id=get_wh_id(current_user), category_id=req.category_id,
        account_id=req.account_id, customer_id=req.customer_id,
        amount=req.amount, currency=req.currency,
        income_date=datetime.fromisoformat(req.income_date),
        voucher=req.voucher, remark=req.remark, confirmed_by=current_user.id,
    )
    db.add(r); await db.flush(); return {"id": r.id, "message": "收款记录创建成功"}

# ==== Expense ====
@router.get("/expense")
async def list_expense(
    page: int = 1, page_size: int = 20, month: str = None,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    query = select(ExpenseRecord); count_q = select(func.count(ExpenseRecord.id))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(ExpenseRecord.warehouse_id == current_user.warehouse_id)
        count_q = count_q.where(ExpenseRecord.warehouse_id == current_user.warehouse_id)
    if month:
        query = query.where(func.to_char(ExpenseRecord.expense_date, 'YYYY-MM') == month)
        count_q = count_q.where(func.to_char(ExpenseRecord.expense_date, 'YYYY-MM') == month)
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(query.order_by(ExpenseRecord.expense_date.desc()).offset((page-1)*page_size).limit(page_size))
    records = result.scalars().all()

    cat_ids = {r.category_id for r in records}
    acc_ids = {r.account_id for r in records}
    sup_ids = {r.supplier_id for r in records if r.supplier_id}
    cat_map = {}; acc_map = {}; sup_map = {}
    if cat_ids:
        cats = (await db.execute(select(IncomeExpenseCategory).where(IncomeExpenseCategory.id.in_(cat_ids)))).scalars().all()
        cat_map = {c.id: c.name for c in cats}
    if acc_ids:
        accs = (await db.execute(select(PaymentAccount).where(PaymentAccount.id.in_(acc_ids)))).scalars().all()
        acc_map = {a.id: a.account_name for a in accs}
    if sup_ids:
        sups = (await db.execute(select(Supplier).where(Supplier.id.in_(sup_ids)))).scalars().all()
        sup_map = {s.id: s.name for s in sups}

    return {"data": [{
        "id": r.id, "warehouse_id": r.warehouse_id, "category_id": r.category_id,
        "account_id": r.account_id, "supplier_id": r.supplier_id,
        "amount": r.amount, "currency": r.currency,
        "expense_date": r.expense_date.isoformat() if r.expense_date else None,
        "voucher": r.voucher, "remark": r.remark,
        "category_name": cat_map.get(r.category_id, ""),
        "account_name": acc_map.get(r.account_id, ""),
        "supplier_name": sup_map.get(r.supplier_id, ""),
    } for r in records], "total": total, "page": page, "page_size": page_size}

@router.post("/expense")
async def create_expense(req: ExpenseRecordCreate, current_user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    r = ExpenseRecord(
        warehouse_id=get_wh_id(current_user), category_id=req.category_id,
        account_id=req.account_id, supplier_id=req.supplier_id,
        amount=req.amount, currency=req.currency,
        expense_date=datetime.fromisoformat(req.expense_date),
        voucher=req.voucher, remark=req.remark, approved_by=current_user.id,
    )
    db.add(r); await db.flush(); return {"id": r.id, "message": "付款记录创建成功"}

# ==== Ledger ====
@router.get("/ledger")
async def ledger(page: int = 1, page_size: int = 20, month: str = None,
                 current_user: User = Depends(get_current_user),
                 db: AsyncSession = Depends(get_db)):
    results = []
    iq = select(IncomeRecord); eq = select(ExpenseRecord)
    if current_user.role != Role.SUPER_ADMIN:
        iq = iq.where(IncomeRecord.warehouse_id == current_user.warehouse_id)
        eq = eq.where(ExpenseRecord.warehouse_id == current_user.warehouse_id)
    if month:
        iq = iq.where(func.to_char(IncomeRecord.income_date, 'YYYY-MM') == month)
        eq = eq.where(func.to_char(ExpenseRecord.expense_date, 'YYYY-MM') == month)
    incomes = (await db.execute(iq)).scalars().all()
    expenses = (await db.execute(eq)).scalars().all()
    for r in incomes:
        results.append({"type": "income", "date": r.income_date.isoformat() if r.income_date else "",
                       "amount": r.amount, "currency": r.currency, "remark": r.remark, "id": r.id})
    for r in expenses:
        results.append({"type": "expense", "date": r.expense_date.isoformat() if r.expense_date else "",
                       "amount": r.amount, "currency": r.currency, "remark": r.remark, "id": r.id})
    results.sort(key=lambda x: x["date"], reverse=True)
    total = len(results)
    return {"data": results[(page-1)*page_size:page*page_size], "total": total, "page": page, "page_size": page_size}

# ==== Monthly Summary ====
@router.get("/monthly-summary")
async def monthly_summary(month: str, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    iq = select(func.sum(IncomeRecord.amount)).where(func.to_char(IncomeRecord.income_date, 'YYYY-MM') == month)
    eq = select(func.sum(ExpenseRecord.amount)).where(func.to_char(ExpenseRecord.expense_date, 'YYYY-MM') == month)
    if current_user.role != Role.SUPER_ADMIN:
        iq = iq.where(IncomeRecord.warehouse_id == current_user.warehouse_id)
        eq = eq.where(ExpenseRecord.warehouse_id == current_user.warehouse_id)
    ti = (await db.execute(iq)).scalar() or 0
    te = (await db.execute(eq)).scalar() or 0
    return {"month": month, "total_income": float(ti), "total_expense": float(te), "net": float(ti - te)}
