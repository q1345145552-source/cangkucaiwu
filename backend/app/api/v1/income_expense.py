from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime
from app.database import get_db
from app.models.income_expense import IncomeRecord, ExpenseRecord, IncomeExpenseCategory, IncomeExpenseType, CategoryStatus
from app.models.customer import Customer, PaymentAccount
from app.models.supplier import Supplier
from app.models.user import User
from app.core.permissions import get_current_user, Role, check_staff_permission
from app.schemas.business import IncomeRecordCreate, ExpenseRecordCreate, CategoryCreate

OPERATING_NAMES = ["仓储费", "操作费", "增值服务费", "工资", "电费", "网费", "房租", "耗材", "物流运费", "快递费", "保险费", "税费"]

router = APIRouter()

def get_wh_id(user: User) -> int:
    return user.warehouse_id if user.warehouse_id else 1

# ==== Categories ====
@router.get("/categories")
async def list_categories(type: str = None, category_group: str = None, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(IncomeExpenseCategory)
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(IncomeExpenseCategory.warehouse_id == current_user.warehouse_id)
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
                          db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN):
        raise HTTPException(403, "无权限")
    # 自动归类：运营类 vs 其他
    from app.api.v1.income_expense import OPERATING_NAMES
    category_group = "operating" if req.name in OPERATING_NAMES else "other"
    c = IncomeExpenseCategory(warehouse_id=get_wh_id(current_user), category_group=category_group, **req.model_dump())
    db.add(c); await db.flush(); return {"id": c.id, "message": "创建成功"}

