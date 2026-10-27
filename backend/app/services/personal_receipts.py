"""Personal receipt association checks on validated input, before business writes."""
from types import SimpleNamespace
from fastapi import HTTPException
from app.core.permissions import Role, get_wh_ids
from app.models.expense_fund import ExpenseFund
from app.services.fund_authorization import identities


async def require_personal_receipts(db, user, receipts, *, personal_only=False):
    if not personal_only and not getattr(user, '_personal_finance', False):
        return
    receipts = tuple(receipts)
    if not any(receipts):
        return
    from app.api.secure_uploads import may_read, upload_root
    # Personal mode must not inherit management menu or administrator read powers.
    personal = SimpleNamespace(**{k: v for k, v in user.__dict__.items() if not k.startswith('_sa_')})
    personal.extra_permissions = []
    personal.role = Role.STAFF
    from app.core.employee_access import own_employee
    employee=await own_employee(db,user)
    if employee is None:raise HTTPException(403,'请先关联有效的本人员工档案')
    owner_ids = await identities(db, user)
    for receipt in receipts:
        if not receipt:
            continue
        target = receipt.lstrip('/')
        parts = target.split('/')
        allowed = False
        if len(parts) >= 3 and parts[0] == 'uploads' and all(p not in ('', '.', '..') for p in parts):
            path = upload_root().joinpath(*parts[1:]).resolve()
            valid_file = path.is_relative_to(upload_root()) and path.is_file() and path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.pdf')
            if valid_file and parts[1].isdigit():
                allowed = await may_read(db, personal, target)
            elif valid_file and len(parts) == 5 and parts[1] == 'fund_receipts' and parts[2].isdigit() and parts[3].isdigit():
                fund = await db.get(ExpenseFund, int(parts[3]))
                allowed = bool(fund and fund.warehouse_id == int(parts[2])
                    and fund.warehouse_id == employee.warehouse_id
                    and fund.warehouse_id in get_wh_ids(user) and fund.employee_id in owner_ids)
        if not allowed:
            raise HTTPException(403, '本人申请不能关联他人附件')
