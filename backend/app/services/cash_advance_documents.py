"""待付单据的只读投影与垫款用途快照，不调用任何付款或归还动作。"""
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select, func, delete

from app.models.cash_advance import CashAdvanceDocument
from app.models.employee import Employee
from app.models.employee_advance import EmployeeAdvance
from app.models.payable import PayableBill
from app.models.payroll import PayrollRecord
from app.models.reimbursement import Reimbursement
from app.models.supplier import Supplier
from app.models.user import User
from app.services.cash_advance_payroll import PAYROLL_CURRENCY

LABELS = {"payroll": "工资单", "payable": "应付账单", "reimbursement": "报销", "employee_advance": "预支"}
MODELS = {"payroll": PayrollRecord, "payable": PayableBill,
          "reimbursement": Reimbursement, "employee_advance": EmployeeAdvance}


def money(value):
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


def document_query(kind, warehouse_id, *, eligible=False):
    model = MODELS[kind]
    if kind in ("payroll", "employee_advance"):
        query = select(model, Employee.name).outerjoin(Employee, Employee.id == model.employee_id)
    elif kind == "payable":
        query = select(model, Supplier.name).outerjoin(Supplier, Supplier.id == model.supplier_id)
    else:
        query = select(model, User.display_name).outerjoin(User, User.id == model.employee_id)
    query = query.where(model.warehouse_id == warehouse_id)
    if eligible:
        if kind == "payroll":
            query = query.where(model.status == "confirmed", model.disbursed.is_not(True), model.voided.is_not(True), model.net_pay > 0)
        elif kind == "payable":
            query = query.where(model.status.in_(("pending", "partially_paid", "overdue")),
                                model.amount > func.coalesce(model.paid_amount, 0))
        elif kind == "reimbursement":
            query = query.where(model.status.in_(("approved", "partially_approved")), model.total_amount > 0)
        else:
            query = query.where(model.not_voided(), model.status.in_(("unpaid", "partial")),
                model.approval_status.in_(("pending", "approved")), model.amount > func.coalesce(model.deducted_amount, 0))
    return query


def project(kind, row, name):
    if kind == "payroll":
        amount, currency, number = money(row.net_pay), PAYROLL_CURRENCY, f"工资单 #{row.id}"
        day = row.settle_end_date
        title = f"{name or '员工'} · {row.period} · {row.settle_start_date or ''}至{day or ''}"
        detail = {"period": row.period, "settle_start_date": str(row.settle_start_date or ""),
                  "settle_end_date": str(day or ""), "gross_pay": row.gross_pay, "net_pay": row.net_pay,
                  "disbursed": bool(row.disbursed), "voided": bool(row.voided)}
    elif kind == "payable":
        amount, currency, number = money(row.amount) - money(row.paid_amount), row.currency or "THB", row.bill_number
        day, title = row.bill_date.date(), name or "供应商"
        detail = {"total_amount": float(money(row.amount)), "paid_amount": float(money(row.paid_amount)), "due_date": str(row.due_date.date())}
    elif kind == "reimbursement":
        amount, currency, number = money(row.total_amount), row.currency or "THB", f"报销单 #{row.id}"
        day, title = row.submit_date.date(), name or "报销人"
        detail = {"total_amount": row.total_amount, "funding_source": row.funding_source}
    else:
        amount, currency, number = money(row.amount) - money(row.deducted_amount), row.currency or "THB", f"预支单 #{row.id}"
        day, title = row.advance_date, name or "员工"
        detail = {"total_amount": row.amount, "settled_amount": row.deducted_amount or 0, "approval_status": row.approval_status}
    return {"document_type": kind, "document_type_label": LABELS[kind], "document_id": row.id,
            "document_number": number, "title": title, "document_date": day.isoformat() if day else None,
            "amount": float(max(amount, Decimal(0))), "currency": currency.upper(), "status": row.status, "detail": detail}


