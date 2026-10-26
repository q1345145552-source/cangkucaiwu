"""One definition of payable identity guards for metadata, migrations and runtime checks."""
import re
from sqlalchemy import inspect

GUARDS = {
    'uq_payable_active_purchase': ('payable_bills', ['purchase_order_id'], "purchase_order_id IS NOT NULL AND COALESCE(status, 'pending') <> 'voided'"),
    'uq_payable_active_invoice': ('payable_bills', ['warehouse_id', 'invoice_identity_key'], "invoice_identity_key IS NOT NULL AND COALESCE(status, 'pending') <> 'voided'"),
    'uq_payable_creation_request': ('payable_bills', ['warehouse_id', 'create_request_key'], 'create_request_key IS NOT NULL'),
    'uq_purchase_creation_request': ('purchase_orders', ['warehouse_id', 'request_key'], 'request_key IS NOT NULL'),
}


def canonical_predicate(value):
    value = re.sub(r'::(?:character varying|text)', '', str(value), flags=re.I)
    return re.sub(r'[\s()]', '', value).lower()


async def missing_guards(conn):
    def read(sync):
        inspector = inspect(sync)
        indexes = {table: inspector.get_indexes(table) for table in ('payable_bills', 'purchase_orders')}
        missing = []
        for name, (table, columns, predicate) in GUARDS.items():
            found = next((i for i in indexes[table] if i['name'] == name), None)
            where = (found or {}).get('dialect_options', {})
            actual = where.get('postgresql_where', where.get('sqlite_where', ''))
            if (not found or not found.get('unique') or found['column_names'] != columns
                    or canonical_predicate(actual) != canonical_predicate(predicate)):
                missing.append(name)
        return missing
    missing = await conn.run_sync(read)
    if conn.dialect.name == 'postgresql':
        from sqlalchemy import text
        valid = set((await conn.execute(text("""SELECT c.relname FROM pg_index i
            JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname=current_schema() AND i.indisvalid AND i.indisready"""))).scalars())
        missing = sorted(set(missing) | (set(GUARDS) - valid))
    return missing
