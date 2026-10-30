"""Legacy Excel formats, read-only preview, explicit atomic confirmation and replay."""
import json,hashlib
from itertools import islice
from types import SimpleNamespace
from decimal import Decimal,InvalidOperation
from fastapi import HTTPException
from sqlalchemy import select
from app.models import Supplier,SupplierProduct,StandardSKU,ProductImportOperation
from app.services import sku_catalog as catalog
from app.services.payable_creation import fingerprint
from app.services.data_history import record_history

HEADERS={'供应商名称':'supplier_name','品名':'product_name','产品名':'product_name','产品名称':'product_name','产品规格':'spec','规格':'spec','规格报价':'spec_price',
 '单价':'unit_price','单位':'unit','币种':'currency','标准SKU编码':'sku_code','SKU编码':'sku_code','结构化规格JSON':'catalog_attributes','基本单位换算数':'factor','阶梯起量':'tier_from','阶梯止量':'tier_to','阶梯单价':'tier_price','生效日期':'valid_from','失效日期':'valid_to'}

def _import_error_message(detail,raw):
 """Only reword an error already raised by the unchanged product validators."""
 message=str(detail)
 if message=='无效单位，请从基本单位清单选择；不自动推断包装换算':
  units='、'.join(catalog.UNITS.values())
  supplied=raw.get('unit')
  if catalog.UNIT_ALIASES.get(str(supplied or '个').strip()) is not None:
   supplied=str(raw.get('catalog_attributes') or '').replace('\u3000','　（全角空格）')
   return f'规格里的单位填错了，可用单位有：{units}。你填的规格内容「{supplied}」里有不支持的单位，请检查“结构化规格JSON”那一列。'
  supplied=str(supplied).replace('\u3000','　（全角空格）')
  return f'单位填错了，只能填 {units} 这几种。你填的「{supplied}」不支持。按箱进货的话，单位填“个”，“基本单位换算数”那一列填每箱多少个。'
 wording={
  '结构化规格JSON格式无效或属性重复':'规格填写格式不对，或者同一个规格项目填了两次。请检查“结构化规格JSON”那一列；不清楚可以先留空。',
  '结构化规格必须是非空JSON对象':'“结构化规格JSON”这一列请按模板填写，不要只填一段文字或一个数字；暂时不填规格可以留空。',
  '结构化规格层级不能超过4层':'规格内容套得太多，最多4层。请简化“结构化规格JSON”那一列后再上传。',
  '结构化规格属性过多':'规格项目太多，每组最多30项，请删减后再上传。',
  '结构化规格含重复属性名':'同一个规格项目填了两次，请删除重复项后再上传。',
  '结构化规格列表过长':'同一组规格最多填30项，请删减后再上传。',
  '结构化规格内容过长':'规格内容太长，请精简“结构化规格JSON”那一列后再上传。',
  '规格数值无效':'规格里的数字填错了，请检查后再上传。',
  '规格数值超出有效范围':'规格里的数字不能超过正负10亿，小数最多8位，请检查后再上传。',
  '规格属性只支持对象、列表、文字、有限数字或布尔值；未知请不填该属性':'规格内容的填写格式不对，请按模板填写；不清楚的项目先不要填。',
  '单位换算数必须是数字':'“基本单位换算数”这一列请填数字，例如每箱100个就填100；不清楚可以先留空。',
  '单位换算数无效':'“基本单位换算数”填错了，请填数字，例如每箱100个就填100；不清楚可以先留空。',
  '单位换算数必须为正数，最多8位小数':'“基本单位换算数”请填大于0、不超过1亿的数字，小数最多8位。按箱进货时，填每箱多少个。',
  '本仓不存在该标准SKU编码或已停用':'在这个仓库找不到填写的标准SKU编号，或者它已停用。请检查“标准SKU编码”那一列。',
  '同SKU编码对应的结构规格不一致，未导入或覆盖':'填写的标准SKU编号与这一行的规格对不上，请核对后再导入；旧产品没有被改动。',
  '核对SKU编码需标准SKU目录权限；也可清空编码并明确以未映射导入':'你没有查看标准SKU目录的权限，不能核对填写的编号。请找有权限的人处理；也可以清空“标准SKU编码”，先导入产品，之后再关联。',
  '产品结构规格未核实或与SKU不一致':'这行产品的规格还没核对清楚，或与选择的标准SKU对不上。请检查规格后再确认。',
 }
 return wording.get(message,message)

