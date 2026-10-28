"""Independent f390302 review: real HTTP/transactions in disposable localhost schemas."""
import asyncio
import pytest
from sqlalchemy import event,select
from app.models import User,ProductImportOperation
from app.models.supplier import SupplierCrossBorderPrice
from app.models.recharge import IncomingFlow
from app.models.customer import PaymentAccount
from tests.test_excel_import_repair import send,template,fill,count,legacy_logistics
from tests.test_supplier_workflow_round1 import setup
from tests.test_incoming_operations import URL
pytestmark=pytest.mark.skipif(not URL,reason='Explicit isolated localhost PostgreSQL required')

async def workbook(c,kind):
    if kind=='incoming':
        path='/incoming/import-excel';blob=fill(await template(c,'/incoming/template'),[['2026-10-20',200,'THB','独立合成人甲','现金','复核',1],['2026-10-21',300,'THB','独立合成人乙','现金','复核',1]])
    else:
        path='/suppliers/1/import/logistics';blob=legacy_logistics([['本仓供应商','陆运','普货','深圳仓',800,'5天','CNY'],['本仓供应商','海运','普货','12345',900,'7天','CNY']])
    return path,blob

@pytest.mark.parametrize('kind',['incoming','logistics'])
def test_preview_cannot_be_confirmed_by_another_account(tmp_path,monkeypatch,kind):
 async def run():
  async with setup(tmp_path,monkeypatch) as (_,f,c):
   async with f() as db:(await db.get(User,3)).extra_permissions=['到账流水','供应商管理'];await db.commit()
   path,blob=await workbook(c,kind);pre=await send(c,path,blob)
   await send(c,path,blob,{'mode':'confirm','request_key':'cross-user','preview_version':pre['preview_version']},uid=3,code=409)
   assert await count(f,IncomingFlow)==0 and await count(f,SupplierCrossBorderPrice)==0 and await count(f,ProductImportOperation)==0
   own=await send(c,path,blob,uid=3)
   saved=await send(c,path,blob,{'mode':'confirm','request_key':'cross-user','preview_version':own['preview_version']},uid=3)
   assert saved['imported']==2
 asyncio.run(run())

def test_receipt_preview_never_takes_account_write_locks(tmp_path,monkeypatch):
 async def run():
  async with setup(tmp_path,monkeypatch) as (engine,f,c):
   statements=[]
   def trace(conn,cursor,statement,*args):statements.append(statement)
   event.listen(engine.sync_engine,'before_cursor_execute',trace)
   try:
    path,blob=await workbook(c,'incoming');pre=await send(c,path,blob);assert pre['valid']
   finally:event.remove(engine.sync_engine,'before_cursor_execute',trace)
   assert not any('FOR UPDATE' in sql.upper() for sql in statements),statements
   writes=[sql for sql in statements if sql.lstrip().upper().startswith(('INSERT','UPDATE','DELETE'))]
   # Existing POST audit middleware is retained; no business-table writes are allowed.
   assert all(sql.lstrip().upper().startswith('INSERT INTO AUDIT_LOGS ') for sql in writes),writes
   assert await count(f,ProductImportOperation)==0
   # A real concurrent account writer must not block read-only preview.
   async with f() as holder:
    await holder.execute(select(PaymentAccount).where(PaymentAccount.id==1).with_for_update())
    result=await asyncio.wait_for(send(c,path,blob),2);assert result['valid']
   assert await count(f,IncomingFlow)==0
 asyncio.run(run())

@pytest.mark.parametrize('kind',['incoming','logistics'])
def test_post_insert_exception_rolls_back_then_original_request_concurrently_recovers(tmp_path,monkeypatch,kind):
 async def run():
  async with setup(tmp_path,monkeypatch) as (engine,f,c):
   path,blob=await workbook(c,kind);pre=await send(c,path,blob)
   data={'mode':'confirm','request_key':'after-write-failure','preview_version':pre['preview_version']}
   table='incoming_flows' if kind=='incoming' else 'supplier_cross_border_prices';executed=[]
   def fail(conn,cursor,statement,*args):
    if statement.lstrip().upper().startswith('INSERT INTO '+table.upper()):
     executed.append(statement);raise RuntimeError('isolated exception AFTER database INSERT')
   event.listen(engine.sync_engine,'after_cursor_execute',fail)
   try:
    with pytest.raises(RuntimeError,match='AFTER database INSERT'):await send(c,path,blob,data)
   finally:event.remove(engine.sync_engine,'after_cursor_execute',fail)
   assert executed and await count(f,IncomingFlow)==0 and await count(f,SupplierCrossBorderPrice)==0 and await count(f,ProductImportOperation)==0
   results=await asyncio.gather(*(send(c,path,blob,data) for _ in range(6)))
   assert len({r['id'] for r in results})==1 and sum(not r.get('replayed',False) for r in results)==1
   model=IncomingFlow if kind=='incoming' else SupplierCrossBorderPrice
   assert await count(f,model)==2 and await count(f,ProductImportOperation)==1
   # Discard the success response and retry after source/account availability changes.
   async with f() as db:
    if kind=='incoming':(await db.get(PaymentAccount,1)).status='inactive'
    else:
     from app.models import Supplier
     (await db.get(Supplier,1)).is_active='false'
    await db.commit()
   replay=await send(c,path,blob,data);assert replay['replayed'] and replay['id']==results[0]['id']
   assert await count(f,model)==2
   # Same key cannot cross user identity, even after successful commit.
   async with f() as db:(await db.get(User,3)).extra_permissions=['到账流水','供应商管理'];await db.commit()
   await send(c,path,blob,data,uid=3,code=409)
 asyncio.run(run())


