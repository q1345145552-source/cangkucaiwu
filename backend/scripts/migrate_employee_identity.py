"""From backend: python -m scripts.migrate_employee_identity. No employee backfill."""
import asyncio
from app.database import _get_engine
from app.services.employee_identity_migration import migrate_employee_identity

async def main():
    engine = _get_engine()
    try:
        async with engine.begin() as conn:
            await migrate_employee_identity(conn)
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