def validate_filename(filename):
 name=(filename or '').strip().lower()
 if name.endswith('.xls'):raise HTTPException(400,'请另存为 xlsx 格式')
 if not name.endswith('.xlsx'):raise HTTPException(400,'仅支持 xlsx 格式，请使用产品导入模板')


def json_value(value):
 def pairs(items):
  result={}
  for key,item in items:
   if key in result:raise ValueError('JSON属性重复')
   result[key]=item
  return result
 try:return json.loads(value,object_pairs_hook=pairs)
 except (ValueError,TypeError):raise HTTPException(400,'结构化规格JSON格式无效或属性重复')

def decimal_value(value,name,optional=False):
 if optional and value in (None,''):return None
 if isinstance(value,bool):raise HTTPException(400,name+'必须是数字')
 try:d=Decimal(str(value))
 except (InvalidOperation,TypeError):raise HTTPException(400,name+'必须是数字')
 if not d.is_finite() or d<=0 or d>1000000000:raise HTTPException(400,name+'必须为有效正数')
 return float(d)

def import_quote_terms(raw):
 fields=('tier_from','tier_to','tier_price','valid_from','valid_to')
 if not any(raw.get(k) not in (None,'') for k in fields):return None
 from datetime import date,datetime
 from app.services.supplier_quotes import tiers
 dates={}
 for key,label in [('valid_from','生效日期'),('valid_to','失效日期')]:
  value=raw.get(key)
  if isinstance(value,datetime):value=value.date()
  try:dates[key]=(value if isinstance(value,date) else date.fromisoformat(str(value))).isoformat()
  except (ValueError,TypeError):raise HTTPException(400,'阶梯起量、阶梯单价、生效日期和失效日期须成组明确填写；日期为YYYY-MM-DD，不自动补有效期')
 if dates['valid_to']<dates['valid_from']:raise HTTPException(400,'失效日期不能早于生效日期')
 return {**dates,'tiers':tiers([{'min_quantity':raw.get('tier_from'),'max_quantity':None if raw.get('tier_to') in (None,'') else raw['tier_to'],'unit_price':raw.get('tier_price')}])}

def duplicate_key(row):return tuple(row.get(k) or '' for k in ('supplier_id','product_name','spec','unit','currency'))

