"""Same-SKU, same-terms quotations. Unknown facts never become zero or a recommendation."""
from datetime import date
from decimal import Decimal,InvalidOperation,localcontext,ROUND_HALF_UP
from fastapi import HTTPException
from sqlalchemy import select
from app.models import SupplierQuote,SupplierQuoteRevision,SupplierQuoteTier,SupplierProduct,Supplier,StandardSKU
from app.services import sku_catalog as catalog
from app.services.supplier_quote_migration import ensure_quote_guards
from app.services.payable_creation import fingerprint
from app.services.data_history import record_history
from app.core.timezone import thai_now,thai_today

QUANTUM=Decimal('0.00000001')
def number(value,label,*,optional=False,zero=False,limit=Decimal('1000000000')):
 if optional and value in (None,''):return None
 if isinstance(value,bool):raise HTTPException(400,label+'必须是数字')
 try:d=Decimal(str(value).strip())
 except (InvalidOperation,ValueError):raise HTTPException(400,label+'必须是有效数字')
 if not d.is_finite() or d<0 or not zero and d==0 or d>limit or d.quantize(QUANTUM)!=d:raise HTTPException(400,label+f'须为有效正数，最多8位小数且不超过{limit}')
 return d

def exact(value):
 if value is None:return None
 v=format(Decimal(value),'f');return v.rstrip('0').rstrip('.') if '.' in v else v

def rounded(value):return value.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)

def labels(values,label):
 if values is None:return None
 if not isinstance(values,list) or len(values)>30:raise HTTPException(400,label+'须为最多30项的列表')
 result=[catalog.label(v,label,100) for v in values]
 if len(set(result))!=len(result):raise HTTPException(400,label+'不能重复')
 return sorted(result)

def fees(data):
 if not isinstance(data,dict):raise HTTPException(400,'请明确税费、运费和其他费用口径')
 if set(data)-{'tax_mode','tax_rate','freight_mode','freight_terms','other_fees'}:raise HTTPException(400,'费用口径包含未知字段')
 tax=data.get('tax_mode','unknown');freight=data.get('freight_mode','unknown')
 if tax not in ('included','excluded','unknown') or freight not in ('included','excluded','unknown'):raise HTTPException(400,'税费和运费请选择含、未含或待确认')
 rate=number(data.get('tax_rate'),'税率',optional=True,zero=True)
 if rate is not None and rate>100:raise HTTPException(400,'税率不能超过100%')
 note=data.get('freight_terms') or '';other=data.get('other_fees') or 'unknown'
 if not isinstance(note,str) or len(note)>300 or not isinstance(other,str) or len(other)>300:raise HTTPException(400,'费用说明最多300字')
 return {'tax_mode':tax,'tax_rate':exact(rate),'freight_mode':freight,'freight_terms':note.strip(),'other_fees':other.strip() or 'unknown'}

def known_fees(value):
 return (value['tax_mode']!='unknown' and value['freight_mode']!='unknown' and value['other_fees']!='unknown'
  and (value['tax_mode']!='excluded' or value['tax_rate'] is not None)
  and (value['freight_mode']!='excluded' or bool(value['freight_terms'])))

def tiers(values):
 if not isinstance(values,list) or not values or len(values)>50:raise HTTPException(400,'请填写1至50个数量档位')
 rows=[]
 for value in values:
  if not isinstance(value,dict) or set(value)!={'min_quantity','max_quantity','unit_price'}:raise HTTPException(400,'档位字段必须为最小数量、最大数量和单价')
  lo=number(value['min_quantity'],'档位起点');hi=number(value['max_quantity'],'档位终点',optional=True);price=number(value['unit_price'],'报价单价')
  if hi is not None and hi<=lo:raise HTTPException(400,'档位终点必须大于起点；起点包含、终点不包含')
  rows.append({'min_quantity':exact(lo),'max_quantity':exact(hi),'unit_price':exact(price)})
 rows.sort(key=lambda v:Decimal(v['min_quantity']))
 for previous,current in zip(rows,rows[1:]):
  if previous['max_quantity'] is None or Decimal(previous['max_quantity'])>Decimal(current['min_quantity']):raise HTTPException(400,'数量档位重叠，未保存报价')
 return rows

