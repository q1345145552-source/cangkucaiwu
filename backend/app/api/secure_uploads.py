"""Private upload reads: current account, warehouse and actual owning business record.

The file-only HttpOnly cookie lets existing img/a/download elements authenticate
without putting tokens into URLs or exposing uploads through nginx aliases.
"""
import json
import os
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.core.permissions import get_current_user, get_wh_ids, Role
from app.core.employee_access import own_employee, attendance_supervisor
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.models.clock_in_records import ClockInRecord
from app.models.attendance import LeaveRequest
from app.models.employee import Employee
from app.models.payroll import PayrollRecord
from app.models.income_expense import ExpenseRecord, IncomeRecord
from app.models.expense_fund import ExpenseFund, ExpenseFundItem
from app.models.reimbursement import Reimbursement
from app.models.recharge import RechargeDeclaration
from app.models.cash_advance import CashAdvance
from app.models.cash_advance_repayment import CashAdvanceRepayment
from app.models.expense_approval import ExpenseApproval
from app.models.payable import PayableBill
from app.models.market import MarketItem
from app.models.overtime import OvertimeTask, OvertimeAssignment
from app.models.reimbursement import ReimbursementItem
from app.models.reimbursement_payment import ReimbursementPayment
from app.models.supplier import PurchaseOrder
from app.services.image_utils import thumb_path_of

router = APIRouter()
COOKIE = "wf_attachment_session"

PRIVATE_FILES = [
    (Employee, ("photo_path","passport_photo_path","work_permit_photo_path"), "employees", None),
    (PayrollRecord,("signature_path",),"payroll",None),
    (ClockInRecord,("photo_path",),"attendance",None),
    (LeaveRequest,("photo_path",),"leave",None),
    (ExpenseRecord,("voucher",),"operating",None), (IncomeRecord,("voucher",),"other_income_expense",None),
    (RechargeDeclaration,("screenshot",),"recharge",None),
    (CashAdvance,("voucher_path",),"cash_advances",None), (CashAdvanceRepayment,("voucher_path",),"cash_advances",None),
    (ExpenseApproval,("voucher_path","payment_voucher"),"expense_approval",None),
    (Reimbursement,("payment_voucher_path",),"reimbursement",None),
    (ReimbursementPayment,("voucher_path",),"reimbursement",None),
    (PayableBill,("payment_voucher","voucher","bill_attachment"),"payable",None),
    (PurchaseOrder,("receipt_file",),"suppliers",None),
    (ExpenseFundItem,("receipt",),"expense_fund",ExpenseFund),
    (ReimbursementItem,("receipt",),"reimbursement",Reimbursement),
    (OvertimeAssignment,("dispute_photo",),"overtime",OvertimeTask),
]


def upload_root():
    return Path(os.environ.get("UPLOAD_DIR", "/app/uploads")).resolve()


def mark_temporary_upload(path, user):
    """Only generic, not-yet-attached uploads need owner metadata for their preview."""
    target = upload_root().joinpath(*Path(path).parts[1:]).resolve()
    if target.is_relative_to(upload_root()):
        target.with_suffix(target.suffix + ".owner.json").write_text(json.dumps({"user_id":user.id}))


def variants(path):
    return {path.lstrip("/"), thumb_path_of(path.lstrip("/"))}


def matches(value, target):
    if not value:
        return False
    try:
        values = json.loads(value) if str(value).startswith("[") else [value]
    except (ValueError, TypeError):
        return False
    return isinstance(values, list) and any(target in variants(v) for v in values if isinstance(v,str))


def reference_filter(columns, target):
    filename=Path(target)
    stem=filename.stem.removesuffix("_thumb")
    prefix=str(filename.with_name(stem))
    # Narrow database results first; exact parsed path/thumbnail matching still decides access.
    return or_(*(column.contains(prefix,autoescape=True) for column in columns))


async def has_private_reference(db, target):
    """Publishing a market image must never turn an existing payroll/HR/voucher file public."""
    for model, fields, _, _ in PRIVATE_FILES:
        columns = [getattr(model, field) for field in fields]
        rows = (await db.execute(select(*columns).where(reference_filter(columns, target)))).all()
        if any(matches(value, target) or matches(value, thumb_path_of(target)) for row in rows for value in row):
            return True
    return False


