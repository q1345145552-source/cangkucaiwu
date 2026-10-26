"""Create empty journals with per-table savepoints; never derive historical stock."""
from fastapi import HTTPException
from sqlalchemy import inspect, Numeric
import re
from app.models.inventory import InventoryAccount, InventoryMovement, InventoryReceiptLink, InventoryOperation, InventoryPolicy

MODELS = (InventoryAccount, InventoryMovement, InventoryReceiptLink, InventoryOperation, InventoryPolicy)


async def ensure_inventory(conn):
    def check(c):
        i = inspect(c)
        missing = []
        for model in MODELS:
            table = model.__table__
            if not i.has_table(table.name):
                missing.append(table.name)
                continue
            cols = {v['name']: v for v in i.get_columns(table.name)}
            missing.extend(table.name + '.' + v.name for v in table.columns
                           if v.name not in cols or (not v.nullable and cols[v.name]['nullable']))
            for v in table.columns:
                if isinstance(v.type, Numeric) and v.name in cols:
                    actual=cols[v.name]['type']
                    if getattr(actual,'precision',None)!=v.type.precision or getattr(actual,'scale',None)!=v.type.scale:
                        missing.append(table.name+'.'+v.name+'_precision')
            uniques = i.get_unique_constraints(table.name)
            checks = i.get_check_constraints(table.name)
            for constraint in table.constraints:
                if constraint.__class__.__name__ == 'UniqueConstraint' and not any(
                    v['name'] == constraint.name and v['column_names'] == [x.name for x in constraint.columns] for v in uniques):
                    missing.append(constraint.name)
                if constraint.__class__.__name__ == 'CheckConstraint' and not any(v['name'] == constraint.name for v in checks):
                    missing.append(constraint.name)
            if table.name=='inventory_accounts':
                definition=next((x['sqltext'] for x in checks if x['name']=='ck_inventory_nonnegative'),'')
                normalized=re.sub(r'[\s()\"]','',re.sub(r'::numeric','',definition.lower()))
                if normalized!='recorded_quantity>=0':missing.append('ck_inventory_nonnegative_definition')
            fks = i.get_foreign_keys(table.name)
            for fk in table.foreign_keys:
                if not any(v['constrained_columns'] == [fk.parent.name] and v['referred_table'] == fk.column.table.name
                           and v['referred_columns'] == [fk.column.name] for v in fks):
                    missing.append(table.name + '.' + fk.parent.name + '_fk')
        return missing
    missing = await conn.run_sync(check)
    if missing:
        raise HTTPException(503, {'code': 'inventory_migration_missing', 'message': '库存结构或保护约束未就绪，请核对迁移', 'missing': missing})


async def migrate_inventory(conn):
    for model in MODELS:
        async with conn.begin_nested():
            await conn.run_sync(lambda c, m=model: m.__table__.create(c, checkfirst=True))
    await ensure_inventory(conn)
    print('库存基础迁移 READY：5张空表；未猜期初、未回填历史收货或成本、未补权限')
