"""Local-only browser fixture, reuses round-one synthetic seed and unmodified application."""
import asyncio,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import run_audit as audit
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
async def prepare():
 engine=create_async_engine(audit.URL)
 async with engine.begin() as c:await c.execute(text('CREATE SCHEMA audit_browser'))
 await engine.dispose()
 engine=create_async_engine(audit.URL,connect_args={'server_settings':{'search_path':'audit_browser'}})
 async with engine.begin() as c:await c.run_sync(audit.database.Base.metadata.create_all)
 factory=async_sessionmaker(engine,expire_on_commit=False)
 async with factory() as db:await audit.seed(db)
 await engine.dispose()
 Path('browser-identities.json').write_text(json.dumps({str(uid):{'token':audit.create_access_token({'sub':str(uid)})} for uid in (1,2,3,6,8)}))
if __name__=='__main__':
 asyncio.run(prepare())
 audit.database._engine=create_async_engine(audit.URL,connect_args={'server_settings':{'search_path':'audit_browser'}})
 audit.database._session_maker=async_sessionmaker(audit.database._engine,expire_on_commit=False)
 import uvicorn
 uvicorn.run(audit.app,host='127.0.0.1',port=65330,lifespan='off',log_level='warning')
