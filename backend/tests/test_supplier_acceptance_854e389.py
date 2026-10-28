"""New acceptance scenarios for 854e389; disposable localhost data only."""
import asyncio
import json
import os
from pathlib import Path
from sqlalchemy import select, text
from app.models import User, SupplierProduct, InventoryMovement, PayableBill
from tests.test_supplier_sku_round5 import fixture, sku, product, map_it
from tests.test_supplier_workflow_round1 import request

ACTUAL = {}
def record(key, value):
    ACTUAL[key] = value
    if os.environ.get('SUPPLIER_ACCEPTANCE_REPORT'):
        Path(os.environ['SUPPLIER_ACCEPTANCE_REPORT']).write_text(json.dumps(ACTUAL, ensure_ascii=False, default=str, indent=2))


def test_summary_legacy_null_currency_and_units_are_separate_without_rewriting_rows(tmp_path, monkeypatch):
    async def run():
        async with fixture(tmp_path, monkeypatch) as (_, f, c, _):
            async with f() as db:
                entries = [SupplierProduct(supplier_id=sid, product_name='验收同名胶带', spec='48mm', unit=unit, currency=cur, unit_price=amount) for sid, unit, cur, amount in [(1,'卷','THB',20),(3,'卷','THB',25),(1,'箱','THB',180),(3,'箱','THB',200),(1,'卷','CNY',3),(3,'卷','CNY',4),(1,'卷','THB',22),(2,'卷','THB',0.01),(3,'卷','THB',24)]]
                db.add_all(entries); await db.flush()
                await db.execute(text('UPDATE supplier_products SET currency=NULL WHERE id=:id'), {'id':entries[6].id})
                await db.execute(text("UPDATE supplier_products SET currency='' WHERE id=:id"), {'id':entries[8].id})
                await db.commit()
            result=await request(c,'GET','/suppliers/procurement-summary')
            rows=[row for row in result['product_compare'] if row['product_name']=='验收同名胶带']
            record('currency_units',{'rows':rows,'tips':result['savings_tips']})
            assert len(rows)==3, rows
            groups={(row['currency'],row['unit']):(row['min_price'],row['max_price']) for row in rows}
            assert groups=={('THB','卷'):(20,25),('THB','箱'):(180,200),('CNY','卷'):(3,4)}
            assert {tip['unit'] for tip in result['savings_tips'] if tip['product_name']=='验收同名胶带'}=={'卷','箱'}
            compared=await request(c,'GET','/suppliers/compare-prices?product_name=验收同名胶带&currency=THB')
            assert len(compared['data'])==6 and all(row['supplier_id']!=2 for row in compared['data'])
            async with f() as db:
                assert (await db.get(SupplierProduct,entries[6].id)).currency is None
                assert (await db.get(SupplierProduct,entries[8].id)).currency == ''
    asyncio.run(run())


def test_ai_comparison_invalid_currency_type_is_400_and_does_not_call_provider(tmp_path, monkeypatch):
    async def run():
        async with fixture(tmp_path, monkeypatch) as (_, f, c, _):
            for value in (['THB'], {'code':'THB'}, 123, True):
                result=await request(c,'POST','/suppliers/ai-compare',code=400,json={'mode':'product','compare_data':[{'currency':value,'unit_price':20}]})
                assert '币种' in result['detail']
            record('invalid_currency_request',{'invalid_types':4,'status':400,'provider_calls':0})
    asyncio.run(run())