async def may_read_market_image(db, user, target):
    if user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        return False
    if user.role in (Role.SUPERVISOR, Role.STAFF) and MENU_PERMISSIONS_BY_KEY['market'].label not in (user.extra_permissions or []):
        return False
    items = (await db.execute(select(MarketItem).where(reference_filter([MarketItem.image], target)))).scalars().all()
    visible = any(matches(item.image, target) and (user.role == Role.SUPER_ADMIN or item.status == 'approved' or item.uploader_id == user.id) for item in items)
    if not visible and user.role == Role.SUPER_ADMIN and Path(target).parent.name == 'market':
        local = upload_root().joinpath(*Path(target).parts[1:])
        try:
            visible = json.loads(local.with_suffix(local.suffix+'.owner.json').read_text()).get('user_id') == user.id
        except (OSError, ValueError):
            pass
    return visible and not await has_private_reference(db, target)


async def may_read(db, user, target):
    if await may_read_market_image(db, user, target):
        return True
    # Platform uploads stay private until published, even to the source warehouse admin.
    if Path(target).parent.name == 'market':
        return False
    if user.role == Role.SUPER_ADMIN:
        return False
    wid = int(target.split("/")[1])
    if wid not in get_wh_ids(user):
        return False
    if user.role == Role.WAREHOUSE_ADMIN:
        return True
    if user.role == Role.WAREHOUSE_LABOR or attendance_supervisor(user):
        employee = await own_employee(db,user)
        own = [] if employee is None or employee.warehouse_id != wid else [
            select(ClockInRecord.photo_path).where(ClockInRecord.warehouse_id==wid,ClockInRecord.user_id==user.id),
            select(LeaveRequest.photo_path).where(LeaveRequest.warehouse_id==wid,LeaveRequest.employee_id==employee.id),
            select(OvertimeAssignment.dispute_photo).join(OvertimeTask).where(OvertimeTask.warehouse_id==wid,
                OvertimeAssignment.employee_id==employee.id,OvertimeAssignment.user_id==user.id),
        ]
        for query in own:
            query=query.where(reference_filter(list(query.selected_columns),target))
            if any(matches(value,target) for value in (await db.execute(query)).scalars()):
                return True
        if user.role == Role.WAREHOUSE_LABOR:
            return False
    if user.role not in (Role.SUPERVISOR,Role.STAFF):
        return False
    if not user.extra_permissions:
        return False
    # Match references before considering unsubmitted upload previews, so revocation applies immediately.
    referenced = False
    for model,fields,key,parent in PRIVATE_FILES:
        columns=[getattr(model,f) for f in fields]
        query = select(*columns).where(reference_filter(columns,target))
        if parent:
            query = query.join(parent).where(parent.warehouse_id==wid)
        else:
            query = query.where(model.warehouse_id==wid)
        for row in (await db.execute(query)).all():
            if any(matches(value,target) for value in row):
                referenced = True
                if MENU_PERMISSIONS_BY_KEY[key].label in (user.extra_permissions or []):
                    return True
    market_images = (await db.execute(select(MarketItem.image).where(reference_filter([MarketItem.image], target)))).scalars()
    referenced = referenced or any(matches(value, target) for value in market_images)
    if not referenced and user.extra_permissions:
        local = upload_root().joinpath(*Path(target).parts[1:])
        try:
            return json.loads(local.with_suffix(local.suffix+".owner.json").read_text()).get("user_id")==user.id
        except (OSError,ValueError):
            return False
    return False


@router.get("/uploads/{file_path:path}", openapi_extra={"x-access-kind":"protected_attachment"})
async def read_upload(file_path: str, request: Request, db: AsyncSession=Depends(get_db)):
    parts = Path(file_path).parts
    root = upload_root()
    path = root.joinpath(*parts).resolve()
    if (not parts or not parts[0].isdigit() or not path.is_relative_to(root)
        or path.suffix.lower() not in (".png",".jpg",".jpeg",".webp",".pdf") or not path.is_file()):
        raise HTTPException(404,"附件不存在")
    header = request.headers.get("Authorization", "")
    token = header[7:] if header.startswith("Bearer ") else request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401,"请先登录")
    user = await get_current_user(request,HTTPAuthorizationCredentials(scheme="Bearer",credentials=token),db)
    if not await may_read(db,user,"uploads/"+"/".join(parts)):
        raise HTTPException(403,"无权访问")
    return FileResponse(path,headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})
