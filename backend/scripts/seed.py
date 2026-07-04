"""Initialize seed data"""
import asyncio, sys
sys.path.insert(0, "/app")
from app.database import async_session_factory, _get_engine, Base
from app.models.warehouse import Warehouse
from app.models.user import User
from app.core.security import hash_password

async def seed():
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_session_factory()
    async with factory() as session:
        from sqlalchemy import select
        result = await session.execute(select(Warehouse))
        if result.scalars().first():
            print("DB already seeded")
            return
        whs = [
            Warehouse(name="曼谷1仓", name_th="คลังสินค้ากรุงเทพ 1", code="BKK1"),
            Warehouse(name="龙仔1仓", name_th="คลังสินค้าลงจาย 1", code="LZ1"),
            Warehouse(name="龙仔2仓", name_th="คลังสินค้าลงจาย 2", code="LZ2"),
        ]
        session.add_all(whs); await session.flush()
        session.add(User(username="admin", password_hash=hash_password("admin123"),
                          display_name="超级管理员", role="super_admin", warehouse_id=None, is_active=True))
        for wh in whs:
            session.add(User(username=f"{wh.code.lower()}_admin", password_hash=hash_password("admin123"),
                              display_name=f"{wh.name}老板", role="warehouse_admin", warehouse_id=wh.id, is_active=True))
        await session.commit()
        print("Seed complete: admin, bkk1_admin, lz1_admin, lz2_admin")

if __name__ == "__main__":
    asyncio.run(seed())