def requirements(data):
 data=data or {}
 if not isinstance(data,dict) or set(data)-{'quality_tags','max_lead_days'}:raise HTTPException(400,'采购需求包含未知字段')
 days=data.get('max_lead_days')
 if days is not None and (type(days) is not int or not 0<=days<=3650):raise HTTPException(400,'最大交期须为0至3650的整数天')
 return {'quality_tags':labels(data.get('quality_tags') or [],'质量要求'),'max_lead_days':days}

async def lock(db,wid):
 await catalog.lock(db,wid);await ensure_quote_guards(await db.connection())

async def fresh(db,model,ident):
 return (await db.execute(select(model).where(model.id==ident).execution_options(populate_existing=True))).scalar_one_or_none()

async def revision_data(db,quote,revision=None):
 revision=revision or (await db.execute(select(SupplierQuoteRevision).where(SupplierQuoteRevision.quote_id==quote.id,SupplierQuoteRevision.revision==quote.current_revision))).scalar_one_or_none()
 if revision is None or revision.warehouse_id!=quote.warehouse_id:raise HTTPException(503,'报价当前版本关系异常，请管理员核对')
 rows=(await db.execute(select(SupplierQuoteTier).where(SupplierQuoteTier.revision_id==revision.id).order_by(SupplierQuoteTier.min_quantity))).scalars()
 actual=[{k:exact(getattr(v,k)) for k in ('min_quantity','max_quantity','unit_price')} for v in rows]
 if actual!=revision.terms.get('tiers') or fingerprint({'terms':revision.terms,'binding':revision.product_binding})!=revision.content_fingerprint:raise HTTPException(503,'报价版本内容与档位证据不一致，已停止使用')
 return {'id':quote.id,'code':quote.code,'warehouse_id':quote.warehouse_id,'product_id':quote.product_id,'revision_id':revision.id,'revision':revision.revision,
  'version':fingerprint({'id':quote.id,'revision_id':revision.id,'content':revision.content_fingerprint}),
  'terms':revision.terms,'product_binding':revision.product_binding,'operator_name':revision.operator_name,'created_at':revision.created_at.isoformat() if revision.created_at else None}

async def owned_quote(db,wid,qid):
 row=await fresh(db,SupplierQuote,qid)
 if row is None or row.warehouse_id!=wid:raise HTTPException(404,'当前仓库未找到该报价')
 await catalog.product_owned(db,row.product_id,wid)
 return row

