"""Execute unchanged round-five assertions with only fixture/output isolation.
Versioned mode converts the synthetic initial users through the real converter, not auth stubs.
"""
from fixtures import *
import runpy
from app.core.action_access import convert_legacy
import fixtures
suite=sys.argv[1];versioned=len(sys.argv)>2 and sys.argv[2]=='versioned'
assert suite in ('acceptance','attachment_acceptance','write_responses','history_fields')
original_seed=fixtures.seed
async def seed(db):
 await original_seed(db)
 if versioned:
  for u in (await db.execute(select(User))).scalars():
   if u.role in ('staff','supervisor'):u.extra_permissions=convert_legacy(u)[0]
  await db.commit()
fixtures.seed=seed
if suite=='attachment_acceptance':
 async def prepare():
  engine=create_async_engine(URL);factory=async_sessionmaker(engine,expire_on_commit=False)
  async with factory() as db:
   (await db.get(Employee,3)).status='regular';u=await db.get(User,4);u.extra_permissions=ALL
   if versioned:u.extra_permissions=convert_legacy(u)[0]
   await db.commit()
  await engine.dispose()
 asyncio.run(prepare())
path=ROOT/'backend/tests/permission_round5'/f'{suite}.py'
source=path.read_text()
if suite=='attachment_acceptance':
 source='\n'.join(line for line in source.splitlines() if not line.startswith("OUT=ROOT/'docs/permissions-round5"))
(OUT/'provenance.json').write_text(json.dumps({'source':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'adaptation':'round7 fixtures/output only; original assertion bodies unchanged','versioned_seed':versioned},indent=2))
exec(compile(source,str(path),'exec'),{'__name__':'__main__'})
