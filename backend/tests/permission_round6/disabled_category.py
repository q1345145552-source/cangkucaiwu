"""Real-route check for an already disabled reference-data write, not a new policy."""
from fixtures import *
async def main():
 engine=create_async_engine(URL);factory=async_sessionmaker(engine,expire_on_commit=False)
 database._engine=engine;database._session_maker=factory
 records=[]
 async with AsyncClient(transport=ASGITransport(app=app),base_url='http://round6.local') as client:
  for uid in [1,2,3]:
   before=await snapshot(factory)
   me=await client.get('/api/v1/auth/me',headers={'Authorization':'Bearer '+create_access_token({'sub':str(uid)})})
   assert me.status_code==200
   assert not any(a['id']=='suppliers.create_category' for a in me.json()['action_access']['actions'])
   r=await client.post('/api/v1/suppliers/categories?name=SYNTHETIC',headers={'Authorization':'Bearer '+create_access_token({'sub':str(uid)})})
   after=await snapshot(factory);diff={t:{'before':before[t],'after':after[t]} for t in before if before[t]!=after[t]}
   assert r.status_code==403,r.text
   assert not any(t not in ('audit_logs','data_change_history') for t in diff)
   records.append({'id':f'disabled-category-{uid}','user':uid,'method':'POST','path':'/suppliers/categories?name=SYNTHETIC','expected':403,'actual':r.status_code,'response':r.json(),'database_diff':diff,'errors':[]})
 (OUT/'requests.json').write_text(json.dumps(records,ensure_ascii=False,indent=2));(OUT/'status.json').write_text(json.dumps({'requests':6,'failures':[]}))
 await engine.dispose()
asyncio.run(main())
