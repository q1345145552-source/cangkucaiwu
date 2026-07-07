"""Migration: add created_by column to warehouses table and backfill data."""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.database import async_session_factory, _get_engine
from sqlalchemy import text

async def migrate():
    engine = _get_engine()
    async with engine.begin() as conn:
        # Check if column exists
        r = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='warehouses' AND column_name='created_by'"
        ))
        if r.scalar_one_or_none():
            print("Column created_by already exists, skipping migration")
        else:
            await conn.execute(text("ALTER TABLE warehouses ADD COLUMN created_by INTEGER REFERENCES users(id)"))
            print("Added created_by column to warehouses")
    
    # Backfill
    factory = async_session_factory()
    async with factory() as session:
        from app.models.warehouse import Warehouse
        from app.models.user_warehouse import UserWarehouse
        from app.models.user import User
        from sqlalchemy import select
        
        whs = (await session.execute(select(Warehouse).where(Warehouse.created_by.is_(None)))).scalars().all()
        if not whs:
            print("No warehouses need backfill")
            return
        
        for wh in whs:
            uw = (await session.execute(
                select(UserWarehouse).join(User, UserWarehouse.user_id == User.id)
                .where(UserWarehouse.warehouse_id == wh.id, User.role == "warehouse_admin")
                .order_by(UserWarehouse.id).limit(1)
            )).scalar_one_or_none()
            if uw:
                wh.created_by = uw.user_id
                print(f"  {wh.name}({wh.id}) -> created_by={uw.user_id}")
        
        await session.commit()
        print(f"Backfilled {len(whs)} warehouses")

if __name__ == "__main__":
    asyncio.run(migrate())
