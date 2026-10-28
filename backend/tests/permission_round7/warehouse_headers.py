"""Real writes must reject forged context instead of silently writing the primary warehouse."""
from harness import *
async def main():
 engine,factory=await environment()
 async with AsyncClient(transport=ASGITransport(app=app),base_url='http://local') as client:
  ev=Evidence(factory,client)
  for header in ('2','abc','0',''):
   await ev.call('order-count-invalid-'+header,1,'PUT','/efficiency/order-count',{'date':'2026-10-28','order_count':17},warehouse=header,expected=403)
  await ev.call('order-count-authorized',1,'PUT','/efficiency/order-count',{'date':'2026-10-28','order_count':19})
  await ev.call('order-count-no-header',1,'PUT','/efficiency/order-count',{'date':'2026-10-28','order_count':20},warehouse=None)
  async with factory() as db:
   db.add(UserWarehouse(user_id=1,warehouse_id=2));await db.commit()
  await ev.call('order-count-authorized-secondary',1,'PUT','/efficiency/order-count',{'date':'2026-10-28','order_count':21},warehouse='2')
  async with factory() as db:
   w=await db.get(Warehouse,2);w.is_active=False;await db.commit()
  await ev.call('order-count-disabled-warehouse',1,'PUT','/efficiency/order-count',{'date':'2026-10-28','order_count':22},warehouse='2',expected=403)
  await ev.call('supervisor-all-header-denied',2,'PUT','/efficiency/order-count',{'date':'2026-10-28','order_count':23},warehouse='all',expected=403)
  ev.finish()
 await engine.dispose()
if __name__=='__main__':asyncio.run(main())
