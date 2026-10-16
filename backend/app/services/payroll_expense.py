"""Payroll disbursement and operating expense share the caller's transaction."""
from decimal import Decimal, InvalidOperation
from fastapi import HTTPException
from sqlalchemy import select, text
from app.models.customer import PaymentAccount
from app.models.income_expense import ExpenseRecord, IncomeExpenseCategory
from app.models.payroll import PayrollRecord
from app.models.warehouse import Warehouse
from app.services.data_history import record_history

PAYROLL_EXPENSE_CATEGORY = "员工工资"


async def backfill_payroll_categories(conn):
    """Startup backfill for every existing warehouse; never backfill expenses."""
    result = await conn.execute(text("""
        INSERT INTO income_expense_categories
            (warehouse_id, type, name, category_group, status, sort_order)
        SELECT w.id, 'expense', CAST(:name AS VARCHAR), 'operating', 'active', 100
        FROM warehouses w
        WHERE NOT EXISTS (
            SELECT 1 FROM income_expense_categories c
            WHERE c.warehouse_id = w.id AND c.type = 'expense'
              AND c.category_group = 'operating' AND c.name = CAST(:name AS VARCHAR)
        )
    """), {"name": PAYROLL_EXPENSE_CATEGORY})
    return result.rowcount


async def payment_account(db, warehouse_id, account_id):
    if not account_id:
        raise HTTPException(400, "请选择工资发放账户")
    account = (await db.execute(select(PaymentAccount).where(
        PaymentAccount.id == account_id, PaymentAccount.warehouse_id == warehouse_id,
    ).with_for_update())).scalar_one_or_none()
    if account is None:
        raise HTTPException(400, "发放账户不存在或不属于当前仓库")
    if account.status not in (None, "active"):
        raise HTTPException(400, "发放账户已停用")
    if (account.currency or "THB").upper() != "THB":
        raise HTTPException(400, "工资以泰铢发放，请选择泰铢账户")
    return account


def expense_amount(record):
    try:
        amount = Decimal(str(record.net_pay))
        if not amount.is_finite() or amount < 0 or amount != amount.quantize(Decimal("0.01")):
            raise ValueError
    except (InvalidOperation, ValueError):
        raise HTTPException(400, "工资实发金额无效，请先核对工资单")
    return float(amount)


def period_label(record):
    if record.settle_start_date and record.settle_end_date:
        return f"{record.settle_start_date:%m-%d}到{record.settle_end_date:%m-%d}"
    return f"{record.period} {'上半月' if record.half == 'first_half' else '下半月'}"


async def create_payroll_expense(db, record, account, operator, now):
    if record.expense_record_id is not None:
        raise HTTPException(400, "工资单已关联支出，请先核对")
    amount = expense_amount(record)
    category = (await db.execute(select(IncomeExpenseCategory).where(
        IncomeExpenseCategory.warehouse_id == record.warehouse_id,
        IncomeExpenseCategory.type == "expense",
        IncomeExpenseCategory.category_group == "operating",
        IncomeExpenseCategory.name == PAYROLL_EXPENSE_CATEGORY,
    ).order_by(IncomeExpenseCategory.id).limit(1))).scalar_one_or_none()
    if category is None:
        raise HTTPException(400, "缺少员工工资支出分类，请先完成启动迁移")
    if category.status != "active":
        raise HTTPException(400, "员工工资支出分类已停用")
    warehouse = await db.get(Warehouse, record.warehouse_id)
    expense = ExpenseRecord(
        warehouse_id=record.warehouse_id, category_id=category.id, account_id=account.id,
        amount=amount, currency="THB", expense_date=now.replace(tzinfo=None),
        remark=f"{warehouse.name} {period_label(record)} 1人", approved_by=operator.id,
    )
    db.add(expense)
    await db.flush()
    record.expense_record_id = expense.id
    record.disbursed = True
    record.disbursed_at = now
    record.disbursed_by = operator.id
    await record_history(db, module="expense", record_id=expense.id, operator=operator,
        operation_type="create", after={"payroll_record_id": record.id, "amount": amount,
        "account_id": account.id, "remark": expense.remark}, warehouse_id=record.warehouse_id)
    return expense


async def reverse_payroll_expense(db, record, operator):
    """Delete the linked expense, retaining its values and reason in history."""
    expense_id = record.expense_record_id
    if expense_id is None:  # Historical disbursement: do not manufacture an expense.
        return None
    expense = (await db.execute(select(ExpenseRecord).where(
        ExpenseRecord.id == expense_id, ExpenseRecord.warehouse_id == record.warehouse_id,
    ).with_for_update())).scalar_one_or_none()
    if expense is None:
        raise HTTPException(400, "关联工资支出不存在，请先核对")
    reason = "因为撤销发放而冲销"
    await record_history(db, module="expense", record_id=expense.id, operator=operator,
        operation_type="delete", before={"payroll_record_id": record.id, "amount": expense.amount,
        "account_id": expense.account_id, "remark": expense.remark},
        after={"remark": f"{expense.remark}；{reason}"}, warehouse_id=record.warehouse_id)
    record.expense_record_id = None
    await db.flush()  # Clear FK before deleting the referenced expense.
    await db.delete(expense)
    return expense_id


async def require_manual_expense(db, expense_id):
    linked = (await db.execute(select(PayrollRecord.id).where(
        PayrollRecord.expense_record_id == expense_id,
    ).limit(1))).scalar_one_or_none()
    if linked is not None:
        raise HTTPException(400, "工资联动支出请在工资模块撤销发放后处理")
