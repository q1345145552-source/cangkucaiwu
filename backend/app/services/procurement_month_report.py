"""Read-only, frozen per-purchase-line price differences. This is not a cash/profit ledger."""
import csv,io,re
from datetime import datetime
from decimal import Decimal,localcontext,ROUND_HALF_UP
from fastapi import HTTPException
from sqlalchemy import select
from app.models import PurchaseOrder,PayableBill,Supplier,User,UserWarehouse
from app.core.timezone import THAI_TZ,thai_today
from app.services.payable_creation import fingerprint
from app.services.purchase_price_review import positive,quote_key
from app.services.supplier_quotes import exact
from app.services.sku_catalog import UNITS

VERSION='purchase-line-price-reference-v1'
NOTE='仅采购商品价差参考，不代表实际付款节省、损失或回扣；不换汇，不自动处罚。'
DATE_NOTE='按采购创建时间的泰国日历月统计，月初含、下月初不含；按当前已生效状态计入，待审/驳回/取消及关联应付作废另列排除。不是付款月或历史时点状态还原。'
MONEY_NOTE='历史差额=(下单时历史行算术均价-采购基本单价)×基本数量；最低差额=(采购基本单价-下单时最低有效价)×基本数量。每行四舍五入到分后合计；正负分别列出，净额保留符号。'

def amount(d):
 with localcontext() as ctx:
  ctx.prec=64;return format(d.quantize(Decimal('.01'),rounding=ROUND_HALF_UP),'f')
def add_amount(value,change):
 with localcontext() as ctx:
  ctx.prec=64;return amount(Decimal(value)+change)
def parse_month(month):
 month=month or thai_today().strftime('%Y-%m')
 if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])',month):raise HTTPException(400,'月份请用YYYY-MM格式')
 y,m=map(int,month.split('-'))
 if not 1<=y<=9998:raise HTTPException(400,'月份年份超出支持范围')
 return month,datetime(y,m,1,tzinfo=THAI_TZ),datetime(y+int(m==12),m%12+1,1,tzinfo=THAI_TZ)

def safe_key(value,wid):
 try:
  key=quote_key(value);selected=value.get('selected_quote') or {};mapping=selected.get('product_binding',{}).get('sku_mapping') or {};sku=mapping.get('sku_snapshot') or {}
  if not key or mapping.get('standard_sku_id')!=key['sku_id'] or (sku.get('id'),sku.get('version'),sku.get('warehouse_id'))!=(key['sku_id'],key['sku_version'],wid):return None
  return key
 except (TypeError,AttributeError,KeyError,ValueError):return None