def test_catalog_inventory_quote_receipt_issue_return_count_reverse_and_scope(tmp_path, monkeypatch):
    async def run():
        from tests.test_inventory_round11 import fixture as stock_fixture, submit as count_submit, review as count_review
        from tests.test_inventory_round10 import opening, receive, issue, returned, detail, reverse
        from tests.test_supplier_quotes_round6 import quoted, preview
        from sqlalchemy import func
        async with stock_fixture(tmp_path, monkeypatch) as (_, f, c, _):
            async with f() as db:
                for uid, perms in [(3,['耗材库存','标准SKU目录','供应商管理']),(4,['耗材库存','标准SKU目录','标准SKU管理','供应商管理']),(5,['耗材库存','标准SKU目录','标准SKU管理','供应商管理']),(9,[])]:
                    (await db.get(User,uid)).extra_permissions=perms
                await db.commit()
            attrs={'material':'BOPP','width':{'value':48,'unit':'mm'}}
            s=await sku(c,code='QA-ROLL-48',name='验收合成胶带',attributes=attrs,base_unit='卷')
            s=await request(c,'PUT',f'/sku-catalog/{s["id"]}',json={'code':s['code'],'name':'验收编辑胶带','attributes':attrs,'base_unit':'卷','category_id':None,'active':True,'expected_version':s['version']})
            p=await product(c,product_name='验收供应商胶带',unit='卷',unit_price=9,catalog_attributes=attrs)
            await map_it(c,p['id'],s)
            q,_=await quoted(c,p['id'],s,unit='卷',tiers=[{'min_quantity':'1','max_quantity':'10','unit_price':'11'},{'min_quantity':'10','max_quantity':None,'unit_price':'9'}])
            v=await preview(c,p['id'],q['id'],12)
            assert v['total']=='108' and v['rows'][0]['unit_price']=='9'
            order=await request(c,'POST','/suppliers/1/purchase-order',json={'request_key':'acceptance-12-rolls','pricing_version':v['version'],'items':[{'product_id':p['id'],'quote_id':q['id'],'quantity':12}]})
            o,_=await opening(c,s,'73')
            await receive(c,order,12,key='acceptance-receipt-12')
            a=(await request(c,'GET',f'/inventory/accounts/{o["account"]["id"]}'))['account'];assert a['available_quantity']=='85'
            out,_=await issue(c,a,'9');back,_=await returned(c,out['movement_id'],out['account'],'2')
            assert back['account']['available_quantity']=='78'
            counted,_=await count_submit(c,back['account'],'75');checked,_=await count_review(c,counted['data']);assert checked['account']['available_quantity']=='75'
            one,_=await issue(c,checked['account'],'1');restored,_=await reverse(c,one['movement_id'],one['account']);assert restored['account']['available_quantity']=='75'
            journal=await detail(c,a['id']);assert all(row['cost_amount'] is None for row in journal['data'])
            async with f() as db:
                before=(await db.execute(select(func.count()).select_from(InventoryMovement))).scalar_one()
            denied=[]
            for uid in (2,5,9):
                for path in ['/inventory','/inventory/catalog',f'/inventory/accounts/{a["id"]}','/sku-catalog','/suppliers/compare-prices','/suppliers/compare-logistics']:
                    denied.append(await request(c,'GET',path,uid=uid,code=403))
            for uid in (3,4):
                assert (await request(c,'GET','/inventory',uid=uid))['total']==1
                await request(c,'POST','/inventory/openings',uid=uid,code=403,json={'request_key':'role-'+str(uid),'sku_id':s['id'],'base_unit':'roll','opening_quantity':'1','occurred_at':'2026-10-01T00:00:00+07:00','confirmed':True,'expected_version':a['version'],'change_reason':'不能越权'})
            for uid,warehouse in [(7,'2'),(1,'2')]:
                await request(c,'GET',f'/inventory/accounts/{a["id"]}',uid=uid,warehouse=warehouse,code=403)
                await request(c,'POST',f'/inventory/accounts/{a["id"]}/issues',uid=uid,warehouse=warehouse,code=403,json={'request_key':'foreign-'+str(uid),'issued_quantity':'1','expected_version':journal['account']['version'],'purpose':'拒绝跨仓'})
                assert (await request(c,'GET','/sku-catalog',uid=uid,warehouse=warehouse))['data']==[]
            await request(c,'PUT',f'/sku-catalog/{s["id"]}',uid=3,code=403,json={'code':s['code'],'name':'不得改','attributes':attrs,'base_unit':'roll'})
            async with f() as db:
                after=(await db.execute(select(func.count()).select_from(InventoryMovement))).scalar_one();assert before==after
            assert (await detail(c,a['id']))['account']['available_quantity']=='75'
            record('complete_quantity_and_scope',{'quote_12_total':108,'opening':73,'received':12,'issued':9,'returned':2,'counted':75,'extra_issue_reversed':True,'final':75,'currency':'THB','unit':'roll','cost_amount':None,'denied_role_reads':len(denied),'cross_warehouse_reads_writes':4,'denial_movement_count_before':before,'denial_movement_count_after':after})
    asyncio.run(run())


def test_same_login_token_observes_revocation_disable_and_unselected_warehouse(tmp_path, monkeypatch):
    async def run():
        from sqlalchemy import func
        from app.models import StandardSKU
        from tests.test_round2_permissions import auth
        async with fixture(tmp_path,monkeypatch) as (_,f,c,_):
            headers={**auth(4),'X-Warehouse-ID':'1'}
            body={'code':'QA-TOKEN-1','name':'验收权限','attributes':{'material':'PE'},'base_unit':'piece'}
            created=await c.post('/api/v1/sku-catalog',headers=headers,json=body);assert created.status_code==200
            foreign=await request(c,'POST','/sku-catalog',uid=7,warehouse='2',json={**body,'code':'QA-FOREIGN'})
            assert all(row['id']!=foreign['id'] for row in (await request(c,'GET','/sku-catalog',uid=4))['data'])
            await request(c,'GET','/suppliers/compare-prices',uid=4,warehouse='2',code=403)
            async with f() as db:
                user=await db.get(User,4);user.extra_permissions=['标准SKU目录','供应商管理'];await db.commit()
                before=(await db.execute(select(func.count()).select_from(StandardSKU))).scalar_one()
            denied=await c.post('/api/v1/sku-catalog',headers=headers,json={**body,'code':'QA-TOKEN-2'});assert denied.status_code==403
            assert (await c.get('/api/v1/sku-catalog',headers=headers)).status_code==200
            async with f() as db:
                assert (await db.execute(select(func.count()).select_from(StandardSKU))).scalar_one()==before
                (await db.get(User,4)).is_active=False;await db.commit()
            inactive=await c.get('/api/v1/sku-catalog',headers=headers);assert inactive.status_code==401
            record('existing_token_security',{'create_before_revoke':200,'same_token_create_after_revoke':403,'read_grant_retained':200,'disabled_same_token':401,'forged_unassigned_warehouse':403,'denied_writes_created_rows':0})
    asyncio.run(run())
