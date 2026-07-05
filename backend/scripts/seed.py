"""Initialize seed data"""
import asyncio, sys
sys.path.insert(0, "/app")
from datetime import datetime
from app.database import async_session_factory, _get_engine, Base
from app.models.warehouse import Warehouse
from app.models.user import User
from app.models.customer import Customer
from app.models.supplier import Supplier
from app.models.recharge import RechargeDeclaration, IncomingFlow
from app.models.market import MarketItem
from app.models.credit import CreditCustomer, CreditShipment, CreditRepayment
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

        # === Warehouses ===
        whs = [
            Warehouse(name="曼谷1仓", name_th="คลังสินค้ากรุงเทพ 1", code="BKK1"),
            Warehouse(name="龙仔1仓", name_th="คลังสินค้าลงจาย 1", code="LZ1"),
            Warehouse(name="龙仔2仓", name_th="คลังสินค้าลงจาย 2", code="LZ2"),
        ]
        session.add_all(whs); await session.flush()

        # === Users ===
        session.add(User(username="admin", password_hash=hash_password("admin123"),
                          display_name="超级管理员", role="super_admin", warehouse_id=None, is_active=True))
        for wh in whs:
            session.add(User(username=f"{wh.code.lower()}_admin", password_hash=hash_password("admin123"),
                              display_name=f"{wh.name}老板", role="warehouse_admin", warehouse_id=wh.id, is_active=True))
            session.add(User(username=f"{wh.code.lower()}_staff", password_hash=hash_password("admin123"),
                              display_name=f"{wh.name}财务", role="staff", warehouse_id=wh.id, is_active=True))
        await session.flush()

        # === Customers ===
        customers = [
            Customer(warehouse_id=1, customer_code="C001", company_name="华泰物流", contact_person="张经理", contact_info="081-234-5678", credit_status=True, credit_limit=100000),
            Customer(warehouse_id=1, customer_code="C002", company_name="顺达贸易", contact_person="李总", contact_info="082-345-6789"),
            Customer(warehouse_id=2, customer_code="C003", company_name="辉煌电商", contact_person="王先生", contact_info="061-456-7890", credit_status=True, credit_limit=50000),
            Customer(warehouse_id=2, customer_code="C004", company_name="泰捷供应链", contact_person="赵小姐", contact_info="062-567-8901"),
            Customer(warehouse_id=3, customer_code="C005", company_name="鑫源国际", contact_person="陈总", contact_info="083-678-9012", credit_status=True, credit_limit=80000),
        ]
        session.add_all(customers); await session.flush()

        # === Suppliers ===
        suppliers = [
            Supplier(warehouse_id=1, name="纸箱王包装", contact_person="林老板", contact_info="089-111-2222"),
            Supplier(warehouse_id=2, name="大象物流设备", contact_person="马经理", contact_info="086-333-4444"),
            Supplier(warehouse_id=3, name="泰丰耗材批发", contact_person="杨先生", contact_info="085-555-6666"),
        ]
        session.add_all(suppliers); await session.flush()

        # === Demo Recharge Declaration ===
        session.add(RechargeDeclaration(
            warehouse_id=1, customer_id=1,
            declare_date=datetime(2026, 7, 4), amount=60000, currency="THB",
            payment_method="bank_transfer", transaction_no="TX20260704",
            declarer_id=2, match_status="unmatched",
        ))
        session.add(RechargeDeclaration(
            warehouse_id=2, customer_id=3,
            declare_date=datetime(2026, 7, 3), amount=35000, currency="THB",
            payment_method="alipay", transaction_no="TX20260703",
            declarer_id=4, match_status="unmatched",
        ))

        # === Demo Incoming Flow ===
        session.add(IncomingFlow(
            warehouse_id=1, received_date=datetime(2026, 7, 4),
            amount=50000, currency="THB", payer_name="华泰物流",
            payment_method="bank_transfer", entrant_id=1, match_status="unmatched",
        ))

        # === Demo Market Items ===
        session.add(MarketItem(
            warehouse_id=1, name="二手纸箱 50个装", quantity=3, price=200,
            description="轻微使用痕迹，适合小件货物打包", uploader_id=2, status="pending",
        ))
        session.add(MarketItem(
            warehouse_id=2, name="9成新叉车托盘", quantity=1, price=5000,
            description="仅使用2个月，承重1.5吨", uploader_id=4, status="pending",
        ))

        await session.commit()
        print("Seed complete:")
        print("  3 warehouses, 7 users")
        print("  5 customers, 3 suppliers")
        print("  2 recharge declarations, 1 incoming flow, 2 market items")

if __name__ == "__main__":
    asyncio.run(seed())
