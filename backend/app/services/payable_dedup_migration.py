"""Add nullable metadata and real unique guards; never repair conflicting history."""
import json
from sqlalchemy import text, inspect
from app.core.payable_constraints import GUARDS, missing_guards


async def conflict_report(conn, warehouse_id=None):
    condition = 'WHERE warehouse_id=:wid' if warehouse_id is not None else ''
    args = {'wid': warehouse_id} if warehouse_id is not None else {}
    result = {}
    columns = await conn.run_sync(lambda c: {table:{v['name'] for v in inspect(c).get_columns(table)} for table in ('payable_bills','purchase_orders')})
    unavailable = []
    specifications = {
        'same_number_suspicions': ("warehouse_id,supplier_id,btrim(bill_number, E' \\t\\r\\n')", ''),
        'active_purchase_conflicts': ('purchase_order_id', "purchase_order_id IS NOT NULL AND COALESCE(status,'pending') <> 'voided'"),
        'active_invoice_conflicts': ('warehouse_id,invoice_identity_key', "invoice_identity_key IS NOT NULL AND COALESCE(status,'pending') <> 'voided'"),
        'creation_request_conflicts': ('warehouse_id,create_request_key', 'create_request_key IS NOT NULL'),
    }
    for name, (group, predicate) in specifications.items():
        required = {'active_invoice_conflicts':'invoice_identity_key','creation_request_conflicts':'create_request_key'}.get(name)
        if required and required not in columns['payable_bills']:
            unavailable.append(name);result[name]=[];continue
        where = condition + (' AND ' if condition else 'WHERE ') + predicate if predicate else condition
        rows = (await conn.execute(text(f"""SELECT {group}, count(*) count, array_agg(id ORDER BY id) bill_ids
            FROM payable_bills {where} GROUP BY {group} HAVING count(*)>1 ORDER BY min(id)"""), args)).mappings().all()
        result[name] = [dict(r) for r in rows]
        if name=='same_number_suspicions':
            for row in result[name]:row['normalized_bill_number']=row.pop('btrim')
    if 'request_key' in columns['purchase_orders']:
        rows = (await conn.execute(text(f"""SELECT warehouse_id,request_key,count(*) count,array_agg(id ORDER BY id) purchase_ids
            FROM purchase_orders {condition + ' AND ' if condition else 'WHERE '}request_key IS NOT NULL
            GROUP BY warehouse_id,request_key HAVING count(*)>1 ORDER BY min(id)"""), args)).mappings().all()
        result['purchase_request_conflicts'] = [dict(r) for r in rows]
    else:
        result['purchase_request_conflicts']=[];unavailable.append('purchase_request_conflicts')
    result['unavailable_before_column_migration']=unavailable
    return result


async def migrate_payable_dedup(conn):
    columns = {
        'payable_bills': {'invoice_identity': 'JSON', 'invoice_identity_key': 'VARCHAR(64)',
            'create_request_key': 'VARCHAR(100)', 'create_request_fingerprint': 'VARCHAR(64)', 'duplicate_confirmation': 'JSON'},
        'purchase_orders': {'request_key': 'VARCHAR(100)', 'request_fingerprint': 'VARCHAR(64)'},
    }
    for table, fields in columns.items():
        for name, kind in fields.items():
            async with conn.begin_nested():
                await conn.execute(text(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {name} {kind}'))
    blocked = []
    for name, (table, fields, predicate) in GUARDS.items():
        try:
            async with conn.begin_nested():
                await conn.execute(text(f"CREATE UNIQUE INDEX IF NOT EXISTS {name} ON {table} ({','.join(fields)}) WHERE {predicate}"))
        except Exception as exc:
            from sqlalchemy.exc import IntegrityError
            if not isinstance(exc, IntegrityError):
                raise
            blocked.append(name)
    missing = await missing_guards(conn)
    result = {'ready': not missing, 'missing_guards': missing, 'blocked_indexes': blocked,
        'conflicts': await conflict_report(conn)}
    # Reads remain available, but runtime creation/association refuses while any guard is missing.
    print('应付查重迁移 ' + ('READY' if result['ready'] else 'BLOCKED：新增和关联已关闭，请核对历史冲突') + ' ' + json.dumps(result, ensure_ascii=False, default=str))
    return result