@pytest.mark.parametrize('kind',['incoming','logistics'])
def test_replay_is_scoped_by_warehouse_and_old_preview_never_crosses_scope(tmp_path,monkeypatch,kind):
 async def run():
  async with setup(tmp_path,monkeypatch) as (_,f,c):
   path,blob=await workbook(c,kind);pre=await send(c,path,blob)
   data={'mode':'confirm','request_key':'same-key-two-scopes','preview_version':pre['preview_version']}
   saved=await send(c,path,blob,data)
   if kind=='incoming':
    target=path;other=fill(await template(c,'/incoming/template'),[['2026-10-20',200,'THB','独立合成人甲','现金','复核',2],['2026-10-21',300,'THB','独立合成人乙','现金','复核',2]])
   else:
    target='/suppliers/2/import/logistics';other=legacy_logistics([['外仓供应商','陆运','普货','深圳仓',800,'5天','CNY'],['外仓供应商','海运','普货','12345',900,'7天','CNY']])
   await send(c,target,other,data,warehouse='2',code=409)
   assert await count(f,ProductImportOperation)==1
   own=await send(c,target,other,warehouse='2');other_data={**data,'preview_version':own['preview_version']}
   second=await send(c,target,other,other_data,warehouse='2');assert second['id']!=saved['id'] if kind=='logistics' else not second.get('replayed')
   replay=await send(c,path,blob,data);assert replay['replayed'] and replay['id']==saved['id']
   assert await count(f,ProductImportOperation)==2
   model=IncomingFlow if kind=='incoming' else SupplierCrossBorderPrice
   assert await count(f,model)==4
 asyncio.run(run())


def test_incoming_confirm_locks_accounts_in_order_before_inserts(tmp_path,monkeypatch):
 async def run():
  async with setup(tmp_path,monkeypatch) as (_,f,c):
   async with f() as db:(await db.get(PaymentAccount,3)).currency='THB';await db.commit()
   path='/incoming/import-excel';blob=fill(await template(c,'/incoming/template'),[['2026-10-20',200,'THB','合成逆序甲','现金','复核',3],['2026-10-21',300,'THB','合成逆序乙','现金','复核',1]])
   pre=await send(c,path,blob);order=[]
   import app.services.wallet as wallet
   original=wallet.lock_account
   async def tracked(db,wid,aid,currency):order.append(aid);return await original(db,wid,aid,currency)
   monkeypatch.setattr(wallet,'lock_account',tracked)
   saved=await send(c,path,blob,{'mode':'confirm','request_key':'sorted-accounts','preview_version':pre['preview_version']})
   assert saved['imported']==2 and order==[1,3]
   assert await count(f,IncomingFlow)==2
 asyncio.run(run())



def test_receipt_preview_is_bound_to_exact_file_not_just_parsed_values(tmp_path,monkeypatch):
 async def run():
  from tests.test_excel_import_repair import blob as make_blob
  async with setup(tmp_path,monkeypatch) as (_,f,c):
   path,content=await workbook(c,'incoming');pre=await send(c,path,content)
   columns=['received_date','amount','currency','payer_name','payment_method','remark','account_id']
   equivalent=make_blob(columns,[[r[k] for k in columns] for r in pre['rows']]);other=await send(c,path,equivalent)
   assert [{k:v for k,v in r.items() if k!='row_number'} for r in other['rows']]==[{k:v for k,v in r.items() if k!='row_number'} for r in pre['rows']]
   assert other['preview_version']!=pre['preview_version']
   await send(c,path,equivalent,{'mode':'confirm','request_key':'old-file-preview','preview_version':pre['preview_version']},code=409)
   assert await count(f,IncomingFlow)==0 and await count(f,ProductImportOperation)==0
 asyncio.run(run())


@pytest.mark.parametrize('kind',['incoming','logistics'])
def test_no_commit_proof_is_only_issued_after_locked_absence_check(tmp_path,monkeypatch,kind):
 async def run():
  async with setup(tmp_path,monkeypatch) as (_,f,c):
   path,content=await workbook(c,kind);pre=await send(c,path,content)
   data={'mode':'confirm','request_key':'recover-changed-preview','preview_version':'obsolete-version'}
   rejected=await send(c,path,content,data,code=409);proof=rejected['detail']
   assert proof['code']=='excel_import_not_saved' and proof['not_created'] is True and proof['request_key']==data['request_key']
   assert proof['preview']['preview_version']==pre['preview_version'] and await count(f,ProductImportOperation)==0
   saved=await send(c,path,content,{**data,'preview_version':proof['preview']['preview_version']});assert saved['imported']==2
   conflict=await send(c,path,content,data,code=409);assert not isinstance(conflict['detail'],dict) or conflict['detail'].get('not_created') is not True
   assert await count(f,ProductImportOperation)==1
 asyncio.run(run())
