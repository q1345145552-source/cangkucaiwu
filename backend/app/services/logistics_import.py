"""Header-based logistics import, atomic confirmation and durable replay."""
import hashlib
from fastapi import HTTPException
from sqlalchemy import select
from app.models import Supplier, ProductImportOperation
from app.models.supplier import SupplierCrossBorderPrice, SupplierRoutePrice
from app.services import sku_catalog as catalog
from app.services.product_import import decimal_value
from app.services.excel_import import table
from app.services.payable_creation import fingerprint
from app.core.permissions import Role

HEADERS = {'供应商名称':'supplier_name','运输方式':'transport_method','货物类型':'cargo_type','发货仓库':'origin_warehouse',
           '单价(元/方)':'price_per_cbm','时效':'estimated_days','币种':'currency'}

ROUTE_HEADERS={'供应商名称':'supplier_name','起点':'origin','终点':'destination','运输方式':'transport_method',
 '重量或体积起':'quantity_from','重量或体积止':'quantity_to','计量单位':'pricing_unit','单价':'unit_price','币种':'currency',
 '时效天数':'transit_days','最低收费':'minimum_charge','备注':'remark'}

def nonnegative(value,name):
 from decimal import Decimal,InvalidOperation
 try:
  number=Decimal(str(value))
  if isinstance(value,bool) or not number.is_finite() or number<0 or number>1000000000 or number!=number.quantize(Decimal('0.000001')):raise ValueError
 except (ValueError,InvalidOperation,TypeError):raise HTTPException(400,name+'必须明确填写非负数字，最多6位小数')
 return float(number)

def route_values(value):
 row={key:catalog.label(str(value.get(key) if value.get(key) is not None else ''),label,200) for key,label in [('origin','起点'),('destination','终点')]}
 row['transport_method']=str(value.get('transport_method') or '').strip()
 if row['transport_method'] not in ('空运','海运','陆运'):raise HTTPException(400,'运输方式只支持空运、海运、陆运')
 row['pricing_unit']=str(value.get('pricing_unit') or '').strip()
 if row['pricing_unit'] not in ('kg','方','件'):raise HTTPException(400,'计量单位只支持kg、方、件，不自动换算')
 for key,label in [('quantity_from','重量或体积起'),('quantity_to','重量或体积止'),('minimum_charge','最低收费')]:row[key]=nonnegative(value.get(key),label)
 if row['quantity_to']<=row['quantity_from']:raise HTTPException(400,'重量或体积止必须大于起量')
 row['unit_price']=decimal_value(value.get('unit_price'),'单价')
 if round(row['unit_price'],6)!=row['unit_price']:raise HTTPException(400,'单价最多6位小数')
 days=nonnegative(value.get('transit_days'),'时效天数')
 if days!=int(days) or days>3650:raise HTTPException(400,'时效天数必须为0至3650的整数')
 row['transit_days']=int(days);row['currency']=str(value.get('currency') or '').strip()
 if row['currency'] not in ('THB','CNY'):raise HTTPException(400,'币种只支持THB/CNY，请明确填写')
 row['remark']=str(value.get('remark') or '').strip() or None
 if row['remark'] and len(row['remark'])>500:raise HTTPException(400,'备注最多500字')
 return row

