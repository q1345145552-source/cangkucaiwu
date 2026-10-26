"""Warehouse catalog: read and manage grants are separate; no automatic grants."""
import json
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import select,delete
from app.database import get_db
from app.models import StandardSKU,SupplierCategory,Supplier,SupplierProduct,SupplierWarehouseTag,SupplierTagLink,ProductSkuMappingEvent
from app.core.permissions import get_current_user,require_non_labor,check_staff_permission
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.services.supplier_payable_read import current_supplier_warehouse
from app.services import sku_catalog as catalog
from app.services.payable_creation import fingerprint
from app.services.data_history import record_history

router=APIRouter(dependencies=[Depends(require_non_labor)])

async def reader(user=Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY['sku_catalog'].label))):
 catalog.require_read(user);return user
async def writer(user=Depends(reader)):
 catalog.require_write(user);return user
async def mapper(user=Depends(writer)):
 catalog.require_mapping(user);return user

class SKURequest(BaseModel):
 model_config=ConfigDict(extra='forbid')
 code:str;name:str;attributes:dict;base_unit:str;category_id:int|None=None;active:bool=True;expected_version:str|None=None

class MappingRequest(BaseModel):
 model_config=ConfigDict(extra='forbid',strict=True)
 sku_id:int|None;expected_product_version:str;expected_sku_version:str|None=None
 confirmed_attributes:dict|None=None;base_unit_factor:str|float|None=None
 request_key:str=Field(min_length=1,max_length=100);reason:str=Field(min_length=1,max_length=1000)

class TagRequest(BaseModel):
 name:str=Field(min_length=1,max_length=50);active:bool=True;expected_version:str|None=None

class TagAssignment(BaseModel):
 model_config=ConfigDict(extra='forbid',strict=True)
 tag_ids:list[int];expected_version:str

def tag_data(row):
 d={k:getattr(row,k) for k in ('id','warehouse_id','name','active','revision')};return {**d,'version':fingerprint(d)}