async def preview(db,wid,user,content,supplier_id=None):
 if not content:raise HTTPException(400,'文件为空，请选择包含表头和数据的 xlsx 文件')
 if len(content)>2*1024*1024:raise HTTPException(400,'请选择2MB以内的xlsx文件')
 from app.services.excel_import import workbook
 wb=workbook(content, allow_active_formulas=True)
 try:
  ws=wb.active
  if ws is None or not hasattr(ws,'iter_rows'):raise HTTPException(400,'文件没有可读取的表头，请使用产品导入模板')
  if (ws.max_row or 0)>501 or (ws.max_column or 0)>20:raise HTTPException(400,'每次最多500条、20列，请拆分文件')
  cells=list(islice(ws.iter_rows(),502));header={};errors=[];rows=[];skipped_rows=[];total_rows=0;example_count=0
  if not cells or not any(c.value not in (None,'') for c in cells[0]):raise HTTPException(400,'文件没有表头，请使用产品导入模板')
  if len(cells)>501 or any(len(r)>20 for r in cells):raise HTTPException(400,'每次最多500条、20列，请拆分文件')
  for index,cell in enumerate(cells[0] if cells else []):
   key=HEADERS.get(str(cell.value or '').strip())
   if cell.value not in (None,'') and key is None:errors.append({'row_number':1,'message':'不支持的表头：'+str(cell.value)+'；请使用模板，不接受隐藏关联编号'})
   if key:
    if key in header:errors.append({'row_number':1,'message':'重复表头：'+str(cell.value)})
    header[key]=index
  if not header:raise HTTPException(400,'文件没有有效表头，请使用产品导入模板')
  if not {'product_name','unit_price'}<=header.keys() or supplier_id is None and 'supplier_name' not in header:
   errors.append({'row_number':1,'message':'耗材模板列不匹配：缺少品名、单价或批量供应商名称；请下载耗材模板，不要上传物流模板。旧版表头仍支持'})
  if any(str(c.value or '').strip()=='品名' for c in cells[0]) and not {'product_name','spec','unit','unit_price','currency'}<=header.keys():errors.append({'row_number':1,'message':'耗材新模板必须保留品名、规格、单位、单价、币种五个基础表头；可选列可留空'})
  suppliers=(await db.execute(select(Supplier).where(Supplier.warehouse_id==wid,Supplier.is_active=='true'))).scalars().all()
  names={}
  for s in suppliers:names.setdefault(s.name.strip(),[]).append(s)
  selected=next((s for s in suppliers if s.id==supplier_id),None) if supplier_id is not None else None
  if supplier_id is not None and selected is None:raise HTTPException(404,'当前仓库未找到所选供应商')
  existing=(await db.execute(select(SupplierProduct).join(Supplier).where(Supplier.warehouse_id==wid,SupplierProduct.catalog_active.is_not(False)))).scalars().all()
  existing_keys={duplicate_key({'supplier_id':p.supplier_id,'product_name':p.product_name,'spec':p.spec,'unit':p.unit,'currency':p.currency or 'THB'}) for p in existing}
  seen={};can_catalog=catalog.permission(user,'sku_catalog')
  for number,cells_row in enumerate(cells[1:],2):
   if not any(c.value not in (None,'') for c in cells_row):continue
   total_rows+=1
   raw={k:cells_row[i].value if i<len(cells_row) else None for k,i in header.items()}
   marker=str(cells_row[0].value or '').strip()
   legacy_example=raw.get('supplier_name') in ('示例: 耗材商A','示例：耗材商A') and raw.get('product_name')=='快递袋' and raw.get('spec')=='一打80个' and raw.get('spec_price')==80 and raw.get('unit_price')==1 and not any(c.data_type=='f' for c in cells_row)
   if marker.startswith('##') or legacy_example or raw.get('product_name')=='## 示例行（不会导入）' or raw.get('supplier_name')=='## 示例供应商（不会导入）':
    example_count+=1;skipped_rows.append({'row_number':number,'message':'跳过了示例行（不会导入）','blocking':False});continue
   entry={'row_number':number,'errors':[],'candidates':[],'catalog_visible':can_catalog,'skipped':False,
    'supplier_name':str(raw.get('supplier_name') or '').strip(),'product_name':str(raw.get('product_name') or '').strip()}
   try:
    source=selected
    if selected:
     if raw.get('supplier_name') not in (None,'') and str(raw['supplier_name']).strip()!=selected.name.strip():raise HTTPException(400,f'该行属于其他供应商「{raw["supplier_name"]}」，当前只允许「{selected.name}」，整批未导入')
    else:
     found=names.get(str(raw.get('supplier_name') or '').strip(),[])
     if len(found)!=1:
      message='供应商名称在本仓不存在或不唯一，该行已跳过，请核对供应商档案'
      entry.update(skipped=True,errors=[message]);rows.append(entry)
      skipped_rows.append({'row_number':number,'message':message,'blocking':False});continue
     source=found[0]
    if any(c.data_type=='f' for c in cells_row):raise HTTPException(400,'不接受公式，请粘贴核实后的数值')
    name=catalog.label(raw.get('product_name'),'产品名',200)
    raw_unit=str(raw.get('unit') or '个').strip();catalog.unit(raw_unit)
    currency=str(raw.get('currency') or source.default_currency or 'THB').strip()
    if currency not in ('THB','CNY'):raise HTTPException(400,'币种只支持THB/CNY，不能混算')
    attrs=catalog.attributes(json_value(raw['catalog_attributes'])) if raw.get('catalog_attributes') not in (None,'') else None
    sku_code=catalog.code(raw['sku_code']) if raw.get('sku_code') not in (None,'') else None
    factor=catalog.scalar_factor(raw.get('factor'))
    row={'supplier_id':source.id,'supplier_name':source.name,'product_name':name,'spec':str(raw.get('spec') or '').strip() or None,
     'spec_price':decimal_value(raw.get('spec_price'),'规格报价',True),'unit_price':decimal_value(raw.get('unit_price'),'单价'),'currency':currency,
     'unit':raw_unit,'catalog_attributes':attrs,'sku_code':sku_code,'factor':str(factor) if factor is not None else None}
    entry['quote_terms']=import_quote_terms(raw)
    key=duplicate_key(row)
    entry['append_quote']=key in existing_keys
    entry['warnings']=['已有该供应商该产品报价，本行将新增报价，不合并、不覆盖旧报价'] if key in existing_keys else []
    if key in seen:raise HTTPException(400,f'与第{seen[key]}行产品重复，请核对后重新预览')
    seen[key]=number;entry.update(row)
    draft=SimpleNamespace(id=None,**{k:v for k,v in row.items() if k not in ('supplier_name','sku_code','factor')},standard_sku_id=None,
     base_unit_factor=None,sku_snapshot=None,catalog_revision=None,catalog_active=True)
    if can_catalog:
     entry['candidates']=(await catalog.suggestions(db,wid,draft))['candidates']
     if sku_code:
      sku=(await db.execute(select(StandardSKU).where(StandardSKU.warehouse_id==wid,StandardSKU.code==sku_code,StandardSKU.active.is_(True)))).scalar_one_or_none()
      if sku is None:raise HTTPException(400,'本仓不存在该标准SKU编码或已停用')
      if attrs and attrs!=sku.attributes:raise HTTPException(400,'同SKU编码对应的结构规格不一致，未导入或覆盖')
      if not any(c['id']==sku.id for c in entry['candidates']):entry['candidates'].append({**catalog.sku_data(sku),'matched_fields':['明确SKU编码'],'differences':['结构规格仍需人工逐项核对'] if not attrs else [],'can_map':True,'auto_mapped':False})
    elif sku_code:raise HTTPException(403,'核对SKU编码需标准SKU目录权限；也可清空编码并明确以未映射导入')
   except HTTPException as e:
    entry['skipped']=True;entry['errors'].append(_import_error_message(e.detail,raw));errors.append({'row_number':number,'message':_import_error_message(e.detail,raw)})
    skipped_rows.append({'row_number':number,'message':_import_error_message(e.detail,raw),'blocking':True})
   rows.append(entry)
  valid_count=sum(not r['skipped'] and not r['errors'] for r in rows)
  message=('全部是示例行，没有可导入数据' if total_rows and total_rows==example_count else '没有可导入数据') if not valid_count else '仅预览，尚未写入产品；核对有效行后整批导入，跳过行不会写入'
  if not valid_count:errors.append({'row_number':2,'message':message})
  elif errors:message='文件含需修正的错误行，整批未导入，请修正后重新预览'
  result={'rows':rows,'errors':errors,'valid':not errors and valid_count>0,
   'total_rows':total_rows,'valid_count':valid_count,'skipped_count':len(skipped_rows),'skipped_rows':skipped_rows,'updated':0,'imported':0,'mode':'preview','supplier_id':supplier_id,'warehouse_id':wid,'operator_id':user.id,
   'message':message}
  result['preview_version']=fingerprint({'content_sha256':hashlib.sha256(content).hexdigest(),**result})
  return result
 finally:wb.close()