async def save(db,wid,user,pid,data,qid=None):
 await lock(db,wid);key=catalog.label(data.get('request_key'),'报价请求编号',100)
 signature=fingerprint({'operation':'create' if qid is None else 'revise','quote_id':qid,'product_id':pid,'body':{k:v for k,v in data.items() if k!='request_key'}})
 previous=(await db.execute(select(SupplierQuoteRevision).where(SupplierQuoteRevision.warehouse_id==wid,SupplierQuoteRevision.request_key==key))).scalar_one_or_none()
 if previous:
  if previous.request_fingerprint!=signature:raise HTTPException(409,'该报价请求已保存但内容不同，请核对原版本，未覆盖或重复新增')
  quote=await owned_quote(db,wid,previous.quote_id);return {**await revision_data(db,quote,previous),'replayed':True}
 product=await catalog.product_owned(db,pid,wid,for_update=True)
 await db.refresh(product)
 if product.catalog_active is False:raise HTTPException(400,'产品已停用，不能登记新报价')
 if data.get('expected_product_version')!=catalog.product_version(product):raise HTTPException(409,'产品或映射已改变，请刷新核对后登记报价')
 mapping=await catalog.mapping_view(db,product,wid)
 if mapping['mapping_status'] in ('unmapped','stale'):raise HTTPException(409,'请先人工映射有效标准SKU，再登记阶梯报价')
 sku=await fresh(db,StandardSKU,product.standard_sku_id);sku_value=catalog.sku_data(sku)
 if data.get('expected_sku_version')!=sku_value['version']:raise HTTPException(409,'标准SKU已变化，请重新核对')
 currency=data.get('currency')
 if currency not in ('THB','CNY') or currency!=product.currency:raise HTTPException(400,'报价币种须与原产品已明确的币种一致，不自动换汇')
 unit=catalog.unit(data.get('unit'))
 if unit!=catalog.unit(product.unit,False):raise HTTPException(400,'报价单位须与原产品单位一致；不同原单位请单独登记产品，不能猜换算')
 factor=number(data.get('base_unit_factor'),'基本单位换算数',optional=True);basis=(data.get('conversion_basis') or '').strip()
 if len(basis)>1000:raise HTTPException(400,'换算依据最多1000字')
 if unit==sku.base_unit:
  if factor not in (None,Decimal(1)):raise HTTPException(400,'相同基本单位换算必须为1')
  factor=Decimal(1);basis=basis or '原报价单位与基本单位相同，恒等换算1'
 elif factor is not None and not basis:raise HTTPException(400,'不同单位填写换算数时必须填写人工核实依据')
 if factor is not None and product.base_unit_factor is not None and factor!=product.base_unit_factor:raise HTTPException(400,'报价换算数与产品已核实的换算不一致，请先核对映射')
 try:start=date.fromisoformat(data['valid_from']);end=date.fromisoformat(data['valid_to'])
 except (ValueError,TypeError,KeyError):raise HTTPException(400,'请填写明确的报价有效起止日期')
 if end<start:raise HTTPException(400,'报价有效期结束不能早于开始')
 days=data.get('lead_days')
 if days is not None and (type(days) is not int or not 0<=days<=3650):raise HTTPException(400,'交期须为0至3650的整数天，未知留空')
 body={'currency':currency,'unit':unit,'original_unit':product.unit,'base_unit':sku.base_unit,'base_unit_factor':exact(factor),'conversion_basis':basis,
  'valid_from':start.isoformat(),'valid_to':end.isoformat(),'fees':fees(data.get('fees') or {}),'quality_tags':labels(data.get('quality_tags'),'报价质量标签'),
  'lead_days':days,'active':bool(data.get('active',True)),'tiers':tiers(data.get('tiers'))}
 binding={'product_version':catalog.product_version(product),'sku_id':sku.id,'sku_version':sku_value['version'],'sku_mapping':mapping,'supplier_id':product.supplier_id}
 if qid is None:
  code=catalog.code(data.get('code'));existing=(await db.execute(select(SupplierQuote.id).where(SupplierQuote.warehouse_id==wid,SupplierQuote.code==code))).first()
  if existing:raise HTTPException(409,'本仓报价编码已存在，请编辑原报价生成新版本，不覆盖')
  quote=SupplierQuote(warehouse_id=wid,product_id=pid,code=code,current_revision=1);db.add(quote);await db.flush();before=None
 else:
  quote=await owned_quote(db,wid,qid)
  if quote.product_id!=pid:raise HTTPException(400,'不能把原报价转移到其他产品')
  before=await revision_data(db,quote)
  if data.get('code')!=quote.code or data.get('expected_quote_version')!=before['version']:raise HTTPException(409,'报价已被修改或编码不一致，请刷新；未覆盖他人版本')
  quote.current_revision+=1
 rev=SupplierQuoteRevision(warehouse_id=wid,quote_id=quote.id,revision=quote.current_revision,request_key=key,request_fingerprint=signature,
  terms=body,product_binding=binding,content_fingerprint=fingerprint({'terms':body,'binding':binding}),operator_id=user.id,operator_name=user.display_name or user.username)
 db.add(rev);await db.flush()
 db.add_all([SupplierQuoteTier(revision_id=rev.id,**{k:Decimal(v) if v is not None else None for k,v in row.items()}) for row in body['tiers']]);await db.flush()
 result=await revision_data(db,quote,rev)
 await record_history(db,module='suppliers',record_id=quote.id,operation_type='quote_create' if before is None else 'quote_revision',operator=user,before=before,after=result,warehouse_id=wid)
 return result

async def source_context(db,wid,product):
 supplier=await fresh(db,Supplier,product.supplier_id)
 if not supplier or supplier.warehouse_id!=wid:raise HTTPException(404,'当前仓库未找到报价供应商')
 mapping=await catalog.mapping_view(db,product,wid)
 sku=await fresh(db,StandardSKU,product.standard_sku_id) if product.standard_sku_id else None
 return supplier,mapping,catalog.sku_data(sku) if sku else None

def match_tier(terms,quantity):
 return next((t for t in terms['tiers'] if quantity>=Decimal(t['min_quantity']) and (t['max_quantity'] is None or quantity<Decimal(t['max_quantity']))),None)

