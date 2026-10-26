"""Nullable references and an empty registry. Historical origins are never backfilled."""
from sqlalchemy import text,inspect
from fastapi import HTTPException
from app.models.cost_identity import CostIdentity,GUARDS
from app.core.payable_constraints import canonical_predicate

async def ensure_cost_guards(conn):
    def check(c):
        i=inspect(c)
        if not i.has_table('cost_identities'):return list(GUARDS)
        indexes={v['name']:v for v in i.get_indexes('cost_identities')};missing=[]
        for name,(cols,predicate) in GUARDS.items():
            v=indexes.get(name,{});options=v.get('dialect_options',{})
            actual=options.get('postgresql_where',options.get('sqlite_where',''))
            if not v.get('unique') or v.get('column_names')!=cols or canonical_predicate(actual)!=canonical_predicate(predicate or ''):missing.append(name)
        return missing
    missing=await conn.run_sync(check)
    if conn.dialect.name=='postgresql':
        valid=set((await conn.execute(text("SELECT c.relname FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema() AND i.indisvalid AND i.indisready"))).scalars())
        missing=sorted(set(missing)|(set(GUARDS)-valid))
    if missing:raise HTTPException(503,{'code':'cost_identity_guards_missing','message':'费用身份唯一约束未就绪，已停止新登记和状态变更，请管理员核查迁移','missing_guards':missing})

async def migrate_cost_identities(conn):
    async with conn.begin_nested():await conn.run_sync(lambda c:CostIdentity.__table__.create(c,checkfirst=True))
    for table in ('payable_bills','expense_approvals','expense_fund_items','expense_records'):
        async with conn.begin_nested():await conn.execute(text(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS cost_identity_id INTEGER REFERENCES cost_identities(id)'))
    await ensure_cost_guards(conn)
    print('跨渠道费用身份迁移 READY：空身份表及4个可空引用，未回填历史费用')