@router.get('/reference')
async def reference(user=Depends(reader),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 cats=(await db.execute(select(SupplierCategory).order_by(SupplierCategory.sort_order,SupplierCategory.id))).scalars()
 return {'categories':[{'id':c.id,'name':c.name,'active':c.is_active=='true','read_only':True} for c in cats],
  'units':[{'code':k,'label':v} for k,v in catalog.UNITS.items()], 'can_manage':catalog.permission(user,'sku_catalog_manage'),
  'can_map':catalog.permission(user,'sku_catalog_manage') and catalog.permission(user,'suppliers'),
  'normalization':'SKU编码仅ASCII去首尾空白并大写；结构属性键排序，不模糊解析名称或包装；箱/包换算未知留空'}

@router.get('')
async def listing(include_inactive:bool=False,user=Depends(reader),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 q=select(StandardSKU).where(StandardSKU.warehouse_id==wid)
 if not include_inactive:q=q.where(StandardSKU.active.is_(True))
 return {'data':[catalog.sku_data(r) for r in (await db.execute(q.order_by(StandardSKU.code))).scalars()]}

@router.post('')
async def create(req:SKURequest,user=Depends(writer),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 return await catalog.save_sku(db,wid,user,req.model_dump())

@router.put('/{sku_id}')
async def update(sku_id:int,req:SKURequest,user=Depends(writer),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 return await catalog.save_sku(db,wid,user,req.model_dump(),sku_id)

@router.get('/products/{product_id}/candidates')
async def candidates(product_id:int,confirmed_attributes:str|None=None,user=Depends(reader),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 if not catalog.permission(user,'suppliers'):raise HTTPException(403,'无此操作权限，需要供应商管理权限')
 product=await catalog.product_owned(db,product_id,wid)
 from app.services.product_import import json_value
 proposed=json_value(confirmed_attributes) if confirmed_attributes is not None else None
 return await catalog.suggestions(db,wid,product,proposed)

@router.post('/products/{product_id}/mapping')
async def mapping(product_id:int,req:MappingRequest,user=Depends(mapper),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 return await catalog.map_product(db,wid,user,product_id,req.model_dump())

@router.get('/products/{product_id}/mapping-history')
async def mapping_history(product_id:int,user=Depends(reader),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 if not catalog.permission(user,'suppliers'):raise HTTPException(403,'无此操作权限，需要供应商管理权限')
 await catalog.product_owned(db,product_id,wid)
 rows=(await db.execute(select(ProductSkuMappingEvent).where(ProductSkuMappingEvent.warehouse_id==wid,ProductSkuMappingEvent.product_id==product_id).order_by(ProductSkuMappingEvent.id.desc()))).scalars()
 return {'data':[{'id':r.id,'before':r.before,'after':r.after,'reason':r.reason,'operator_id':r.operator_id,'operator_name':r.operator_name,'created_at':r.created_at} for r in rows]}

@router.get('/history-candidates')
async def history_candidates(user=Depends(reader),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 if not catalog.permission(user,'suppliers'):raise HTTPException(403,'无此操作权限，需要供应商管理权限')
 rows=(await db.execute(select(SupplierProduct).join(Supplier).where(Supplier.warehouse_id==wid,SupplierProduct.standard_sku_id.is_(None)).order_by(SupplierProduct.id))).scalars()
 return {'read_only':True,'data':[await catalog.suggestions(db,wid,r) for r in rows],'message':'旧产品候选报告；不回填、不自动映射，缺规格和换算保持未知'}

@router.get('/tags')
async def tags(user=Depends(reader),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 rows=(await db.execute(select(SupplierWarehouseTag).where(SupplierWarehouseTag.warehouse_id==wid).order_by(SupplierWarehouseTag.id))).scalars()
 return {'data':[tag_data(r) for r in rows]}

@router.post('/tags')
async def create_tag(req:TagRequest,user=Depends(writer),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 await catalog.lock(db,wid);name=catalog.label(req.name,'仓内标签',50)
 old=(await db.execute(select(SupplierWarehouseTag).where(SupplierWarehouseTag.warehouse_id==wid,SupplierWarehouseTag.name==name))).scalar_one_or_none()
 if old:raise HTTPException(409,'本仓已存在该标签，未重复创建')
 r=SupplierWarehouseTag(warehouse_id=wid,name=name,active=req.active);db.add(r);await db.flush()
 await record_history(db,module='sku_catalog',record_id=r.id,operation_type='create_tag',operator=user,before=None,after=tag_data(r),warehouse_id=wid)
 return tag_data(r)

@router.put('/tags/{tag_id}')
async def update_tag(tag_id:int,req:TagRequest,user=Depends(writer),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 await catalog.lock(db,wid);r=await db.get(SupplierWarehouseTag,tag_id)
 if not r or r.warehouse_id!=wid:raise HTTPException(404,'当前仓库未找到该标签')
 before=tag_data(r)
 if req.expected_version!=before['version']:raise HTTPException(409,'标签已被修改，请刷新')
 name=catalog.label(req.name,'仓内标签',50)
 other=(await db.execute(select(SupplierWarehouseTag.id).where(SupplierWarehouseTag.warehouse_id==wid,SupplierWarehouseTag.name==name,SupplierWarehouseTag.id!=r.id))).first()
 if other:raise HTTPException(409,'本仓标签名重复')
 r.name=name;r.active=req.active;r.revision+=1;await db.flush()
 await record_history(db,module='sku_catalog',record_id=r.id,operation_type='update_tag',operator=user,before=before,after=tag_data(r),warehouse_id=wid)
 return tag_data(r)

@router.get('/suppliers/{supplier_id}/tags')
async def supplier_tags(supplier_id:int,user=Depends(reader),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 if not catalog.permission(user,'suppliers'):raise HTTPException(403,'无此操作权限，需要供应商管理权限')
 s=await db.get(Supplier,supplier_id)
 if not s or s.warehouse_id!=wid:raise HTTPException(404,'当前仓库未找到该供应商')
 ids=list((await db.execute(select(SupplierTagLink.tag_id).where(SupplierTagLink.warehouse_id==wid,SupplierTagLink.supplier_id==supplier_id).order_by(SupplierTagLink.tag_id))).scalars())
 return {'tag_ids':ids,'version':fingerprint(ids)}

@router.put('/suppliers/{supplier_id}/tags')
async def assign_tags(supplier_id:int,req:TagAssignment,user=Depends(mapper),wid=Depends(current_supplier_warehouse),db=Depends(get_db)):
 await catalog.lock(db,wid);current=await supplier_tags(supplier_id,user,wid,db)
 if req.expected_version!=current['version']:raise HTTPException(409,'供应商标签已变更，请刷新，未覆盖他人修改')
 ids=sorted(set(req.tag_ids))
 if len(ids)!=len(req.tag_ids):raise HTTPException(400,'标签编号重复')
 for tid in ids:
  tag=await db.get(SupplierWarehouseTag,tid)
  if not tag or tag.warehouse_id!=wid or not tag.active:raise HTTPException(403,'标签不属于本仓或已停用')
 await db.execute(delete(SupplierTagLink).where(SupplierTagLink.warehouse_id==wid,SupplierTagLink.supplier_id==supplier_id))
 db.add_all([SupplierTagLink(warehouse_id=wid,supplier_id=supplier_id,tag_id=tid) for tid in ids]);await db.flush()
 await record_history(db,module='sku_catalog',record_id=supplier_id,operation_type='assign_supplier_tags',operator=user,before=current,after={'tag_ids':ids},warehouse_id=wid)
 return {'tag_ids':ids,'version':fingerprint(ids)}
