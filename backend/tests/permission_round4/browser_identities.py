from fixtures import *
async def main():
 engine=create_async_engine(URL);factory=async_sessionmaker(engine,expire_on_commit=False);result={}
 async with factory() as db:
  # Restore synthetic finance management grants removed by negative API cases.
  finance=await db.get(User,3);finance.extra_permissions=ALL;await db.commit()
  for uid in (1,2,3,4,6):
   u=await db.get(User,uid);result[uid]={'token':create_access_token({'sub':str(uid)}),'user':{'id':u.id,'username':u.username,'display_name':u.display_name,'role':u.role,'warehouse_id':u.warehouse_id,'extra_permissions':u.extra_permissions,'is_active':True,'warehouses':[{'id':1,'name':'SYNTHETIC WH1','code':'AUDIT1'}]}}
 Path('browser-identities.json').write_text(json.dumps(result));await engine.dispose()
asyncio.run(main())
