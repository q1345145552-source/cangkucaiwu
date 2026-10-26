"""Owner-only explanatory signals over existing procurement evidence; no business writes."""
import csv,io
from datetime import timedelta
from decimal import Decimal,localcontext
from sqlalchemy import select,or_
from app.models import PurchaseOrder,PayableBill,Supplier,SystemSetting
from app.services import procurement_month_report as prices,purchase_matching as receipts
from app.services.payable_creation import fingerprint

VERSION='procurement-evidence-risk-v1'
NOTICE='仅待核实线索，不认定回扣、损失或违规；不评分、不自动处罚、不改变采购付款。急单、交期、质量及选择理由需人工结合核实。'
RULES={'historical_price':'冻结历史价格异常','non_lowest':'非最低有效价','new_supplier':'系统首次有效采购供应商','concentration':'供应商集中度','split_window':'24小时累计疑似拆单','self_receipt':'同人下单收货','receipt_quantity':'累计收货数量'}

def dec(v):return receipts.decimal(v)
def dt(v):return v.astimezone(prices.THAI_TZ) if v is not None else None

def evidence(po,line=None,event=None):
 lid=line.get('line_ref') if line else None
 return {'order_id':po.id,'order_number':po.order_number,'orderer_id':po.created_by,'supplier_id':po.supplier_id,'currency':po.currency,'amount':prices.amount(dec(po.total_amount)) if dec(po.total_amount) is not None else None,'created_at':dt(po.created_at).isoformat() if po.created_at else None,'line_id':lid,'event_id':event,
  'url':f'/suppliers/purchase-orders/{po.id}'+(f'#receipt-event-{event}' if event is not None else f'#purchase-line-{lid}' if lid else ''),'remark':po.remark or ''}

def signal(rule,subject,state,message,threshold,denominator,source,orders,**detail):
 return {'id':fingerprint({'rule':rule,'subject':subject,'version':VERSION}),'subject':subject,'rule':rule,'label':RULES[rule],'version':VERSION,'state':state,'explanation':message,'threshold':threshold,'denominator':denominator,'source':source,'time_basis':prices.DATE_NOTE,'evidence':orders,'detail':detail,'limitation':NOTICE}

async def settings(db,wid):
 # Existing policy keys and precedence, but do not conceal invalid values behind a default.
 from app.api.v1.suppliers import DEFAULT_CONCENTRATION_THRESHOLD
 rows=(await db.execute(select(SystemSetting).where(SystemSetting.warehouse_id.in_([wid,0]),SystemSetting.key.in_(['supplier_concentration_threshold','purchase_approval_threshold'])))).scalars().all()
 def read(key,default):
  found=[r for r in rows if r.key==key and r.warehouse_id==wid] or [r for r in rows if r.key==key and r.warehouse_id==0]
  value=dec(found[0].value) if len(found)==1 else default if not found else None
  return {'value':str(value) if value is not None else None,'source':f'system_settings:{found[0].id}' if len(found)==1 else 'existing_default' if not found else 'invalid_duplicate','warehouse_id':found[0].warehouse_id if len(found)==1 else None,'key':key}
 c=read('supplier_concentration_threshold',Decimal(str(DEFAULT_CONCENTRATION_THRESHOLD)));a=read('purchase_approval_threshold',None)
 if c['value'] is not None and not 0<=dec(c['value'])<=100:c['value']=None
 if a['value'] is not None and dec(a['value'])<=0:a['value']=None
 return {'concentration':c,'approval_THB':a,'split_window_hours':24,'split_basis':'仅复用现有泰铢审批门槛；人民币没有可靠门槛则不可判断。当前门槛回看，不证明采购当时规避审批。24小时是本版本线索窗口，不新增审批政策。'}

