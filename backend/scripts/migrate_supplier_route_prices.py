"""Add only the independent route-quote table. No legacy updates or pricing conversion.

Explicit local/admin invocation only; this task does not execute it against production.
"""
import asyncio
from app.database import _get_engine
from app.models.supplier import SupplierRoutePrice

async def migrate(connection):
    await connection.run_sync(lambda c:SupplierRoutePrice.__table__.create(c,checkfirst=True))

async def main():
    engine=_get_engine()
    async with engine.begin() as connection:await migrate(connection)
    await engine.dispose()

if __name__=='__main__':asyncio.run(main())
