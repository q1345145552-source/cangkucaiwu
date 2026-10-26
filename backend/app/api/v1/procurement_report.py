"""Supplier-scoped monthly price reference. All endpoints share one read-only calculation."""
from typing import Literal
from fastapi import APIRouter,Depends,Query
from fastapi.responses import Response
from app.database import get_db
from app.core.permissions import check_staff_permission,require_non_labor
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.services.supplier_payable_read import current_supplier_warehouse
from app.services import procurement_month_report as service
router=APIRouter(dependencies=[Depends(require_non_labor),Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY['suppliers'].label))])

def filters(month:str|None=None,supplier_id:int|None=Query(None,gt=0),orderer_id:int|None=Query(None,gt=0),currency:Literal['THB','CNY']|None=None):
 return {'month':month,'supplier_id':supplier_id,'orderer_id':orderer_id,'currency':currency}

@router.get('')
async def monthly(values=Depends(filters),page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),view:Literal['all','non_lowest','unavailable']='all',wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 return await service.report(db,wid,page=page,page_size=page_size,view=view,**values)

@router.get('/export')
async def download(values=Depends(filters),view:Literal['all','non_lowest','unavailable']='all',wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 content=await service.export(db,wid,view=view,**values);month=service.parse_month(values['month'])[0]
 return Response(content,media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="purchase-price-reference-{month}.csv"','Cache-Control':'private, no-store'})

@router.get('/orders/{order_id}/lines/{line_ref}')
async def detail(order_id:int,line_ref:str,wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 return await service.line_detail(db,wid,order_id,line_ref)
