"""报销公司付款与垫款额度共用请求事务；垫付不先记公司支出。"""
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select, text

from app.core.timezone import thai_now
from app.models.cash_advance import CashAdvance
from app.models.customer import PaymentAccount
from app.models.expense_fund import ExpenseFund, ExpenseFundItem
from app.models.income_expense import ExpenseRecord, IncomeExpenseCategory
from app.models.reimbursement import Reimbursement
from app.models.reimbursement_payment import ReimbursementPayment
from app.services.data_history import record_history

REIMBURSEMENT_CATEGORY = "报销"
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/app/uploads")
SOURCE_LABELS = {"company_account": "公司账户", "cash_advance": "垫款单", "expense_fund": "备用金扣款"}


async def backfill_reimbursement_categories(conn):
    result = await conn.execute(text("""
        INSERT INTO income_expense_categories (warehouse_id,type,name,category_group,status,sort_order)
        SELECT w.id,'expense',CAST(:name AS VARCHAR),'operating','active',101 FROM warehouses w
        WHERE NOT EXISTS (SELECT 1 FROM income_expense_categories c WHERE c.warehouse_id=w.id
            AND c.type='expense' AND c.category_group='operating' AND c.name=CAST(:name AS VARCHAR))
    """), {"name": REIMBURSEMENT_CATEGORY})
    return result.rowcount