async def _calculate(db,wid,*,month=None,supplier_id=None,orderer_id=None,currency=None):
 month,start,end=prices.parse_month(month)
 _,lines=await prices.rows_for(db,wid,month=month,supplier_id=supplier_id,orderer_id=orderer_id,currency=currency)
 policy=await settings(db,wid)
 all_orders=(await db.execute(select(PurchaseOrder).where(PurchaseOrder.warehouse_id==wid,or_(PurchaseOrder.created_at<end,PurchaseOrder.created_at.is_(None))).order_by(PurchaseOrder.created_at,PurchaseOrder.id))).scalars().all()
 bills={b.id:b for b in (await db.execute(select(PayableBill).where(PayableBill.warehouse_id==wid,PayableBill.id.in_({p.payable_bill_id for p in all_orders if p.payable_bill_id})))).scalars()}
 suppliers={s.id:s for s in (await db.execute(select(Supplier).where(Supplier.warehouse_id==wid))).scalars()}
 effective=[p for p in all_orders if not prices.order_state_exclusion(p,bills) and dec(p.total_amount) is not None and dec(p.total_amount)>0 and p.supplier_id in suppliers and p.currency in ('THB','CNY')]
 def matches(p):return (supplier_id is None or p.supplier_id==supplier_id) and (orderer_id is None or p.created_by==orderer_id) and (currency is None or p.currency==currency)
 orders=[p for p in effective if p.created_at and start<=dt(p.created_at)<end and matches(p)]
 by_id={p.id:p for p in orders};observations=[]
 for row in lines:
  if row['order_id'] not in by_id:continue
  po=by_id[row['order_id']];subject=(po.id,row['line_ref']) if not row['state_exclusion'] else ('invalid_line',po.id,row['line_index']);e=[evidence(po,row if not row['state_exclusion'] else None)];h=row.get('historical_evidence') or {};threshold=dec(h.get('threshold'))
  known=row['historical_available'] and threshold is not None and threshold>=0
  with localcontext() as ctx:
   ctx.prec=48;pct=(dec(row['purchase_base_price'])/dec(row['historical_base_price'])-1)*100 if known else None
  high=known and pct>threshold
  observations.append(signal('historical_price',subject,'attention' if high else 'normal' if known else 'unavailable',f'采购基本价高于冻结历史行均价 {prices.amount(pct)}%，请核实' if high else '未超过冻结历史异常阈值' if known else row['historical_unavailable'] or '冻结阈值不可核实',{'percent':str(threshold) if threshold is not None else None,'evaluated_at':h.get('evaluated_at')},'本月筛选内有效采购行；旧口径/未知依据另列不可判断','R6冻结historical_price_review + R7严格可比判定',e,price=row,percent=prices.amount(pct) if pct is not None else None))
  known=row['lowest_available'];high=known and dec(row['lowest_difference'])>0
  observations.append(signal('non_lowest',subject,'attention' if high else 'normal' if known else 'unavailable','高于当时最低有效可比价；已有理由不自动认定违规或无风险' if high else '属于当时最低或并列最低' if known else row['lowest_unavailable'],{'difference_gt':'0.00'},'本月筛选内有效采购行','R6冻结eligible_candidates + R7严格可比判定',e,price=row))
 # Count each order once, never count payable payments or price history as another order.
 totals={};aggregate={};concentration={}
 for p in orders:
  value=dec(p.total_amount);totals[p.currency]=totals.get(p.currency,Decimal(0))+value
  key=(p.created_by,p.supplier_id,p.currency);g=aggregate.setdefault(key,{'orderer_id':p.created_by,'supplier_id':p.supplier_id,'supplier_name':suppliers[p.supplier_id].name,'currency':p.currency,'order_count':0,'amount':Decimal(0),'order_ids':[]});g['order_count']+=1;g['amount']+=value;g['order_ids'].append(p.id)
  concentration.setdefault((p.supplier_id,p.currency),[]).append(p)
 for (sid,cur),pos in concentration.items():
  numerator=sum((dec(p.total_amount) for p in pos),Decimal(0));denominator=totals[cur];pct=numerator*100/denominator if denominator else None;threshold=dec(policy['concentration']['value']);known=threshold is not None and pct is not None
  observations.append(signal('concentration',(sid,cur),'attention' if known and pct>threshold else 'normal' if known else 'unavailable','占比超过当前集中度阈值，需结合供货约束核实' if known and pct>threshold else '未超过当前集中度阈值' if known else '配置或分母无法核实',policy['concentration'],{'amount':prices.amount(denominator),'currency':cur,'scope':'当前筛选内所有有效采购单金额，每单一次'},'当前采购单金额 + 现有集中度配置',[evidence(p) for p in pos],supplier_id=sid,currency=cur,amount=prices.amount(numerator),percent=prices.amount(pct) if pct is not None else None))
 # New = reliably dated system-first effective purchase; not proof of first real-world cooperation.
 for sid in sorted({p.supplier_id for p in orders}):
  history=[p for p in effective if p.supplier_id==sid];dated=[p for p in history if p.created_at];first=min((dt(p.created_at) for p in dated),default=None);registered=dt(suppliers[sid].created_at)
  known=bool(first and registered and registered<=first and len(dated)==len(history));new=known and start<=first<end
  observations.append(signal('new_supplier',sid,'info' if new else 'normal' if known else 'unavailable','系统当前可核记录中首次有效采购在本月；不证明首次真实合作' if new else '当前可核首次有效采购不在本月' if known else '供应商登记或有效采购历史日期缺失/冲突，不假定为新供应商',{'definition':'可靠登记日期不晚于首笔采购，且无缺日期有效历史；首次有效采购在本月'},'当前筛选内使用的供应商；首次日期核全部本仓有效历史','suppliers.created_at + 本仓全部当前有效PO',[evidence(p) for p in orders if p.supplier_id==sid],supplier_id=sid,registered_at=registered.isoformat() if registered else None,first_effective_at=first.isoformat() if first else None))
 # Deterministic minimal crossing episodes from known history: no order reused, assignment at crossing.
 for cur in sorted({p.currency for p in orders}):
  threshold=dec(policy['approval_THB']['value']) if cur=='THB' else None
  candidates=[p for p in effective if matches(p) and p.currency==cur]
  if threshold is None:
   observations.append(signal('split_window',('unconfigured',cur),'unavailable','没有可核审批金额门槛，不判断疑似拆单',{'currency':cur,'value':None},'当前筛选有效订单','现有purchase_approval_threshold（仅THB）',[evidence(p) for p in orders if p.currency==cur],currency=cur));continue
  grouped={}
  for p in candidates:
   if p.created_by and p.created_at and dec(p.total_amount)<threshold:grouped.setdefault((p.created_by,p.supplier_id),[]).append(p)
  flagged=set()
  for (uid,sid),pos in grouped.items():
   pos.sort(key=lambda p:(dt(p.created_at),p.id));i=0
   while i<len(pos):
    total=Decimal(0);j=i
    while j<len(pos) and dt(pos[j].created_at)<dt(pos[i].created_at)+timedelta(hours=24):
     total+=dec(pos[j].total_amount)
     if j>i and total>=threshold:break
     j+=1
    if j<len(pos) and j>i and total>=threshold and dt(pos[j].created_at)<dt(pos[i].created_at)+timedelta(hours=24):
     members=pos[i:j+1];flagged.update(p.id for p in members)
     if start<=dt(pos[j].created_at)<end:
      observations.append(signal('split_window',tuple(p.id for p in members),'attention','同人/供应商/币种24小时内单笔均低于门槛，累计达到门槛；需核实是否合理急单',{'currency':cur,**policy['approval_THB'],'window_hours':24,'assignment':'累计首次达到门槛时点所属月，成员只使用一次'}, {'orders':len(candidates),'scope':'当前筛选币种的全部本仓有效历史；窗口跨月取证'},'当前PO金额与创建时间；当前配置不证明当时政策',[evidence(p) for p in members],currency=cur,amount=prices.amount(total),orderer_id=uid,supplier_id=sid,crossing_at=dt(pos[j].created_at).isoformat()))
     i=j+1
    else:i+=1
  for p in orders:
   if p.currency==cur and p.id not in flagged:
    known=bool(p.created_by and p.created_at)
    observations.append(signal('split_window',('not_crossing',p.id),'normal' if known else 'unavailable','未形成该版本累计越线组合（不代表无其他风险）' if known else '采购人或时间缺失，不能判断',{'currency':cur,**policy['approval_THB'],'window_hours':24},'本月筛选有效采购单','同人/供应商/币种时间窗',[evidence(p)],currency=cur))
 for po in orders:
  state=await receipts.receipt_state(db,po)
  events=[e for e in state['batches'] if e['status']=='active']
  if not events or state['issues']:
   observations.append(signal('self_receipt',po.id,'unavailable','没有可核真实收货事件或记录有异常，旧累计/姓名不能推断本人收货',None,'本月有效采购的真实有效收货事件','R3 receipt_state',[evidence(po)],issues=state['issues']))
  else:
   for event in events:
    known=bool(po.created_by and event['operator_id']);same=known and po.created_by==event['operator_id']
    observations.append(signal('self_receipt',(po.id,event['id']),'attention' if same else 'normal' if known else 'unavailable','采购人与实际收货事件操作者账号相同，需核实职责安排' if same else '该次收货操作者与采购人不同' if known else '账号依据缺失',{'comparison':'稳定账号ID，不比名字'},'本月有效采购的真实有效收货事件','R3 purchase_receipt_events',[evidence(po,event=event['id'])],event=event))
  for index,item in enumerate(state['items'] or [{}]):
   lid=item.get('line_id');known=not state['issues'] and item.get('line_id_source')=='stored' and state['baseline'].get('event_history_known') is True and item.get('quantity_status') in ('matched','short','over')
   q=item.get('quantity_status');msg={'matched':'累计已记录数量相符','short':'累计尚未收齐，可为正常分批；没有业务截止定义，不认定短缺违规','over':'累计记录超收，需核实凭证与单位'}
   observations.append(signal('receipt_quantity',(po.id,lid) if not state['issues'] else ('invalid_line',po.id,index),'normal' if known and q=='matched' else 'info' if known and q=='short' else 'attention' if known else 'unavailable',msg[q] if known else '历史基数/稳定行/有效事件依据不足，不猜算收货差异',{'comparison':'R3有效累计与订购数量；无强制截止日'},'本月有效采购稳定行，历史不明单列','R3 receipt_state',[evidence(po,{'line_ref':lid} if known else None)],quantity={k:item.get(k) for k in ['quantity','received_quantity','diff_quantity','over_quantity','quantity_status']},issues=state['issues']))
 observations.sort(key=lambda r:(r['rule'],r['id']))
 assert len({r['id'] for r in observations})==len(observations)
 for g in aggregate.values():g['amount']=prices.amount(g['amount'])
 return {'month':month,'warehouse_id':wid,'version':VERSION,'notice':NOTICE,'date_basis':prices.DATE_NOTE,'policy':policy,'inventory':{'state':'unavailable','message':'第11轮待接入；未伪造库存或用量信号'},'orders':{'included':len(orders),'excluded':sum(1 for p in all_orders if p.created_at and start<=dt(p.created_at)<end and matches(p) and p not in orders),'totals_by_currency':{c:prices.amount(v) for c,v in totals.items()}},'by_orderer_supplier':list(aggregate.values()),'_order_facts':[{**evidence(p),'supplier_name':suppliers[p.supplier_id].name} for p in orders],'observations':observations}

