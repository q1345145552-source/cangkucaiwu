"""Quotation read/write follows supplier and independent SKU capabilities."""
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,StrictInt,Field
from sqlalchemy import select
from app.database import get_db
from app.models import Supplier,SupplierProduct,SupplierQuote,SupplierQuoteRevision
from app.core.permissions import check_staff_permission,require_non_labor
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.services.supplier_payable_read import current_supplier_warehouse
from app.services import sku_catalog as catalog,supplier_quotes as quotes

router=APIRouter(dependencies=[Depends(require_non_labor)])
async def reader(user=Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY['suppliers'].label))):
 catalog.require_read(user);return user
async def writer(user=Depends(reader)):
 catalog.require_write(user);return user

class TierRequest(BaseModel):
 model_config=ConfigDict(extra='forbid',strict=True)
 min_quantity:str|int|float;max_quantity:str|int|float|None;unit_price:str|int|float
class QuoteRequest(BaseModel):
 model_config=ConfigDict(extra='forbid',strict=True)
 code:str;request_key:str=Field(min_length=1,max_length=100);expected_product_version:str;expected_sku_version:str
 expected_quote_version:str|None=None;currency:str;unit:str;base_unit_factor:str|int|float|None=None;conversion_basis:str=''
 valid_from:str;valid_to:str;fees:dict;quality_tags:list[str]|None=None;lead_days:StrictInt|None=None;active:bool=True;tiers:list[TierRequest]
class PreviewItem(BaseModel):
 model_config=ConfigDict(extra='forbid',strict=True)
 product_id:StrictInt;quantity:str|int|float;quote_id:StrictInt|None=None
class PreviewRequest(BaseModel):
 model_config=ConfigDict(extra='forbid',strict=True)
 supplier_id:StrictInt;items:list[PreviewItem];requirements:dict|None=None

@router.get('/suppliers/{supplier_id}')
async def listing(supplier_id:int,user=Depends(reader),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 supplier=await db.get(Supplier,supplier_id)
 if not supplier or supplier.warehouse_id!=wid:raise HTTPException(404,'当前仓库未找到该供应商')
 products=(await db.execute(select(SupplierProduct).where(SupplierProduct.supplier_id==supplier_id).order_by(SupplierProduct.id))).scalars().all()
 rows=(await db.execute(select(SupplierQuote).where(SupplierQuote.warehouse_id==wid,SupplierQuote.product_id.in_([p.id for p in products])).order_by(SupplierQuote.id))).scalars().all()
 result=[]
 for p in products:
  _,mapping,sku=await quotes.source_context(db,wid,p)
  result.append({'id':p.id,'product_name':p.product_name,'spec':p.spec,'currency':p.currency,'unit':p.unit,'mapping':mapping,'sku':sku})
 return {'data':[await quotes.revision_data(db,q) for q in rows],'products':result,'can_manage':catalog.permission(user,'sku_catalog_manage'),
  'quantity_mode':'whole_units','tier_bounds':'按原报价单位数量，起点含、终点不含；空终点无上限。不同单位不猜箱数，折算小数原单位不自动取整。',
  'fees_note':'仅同明确费用口径的商品单价可比，不换汇，不宣称含未知费用的落地总成本。未知条件保持待确认。'}

@router.post('/products/{product_id}')
async def create(product_id:int,req:QuoteRequest,user=Depends(writer),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 return await quotes.save(db,wid,user,product_id,req.model_dump())

@router.put('/{quote_id}')
async def revise(quote_id:int,req:QuoteRequest,user=Depends(writer),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 quote=await quotes.owned_quote(db,wid,quote_id)
 return await quotes.save(db,wid,user,quote.product_id,req.model_dump(),quote_id)

@router.get('/{quote_id}/revisions')
async def history(quote_id:int,user=Depends(reader),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 quote=await quotes.owned_quote(db,wid,quote_id)
 rows=(await db.execute(select(SupplierQuoteRevision).where(SupplierQuoteRevision.quote_id==quote_id).order_by(SupplierQuoteRevision.revision.desc()))).scalars()
 return {'data':[await quotes.revision_data(db,quote,r) for r in rows],'immutable':True}

@router.post('/purchase-preview')
async def preview(req:PreviewRequest,user=Depends(reader),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 return await quotes.cart_preview(db,wid,req.supplier_id,[v.model_dump() for v in req.items],req.requirements)
