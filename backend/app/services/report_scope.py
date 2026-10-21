"""Selected, freshly authorised report scope shared by previews, details and exports."""
from dataclasses import dataclass
from datetime import date
from fastapi import Depends, Request
from app.database import get_db
from app.core.permissions import get_current_user
from app.services.money_period import money_period
from app.services.warehouse_summary import warehouse_scope
from app.services.wallet import day
from sqlalchemy import select, or_

@dataclass(frozen=True)
class ReportScope:
    warehouse_ids: list[int]
    start: date
    end: date

async def selected_report_scope(request: Request, start_date: str | None = None, end_date: str | None = None,
        month: str | None = None, year: str | None = None, warehouse_id: int | None = None,
        user=Depends(get_current_user), db=Depends(get_db)):
    warehouses = await warehouse_scope(db,user,request.headers.get('X-Warehouse-ID'),warehouse_id=warehouse_id)
    start,end = money_period(month,start_date,end_date,year=year,default_start=date(1900,1,1),default_end=date.max)
    return ReportScope([w.id for w in warehouses],start,end)

def scoped_query(db, scope, model, date_column=None):
    query=select(model).where(model.warehouse_id.in_(scope.warehouse_ids))
    if date_column is not None:
        query=query.where(day(db,date_column)>=scope.start,day(db,date_column)<=scope.end)
    return query

def payable_query(db, scope):
    from app.models.payable import PayableBill
    from app.models.supplier import PurchaseOrder
    b,p=PayableBill,PurchaseOrder
    return scoped_query(db,scope,b,b.due_date).outerjoin(p,b.purchase_order_id==p.id).where(
        b.status!='voided',or_(b.purchase_order_id.is_(None),p.status=='confirmed'))
