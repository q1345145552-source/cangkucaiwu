"""Recorded-quantity and three-way evidence, never inferred from names or free text."""
from decimal import Decimal, InvalidOperation
from sqlalchemy import select
from fastapi import HTTPException
from app.models import PurchaseOrder, PurchaseReceiptEvent, SystemSetting, Warehouse
from app.core.timezone import thai_now
from app.services.payable_creation import fingerprint
from app.services.data_history import record_history

KINDS = {'goods': '商品采购', 'prepayment': '预付款', 'non_goods': '非商品费用', 'unknown': '类型待核实'}
POLICY_KEY = 'purchase_three_way_strict'


def kind(value):
    if value is None or value == '':
        return 'unknown'
    if value not in KINDS:
        raise HTTPException(400, '三单匹配类型不正确')
    return value


def decimal(value):
    try:
        if value is None or isinstance(value, bool): return None
        v = Decimal(str(value))
        return v if v.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def amount(value):
    v = decimal(value)
    try: return v.quantize(Decimal('.01')) if v is not None else None
    except InvalidOperation: return None


def historical_quantity(value):
    n = decimal(value)
    return int(n) if n is not None and 0 <= n <= 2147483647 and n == n.to_integral_value() else None


def lines(po):
    if not isinstance(po.items, list): return []
    return [{**it, 'line_id': it['line_id'] if isinstance(it.get('line_id'),str) and it['line_id'] else f'legacy:{po.id}:{i+1}',
             'line_id_source': 'stored' if isinstance(it.get('line_id'),str) and it['line_id'] else 'invalid_stored' if it.get('line_id') is not None else 'legacy_order_position'}
            for i, it in enumerate(po.items) if isinstance(it, dict)]


def baseline(po):
    if po.receipt_baseline is not None:
        return po.receipt_baseline if isinstance(po.receipt_baseline,dict) else {'source':'invalid_stored_baseline','lines':[],
            'note':'历史基数格式异常，未改数据或猜算。'}
    return {'source': 'legacy_recorded_fields', 'event_history_known': False,
        'note': '仅保留旧字段已记录累计；历史批次、原始来源未知，未补造事件。未记录实收按累计已记录0展示，不证明实际未收货。',
        'photo_path': po.arrival_photo, 'operator_id': po.received_by,
        'received_at': po.received_at.isoformat() if po.received_at else None,
        'lines': [{'line_id': it['line_id'], 'quantity': historical_quantity(it.get('received_quantity', 0)),
                   'line_id_source': it['line_id_source'],
                   'original_received_quantity': it.get('received_quantity'),
                   'recorded': 'received_quantity' in it} for it in lines(po)]}


def new_baseline(items):
    return {'source': 'new_order_no_receipt', 'event_history_known': True,
        'note': '新采购从0开始，收货以有效批次累计。',
        'lines': [{'line_id': it['line_id'], 'quantity': 0, 'recorded': True} for it in items]}


def bill_lines(items):
    return {'source': 'purchase_generated_bill', 'note': '系统生成应付的原始采购行快照，不代表外部发票独立认证。',
        'items': [{k: it.get(k) for k in ('line_id','quantity','unit','unit_price','subtotal','currency')} for it in items]}


async def scope_lock(db, warehouse_id):
    await db.execute(select(Warehouse.id).where(Warehouse.id == warehouse_id).with_for_update())


async def policy(db, warehouse_id):
    rows = (await db.execute(select(SystemSetting).where(SystemSetting.warehouse_id == warehouse_id,
        SystemSetting.key == POLICY_KEY))).scalars().all()
    if len(rows)>1 or (rows and rows[0].value not in ('true','false')):
        raise HTTPException(503, '三单校验配置异常，请管理员核对')
    return {'strict': bool(rows and rows[0].value == 'true'), 'default': False,
        'quantity_mode': 'whole_units',
        'description': '关闭时保留原付款规则；开启后商品采购必须有结构化匹配依据，累计付款不超过已记录实收金额。预付款和非商品费用不套商品数量上限；旧待老板确认规则始终保留。'}


