"""Duty settings and explicit one-use exceptions; only owner mutation, no implicit grants."""
from datetime import datetime
from typing import Literal
from fastapi import APIRouter,Depends,Query
from pydantic import BaseModel,ConfigDict,Field,StrictBool,StrictInt
from sqlalchemy import select,func
from app.database import get_db
from app.models import ProcurementActionException
from app.core.permissions import get_current_user,check_staff_permission,require_non_labor
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.api.v1.procurement_risk import require_procurement_owner
from app.services.supplier_payable_read import current_supplier_warehouse
from app.services import procurement_controls as service

router=APIRouter(dependencies=[Depends(require_non_labor),Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY['suppliers'].label))])
Action=Literal['approve','reject','receive']
class StrictBody(BaseModel):
 model_config=ConfigDict(extra='forbid')
 request_key:str=Field(min_length=1,max_length=100)
class PolicySet(StrictBody):
 no_self_approve:StrictBool
 no_self_receive:StrictBool
 expected_version:str=Field(min_length=64,max_length=64)
 change_reason:str=Field(max_length=1000)
class Grant(StrictBody):
 po_id:StrictInt=Field(gt=0)
 action:Action
 operator_id:StrictInt=Field(gt=0)
 expected_policy_version:str=Field(min_length=64,max_length=64)
 expected_business_version:str=Field(min_length=64,max_length=64)
 expires_at:datetime
 grant_reason:str=Field(max_length=1000)
class Revoke(StrictBody):
 revoke_reason:str=Field(max_length=1000)

@router.get('/policy')
async def get_policy(user=Depends(require_procurement_owner),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 return await service.policy(db,wid)
@router.put('/policy')
async def set_policy(req:PolicySet,user=Depends(require_procurement_owner),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 return await service.update_policy(db,wid,user,**req.model_dump())
@router.get('/orders/{po_id}/context')
async def get_context(po_id:int,action:Action,operator_id:int|None=Query(None,gt=0),user=Depends(get_current_user),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 return await service.context(db,wid,user,po_id,action,operator_id)
@router.get('/exceptions')
async def list_exceptions(po_id:int|None=Query(None,gt=0),page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),user=Depends(require_procurement_owner),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 if po_id is not None:await service.owned_order(db,wid,po_id)
 q=select(ProcurementActionException).where(ProcurementActionException.warehouse_id==wid)
 if po_id is not None:q=q.where(ProcurementActionException.purchase_order_id==po_id)
 count=(await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
 rows=(await db.execute(q.order_by(ProcurementActionException.id.desc()).offset((page-1)*page_size).limit(page_size))).scalars().all()
 p=await service.policy(db,wid);data=[]
 for row in rows:
  value=service.grant_value(row);po=await service.owned_order(db,wid,row.purchase_order_id)
  v=await service.business(db,po,row.action)
  value['effective']=row.status=='active' and row.expires_at>service.thai_now() and row.policy_version==p['version'] and row.business_version==v
  data.append(value)
 return {'data':data,'total':count,'page':page}
@router.post('/exceptions')
async def grant(req:Grant,user=Depends(require_procurement_owner),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 return await service.grant(db,wid,user,**req.model_dump())
@router.post('/exceptions/{ident}/revoke')
async def revoke(ident:int,req:Revoke,user=Depends(require_procurement_owner),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 return await service.revoke(db,wid,user,ident,**req.model_dump())

@router.get('/exceptions/{ident}')
async def exception_detail(ident:int,user=Depends(require_procurement_owner),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 from fastapi import HTTPException
 row=await db.get(ProcurementActionException,ident)
 if row is None or row.warehouse_id!=wid:raise HTTPException(404,'本仓未找到该例外授权')
 po=await service.owned_order(db,wid,row.purchase_order_id);p=await service.policy(db,wid);v=await service.business(db,po,row.action)
 return {'data':{**service.grant_value(row),'effective':row.status=='active' and row.expires_at>service.thai_now() and row.policy_version==p['version'] and row.business_version==v}}
