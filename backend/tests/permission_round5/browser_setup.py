from fixtures import *
async def main():
 engine=create_async_engine(URL);factory=async_sessionmaker(engine,expire_on_commit=False);result={}
 async with factory() as db:
  (await db.get(Employee,3)).status='regular'
  for uid in (1,2,3,4,6,11,12):
   u=await db.get(User,uid)
   if uid==4:u.extra_permissions=ALL
   result[uid]={'token':create_access_token({'sub':str(uid)}),'user':{'id':uid,'username':u.username,'display_name':u.display_name,'role':u.role,'warehouse_id':u.warehouse_id,'extra_permissions':u.extra_permissions,'is_active':True}}
  await db.commit()
 Path('browser-identities.json').write_text(json.dumps(result));await engine.dispose()
asyncio.run(main())