async def receipt_state(db, po):
    original = lines(po)
    ids = [it['line_id'] for it in original]
    issues = []
    if (not isinstance(po.items,list) or not original or len(original) != len(po.items) or len(set(ids)) != len(ids)
            or any(it['line_id_source']=='invalid_stored' for it in original)):
        issues.append('采购明细缺失、格式异常或行编号重复，未猜配')
    basis = baseline(po)
    base_rows = basis.get('lines', [])
    if not isinstance(base_rows,list): issues.append('历史基数明细格式异常');base_rows=[]
    base = {it['line_id']: it for it in base_rows if isinstance(it,dict) and isinstance(it.get('line_id'),str)}
    if len(base) != len(base_rows) or set(base) != set(ids):
        issues.append('历史基数与采购稳定行不一致')
    events = (await db.execute(select(PurchaseReceiptEvent).where(PurchaseReceiptEvent.purchase_order_id == po.id)
        .order_by(PurchaseReceiptEvent.id))).scalars().all()
    totals = {line_id: 0 for line_id in ids}
    batches = []
    for event in events:
        if event.warehouse_id != po.warehouse_id:
            raise HTTPException(409, '收货批次仓库关联异常，请管理员核对')
        batches.append({'id': event.id, 'request_key': event.request_key, 'items': event.items,
            'photo_path': event.photo_path, 'operator_id': event.operator_id, 'operator_name': event.operator_name,
            'received_at': event.received_at.isoformat(), 'remark': event.remark, 'source': event.source, 'status': event.status})
        if event.status != 'active': continue
        seen = set()
        if not isinstance(event.items,list): issues.append('历史批次明细异常'); continue
        for row in event.items:
            lid = row.get('line_id') if isinstance(row,dict) else None
            q = row.get('quantity') if isinstance(row,dict) else None
            expected = next((it for it in original if it['line_id'] == lid), None)
            if expected is None or not isinstance(lid,str) or lid in seen or type(q) is not int or q < 0 or row.get('unit') != expected.get('unit'):
                issues.append(f'批次#{event.id}行归属、单位或数量异常');continue
            seen.add(lid); totals[lid] += q
    result = []
    for it in original:
        lid = it['line_id']; b = base.get(lid, {})
        recorded = historical_quantity(b.get('quantity'))
        ordered = historical_quantity(it.get('quantity'))
        if recorded is None or ordered is None:
            issues.append(f'行{lid}的历史数量无法确定，未归零或截断')
        cumulative = recorded + totals[lid] if recorded is not None else None
        remaining = ordered - cumulative if ordered is not None and cumulative is not None else None
        result.append({**it, 'historical_received_quantity': recorded, 'batch_received_quantity': totals[lid],
            'received_quantity': cumulative, 'diff_quantity': remaining, 'remaining_quantity': max(remaining,0) if remaining is not None else None,
            'over_quantity': max(-remaining,0) if remaining is not None else None,
            'quantity_status': 'unknown' if remaining is None else 'matched' if remaining == 0 else 'short' if remaining > 0 else 'over',
            'unit_status': 'known' if it.get('unit') else 'unknown'})
    return {'items': result, 'baseline': basis, 'batches': batches, 'issues': list(dict.fromkeys(issues)),
        'quantity_mode': 'whole_units', 'quantity_mode_note': '现有采购数量仅支持整数单位；小数、负数和非数字输入不会自动截断或归零。',
        'has_recorded_receipt': bool(events or any(it.get('recorded') for it in base_rows if isinstance(it,dict)))}