async def calculate(db,wid,**filters):
 with localcontext() as ctx:
  ctx.prec=64
  return await _calculate(db,wid,**filters)

def filtered_report(result,rule=None,state=None):
 rows=[r for r in result['observations'] if (not rule or r['rule']==rule) and (not state or r['state']==state)]
 coverage={}
 for key in RULES:
  group=[r for r in rows if r['rule']==key];known=sum(r['state']!='unavailable' for r in group)
  coverage[key]={'label':RULES[key],'denominator':len(group),'known':known,'percent':prices.amount(Decimal(known)*100/len(group)) if group else None,'attention':sum(r['state']=='attention' for r in group),'info':sum(r['state']=='info' for r in group),'unavailable':len(group)-known}
 output={**{k:v for k,v in result.items() if k not in ('observations','_order_facts')},'summary':coverage,'total':len(rows),'data':rows}
 if rule or state:
  ids={e['order_id'] for r in rows for e in r['evidence']};facts=[p for p in result['_order_facts'] if p['order_id'] in ids];totals={};groups={}
  for p in facts:
   cur=p['currency'];value=dec(p['amount']);totals[cur]=totals.get(cur,Decimal(0))+value
   key=(p['orderer_id'],p['supplier_id'],cur);g=groups.setdefault(key,{'orderer_id':p['orderer_id'],'supplier_id':p['supplier_id'],'supplier_name':p['supplier_name'],'currency':cur,'order_count':0,'amount':Decimal(0),'order_ids':[]});g['order_count']+=1;g['amount']+=value;g['order_ids'].append(p['order_id'])
  for g in groups.values():g['amount']=prices.amount(g['amount'])
  output['orders']={**result['orders'],'included':len(facts),'totals_by_currency':{c:prices.amount(v) for c,v in totals.items()},'scope':'筛选线索引用的本月有效采购去重；跨月窗口外月证据不计本月金额；排除数为基础日期/人员/供应商/币种范围'}
  output['by_orderer_supplier']=list(groups.values())
 return output

def export(result):
 import json
 out=io.StringIO(newline='');w=csv.writer(out);w.writerow(['月份','线索ID','规则','版本','状态','说明','门槛','分母','时间口径','证据来源','采购编号列表','币种列表','相对历史差额(参考)','相对最低差额(参考)','原因/备注','证据明细(采购金额不可跨线索相加)'])
 for r in result['data']:
  p=r['detail'].get('price') or {}
  vals=[result['month'],r['id'],r['label'],r['version'],r['state'],r['explanation'],json.dumps(r['threshold'],ensure_ascii=False),json.dumps(r['denominator'],ensure_ascii=False),r['time_basis'],r['source'],json.dumps([e['order_id'] for e in r['evidence']]),json.dumps(sorted({e['currency'] for e in r['evidence']})),p.get('historical_difference'),p.get('lowest_difference'),p.get('reason') or '；'.join(e.get('remark','') for e in r['evidence']),json.dumps(r['evidence'],ensure_ascii=False)]
  w.writerow([prices.cell(v,i in (12,13)) for i,v in enumerate(vals)])
 return ('\ufeff'+out.getvalue()).encode()
