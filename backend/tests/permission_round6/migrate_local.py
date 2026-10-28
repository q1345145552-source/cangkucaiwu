"""Explicit, synthetic-only CLI. Dry-run by default; no dotenv or production host allowed."""
import argparse,asyncio,json,os,sys
from pathlib import Path
from urllib.parse import urlparse
p=argparse.ArgumentParser();p.add_argument('--database-url',required=True);p.add_argument('--actor-id',type=int,required=True);p.add_argument('--user-ids',type=int,nargs='+',required=True);p.add_argument('--reason',required=True);p.add_argument('--apply',action='store_true');args=p.parse_args()
u=urlparse(args.database_url)
assert u.hostname=='127.0.0.1' and u.port==65509 and u.path in ('/round6','/round6browser','/round6migration'), 'only the dedicated synthetic local cluster is permitted'
assert Path.cwd()==Path('/private/tmp/permissions-round6-env') and not Path('.env').exists()
os.environ.update(DATABASE_URL=args.database_url,SECRET_KEY='synthetic-round6-migration-only-signing-key')
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/'backend'))
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.models.user import User
from app.models.user_warehouse import UserWarehouse
from app.core.permissions import Role
from app.core.round2_access import require_account_manager,login_target_scope
from app.core.action_access import permission_state,convert_legacy
from app.services.action_permission_migration import migrate_permissions
async def main():
 engine=create_async_engine(args.database_url);factory=async_sessionmaker(engine,expire_on_commit=False)
 async with factory() as db:
  actor=await db.get(User,args.actor_id)
  assert actor is not None and actor.is_active, 'active actor required'
  actor._warehouse_ids=list((await db.execute(select(UserWarehouse.warehouse_id).where(UserWarehouse.user_id==actor.id))).scalars());actor._all_warehouse_ids=actor._warehouse_ids
  require_account_manager(actor,platform=True)
  if args.apply:
   result=await migrate_permissions(db,actor,args.user_ids,args.reason);await db.commit();print(json.dumps({'mode':'apply',**result}))
  else:
   result=[]
   for ident in args.user_ids:
    target=await db.get(User,ident);assert target is not None and target.id!=actor.id
    await login_target_scope(db,actor,target);converted,state=convert_legacy(target)
    result.append({'id':ident,'source_version':state['version'],'original':target.extra_permissions,'proposed':converted,'unknown':state['unknown']})
   await db.rollback();print(json.dumps({'mode':'dry-run','targets':result},ensure_ascii=False,indent=2))
 await engine.dispose()
asyncio.run(main())
