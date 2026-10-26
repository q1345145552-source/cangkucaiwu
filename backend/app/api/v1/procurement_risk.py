"""Owner-only evidence board. Success audit is the only write performed here."""
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query,Request
from fastapi.responses import Response
from app.database import get_db
from app.core.permissions import get_current_user,check_staff_permission,require_non_labor,Role
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.core.client_ip import get_client_ip
from app.core.ip_location import get_ip_location
from app.core.timezone import thai_now
from app.models import AuditLog
from app.services.supplier_payable_read import current_supplier_warehouse
from app.api.v1.procurement_report import filters
from app.services import procurement_risk as service

async def require_procurement_owner(user=Depends(get_current_user)):
 if user.role!=Role.WAREHOUSE_ADMIN:raise HTTPException(403,'仅仓库管理员可以查看采购风险看板')
 return user

router=APIRouter(dependencies=[Depends(require_procurement_owner),Depends(require_non_labor),Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY['suppliers'].label))])
State=Literal['attention','normal','unavailable','info']
Rule=Literal['historical_price','non_lowest','new_supplier','concentration','split_window','self_receipt','receipt_quantity']
async def selection(values=Depends(filters),rule:Rule|None=None,state:State|None=None):return {**values,'rule':rule,'state':state}

async def read(db,wid,values):
 options=dict(values);rule=options.pop('rule');state=options.pop('state')
 return service.filtered_report(await service.calculate(db,wid,**options),rule,state)

async def audit(db,request,user,wid,values,action,signal_id=None):
 ip=get_client_ip(request)
 db.add(AuditLog(user_id=user.id,warehouse_id=wid,action_type=action,module='procurement_risk',ip_address=ip,**get_ip_location(ip),detail={'filters':values,'rule_version':service.VERSION,'action':action,'at':thai_now().isoformat(),'signal_id':signal_id}))
 await db.flush()

@router.get('')
async def board(request:Request,values=Depends(selection),page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),user=Depends(require_procurement_owner),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 result=await read(db,wid,values);await audit(db,request,user,wid,{**values,'month':result['month']},'view')
 return {**result,'data':result['data'][(page-1)*page_size:page*page_size],'page':page,'page_size':page_size}

@router.get('/export')
async def download(request:Request,values=Depends(selection),user=Depends(require_procurement_owner),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 result=await read(db,wid,values);content=service.export(result);await audit(db,request,user,wid,{**values,'month':result['month']},'export')
 return Response(content,media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="procurement-risk-{result["month"]}.csv"','Cache-Control':'private, no-store'})

@router.get('/signals/{signal_id}')
async def detail(signal_id:str,request:Request,values=Depends(selection),user=Depends(require_procurement_owner),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 result=await read(db,wid,values);found=next((r for r in result['data'] if r['id']==signal_id),None)
 if found is None:raise HTTPException(404,'当前仓库及筛选范围未找到该线索')
 await audit(db,request,user,wid,{**values,'month':result['month']},'view_detail',signal_id)
 return {'data':found,'version':service.VERSION,'month':result['month'],'warehouse_id':wid}
