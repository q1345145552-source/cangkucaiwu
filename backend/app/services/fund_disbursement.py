"""备用金拨付记成本和资金，后续开销只记用途；调用方统一提交事务。"""
from datetime import datetime, time, timezone
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import exists, select, text

from app.core.timezone import thai_today
from app.models.customer import PaymentAccount
from app.models.employee_advance import EmployeeAdvance
from app.models.expense_fund import ExpenseFund, ExpenseFundDisbursement, ExpenseFundItem
from app.models.income_expense import ExpenseRecord, IncomeExpenseCategory
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services.data_history import record_history

CATEGORY = "备用金拨付"
ZERO = Decimal("0.00")


def money(value):
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def validate_amount(value):
    try:
        raw = Decimal(str(value))
        rounded = money(raw)
        if not raw.is_finite() or rounded <= 0 or rounded >= Decimal("1000000000000") or abs(raw - rounded) > Decimal("0.00000001"):
            raise ValueError
        return rounded
    except (ValueError, InvalidOperation):
        raise HTTPException(400, "拨付金额必须大于0，且最多两位小数")


def disbursement_date(value):
    try:
        if not value:
            return datetime.combine(thai_today(), time.min)
        parsed = datetime.fromisoformat(value)
        return datetime.combine(parsed.date(), time.min)
    except (ValueError, TypeError):
        raise HTTPException(400, "拨付日期格式错误，应为 YYYY-MM-DD")


async def backfill_fund_disbursement_categories(conn):
    result = await conn.execute(text("""
        INSERT INTO income_expense_categories (warehouse_id,type,name,category_group,status,sort_order)
        SELECT w.id,'expense',CAST(:name AS VARCHAR),'operating','active',111 FROM warehouses w
        WHERE NOT EXISTS (SELECT 1 FROM income_expense_categories c WHERE c.warehouse_id=w.id
          AND c.type='expense' AND c.category_group='operating' AND c.name=CAST(:name AS VARCHAR))
    """), {"name": CATEGORY})
    return result.rowcount


def cost_record_filter(expense=ExpenseRecord):
    """只去重本轮之后的备用金预支，旧的正式支出一条不删除、不改写。"""
    return ~exists(select(EmployeeAdvance.id).join(ExpenseFundItem,
        ExpenseFundItem.id == EmployeeAdvance.fund_item_id).where(
        EmployeeAdvance.expense_record_id == expense.id,
        EmployeeAdvance.warehouse_id == expense.warehouse_id,
        EmployeeAdvance.source == "fund", ExpenseFundItem.cost_record_only.is_(True)))


async def create_disbursement(db, fund, amount, payment_account_id, operator, *, receive_date=None, request_id=None):
    amount = validate_amount(amount)
    when = disbursement_date(receive_date)
    if not payment_account_id:
        raise HTTPException(400, "请选择备用金拨付账户")
    # 调用者已锁备用金账户；付款账户也锁定，避免并发拨付越过余额。
    account = (await db.execute(select(PaymentAccount).where(
        PaymentAccount.id == payment_account_id, PaymentAccount.warehouse_id == fund.warehouse_id,
    ).with_for_update())).scalar_one_or_none()
    if account is None:
        raise HTTPException(400, "付款账户不存在或不属于当前仓库")
    if account.status not in (None, "active"):
        raise HTTPException(400, "付款账户已停用")
    currency = fund.currency or "THB"
    if (account.currency or "THB") != currency:
        raise HTTPException(400, "付款账户币种必须与备用金账户一致")
    from app.services.account_balances import current_account_balances
    before_balance = (await current_account_balances(db, [account]))[account.id]
    if before_balance < amount:
        raise HTTPException(400, "付款账户余额不足")
    await db.execute(select(Warehouse.id).where(Warehouse.id == fund.warehouse_id).with_for_update())
    category = (await db.execute(select(IncomeExpenseCategory).where(
        IncomeExpenseCategory.warehouse_id == fund.warehouse_id, IncomeExpenseCategory.type == "expense",
        IncomeExpenseCategory.category_group == "operating", IncomeExpenseCategory.name == CATEGORY,
    ).order_by(IncomeExpenseCategory.id).limit(1))).scalar_one_or_none()
    if category is None:
        category = IncomeExpenseCategory(warehouse_id=fund.warehouse_id, type="expense", category_group="operating",
            name=CATEGORY, status="active", sort_order=111)
        db.add(category)
        await db.flush()
    if category.status != "active":
        raise HTTPException(400, "备用金拨付支出分类已停用")
    who = await db.get(User, fund.employee_id)
    warehouse = await db.get(Warehouse, fund.warehouse_id)
    remark = f"拨给{who.display_name if who else fund.employee_id} {warehouse.name} 备用金"
    expense = ExpenseRecord(warehouse_id=fund.warehouse_id, category_id=category.id, account_id=account.id,
        amount=float(amount), currency=currency, expense_date=when, remark=remark, approved_by=operator.id)
    db.add(expense)
    await db.flush()
    row = ExpenseFundDisbursement(warehouse_id=fund.warehouse_id, fund_id=fund.id, amount=amount,
        currency=currency, disbursed_date=when, payment_account_id=account.id, account_name=account.account_name,
        expense_record_id=expense.id, recharge_request_id=request_id,
        operator_id=operator.id, operator_name=operator.display_name, remark=remark)
    db.add(row)
    fund.remaining_balance = float(money(fund.remaining_balance) + amount)
    fund.amount = float(money(fund.amount) + amount)
    # receive_date 保留旧累计记录的历史日期；新拨付日期在逐笔记录中单独保存。
    await db.flush()
    await record_history(db, module="expense", record_id=expense.id, operator=operator,
        operation_type="create", after={"fund_disbursement_id": row.id, "fund_id": fund.id,
            "amount": float(amount), "currency": currency, "account_id": account.id,
            "expense_date": when.date().isoformat(), "remark": remark}, warehouse_id=fund.warehouse_id)
    await record_history(db, module="expense_fund", record_id=fund.id, operator=operator,
        operation_type="disburse", after={"disbursement_id": row.id, "expense_record_id": expense.id,
            "amount": float(amount), "currency": currency, "payment_account_id": account.id}, warehouse_id=fund.warehouse_id)
    return {**disbursement_fields(row), "account_balance": float(before_balance - amount),
        "new_balance": fund.remaining_balance, "total_topped_up": fund.amount}


