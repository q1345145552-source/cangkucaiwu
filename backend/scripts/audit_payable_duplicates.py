"""Explicit connection only; output conflicts without changing history or installing constraints."""
import asyncio, json, os, sys, argparse, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.services.payable_dedup_migration import conflict_report
from app.core.payable_constraints import missing_guards

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--warehouse-id', type=int)
    parser.add_argument('--schema', help='Optional explicit schema, primarily for isolated validation')
    args = parser.parse_args()
    url = os.environ.get('PAYABLE_AUDIT_DATABASE_URL')
    if not url:
        raise SystemExit('请显式设置PAYABLE_AUDIT_DATABASE_URL；脚本不读取默认或生产连接')
    if args.schema and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',args.schema):raise SystemExit('schema格式不正确')
    engine = create_async_engine(url,connect_args={'server_settings':{'search_path':args.schema}} if args.schema else {})
    try:
        async with engine.connect() as conn:
            await conn.execute(text('SET TRANSACTION READ ONLY'))
            result = {'read_only': True, 'warehouse_id': args.warehouse_id,
                'missing_guards': await missing_guards(conn), 'conflicts': await conflict_report(conn,args.warehouse_id)}
            await conn.rollback()
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    finally:
        await engine.dispose()
if __name__ == '__main__': asyncio.run(main())