def money(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite():
            raise ValueError
        rounded = amount.quantize(Decimal("0.01"))
        # 报销合计原字段为 Float；容忍 0.1+0.2 一类浮点尾差，不接受真实的厘位金额。
        if rounded <= 0 or abs(amount - rounded) > Decimal("0.00000001") or rounded >= Decimal("1000000000000"):
            raise ValueError
    except (InvalidOperation, ValueError):
        raise HTTPException(400, "报销付款金额无效，请先核对报销单")
    return rounded


def payment_dict(p):
    return {"id": p.id, "reimbursement_id": p.reimbursement_id, "warehouse_id": p.warehouse_id,
        "amount": float(p.amount), "currency": p.currency, "funding_source": p.funding_source,
        "funding_source_label": SOURCE_LABELS[p.funding_source], "payment_account_id": p.payment_account_id,
        "account_name": p.account_name, "payment_method": p.payment_method,
        "payment_method_label": "现金" if p.payment_method == "cash" else "转账" if p.payment_method == "transfer" else "备用金扣款",
        "payment_voucher_path": p.voucher_path, "cash_advance_id": p.cash_advance_id,
        "expense_record_id": p.expense_record_id, "paid_by_id": p.paid_by_id,
        "paid_by_name": p.paid_by_name, "paid_at": p.paid_at.isoformat(), "status": p.status,
        "status_label": "有效" if p.status == "active" else "已撤销",
        "revoked_by_id": p.revoked_by_id, "revoked_by_name": p.revoked_by_name,
        "revoked_at": p.revoked_at.isoformat() if p.revoked_at else None, "revoke_reason": p.revoke_reason,
        "ledger_ref_no": f"RB-P-{p.id}" if p.funding_source == "company_account" else None}


async def active_payment_map(db, reimbs):
    if not reimbs: return {}
    rows = (await db.execute(select(ReimbursementPayment).where(
        ReimbursementPayment.reimbursement_id.in_([r.id for r in reimbs]), ReimbursementPayment.status == "active",
    ))).scalars().all()
    return {p.reimbursement_id: p for p in rows}


def payment_fields(r, payment=None, *, can_revoke=False):
    return {"payment_account_id": r.payment_account_id, "payment_method": r.payment_method,
        "payment_voucher_path": r.payment_voucher_path, "funding_source": r.funding_source,
        "funding_source_label": SOURCE_LABELS.get(r.funding_source), "cash_advance_id": r.cash_advance_id,
        "expense_record_id": r.expense_record_id, "payment_id": payment.id if payment else None,
        "paid_by_id": payment.paid_by_id if payment else None, "paid_by_name": payment.paid_by_name if payment else None,
        "account_name": payment.account_name if payment else None, "can_revoke_payment": payment is not None and can_revoke}


async def payment_account(db, r, account_id, *, reversing=False):
    if not account_id: raise HTTPException(400, "请选择付款账户")
    account = (await db.execute(select(PaymentAccount).where(
        PaymentAccount.id == account_id, PaymentAccount.warehouse_id == r.warehouse_id,
    ).with_for_update())).scalar_one_or_none()
    if account is None: raise HTTPException(400, "付款账户不存在或不属于当前仓库")
    if not reversing and account.status not in (None, "active"): raise HTTPException(400, "付款账户已停用")
    if (account.currency or "THB").upper() != (r.currency or "THB").upper():
        raise HTTPException(400, "付款账户币种与报销单不一致")
    return account


def validate_voucher(path, warehouse_id):
    path = (path or "").strip()
    if not path: raise HTTPException(400, "请上传付款凭证")
    parts = path.split("/")
    if len(parts) != 5 or parts[:2] != ["uploads", str(warehouse_id)] or parts[3] != "reimbursement-payments" or any(p in ("", ".", "..") or "\\" in p for p in parts):
        raise HTTPException(400, "付款凭证不属于当前仓库")
    if not Path(UPLOAD_DIR).joinpath(*parts[1:]).is_file():
        raise HTTPException(400, "付款凭证不存在，请重新上传")
    return path


async def lock_advance(db, r, advance_id, amount):
    if not advance_id: raise HTTPException(400, "请选择报销垫款单")
    advance = (await db.execute(select(CashAdvance).where(
        CashAdvance.id == advance_id, CashAdvance.warehouse_id == r.warehouse_id,
    ).with_for_update())).scalar_one_or_none()
    if advance is None: raise HTTPException(400, "垫款单不存在或不属于当前仓库")
    if advance.status != "confirmed": raise HTTPException(400, "只能使用已确认的垫款单")
    if advance.currency != (r.currency or "THB").upper(): raise HTTPException(400, "垫款单币种与报销单不一致")
    from app.services.cash_advance_payroll import payroll_usage_totals
    from app.services.cash_advance_usage import reimbursement_usage_totals, employee_advance_usage_totals
    wages = (await payroll_usage_totals(db, [advance]))[advance.id]
    expenses = (await reimbursement_usage_totals(db, [advance]))[advance.id]
    advances = (await employee_advance_usage_totals(db, [advance]))[advance.id]
    if amount > advance.amount - advance.repaid_amount or amount > advance.amount - wages - expenses - advances:
        raise HTTPException(400, "垫款单剩余金额不足")
    return advance


def fund_snapshot(item):
    return {"expense_date": item.expense_date.isoformat(), "category": item.category, "amount": item.amount,
        "currency": item.currency, "description": item.description, "receipt": item.receipt,
        "review_status": item.review_status, "review_remark": item.review_remark, "review_action": item.review_action}


async def fund_details(db, r):
    """初次付款不再扣款；撤销后的再次付款重建原开销、只扣回原来退还的金额。"""
    if r.fund_item_id:
        item = (await db.execute(select(ExpenseFundItem).where(ExpenseFundItem.id == r.fund_item_id).with_for_update())).scalar_one_or_none()
        if item is None: raise HTTPException(400, "关联备用金开销不存在，请先核对")
        fund_id = item.fund_id
    else:
        old = (await db.execute(select(ReimbursementPayment).where(
            ReimbursementPayment.reimbursement_id == r.id, ReimbursementPayment.warehouse_id == r.warehouse_id,
            ReimbursementPayment.funding_source == "expense_fund", ReimbursementPayment.status == "revoked",
        ).order_by(ReimbursementPayment.id.desc()).limit(1))).scalar_one_or_none()
        if old is None or not old.fund_id or not old.fund_item_snapshot:
            raise HTTPException(400, "关联备用金开销不存在，请先核对")
        fund_id, item = old.fund_id, None
    fund = (await db.execute(select(ExpenseFund).where(
        ExpenseFund.id == fund_id, ExpenseFund.warehouse_id == r.warehouse_id, ExpenseFund.employee_id == r.employee_id,
    ).with_for_update())).scalar_one_or_none()
    if fund is None: raise HTTPException(400, "关联备用金不存在或不属于本仓报销人")
    if item is None:
        if fund.status != "active": raise HTTPException(400, "关联备用金已结算，不能再次扣款")
        snapshot = dict(old.fund_item_snapshot)
        amount = money(snapshot["amount"])
        if Decimal(str(fund.remaining_balance or 0)) < amount: raise HTTPException(400, "备用金余额不足")
        snapshot["expense_date"] = datetime.fromisoformat(snapshot["expense_date"])
        item = ExpenseFundItem(fund_id=fund.id, **snapshot)
        db.add(item)
        fund.remaining_balance = float(Decimal(str(fund.remaining_balance or 0)) - amount)
        await db.flush()
        r.fund_item_id = item.id
    if item.review_status == "rejected": raise HTTPException(400, "关联备用金开销已驳回，不能付款")
    return fund, item


async def create_cost(db, r, amount, account_id, voucher, user, now):
    category = (await db.execute(select(IncomeExpenseCategory).where(
        IncomeExpenseCategory.warehouse_id == r.warehouse_id, IncomeExpenseCategory.type == "expense",
        IncomeExpenseCategory.category_group == "operating", IncomeExpenseCategory.name == REIMBURSEMENT_CATEGORY,
    ).order_by(IncomeExpenseCategory.id).limit(1))).scalar_one_or_none()
    if category is None or category.status != "active": raise HTTPException(400, "缺少有效报销支出分类，请先完成启动迁移")
    expense = ExpenseRecord(warehouse_id=r.warehouse_id, category_id=category.id, account_id=account_id,
        amount=float(amount), currency=(r.currency or "THB").upper(), expense_date=now.replace(tzinfo=None),
        voucher=voucher, remark=f"报销付款 #{r.id}", approved_by=user.id)
    db.add(expense)
    await db.flush()
    r.expense_record_id = expense.id
    await record_history(db, module="expense", record_id=expense.id, operator=user, operation_type="create",
        after={"reimbursement_id": r.id, "amount": float(amount), "currency": expense.currency,
            "account_id": account_id, "cash_advance_id": r.cash_advance_id, "remark": expense.remark}, warehouse_id=r.warehouse_id)
    return expense


async def result(db, r, p, account=None):
    balance = None
    if account is not None:
        from app.services.account_balances import current_account_balances
        balance = float((await current_account_balances(db, [account]))[account.id])
    return {"id": r.id, "status": r.status, "expense_record_id": r.expense_record_id,
        "cash_advance_id": r.cash_advance_id, "payment": payment_dict(p), "account_balance": balance}


async def pay(db, r, req, user):
    if r.status not in ("approved", "partially_approved"):
        raise HTTPException(400, "该报销单已付款" if r.status == "paid" else "仅已审批状态可付款")
    if r.expense_record_id is not None or await active_payment_map(db, [r]):
        raise HTTPException(400, "该报销单已有付款记录，请先核对")
    source = req.funding_source or ("expense_fund" if r.is_fund_linked == "1" else "company_account")
    if r.is_fund_linked == "1" and source != "expense_fund":
        raise HTTPException(400, "该报销已关联备用金，请使用备用金扣款")
    if r.is_fund_linked != "1" and source == "expense_fund":
        raise HTTPException(400, "该报销未关联备用金，不能选择备用金扣款")
    if source != "company_account" and req.payment_account_id is not None:
        raise HTTPException(400, "该资金来源不应选择公司账户")
    if source != "cash_advance" and req.cash_advance_id is not None:
        raise HTTPException(400, "该资金来源不应选择垫款单")
    amount, now, previous = money(r.total_amount), thai_now(), r.status
    account, advance, fund, item, voucher = None, None, None, None, None
    if source != "expense_fund":
        voucher = validate_voucher(req.payment_voucher_path, r.warehouse_id)
        if req.payment_method not in ("cash", "transfer"): raise HTTPException(400, "请选择现金或转账付款方式")
        if source == "company_account":
            account = await payment_account(db, r, req.payment_account_id)
            from app.services.account_balances import current_account_balances
            if (await current_account_balances(db, [account]))[account.id] < amount:
                raise HTTPException(400, "公司账户余额不足")
        else: advance = await lock_advance(db, r, req.cash_advance_id, amount)
    else:
        fund, item = await fund_details(db, r)
    r.funding_source = source
    r.payment_account_id = account.id if account else None
    r.cash_advance_id = advance.id if advance else None
    r.payment_method = req.payment_method if source != "expense_fund" else None
    r.payment_voucher_path = voucher
    expense = await create_cost(db, r, amount, r.payment_account_id, voucher, user, now) if source == "company_account" else None
    p = ReimbursementPayment(reimbursement_id=r.id, warehouse_id=r.warehouse_id, amount=amount,
        currency=(r.currency or "THB").upper(), funding_source=source, payment_account_id=r.payment_account_id,
        account_name=account.account_name if account else None, cash_advance_id=r.cash_advance_id,
        payment_method=r.payment_method, voucher_path=voucher, expense_record_id=expense.id if expense else None,
        previous_status=previous, paid_by_id=user.id, paid_by_name=user.display_name, paid_at=now, status="active",
        fund_id=fund.id if fund else None, fund_item_snapshot=fund_snapshot(item) if item else None)
    db.add(p)
    r.status, r.paid_at = "paid", now
    await db.flush()
    output = await result(db, r, p, account)
    await record_history(db, module="reimbursement", record_id=r.id, operator=user, operation_type="pay",
        before={"status": previous}, after=output, warehouse_id=r.warehouse_id)
    if advance:
        await record_history(db, module="cash_advances", record_id=advance.id, operator=user, operation_type="reimbursement_use",
            after={"reimbursement_id": r.id, "payment_id": p.id, "amount": float(amount), "currency": p.currency}, warehouse_id=r.warehouse_id)
    return {"message": "付款成功", **output}


async def revoke(db, r, user, reason):
    p = (await db.execute(select(ReimbursementPayment).where(
        ReimbursementPayment.reimbursement_id == r.id, ReimbursementPayment.warehouse_id == r.warehouse_id,
        ReimbursementPayment.status == "active",
    ).with_for_update())).scalar_one_or_none()
    if p is None: raise HTTPException(400, "没有可撤销的付款记录，历史付款不自动推断资金来源")
    if r.status != "paid": raise HTTPException(400, "报销单付款状态异常，请先核对")
    before = payment_dict(p)
    account = None
    if p.funding_source == "company_account": account = await payment_account(db, r, p.payment_account_id, reversing=True)
    elif p.funding_source == "cash_advance":
        advance = (await db.execute(select(CashAdvance).where(
            CashAdvance.id == p.cash_advance_id, CashAdvance.warehouse_id == r.warehouse_id,
        ).with_for_update())).scalar_one_or_none()
        if advance is None: raise HTTPException(400, "关联垫款单不存在，请先核对")
    else:
        if not r.fund_item_id: raise HTTPException(400, "关联备用金开销不存在，请先核对")
        fund, item = await fund_details(db, r)
        fund.remaining_balance = float(Decimal(str(fund.remaining_balance or 0)) + money(item.amount))
        r.fund_item_id = None
        await db.delete(item)
    if p.funding_source != "expense_fund":
        expense = (await db.execute(select(ExpenseRecord).where(
            ExpenseRecord.id == r.expense_record_id, ExpenseRecord.warehouse_id == r.warehouse_id,
        ).with_for_update())).scalar_one_or_none()
        if expense is None or expense.id != p.expense_record_id:
            raise HTTPException(400, "关联报销成本不存在或不一致，请先核对")
        await record_history(db, module="expense", record_id=expense.id, operator=user, operation_type="delete",
            before={"reimbursement_id": r.id, "amount": expense.amount, "account_id": expense.account_id},
            after={"remark": f"撤销报销付款：{reason}"}, warehouse_id=r.warehouse_id)
        r.expense_record_id = None
        await db.flush()
        await db.delete(expense)
    p.status = "revoked"
    p.revoked_by_id, p.revoked_by_name, p.revoked_at, p.revoke_reason = user.id, user.display_name, thai_now(), reason
    r.status, r.paid_at = p.previous_status, None
    r.payment_account_id, r.payment_method, r.payment_voucher_path, r.cash_advance_id = None, None, None, None
    r.funding_source = "expense_fund" if r.is_fund_linked == "1" else None
    await db.flush()
    output = await result(db, r, p, account)
    await record_history(db, module="reimbursement", record_id=r.id, operator=user, operation_type="revoke_payment",
        before=before, after={**output, "reason": reason}, warehouse_id=r.warehouse_id)
    if p.funding_source == "cash_advance":
        await record_history(db, module="cash_advances", record_id=p.cash_advance_id, operator=user, operation_type="reimbursement_undo",
            before={"reimbursement_id": r.id, "amount": float(p.amount), "currency": p.currency}, after={"reason": reason}, warehouse_id=r.warehouse_id)
    return {"message": "付款已撤销", **output}


async def require_manual_reimbursement_expense(db, expense_id):
    linked = (await db.execute(select(Reimbursement.id).where(Reimbursement.expense_record_id == expense_id).limit(1))).first()
    if linked: raise HTTPException(400, "报销联动支出请先在报销模块撤销付款")


async def sync_fund_review_payment(db, r, user, *, approved, reason=None):
    """备用金原审核已完成扣/退款；这里只同步付款历史，不再动金额或审批状态。"""
    p = (await active_payment_map(db, [r])).get(r.id)
    if approved:
        r.funding_source = "expense_fund"
        if p is not None: return
        fund, item = await fund_details(db, r)
        paid_at = r.paid_at or thai_now()
        if paid_at.tzinfo is None:
            paid_at = paid_at.replace(tzinfo=timezone.utc)
        p = ReimbursementPayment(reimbursement_id=r.id, warehouse_id=r.warehouse_id,
            amount=money(r.total_amount), currency=(r.currency or "THB").upper(), funding_source="expense_fund",
            previous_status="approved", paid_by_id=user.id, paid_by_name=user.display_name,
            paid_at=paid_at, status="active", fund_id=fund.id, fund_item_snapshot=fund_snapshot(item))
        db.add(p)
        await db.flush()
        await record_history(db, module="reimbursement", record_id=r.id, operator=user, operation_type="pay",
            after={"payment": payment_dict(p), "via": "expense_fund_review"}, warehouse_id=r.warehouse_id)
    elif p is not None and p.funding_source == "expense_fund":
        before = payment_dict(p)
        p.status, p.revoked_by_id, p.revoked_by_name, p.revoked_at = "revoked", user.id, user.display_name, thai_now()
        p.revoke_reason = reason or "备用金审核驳回"
        r.funding_source = None
        await record_history(db, module="reimbursement", record_id=r.id, operator=user, operation_type="revoke_payment",
            before=before, after={"reason": p.revoke_reason, "via": "expense_fund_review"}, warehouse_id=r.warehouse_id)