async def preview(db, wid, user, content, supplier_id):
    from app.services.excel_import import workbook
    wb=workbook(content)
    try:columns=[str(v or '').strip() for v in next(wb.active.iter_rows(values_only=True),[])]
    finally:wb.close()
    route=any(h in columns for h in ('起点','终点','计量单位','重量或体积起'))
    headers=ROUTE_HEADERS if route else HEADERS
    required = set(headers.values()) - {'supplier_name','remark'}
    if supplier_id is None: required.add('supplier_name')
    raw, errors = table(content, headers, required)
    if errors:errors=[{**e,'message':'物流模板列不匹配：'+e['message']+'；请使用物流模板，不要上传耗材模板'} if e['row_number']==1 else e for e in errors]
    suppliers = (await db.execute(select(Supplier).where(Supplier.warehouse_id == wid, Supplier.is_active == 'true'))).scalars().all()
    names = {}
    for supplier in suppliers: names.setdefault(supplier.name.strip(), []).append(supplier)
    selected = next((s for s in suppliers if s.id == supplier_id), None)
    if supplier_id is not None and selected is None: raise HTTPException(404, '当前仓库未找到所选供应商')
    rows = []
    for number, value in raw:
        if str(next(iter(value.values()),'') or '').startswith('##') or value.get('origin')=='## 示例起点（不会导入）' or value.get('supplier_name')=='## 示例供应商（不会导入）':continue
        if value == dict(zip(HEADERS.values(), ['示例: 物流公司A','陆运','普货','深圳仓',800,'5-7天','CNY'])): continue
        try:
            source = selected
            name = str(value.get('supplier_name') or '').strip()
            if selected and name and name != selected.name.strip():
                raise HTTPException(400, '供应商与当前入口不一致；请选择正确供应商或多供应商物流导入')
            if not selected:
                found = names.get(name, [])
                if len(found) != 1: raise HTTPException(400, '本仓供应商名称不存在或不唯一，不会猜测匹配')
                source = found[0]
            row = {'supplier_id': source.id}
            if route:
                rows.append({'row_number':number,'supplier_name':source.name,'quote_format':'route',**row,**route_values(value)});continue
            for key, limit in [('transport_method',20),('cargo_type',20),('origin_warehouse',20)]:
                row[key] = catalog.label(str(value.get(key) if value.get(key) is not None else ''), next(h for h,k in HEADERS.items() if k == key), limit)
            row['price_per_cbm'] = decimal_value(value.get('price_per_cbm'), '单价')
            row['currency'] = str(value.get('currency') or '').strip()
            if row['currency'] not in ('THB','CNY'): raise HTTPException(400, '币种只支持THB/CNY，请明确填写')
            row['estimated_days'] = catalog.label(str(value['estimated_days']), '时效', 30) if value.get('estimated_days') not in (None,'') else None
            rows.append({'row_number':number,'supplier_name':source.name, **row})
        except HTTPException as exc: errors.append({'row_number':number,'message':str(exc.detail)})
    if not raw or not rows and not errors: errors.append({'row_number':2,'message':'没有实际数据，空模板或只有示例行'})
    result = {'mode':'preview','rows':rows,'errors':errors,'valid':not errors,'imported':0,
              'supplier_id':supplier_id,'warehouse_id':wid,'operator_id':user.id,'message':'预览成功，尚未保存' if not errors else '校验失败，整批未保存'}
    result['preview_version'] = fingerprint({'content':hashlib.sha256(content).hexdigest(), **result})
    return result

async def execute(db, wid, user, content, supplier_id, mode, version, request_key):
    if user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF): raise HTTPException(403, '无权限')
    if mode == 'preview': return await preview(db,wid,user,content,supplier_id)
    if mode != 'confirm': raise HTTPException(400, '请先预览，再明确确认')
    await catalog.lock(db,wid)
    key = 'logistics:' + catalog.label(request_key,'请求编号',80)
    signature = fingerprint({'content':hashlib.sha256(content).hexdigest(),'supplier_id':supplier_id,'preview_version':version,'operator_id':user.id})
    old = (await db.execute(select(ProductImportOperation).where(ProductImportOperation.warehouse_id==wid,ProductImportOperation.request_key==key))).scalar_one_or_none()
    if old:
        if old.request_fingerprint != signature: raise HTTPException(409, '原请求内容不同，未重复新增；请核对原记录')
        return {**old.result,'replayed':True}
    current = await preview(db,wid,user,content,supplier_id)
    if not current['valid']: raise HTTPException(422, {'code':'excel_import_not_saved','not_created':True,'request_key':request_key,'message':'校验失败，整批未保存','errors':current['errors'],'preview':current})
    if version != current['preview_version']: raise HTTPException(409, {'code':'excel_import_not_saved','not_created':True,'request_key':request_key,'message':'原请求未保存，预览已变更，请重新核对并确认；沿用原请求编号','preview':current})
    for row in current['rows']:
        model=SupplierRoutePrice if row.get('quote_format')=='route' else SupplierCrossBorderPrice
        db.add(model(**{k:v for k,v in row.items() if k not in ('row_number','supplier_name','quote_format')}))
    result = {'mode':'confirmed','imported':len(current['rows']),'errors':[],'message':f"已整批保存{len(current['rows'])}条物流报价，未覆盖旧报价"}
    op = ProductImportOperation(warehouse_id=wid,request_key=key,request_fingerprint=signature,result=result,operator_id=user.id)
    db.add(op); await db.flush(); result = {**result,'id':op.id}; op.result=result
    return result