async def matching(db, bill, po=None):
    from app.models import PayableBill
    from app.services.supplier_payable_read import checked_link
    configuration = await policy(db, bill.warehouse_id)
    document_kind = bill.matching_kind or 'unknown'
    result = {'kind': document_kind, 'kind_label': KINDS.get(document_kind,'类型待核实'),
        'policy': configuration, 'quantity_match': 'unknown', 'amount_match': 'unknown',
        'receipt_quantity_match': 'unknown', 'line_amount_match': 'unknown', 'payment_cap': None, 'currency': bill.currency,
        'notes': [], 'lines': [], 'status': 'unknown'}
    if po is None and bill.purchase_order_id:
        po = await db.get(PurchaseOrder, bill.purchase_order_id)
    if bill.purchase_order_id and po is None:
        raise HTTPException(409, '关联采购单缺失，请管理员核对')
    state = None
    if po:
        await checked_link(db,bill,po,bill.warehouse_id)
        state = await receipt_state(db,po)
        result['lines'] = state['items']; result['notes'].extend(state['issues'])
        result['purchase_order_id'] = po.id
        ordered_amount, invoiced_amount = amount(po.total_amount), amount(bill.amount)
        result.update(purchase_amount=float(ordered_amount) if ordered_amount is not None else None,
            bill_amount=float(invoiced_amount) if invoiced_amount is not None else None)
        result['amount_match'] = 'unknown' if ordered_amount is None or invoiced_amount is None else 'matched' if ordered_amount == invoiced_amount else 'different'
        result['receipt_quantity_match'] = ('unknown' if not state['has_recorded_receipt'] or state['issues'] or not state['items']
            else 'matched' if all(i['quantity_status']=='matched' for i in state['items'])
            else 'different' if any(i['quantity_status'] in ('short','over') for i in state['items']) else 'unknown')
        structured = bill.match_lines
        if isinstance(structured,dict) and isinstance(structured.get('items'),list):
            rows=structured['items']; m={r['line_id']:r for r in rows
                if isinstance(r,dict) and isinstance(r.get('line_id'),str) and r['line_id']}
            if len(m)==len(rows)==len(state['items']) and set(m)=={i['line_id'] for i in state['items']}:
                known = all(i.get('unit') and m[i['line_id']].get('unit') for i in state['items'])
                same = all(m[i['line_id']].get('quantity')==i.get('quantity') and m[i['line_id']].get('unit')==i.get('unit')
                    and m[i['line_id']].get('currency') == bill.currency for i in state['items'])
                result['quantity_match'] = 'unknown' if not known else 'matched' if same else 'different'
                prices_known=all(decimal(i.get('unit_price')) is not None and decimal(m[i['line_id']].get('unit_price')) is not None
                    and amount(i.get('subtotal')) is not None and amount(m[i['line_id']].get('subtotal')) is not None for i in state['items'])
                result['line_amount_match']='unknown' if not prices_known else 'matched' if all(
                    decimal(i.get('unit_price'))==decimal(m[i['line_id']].get('unit_price'))
                    and amount(i.get('subtotal'))==amount(m[i['line_id']].get('subtotal')) for i in state['items']) else 'different'
                if prices_known:
                    order_sum=sum((amount(i['subtotal']) for i in state['items']),Decimal(0))
                    bill_sum=sum((amount(r['subtotal']) for r in rows),Decimal(0))
                    arithmetic_known=all(historical_quantity(i.get('quantity')) is not None and historical_quantity(m[i['line_id']].get('quantity')) is not None for i in state['items'])
                    if not arithmetic_known:
                        result['line_amount_match']='unknown'
                    elif (order_sum!=ordered_amount or bill_sum!=invoiced_amount or any(
                            amount(decimal(i['unit_price'])*historical_quantity(i['quantity']))!=amount(i['subtotal'])
                            or amount(decimal(m[i['line_id']]['unit_price'])*historical_quantity(m[i['line_id']]['quantity']))!=amount(m[i['line_id']]['subtotal'])
                            for i in state['items'])):
                        result['line_amount_match']='different'
                        result['notes'].append('结构化行的单价×数量、小计或行合计与单据金额不一致；未改写金额。')
        if result['quantity_match']=='unknown': result['notes'].append('应付缺可靠结构化行或单位，数量三单匹配未知；未按名称或文字明细猜配。')
        cap = Decimal(0); cap_known = bool(state['items']) and not state['issues']
        for it in state['items']:
            price=decimal(it.get('unit_price')); ordered=historical_quantity(it.get('quantity')); received=it['received_quantity']
            if price is None or price < 0 or ordered is None or received is None or not it.get('unit'):
                cap_known=False;continue
            cap += min(ordered, received)*price
        result['payment_cap']=float(amount(cap)) if cap_known and amount(cap) is not None else None
        result['notes'].append(state['baseline'].get('note','历史来源未记录'))
    else:
        result['notes'].append('无真实采购关联，不能进行商品三单匹配；未补造采购或行映射。')
    if document_kind in ('prepayment','non_goods'):
        result['quantity_match']='not_applicable'; result['receipt_quantity_match']='not_applicable';result['payment_cap']=None
        result['status']='not_applicable'
        result['notes'].append('预付款或非商品费用不使用商品收货数量上限，仍保留原付款和老板复核规则。')
    elif document_kind=='goods' and all(result[k]=='matched' for k in ('quantity_match','receipt_quantity_match','amount_match','line_amount_match')):
        result['status']='matched'
    elif any(result[k] in ('different',) for k in ('quantity_match','receipt_quantity_match','amount_match','line_amount_match')):
        result['status']='different'
    snapshot = {'version':1,'bill':{k:getattr(bill,k) for k in ('id','warehouse_id','supplier_id','purchase_order_id','amount','currency','confirmed_amount','matching_kind','match_lines')},
        'purchase':None if po is None else {'id':po.id,'warehouse_id':po.warehouse_id,'supplier_id':po.supplier_id,
            'total_amount':po.total_amount,'currency':po.currency,'ordered_lines':[{k:i.get(k) for k in ('line_id','quantity','unit','unit_price','subtotal','currency')} for i in state['items']],
            'receipt_baseline':state['baseline'],'events':[{'id':e['id'],'status':e['status'],'items':e['items']} for e in state['batches']]}}
    result['snapshot']=snapshot; result['snapshot_hash']=fingerprint(snapshot)
    review=bill.match_review
    result['review']=review
    result['review_valid']=bool(review and review.get('snapshot_hash')==result['snapshot_hash'])
    result['review_status']='valid' if result['review_valid'] else 'stale' if review else 'not_reviewed'
    result['need_boss_confirm']=bill.need_boss_confirm=='true' or bool(review and not result['review_valid'])
    from app.models import DataChangeHistory
    history=(await db.execute(select(DataChangeHistory).where(DataChangeHistory.module=='payable',
        DataChangeHistory.warehouse_id==bill.warehouse_id,DataChangeHistory.record_id==bill.id,
        DataChangeHistory.operation_type.in_(['match_confirm','match_review_stale'])).order_by(DataChangeHistory.id))).scalars().all()
    result['review_history']=[{'id':h.id,'action':h.operation_type,'operator_name':h.operator_name,
        'created_at':h.created_at.isoformat(),'data':h.after_data} for h in history]
    return result


