"""Disposable localhost only: actual quote HTTP, Decimal tiers, immutable purchase evidence."""
import asyncio,json,uuid,os
from datetime import date
from pathlib import Path
from contextlib import asynccontextmanager
from decimal import Decimal
import pytest
from sqlalchemy import select,func,text
from app.models import SupplierQuote,SupplierQuoteRevision,SupplierQuoteTier,PurchaseOrder,PayableBill,SupplierProduct,ProcurementNonLowestRecord,ProcurementPriceHistory,SystemSetting,StandardSKU
from app.services import supplier_quotes as quotes
from tests.test_supplier_sku_round5 import fixture as round5_fixture,sku,product,map_it,ATTRS
from tests.test_supplier_workflow_round1 import request
from tests.test_incoming_operations import URL
from tests.test_round2_permissions import auth,png
pytestmark=pytest.mark.skipif(not URL,reason='Explicit disposable localhost database required')
FEES={'tax_mode':'included','tax_rate':None,'freight_mode':'included','freight_terms':'','other_fees':'none'}
ACTUAL={}
def actual(k,v):
 ACTUAL[k]=v
 if os.environ.get('SUPPLIER06_REPORT'):Path(os.environ['SUPPLIER06_REPORT']).write_text(json.dumps(ACTUAL,ensure_ascii=False,default=str,indent=2))
@asynccontextmanager
async def fixture(tmp_path,mp):
 async with round5_fixture(tmp_path,mp) as value:
  mp.setattr(quotes,'thai_today',lambda:date(2026,10,26));yield value

async def quoted(c,pid,s,**patch):
 info=await request(c,'GET',f'/sku-catalog/products/{pid}/candidates')
 body={'code':'Q-'+uuid.uuid4().hex[:10].upper(),'request_key':uuid.uuid4().hex,'expected_product_version':info['product_version'],'expected_sku_version':s['version'],
  'currency':'THB','unit':'个','base_unit_factor':'1','valid_from':'2026-10-01','valid_to':'2026-10-31','fees':FEES,'quality_tags':['A级'],'lead_days':2,
  'tiers':[{'min_quantity':'1','max_quantity':None,'unit_price':'10'}],**patch}
 return await request(c,'POST',f'/supplier-quotes/products/{pid}',json=body),body

async def pair(c):
 s=await sku(c);p=await product(c,product_name='供应商甲叫法');await map_it(c,p['id'],s)
 b=await request(c,'POST','/suppliers/3/products',json={'product_name':'供应商乙另一名称','spec':'同结构不同名称','unit_price':9,'unit':'个','currency':'THB','catalog_attributes':ATTRS});await map_it(c,b['id'],s)
 qa,body=await quoted(c,p['id'],s,tiers=[{'min_quantity':'1','max_quantity':'10','unit_price':'10'},{'min_quantity':'10','max_quantity':None,'unit_price':'8'}])
 qb,other=await quoted(c,b['id'],s,tiers=[{'min_quantity':'1','max_quantity':None,'unit_price':'9'}])
 return s,p,b,qa,qb,body,other

async def preview(c,pid,qid,qty=5,**patch):return await request(c,'POST','/supplier-quotes/purchase-preview',json={'supplier_id':1,'items':[{'product_id':pid,'quote_id':qid,'quantity':qty}],**patch})