def disbursement_fields(row):
    return {"id": row.id, "disbursement_id": row.id, "fund_id": row.fund_id,
        "warehouse_id": row.warehouse_id, "amount": float(row.amount), "currency": row.currency,
        "disbursed_date": row.disbursed_date.date().isoformat(), "payment_account_id": row.payment_account_id,
        "account_name": row.account_name, "expense_record_id": row.expense_record_id,
        "recharge_request_id": row.recharge_request_id, "operator_name": row.operator_name,
        "created_at": row.created_at.isoformat() if row.created_at else None, "remark": row.remark}


def utc(value):
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def fund_sources(db, fund):
    """只读先拨先用分摊；无法还原的老资金明确标历史余额，不伪造拨付编号。"""
    rows = (await db.execute(select(ExpenseFundDisbursement).where(
        ExpenseFundDisbursement.fund_id == fund.id, ExpenseFundDisbursement.warehouse_id == fund.warehouse_id,
    ).order_by(ExpenseFundDisbursement.created_at, ExpenseFundDisbursement.id))).scalars().all()
    items = (await db.execute(select(ExpenseFundItem).where(ExpenseFundItem.fund_id == fund.id)
        .order_by(ExpenseFundItem.created_at, ExpenseFundItem.id))).scalars().all()
    legacy = max(ZERO, money(fund.amount) - sum((r.amount for r in rows), ZERO))
    pools = [{"disbursement_id": None, "remaining": legacy, "label": "历史余额（原拨付编号未记录）"}]
    by_item = {}
    offset = 0
    for item in items:
        while offset < len(rows) and utc(rows[offset].created_at) <= utc(item.created_at):
            r = rows[offset]
            pools.append({"disbursement_id": r.id, "remaining": r.amount, "label": f"拨付 #{r.id}"})
            offset += 1
        if item.review_status == "rejected" or item.is_voided:
            by_item[item.id] = []
            continue
        remaining = money(item.amount)
        parts = []
        # 旧混币种开销不能冒充消耗本币的新拨付。
        if (item.currency or "THB") == (fund.currency or "THB"):
            for pool in pools:
                used = min(remaining, pool["remaining"])
                if used > 0:
                    parts.append({"disbursement_id": pool["disbursement_id"], "amount": float(used), "label": pool["label"]})
                    pool["remaining"] -= used
                    remaining -= used
        if remaining > 0:
            parts.append({"disbursement_id": None, "amount": float(remaining), "label": "历史来源未记录"})
        by_item[item.id] = parts
    return rows, by_item


async def require_manual_disbursement_expense(db, expense_id):
    if (await db.execute(select(ExpenseFundDisbursement.id).where(
        ExpenseFundDisbursement.expense_record_id == expense_id).limit(1))).first():
        raise HTTPException(400, "备用金拨付联动支出不能单独修改或删除")
