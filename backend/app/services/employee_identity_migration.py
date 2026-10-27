"""Add nullable identity/payment columns without changing any employee row."""
from sqlalchemy import text

COLUMNS = {
    "nationality": "VARCHAR(20)",
    "thai_id_number": "VARCHAR(13)",
    "sso_number": "VARCHAR(50)",
    "bank_account_number": "VARCHAR(100)",
    "bank_name": "VARCHAR(100)",
    "bank_account_holder": "VARCHAR(100)",
}

async def migrate_employee_identity(conn):
    for name, sql_type in COLUMNS.items():
        await conn.execute(text(f"ALTER TABLE employees ADD COLUMN IF NOT EXISTS {name} {sql_type}"))
