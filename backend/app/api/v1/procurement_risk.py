"""Owner-only evidence board. Success audit is the only write performed here."""
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field,StrictInt
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
from app.services import procurement_risk_reviews as reviews

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
 rows=result['data'][(page-1)*page_size:page*page_size]
 enriched=[{**row,'review':await reviews.state(db,wid,row,reviews.scope_of(values))} for row in rows]
 return {**result,'data':enriched,'page':page,'page_size':page_size}

@router.get('/export')
async def download(request:Request,values=Depends(selection),user=Depends(require_procurement_owner),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 result=await read(db,wid,values);content=service.export(result);await audit(db,request,user,wid,{**values,'month':result['month']},'export')
 return Response(content,media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="procurement-risk-{result["month"]}.csv"','Cache-Control':'private, no-store'})

@router.get('/signals/{signal_id}')
async def detail(signal_id:str,request:Request,values=Depends(selection),user=Depends(require_procurement_owner),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 result=await read(db,wid,values);found=next((r for r in result['data'] if r['id']==signal_id),None)
 if found is None:raise HTTPException(404,'当前仓库及筛选范围未找到该线索')
 await audit(db,request,user,wid,{**values,'month':result['month']},'view_detail',signal_id)
 return {'data':{**found,'review':await reviews.state(db,wid,found,reviews.scope_of(values))},'version':service.VERSION,'month':result['month'],'warehouse_id':wid}

class ReviewRequest(BaseModel):
 model_config=ConfigDict(extra='forbid')
 request_key:str=Field(min_length=1,max_length=100)
 expected_evidence_version:str=Field(min_length=64,max_length=64)
 expected_latest_review_id:StrictInt=Field(ge=0)
 conclusion:Literal['pending','cleared','follow_up']
 review_reason:str=Field(max_length=1000)

@router.post('/signals/{signal_id}/reviews')
async def save_review(signal_id:str,req:ReviewRequest,values=Depends(selection),user=Depends(require_procurement_owner),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 return await reviews.append(db,wid,user,signal_id,values,**req.model_dump())

@router.get('/reviews')
async def review_history(request:Request,values=Depends(filters),rule:Rule|None=None,all_scopes:bool=False,page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),user=Depends(require_procurement_owner),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 rows=await reviews.listing(db,wid,values,rule,all_scopes)
 await audit(db,request,user,wid,{**reviews.scope_of(values),'rule':rule,'all_scopes':all_scopes},'view_reviews')
 return {'data':rows[(page-1)*page_size:page*page_size],'total':len(rows),'page':page,'notice':'历史结论与证据原样保留，不代表当前证据仍有效，也不是业务例外授权'}

@router.get('/reviews/export')
async def export_reviews(request:Request,values=Depends(filters),rule:Rule|None=None,all_scopes:bool=False,user=Depends(require_procurement_owner),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 rows=await reviews.listing(db,wid,values,rule,all_scopes);content=reviews.export(rows)
 await audit(db,request,user,wid,{**reviews.scope_of(values),'rule':rule,'all_scopes':all_scopes},'export_reviews')
 return Response(content,media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="procurement-risk-review-history.csv"','Cache-Control':'private, no-store'})
