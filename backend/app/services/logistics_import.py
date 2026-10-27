"""Header-based logistics import, atomic confirmation and durable replay."""
import hashlib
from fastapi import HTTPException
from sqlalchemy import select
from app.models import Supplier, ProductImportOperation
from app.models.supplier import SupplierCrossBorderPrice
from app.services import sku_catalog as catalog
from app.services.product_import import decimal_value
from app.services.excel_import import table
from app.services.payable_creation import fingerprint
from app.core.permissions import Role

HEADERS = {'供应商名称':'supplier_name','运输方式':'transport_method','货物类型':'cargo_type','发货仓库':'origin_warehouse',
           '单价(元/方)':'price_per_cbm','时效':'estimated_days','币种':'currency'}

async def preview(db, wid, user, content, supplier_id):
    required = set(HEADERS.values()) - {'supplier_name'}
    if supplier_id is None: required.add('supplier_name')
    raw, errors = table(content, HEADERS, required)
    suppliers = (await db.execute(select(Supplier).where(Supplier.warehouse_id == wid, Supplier.is_active == 'true'))).scalars().all()
    names = {}
    for supplier in suppliers: names.setdefault(supplier.name.strip(), []).append(supplier)
    selected = next((s for s in suppliers if s.id == supplier_id), None)
    if supplier_id is not None and selected is None: raise HTTPException(404, '当前仓库未找到所选供应商')
    rows = []
    for number, value in raw:
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
            for key, limit in [('transport_method',20),('cargo_type',20),('origin_warehouse',20)]:
                row[key] = catalog.label(str(value.get(key) or ''), next(h for h,k in HEADERS.items() if k == key), limit)
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
        db.add(SupplierCrossBorderPrice(**{k:v for k,v in row.items() if k not in ('row_number','supplier_name')}))
    result = {'mode':'confirmed','imported':len(current['rows']),'errors':[],'message':f"已整批保存{len(current['rows'])}条物流报价，未覆盖旧报价"}
    op = ProductImportOperation(warehouse_id=wid,request_key=key,request_fingerprint=signature,result=result,operator_id=user.id)
    db.add(op); await db.flush(); result = {**result,'id':op.id}; op.result=result
    return result
