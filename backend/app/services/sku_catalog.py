"""Explicit, versioned human mappings. No fuzzy identities or implicit pack conversions."""
from app.core.action_access import has_module
import json,re
from decimal import Decimal,InvalidOperation
from fastapi import HTTPException
from sqlalchemy import select
from app.models import StandardSKU,SupplierCategory,Supplier,SupplierProduct,ProductSkuMappingEvent
from app.core.permissions import Role
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.core.timezone import thai_now
from app.services.payable_creation import fingerprint
from app.services.purchase_matching import scope_lock
from app.services.data_history import record_history
from app.services.sku_catalog_migration import ensure_catalog_guards

UNITS={'piece':'个','item':'件','set':'套','roll':'卷','box':'箱','pack':'包','bag':'袋','pallet':'托','dozen':'打','mm':'毫米','cm':'厘米','m':'米','g':'克','kg':'千克','ml':'毫升','l':'升'}
UNIT_ALIASES={**{k:k for k in UNITS},**{v:k for k,v in UNITS.items()},'只':'piece','公斤':'kg','PCS':'piece','pcs':'piece'}

def permission(user,key):
 return user.role==Role.WAREHOUSE_ADMIN or user.role in (Role.SUPERVISOR,Role.STAFF) and has_module(user,key)

def require_read(user):
 if not permission(user,'sku_catalog'):raise HTTPException(403,'无此操作权限，需要标准SKU目录权限')

def require_write(user):
 require_read(user)
 if not permission(user,'sku_catalog_manage'):raise HTTPException(403,'无此操作权限，需要标准SKU管理权限')

def require_mapping(user):
 require_write(user)
 if not permission(user,'suppliers'):raise HTTPException(403,'无此操作权限，需要供应商管理权限')

def label(value,name,limit):
 if not isinstance(value,str) or not value.strip() or len(value.strip())>limit:raise HTTPException(400,f'{name}不能为空且最多{limit}字')
 return value.strip()

def code(value):
 value=label(value,'SKU编码',64).upper()
 if not re.fullmatch(r'[A-Z0-9][A-Z0-9._-]{0,63}',value):raise HTTPException(400,'SKU编码只能包含英文字母、数字、点、下划线和短横线')
 return value

def unit(value,strict=True):
 result=UNIT_ALIASES.get(value.strip()) if isinstance(value,str) else None
 if strict and result is None:raise HTTPException(400,'无效单位，请从基本单位清单选择；不自动推断包装换算')
 return result

def attributes(value,*,required=False,depth=0):
 if depth==0:
  if value is None and not required:return None
  if not isinstance(value,dict) or required and not value:raise HTTPException(400,'结构化规格必须是非空JSON对象')
 if depth>4:raise HTTPException(400,'结构化规格层级不能超过4层')
 if isinstance(value,dict):
  if len(value)>30:raise HTTPException(400,'结构化规格属性过多')
  result={}
  for key,item in value.items():
   key=label(key,'规格属性名',64)
   if key in result:raise HTTPException(400,'结构化规格含重复属性名')
   result[key]=unit(item) if key=='unit' else attributes(item,depth=depth+1)
  result=dict(sorted(result.items()))
 elif isinstance(value,list):
  if len(value)>30:raise HTTPException(400,'结构化规格列表过长')
  result=[attributes(v,depth=depth+1) for v in value]
 elif isinstance(value,bool):result=value
 elif isinstance(value,(int,float,Decimal)):
  try:d=Decimal(str(value))
  except InvalidOperation:raise HTTPException(400,'规格数值无效')
  if not d.is_finite() or abs(d)>Decimal('1000000000') or d.as_tuple().exponent < -8:raise HTTPException(400,'规格数值超出有效范围')
  result=int(d) if d==d.to_integral_value() else float(d)
 elif isinstance(value,str):result=label(value,'规格属性值',256)
 else:raise HTTPException(400,'规格属性只支持对象、列表、文字、有限数字或布尔值；未知请不填该属性')
 if depth==0 and len(json.dumps(result,ensure_ascii=False))>8192:raise HTTPException(400,'结构化规格内容过长')
 return result

def scalar_factor(value):
 if value in (None,''):return None
 if isinstance(value,bool):raise HTTPException(400,'单位换算数必须是数字')
 try:d=Decimal(str(value))
 except (InvalidOperation,TypeError):raise HTTPException(400,'单位换算数无效')
 if not d.is_finite() or d<=0 or d>100000000 or d.as_tuple().exponent < -8:raise HTTPException(400,'单位换算数必须为正数，最多8位小数')
 return d

async def lock(db,wid):
 if not isinstance(wid,int) or wid<=0:raise HTTPException(400,'请先选择单个仓库')
 await scope_lock(db,wid);await ensure_catalog_guards(await db.connection())

