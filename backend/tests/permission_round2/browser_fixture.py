import sys,asyncio,json,os
sys.path.insert(0,'/private/tmp/permissions-round2-20261028/backend/tests/permission_round2')
from fixtures import *
async def main():
    engine=create_async_engine(URL);factory=async_sessionmaker(engine,expire_on_commit=False)
    database._engine=engine;database._session_maker=factory
    async with AsyncClient(transport=ASGITransport(app=app),base_url='http://round2.local') as client:
        for state in ('pending','verified','approved_ready'):
            def headers(uid):return {'Authorization':'Bearer '+create_access_token({'sub':str(uid)})}
            response=await client.post('/api/v1/expense-fund/recharge/request',headers=headers(2),json={'amount':5,'reason':'SYNTHETIC UI '+state})
            assert response.status_code==200,response.text
            rid=response.json()['id']
            if state!='pending':
                response=await client.post('/api/v1/expense-fund/recharge/review',headers=headers(3),json={'request_id':rid,'action':'verify'})
                assert response.status_code==200,response.text
            if state=='approved_ready':
                response=await client.post('/api/v1/expense-fund/recharge/review',headers=headers(1),json={'request_id':rid,'action':'approve'})
                assert response.status_code==200,response.text
            print('SYNTHETIC UI request',rid,state)
    result={}
    async with factory() as db:
        for uid in (1,2,3,4,6):
            u=await db.get(User,uid)
            result[uid]={'token':create_access_token({'sub':str(uid)}),'user':{'id':u.id,'username':u.username,'display_name':u.display_name,'role':u.role,'warehouse_id':u.warehouse_id,'extra_permissions':u.extra_permissions,'is_active':True,'warehouses':[{'id':1,'name':'SYNTHETIC WH1'}]}}
    Path('/private/tmp/permissions-round2-env/browser-identities.json').write_text(json.dumps(result))
    await engine.dispose()
asyncio.run(main())