async def confirm(db,wid,user,content,supplier_id,request_key,preview_version,choices):
 await catalog.lock(db,wid);key=catalog.label(request_key,'导入请求编号',100)
 if isinstance(choices,str):choices=json_value(choices)
 if not isinstance(choices,list):raise HTTPException(400,'请逐行确认映射选择')
 signature=fingerprint({'file_sha256':hashlib.sha256(content).hexdigest(),'supplier_id':supplier_id,'operator_id':user.id,'preview_version':preview_version,'choices':choices})
 old=(await db.execute(select(ProductImportOperation).where(ProductImportOperation.warehouse_id==wid,ProductImportOperation.request_key==key))).scalar_one_or_none()
 if old:
  if old.request_fingerprint!=signature:raise HTTPException(409,'该导入请求已保存但内容不同，未覆盖或重复导入')
  return {**old.result,'replayed':True}
 current=await preview(db,wid,user,content,supplier_id)
 if current['preview_version']!=preview_version:raise HTTPException(409,{'code':'product_import_preview_changed','not_created':True,'request_key':key,'message':'原请求未保存，产品、目录、账号或文件已变更，请重新核对；沿用原请求编号','preview':current})
 if not current['valid']:raise HTTPException(422,{'code':'product_import_invalid_rows','message':'文件含错误行，整批未导入','errors':current['errors']})
 importable=[r for r in current['rows'] if not r.get('skipped') and not r['errors']]
 by_row={}
 for choice in choices:
  if not isinstance(choice,dict) or type(choice.get('row_number')) is not int or choice['row_number'] in by_row or choice.get('confirmed') is not True:raise HTTPException(400,'每行必须明确确认一次，不接受重复行号或缺少确认')
  by_row[choice['row_number']]=choice
 if set(by_row)!={r['row_number'] for r in importable}:raise HTTPException(400,'确认行号与本次预览不一致')
 # Validate every selection before inserting any product. Mapping rechecks under the same lock.
 for row in importable:
  choice=by_row[row['row_number']]
  try:
   if row.get('quote_terms'):
    from app.core.action_access import access_description
    catalog.require_mapping(user)
    if not any(a['id']=='supplier_quotes.create' and a['tier']=='operate' for a in access_description(user)['actions']):raise HTTPException(403,'导入阶梯报价仍需现有报价新增权限')
    if choice.get('decision')!='map':raise HTTPException(400,'填写阶梯或有效期的产品必须人工映射标准SKU后登记报价；不能以未映射导入绕过原报价规则')
   if choice.get('decision')=='map':
    catalog.require_mapping(user)
    if type(choice.get('sku_id')) is not int or choice['sku_id']<=0:raise HTTPException(400,'SKU编号必须是有效整数')
    if not any(c['id']==choice['sku_id'] and c['can_map'] for c in row['candidates']):raise HTTPException(400,'所选SKU不在本次有效候选中，请重新预览，不接受隐藏字段指定')
    sku=await db.get(StandardSKU,choice.get('sku_id'))
    if not sku or sku.warehouse_id!=wid:raise HTTPException(403,'SKU不存在或不属于当前仓库')
    if not sku.active or catalog.sku_data(sku)['version']!=choice.get('expected_sku_version'):raise HTTPException(409,'SKU已变更，请重新预览')
    attrs=row.get('catalog_attributes') or catalog.attributes(choice.get('confirmed_attributes'))
    if attrs!=sku.attributes:raise HTTPException(400,'产品结构规格未核实或与SKU不一致')
    if row.get('sku_code') and row['sku_code']!=sku.code:raise HTTPException(400,'所选SKU与文件编码不一致')
    catalog.label(choice.get('reason'),'映射核对依据',1000);catalog.scalar_factor(choice.get('base_unit_factor',row.get('factor')))
   elif choice.get('decision')!='unmapped':raise HTTPException(400,'请选择人工映射或明确保持未映射')
  except HTTPException as e:raise HTTPException(e.status_code,{'row_number':row['row_number'],'message':_import_error_message(e.detail,{**row,'catalog_attributes':row.get('catalog_attributes') or choice.get('confirmed_attributes')}),'imported':0})
 created=[]
 for row in importable:
  choice=by_row[row['row_number']]
  p=SupplierProduct(**{k:row[k] for k in ('supplier_id','product_name','spec','spec_price','unit_price','currency','unit','catalog_attributes')});db.add(p);await db.flush()
  event_id=None
  if choice['decision']=='map':
   try:
    mapped=await catalog.map_product(db,wid,user,p.id,{**choice,'request_key':'import:'+fingerprint({'request':key,'row':row['row_number']}),
     'expected_product_version':catalog.product_version(p),'base_unit_factor':choice.get('base_unit_factor',row.get('factor'))})
    event_id=mapped['event_id']
   except HTTPException as e:raise HTTPException(e.status_code,{'row_number':row['row_number'],'message':_import_error_message(e.detail,{**row,'catalog_attributes':row.get('catalog_attributes') or choice.get('confirmed_attributes')}),'imported':0})
  quote_id=None
  if row.get('quote_terms'):
   from app.services import supplier_quotes as quotes
   sku=await db.get(StandardSKU,p.standard_sku_id)
   quote=await quotes.save(db,wid,user,p.id,{**row['quote_terms'],'code':f'IMPORT-{p.id}-{fingerprint(key)[:12]}','request_key':'import-quote:'+fingerprint({'request':key,'row':row['row_number']}),
    'expected_product_version':catalog.product_version(p),'expected_sku_version':catalog.sku_data(sku)['version'],'currency':p.currency,'unit':p.unit,
    'base_unit_factor':str(p.base_unit_factor) if p.base_unit_factor is not None else None,'conversion_basis':choice.get('reason',''),
    'fees':{'tax_mode':'unknown','freight_mode':'unknown','other_fees':'unknown'},'quality_tags':[],'active':True})
   quote_id=quote['id']
  created.append({'quote_id':quote_id,'row_number':row['row_number'],'product_id':p.id,'mapping_event_id':event_id,'status':'人工映射' if event_id else '未映射/待核对'})
 result={'mode':'confirmed','imported':len(created),'skipped':current['skipped_count'],'updated':0,'skipped_rows':current['skipped_rows'],'errors':[],'data':created,
  'message':f'导入成功 {len(created)} 条，跳过 {current["skipped_count"]} 条，更新 0 条；已新增报价，未自动合并或覆盖旧报价'}
 operation=ProductImportOperation(warehouse_id=wid,request_key=key,request_fingerprint=signature,result=result,operator_id=user.id)
 db.add(operation);await db.flush();result={**result,'id':operation.id};operation.result=result
 await record_history(db,module='sku_catalog',record_id=0,operation_type='import_products',operator=user,before=None,after={**result,'request_key':key},warehouse_id=wid)
 await db.flush();return result
