"""Only the dedicated synthetic browser database; authentication remains real JWT."""
from fixtures import *
from app.core.action_access import encode_permissions
from app.core.security import hash_password
async def main():
 url='postgresql+asyncpg://round7@127.0.0.1:65519/round7browser'
 engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
 async with engine.begin() as c:
  await c.execute(text('DROP SCHEMA public CASCADE'));await c.execute(text('CREATE SCHEMA public'));await c.run_sync(database.Base.metadata.create_all)
 async with factory() as db:
  await seed(db)
  db.add(StandardSKU(id=1,warehouse_id=1,code='SYN-CARTON',name='合成纸箱',attributes={},base_unit='个',created_by=1));await db.flush()
  db.add(InventoryAccount(id=7,warehouse_id=1,sku_id=1,base_unit='个',sku_snapshot={'name':'合成纸箱'},recorded_quantity=10,opening_confirmed=True))
  db.add(PurchaseOrder(id=21,warehouse_id=1,supplier_id=1,created_by=1,order_number='SYN-BROWSER-21',total_amount=100,currency='THB',status='confirmed',items=[{'line_id':'line-21','product_name':'合成纸箱','quantity':10,'received_quantity':0,'unit':'个','unit_price':10,'subtotal':100}]))
  db.add(UserWarehouse(user_id=1,warehouse_id=2))
  (await db.get(Employee,3)).passport_photo_path="uploads/1/r7-browser-own.png"
  own=Path(os.environ["UPLOAD_DIR"])/"1/r7-browser-own.png";own.parent.mkdir(parents=True,exist_ok=True);own.write_bytes(PNG)
  grants={2:['employees:view','attendance:view','leave:view'],3:['employees:view','payroll:view','expense_fund:view','reimbursement:view'],4:['payroll:operate','employees:operate','expense_fund:operate','reimbursement:operate','payable:operate','payment_plans:operate','suppliers:operate','inventory:operate'],6:['leave:approve']}
  for uid,g in grants.items():
   u=await db.get(User,uid);u.extra_permissions=encode_permissions(u.role,g)
  for uid in range(1,9):(await db.get(User,uid)).password_hash=hash_password('SYNTHETIC-ONLY-password')
  await db.commit()
 Path('/private/tmp/permissions-round7-env/browser-identities.json').write_text(json.dumps({i:{'token':create_access_token({'sub':str(i)})} for i in range(1,9)}))
 await engine.dispose()
asyncio.run(main())
