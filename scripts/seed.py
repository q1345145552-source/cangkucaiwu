"""初始化种子数据：仓库 + 超级管理员"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.database import Base, _get_engine, async_session_factory
from app.models import Warehouse, User
from app.core.security import hash_password
from app.core.permissions import Role
from sqlalchemy import select

async def seed():
    engine = _get_engine()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_session_factory(engine)
    async with factory() as session:
        result = await session.execute(select(Warehouse))
        if result.scalars().first():
            print("数据库已有数据，跳过种子初始化")
            return

        warehouses = [
            Warehouse(name="曼谷1仓", name_th="คลังสินค้ากรุงเทพ 1", code="BKK1", is_active=True),
            Warehouse(name="龙仔1仓", name_th="คลังสินค้าลงจาย 1", code="LZ1", is_active=True),
            Warehouse(name="龙仔2仓", name_th="คลังสินค้าลงจาย 2", code="LZ2", is_active=True),
        ]
        session.add_all(warehouses)
        await session.flush()

        superadmin = User(
            username="admin",
            password_hash=hash_password("admin123"),
            display_name="超级管理员",
            role=Role.SUPER_ADMIN,
            warehouse_id=None,
            is_active=True,
        )
        session.add(superadmin)

        for wh in warehouses:
            admin = User(
                username=f"{wh.code.lower()}_admin",
                password_hash=hash_password("admin123"),
                display_name=f"{wh.name}老板",
                role=Role.WAREHOUSE_ADMIN,
                warehouse_id=wh.id,
                is_active=True,
            )
            session.add(admin)

        await session.commit()
        print("种子数据初始化完成！")
        print("  超级管理员: admin / admin123")
        print("  曼谷1仓管理员: bkk1_admin / admin123")
        print("  龙仔1仓管理员: lz1_admin / admin123")
        print("  龙仔2仓管理员: lz2_admin / admin123")

if __name__ == "__main__":
    asyncio.run(seed())
