"""Run explicitly from backend: python -m scripts.migrate_attendance_exemptions."""
import asyncio
from app.database import _get_engine
from app.services.attendance_exemption_migration import migrate_attendance_exemptions

async def main():
    engine = _get_engine()
    try:
        async with engine.begin() as conn:
            await migrate_attendance_exemptions(conn)
    finally:
        await engine.dispose()

if __name__ == '__main__':
    asyncio.run(main())
