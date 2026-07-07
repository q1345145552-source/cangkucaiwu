"""Fix script: backfill UserWarehouse association records for existing users.
Run: python scripts/fix_user_warehouses.py"""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.database import async_session_factory
from app.models.user import User
from app.models.user_warehouse import UserWarehouse
from sqlalchemy import select

async def fix():
    factory = async_session_factory()
    async with factory() as session:
        # Find all users with warehouse_id who don't have UserWarehouse record
        result = await session.execute(
            select(User).where(User.warehouse_id.isnot(None))
        )
        users = result.scalars().all()
        
        created = 0
        skipped = 0
        for user in users:
            # Check if association already exists
            existing = await session.execute(
                select(UserWarehouse).where(
                    UserWarehouse.user_id == user.id,
                    UserWarehouse.warehouse_id == user.warehouse_id,
                )
            )
            if existing.scalar_one_or_none():
                skipped += 1
                continue
            session.add(UserWarehouse(user_id=user.id, warehouse_id=user.warehouse_id))
            created += 1
            print(f"  + UserWarehouse: user={user.username}({user.id}) -> warehouse={user.warehouse_id}")
        
        await session.commit()
        print(f"\nDone: {created} created, {skipped} already existed, {len(users)} total users with warehouse_id")

if __name__ == "__main__":
    asyncio.run(fix())