async def invalidate_review(db,bill,operator, *, receipt_changed=False):
    state=await matching(db,bill)
    has_quantity_difference=receipt_changed and state['receipt_quantity_match'] in ('different','unknown')
    stale=bool(bill.match_review and not state['review_valid'])
    if has_quantity_difference or stale:
        bill.need_boss_confirm='true'
    if stale:
        await record_history(db,module='payable',record_id=bill.id,operator=operator,operation_type='match_review_stale',
            after={'previous_snapshot_hash':bill.match_review.get('snapshot_hash'),'current_snapshot_hash':state['snapshot_hash'],
                   'reason':'后续收货或账单匹配字段变化，旧复核失效；不改变已有付款'},warehouse_id=bill.warehouse_id)
    return state


async def check_payment(db,bill,value):
    state=await matching(db,bill)
    if state['need_boss_confirm']:
        raise HTTPException(400,'该账单存在收货差异或复核已失效，需老板确认后才能付款')
    if not state['policy']['strict']: return
    if state['kind'] in ('prepayment','non_goods'): return
    if (state['kind']!='goods' or state['quantity_match']!='matched' or state['amount_match']!='matched'
            or state['line_amount_match']!='matched' or state['payment_cap'] is None or amount(bill.paid_amount) is None):
        raise HTTPException(400,'严格三单校验未通过：采购、单位、结构化应付或付款依据未知，请核对')
    if amount(bill.paid_amount)+amount(value)>amount(state['payment_cap']):
        raise HTTPException(400,f'严格三单校验：累计付款不能超过已记录实收金额 {state["payment_cap"]:.2f} {bill.currency}')
