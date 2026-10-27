"""Private file access derives from every matching business reference, not a directory/menu alone."""
import json
from sqlalchemy import select
from app.core.permissions import Role,get_wh_ids
from app.core.employee_access import own_employee
from app.core.round5_access import has_menu,financial_reader
from app.services.fund_authorization import identities
from app.models.employee import Employee
from app.models.payroll import PayrollRecord
from app.models.clock_in_records import ClockInRecord
from app.models.attendance import LeaveRequest
from app.models.overtime import OvertimeAssignment
from app.models.expense_fund import ExpenseFund,ExpenseFundItem
from app.models.reimbursement import Reimbursement,ReimbursementItem
from app.models.reimbursement_payment import ReimbursementPayment
from app.models.cash_advance import CashAdvance
from app.models.cash_advance_repayment import CashAdvanceRepayment
from app.models.expense_approval import ExpenseApproval
from app.models.income_expense import ExpenseRecord
from app.models.payable import PayableBill
from app.models.recharge import RechargeDeclaration
from app.models.supplier import PurchaseOrder
from app.models.purchase_receipt import PurchaseReceiptEvent


async def fund_receipt_allowed(db,user,fund_id,wid):
    fund=await db.get(ExpenseFund,fund_id)
    if not fund or fund.warehouse_id != wid or wid not in get_wh_ids(user):return False
    employee=await own_employee(db,user)
    own=employee is not None and employee.warehouse_id == wid and fund.employee_id in await identities(db,user)
    return own or financial_reader(user,'expense_fund')


async def reference_allowed(db,user,obj,parent,field,employee,owner_ids,key):
    if user.role == Role.WAREHOUSE_ADMIN:return True
    if user.role == Role.SUPER_ADMIN:return False
    own_eid=employee.id if employee is not None else None
    if isinstance(obj,Employee):
        return obj.id == own_eid or (field == 'photo_path' and user.role == Role.SUPERVISOR and has_menu(user,'employees'))
    if isinstance(obj,PayrollRecord):return obj.employee_id == own_eid or financial_reader(user,'payroll')
    if isinstance(obj,ClockInRecord):return (employee is not None and obj.user_id in owner_ids) or (user.role == Role.SUPERVISOR and has_menu(user,'attendance'))
    if isinstance(obj,LeaveRequest):return obj.employee_id == own_eid or (user.role == Role.SUPERVISOR and has_menu(user,'leave'))
    if isinstance(obj,OvertimeAssignment):return obj.employee_id == own_eid or (user.role == Role.SUPERVISOR and has_menu(user,'overtime'))
    if isinstance(obj,ExpenseFundItem):return (employee is not None and parent.employee_id in owner_ids) or financial_reader(user,'expense_fund')
    if isinstance(obj,(Reimbursement,ReimbursementItem,ReimbursementPayment)):
        reimb=parent if isinstance(obj,ReimbursementItem) else obj if isinstance(obj,Reimbursement) else await db.get(Reimbursement,obj.reimbursement_id)
        return bool(reimb and ((employee is not None and reimb.employee_id in owner_ids) or financial_reader(user,'reimbursement')))
    if isinstance(obj,(CashAdvance,CashAdvanceRepayment)):
        advance=obj if isinstance(obj,CashAdvance) else await db.get(CashAdvance,obj.cash_advance_id)
        return bool(advance and ((employee is not None and advance.payer_id in owner_ids) or financial_reader(user,'cash_advances')))
    if isinstance(obj,ExpenseApproval):return (employee is not None and obj.applicant_id in owner_ids) or financial_reader(user,'expense_approval')
    if isinstance(obj,ExpenseRecord) and employee is not None:
        # Automatic accounting references do not remove the actual beneficiary's receipt access.
        for model,column in ((Reimbursement,Reimbursement.employee_id),(PayrollRecord,PayrollRecord.employee_id),(ExpenseApproval,ExpenseApproval.applicant_id)):
            own_values=[own_eid] if model is PayrollRecord else list(owner_ids)
            found=(await db.execute(select(model.id).where(model.expense_record_id==obj.id,column.in_(own_values),model.warehouse_id==obj.warehouse_id))).first()
            if found:return True
    if isinstance(obj,PayableBill) and user.role == Role.SUPERVISOR:
        return field == 'bill_attachment' and bool(obj.purchase_order_id) and has_menu(user,'suppliers')
    if isinstance(obj,(PurchaseOrder,PurchaseReceiptEvent)):
        return user.role in (Role.SUPERVISOR,Role.STAFF) and has_menu(user,'suppliers')
    if isinstance(obj,RechargeDeclaration) and employee is not None and obj.declarer_id in owner_ids:return True
    return financial_reader(user,key)


async def private_reference_access(db,user,target,references):
    from app.api.secure_uploads import matches,reference_filter,upload_root
    parts=target.split('/')
    if len(parts)<3 or parts[0]!='uploads' or not parts[1].isdigit():return False
    wid=int(parts[1])
    if wid not in get_wh_ids(user) or user.role == Role.SUPER_ADMIN:return False
    employee=await own_employee(db,user)
    if employee is not None and employee.warehouse_id != wid:employee=None
    owner_ids=await identities(db,user) if employee is not None else set()
    referenced=False
    for model,fields,key,parent_type in references:
        columns=[getattr(model,field) for field in fields]
        query=select(model,parent_type).join(parent_type) if parent_type else select(model)
        rows=(await db.execute(query.where(reference_filter(columns,target)))).all()
        for row in rows:
            obj=row[0];parent=row[1] if parent_type else None
            for field in fields:
                if not matches(getattr(obj,field),target):continue
                referenced=True
                actual_wid=getattr(parent if parent_type else obj,'warehouse_id',None)
                if actual_wid != wid or not await reference_allowed(db,user,obj,parent,field,employee,owner_ids,key):return False
    if referenced:return True
    # Pending generic uploads are private to their real uploader, never any same-warehouse administrator.
    if user.role not in (Role.WAREHOUSE_ADMIN,Role.STAFF,Role.SUPERVISOR):return False
    try:
        path=upload_root().joinpath(*parts[1:]).resolve()
        if not path.is_relative_to(upload_root()):return False
        return json.loads(path.with_suffix(path.suffix+'.owner.json').read_text()).get('user_id')==user.id
    except (OSError,ValueError):return False
