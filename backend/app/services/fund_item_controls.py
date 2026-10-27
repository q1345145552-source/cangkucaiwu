from app.services.balance_warning import balance_warning,record_balance_warning
"""手工备用金开销的管理员编辑/作废及留痕，系统联动台账不从此入口改动。"""
from datetime import datetime, time
from decimal import Decimal
from fastapi import HTTPException
from sqlalchemy import select, func
from app.core.timezone import thai_now
from app.models.expense_fund import ExpenseFund, ExpenseFundItem, ReviewStatus
from app.models.employee_advance import EmployeeAdvance
from app.models.reimbursement import Reimbursement
from app.services.data_history import record_history
from app.services.flow_rules import fund_available
from app.services import cost_identity as costs


def fields(item):
    return {"id": item.id, "fund_id": item.fund_id, "expense_date": item.expense_date.isoformat(),
        "category": item.category, "amount": item.amount, "currency": item.currency or "THB",
        "description": item.description, "receipt": item.receipt, "review_status": item.review_status,
        "review_remark": item.review_remark, "review_action": item.review_action, "cost_record_only": item.cost_record_only,
        "is_voided": item.is_voided, "voided_by": item.voided_by,
        "voided_at": item.voided_at.isoformat() if item.voided_at else None, "void_reason": item.void_reason}


async def linked_ids(db, ids):
    if not ids: return set()
    result = set()
    from app.models import ExpenseApproval
    for model in (EmployeeAdvance, Reimbursement,ExpenseApproval):
        result.update((await db.execute(select(model.fund_item_id).where(model.fund_item_id.in_(ids)))).scalars().all())
    return result


async def lock_manual_item(db, account_id, item_id, wh_ids, *, action):
    wid=(await db.execute(select(ExpenseFund.warehouse_id).where(ExpenseFund.id==account_id,ExpenseFund.warehouse_id.in_(wh_ids)))).scalar_one_or_none()
    if wid is None:raise HTTPException(404,'开销记录不存在或不属于当前仓库')
    await costs.lock(db,wid)
    # 审核同样先锁开销行；避免与审核并发时越过“已通过不能改”的判断。
    item = (await db.execute(select(ExpenseFundItem).join(ExpenseFund).where(
        ExpenseFundItem.id == item_id, ExpenseFundItem.fund_id == account_id,
        ExpenseFund.warehouse_id.in_(wh_ids),
    ).with_for_update(of=ExpenseFundItem).execution_options(populate_existing=True))).scalar_one_or_none()
    if item is None: raise HTTPException(404, "开销记录不存在或不属于当前仓库")
    if item.is_voided: raise HTTPException(400, "该开销已作废，不能再修改或作废")
    if item.review_status == ReviewStatus.APPROVED.value:
        raise HTTPException(400, "该开销已审核通过 不能修改" if action == "edit" else "该开销已审核通过 不能作废")
    if item_id in await linked_ids(db, [item_id]):
        raise HTTPException(400, "报销或预支关联开销请在原业务模块处理")
    fund = (await db.execute(select(ExpenseFund).where(ExpenseFund.id == account_id,
        ExpenseFund.warehouse_id.in_(wh_ids)).with_for_update().execution_options(populate_existing=True))).scalar_one()
    return fund, item


async def update(db, fund, item, changes, user, validate_receipt):
    before = fields(item)
    if "amount" in changes and changes["amount"] is None: raise HTTPException(400, "开销金额必须大于0")
    if "category" in changes and not (changes["category"] or "").strip(): raise HTTPException(400, "请填写开销用途")
    if "currency" in changes and changes["currency"] != (item.currency or "THB"):
        raise HTTPException(400, "开销币种不能修改")
    if "receipt" in changes and changes["receipt"] != item.receipt:
        changes["receipt"] = validate_receipt(changes["receipt"], fund)
    warning=None
    new_amount = float(changes.get("amount", item.amount))
    category = changes.get("category", item.category)
    if ("amount" in changes or "category" in changes) and item.review_status not in (None, ReviewStatus.REJECTED.value) and category != "报销":
        spent = float((await db.execute(select(func.coalesce(func.sum(ExpenseFundItem.amount), 0)).where(
            ExpenseFundItem.fund_id == fund.id, ExpenseFundItem.category != "报销",
            ExpenseFundItem.review_status != ReviewStatus.REJECTED.value, ExpenseFundItem.not_voided(),
        ))).scalar() or 0)
        available = fund_available(fund.remaining_balance, spent) + (item.amount if item.category != "报销" else 0)
        warning=balance_warning(available,new_amount,item.currency or 'THB',source='expense_fund',source_id=fund.id)
    for key in ("expense_date", "category", "amount", "description", "receipt"):
        if key in changes:
            value = changes[key]
            if key == "expense_date":
                if value is None: raise HTTPException(400, "请选择开销日期")
                value = datetime.combine(value, time.min)
            if key == "amount": value = float(value)
            if key == "description" and value is None: raise HTTPException(400, "开销说明不能为null")
            setattr(item, key, value)
    await costs.sync(db,'fund_item',item,user,
        supplier=changes.get('supplier_id',costs.UNSET),
        identity=costs.parse_identity(changes['invoice_identity'],user) if 'invoice_identity' in changes else costs.UNSET,
        confirmation=changes.get('cost_confirmation'))
    await db.flush()
    after = fields(item)
    await record_history(db, module="expense_fund_item", record_id=item.id, operator=user, operation_type="edit",
        before=before, after=after, warehouse_id=fund.warehouse_id)
    await record_balance_warning(db,warning,user,module='expense_fund_item',record_id=item.id,warehouse_id=fund.warehouse_id)
    return {'warning':warning,**after, "message": "开销记录已修改"}


async def void(db, fund, item, reason, user):
    reason = (reason or "").strip()
    if not reason: raise HTTPException(400, "请填写作废原因")
    before = fields(item)
    item.review_status = ReviewStatus.VOIDED.value
    item.voided_by, item.voided_at, item.void_reason = user.id, thai_now(), reason
    await costs.sync(db,'fund_item',item,user,skip_suspicion=True)
    await db.flush()
    after = fields(item)
    await record_history(db, module="expense_fund_item", record_id=item.id, operator=user, operation_type="void",
        before=before, after=after, warehouse_id=fund.warehouse_id)
    return {**after, "message": "开销记录已作废"}