# ==== Income ====
@router.get("/income")
async def list_income(
    page: int = 1, page_size: int = 20, month: str = None,
    account_id: int = None, customer_id: int = None,
    category_id: int = None,
    category_group: str = None,
    currency: str = None,
    search: str = None,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(IncomeRecord); count_q = select(func.count(IncomeRecord.id))
    if category_group:
        query = query.join(IncomeExpenseCategory, IncomeRecord.category_id == IncomeExpenseCategory.id)
        query = query.where(IncomeExpenseCategory.category_group == category_group)
        count_q = count_q.join(IncomeExpenseCategory, IncomeRecord.category_id == IncomeExpenseCategory.id)
        count_q = count_q.where(IncomeExpenseCategory.category_group == category_group)
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(IncomeRecord.warehouse_id == current_user.warehouse_id)
        count_q = count_q.where(IncomeRecord.warehouse_id == current_user.warehouse_id)
    if month:
        query = query.where(func.to_char(IncomeRecord.income_date, 'YYYY-MM') == month)
        count_q = count_q.where(func.to_char(IncomeRecord.income_date, 'YYYY-MM') == month)
    if account_id:
        query = query.where(IncomeRecord.account_id == account_id)
        count_q = count_q.where(IncomeRecord.account_id == account_id)
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
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role == Role.STAFF and "收付款管理" not in (current_user.extra_permissions or []):
        raise HTTPException(403, "无确认入账权限")
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

# ==== Income Edit / Delete ====
@router.put("/income/{income_id}")
async def update_income(income_id: int, req: IncomeRecordCreate, current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    r = (await db.execute(select(IncomeRecord).where(IncomeRecord.id == income_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "记录不存在")
    if current_user.role != Role.SUPER_ADMIN and r.warehouse_id != current_user.warehouse_id:
        raise HTTPException(403, "无权限")
    r.category_id = req.category_id
    r.account_id = req.account_id
    r.amount = req.amount
    r.currency = req.currency
    r.income_date = datetime.fromisoformat(req.income_date)
    r.remark = req.remark
    await db.flush()
    return {"message": "更新成功"}

@router.delete("/income/{income_id}")
async def delete_income(income_id: int, current_user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    r = (await db.execute(select(IncomeRecord).where(IncomeRecord.id == income_id))).scalar_one_or_none()
    if not r:
        raise HTTPException(404, "记录不存在")
    if current_user.role != Role.SUPER_ADMIN and r.warehouse_id != current_user.warehouse_id:
        raise HTTPException(403, "无权限")
    await db.delete(r)
    await db.flush()
    return {"message": "删除成功"}


# ==== Expense ====
@router.get("/expense")
async def list_expense(
    page: int = 1, page_size: int = 20, month: str = None,
    category_id: int = None, account_id: int = None,
    start_date: str = None, end_date: str = None,
    category_group: str = None,
    currency: str = None,
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(ExpenseRecord); count_q = select(func.count(ExpenseRecord.id))
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(ExpenseRecord.warehouse_id == current_user.warehouse_id)
        count_q = count_q.where(ExpenseRecord.warehouse_id == current_user.warehouse_id)
    if month:
        query = query.where(func.to_char(ExpenseRecord.expense_date, 'YYYY-MM') == month)
        count_q = count_q.where(func.to_char(ExpenseRecord.expense_date, 'YYYY-MM') == month)
    if category_id:
        query = query.where(ExpenseRecord.category_id == category_id)
        count_q = count_q.where(ExpenseRecord.category_id == category_id)
    if account_id:
        query = query.where(ExpenseRecord.account_id == account_id)
        count_q = count_q.where(ExpenseRecord.account_id == account_id)
    if start_date:
        query = query.where(ExpenseRecord.expense_date >= datetime.strptime(start_date, "%Y-%m-%d"))
        count_q = count_q.where(ExpenseRecord.expense_date >= datetime.strptime(start_date, "%Y-%m-%d"))
    if end_date:
        query = query.where(ExpenseRecord.expense_date <= datetime.strptime(end_date, "%Y-%m-%d"))
        count_q = count_q.where(ExpenseRecord.expense_date <= datetime.strptime(end_date, "%Y-%m-%d"))
    if currency:
        query = query.where(ExpenseRecord.currency == currency)
        count_q = count_q.where(ExpenseRecord.currency == currency)
    if category_group:
        query = query.join(IncomeExpenseCategory, ExpenseRecord.category_id == IncomeExpenseCategory.id)
        query = query.where(IncomeExpenseCategory.category_group == category_group)
        count_q = count_q.join(IncomeExpenseCategory, ExpenseRecord.category_id == IncomeExpenseCategory.id)
        count_q = count_q.where(IncomeExpenseCategory.category_group == category_group)
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
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role == Role.STAFF and "收付款管理" not in (current_user.extra_permissions or []):
        raise HTTPException(403, "无确认出账权限")
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
async def ledger(
    page: int = 1, page_size: int = 30,
    month: str = None,
    source: str = None,
    flow_type: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    wh_id = current_user.warehouse_id
    results = []

    # Helper: build warehouse+month filter
    def apply_month(q, col, model):
        q = q.where(model.warehouse_id == wh_id)
        if month:
            q = q.where(func.to_char(col, 'YYYY-MM') == month)
        return q

    from app.models.recharge import RechargeDeclaration, IncomingFlow
    from app.models.expense_fund import ExpenseFund, ExpenseFundItem
    from app.models.reimbursement import Reimbursement
    from app.models.payable import PayableBill
    from app.models.customer import Customer

    # 1. 充值申报
    if not source or source == "recharge":
        q = apply_month(select(RechargeDeclaration), RechargeDeclaration.declare_date, RechargeDeclaration)
        recharges = (await db.execute(q.order_by(RechargeDeclaration.declare_date.desc()))).scalars().all()
        cust_ids = list(set(r.customer_id for r in recharges if r.customer_id))
        cust_map = {}
        if cust_ids:
            custs = (await db.execute(select(Customer).where(Customer.id.in_(cust_ids)))).scalars().all()
            cust_map = {c.id: c.company_name for c in custs}
        for r in recharges:
            results.append({
                "date": r.declare_date.isoformat()[:10] if r.declare_date else "",
                "amount": r.amount, "currency": r.currency or "THB",
                "type": "income", "source": "recharge", "source_label": "充值申报",
                "remark": f"客户: {cust_map.get(r.customer_id, '')}" if r.customer_id else "充值",
                "ref_no": f"RC-{r.id}",
                "id": r.id,
            })

    # 2. 到账流水
    if not source or source == "incoming":
        q = apply_month(select(IncomingFlow), IncomingFlow.received_date, IncomingFlow)
        flows = (await db.execute(q.order_by(IncomingFlow.received_date.desc()))).scalars().all()
        for r in flows:
            results.append({
                "date": r.received_date.isoformat()[:10] if r.received_date else "",
                "amount": r.amount, "currency": r.currency or "THB",
                "type": "income", "source": "incoming", "source_label": "到账流水",
                "remark": f"付款方: {r.payer_name or ''}" + (f" ({r.payment_method})" if r.payment_method else ""),
                "ref_no": f"FL-{r.id}",
                "id": r.id,
            })

    # 3. 备用金领用（top-up 记录）
    if not source or source == "expense_fund":
        q = apply_month(select(ExpenseFund).where(ExpenseFund.amount > 0), ExpenseFund.receive_date, ExpenseFund)
        funds = (await db.execute(q.order_by(ExpenseFund.receive_date.desc()))).scalars().all()
        emp_ids = list(set(f.employee_id for f in funds))
        emp_map = {}
        if emp_ids:
            emps = (await db.execute(select(User).where(User.id.in_(emp_ids)))).scalars().all()
            emp_map = {e.id: e.display_name for e in emps}
        for r in funds:
            results.append({
                "date": r.receive_date.isoformat()[:10] if r.receive_date else "",
                "amount": r.amount or 0, "currency": "THB",
                "type": "expense", "source": "expense_fund", "source_label": "备用金领用",
                "remark": f"领用人: {emp_map.get(r.employee_id, '')} ({r.purpose or ''})",
                "ref_no": f"EF-{r.id}",
                "id": r.id,
            })

    # 4. 备用金开销
    if not source or source == "fund_item":
        q = select(ExpenseFundItem).join(ExpenseFund, ExpenseFundItem.fund_id == ExpenseFund.id)
        q = q.where(ExpenseFund.warehouse_id == wh_id)
        if month:
            q = q.where(func.to_char(ExpenseFundItem.expense_date, 'YYYY-MM') == month)
        items = (await db.execute(q.order_by(ExpenseFundItem.expense_date.desc()))).scalars().all()
        fund_ids = list(set(it.fund_id for it in items))
        fund_map = {}
        if fund_ids:
            fds = (await db.execute(select(ExpenseFund).where(ExpenseFund.id.in_(fund_ids)))).scalars().all()
            emp_ids2 = list(set(f.employee_id for f in fds))
            emp_map2 = {}
            if emp_ids2:
                emps2 = (await db.execute(select(User).where(User.id.in_(emp_ids2)))).scalars().all()
                emp_map2 = {e.id: e.display_name for e in emps2}
            fund_map = {f.id: (f, emp_map2.get(f.employee_id, "")) for f in fds}
        for r in items:
            f, ename = fund_map.get(r.fund_id, (None, ""))
            results.append({
                "date": r.expense_date.isoformat()[:10] if r.expense_date else "",
                "amount": r.amount, "currency": r.currency or "THB",
                "type": "expense", "source": "fund_item", "source_label": "备用金开销",
                "remark": f"{ename}: {r.category} - {r.description or ''}",
                "ref_no": f"FI-{r.id}",
                "id": r.id,
            })

    # 5. 报销出款（已付款）
    if not source or source == "reimbursement":
        q = apply_month(select(Reimbursement).where(Reimbursement.status == "paid"), Reimbursement.paid_at, Reimbursement)
        # paid_at might be None for some records, fallback to submit_date
        reimbs = (await db.execute(q.order_by(Reimbursement.paid_at.desc().nulls_last()))).scalars().all()
        emp_ids3 = list(set(r.employee_id for r in reimbs))
        emp_map3 = {}
        if emp_ids3:
            emps3 = (await db.execute(select(User).where(User.id.in_(emp_ids3)))).scalars().all()
            emp_map3 = {e.id: e.display_name for e in emps3}
        for r in reimbs:
            d = r.paid_at or r.submit_date
            results.append({
                "date": d.isoformat()[:10] if d else "",
                "amount": r.total_amount or 0, "currency": r.currency or "THB",
                "type": "expense", "source": "reimbursement", "source_label": "报销",
                "remark": f"报销人: {emp_map3.get(r.employee_id, '')}",
                "ref_no": f"RB-{r.id}",
                "id": r.id,
            })

    # 6. 应付账款付款
    if not source or source == "payable":
        q = apply_month(select(PayableBill).where(PayableBill.paid_amount > 0), PayableBill.paid_at, PayableBill)
        bills = (await db.execute(q.order_by(PayableBill.paid_at.desc().nulls_last()))).scalars().all()
        for r in bills:
            d = r.paid_at or r.bill_date
            results.append({
                "date": d.isoformat()[:10] if d else "",
                "amount": r.paid_amount or 0, "currency": r.currency or "THB",
                "type": "expense", "source": "payable", "source_label": "应付账款",
                "remark": f"账单: {r.bill_number or ''}" + (f" ({r.remark})" if r.remark else ""),
                "ref_no": f"PB-{r.id}",
                "id": r.id,
            })

    # 7. 手工收支
    if not source or source == "manual":
        iq = apply_month(select(IncomeRecord), IncomeRecord.income_date, IncomeRecord)
        eq = apply_month(select(ExpenseRecord), ExpenseRecord.expense_date, ExpenseRecord)
        incomes = (await db.execute(iq.order_by(IncomeRecord.income_date.desc()))).scalars().all()
        expenses = (await db.execute(eq.order_by(ExpenseRecord.expense_date.desc()))).scalars().all()

        # resolve category names
        cat_ids = set()
        for r in incomes: cat_ids.add(r.category_id)
        for r in expenses: cat_ids.add(r.category_id)
        cat_map = {}
        if cat_ids:
            cats = (await db.execute(select(IncomeExpenseCategory).where(IncomeExpenseCategory.id.in_(cat_ids)))).scalars().all()
            cat_map = {c.id: c.name for c in cats}

        for r in incomes:
            results.append({
                "date": r.income_date.isoformat()[:10] if r.income_date else "",
                "amount": r.amount, "currency": r.currency or "THB",
                "type": "income", "source": "manual", "source_label": "手工收支",
                "remark": f"{cat_map.get(r.category_id, '')}" + (f" - {r.remark}" if r.remark else ""),
                "ref_no": f"IN-{r.id}",
                "id": r.id,
            })
        for r in expenses:
            results.append({
                "date": r.expense_date.isoformat()[:10] if r.expense_date else "",
                "amount": r.amount, "currency": r.currency or "THB",
                "type": "expense", "source": "manual", "source_label": "手工收支",
                "remark": f"{cat_map.get(r.category_id, '')}" + (f" - {r.remark}" if r.remark else ""),
                "ref_no": f"EX-{r.id}",
                "id": r.id,
            })

    # filter by type
    if flow_type == "income":
        results = [r for r in results if r["type"] == "income"]
    elif flow_type == "expense":
        results = [r for r in results if r["type"] == "expense"]

    # sort by date descending
    results.sort(key=lambda x: x["date"] or "", reverse=True)

    # compute summary for current month
    today = __import__('datetime').date.today()
    cur_month = f"{today.year}-{today.month:02d}"
    total_income = sum(r["amount"] for r in results if r["type"] == "income")
    total_expense = sum(r["amount"] for r in results if r["type"] == "expense")
    # If filtered by month, use that; if showing all, compute only current month for cards
    if month:
        card_income = total_income
        card_expense = total_expense
    else:
        # For the cards, we always show current month regardless of filter
        card_income = sum(r["amount"] for r in results if r["type"] == "income" and (r["date"] or "").startswith(cur_month[:7]))
        card_expense = sum(r["amount"] for r in results if r["type"] == "expense" and (r["date"] or "").startswith(cur_month[:7]))

    total_all = len(results)
    start_idx = (page - 1) * page_size
    paged = results[start_idx:start_idx + page_size]

    return {
        "data": paged, "total": total_all, "page": page, "page_size": page_size,
        "total_income": total_income, "total_expense": total_expense,
        "net": total_income - total_expense,
        "card_income": card_income, "card_expense": card_expense,
        "card_net": card_income - card_expense,
    }


# ==== Ledger Export ====
@router.get("/ledger/export")
async def ledger_export(
    month: str = None, source: str = None, flow_type: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    # Reuse same aggregation logic
    r = await ledger(page=1, page_size=99999, month=month, source=source, flow_type=flow_type, current_user=current_user, db=db)
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
    output = __import__('io').BytesIO(); wb.save(output); output.seek(0)
    filename = f"ledger_{month or 'all'}.xlsx"
    return __import__('fastapi').responses.StreamingResponse(
        output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ==== Income Export ====
@router.get("/income/export")
async def export_income(
    month: str = None,
    category_group: str = None,
    currency: str = None,
    search: str = None,
    category_id: int = None,
    start_date: str = None,
    end_date: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(IncomeRecord)
    if current_user.role != Role.SUPER_ADMIN:
        query = query.where(IncomeRecord.warehouse_id == current_user.warehouse_id)
    if month:
        query = query.where(func.to_char(IncomeRecord.income_date, 'YYYY-MM') == month)
    if category_group:
        query = query.join(IncomeExpenseCategory, IncomeRecord.category_id == IncomeExpenseCategory.id)
        query = query.where(IncomeExpenseCategory.category_group == category_group)
    if currency:
        query = query.where(IncomeRecord.currency == currency)
    if search:
        query = query.where(IncomeRecord.remark.ilike(f"%{search}%"))
    if category_id:
        query = query.where(IncomeRecord.category_id == category_id)
    if start_date:
        query = query.where(IncomeRecord.income_date >= datetime.strptime(start_date, "%Y-%m-%d"))
    if end_date:
        query = query.where(IncomeRecord.income_date <= datetime.strptime(end_date, "%Y-%m-%d"))
    result = await db.execute(query.order_by(IncomeRecord.income_date.desc()))
    records = result.scalars().all()

    cat_ids = {r.category_id for r in records}
    acc_ids = {r.account_id for r in records}
    cat_map = {}; acc_map = {}
    if cat_ids:
        cats = (await db.execute(select(IncomeExpenseCategory).where(IncomeExpenseCategory.id.in_(cat_ids)))).scalars().all()
        cat_map = {c.id: c.name for c in cats}
    if acc_ids:
        accs = (await db.execute(select(PaymentAccount).where(PaymentAccount.id.in_(acc_ids)))).scalars().all()
        acc_map = {a.id: a.account_name for a in accs}

    from fastapi.responses import StreamingResponse
    import openpyxl
    from io import BytesIO

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "其他收入"
    ws.append(["日期", "分类", "物品说明", "金额", "币种", "账户"])
    for r in records:
        ws.append([
            r.income_date.strftime("%Y-%m-%d") if r.income_date else "",
            cat_map.get(r.category_id, ""),
            r.remark or "",
            r.amount,
            r.currency,
            acc_map.get(r.account_id, ""),
        ])
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": "attachment; filename=other_income.xlsx"})

# ==== Monthly Summary ====
@router.get("/monthly-summary")
async def monthly_summary(month: str, category_group: str = None, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    iq = select(func.sum(IncomeRecord.amount)).where(func.to_char(IncomeRecord.income_date, 'YYYY-MM') == month)
    eq = select(func.sum(ExpenseRecord.amount)).where(func.to_char(ExpenseRecord.expense_date, 'YYYY-MM') == month)
    if category_group:
        iq = iq.join(IncomeExpenseCategory, IncomeRecord.category_id == IncomeExpenseCategory.id).where(IncomeExpenseCategory.category_group == category_group)
        eq = eq.join(IncomeExpenseCategory, ExpenseRecord.category_id == IncomeExpenseCategory.id).where(IncomeExpenseCategory.category_group == category_group)
    if current_user.role != Role.SUPER_ADMIN:
        iq = iq.where(IncomeRecord.warehouse_id == current_user.warehouse_id)
        eq = eq.where(ExpenseRecord.warehouse_id == current_user.warehouse_id)
    ti = (await db.execute(iq)).scalar() or 0
    te = (await db.execute(eq)).scalar() or 0
    return {"month": month, "total_income": float(ti), "total_expense": float(te), "net": float(ti - te)}
# ==== Operating Dashboard ====
@router.get("/operating-dashboard")
async def operating_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    from datetime import date, timedelta
    import calendar

    today = date.today()
    months_list = []
    for i in range(11, -1, -1):
        m = today.month - i; y = today.year
        if m <= 0: m += 12; y -= 1
        months_list.append(f"{y}-{m:02d}")

    # Monthly recharge totals (income)
    from app.models.recharge import RechargeDeclaration
    recharge_map = {}
    for month in months_list:
        m_start = f"{month}-01"
        last_day = calendar.monthrange(int(month[:4]), int(month[5:]))[1]
        m_end = f"{month}-{last_day:02d}"
        q = select(func.coalesce(func.sum(RechargeDeclaration.amount), 0)).where(
            RechargeDeclaration.warehouse_id == current_user.warehouse_id,
            func.to_char(RechargeDeclaration.declare_date, 'YYYY-MM') == month,
        )
        total = float((await db.execute(q)).scalar() or 0)
        recharge_map[month] = total

    # Monthly operating expense totals
    expense_map = {}
    for month in months_list:
        m_start = f"{month}-01"
        last_day = calendar.monthrange(int(month[:4]), int(month[5:]))[1]
        m_end = f"{month}-{last_day:02d}"
        q = select(func.coalesce(func.sum(ExpenseRecord.amount), 0)).where(
            ExpenseRecord.warehouse_id == current_user.warehouse_id,
            func.to_char(ExpenseRecord.expense_date, 'YYYY-MM') == month,
        )
        # Join to filter only operating categories
        q = q.join(IncomeExpenseCategory, ExpenseRecord.category_id == IncomeExpenseCategory.id)
        q = q.where(IncomeExpenseCategory.category_group == "operating")
        total = float((await db.execute(q)).scalar() or 0)
        expense_map[month] = total

    data = []
    for month in months_list:
        income = recharge_map.get(month, 0)
        expense = expense_map.get(month, 0)
        data.append({
            "month": month,
            "recharge_income": income,
            "operating_expense": expense,
            "net": income - expense,
        })

    cur_month = f"{today.year}-{today.month:02d}"
    cur_income = recharge_map.get(cur_month, 0)
    cur_expense = expense_map.get(cur_month, 0)

    return {
        "data": data,
        "current_month": cur_month,
        "current_income": cur_income,
        "current_expense": cur_expense,
        "current_net": cur_income - cur_expense,
    }