def line_value(po,it,index,supplier_name,orderer_name,state_reason):
 ref=it.get('line_id') or f'legacy-{index}'
 r={'order_id':po.id,'order_number':po.order_number,'line_id':it.get('line_id'),'line_ref':ref,'line_index':index,'product_name':it.get('product_name') or '未记录','original_unit':it.get('unit'),
  'created_at':po.created_at.astimezone(THAI_TZ).isoformat() if po.created_at else None,'status':po.status,'flow_status':po.flow_status,
  'supplier_id':po.supplier_id,'supplier_name':supplier_name,'orderer_id':po.created_by,'orderer_name':orderer_name,'currency':po.currency,
  'quantity':str(it.get('quantity')) if it.get('quantity') is not None else None,'purchase_price':str(it.get('unit_price')) if it.get('unit_price') is not None else None,
  'base_quantity':None,'base_unit':None,'base_unit_label':None,'sku_code':None,'sku_name':None,'purchase_base_price':None,'historical_base_price':None,'lowest_base_price':None,'historical_difference':None,'lowest_difference':None,
  'historical_available':False,'lowest_available':False,'historical_unavailable':None,'lowest_unavailable':None,'group_key':None,'group':None,'state_exclusion':state_reason,
  'reason':it.get('reason') or '', 'lowest_candidates':[], 'selected_quote':None,'legacy_history_reference':None,'historical_evidence':None,
  'purchase_url':f'/suppliers/purchase-orders/{po.id}#purchase-line-{ref}'}
 snap=it.get('pricing_snapshot') if isinstance(it.get('pricing_snapshot'),dict) else {};h=snap.get('historical_price_review') if isinstance(snap.get('historical_price_review'),dict) else {};q=snap.get('selected_quote') if isinstance(snap.get('selected_quote'),dict) else {}
 if h.get('basis')=='legacy_name_spec_unit_reference':r['legacy_history_reference']=h
 reason=None;key=safe_key(snap,po.warehouse_id) if isinstance(snap,dict) else None
 quantity=positive(it.get('quantity'));price=positive(it.get('unit_price'))
 if not it.get('line_id'):reason='旧行缺稳定行编号，无法作为严格可比行'
 elif snap.get('mode')!='quote':reason='旧数据或原产品单价模式，无可靠标准SKU报价基线'
 elif key is None:reason='SKU、基本单位换算或明确费用口径证据缺失'
 elif q.get('warehouse_id')!=po.warehouse_id or q.get('supplier_id')!=po.supplier_id or q.get('product_id')!=it.get('product_id'):reason='冻结报价的仓库、供应商或产品归属不一致'
 elif not quantity or not price:reason='原采购数量或价格未知'
 elif (snap.get('quantity')!=exact(quantity) or snap.get('unit_price')!=exact(price) or snap.get('unit')!=it.get('unit') or snap.get('currency')!=po.currency or key['currency']!=po.currency):reason='采购行与冻结报价数量、价格、币种或原单位不一致'
 elif not positive(q.get('terms',{}).get('base_unit_factor')):reason='基本单位换算未知'
 if reason:
  r.update(historical_unavailable=reason,lowest_unavailable=reason);return r
 factor=Decimal(q['terms']['base_unit_factor'])
 with localcontext() as ctx:
  ctx.prec=48;base_quantity=quantity*factor;unit_price=price/factor
  if positive(snap.get('base_quantity'))!=base_quantity:reason='冻结基本数量与已核实换算不一致'
  sku_snapshot=q.get('product_binding',{}).get('sku_mapping',{}).get('sku_snapshot',{})
  r.update(base_quantity=exact(base_quantity),base_unit=key['base_unit'],base_unit_label=UNITS.get(key['base_unit'],key['base_unit']),sku_code=sku_snapshot.get('code'),sku_name=sku_snapshot.get('name'),purchase_base_price=exact(unit_price),group_key=fingerprint(key),group=key,
   supplier_name=q.get('supplier_name') or supplier_name,selected_quote={'id':q.get('id'),'code':q.get('code'),'revision':q.get('revision'),'version':q.get('version'),'tier':q.get('tier'),'terms':q.get('terms')})
  if reason:r.update(historical_unavailable=reason,lowest_unavailable=reason);return r
  r['historical_evidence']=h
  hist=positive(h.get('average_normalized_price'))
  samples=h.get('samples') if isinstance(h.get('samples'),list) else []
  sample_prices=[positive(x.get('normalized_price')) if isinstance(x,dict) else None for x in samples]
  consistent=bool(sample_prices and all(x is not None for x in sample_prices) and sum(sample_prices,Decimal(0))/len(sample_prices)==hist)
  if h.get('basis')=='same_sku_known_terms' and h.get('comparison_key')==key and hist is not None and positive(h.get('current_normalized_price'))==unit_price and consistent:
   r.update(historical_available=not state_reason,historical_base_price=exact(hist),historical_difference=amount((hist-unit_price)*base_quantity) if not state_reason else None)
  else:r['historical_unavailable']='没有同SKU/币种/单位/费用口径的冻结历史行算术均价证据'
  candidates=snap.get('eligible_candidates') if isinstance(snap.get('eligible_candidates'),list) else [];valid=[]
  for c in candidates:
   if isinstance(c,dict) and c.get('eligible') and c.get('warehouse_id')==po.warehouse_id and safe_key({'selected_quote':c},po.warehouse_id)==key:
    cp=positive(c.get('comparable_price'));cf=positive(c.get('terms',{}).get('base_unit_factor'));ct=positive((c.get('tier') or {}).get('unit_price'))
    if cp and cf and ct and ct/cf==cp:valid.append(c)
  lowest=positive(snap.get('lowest_comparable_price'))
  true_lowest=min((Decimal(c['comparable_price']) for c in valid),default=None)
  ties=[c for c in valid if Decimal(c['comparable_price'])==true_lowest]
  if lowest is not None and lowest==true_lowest and sorted(c['id'] for c in ties)==sorted(snap.get('lowest') or []) and unit_price>=lowest:
   r.update(lowest_available=not state_reason,lowest_base_price=exact(lowest),lowest_difference=amount((unit_price-lowest)*base_quantity) if not state_reason else None,
    lowest_candidates=[{'id':c['id'],'code':c.get('code'),'revision':c.get('revision'),'supplier_id':c.get('supplier_id'),'supplier_name':c.get('supplier_name'),'original_unit':c.get('terms',{}).get('original_unit'),'tier':c.get('tier'),'base_price':c['comparable_price']} for c in ties])
  else:r['lowest_unavailable']='没有一致可核实的下单时最低及全部并列候选证据'
 if state_reason:r['historical_unavailable']=r['lowest_unavailable']=state_reason
 return r

