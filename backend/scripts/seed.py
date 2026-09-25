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
from app.models.labor_efficiency import EfficiencyOrderCount
from app.models.employee_advance import EmployeeAdvance
from app.models.salary_template import SalaryTemplate
from app.models.deduction_template import DeductionTemplate
from app.models.employee_deduction import EmployeeDeduction, EmployeeFixedDeduction
from app.models.expense_approval import ExpenseApproval
from app.models.expense_fund import ExpenseFund, ExpenseFundItem, SystemSetting
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
        # Migration: expense_records.voucher 加宽为 TEXT（支持多张凭证 JSON 数组）
        try:
            await conn.execute(text(
                "ALTER TABLE expense_records ALTER COLUMN voucher TYPE TEXT"
            ))
        except Exception:
            pass
        # Migration: data_change_history 修改历史表（IF NOT EXISTS，幂等）
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS data_change_history (
                    id SERIAL PRIMARY KEY,
                    module VARCHAR(50) NOT NULL,
                    record_id INTEGER NOT NULL,
                    operator_id INTEGER REFERENCES users(id),
                    operator_name VARCHAR(100),
                    operation_type VARCHAR(20) NOT NULL,
                    before_data JSON,
                    after_data JSON,
                    warehouse_id INTEGER REFERENCES warehouses(id),
                    created_at TIMESTAMPTZ DEFAULT now()
                )
            """))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_data_change_history_module ON data_change_history (module)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_data_change_history_record_id ON data_change_history (record_id)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_data_change_history_created_at ON data_change_history (created_at)"))
        except Exception:
            pass
        # Migration: 人效管理订单数表（按天，每仓每天一条，可修改）
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS efficiency_daily_orders (
                    id SERIAL PRIMARY KEY,
                    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
                    date DATE NOT NULL,
                    order_count INTEGER NOT NULL DEFAULT 0,
                    updated_by INTEGER REFERENCES users(id),
                    created_at TIMESTAMPTZ DEFAULT now(),
                    updated_at TIMESTAMPTZ,
                    CONSTRAINT uq_efficiency_daily_wh_date UNIQUE (warehouse_id, date)
                )
            """))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_efficiency_daily_orders_wh ON efficiency_daily_orders (warehouse_id)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_efficiency_daily_orders_date ON efficiency_daily_orders (date)"))
        except Exception:
            pass
        # Migration: 员工离职前身份状态（人效时薪估算用）
        try:
            await conn.execute(text(
                "ALTER TABLE employees ADD COLUMN IF NOT EXISTS pre_resign_status VARCHAR(20)"
            ))
        except Exception:
            pass
        # Migration: 人效管理手动补录工时表（同一员工同一天一条，可修改）
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS efficiency_manual_hours (
                    id SERIAL PRIMARY KEY,
                    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
                    employee_id INTEGER NOT NULL REFERENCES employees(id),
                    date DATE NOT NULL,
                    hours DOUBLE PRECISION NOT NULL DEFAULT 0,
                    operator_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMPTZ DEFAULT now(),
                    updated_at TIMESTAMPTZ,
                    CONSTRAINT uq_manual_hours_emp_date UNIQUE (employee_id, date)
                )
            """))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_efficiency_manual_hours_wh ON efficiency_manual_hours (warehouse_id)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_efficiency_manual_hours_emp ON efficiency_manual_hours (employee_id)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_efficiency_manual_hours_date ON efficiency_manual_hours (date)"))
        except Exception:
            pass
        # Migration: 耗材采购价格历史表（每次下单每个产品一行）
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS procurement_price_history (
                    id SERIAL PRIMARY KEY,
                    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
                    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
                    purchase_order_id INTEGER REFERENCES purchase_orders(id),
                    product_name VARCHAR(200) NOT NULL,
                    spec VARCHAR(300),
                    unit_price DOUBLE PRECISION NOT NULL,
                    quantity INTEGER DEFAULT 1,
                    created_by INTEGER REFERENCES users(id),
                    created_at TIMESTAMPTZ DEFAULT now()
                )
            """))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_proc_price_history_wh ON procurement_price_history (warehouse_id)"))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_proc_price_history_prod ON procurement_price_history (product_name, spec)"))
        except Exception:
            pass
        # Migration: 耗材采购价格异常记录表
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS procurement_price_anomalies (
                    id SERIAL PRIMARY KEY,
                    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
                    product_name VARCHAR(200) NOT NULL,
                    spec VARCHAR(300),
                    purchase_price DOUBLE PRECISION NOT NULL,
                    historical_avg DOUBLE PRECISION NOT NULL DEFAULT 0,
                    exceed_percent DOUBLE PRECISION NOT NULL DEFAULT 0,
                    orderer_id INTEGER REFERENCES users(id),
                    orderer_name VARCHAR(100),
                    created_at TIMESTAMPTZ DEFAULT now()
                )
            """))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_proc_price_anomaly_wh ON procurement_price_anomalies (warehouse_id)"))
        except Exception:
            pass
        # Migration: 采购单驳回原因字段
        try:
            await conn.execute(text(
                "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS reject_reason VARCHAR(500)"
            ))
        except Exception:
            pass
        # Migration: 应付账单来源 + 关联采购单
        try:
            await conn.execute(text(
                "ALTER TABLE payable_bills ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'manual'"
            ))
            await conn.execute(text(
                "ALTER TABLE payable_bills ADD COLUMN IF NOT EXISTS purchase_order_id INTEGER"
            ))
            await conn.execute(text(
                "ALTER TABLE payable_bills ADD COLUMN IF NOT EXISTS need_boss_confirm VARCHAR(5) DEFAULT 'false'"
            ))
        except Exception:
            pass
        # Migration: 采购收货验收字段
        try:
            await conn.execute(text(
                "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS receipt_status VARCHAR(20) DEFAULT 'not_received'"
            ))
            await conn.execute(text(
                "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS arrival_photo VARCHAR(500)"
            ))
            await conn.execute(text(
                "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS received_by INTEGER"
            ))
            await conn.execute(text(
                "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS received_at TIMESTAMPTZ"
            ))
        except Exception:
            pass
        # Migration: 采购单流程状态 + 发送/回执/发货标记
        try:
            await conn.execute(text(
                "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS flow_status VARCHAR(30) DEFAULT 'pending_confirmation'"
            ))
            await conn.execute(text(
                "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS sent_at TIMESTAMPTZ"
            ))
            await conn.execute(text(
                "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS sent_by INTEGER"
            ))
            await conn.execute(text(
                "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS receipt_file VARCHAR(500)"
            ))
            await conn.execute(text(
                "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS receipt_uploaded_by INTEGER"
            ))
            await conn.execute(text(
                "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS receipt_uploaded_at TIMESTAMPTZ"
            ))
            await conn.execute(text(
                "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS shipped_at TIMESTAMPTZ"
            ))
            await conn.execute(text(
                "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS shipped_by INTEGER"
            ))
        except Exception:
            pass
        # Migration: 采购单号唯一约束
        try:
            await conn.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_purchase_orders_order_number ON purchase_orders (order_number)"
            ))
        except Exception:
            pass
        # Migration: 供应商默认币种 + 产品币种 + 币种值统一
        try:
            await conn.execute(text(
                "ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS default_currency VARCHAR(10) DEFAULT 'THB'"
            ))
            await conn.execute(text(
                "ALTER TABLE supplier_products ADD COLUMN IF NOT EXISTS currency VARCHAR(10) DEFAULT 'THB'"
            ))
            await conn.execute(text(
                "ALTER TABLE expense_funds ADD COLUMN IF NOT EXISTS currency VARCHAR(5) DEFAULT 'THB'"
            ))
            await conn.execute(text(
                "ALTER TABLE employees ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT false"
            ))
            await conn.execute(text(
                "ALTER TABLE employees ADD COLUMN IF NOT EXISTS deleted_by INTEGER"
            ))
            await conn.execute(text(
                "ALTER TABLE employees ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ"
            ))
            await conn.execute(text(
                "ALTER TABLE clock_in_records ADD COLUMN IF NOT EXISTS is_makeup BOOLEAN DEFAULT false"
            ))
            await conn.execute(text(
                "ALTER TABLE clock_in_records ADD COLUMN IF NOT EXISTS makeup_by INTEGER"
            ))
            await conn.execute(text(
                "ALTER TABLE clock_in_records ADD COLUMN IF NOT EXISTS makeup_at TIMESTAMPTZ"
            ))
            await conn.execute(text(
                "ALTER TABLE clock_in_records ADD COLUMN IF NOT EXISTS makeup_reason VARCHAR(500)"
            ))
            await conn.execute(text(
                "ALTER TABLE leave_requests ADD COLUMN IF NOT EXISTS duration_type VARCHAR(20) DEFAULT 'full'"
            ))
            await conn.execute(text(
                "ALTER TABLE leave_requests ADD COLUMN IF NOT EXISTS hours DOUBLE PRECISION"
            ))
            await conn.execute(text(
                "ALTER TABLE leave_requests ADD COLUMN IF NOT EXISTS notified_at TIMESTAMPTZ"
            ))
            await conn.execute(text(
                "UPDATE supplier_cross_border_prices SET currency = 'CNY' WHERE currency = '人民币'"
            ))
            await conn.execute(text(
                "UPDATE supplier_cross_border_prices SET currency = 'THB' WHERE currency = '泰铢'"
            ))
            await conn.execute(text(
                "UPDATE supplier_products SET currency = 'CNY' WHERE currency = '人民币'"
            ))
            await conn.execute(text(
                "UPDATE supplier_products SET currency = 'THB' WHERE currency = '泰铢'"
            ))
        except Exception:
            pass

        # Migration: 补全各表模型字段（幂等 ADD COLUMN IF NOT EXISTS，缺哪个补哪个）
        try:
            # ── 工资表 payroll_records ──
            await conn.execute(text("ALTER TABLE payroll_records ALTER COLUMN half TYPE VARCHAR(20)"))
            # detail 加宽为 TEXT（存逐天明细/迟到明细，VARCHAR(3000) 可能不够）
            await conn.execute(text("ALTER TABLE payroll_records ALTER COLUMN detail TYPE TEXT"))
            # 出勤/请假/休息/缺勤加宽为 DOUBLE PRECISION（支持半天 0.5）
            for _c in ("attendance_days", "leave_days", "rest_days", "absence_days"):
                await conn.execute(text(f"ALTER TABLE payroll_records ALTER COLUMN {_c} TYPE DOUBLE PRECISION"))
            payroll_cols = [
                ("settle_start_date", "DATE"),
                ("settle_end_date", "DATE"),
                ("disbursed", "BOOLEAN DEFAULT false"),
                ("total_days_in_month", "INTEGER DEFAULT 0"),
                ("attendance_days", "DOUBLE PRECISION DEFAULT 0"),
                ("leave_days", "DOUBLE PRECISION DEFAULT 0"),
                ("rest_days", "DOUBLE PRECISION DEFAULT 0"),
                ("absence_days", "DOUBLE PRECISION DEFAULT 0"),
                ("employee_status", "VARCHAR(20) DEFAULT 'trial'"),
                ("daily_wage", "DOUBLE PRECISION DEFAULT 400"),
                ("base_salary", "DOUBLE PRECISION DEFAULT 12000"),
                ("base_pay", "DOUBLE PRECISION DEFAULT 0"),
                ("overtime_pay", "DOUBLE PRECISION DEFAULT 0"),
                ("overtime_hours", "DOUBLE PRECISION DEFAULT 0"),
                ("late_penalty", "DOUBLE PRECISION DEFAULT 0"),
                ("early_penalty", "DOUBLE PRECISION DEFAULT 0"),
                ("leave_deduction", "DOUBLE PRECISION DEFAULT 0"),
                ("absence_deduction", "DOUBLE PRECISION DEFAULT 0"),
                ("absence_fine", "DOUBLE PRECISION DEFAULT 0"),
                ("fixed_deduction", "DOUBLE PRECISION DEFAULT 0"),
                ("temp_deduction", "DOUBLE PRECISION DEFAULT 0"),
                ("advance_deduction", "DOUBLE PRECISION DEFAULT 0"),
                ("remaining_debt", "DOUBLE PRECISION DEFAULT 0"),
                ("gross_pay", "DOUBLE PRECISION DEFAULT 0"),
                ("total_deductions", "DOUBLE PRECISION DEFAULT 0"),
                ("net_pay", "DOUBLE PRECISION DEFAULT 0"),
                ("detail", "VARCHAR(3000)"),
                ("confirmed_by", "INTEGER"),
                ("confirmed_at", "TIMESTAMPTZ"),
                ("disbursed_by", "INTEGER"),
                ("disbursed_at", "TIMESTAMPTZ"),
                ("signature_path", "VARCHAR(500)"),
                ("created_at", "TIMESTAMPTZ DEFAULT now()"),
                ("updated_at", "TIMESTAMPTZ"),
            ]
            for _c, _t in payroll_cols:
                await conn.execute(text(f"ALTER TABLE payroll_records ADD COLUMN IF NOT EXISTS {_c} {_t}"))

            # ── 打卡记录表 clock_in_records ──
            clock_cols = [
                ("warehouse_id", "INTEGER"),
                ("clock_date", "DATE"),
                ("session", "INTEGER DEFAULT 1"),
                ("clocked_in_at", "TIMESTAMPTZ DEFAULT now()"),
                ("photo_path", "VARCHAR(500)"),
                ("status", "VARCHAR(20) DEFAULT 'normal'"),
                ("penalty_amount", "DOUBLE PRECISION DEFAULT 0"),
                ("remark", "VARCHAR(200)"),
            ]
            for _c, _t in clock_cols:
                await conn.execute(text(f"ALTER TABLE clock_in_records ADD COLUMN IF NOT EXISTS {_c} {_t}"))

            # ── 员工表 employees ──
            emp_cols = [
                ("position", "VARCHAR(50) DEFAULT '仓库劳工'"),
                ("myanmar_id", "VARCHAR(50)"),
                ("address", "VARCHAR(300)"),
                ("phone", "VARCHAR(50)"),
                ("emergency_contact", "VARCHAR(100)"),
                ("hire_date", "TIMESTAMPTZ"),
                ("status", "VARCHAR(20) DEFAULT 'trial'"),
                ("daily_wage", "DOUBLE PRECISION DEFAULT 400"),
                ("base_salary", "DOUBLE PRECISION DEFAULT 12000"),
                ("remark", "VARCHAR(500)"),
                ("photo_path", "VARCHAR(500)"),
                ("passport_photo_path", "VARCHAR(500)"),
                ("work_permit_photo_path", "VARCHAR(500)"),
                ("passport_number", "VARCHAR(50)"),
                ("work_permit_number", "VARCHAR(50)"),
                ("passport_expiry", "DATE"),
                ("work_permit_expiry", "DATE"),
                ("promotion_date", "DATE"),
                ("tags", "TEXT"),
                ("user_id", "INTEGER"),
                ("salary_template_id", "INTEGER"),
                ("deduction_template_id", "INTEGER"),
                ("resignation_date", "DATE"),
                ("resignation_reason", "VARCHAR(50)"),
                ("resignation_note", "VARCHAR(500)"),
                ("blacklisted", "BOOLEAN DEFAULT false"),
                ("blacklist_reason", "VARCHAR(500)"),
                ("created_by", "INTEGER"),
                ("created_at", "TIMESTAMPTZ DEFAULT now()"),
                ("updated_at", "TIMESTAMPTZ"),
            ]
            for _c, _t in emp_cols:
                await conn.execute(text(f"ALTER TABLE employees ADD COLUMN IF NOT EXISTS {_c} {_t}"))

            # ── 扣款模板表 deduction_templates：早退/迟到红线时间（列保留，ORM 不再映射） ──
            await conn.execute(text("ALTER TABLE deduction_templates ADD COLUMN IF NOT EXISTS early_half_threshold VARCHAR(5) DEFAULT '17:30'"))
            await conn.execute(text("ALTER TABLE deduction_templates ADD COLUMN IF NOT EXISTS early_one_threshold VARCHAR(5) DEFAULT '17:00'"))
            await conn.execute(text("ALTER TABLE deduction_templates ADD COLUMN IF NOT EXISTS late_half_threshold VARCHAR(5) DEFAULT '09:05'"))
            await conn.execute(text("ALTER TABLE deduction_templates ADD COLUMN IF NOT EXISTS late_one_threshold VARCHAR(5) DEFAULT '09:31'"))

            # ── 迁移：四个红线迁到配置中心 SystemSetting（每仓取第一个扣款模板，幂等） ──
            try:
                tpl_rows = await conn.execute(text("""
                    SELECT DISTINCT ON (warehouse_id)
                           warehouse_id, late_half_threshold, late_one_threshold,
                           early_half_threshold, early_one_threshold
                    FROM deduction_templates
                    ORDER BY warehouse_id, created_at ASC, id ASC
                """))
                for wh_id, lh, lo, eh, eo in tpl_rows.all():
                    for key, val in (
                        ("schedule_late_half", lh),
                        ("schedule_late_one", lo),
                        ("schedule_early_half", eh),
                        ("schedule_early_one", eo),
                    ):
                        if val:
                            await conn.execute(text("""
                                INSERT INTO system_settings (warehouse_id, key, value)
                                SELECT CAST(:wh AS INTEGER), CAST(:key AS VARCHAR), CAST(:val AS VARCHAR)
                                WHERE NOT EXISTS (
                                    SELECT 1 FROM system_settings WHERE warehouse_id = CAST(:wh AS INTEGER) AND key = CAST(:key AS VARCHAR)
                                )
                            """), {"wh": wh_id, "key": key, "val": val})
            except Exception:
                pass

            # ── 报销表 reimbursements / reimbursement_items ──
            reimb_cols = [
                ("submit_date", "TIMESTAMPTZ"),
                ("total_amount", "DOUBLE PRECISION DEFAULT 0"),
                ("currency", "VARCHAR(5) DEFAULT 'THB'"),
                ("status", "VARCHAR(30) DEFAULT 'pending'"),
                ("reviewer_id", "INTEGER"),
                ("review_remark", "VARCHAR(500)"),
                ("paid_at", "TIMESTAMPTZ"),
                ("payment_method", "VARCHAR(20)"),
                ("is_fund_linked", "VARCHAR(5) DEFAULT '0'"),
                ("fund_item_id", "INTEGER"),
                ("created_at", "TIMESTAMPTZ DEFAULT now()"),
            ]
            for _c, _t in reimb_cols:
                await conn.execute(text(f"ALTER TABLE reimbursements ADD COLUMN IF NOT EXISTS {_c} {_t}"))

            reimb_item_cols = [
                ("category", "VARCHAR(100)"),
                ("amount", "DOUBLE PRECISION DEFAULT 0"),
                ("description", "VARCHAR(500)"),
                ("receipt", "VARCHAR(500)"),
                ("review_status", "VARCHAR(20) DEFAULT 'pending'"),
                ("created_at", "TIMESTAMPTZ DEFAULT now()"),
            ]
            for _c, _t in reimb_item_cols:
                await conn.execute(text(f"ALTER TABLE reimbursement_items ADD COLUMN IF NOT EXISTS {_c} {_t}"))

            # ── 备用金表 expense_funds / expense_fund_items ──
            fund_cols = [
                ("fund_number", "VARCHAR(30)"),
                ("receive_date", "TIMESTAMPTZ"),
                ("amount", "DOUBLE PRECISION DEFAULT 0"),
                ("purpose", "VARCHAR(500)"),
                ("expected_return_date", "TIMESTAMPTZ"),
                ("status", "VARCHAR(30) DEFAULT 'active'"),
                ("remaining_balance", "DOUBLE PRECISION DEFAULT 0"),
                ("fund_limit", "DOUBLE PRECISION DEFAULT 5000"),
                ("alert_threshold", "DOUBLE PRECISION DEFAULT 500"),
                ("created_at", "TIMESTAMPTZ DEFAULT now()"),
            ]
            for _c, _t in fund_cols:
                await conn.execute(text(f"ALTER TABLE expense_funds ADD COLUMN IF NOT EXISTS {_c} {_t}"))

            fund_item_cols = [
                ("expense_date", "TIMESTAMPTZ"),
                ("category", "VARCHAR(100)"),
                ("amount", "DOUBLE PRECISION DEFAULT 0"),
                ("currency", "VARCHAR(5) DEFAULT 'THB'"),
                ("description", "VARCHAR(500)"),
                ("receipt", "VARCHAR(500)"),
                ("review_status", "VARCHAR(20) DEFAULT 'pending'"),
                ("review_remark", "VARCHAR(500)"),
                ("review_action", "VARCHAR(20)"),
                ("created_at", "TIMESTAMPTZ DEFAULT now()"),
            ]
            for _c, _t in fund_item_cols:
                await conn.execute(text(f"ALTER TABLE expense_fund_items ADD COLUMN IF NOT EXISTS {_c} {_t}"))

            # ── 应付账款表 payable_bills / payable_plans ──
            bill_cols = [
                ("bill_number", "VARCHAR(50)"),
                ("bill_date", "TIMESTAMPTZ"),
                ("due_date", "TIMESTAMPTZ"),
                ("amount", "DOUBLE PRECISION DEFAULT 0"),
                ("currency", "VARCHAR(5) DEFAULT 'THB'"),
                ("paid_amount", "DOUBLE PRECISION DEFAULT 0"),
                ("status", "VARCHAR(30) DEFAULT 'pending'"),
                ("confirmed_amount", "DOUBLE PRECISION"),
                ("payment_commitment_days", "INTEGER"),
                ("payment_voucher", "VARCHAR(500)"),
                ("payment_method", "VARCHAR(50)"),
                ("is_fund_linked", "VARCHAR(10)"),
                ("is_duplicate_warned", "VARCHAR(10)"),
                ("detail", "VARCHAR(1000)"),
                ("bill_attachment", "VARCHAR(500)"),
                ("remark", "VARCHAR(500)"),
                ("voucher", "VARCHAR(500)"),
                ("diff_note", "VARCHAR(1000)"),
                ("paid_at", "TIMESTAMPTZ"),
                ("created_by", "INTEGER"),
                ("created_at", "TIMESTAMPTZ DEFAULT now()"),
            ]
            for _c, _t in bill_cols:
                await conn.execute(text(f"ALTER TABLE payable_bills ADD COLUMN IF NOT EXISTS {_c} {_t}"))

            plan_cols = [
                ("plan_name", "VARCHAR(200)"),
                ("planned_date", "TIMESTAMPTZ"),
                ("total_amount", "DOUBLE PRECISION DEFAULT 0"),
                ("status", "VARCHAR(20) DEFAULT 'pending'"),
                ("bill_ids", "JSON"),
                ("detail", "VARCHAR(1000)"),
                ("bill_attachment", "VARCHAR(500)"),
                ("remark", "VARCHAR(500)"),
                ("created_by", "INTEGER"),
                ("created_at", "TIMESTAMPTZ DEFAULT now()"),
            ]
            for _c, _t in plan_cols:
                await conn.execute(text(f"ALTER TABLE payable_plans ADD COLUMN IF NOT EXISTS {_c} {_t}"))
        except Exception:
            pass

        # Migration: 非最低价采购记录表
        try:
            await conn.execute(text("""
                CREATE TABLE IF NOT EXISTS procurement_non_lowest_records (
                    id SERIAL PRIMARY KEY,
                    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
                    product_name VARCHAR(200) NOT NULL,
                    spec VARCHAR(300),
                    selected_supplier_id INTEGER REFERENCES suppliers(id),
                    selected_supplier_name VARCHAR(200),
                    selected_price DOUBLE PRECISION NOT NULL,
                    lowest_supplier_id INTEGER REFERENCES suppliers(id),
                    lowest_supplier_name VARCHAR(200),
                    lowest_price DOUBLE PRECISION NOT NULL DEFAULT 0,
                    price_diff DOUBLE PRECISION NOT NULL DEFAULT 0,
                    quantity INTEGER DEFAULT 1,
                    reason VARCHAR(500),
                    orderer_id INTEGER REFERENCES users(id),
                    orderer_name VARCHAR(100),
                    created_at TIMESTAMPTZ DEFAULT now()
                )
            """))
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_proc_non_lowest_wh ON procurement_non_lowest_records (warehouse_id)"))
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