def sku_data(row):
 data={k:getattr(row,k) for k in ('id','warehouse_id','code','name','attributes','base_unit','category_id','active','revision')}
 return {**data,'version':fingerprint(data)}

def product_state(row):
 data={k:getattr(row,k) for k in ('id','supplier_id','product_name','spec','unit','unit_price','currency','catalog_attributes','standard_sku_id','base_unit_factor','sku_snapshot','catalog_revision','catalog_active')}
 if data['base_unit_factor'] is not None:data['base_unit_factor']=format(Decimal(data['base_unit_factor']).normalize(),'f')
 return data

def product_version(row):return fingerprint(product_state(row))

async def product_owned(db,pid,wid,*,for_update=False):
 q=select(SupplierProduct).join(Supplier).where(SupplierProduct.id==pid,Supplier.warehouse_id==wid)
 if for_update:q=q.with_for_update(of=SupplierProduct)
 row=(await db.execute(q)).scalar_one_or_none()
 if row is None:raise HTTPException(404,'当前仓库未找到该供应商产品')
 return row

async def category_checked(db,cid):
 if cid is None:return
 row=await db.get(SupplierCategory,cid)
 if row is None or row.is_active!='true':raise HTTPException(400,'分类不存在或已停用；旧分类引用保留但不能用于新目录')

async def save_sku(db,wid,user,data,existing=None):
 await lock(db,wid)
 if existing is not None:
  row=(await db.execute(select(StandardSKU).where(StandardSKU.id==existing,StandardSKU.warehouse_id==wid).with_for_update())).scalar_one_or_none()
  if row is None:raise HTTPException(404,'当前仓库未找到SKU')
  if data.get('expected_version')!=sku_data(row)['version']:raise HTTPException(409,'SKU已被修改，请刷新后重新核对')
 else:row=None
 body={'code':code(data.get('code')),'name':label(data.get('name'),'SKU名称',200),'attributes':attributes(data.get('attributes'),required=True),
  'base_unit':unit(data.get('base_unit')),'category_id':data.get('category_id'),'active':data.get('active',True)}
 if row is None or row.category_id!=body['category_id']:await category_checked(db,body['category_id'])
 old=(await db.execute(select(StandardSKU).where(StandardSKU.warehouse_id==wid,StandardSKU.code==body['code']))).scalar_one_or_none()
 if old is not None and (row is None or old.id!=row.id):
  if row is None and all(getattr(old,k)==v for k,v in body.items()):return {**sku_data(old),'replayed':True}
  raise HTTPException(409,'本仓SKU编码已存在，名称、规格或基本单位不一致；未覆盖原目录')
 before=sku_data(row) if row else None
 if row is None:row=StandardSKU(warehouse_id=wid,created_by=user.id,**body);db.add(row)
 else:
  for k,v in body.items():setattr(row,k,v)
  row.revision+=1
 await db.flush()
 await record_history(db,module='sku_catalog',record_id=row.id,operation_type='create' if before is None else 'update',operator=user,
  before=before,after=sku_data(row),warehouse_id=wid)
 return sku_data(row)

async def suggestions(db,wid,product,proposed=None):
 attrs=attributes(proposed) if proposed is not None else product.catalog_attributes
 rows=(await db.execute(select(StandardSKU).where(StandardSKU.warehouse_id==wid,StandardSKU.active.is_(True)).order_by(StandardSKU.code))).scalars().all()
 result=[]
 for row in rows:
  same_attrs=bool(attrs) and attrs==row.attributes;same_name=product.product_name.strip()==row.name
  if not same_attrs and not same_name:continue
  raw=unit(product.unit,False);differences=[]
  if not attrs:differences.append('原产品没有已核实的结构规格，确认映射前须逐项填写')
  elif attrs!=row.attributes:differences.append('尺寸/材质/包装等结构属性不一致，不允许映射')
  if raw!=row.base_unit:differences.append('原报价单位与基本单位不同或未知；换算数量未知，不推断')
  result.append({**sku_data(row),'matched_fields':(['结构化规格'] if same_attrs else [])+(['显示名称'] if same_name else []),
   'differences':differences,'can_map':not attrs or same_attrs,'auto_mapped':False})
 return {'product_id':product.id,'product_name':product.product_name,'spec':product.spec,'unit':product.unit,'catalog_attributes':attrs,
  'product_version':product_version(product),'candidates':result,'multiple_candidates':len(result)>1,'message':'仅建议，必须人工核对；名称不是SKU身份，未自动关联'}