async def options(db, warehouse_id, kind, currency, search, page, page_size):
    model = MODELS[kind]
    query = document_query(kind, warehouse_id, eligible=True)
    query = query.where(func.upper(func.coalesce(model.currency, "THB")) == currency) if kind != "payroll" else query.where(PAYROLL_CURRENCY == currency)
    if search:
        name_col = Employee.name if kind in ("payroll", "employee_advance") else Supplier.name if kind == "payable" else User.display_name
        from sqlalchemy import or_
        clauses = [name_col.contains(search, autoescape=True)]
        if kind == "payable": clauses.append(model.bill_number.contains(search, autoescape=True))
        if search.isdecimal(): clauses.append(model.id == int(search))
        query = query.where(or_(*clauses))
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = (await db.execute(query.order_by(model.id.desc()).offset((page - 1) * page_size).limit(page_size))).all()
    return {"data": [project(kind, row, name) for row, name in rows], "total": total, "page": page, "page_size": page_size}


async def resolve(db, warehouse_id, currency, requested):
    keys = [(x.document_type, x.document_id) for x in requested]
    if len(set(keys)) != len(keys): raise HTTPException(400, "关联单据不能重复选择")
    documents = []
    for kind, rid in sorted(keys):
        model = MODELS[kind]
        result = (await db.execute(document_query(kind, warehouse_id, eligible=True).where(model.id == rid)
            .with_for_update(of=model).execution_options(populate_existing=True))).first()
        if result is None:
            raise HTTPException(400, f"{LABELS[kind]} #{rid} 不存在、不属于当前仓库或已不在待付范围，请刷新后重新选择")
        data = project(kind, *result)
        if data["currency"] != currency: raise HTTPException(400, "关联单据币种必须与垫款单一致")
        documents.append(data)
    return documents


def validate_difference(amount, documents, note):
    total = sum((money(d["amount"]) for d in documents), Decimal(0))
    if documents and money(amount) != total and not (note or "").strip():
        raise HTTPException(400, "垫款金额与关联单据合计不一致，请填写差额备注")
    return total


async def save_links(db, advance, documents):
    await db.execute(delete(CashAdvanceDocument).where(CashAdvanceDocument.cash_advance_id == advance.id,
        CashAdvanceDocument.warehouse_id == advance.warehouse_id))
    from datetime import date
    for d in documents:
        db.add(CashAdvanceDocument(cash_advance_id=advance.id, warehouse_id=advance.warehouse_id,
            document_type=d["document_type"], document_id=d["document_id"], document_number=d["document_number"],
            title=d["title"], document_date=date.fromisoformat(d["document_date"]) if d["document_date"] else None,
            amount=money(d["amount"]), currency=d["currency"]))
    await db.flush()


def link_dict(link):
    return {"id": link.id, "document_type": link.document_type, "document_type_label": LABELS[link.document_type],
        "document_id": link.document_id, "document_number": link.document_number, "title": link.title,
        "document_date": link.document_date.isoformat() if link.document_date else None,
        "amount": float(link.amount), "currency": link.currency}


async def links_map(db, advances):
    if not advances: return {}
    warehouses = {r.id: r.warehouse_id for r in advances}
    links = (await db.execute(select(CashAdvanceDocument).where(CashAdvanceDocument.cash_advance_id.in_(warehouses))
        .order_by(CashAdvanceDocument.id))).scalars().all()
    groups = {r.id: [] for r in advances}
    for link in links:
        if link.warehouse_id == warehouses[link.cash_advance_id]: groups[link.cash_advance_id].append(link_dict(link))
    return groups


async def view_document(db, warehouse_id, advance_id, link_id):
    link = (await db.execute(select(CashAdvanceDocument).where(CashAdvanceDocument.id == link_id,
        CashAdvanceDocument.cash_advance_id == advance_id, CashAdvanceDocument.warehouse_id == warehouse_id))).scalar_one_or_none()
    if link is None: raise HTTPException(404, "关联单据不存在或不属于当前仓库")
    kind = link.document_type
    row = (await db.execute(document_query(kind, warehouse_id).where(MODELS[kind].id == link.document_id))).first()
    return {"snapshot": link_dict(link), "current": project(kind, *row) if row else None,
            "notice": "此处为垫款用途关联，不代表该单据已由此垫款实际付款"}