async def candidate(db,wid,quote,demand,reference,needed,today):
 value=await revision_data(db,quote);terms=value['terms'];binding=value['product_binding'];p=await catalog.product_owned(db,quote.product_id,wid)
 supplier,mapping,sku=await source_context(db,wid,p);reasons=[]
 if supplier.is_active!='true':reasons.append('供应商已停用')
 if p.catalog_active is False:reasons.append('产品已停用')
 if not terms['active']:reasons.append('报价已停用')
 if today<date.fromisoformat(terms['valid_from']):reasons.append('报价尚未生效')
 if today>date.fromisoformat(terms['valid_to']):reasons.append('报价已过期')
 if not sku or not sku['active']:reasons.append('标准SKU不存在或已停用')
 if mapping['mapping_status'] in ('unmapped','stale') or catalog.product_version(p)!=binding['product_version'] or not sku or sku['version']!=binding['sku_version']:reasons.append('产品或SKU映射已变更，报价需重新核对')
 if binding['sku_id']!=reference['sku_id']:reasons.append('不是本次同一标准SKU')
 if terms['currency']!=reference['currency']:reasons.append('币种不同，不换汇比较')
 if not known_fees(terms['fees']):reasons.append('税费、运费或其他费用口径待确认')
 elif terms['fees']!=reference['fees']:reasons.append('税费或运费等费用口径不同')
 if needed['quality_tags'] and (terms['quality_tags'] is None or not set(needed['quality_tags'])<=set(terms['quality_tags'])):reasons.append('质量要求未满足或未知')
 if needed['max_lead_days'] is not None and (terms['lead_days'] is None or terms['lead_days']>needed['max_lead_days']):reasons.append('交期要求未满足或未知')
 factor=Decimal(terms['base_unit_factor']) if terms['base_unit_factor'] is not None else None;quantity=None;tier=None;price=None
 if factor is None:reasons.append('基本单位换算未知')
 elif demand is None:reasons.append('本次需求基本数量未知')
 else:
  with localcontext() as ctx:
   ctx.prec=48;quantity=demand/factor
   if quantity!=quantity.to_integral_value():reasons.append('折算为小数原单位，当前采购仅支持整单位，不能自动取整')
   tier=match_tier(terms,quantity)
   if tier is None:reasons.append('本次数量不满足报价档位')
   else:price=Decimal(tier['unit_price'])/factor
 return {**value,'supplier_id':supplier.id,'supplier_name':supplier.name,'product_name':p.product_name,'quantity':exact(quantity),'tier':tier,
  'comparable_price':exact(price),'eligible':not reasons,'exclusions':reasons,'is_lowest':False}