async def map_product(db,wid,user,pid,data):
 await lock(db,wid);key=label(data.get('request_key'),'映射请求编号',100);signature=fingerprint({'product_id':pid,**data})
 old=(await db.execute(select(ProductSkuMappingEvent).where(ProductSkuMappingEvent.warehouse_id==wid,ProductSkuMappingEvent.request_key==key))).scalar_one_or_none()
 if old:
  if old.request_fingerprint!=signature:raise HTTPException(409,'原映射请求已保存且内容不同，未覆盖当前映射')
  return {'id':old.id,'event_id':old.id,'mapping':old.after,'replayed':True}
 product=await product_owned(db,pid,wid,for_update=True)
 if product.catalog_active is False:raise HTTPException(400,'产品已停用，不能建立新映射')
 if data.get('expected_product_version')!=product_version(product):raise HTTPException(409,'产品或映射已被修改，请刷新后重新核对')
 reason=label(data.get('reason'),'映射核对依据',1000);sid=data.get('sku_id');before=product_state(product)
 if sid is None:
  product.standard_sku_id=None;product.base_unit_factor=None;product.sku_snapshot=None
 else:
  sku=(await db.execute(select(StandardSKU).where(StandardSKU.id==sid,StandardSKU.warehouse_id==wid).with_for_update())).scalar_one_or_none()
  if sku is None:raise HTTPException(404,'当前仓库未找到该SKU')
  snapshot=sku_data(sku)
  if not sku.active or data.get('expected_sku_version')!=snapshot['version']:raise HTTPException(409,'SKU已停用或已变更，请重新核对规格')
  confirmed=attributes(data.get('confirmed_attributes')) if data.get('confirmed_attributes') is not None else None
  if product.catalog_attributes and confirmed is not None and confirmed!=product.catalog_attributes:raise HTTPException(400,'已记录的产品结构规格与本次核对不一致，不能用映射改写原规格')
  attrs=product.catalog_attributes or confirmed
  if not attrs or attrs!=sku.attributes:raise HTTPException(400,'产品结构规格未核实或与SKU不一致，不能映射；不能仅凭名称合并')
  raw_unit=unit(product.unit,False);factor=scalar_factor(data.get('base_unit_factor'))
  if raw_unit==sku.base_unit:
   if factor not in (None,Decimal(1)):raise HTTPException(400,'相同基本单位换算必须为1')
   factor=Decimal(1)
  elif raw_unit is None and factor is not None:raise HTTPException(400,'原单位未知，不能填写未经定义的换算数')
  product.catalog_attributes=attrs;product.standard_sku_id=sku.id;product.base_unit_factor=factor
  product.sku_snapshot={**snapshot,'original_unit':product.unit,'base_unit_factor':str(factor) if factor is not None else None,
   'confirmed_by':user.id,'confirmed_at':thai_now().isoformat()}
 product.catalog_revision=(product.catalog_revision or 0)+1;await db.flush()
 after=json.loads(json.dumps(product_state(product),default=str,ensure_ascii=False))
 event=ProductSkuMappingEvent(warehouse_id=wid,product_id=pid,request_key=key,request_fingerprint=signature,
  before=json.loads(json.dumps(before,default=str,ensure_ascii=False)),after=after,reason=reason,operator_id=user.id,operator_name=user.display_name or user.username)
 db.add(event);await db.flush()
 await record_history(db,module='sku_catalog',record_id=pid,operation_type='map_product',operator=user,before=event.before,
  after={**after,'event_id':event.id,'reason':reason},warehouse_id=wid)
 return {'id':event.id,'event_id':event.id,'mapping':after,'product_version':product_version(product)}

async def mapping_view(db,product,wid):
 result={'standard_sku_id':product.standard_sku_id,'sku_snapshot':product.sku_snapshot,'catalog_attributes':product.catalog_attributes,
  'base_unit_factor':str(product.base_unit_factor) if product.base_unit_factor is not None else None,'product_version':product_version(product),'mapping_status':'unmapped','mapping_label':'未映射/待核对','comparable':False}
 if product.standard_sku_id is None:return result
 sku=await db.get(StandardSKU,product.standard_sku_id)
 if not sku or sku.warehouse_id!=wid:raise HTTPException(409,'产品SKU仓库关系异常，未展示其他仓库资料')
 current=sku_data(sku)
 if not sku.active or not product.sku_snapshot or current['version']!=product.sku_snapshot.get('version'):
  return {**result,'mapping_status':'stale','mapping_label':'目录已变更或停用，待重新核对'}
 known=product.base_unit_factor is not None
 return {**result,'mapping_status':'mapped' if known else 'unit_unknown','mapping_label':'已人工映射' if known else '已映射，单位换算待核对','comparable':known}

async def purchase_snapshot(db,product,wid,quantity):
 info=await mapping_view(db,product,wid)
 return {**info,'base_quantity':str(Decimal(quantity)*product.base_unit_factor) if info['comparable'] else None}