def order_state_exclusion(po,bills):
 state=None
 if po.status!='confirmed' or po.flow_status in ('cancelled','canceled','voided','rejected'):state='采购尚未生效或当前已驳回/取消/作废'
 if po.payable_bill_id:
  b=bills.get(po.payable_bill_id)
  if not b or b.purchase_order_id!=po.id or b.supplier_id!=po.supplier_id or b.currency!=po.currency:state='采购应付关联异常，未计入'
  elif b.status=='voided':state='关联应付已作废，未计入'
 return state

async def rows_for(db,wid,*,month=None,supplier_id=None,orderer_id=None,currency=None,po_id=None):
 month,start,end=parse_month(month)
 if supplier_id is not None:
  supplier=await db.get(Supplier,supplier_id)
  if not supplier or supplier.warehouse_id!=wid:raise HTTPException(404,'当前仓库未找到筛选供应商')
 if orderer_id is not None:
  member=(await db.execute(select(UserWarehouse.id).where(UserWarehouse.user_id==orderer_id,UserWarehouse.warehouse_id==wid).limit(1))).first()
  own_history=(await db.execute(select(PurchaseOrder.id).where(PurchaseOrder.created_by==orderer_id,PurchaseOrder.warehouse_id==wid).limit(1))).first()
  if not member and not own_history:raise HTTPException(404,'当前仓库未找到筛选采购人')
 q=select(PurchaseOrder).where(PurchaseOrder.warehouse_id==wid)
 if po_id is None:q=q.where(PurchaseOrder.created_at>=start,PurchaseOrder.created_at<end)
 else:q=q.where(PurchaseOrder.id==po_id)
 for column,value in [(PurchaseOrder.supplier_id,supplier_id),(PurchaseOrder.created_by,orderer_id),(PurchaseOrder.currency,currency)]:
  if value is not None:q=q.where(column==value)
 orders=(await db.execute(q.order_by(PurchaseOrder.created_at,PurchaseOrder.id))).scalars().all()
 suppliers={s.id:s.name for s in (await db.execute(select(Supplier).where(Supplier.warehouse_id==wid))).scalars()}
 ids={p.created_by for p in orders if p.created_by};users={u.id:u.display_name or u.username for u in (await db.execute(select(User).where(User.id.in_(ids)))).scalars()}
 bill_ids={p.payable_bill_id for p in orders if p.payable_bill_id};bills={b.id:b for b in (await db.execute(select(PayableBill).where(PayableBill.warehouse_id==wid,PayableBill.id.in_(bill_ids)))).scalars()}
 result=[]
 for po in orders:
  state=order_state_exclusion(po,bills)
  items=[it if isinstance(it,dict) else {} for it in po.items] if isinstance(po.items,list) else [{}]
  counts={it.get('line_id'):sum(1 for x in items if x.get('line_id')==it.get('line_id')) for it in items if it.get('line_id')}
  for i,it in enumerate(items):
   reason='稳定行编号重复，未计入' if counts.get(it.get('line_id'),0)>1 else state
   result.append(line_value(po,it,i,suppliers.get(po.supplier_id,'供应商档案未找到'),users.get(po.created_by,'账号名称未找到（按账号编号筛选）'),reason))
 return month,result

def select_rows(rows,view):
 if view=='non_lowest':return [r for r in rows if r['lowest_available'] and Decimal(r['lowest_difference'])>0]
 if view=='unavailable':return [r for r in rows if not r['historical_available'] or not r['lowest_available']]
 return rows

