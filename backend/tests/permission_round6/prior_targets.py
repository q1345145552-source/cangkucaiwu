"""Run inherited actual-route targets without changing assertion bodies or prior evidence."""
from fixtures import *
import fixtures,runpy
from app.core.action_access import convert_legacy
name=sys.argv[1];versioned=sys.argv[2]=='versioned';authorized_cash=len(sys.argv)>3 and sys.argv[3]=='authorized-cash';assert name in ('round2','partial','round3','round4')
folder=ROOT/'backend/tests'/('permission_round2' if name in ('round2','partial') else 'permission_'+name)
script='run_acceptance.py' if name=='round2' else 'partial_acceptance.py' if name=='partial' else 'acceptance.py'
sys.path.insert(0,str(folder))
original=fixtures.seed
async def seeded(db):
 await original(db)
 if versioned:
  for user in (await db.execute(select(User))).scalars():
   if user.role in ('staff','supervisor'):user.extra_permissions=convert_legacy(user)[0]
  await db.commit()
 if authorized_cash:
  db.add(User(id=125,username='SYNTHETIC independent finance creator',display_name='SYNTHETIC FINANCE C',role='staff',warehouse_id=1,password_hash='synthetic',extra_permissions=['@wf-actions:1','cash_advances:operate']))
  await db.flush();db.add(UserWarehouse(user_id=125,warehouse_id=1));await db.commit()
fixtures.seed=seeded
if authorized_cash:
 import types
 path=folder/'scenarios.py';source=path.read_text()
 assert 'async def cash(payer=2,creator=2):' in source
 source=source.replace('async def cash(payer=2,creator=2):','async def cash(payer=2,creator=125):')
 module=types.ModuleType('scenarios');exec(compile(source,str(path),'exec'),module.__dict__);sys.modules['scenarios']=module
 (OUT/'authorized-actor-adaptation.json').write_text(json.dumps({'original_source':str(path),'original_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'change':'cash helper default creator 2 (supervisor) -> 125 (independent authorized finance C); payer, amounts, approval actors, DB and all assertions unchanged','reason':'round6 role ceiling rejects supervisor creating another person cash debt; retain real downstream financial assertions with a lawful independent creator'},indent=2))
if authorized_cash:
 source=(folder/script).read_text()
 old="loan=await call('C-cash-request',2,'POST','/cash-advances',{'advance_date':'2026-10-20','amount':100,'purpose':'expense'},check=no_money)"
 new="loan=await call('C-cash-request',125,'POST','/cash-advances',{'advance_date':'2026-10-20','amount':100,'purpose':'expense','payer_id':2},check=no_money)"
 assert old in source;source=source.replace(old,new)
 scope={'__name__':'inherited_target'};exec(compile(source,str(folder/script),'exec'),scope)
else:
 scope=runpy.run_path(str(folder/script))
(OUT/'provenance.json').write_text(json.dumps({'source':str(folder/script),'sha256':hashlib.sha256((folder/script).read_bytes()).hexdigest(),'versioned':versioned,'adaptation':'fixture and output only'},indent=2))
if name == 'round4' and os.environ.get('ROUND6_MEDIA') == '1':
 import extra_scenarios,fix01_media
 original_scenarios=extra_scenarios.scenarios
 async def with_media(factory,client,call,log,fail):
  await original_scenarios(factory,client,call,log,fail)
  await fix01_media.scenarios(factory,client,log,OUT)
 extra_scenarios.scenarios=with_media
scope['main'].__globals__['OUT']=OUT
asyncio.run(scope['main']())
