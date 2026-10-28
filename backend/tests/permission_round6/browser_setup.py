"""Only the dedicated synthetic browser database; authentication remains real JWT."""
from fixtures import *
from app.core.action_access import encode_permissions
from app.core.security import hash_password
async def main():
 url='postgresql+asyncpg://round6@127.0.0.1:65509/round6browser'
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 async with engine.begin() as c:
  await c.execute(text('DROP SCHEMA public CASCADE'));await c.execute(text('CREATE SCHEMA public'));await c.run_sync(database.Base.metadata.create_all)
 async with factory() as db:
  await seed(db)
  grants={2:['employees:view','attendance:view','leave:view'],3:['employees:view','payroll:view','expense_fund:view','reimbursement:view'],4:['payroll:operate','employees:operate','expense_fund:operate','reimbursement:operate'],6:['leave:approve']}
  for uid,g in grants.items():
   u=await db.get(User,uid);u.extra_permissions=encode_permissions(u.role,g)
  for uid in range(1,9):(await db.get(User,uid)).password_hash=hash_password('SYNTHETIC-ONLY-password')
  await db.commit()
 Path('/private/tmp/permissions-round6-env/browser-identities.json').write_text(json.dumps({i:{'token':create_access_token({'sub':str(i)})} for i in range(1,9)}))
 await engine.dispose()
asyncio.run(main())