async def line_preview(db,wid,p,quantity,qid,needed,today,all_quotes):
 supplier,mapping,sku=await source_context(db,wid,p)
 if supplier.is_active!='true' or p.catalog_active is False:raise HTTPException(400,'供应商或产品已停用，不能新增采购')
 result={'product_id':p.id,'product_name':p.product_name,'quantity':exact(quantity),'unit':p.unit,'currency':p.currency or 'THB','requirements':needed,'selected_quote':None,
  'eligible_candidates':[],'excluded_candidates':[],'lowest':[],'lowest_comparable_price':None,'non_lowest':False,'requires_reason':False,'reason':None}
 if qid is None:
  blockers=[]
  if needed['quality_tags'] or needed['max_lead_days'] is not None:blockers.append('历史单价缺明确质量或交期声明，无法确认满足本次需求')
  if quantity!=quantity.to_integral_value():blockers.append('实际采购只支持整数原单位，不自动截断小数')
  price=number(p.unit_price,'原产品单价');result.update({'mode':'legacy','unit_price':exact(price),'subtotal':exact(rounded(price*quantity)),'blockers':blockers,
   'message':'历史单价采购；缺明确有效报价或费用条件，无有效可比推荐，不按同名猜配','effective_date':today.isoformat()});return result
 quote=await owned_quote(db,wid,qid)
 if quote.product_id!=p.id:raise HTTPException(400,'所选报价不属于本次供应商产品')
 selected=await revision_data(db,quote);terms=selected['terms'];factor=Decimal(terms['base_unit_factor']) if terms['base_unit_factor'] is not None else None
 with localcontext() as ctx:
  ctx.prec=48;demand=quantity*factor if factor is not None else None
 reference={'sku_id':p.standard_sku_id,'currency':terms['currency'],'fees':terms['fees']}
 values=[await candidate(db,wid,q,demand,reference,needed,today) for q in all_quotes]
 own=next(v for v in values if v['id']==qid);tier=match_tier(terms,quantity)
 own={**own,'tier':tier,'quantity':exact(quantity)}
 # Unknown fees/conversion prohibit recommendations, not the legacy ability to buy an explicitly priced valid quote.
 blockers=[s for s in own['exclusions'] if s not in ('税费、运费或其他费用口径待确认','基本单位换算未知','本次需求基本数量未知')]
 if not tier and '本次数量不满足报价档位' not in blockers:blockers.append('本次数量不满足报价档位')
 if quantity!=quantity.to_integral_value():blockers.append('实际采购只支持整数原单位，不自动截断小数')
 eligible=[v for v in values if v['eligible']] if known_fees(terms['fees']) and demand is not None and not blockers else []
 lowest=min((Decimal(v['comparable_price']) for v in eligible),default=None)
 for v in eligible:v['is_lowest']=Decimal(v['comparable_price'])==lowest
 own['is_lowest']=any(v['id']==qid and v['is_lowest'] for v in eligible)
 price=Decimal(tier['unit_price']) if tier else None
 result.update({'mode':'quote','selected_quote':own,'base_quantity':exact(demand),'unit_price':exact(price),'subtotal':exact(rounded(price*quantity)) if price is not None else None,
  'eligible_candidates':eligible,'excluded_candidates':[v for v in values if not v['eligible']],
  'lowest':[v['id'] for v in eligible if v['is_lowest']],'lowest_comparable_price':exact(lowest),'non_lowest':bool(lowest is not None and own['comparable_price'] is not None and Decimal(own['comparable_price'])>lowest),
  'blockers':blockers,'message':'同SKU、同币种、同明确费用口径，按本次数量的基本单位单价比较；不自动替换供应商' if lowest is not None else '无有效可比报价；未知条件未当成0或1',
  'effective_date':today.isoformat(),'comparison_reference':reference})
 result['requires_reason']=result['non_lowest'];return result

async def cart_preview(db,wid,supplier_id,items,needed=None):
 await lock(db,wid);needed=requirements(needed);today=thai_today();rows=[]
 supplier=await fresh(db,Supplier,supplier_id)
 if not supplier or supplier.warehouse_id!=wid:raise HTTPException(404,'当前仓库未找到该供应商')
 quotes=(await db.execute(select(SupplierQuote).where(SupplierQuote.warehouse_id==wid).order_by(SupplierQuote.id))).scalars().all()
 if not items or len(items)>100:raise HTTPException(400,'请选择1至100项产品')
 for index,item in enumerate(items,1):
  pid=item.get('product_id')
  if type(pid) is not int:raise HTTPException(400,'产品编号无效')
  p=await catalog.product_owned(db,pid,wid)
  await db.refresh(p)
  if p.supplier_id!=supplier_id:raise HTTPException(400,'产品不属于所选供应商')
  quantity=number(item.get('quantity'),'采购数量',limit=Decimal(2147483647));qid=item.get('quote_id')
  if qid is not None and type(qid) is not int:raise HTTPException(400,'报价编号必须为整数')
  row=await line_preview(db,wid,p,quantity,qid,needed,today,quotes);row['input_line']=index;rows.append(row)
 currencies={r['currency'] for r in rows}
 if len(currencies)!=1:raise HTTPException(400,'不同币种不能在同一采购单，不换汇')
 body={'warehouse_id':wid,'supplier_id':supplier_id,'currency':next(iter(currencies)),'effective_date':today.isoformat(),'requirements':needed,'rows':rows,
  'amount_basis':'quoted_goods_only','amount_note':'采购及应付按所选报价商品价登记，不自动另加税或运费；未含费用须按明确条款另外核定，不代表落地总成本。',
  'total':exact(sum((Decimal(v['subtotal']) for v in rows if v['subtotal'] is not None),Decimal(0))),
  'can_order':all(v['subtotal'] is not None and not v.get('blockers') and Decimal(v['quantity'])==Decimal(v['quantity']).to_integral_value() for v in rows)}
 # Reasons are supplied separately and never change the comparable candidate set or stale-preview identity.
 return {**body,'version':fingerprint(body),'evaluated_at':thai_now().isoformat()}
