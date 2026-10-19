"""员工预支与现有运营支出共用调用方事务，不参与工资抵扣。"""
from datetime import datetime, time

from fastapi import HTTPException
from sqlalchemy import select, text

from app.models.employee import Employee
from app.models.employee_advance import EmployeeAdvance, AdvanceApprovalStatus
from app.models.expense_fund import ExpenseFundItem
from app.models.income_expense import ExpenseRecord, IncomeExpenseCategory
from app.models.warehouse import Warehouse
from app.services.data_history import record_history

ADVANCE_EXPENSE_CATEGORY = "员工预支"


async def backfill_advance_categories(conn):
    """只补每仓分类，绝不补历史预支的成本。"""
    result = await conn.execute(text("""
        INSERT INTO income_expense_categories
            (warehouse_id, type, name, category_group, status, sort_order)
        SELECT w.id, 'expense', CAST(:name AS VARCHAR), 'operating', 'active', 110
        FROM warehouses w
        WHERE NOT EXISTS (
            SELECT 1 FROM income_expense_categories c
            WHERE c.warehouse_id = w.id AND c.type = 'expense'
              AND c.category_group = 'operating' AND c.name = CAST(:name AS VARCHAR)
        )
    """), {"name": ADVANCE_EXPENSE_CATEGORY})
    return result.rowcount


async def create_advance_expense(db, advance, operator, *, paid_at=None):
    if not advance.expense_tracking_enabled or advance.approval_status != AdvanceApprovalStatus.APPROVED.value:
        return None
    if advance.funding_source in ("cash_advance", "expense_fund"):
        return None
    if advance.expense_record_id is not None:
        raise HTTPException(400, "该预支已记入运营支出")
    employee = (await db.execute(select(Employee).where(
        Employee.id == advance.employee_id, Employee.warehouse_id == advance.warehouse_id,
    ))).scalar_one_or_none()
    if employee is None:
        raise HTTPException(400, "预支员工不存在或不属于当前仓库")
    # 同仓新分类的懒创建串行化，避免并发新预支建出同名分类。
    await db.execute(select(Warehouse.id).where(Warehouse.id == advance.warehouse_id).with_for_update())
    category = (await db.execute(select(IncomeExpenseCategory).where(
        IncomeExpenseCategory.warehouse_id == advance.warehouse_id,
        IncomeExpenseCategory.type == "expense", IncomeExpenseCategory.category_group == "operating",
        IncomeExpenseCategory.name == ADVANCE_EXPENSE_CATEGORY,
    ).order_by(IncomeExpenseCategory.id).limit(1))).scalar_one_or_none()
    # 新仓在启动之后创建时，也可沿用同一分类体系，不依赖固定编号。
    if category is None:
        category = IncomeExpenseCategory(warehouse_id=advance.warehouse_id, type="expense",
            category_group="operating", name=ADVANCE_EXPENSE_CATEGORY, status="active", sort_order=110)
        db.add(category)
        await db.flush()
    if category.status != "active":
        raise HTTPException(400, "员工预支支出分类已停用")
    expense = ExpenseRecord(warehouse_id=advance.warehouse_id, category_id=category.id,
        account_id=advance.payment_account_id if advance.funding_source == "company_account" else None,
        amount=advance.amount, currency=advance.currency or "THB",
        expense_date=(paid_at.replace(tzinfo=None) if paid_at else datetime.combine(advance.advance_date, time.min)),
        remark=f"{employee.name} 预支（预支单 #{advance.id}）", approved_by=operator.id)
    db.add(expense)
    await db.flush()
    advance.expense_record_id = expense.id
    await record_history(db, module="expense", record_id=expense.id, operator=operator,
        operation_type="create", after={"employee_advance_id": advance.id,
            "employee_id": advance.employee_id, "amount": expense.amount, "currency": expense.currency,
            "expense_date": expense.expense_date.isoformat(), "remark": expense.remark},
        warehouse_id=advance.warehouse_id)
    return expense


async def delete_advance_expense(db, advance, operator, *, reason=None):
    """作废预支时删除精确关联的成本并留痕，不猜补历史关联。"""
    if not advance.expense_tracking_enabled and advance.expense_record_id is None and advance.fund_item_id is None:
        return
    if advance.expense_record_id is not None:
        expense = (await db.execute(select(ExpenseRecord).where(
            ExpenseRecord.id == advance.expense_record_id, ExpenseRecord.warehouse_id == advance.warehouse_id,
        ).with_for_update())).scalar_one_or_none()
        if expense is None:
            raise HTTPException(400, "关联预支支出不存在，请先核对")
        await record_history(db, module="expense", record_id=expense.id, operator=operator,
            operation_type="delete", before={"employee_advance_id": advance.id,
                "employee_id": advance.employee_id, "amount": expense.amount, "currency": expense.currency,
                "remark": expense.remark}, after={"reason": reason or "删除预支时同时删除关联支出"},
            warehouse_id=advance.warehouse_id)
        advance.expense_record_id = None
        await db.flush()
        await db.delete(expense)
    # 只处理本轮新建且精确关联的备用金开销，避免删除预支后又浮现成一笔成本。
    if advance.fund_item_id is not None:
        from app.models.expense_fund import ExpenseFund
        item = (await db.execute(select(ExpenseFundItem).join(ExpenseFund).where(
            ExpenseFundItem.id == advance.fund_item_id, ExpenseFund.warehouse_id == advance.warehouse_id,
            ExpenseFundItem.fund_id == advance.fund_account_id,
        ).with_for_update())).scalar_one_or_none()
        if item is None:
            raise HTTPException(400, "关联预支备用金开销不存在，请先核对")
        advance.fund_item_id = None
        await db.flush()
        await db.delete(item)


async def require_manual_advance_expense(db, expense_id):
    if (await db.execute(select(EmployeeAdvance.id).where(
        EmployeeAdvance.expense_record_id == expense_id,
    ).limit(1))).first():
        raise HTTPException(400, "预支联动支出请在员工预支模块处理")
