"""Additive migration only: no attendance/payroll updates or backfills."""
from sqlalchemy import text

async def migrate_attendance_exemptions(conn):
    await conn.execute(text('''CREATE TABLE IF NOT EXISTS attendance_exemptions (
        id SERIAL PRIMARY KEY, warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
        date DATE NOT NULL, reason VARCHAR(500) NOT NULL,
        created_by INTEGER NOT NULL REFERENCES users(id), created_by_name VARCHAR(100) NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(), status VARCHAR(20) NOT NULL DEFAULT 'active',
        revoked_by INTEGER REFERENCES users(id), revoked_by_name VARCHAR(100),
        revoked_at TIMESTAMPTZ, revoke_reason VARCHAR(500)
    )'''))
    await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_attendance_exemption_active ON attendance_exemptions(warehouse_id,date) WHERE status = 'active'"))
