"""Incremental receipt registration with one transaction and immutable per-batch evidence."""
import hashlib
import json
import uuid
from sqlalchemy import select
from fastapi import HTTPException
from app.models import PurchaseOrder, PayableBill, PurchaseReceiptEvent, ProcurementDutyExecution
from app.core.timezone import thai_now
from app.services import purchase_matching as match
from app.services.payable_creation import number, fingerprint, flush_unique
from app.services.purchase_receipt_migration import ensure_receipt_guard
from app.services.supplier_payable_read import checked_link, can_read_bills
from app.services.data_history import record_history


async def receive(db,po_id,warehouse_id,user,raw_items,content,filename,request_key,remark='',controls=None):
    key=number(request_key,'收货请求编号',100)
    from app.services.image_utils import is_image
    if not content or not is_image(content): raise HTTPException(400,'请上传有效到货照片')
    if len(remark)>1000: raise HTTPException(400,'收货备注不能超过1000字')
    try: submitted=json.loads(raw_items)
    except (TypeError,ValueError): raise HTTPException(400,'收货明细格式错误')
    if not isinstance(submitted,list) or not submitted: raise HTTPException(400,'请按稳定行编号填写本次收货明细')
    await match.scope_lock(db,warehouse_id)
    await ensure_receipt_guard(await db.connection())
    from app.services.procurement_control_migration import ensure_procurement_controls
    await ensure_procurement_controls(await db.connection())
    from app.services.inventory_migration import ensure_inventory
    await ensure_inventory(await db.connection())
    po=(await db.execute(select(PurchaseOrder).where(PurchaseOrder.id==po_id).with_for_update())).scalar_one_or_none()
    if po is None: raise HTTPException(404,'采购单不存在')
    if po.warehouse_id!=warehouse_id: raise HTTPException(403,'无权操作其他仓库的采购单')
    state=await match.receipt_state(db,po)
    if state['issues']: raise HTTPException(409,{'message':'历史收货依据异常，未自动改数据','issues':state['issues']})
    expected={it['line_id']:it for it in state['items']}
    rows=[];seen=set()
    for it in submitted:
        if not isinstance(it,dict) or not isinstance(it.get('line_id'),str): raise HTTPException(400,'收货必须使用采购明细的稳定行编号')
        lid=it['line_id'];q=it.get('received_quantity')
        if lid in seen: raise HTTPException(400,'收货行编号不能重复')
        if lid not in expected: raise HTTPException(400,'收货包含未知或其他采购单的行编号')
        if type(q) is not int or not 0<=q<=2147483647:
            raise HTTPException(400,'本次收货数量必须是非负整数，不支持小数、负数或自动截断')
        if expected[lid]['received_quantity'] is None or match.historical_quantity(expected[lid].get('quantity')) is None:
            raise HTTPException(409,'该行历史数量无法确定，请先核对；未将未知实收改成零')
        seen.add(lid)
        rows.append({'line_id':lid,'quantity':q,'unit':expected[lid].get('unit'),
            'product_name':expected[lid].get('product_name'),'spec':expected[lid].get('spec')})
    if not any(r['quantity']>0 for r in rows): raise HTTPException(400,'本次至少一行收货数量须大于零')
    signature=fingerprint({'purchase_order_id':po.id,'items':sorted(rows,key=lambda r:r['line_id']),
        'remark':remark,'photo_sha256':hashlib.sha256(content).hexdigest()})
    old=(await db.execute(select(PurchaseReceiptEvent).where(PurchaseReceiptEvent.warehouse_id==warehouse_id,
        PurchaseReceiptEvent.purchase_order_id==po.id,PurchaseReceiptEvent.request_key==key))).scalar_one_or_none()
    if old and old.operator_id!=user.id:raise HTTPException(403,'收货请求属于其他操作者，不能冒用原请求重放')
    legacy_replay=old and not (await db.execute(select(ProcurementDutyExecution.id).where(ProcurementDutyExecution.warehouse_id==warehouse_id,
        ProcurementDutyExecution.action=='receive',ProcurementDutyExecution.operator_id==user.id,ProcurementDutyExecution.request_key==key))).first()
    from app.services import procurement_controls as duty
    ticket=None if legacy_replay else await duty.begin(db,po,user,'receive',key,{'receipt_signature':signature},controls)
    if ticket and ticket.get('replay'):return ticket['replay']
    if old:
        if old.request_fingerprint!=signature: raise HTTPException(409,f'该收货请求已登记为批次#{old.id}且内容不同，未重复累计')
        return {'id':old.id,'receipt_event_id':old.id,'replayed':True,'message':'原收货批次已保存，未重复累计',
            'receipt_status':po.receipt_status,'flow_status':po.flow_status,
            'has_diff':any(i['quantity_status']!='matched' for i in state['items'])}
    if po.status!='confirmed': raise HTTPException(400,'仅已生效采购单可收货')
    bill=None
    if po.payable_bill_id:
        bill=(await db.execute(select(PayableBill).where(PayableBill.id==po.payable_bill_id).with_for_update())).scalar_one_or_none()
        if bill is None: raise HTTPException(409,'关联账单缺失，请管理员核对')
        await checked_link(db,bill,po,warehouse_id)
    elif (await db.execute(select(PayableBill.id).where(PayableBill.purchase_order_id==po.id))).first():
        raise HTTPException(409,'采购与应付历史关联不一致，未自动修复')
    if po.receipt_baseline is None: po.receipt_baseline=match.baseline(po)
    event=PurchaseReceiptEvent(warehouse_id=warehouse_id,purchase_order_id=po.id,request_key=key,
        request_fingerprint=signature,items=[r for r in rows if r['quantity']>0],photo_path='',
        operator_id=user.id,operator_name=user.display_name or user.username,received_at=thai_now(),
        remark=remark,source='purchase_receive',status='active')
    db.add(event);await flush_unique(db)
    from app.services.image_utils import save_image
    ext=filename.rsplit('.',1)[-1] if filename and '.' in filename else 'png'
    import os
    from pathlib import Path
    rel=f'{warehouse_id}/{event.received_at.date().isoformat()}/arrival_photos'
    saved=save_image(content,str(Path(os.environ.get('UPLOAD_DIR','/app/uploads'))/rel),f'/uploads/{rel}',f'{uuid.uuid4().hex}.{ext}')
    event.photo_path=saved['path']
    await db.flush()
    from app.services.inventory import record_receipt
    stock_result = await record_receipt(db,po,event,user)
    state=await match.receipt_state(db,po)
    has_diff=any(i['quantity_status']!='matched' for i in state['items'])
    po.items=[{**it,'line_id':it['line_id'],'received_quantity':it['received_quantity'],'diff_quantity':it['diff_quantity']}
        for it in state['items']]
    po.receipt_status='partially_received' if has_diff else 'received'
    po.flow_status='arrived' if has_diff else 'completed'
    # Compatibility pointer is only the latest photo; all originals remain in baseline/events and on disk.
    po.arrival_photo=event.photo_path;po.received_by=user.id;po.received_at=event.received_at
    await db.flush()
    if bill: await match.invalidate_review(db,bill,user,receipt_changed=True)
    await record_history(db,module='suppliers',record_id=po.id,operator=user,operation_type='receive_batch',
        after={'receipt_event_id':event.id,'request_key':key,'items':event.items,'photo_path':event.photo_path,
               'remark':remark,'quantity_basis':po.receipt_baseline['source']},warehouse_id=warehouse_id)
    await db.flush()
    response={'inventory': stock_result, 'id':event.id,'receipt_event_id':event.id,'message':'本次收货已登记'+('，累计数量有差异，待老板复核' if has_diff else ''),
        'has_diff':has_diff,'receipt_status':po.receipt_status,'flow_status':po.flow_status,
        'items':state['items'],'photo_path':event.photo_path,
        'matching':await match.matching(db,bill,po) if bill and can_read_bills(user) else None}
    return await duty.finish(db,ticket,response)
