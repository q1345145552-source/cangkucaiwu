"""Backfill: set created_by for existing warehouses to the first admin who manages it."""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.database import async_session_factory
from app.models.warehouse import Warehouse
from app.models.user_warehouse import UserWarehouse
from app.models.user import User
from sqlalchemy import select

async def fix():
    factory = async_session_factory()
    async with factory() as session:
        whs = (await session.execute(select(Warehouse).where(Warehouse.created_by.is_(None)))).scalars().all()
        if not whs:
            print("All warehouses already have created_by set")
            return
        
        for wh in whs:
            # Find the first warehouse_admin who manages this warehouse
            uw = (await session.execute(
                select(UserWarehouse).join(User, UserWarehouse.user_id == User.id)
                .where(UserWarehouse.warehouse_id == wh.id, User.role == "warehouse_admin")
                .order_by(UserWarehouse.id)
                .limit(1)
            )).scalar_one_or_none()
            if uw:
                wh.created_by = uw.user_id
                print(f"  Warehouse {wh.name}({wh.id}) -> created_by={uw.user_id}")
            else:
                print(f"  Warehouse {wh.name}({wh.id}) -> no admin found, created_by stays NULL")
        
        await session.commit()
        print(f"\nDone: updated {len(whs)} warehouses")

if __name__ == "__main__":
    asyncio.run(fix())
