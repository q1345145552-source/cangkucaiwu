"""Initialize seed data"""
import asyncio, sys
sys.path.insert(0, "/app")
from datetime import datetime
from app.database import async_session_factory, _get_engine, Base
from app.models.warehouse import Warehouse
from app.models.user import User
from app.models.user_warehouse import UserWarehouse
from app.models.income_expense import IncomeExpenseCategory, IncomeExpenseType
from app.models.customer import Customer
from app.models.supplier import Supplier, PurchaseOrder
from app.models.employee import Employee
from app.models.attendance import LeaveRequest, RestDay, Absence
from app.models.clock_in_records import ClockInRecord
from app.models.overtime import OvertimeTask, OvertimeAssignment
from app.models.payroll import PayrollRecord
from app.models.recharge import RechargeDeclaration, IncomingFlow
from app.models.market import MarketItem
from app.models.credit import CreditCustomer, CreditShipment, CreditRepayment
from app.core.security import hash_password

async def seed():
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Migration: add half column to payroll_records if not exists
        from sqlalchemy import text
        try:
            await conn.execute(text(
                "ALTER TABLE payroll_records ADD COLUMN IF NOT EXISTS half VARCHAR(10) DEFAULT 'first_half'"
            ))
            await conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_payroll_records_half ON payroll_records (half)"
            ))
        except Exception:
            pass
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
        # 初始密码从环境变量读取；未设置则随机生成并打印到日志（不再用弱默认 admin123）
        import os, secrets
        init_pw = os.environ.get("SEED_ADMIN_PASSWORD") or secrets.token_urlsafe(9)
        print("=" * 60)
        print(f"  初始登录密码（所有 seed 账号通用）: {init_pw}")
        print("  请首次登录后立即修改密码！")
        print("=" * 60)
        pw_hash = hash_password(init_pw)

        admin_user = User(username="admin", password_hash=pw_hash,
                          display_name="超级管理员", role="super_admin", warehouse_id=None, is_active=True)
        session.add(admin_user)
        wh_users = []  # (user, warehouse) tuples for UserWarehouse association
        for wh in whs:
            ua = User(username=f"{wh.code.lower()}_admin", password_hash=pw_hash,
                      display_name=f"{wh.name}老板", role="warehouse_admin", warehouse_id=wh.id, is_active=True)
            us = User(username=f"{wh.code.lower()}_staff", password_hash=pw_hash,
                      display_name=f"{wh.name}财务", role="staff", warehouse_id=wh.id, is_active=True)
            session.add(ua); session.add(us)
            wh_users.append((ua, wh)); wh_users.append((us, wh))
        await session.flush()

        # === User-Warehouse Associations ===
        for user, wh in wh_users:
            session.add(UserWarehouse(user_id=user.id, warehouse_id=wh.id))
        await session.flush()

        # === Expense Fund Accounts ===
        from app.models.expense_fund import ExpenseFund
        from datetime import datetime as dt
        # Create account for each warehouse admin and staff
        for wh in whs:
            # Get admin and staff for this warehouse by name pattern
            admin_user = (await session.execute(select(User).where(
                User.warehouse_id == wh.id, User.role == "warehouse_admin"
            ))).scalar_one()
            staff_user = (await session.execute(select(User).where(
                User.warehouse_id == wh.id, User.role == "staff"
            ))).scalar_one()
            session.add(ExpenseFund(
                warehouse_id=wh.id, employee_id=admin_user.id,
                receive_date=dt.utcnow(), amount=0, purpose="",
                remaining_balance=0, fund_limit=5000, alert_threshold=500,
                status="active",
            ))
            session.add(ExpenseFund(
                warehouse_id=wh.id, employee_id=staff_user.id,
                receive_date=dt.utcnow(), amount=0, purpose="",
                remaining_balance=0, fund_limit=5000, alert_threshold=500,
                status="active",
            ))
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

        # === Default Categories ===
        default_categories = [
            "仓储费", "操作费", "增值服务费", "工资", "电费", "网费",
            "房租", "耗材", "物流运费", "快递费", "保险费", "税费",
        ]
        for wh in whs:
            for idx, name in enumerate(default_categories):
                cat_type = IncomeExpenseType.EXPENSE if name != "仓储费" else IncomeExpenseType.INCOME
                # Most are expense types; 仓储费 can be income
                session.add(IncomeExpenseCategory(
                    warehouse_id=wh.id,
                    type="expense",
                    name=name,
                    sort_order=idx + 1,
                    category_group="operating",
                ))
            # Add some "other" categories
            session.add(IncomeExpenseCategory(
                warehouse_id=wh.id, type="income", name="仓储费收入",
                sort_order=1, category_group="other",
            ))
            session.add(IncomeExpenseCategory(
                warehouse_id=wh.id, type="income", name="其他收入",
                sort_order=2, category_group="other",
            ))
        await session.flush()

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
        print("  3 warehouses, 7 users, 6 expense fund accounts")
        print("  5 customers, 3 suppliers")
        print("  2 recharge declarations, 1 incoming flow, 2 market items")

if __name__ == "__main__":
    asyncio.run(seed())
