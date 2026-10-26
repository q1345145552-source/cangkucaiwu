"""Frozen historical-price warnings; separate from current effective lowest quotations."""
from datetime import timedelta
from decimal import Decimal, InvalidOperation, localcontext
from fastapi import HTTPException
from sqlalchemy import select
from app.models import ProcurementPriceHistory
from app.services.payable_creation import fingerprint
from app.services.supplier_quotes import exact, known_fees
from app.core.security import create_access_token, decode_token
from app.core.timezone import thai_now


def positive(value):
 try:
  d=Decimal(str(value))
  return d if d.is_finite() and d>0 else None
 except (InvalidOperation, ValueError, TypeError):return None


def quote_key(snapshot):
 selected=snapshot.get('selected_quote') or {};terms=selected.get('terms') or {};binding=selected.get('product_binding') or {}
 fees=terms.get('fees') or {}
 try:
  if not known_fees(fees) or not positive(terms.get('base_unit_factor')):return None
 except KeyError:return None
 if not binding.get('sku_id') or not binding.get('sku_version') or not terms.get('base_unit') or not terms.get('currency'):return None
 return {'sku_id':binding['sku_id'],'sku_version':binding['sku_version'],'base_unit':terms['base_unit'],'currency':terms['currency'],'fees':fees}


async def evaluate(db,wid,pricing,products,threshold):
 """Arithmetic mean of historical lines, not quantity-weighted. Each tier stays frozen."""
 histories=(await db.execute(select(ProcurementPriceHistory).where(ProcurementPriceHistory.warehouse_id==wid).order_by(ProcurementPriceHistory.id))).scalars().all()
 result=[]
 for row in pricing['rows']:
  product=products[row['product_id']];quote=row['mode']=='quote';key=quote_key(row) if quote else None
  factor=positive((row.get('selected_quote') or {}).get('terms',{}).get('base_unit_factor')) if quote else Decimal(1)
  basis='same_sku_known_terms' if quote else 'legacy_name_spec_unit_reference'
  note='同SKU及版本、同币种、同基本单位和明确费用口径的历史采购行均价参考；不是当前最低报价或真实损失。' if quote else '旧口径参考：仅同名规格、币种及原单位的历史行均价，不代表同一标准SKU、有效最低价或真实损失。'
  samples=[];excluded=[]
  for h in histories:
   snap=h.pricing_snapshot or {};why=None;hf=Decimal(1);price=positive(h.unit_price)
   if quote:
    if key is None:why='当前报价费用、SKU或换算证据不完整'
    elif snap.get('mode')!='quote' or quote_key(snap)!=key:why='历史SKU/版本、币种、基本单位、费用或换算证据不一致或缺失'
    else:
     hf=positive(snap['selected_quote']['terms']['base_unit_factor']);price=positive(snap.get('unit_price'))
     if h.currency!=key['currency'] or h.unit!=snap.get('unit'):why='历史存储币种或原单位与快照不一致'
     if positive(h.unit_price)!=price:why='历史价格与冻结报价证据不一致'
   elif h.product_name!=product.product_name or (h.spec or '')!=(product.spec or '') or not product.currency or not product.unit or h.currency!=product.currency or h.unit!=product.unit or snap.get('mode')=='quote':why='不是同名规格币种原单位的旧口径历史'
   if not price:why=why or '历史价格未知或无效'
   if why:excluded.append({'history_id':h.id,'reason':why});continue
   with localcontext() as ctx:
    ctx.prec=48;normalized=price/hf
   samples.append({'history_id':h.id,'purchase_order_id':h.purchase_order_id,'quantity':h.quantity,'original_unit':h.unit,'original_price':exact(price),'factor':exact(hf),'normalized_price':exact(normalized),'created_at':h.created_at.isoformat() if h.created_at else None})
  with localcontext() as ctx:
   ctx.prec=48;avg=sum((Decimal(s['normalized_price']) for s in samples),Decimal(0))/len(samples) if samples else None
   current=Decimal(row['unit_price'])/factor if factor else None
   exceeded=bool(avg is not None and current is not None and current>avg*(1+Decimal(str(threshold))/100))
   percent=((current-avg)/avg*100).quantize(Decimal('.1')) if avg is not None and current is not None else None
   result.append({'basis':basis,'note':note,'threshold':str(threshold),'evaluated_at':thai_now().isoformat(),'comparison_key':key,'reference_unit':key['base_unit'] if key else product.unit,
    'product_id':product.id,'product_name':product.product_name,'spec':product.spec,'currency':row['currency'],'quantity':row['quantity'],'original_unit':row['unit'],'unit_price':row['unit_price'],
    'factor':exact(factor),'historical_avg':exact(avg*factor) if avg is not None and factor else None,'average_normalized_price':exact(avg),'current_normalized_price':exact(current),
    'exceed_percent':exact(percent),'is_anomaly':exceeded,'samples':samples,'excluded':excluded,'available':avg is not None,'unavailable_reason':None if samples else '没有可核实的可比历史价格，无法计算；未按0处理'})
 return result


def review_binding(wid,user_id,key,supplier_id,pricing):
 # Reasons may be filled after the warning; the selection/quantity/price/conditions may not change.
 return fingerprint({'warehouse':wid,'user':user_id,'key':key,'supplier':supplier_id,'pricing':pricing['version']})


def restore(token,binding):
 value=decode_token(token)
 if not value or value.get('purpose')!='purchase_price_review' or value.get('binding')!=binding or not isinstance(value.get('reviews'),list):
  raise HTTPException(409,{'code':'price_review_changed','message':'历史价格核对已过期或采购条件已改变，请重新核对后确认；未创建采购'})
 return value['reviews']


def seal(reviews,binding):
 return create_access_token({'purpose':'purchase_price_review','binding':binding,'reviews':reviews},timedelta(minutes=30))


def public_anomalies(reviews):
 # Preserve the original numeric response fields; the frozen evidence keeps exact decimals.
 return [{**r,**{k:float(r[k]) for k in ('unit_price','historical_avg','exceed_percent')},
   'unit_price_exact':r['unit_price'],'historical_avg_exact':r['historical_avg'],'exceed_percent_exact':r['exceed_percent']} for r in reviews]