def test_quantity_selects_tier_same_sku_different_names_nonlowest_reason_and_snapshot(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
   s,p,b,qa,qb,body,other=await pair(c)
   small=await preview(c,p['id'],qa['id'],5);large=await preview(c,p['id'],qa['id'],10)
   assert small['rows'][0]['lowest']==[qb['id']] and small['rows'][0]['non_lowest'] and small['total']=='50'
   assert large['rows'][0]['lowest']==[qa['id']] and large['rows'][0]['unit_price']=='8' and large['total']=='80'
   assert large['rows'][0]['selected_quote']['is_lowest'] and not small['rows'][0]['selected_quote']['is_lowest']
   req={'request_key':'quoted-order','pricing_version':small['version'],'items':[{'product_id':p['id'],'quote_id':qa['id'],'quantity':5}]}
   denied=await request(c,'POST','/suppliers/1/purchase-order',json=req);assert denied['need_reason']
   req['items'][0]['reason']='选甲因质量记录更完整';po=await request(c,'POST','/suppliers/1/purchase-order',json=req)
   line=po['order']['items'][0];assert line['unit_price']=='10' and line['quantity']==5 and line['line_id'] and line['unit']=='个' and line['pricing_snapshot']['lowest']==[qb['id']]
   repeated=await request(c,'POST','/suppliers/1/purchase-order',json=req);assert repeated['replayed'] and repeated['order']['id']==po['order']['id']
   async with f() as db:
    original=(await db.get(PurchaseOrder,po['order']['id'])).items
    record=(await db.execute(select(ProcurementNonLowestRecord))).scalar_one();assert record.reason==req['items'][0]['reason'] and record.price_diff==1
    assert (await db.get(PurchaseOrder,1)).items==[{'product_name':'耗材','quantity':10}]
   changed=await request(c,'PUT',f'/supplier-quotes/{qb["id"]}',json={**other,'request_key':'change-qb','expected_quote_version':qb['version'],'tiers':[{'min_quantity':'1','max_quantity':None,'unit_price':'1'}]})
   async with f() as db:assert (await db.get(PurchaseOrder,po['order']['id'])).items==original
   oldreq=await request(c,'POST','/suppliers/1/purchase-order',json=req);assert oldreq['order']['items']==original
   await request(c,'POST','/suppliers/1/purchase-order',code=409,json={**req,'request_key':'stale-new'})
   actual('quantity_reason_snapshot',{'small':small,'large':large,'order':po,'retry':repeated,'changed_quote':changed,'old_order_unchanged':True})
 asyncio.run(run())

def test_tier_overlap_dates_unknown_terms_and_independent_permissions(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
   s=await sku(c);p=await product(c);await map_it(c,p['id'],s);q,body=await quoted(c,p['id'],s)
   for uid in (2,3,5,8,9,10):await request(c,'POST',f'/supplier-quotes/products/{p["id"]}',uid=uid,code=403,json={**body,'request_key':uuid.uuid4().hex,'code':'NO-'+str(uid)})
   for uid in (1,3,4):await request(c,'GET','/supplier-quotes/suppliers/1',uid=uid)
   for uid in (2,5,8,9,10):await request(c,'GET','/supplier-quotes/suppliers/1',uid=uid,code=403)
   await request(c,'GET',f'/supplier-quotes/{q["id"]}/revisions',uid=7,warehouse='2',code=404)
   bads=[{'valid_to':'2026-09-01'},{'tiers':[{'min_quantity':'1','max_quantity':'5','unit_price':'2'},{'min_quantity':'4.99','max_quantity':None,'unit_price':'1'}]},
    {'tiers':[{'min_quantity':'0','max_quantity':None,'unit_price':'1'}]}, {'tiers':[{'min_quantity':'1','max_quantity':None,'unit_price':'-1'}]}, {'base_unit_factor':'2'}]
   for patch in bads:await request(c,'POST',f'/supplier-quotes/products/{p["id"]}',code=400,json={**body,'code':'INVALID','request_key':uuid.uuid4().hex,**patch})
   unknown,_=await quoted(c,p['id'],s,fees={'tax_mode':'unknown','freight_mode':'unknown'})
   v=await preview(c,p['id'],unknown['id']);assert v['rows'][0]['lowest']==[] and v['rows'][0]['lowest_comparable_price'] is None and v['can_order']
   actual('validation_permissions',{'bad_terms':400,'write_denied':[2,3,5,8,9,10],'cross_warehouse':404,'unknown_terms':v})
 asyncio.run(run())

def test_real_quote_order_receipt_payable_payment_keeps_line_identity(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
   s=await sku(c);p=await product(c);await map_it(c,p['id'],s);q,_=await quoted(c,p['id'],s,tiers=[{'min_quantity':'1','max_quantity':None,'unit_price':'12.34'}])
   v=await preview(c,p['id'],q['id'],2);order=await request(c,'POST','/suppliers/1/purchase-order',json={'request_key':'whole-chain','pricing_version':v['version'],'items':[{'product_id':p['id'],'quote_id':q['id'],'quantity':2}]})
   oid=order['order']['id'];bid=order['payable_bill_id'];line=order['order']['items'][0]
   received=await request(c,'POST',f'/suppliers/purchase-orders/{oid}/receive',data={'request_key':'receive-quoted','items':json.dumps([{'line_id':line['line_id'],'received_quantity':2}])},files={'file':('proof.png',png(),'image/png')})
   paid=await request(c,'PUT',f'/payable/{bid}/pay',params={'paid_amount':24.68,'account_id':1,'payment_method':'现金','request_key':'pay-quoted'})
   async with f() as db:assert (await db.get(PurchaseOrder,oid)).items[0]['pricing_snapshot']==line['pricing_snapshot']
   actual('quote_procurement_chain',{'line':line,'received':received,'paid':paid})
 asyncio.run(run())

@pytest.mark.parametrize('quantity,price,orderable',[('1','10',True),('9.99999999','10',False),('10','8',True),('10.00000001','8',False),('0.99999999',None,False),('99','8',True),('100',None,False)])
def test_tier_exact_decimal_boundaries_no_rounding_to_an_order(tmp_path,monkeypatch,quantity,price,orderable):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
   s=await sku(c);p=await product(c);await map_it(c,p['id'],s)
   q,_=await quoted(c,p['id'],s,tiers=[{'min_quantity':'1','max_quantity':'10','unit_price':'10'},{'min_quantity':'10','max_quantity':'100','unit_price':'8'}])
   result=await preview(c,p['id'],q['id'],quantity)
   assert result['rows'][0]['unit_price']==price and result['can_order'] is orderable
   assert result['rows'][0]['quantity']==quantity
   if not orderable:assert result['rows'][0]['lowest_comparable_price'] is None
   actual('boundary_'+quantity,result)
 asyncio.run(run())

def test_validity_includes_both_dates_and_does_not_reuse_yesterday_preview(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
   s=await sku(c);p=await product(c);await map_it(c,p['id'],s);q,_=await quoted(c,p['id'],s)
   results=[]
   for value,expected in [(date(2026,9,30),False),(date(2026,10,1),True),(date(2026,10,31),True),(date(2026,11,1),False)]:
    monkeypatch.setattr(quotes,'thai_today',lambda v=value:v);r=await preview(c,p['id'],q['id'],1);assert r['can_order'] is expected;results.append(r)
   denied=await request(c,'POST','/suppliers/1/purchase-order',code=409,json={'request_key':'yesterday-preview','pricing_version':results[2]['version'],'items':[{'product_id':p['id'],'quote_id':q['id'],'quantity':1}]})
   assert denied['detail']['not_created'] is True and denied['detail']['request_key']=='yesterday-preview'
   actual('validity',{'days':results,'stale':denied})
 asyncio.run(run())

def test_unit_conversion_ties_different_sku_currency_fees_and_unknown_exclusions(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
   s,p,b,qa,qb,body,other=await pair(c)
   box=await product(c,product_name='十只一箱',unit='箱');await map_it(c,box['id'],s)
   converted,_=await quoted(c,box['id'],s,unit='箱',base_unit_factor='10',conversion_basis='合成凭据核实：每箱10只',tiers=[{'min_quantity':'1','max_quantity':None,'unit_price':'80'}])
   unknown,_=await quoted(c,box['id'],s,unit='箱',base_unit_factor=None,tiers=[{'min_quantity':'1','max_quantity':None,'unit_price':'0.01'}])
   same_name_sku=await sku(c,code='OTHER',name='供应商甲叫法');different=await product(c,product_name='供应商甲叫法');await map_it(c,different['id'],same_name_sku)
   wrong,_=await quoted(c,different['id'],same_name_sku,tiers=[{'min_quantity':'1','max_quantity':None,'unit_price':'0.01'}])
   cny=await product(c,product_name='人民币同SKU',currency='CNY');await map_it(c,cny['id'],s)
   foreign_currency,_=await quoted(c,cny['id'],s,currency='CNY',tiers=[{'min_quantity':'1','max_quantity':None,'unit_price':'0.01'}])
   mismatch,_=await quoted(c,b['id'],s,fees={**FEES,'tax_mode':'excluded','tax_rate':'7'},tiers=[{'min_quantity':'1','max_quantity':None,'unit_price':'0.01'}])
   r=await preview(c,p['id'],qa['id'],10);row=r['rows'][0];assert set(row['lowest'])=={qa['id'],converted['id']}
   excluded={v['id']:v['exclusions'] for v in row['excluded_candidates']}
   assert '基本单位换算未知' in excluded[unknown['id']] and '不是本次同一标准SKU' in excluded[wrong['id']]
   assert '币种不同，不换汇比较' in excluded[foreign_currency['id']] and '税费或运费等费用口径不同' in excluded[mismatch['id']]
   fractional=await preview(c,p['id'],qa['id'],15);v=next(v for v in fractional['rows'][0]['excluded_candidates'] if v['id']==converted['id'])
   assert v['quantity']=='1.5' and any('自动取整' in x for x in v['exclusions'])
   actual('conversion_ties_exclusions',{'ten_pieces':r,'fifteen_pieces':fractional})
 asyncio.run(run())

def test_quality_lead_time_unknowns_are_not_satisfied_and_legacy_does_not_guess(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
   s,p,b,qa,qb,body,other=await pair(c)
   no_quality,_=await quoted(c,b['id'],s,quality_tags=None,lead_days=1,tiers=[{'min_quantity':'1','max_quantity':None,'unit_price':'0.01'}])
   no_lead,_=await quoted(c,b['id'],s,quality_tags=['A级'],lead_days=None,tiers=[{'min_quantity':'1','max_quantity':None,'unit_price':'0.01'}])
   bad_lead,_=await quoted(c,b['id'],s,quality_tags=['A级'],lead_days=7,tiers=[{'min_quantity':'1','max_quantity':None,'unit_price':'0.01'}])
   wanted={'quality_tags':['A级'],'max_lead_days':3};v=await preview(c,p['id'],qa['id'],10,requirements=wanted)
   assert v['rows'][0]['lowest']==[qa['id']]
   bad={x['id']:x['exclusions'] for x in v['rows'][0]['excluded_candidates']}
   assert '质量要求未满足或未知' in bad[no_quality['id']] and '交期要求未满足或未知' in bad[no_lead['id']] and '交期要求未满足或未知' in bad[bad_lead['id']]
   failed=await preview(c,p['id'],qa['id'],10,requirements={'quality_tags':['食品级'],'max_lead_days':1});assert not failed['can_order']
   legacy=await preview(c,1,None,2,requirements=wanted);assert not legacy['can_order'] and legacy['rows'][0]['lowest_comparable_price'] is None
   normal=await preview(c,1,None,2);assert normal['can_order'] and normal['rows'][0]['lowest_comparable_price'] is None
   actual('requirements_unknown',{'filtered':v,'selected_not_met':failed,'legacy_required':legacy,'legacy_compatible':normal})
 asyncio.run(run())

@pytest.mark.parametrize('state',['supplier','product','sku','mapping','quote'])
def test_disabled_or_stale_facts_are_excluded(tmp_path,monkeypatch,state):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
   s,p,b,qa,qb,body,other=await pair(c)
   if state=='supplier':await request(c,'PUT','/suppliers/3',json={'is_active':'false'})
   if state=='product':await request(c,'DELETE',f'/suppliers/3/products/{b["id"]}')
   if state=='quote':await request(c,'PUT',f'/supplier-quotes/{qb["id"]}',json={**other,'request_key':'disable-quote','expected_quote_version':qb['version'],'active':False})
   if state=='mapping':
    current=await request(c,'GET',f'/sku-catalog/products/{b["id"]}/candidates')
    await request(c,'POST',f'/sku-catalog/products/{b["id"]}/mapping',json={'sku_id':None,'expected_product_version':current['product_version'],'request_key':'unmap-for-test','reason':'合成核对取消旧映射'})
   if state=='sku':await request(c,'PUT',f'/sku-catalog/{s["id"]}',json={k:s[k] for k in ['code','name','attributes','base_unit','category_id']}|{'active':False,'expected_version':s['version']})
   v=await preview(c,p['id'],qa['id'],5);row=v['rows'][0]
   excluded=next(x for x in row['excluded_candidates'] if x['id']==qb['id']);assert excluded['exclusions']
   if state=='sku':assert not v['can_order'] and row['lowest_comparable_price'] is None
   else:assert row['lowest']==[qa['id']]
   actual('excluded_'+state,v)
 asyncio.run(run())

def test_concurrent_quote_edits_and_locked_edit_versus_order_preview(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
   s,p,b,qa,qb,body,other=await pair(c)
   def change(key,price):return {**body,'request_key':key,'expected_quote_version':qa['version'],'tiers':[{'min_quantity':'1','max_quantity':None,'unit_price':price}]}
   responses=await asyncio.gather(c.put(f'/api/v1/supplier-quotes/{qa["id"]}',headers=auth(1),json=change('race-one','7')),c.put(f'/api/v1/supplier-quotes/{qa["id"]}',headers=auth(1),json=change('race-two','6')))
   assert sorted(r.status_code for r in responses)==[200,409]
   current=next(r.json() for r in responses if r.status_code==200);view=await preview(c,p['id'],qa['id'],5)
   original=quotes.save;held=asyncio.Event();release=asyncio.Event()
   async def pause(db,wid,user,pid,data,qid=None):
    await quotes.lock(db,wid);held.set();await release.wait();return await original(db,wid,user,pid,data,qid)
   monkeypatch.setattr(quotes,'save',pause)
   editing=asyncio.create_task(c.put(f'/api/v1/supplier-quotes/{qa["id"]}',headers=auth(1),json={**body,'request_key':'locked-edit','expected_quote_version':current['version'],'tiers':[{'min_quantity':'1','max_quantity':None,'unit_price':'5'}]}))
   await asyncio.wait_for(held.wait(),5)
   buying=asyncio.create_task(c.post('/api/v1/suppliers/1/purchase-order',headers=auth(1),json={'request_key':'racing-order','pricing_version':view['version'],'items':[{'product_id':p['id'],'quote_id':qa['id'],'quantity':5}]}))
   await asyncio.sleep(.03);assert not buying.done();release.set();edited,denied=await asyncio.gather(editing,buying)
   assert edited.status_code==200 and denied.status_code==409 and denied.json()['detail']['not_created']
   async with f() as db:assert (await db.execute(select(func.count(PurchaseOrder.id)))).scalar_one()==1
   actual('concurrency',{'edit_codes':[r.status_code for r in responses],'locked_editor':edited.json(),'stale_order':denied.json(),'no_stale_purchase':True})
 asyncio.run(run())

def test_pending_order_approval_uses_original_baseline_and_concurrent_replay_is_one_bill(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
   s,p,b,qa,qb,body,other=await pair(c)
   async with f() as db:db.add(SystemSetting(warehouse_id=1,key='purchase_approval_threshold',value='1'));await db.commit()
   view=await preview(c,p['id'],qa['id'],5);req={'request_key':'pending-original','pricing_version':view['version'],'items':[{'product_id':p['id'],'quote_id':qa['id'],'quantity':5,'reason':'质量更稳定'}]}
   responses=await asyncio.gather(c.post('/api/v1/suppliers/1/purchase-order',headers=auth(1),json=req),c.post('/api/v1/suppliers/1/purchase-order',headers=auth(1),json=req))
   assert all(r.status_code==200 for r in responses);order=responses[0].json();assert responses[1].json()['order']['id']==order['order']['id'] and order['pending']
   await request(c,'PUT',f'/supplier-quotes/{qb["id"]}',json={**other,'request_key':'later-cheaper','expected_quote_version':qb['version'],'tiers':[{'min_quantity':'1','max_quantity':None,'unit_price':'1'}]})
   approved=await request(c,'PUT',f'/suppliers/purchase-approvals/{order["order"]["id"]}/approve')
   repeated=await request(c,'PUT',f'/suppliers/purchase-approvals/{order["order"]["id"]}/approve');assert repeated['replayed'] and repeated['payable_bill_id']==approved['payable_bill_id']
   async with f() as db:
    record=(await db.execute(select(ProcurementNonLowestRecord))).scalar_one();assert record.lowest_price==9 and record.price_diff==1
    po=await db.get(PurchaseOrder,order['order']['id']);assert po.items==order['order']['items']
    assert (await db.execute(select(func.count(PayableBill.id)))).scalar_one()==2
   actual('approval_frozen',{'order':order,'approved':approved,'repeat':repeated,'lowest_at_creation':9,'after_later_price':1,'recorded_diff':1})
 asyncio.run(run())

@pytest.mark.parametrize('old',[False,True])
def test_migration_new_old_repeat_unknown_history_and_fail_closed(tmp_path,monkeypatch,old):
 async def run():
  from app.services.supplier_quote_migration import migrate_supplier_quotes
  async with fixture(tmp_path,monkeypatch) as (engine,f,c,receipt):
   async with f() as db:
    db.add(ProcurementPriceHistory(warehouse_id=1,supplier_id=1,product_name='旧价',unit_price=7,quantity=1));await db.commit()
   if old:
    async with engine.begin() as conn:
     await conn.execute(text('ALTER TABLE procurement_price_history DROP COLUMN pricing_snapshot'))
     for table in ['supplier_quote_tiers','supplier_quote_revisions','supplier_quotes']:await conn.execute(text(f'DROP TABLE {table}'))
   async with engine.begin() as conn:await migrate_supplier_quotes(conn);await migrate_supplier_quotes(conn)
   async with f() as db:
    history=(await db.execute(select(ProcurementPriceHistory))).scalar_one();assert history.pricing_snapshot is None and history.unit_price==7
    assert (await db.execute(select(func.count(SupplierQuote.id)))).scalar_one()==0
   s=await sku(c);p=await product(c);await map_it(c,p['id'],s)
   async with engine.begin() as conn:
    await conn.execute(text('ALTER TABLE supplier_quote_tiers DROP CONSTRAINT ck_quote_tier_price'))
    await conn.execute(text('ALTER TABLE supplier_quote_tiers ADD CONSTRAINT ck_quote_tier_price CHECK (unit_price >= 0)'))
   info=await request(c,'GET',f'/sku-catalog/products/{p["id"]}/candidates')
   failed=await request(c,'POST',f'/supplier-quotes/products/{p["id"]}',code=503,json={'code':'NOT-READY','request_key':'guard','expected_product_version':info['product_version'],'expected_sku_version':s['version'],'currency':'THB','unit':'个','valid_from':'2026-10-01','valid_to':'2026-10-31','fees':FEES,'tiers':[{'min_quantity':'1','max_quantity':None,'unit_price':'1'}]})
   assert 'ck_quote_tier_price' in failed['detail']['missing']
   actual('migration_'+str(old),{'repeat_ready':True,'old_unknown_preserved':True,'wrong_check_same_name':failed})
 asyncio.run(run())

def test_forged_comparison_fields_multiwarehouse_member_and_quote_failure_rollback(tmp_path,monkeypatch):
 async def run():
  async with fixture(tmp_path,monkeypatch) as (_,f,c,receipt):
   s,p,b,qa,qb,body,other=await pair(c)
   await request(c,'POST','/supplier-quotes/purchase-preview',code=422,json={'supplier_id':1,'items':[{'product_id':p['id'],'quote_id':qa['id'],'quantity':1,'lowest_price':0}]})
   await request(c,'POST','/suppliers/1/purchase-order',code=422,json={'request_key':'forged','items':[{'product_id':p['id'],'quote_id':qa['id'],'quantity':1,'unit_price':0}]})
   for path in ['/supplier-quotes/suppliers/1',f'/supplier-quotes/{qa["id"]}/revisions']:await request(c,'GET',path,warehouse='2',code=404)
   await request(c,'POST','/supplier-quotes/purchase-preview',warehouse='2',code=404,json={'supplier_id':1,'items':[{'product_id':p['id'],'quote_id':qa['id'],'quantity':1}]})
   original=quotes.record_history
   async def fail(*args,**kwargs):raise RuntimeError('synthetic audit write failure')
   monkeypatch.setattr(quotes,'record_history',fail);req={**body,'request_key':'rollback-revision','expected_quote_version':qa['version'],'tiers':[{'min_quantity':'1','max_quantity':None,'unit_price':'7'}]}
   # The ASGI test transport re-raises unhandled application exceptions instead of returning its HTTP 500.
   with pytest.raises(RuntimeError,match='synthetic audit write failure'):
    await c.put(f'/api/v1/supplier-quotes/{qa["id"]}',headers=auth(1),json=req)
   async with f() as db:
    assert (await db.get(SupplierQuote,qa['id'])).current_revision==1
    assert (await db.execute(select(func.count(SupplierQuoteRevision.id)))).scalar_one()==2
   monkeypatch.setattr(quotes,'record_history',original);saved=await request(c,'PUT',f'/supplier-quotes/{qa["id"]}',json=req);again=await request(c,'PUT',f'/supplier-quotes/{qa["id"]}',json=req)
   assert again['replayed'] and again['revision_id']==saved['revision_id'] and saved['revision']==2
   actual('forgery_rollback',{'forged_fields':422,'multiwarehouse_selected_foreign':404,'failed_version_rolled_back':True,'same_request_recovery':saved,'retry':again})
 asyncio.run(run())