def summary(rows):
 active=[r for r in rows if not r['state_exclusion']];groups={}
 for r in active:
  if not r['group_key']:continue
  g=groups.setdefault(r['group_key'],{'key':r['group_key'],'group':r['group'],'sku_code':r['sku_code'],'sku_name':r['sku_name'],'base_unit_label':r['base_unit_label'],'line_count':0,'historical':{'count':0,'positive':'0.00','negative':'0.00','net':'0.00'},'lowest':{'count':0,'positive':'0.00','negative':'0.00','net':'0.00'}});g['line_count']+=1
  for name in ('historical','lowest'):
   if not r[name+'_available']:continue
   n=Decimal(r[name+'_difference']);v=g[name];v['count']+=1
   for k in ('net','positive' if n>=0 else 'negative'):v[k]=add_amount(v[k],n)
 return {'groups':list(groups.values()),'coverage':{'denominator':len(active),'definition':'当前筛选内已生效且无状态排除的采购行数（包括缺基线行）；状态排除另列，不进入金额',
  'historical_calculable':sum(r['historical_available'] for r in active),'lowest_calculable':sum(r['lowest_available'] for r in active),
  'historical_percent':amount(Decimal(sum(r['historical_available'] for r in active))*100/len(active)) if active else None,
  'lowest_percent':amount(Decimal(sum(r['lowest_available'] for r in active))*100/len(active)) if active else None,
  'state_excluded':len(rows)-len(active)},'total_lines':len(rows)}

async def report(db,wid,*,page=1,page_size=20,view='all',**filters):
 month,rows=await rows_for(db,wid,**filters);rows=select_rows(rows,view)
 return {'warehouse_id':wid,'month':month,'version':VERSION,'notice':NOTE,'date_basis':DATE_NOTE,'formula':MONEY_NOTE,**summary(rows),
  'filter_options':{'suppliers':list({r['supplier_id']:{'id':r['supplier_id'],'name':r['supplier_name']} for r in rows}.values()),'orderers':list({r['orderer_id']:{'id':r['orderer_id'],'name':r['orderer_name']} for r in rows if r['orderer_id'] is not None}.values())},
  'data':rows[(page-1)*page_size:page*page_size],'page':page,'page_size':page_size}

async def line_detail(db,wid,po_id,line_ref):
 _,rows=await rows_for(db,wid,po_id=po_id)
 if not rows:raise HTTPException(404,'当前仓库未找到该采购单')
 found=[r for r in rows if r['line_ref']==line_ref]
 if len(found)!=1:raise HTTPException(404 if not found else 409,'未找到唯一对应采购行，请核对原单')
 return {'data':found[0],'version':VERSION,'notice':NOTE,'date_basis':DATE_NOTE,'formula':MONEY_NOTE}

def cell(value,numeric=False):
 if value is None:return '不可计算'
 s=str(value)
 if numeric and re.fullmatch(r'-?\d+(?:\.\d+)?',s):return s
 return "'"+s if s.lstrip(' \t\r\n').startswith(('=','+','-','@')) else s

async def export(db,wid,*,view='all',**filters):
 month,rows=await rows_for(db,wid,**filters);rows=select_rows(rows,view);out=io.StringIO(newline='');writer=csv.writer(out)
 writer.writerow(['月份','采购单编号','单号','行编号','创建时间(泰国)','状态','采购人编号','采购人(当前账号名)','供应商编号','供应商(冻结报价名优先)','产品','币种','SKU编号','SKU版本','基本单位','费用口径','原数量','基本数量','采购基本单价','冻结历史行算术均价','相对历史差额(正节省参考负超历史)','当时最低有效基本价','相对当时最低差额(正高于最低)','非最低原因','历史不可算原因','最低不可算原因','状态排除','原单入口'])
 for r in rows:
  g=r['group'] or {};fees=g.get('fees') or {};mode={'included':'已含','excluded':'未含','unknown':'待确认'};fee_label=f"税:{mode.get(fees.get('tax_mode'),'待确认')} 税率:{fees.get('tax_rate') or '未记录'} 运费:{mode.get(fees.get('freight_mode'),'待确认')} {fees.get('freight_terms','')} 其他:{'无' if fees.get('other_fees')=='none' else fees.get('other_fees','待确认')}"
  vals=[month,r['order_id'],r['order_number'],r['line_ref'],r['created_at'],{'confirmed':'已生效','pending':'待审批','rejected':'已驳回','cancelled':'已取消','voided':'已作废'}.get(r['status'],r['status']),r['orderer_id'],r['orderer_name'],r['supplier_id'],r['supplier_name'],r['product_name'],r['currency'],g.get('sku_id'),g.get('sku_version'),r['base_unit_label'],fee_label,r['quantity'],r['base_quantity'],r['purchase_base_price'],r['historical_base_price'],r['historical_difference'],r['lowest_base_price'],r['lowest_difference'],r['reason'],r['historical_unavailable'] or '',r['lowest_unavailable'] or '',r['state_exclusion'] or '',r['purchase_url']]
  writer.writerow([cell(v,i in {1,6,8,12,16,17,18,19,20,21,22}) for i,v in enumerate(vals)])
 return ('\ufeff'+out.getvalue()).encode('utf-8')
