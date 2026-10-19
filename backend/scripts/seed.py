"""Initialize seed data"""
import asyncio, sys
sys.path.insert(0, "/app")
from datetime import datetime, date
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
from app.models.cash_advance import CashAdvance
from app.models.cash_advance_repayment import CashAdvanceRepayment
from app.models.expense_fund import ExpenseFund, ExpenseFundItem, SystemSetting
from app.core.security import hash_password

async def _migrate_audit_ip_location(conn):
    """Add nullable location columns only; never geolocate historical logs."""
    from sqlalchemy import text
    for name, size in (("ip_country", 100), ("ip_region", 150), ("ip_city", 150)):
        try:
            async with conn.begin_nested():
                await conn.execute(text(f"ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS {name} VARCHAR({size})"))
        except Exception as exc:
            print(f"迁移 操作日志地区字段 {name} 失败：{exc}")
            raise

async def _migrate_user_attendance_columns(conn):
    """只加账号身份字段；每列独立保存点，失败不回滚其他启动迁移。"""
    from sqlalchemy import text
    columns = (
        ("attendance_enabled", "ALTER TABLE users ADD COLUMN IF NOT EXISTS attendance_enabled BOOLEAN NOT NULL DEFAULT false"),
        ("attendance_employee_id", "ALTER TABLE users ADD COLUMN IF NOT EXISTS attendance_employee_id INTEGER REFERENCES employees(id) ON DELETE SET NULL"),
        ("attendance_enabled_at", "ALTER TABLE users ADD COLUMN IF NOT EXISTS attendance_enabled_at TIMESTAMPTZ"),
    )
    for name, statement in columns:
        try:
            async with conn.begin_nested():
                await conn.execute(text(statement))
        except Exception as exc:
            print(f"迁移 账号纳入考勤字段 {name} 失败：{exc}")


async def _migrate_makeup_quota_column(conn):
    """旧记录和普通补卡默认计额度；系统故障批量补卡显式设为 false。"""
    from sqlalchemy import text
    try:
        async with conn.begin_nested():
            await conn.execute(text(
                "ALTER TABLE clock_in_records ADD COLUMN IF NOT EXISTS makeup_counts_toward_limit BOOLEAN NOT NULL DEFAULT true"
            ))
    except Exception as exc:
        print(f"迁移 补卡额度字段 makeup_counts_toward_limit 失败：{exc}")
        raise


async def _migrate_makeup_batches(conn):
    """按独立保存点幂等建批次表和关联列；旧补卡不回填批次。"""
    from sqlalchemy import text
    statements = (
        ("clock_in_makeup_batches", """CREATE TABLE IF NOT EXISTS clock_in_makeup_batches (
            id SERIAL PRIMARY KEY,
            warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
            clock_date DATE NOT NULL,
            operator_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            operator_name VARCHAR(100) NOT NULL,
            operated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            reason VARCHAR(500) NOT NULL,
            created_count INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            revoked_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            revoked_by_name VARCHAR(100),
            revoked_at TIMESTAMPTZ
        )"""),
        ("makeup_batch_id", "ALTER TABLE clock_in_records ADD COLUMN IF NOT EXISTS makeup_batch_id INTEGER REFERENCES clock_in_makeup_batches(id)"),
        ("batch_records_index", "CREATE INDEX IF NOT EXISTS ix_clock_in_records_makeup_batch_id ON clock_in_records(makeup_batch_id)"),
        ("batch_history_index", "CREATE INDEX IF NOT EXISTS ix_clock_in_makeup_batches_warehouse_date ON clock_in_makeup_batches(warehouse_id, clock_date)"),
    )
    for name, statement in statements:
        try:
            async with conn.begin_nested():
                await conn.execute(text(statement))
        except Exception as exc:
            print(f"迁移 批量补卡批次 {name} 失败：{exc}")
            raise


async def _migrate_advance_approval_columns(conn):
    """Old advances remain effective; never reset a pending/rejected row on restart."""
    from sqlalchemy import text
    statements = (
        ("approval_status", "ALTER TABLE employee_advances ADD COLUMN IF NOT EXISTS approval_status VARCHAR(20) NOT NULL DEFAULT 'approved'"),
        ("reviewer_id", "ALTER TABLE employee_advances ADD COLUMN IF NOT EXISTS reviewer_id INTEGER REFERENCES users(id) ON DELETE SET NULL"),
        ("reviewed_at", "ALTER TABLE employee_advances ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ"),
        ("reject_reason", "ALTER TABLE employee_advances ADD COLUMN IF NOT EXISTS reject_reason VARCHAR(500)"),
        ("backfill", "UPDATE employee_advances SET approval_status = 'approved' WHERE approval_status IS NULL"),
    )
    for name, statement in statements:
        try:
            async with conn.begin_nested():
                await conn.execute(text(statement))
        except Exception as exc:
            print(f"迁移 预支审批字段 {name} 失败：{exc}")


async def _migrate_employee_advance_expenses(conn):
    """仅加新旧标记和关联列；老预支不补任何支出。"""
    from sqlalchemy import text
    for name, statement in (
        ("expense_tracking_enabled", "ALTER TABLE employee_advances ADD COLUMN IF NOT EXISTS expense_tracking_enabled BOOLEAN NOT NULL DEFAULT false"),
        ("expense_record_id", "ALTER TABLE employee_advances ADD COLUMN IF NOT EXISTS expense_record_id INTEGER REFERENCES expense_records(id)"),
        ("fund_item_id", "ALTER TABLE employee_advances ADD COLUMN IF NOT EXISTS fund_item_id INTEGER REFERENCES expense_fund_items(id)"),
        ("expense_index", "CREATE UNIQUE INDEX IF NOT EXISTS ix_employee_advances_expense_record_id ON employee_advances(expense_record_id)"),
        ("fund_item_index", "CREATE UNIQUE INDEX IF NOT EXISTS ix_employee_advances_fund_item_id ON employee_advances(fund_item_id)"),
    ):
        try:
            async with conn.begin_nested():
                await conn.execute(text(statement))
        except Exception as exc:
            print(f"迁移 员工预支支出关联 {name} 失败：{exc}")
            raise


async def _migrate_employee_advance_funding(conn):
    """仅加可空来源、垫款和付款账户列；不回填任何老数据。"""
    from sqlalchemy import text
    for name, statement in (
        ("funding_source", "ALTER TABLE employee_advances ADD COLUMN IF NOT EXISTS funding_source VARCHAR(20)"),
        ("cash_advance_id", "ALTER TABLE employee_advances ADD COLUMN IF NOT EXISTS cash_advance_id INTEGER REFERENCES cash_advances(id)"),
        ("payment_account_id", "ALTER TABLE employee_advances ADD COLUMN IF NOT EXISTS payment_account_id INTEGER REFERENCES payment_accounts(id)"),
    ):
        try:
            async with conn.begin_nested():
                await conn.execute(text(statement))
        except Exception as exc:
            print(f"迁移 员工预支资金来源 {name} 失败：{exc}")
            raise


async def _migrate_employee_advance_void_columns(conn):
    """仅加可空留痕列；老记录不变，每列独立保存点，可重复运行。"""
    from sqlalchemy import text
    for name, statement in (
        ("voided_by", "ALTER TABLE employee_advances ADD COLUMN IF NOT EXISTS voided_by INTEGER REFERENCES users(id) ON DELETE SET NULL"),
        ("voided_at", "ALTER TABLE employee_advances ADD COLUMN IF NOT EXISTS voided_at TIMESTAMPTZ"),
        ("void_reason", "ALTER TABLE employee_advances ADD COLUMN IF NOT EXISTS void_reason VARCHAR(500)"),
    ):
        try:
            async with conn.begin_nested():
                await conn.execute(text(statement))
        except Exception as exc:
            print(f"迁移 员工预支作废字段 {name} 失败：{exc}")
            raise


async def _migrate_fund_disbursements(conn):
    """老开销保留原口径；新拨付逐笔记账，不回填历史拨付或支出。"""
    from sqlalchemy import text
    statements = (
        ("cost_record_only", "ALTER TABLE expense_fund_items ADD COLUMN IF NOT EXISTS cost_record_only BOOLEAN"),
        ("legacy_item_basis", "UPDATE expense_fund_items SET cost_record_only=false WHERE cost_record_only IS NULL"),
        ("new_item_default", "ALTER TABLE expense_fund_items ALTER COLUMN cost_record_only SET DEFAULT true"),
        ("item_not_null", "ALTER TABLE expense_fund_items ALTER COLUMN cost_record_only SET NOT NULL"),
        ("disbursements", """CREATE TABLE IF NOT EXISTS expense_fund_disbursements (
            id SERIAL PRIMARY KEY, warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
            fund_id INTEGER NOT NULL REFERENCES expense_funds(id),
            amount NUMERIC(14,2) NOT NULL CHECK(amount > 0), currency VARCHAR(5) NOT NULL,
            disbursed_date TIMESTAMP NOT NULL,
            payment_account_id INTEGER NOT NULL REFERENCES payment_accounts(id), account_name VARCHAR(100) NOT NULL,
            expense_record_id INTEGER NOT NULL REFERENCES expense_records(id),
            recharge_request_id INTEGER REFERENCES fund_recharge_requests(id),
            operator_id INTEGER REFERENCES users(id), operator_name VARCHAR(100) NOT NULL,
            remark VARCHAR(500), created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )"""),
        ("expense_unique", "CREATE UNIQUE INDEX IF NOT EXISTS ix_expense_fund_disbursements_expense_record_id ON expense_fund_disbursements(expense_record_id)"),
        ("request_unique", "CREATE UNIQUE INDEX IF NOT EXISTS ix_expense_fund_disbursements_recharge_request_id ON expense_fund_disbursements(recharge_request_id)"),
        ("fund_index", "CREATE INDEX IF NOT EXISTS ix_expense_fund_disbursements_fund_id ON expense_fund_disbursements(fund_id)"),
        ("warehouse_date_index", "CREATE INDEX IF NOT EXISTS ix_fund_disbursements_warehouse_date ON expense_fund_disbursements(warehouse_id,disbursed_date)"),
    )
    for name, statement in statements:
        try:
            async with conn.begin_nested():
                await conn.execute(text(statement))
        except Exception as exc:
            print(f"迁移 备用金拨付 {name} 失败：{exc}")
            raise


async def _migrate_fund_item_void_columns(conn):
    """只加作废留痕三列；不回填或改动旧开销、审核状态和金额。"""
    from sqlalchemy import text
    for name, statement in (
        ("voided_by", "ALTER TABLE expense_fund_items ADD COLUMN IF NOT EXISTS voided_by INTEGER REFERENCES users(id) ON DELETE SET NULL"),
        ("voided_at", "ALTER TABLE expense_fund_items ADD COLUMN IF NOT EXISTS voided_at TIMESTAMPTZ"),
        ("void_reason", "ALTER TABLE expense_fund_items ADD COLUMN IF NOT EXISTS void_reason VARCHAR(500)"),
    ):
        try:
            async with conn.begin_nested():
                await conn.execute(text(statement))
        except Exception as exc:
            print(f"迁移 备用金开销作废字段 {name} 失败：{exc}")
            raise


async def _migrate_payroll_expense_link(conn):
    from sqlalchemy import text
    for name, statement in (
        ("expense_record_id", "ALTER TABLE payroll_records ADD COLUMN IF NOT EXISTS expense_record_id INTEGER REFERENCES expense_records(id)"),
        ("expense_record_index", "CREATE UNIQUE INDEX IF NOT EXISTS ix_payroll_records_expense_record_id ON payroll_records (expense_record_id)"),
    ):
        try:
            async with conn.begin_nested():
                await conn.execute(text(statement))
        except Exception as exc:
            print(f"迁移 工资支出联动字段 {name} 失败：{exc}")


async def _migrate_cash_advances(conn):
    """只建垫款登记表，独立保存点；不回填任何历史财务记录。"""
    from sqlalchemy import text
    statements = (
        ("cash_advances", """CREATE TABLE IF NOT EXISTS cash_advances (
            id SERIAL PRIMARY KEY,
            warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
            payer_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            payer_name VARCHAR(100) NOT NULL,
            advance_date DATE NOT NULL,
            amount NUMERIC(14,2) NOT NULL CONSTRAINT ck_cash_advances_amount CHECK (amount > 0),
            currency VARCHAR(10) NOT NULL DEFAULT 'THB',
            purpose VARCHAR(20) NOT NULL CONSTRAINT ck_cash_advances_purpose CHECK (purpose IN ('salary','purchase','expense','other')),
            description VARCHAR(2000), voucher_path VARCHAR(500),
            status VARCHAR(20) NOT NULL DEFAULT 'pending' CONSTRAINT ck_cash_advances_status CHECK (status IN ('pending','confirmed','rejected','repaid')),
            repaid_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
            created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_by_name VARCHAR(100) NOT NULL, created_at TIMESTAMPTZ NOT NULL,
            reviewed_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            reviewed_by_name VARCHAR(100), reviewed_at TIMESTAMPTZ, reject_reason VARCHAR(500),
            CONSTRAINT ck_cash_advances_repaid CHECK (repaid_amount >= 0 AND repaid_amount <= amount)
        )"""),
        ("cash_advances_index", "CREATE INDEX IF NOT EXISTS ix_cash_advances_warehouse_date ON cash_advances(warehouse_id, advance_date)"),
    )
    for name, statement in statements:
        try:
            async with conn.begin_nested():
                await conn.execute(text(statement))
        except Exception as exc:
            print(f"迁移 垫款单 {name} 失败：{exc}")
            raise


async def _migrate_cash_advance_currency(conn):
    """旧单沿用原系统泰铢口径，金额不转换；新单明确选币种。"""
    from sqlalchemy import text
    try:
        async with conn.begin_nested():
            await conn.execute(text("ALTER TABLE cash_advances ADD COLUMN IF NOT EXISTS currency VARCHAR(10) NOT NULL DEFAULT 'THB'"))
    except Exception as exc:
        print(f"迁移 垫款单币种 失败：{exc}")
        raise


async def _migrate_cash_advance_repayments(conn):
    """仅加归还表和索引，独立保存点，不改账户月初余额或历史成本。"""
    from sqlalchemy import text
    statements = (
        ("cash_advance_repayments", """CREATE TABLE IF NOT EXISTS cash_advance_repayments (
            id SERIAL PRIMARY KEY,
            cash_advance_id INTEGER NOT NULL REFERENCES cash_advances(id),
            warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
            repayment_date DATE NOT NULL,
            amount NUMERIC(14,2) NOT NULL CONSTRAINT ck_cash_repayments_amount CHECK (amount > 0),
            account_id INTEGER NOT NULL REFERENCES payment_accounts(id),
            account_name VARCHAR(100) NOT NULL, currency VARCHAR(10) NOT NULL,
            payment_method VARCHAR(20) NOT NULL CONSTRAINT ck_cash_repayments_method CHECK (payment_method IN ('cash','transfer')),
            voucher_path VARCHAR(500) NOT NULL, description VARCHAR(2000), request_key VARCHAR(64),
            created_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_by_name VARCHAR(100) NOT NULL, created_at TIMESTAMPTZ NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'active' CONSTRAINT ck_cash_repayments_status CHECK (status IN ('active','revoked')),
            revoked_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            revoked_by_name VARCHAR(100), revoked_at TIMESTAMPTZ, revoke_reason VARCHAR(500),
            CONSTRAINT uq_cash_repayment_request UNIQUE (warehouse_id, request_key)
        )"""),
        ("cash_repayments_date_index", "CREATE INDEX IF NOT EXISTS ix_cash_repayments_warehouse_date ON cash_advance_repayments(warehouse_id, repayment_date)"),
        ("cash_repayments_advance_index", "CREATE INDEX IF NOT EXISTS ix_cash_repayments_advance ON cash_advance_repayments(cash_advance_id)"),
        ("cash_repayments_account_index", "CREATE INDEX IF NOT EXISTS ix_cash_repayments_account ON cash_advance_repayments(account_id)"),
    )
    for name, statement in statements:
        try:
            async with conn.begin_nested():
                await conn.execute(text(statement))
        except Exception as exc:
            print(f"迁移 垫款归还 {name} 失败：{exc}")
            raise


async def _migrate_cash_advance_documents(conn):
    """用途关联只加结构，不回填旧垫款或改动任何业务单据。"""
    from sqlalchemy import text
    statements = (
        ("amount_difference_note", "ALTER TABLE cash_advances ADD COLUMN IF NOT EXISTS amount_difference_note VARCHAR(2000)"),
        ("cash_advance_documents", """CREATE TABLE IF NOT EXISTS cash_advance_documents (
            id SERIAL PRIMARY KEY, cash_advance_id INTEGER NOT NULL REFERENCES cash_advances(id),
            warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
            document_type VARCHAR(30) NOT NULL CONSTRAINT ck_cash_advance_document_type
                CHECK (document_type IN ('payroll','payable','reimbursement','employee_advance')),
            document_id INTEGER NOT NULL, document_number VARCHAR(100) NOT NULL,
            title VARCHAR(300) NOT NULL, document_date DATE, amount NUMERIC(14,2) NOT NULL,
            currency VARCHAR(10) NOT NULL,
            CONSTRAINT uq_cash_advance_document UNIQUE(cash_advance_id, document_type, document_id)
        )"""),
        ("documents_index", "CREATE INDEX IF NOT EXISTS ix_cash_advance_documents_advance ON cash_advance_documents(cash_advance_id)"),
    )
    for name, statement in statements:
        try:
            async with conn.begin_nested():
                await conn.execute(text(statement))
        except Exception as exc:
            print(f"迁移 垫款关联单据 {name} 失败：{exc}")
            raise


async def _migrate_payroll_cash_advance_link(conn):
    """只加工资资金来源关联；垫款成本允许没有公司账户，不回填历史单。"""
    from sqlalchemy import text
    for name, statement in (
        ("cash_advance_id", "ALTER TABLE payroll_records ADD COLUMN IF NOT EXISTS cash_advance_id INTEGER REFERENCES cash_advances(id)"),
        ("cash_advance_index", "CREATE INDEX IF NOT EXISTS ix_payroll_records_cash_advance_id ON payroll_records(cash_advance_id)"),
        ("expense_account_nullable", "ALTER TABLE expense_records ALTER COLUMN account_id DROP NOT NULL"),
    ):
        try:
            async with conn.begin_nested():
                await conn.execute(text(statement))
        except Exception as exc:
            print(f"迁移 工资垫款资金来源 {name} 失败：{exc}")
            raise


async def _migrate_reimbursement_payments(conn):
    """仅加付款字段、成本关联及撤销历史；不补历史付款或成本。"""
    from sqlalchemy import text
    statements = [
        ("payment_account_id", "ALTER TABLE reimbursements ADD COLUMN IF NOT EXISTS payment_account_id INTEGER REFERENCES payment_accounts(id)"),
        ("payment_method", "ALTER TABLE reimbursements ADD COLUMN IF NOT EXISTS payment_method VARCHAR(20)"),
        ("payment_voucher_path", "ALTER TABLE reimbursements ADD COLUMN IF NOT EXISTS payment_voucher_path VARCHAR(500)"),
        ("funding_source", "ALTER TABLE reimbursements ADD COLUMN IF NOT EXISTS funding_source VARCHAR(30)"),
        ("cash_advance_id", "ALTER TABLE reimbursements ADD COLUMN IF NOT EXISTS cash_advance_id INTEGER REFERENCES cash_advances(id)"),
        ("expense_record_id", "ALTER TABLE reimbursements ADD COLUMN IF NOT EXISTS expense_record_id INTEGER REFERENCES expense_records(id)"),
        ("expense_index", "CREATE UNIQUE INDEX IF NOT EXISTS ix_reimbursements_expense_record_id ON reimbursements(expense_record_id)"),
        ("advance_index", "CREATE INDEX IF NOT EXISTS ix_reimbursements_cash_advance_id ON reimbursements(cash_advance_id)"),
        ("payment_history", """CREATE TABLE IF NOT EXISTS reimbursement_payments (
            id SERIAL PRIMARY KEY,
            reimbursement_id INTEGER NOT NULL REFERENCES reimbursements(id),
            warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
            amount NUMERIC(14,2) NOT NULL CONSTRAINT ck_reimb_payment_amount CHECK (amount > 0),
            currency VARCHAR(10) NOT NULL,
            funding_source VARCHAR(30) NOT NULL CONSTRAINT ck_reimb_payment_source CHECK (funding_source IN ('company_account','cash_advance','expense_fund')),
            payment_account_id INTEGER REFERENCES payment_accounts(id), account_name VARCHAR(100),
            cash_advance_id INTEGER REFERENCES cash_advances(id), payment_method VARCHAR(20), voucher_path VARCHAR(500),
            expense_record_id INTEGER, previous_status VARCHAR(30) NOT NULL,
            paid_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL, paid_by_name VARCHAR(100) NOT NULL,
            paid_at TIMESTAMPTZ NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'active' CONSTRAINT ck_reimb_payment_status CHECK (status IN ('active','revoked')),
            revoked_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL, revoked_by_name VARCHAR(100),
            revoked_at TIMESTAMPTZ, revoke_reason VARCHAR(500),
            fund_id INTEGER REFERENCES expense_funds(id) ON DELETE SET NULL, fund_item_snapshot JSON
        )"""),
        ("history_date_index", "CREATE INDEX IF NOT EXISTS ix_reimb_payment_warehouse_date ON reimbursement_payments(warehouse_id,paid_at)"),
        ("history_advance_index", "CREATE INDEX IF NOT EXISTS ix_reimb_payment_advance ON reimbursement_payments(cash_advance_id)"),
        ("history_account_index", "CREATE INDEX IF NOT EXISTS ix_reimb_payment_account ON reimbursement_payments(payment_account_id)"),
        ("active_payment_index", "CREATE UNIQUE INDEX IF NOT EXISTS uq_reimb_payment_active ON reimbursement_payments(reimbursement_id) WHERE status='active'"),
    ]
    for name, statement in statements:
        try:
            async with conn.begin_nested():
                await conn.execute(text(statement))
        except Exception as exc:
            print(f"迁移 报销付款 {name} 失败：{exc}")
            raise


async def seed():
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_audit_ip_location(conn)
        await _migrate_user_attendance_columns(conn)
        await _migrate_advance_approval_columns(conn)
        await _migrate_employee_advance_expenses(conn)
        await _migrate_employee_advance_void_columns(conn)
        await _migrate_employee_advance_funding(conn)
        await _migrate_fund_disbursements(conn)
        await _migrate_fund_item_void_columns(conn)
        await _migrate_makeup_quota_column(conn)
        await _migrate_makeup_batches(conn)
        await _migrate_payroll_expense_link(conn)
        await _migrate_cash_advances(conn)
        await _migrate_cash_advance_currency(conn)
        await _migrate_cash_advance_documents(conn)
        await _migrate_cash_advance_repayments(conn)
        await _migrate_payroll_cash_advance_link(conn)
        await _migrate_reimbursement_payments(conn)
        # Migration: add half column to payroll_records if not exists
        from sqlalchemy import text
        try:
            async with conn.begin_nested():
                await conn.execute(text(
                    "ALTER TABLE payroll_records ADD COLUMN IF NOT EXISTS half VARCHAR(10) DEFAULT 'first_half'"
                ))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_payroll_records_half ON payroll_records (half)"
                ))
        except Exception as _e:
            print(f"迁移 工资表half字段 失败：{_e}")
        # Migration: expense_records.voucher 加宽为 TEXT（支持多张凭证 JSON 数组）
        try:
            async with conn.begin_nested():
                await conn.execute(text(
                    "ALTER TABLE expense_records ALTER COLUMN voucher TYPE TEXT"
                ))
        except Exception as _e:
            print(f"迁移 报销凭证voucher加宽 失败：{_e}")
        # Migration: data_change_history 修改历史表（IF NOT EXISTS，幂等）
        try:
            async with conn.begin_nested():
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
        except Exception as _e:
            print(f"迁移 操作历史表data_change_history 失败：{_e}")
        # Migration: 人效管理订单数表（按天，每仓每天一条，可修改）
        try:
            async with conn.begin_nested():
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
        except Exception as _e:
            print(f"迁移 人效订单数表 失败：{_e}")
        # Migration: 员工离职前身份状态（人效时薪估算用）
        try:
            async with conn.begin_nested():
                await conn.execute(text(
                    "ALTER TABLE employees ADD COLUMN IF NOT EXISTS pre_resign_status VARCHAR(20)"
                ))
        except Exception as _e:
            print(f"迁移 员工离职前身份状态 失败：{_e}")
        # Migration: 人效管理手动补录工时表（同一员工同一天一条，可修改）
        try:
            async with conn.begin_nested():
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
        except Exception as _e:
            print(f"迁移 人效手动补录工时表 失败：{_e}")
        # Migration: 耗材采购价格历史表（每次下单每个产品一行）
        try:
            async with conn.begin_nested():
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
        except Exception as _e:
            print(f"迁移 耗材采购价格历史表 失败：{_e}")
        # Migration: 耗材采购价格异常记录表
        try:
            async with conn.begin_nested():
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
        except Exception as _e:
            print(f"迁移 耗材采购价格异常表 失败：{_e}")
        # Migration: 采购单驳回原因字段
        try:
            async with conn.begin_nested():
                await conn.execute(text(
                    "ALTER TABLE purchase_orders ADD COLUMN IF NOT EXISTS reject_reason VARCHAR(500)"
                ))
        except Exception as _e:
            print(f"迁移 采购单驳回原因 失败：{_e}")
        # Migration: 应付账单来源 + 关联采购单
        try:
            async with conn.begin_nested():
                await conn.execute(text(
                    "ALTER TABLE payable_bills ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'manual'"
                ))
                await conn.execute(text(
                    "ALTER TABLE payable_bills ADD COLUMN IF NOT EXISTS purchase_order_id INTEGER"
                ))
                await conn.execute(text(
                    "ALTER TABLE payable_bills ADD COLUMN IF NOT EXISTS need_boss_confirm VARCHAR(5) DEFAULT 'false'"
                ))
        except Exception as _e:
            print(f"迁移 应付账单来源+关联采购单 失败：{_e}")
        # Migration: 应付账单作废字段
        try:
            async with conn.begin_nested():
                await conn.execute(text(
                    "ALTER TABLE payable_bills ADD COLUMN IF NOT EXISTS void_reason VARCHAR(500)"
                ))
                await conn.execute(text(
                    "ALTER TABLE payable_bills ADD COLUMN IF NOT EXISTS voided_by INTEGER"
                ))
                await conn.execute(text(
                    "ALTER TABLE payable_bills ADD COLUMN IF NOT EXISTS voided_at TIMESTAMPTZ"
                ))
        except Exception as _e:
            print(f"迁移 应付账单作废字段 失败：{_e}")
        # Migration: 采购收货验收字段
        try:
            async with conn.begin_nested():
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
        except Exception as _e:
            print(f"迁移 采购收货验收字段 失败：{_e}")
        # Migration: 采购单流程状态 + 发送/回执/发货标记
        try:
            async with conn.begin_nested():
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
        except Exception as _e:
            print(f"迁移 采购单流程状态 失败：{_e}")
        # Migration: 采购单号唯一约束
        try:
            async with conn.begin_nested():
                await conn.execute(text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_purchase_orders_order_number ON purchase_orders (order_number)"
                ))
        except Exception as _e:
            print(f"迁移 采购单号唯一约束 失败：{_e}")
        # Migration: 操作日志仓库归属（仓库隔离用，历史日志为空）
        try:
            async with conn.begin_nested():
                await conn.execute(text(
                    "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS warehouse_id INTEGER"
                ))
                await conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_audit_logs_warehouse_id ON audit_logs (warehouse_id)"
                ))
        except Exception as _e:
            print(f"迁移 操作日志仓库归属 失败：{_e}")
        # Migration: 权限名「收付款管理」→「运营收支」（幂等，一次性数据迁移）
        try:
            async with conn.begin_nested():
                await conn.execute(text("""
                    UPDATE users
                    SET extra_permissions = (
                        SELECT COALESCE(json_agg(CASE WHEN elem = '收付款管理' THEN '运营收支' ELSE elem END), '[]'::json)
                        FROM json_array_elements_text(COALESCE(extra_permissions, '[]'::json)) AS elem
                    )
                    WHERE extra_permissions IS NOT NULL
                      AND extra_permissions::text LIKE '%收付款管理%'
                """))
        except Exception as _e:
            print(f"迁移 权限名收付款管理→运营收支 失败：{_e}")
        # Migration: 主管扩展权限一次性补全（8 个全补，幂等；全局标记确保只跑一次）
        try:
            async with conn.begin_nested():
                migrated = (await conn.execute(text(
                    "SELECT 1 FROM system_settings WHERE key = 'supervisor_perms_backfilled_v1'"
                ))).first()
                if not migrated:
                    await conn.execute(text("""
                        UPDATE users
                        SET extra_permissions = (
                            SELECT COALESCE(json_agg(DISTINCT elem), '[]'::json)
                            FROM (
                                SELECT elem FROM json_array_elements_text(COALESCE(extra_permissions, '[]'::json)) AS elem
                                UNION
                                SELECT unnest(ARRAY['到账流水','备用金管理','报销管理','运营收支','账期管理','操作日志','供应商管理','其他收支']) AS elem
                            ) t
                        )
                        WHERE role = 'supervisor'
                    """))
                    await conn.execute(text("""
                        INSERT INTO system_settings (warehouse_id, key, value)
                        SELECT MIN(id), 'supervisor_perms_backfilled_v1', 'true' FROM warehouses
                    """))
        except Exception as _e:
            print(f"迁移 主管扩展权限补全 失败：{_e}")
        # Migration: 供应商默认币种 + 产品币种 + 币种值统一
        try:
            async with conn.begin_nested():
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
        except Exception as _e:
            print(f"迁移 币种统一 失败：{_e}")

        # Migration: 补全各表模型字段（幂等 ADD COLUMN IF NOT EXISTS，缺哪个补哪个）
        try:
            async with conn.begin_nested():
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
                    ("voided", "BOOLEAN DEFAULT false"),
                    ("voided_by", "INTEGER"),
                    ("voided_at", "TIMESTAMPTZ"),
                    ("void_reason", "VARCHAR(500)"),
                    ("recalc_from_id", "INTEGER"),
                ]
                for _c, _t in payroll_cols:
                    await conn.execute(text(f"ALTER TABLE payroll_records ADD COLUMN IF NOT EXISTS {_c} {_t}"))

                # Migration: 补齐老数据——结算开始日/结束日为空时按周期+半月反推（幂等，只补空的那一侧）
                # 包在保存点（嵌套事务）里：SQL 出错只回滚这一段，不影响前面的建表和加字段
                try:
                    import calendar as _cal
                    async with conn.begin_nested():
                        rows = (await conn.execute(text(
                            "SELECT id, period, half, settle_start_date, settle_end_date "
                            "FROM payroll_records WHERE settle_start_date IS NULL OR settle_end_date IS NULL"
                        ))).all()
                        backfilled = 0
                        for _id, _period, _half, _sd, _ed in rows:
                            try:
                                _y, _m = str(_period).split("-")
                                _year, _month = int(_y), int(_m)
                                _last = _cal.monthrange(_year, _month)[1]
                            except (ValueError, TypeError, AttributeError):
                                continue  # 周期格式不对，跳过
                            if _half == "second_half":
                                _start = date(_year, _month, 16)
                                _end = date(_year, _month, _last)
                            else:
                                _start = date(_year, _month, 1)
                                _end = date(_year, _month, 15)
                            _sets, _params = [], {}
                            if _sd is None:
                                _sets.append("settle_start_date = :sd")
                                _params["sd"] = _start
                            if _ed is None:
                                _sets.append("settle_end_date = :ed")
                                _params["ed"] = _end
                            if _sets:
                                await conn.execute(
                                    text(f"UPDATE payroll_records SET {', '.join(_sets)} WHERE id = :id"),
                                    {**_params, "id": _id},
                                )
                                backfilled += 1
                    print(f"工资单补齐老数据：补了 {backfilled} 条")
                except Exception as _e:
                    print(f"工资单补齐老数据：跳过（{_e}）")

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
                    async with conn.begin_nested():
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
                except Exception as _e:
                    print(f"迁移 红线迁到配置中心 失败：{_e}")

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

                # ── 加班任务/分配表（管理员核实环节）──
                overtime_task_cols = [
                    ("needs_verification", "BOOLEAN DEFAULT false"),
                ]
                for _c, _t in overtime_task_cols:
                    await conn.execute(text(f"ALTER TABLE overtime_tasks ADD COLUMN IF NOT EXISTS {_c} {_t}"))

                overtime_assign_cols = [
                    ("actual_hours", "DOUBLE PRECISION"),
                    ("has_dispute", "BOOLEAN DEFAULT false"),
                    ("dispute_reason", "VARCHAR(500)"),
                    ("dispute_photo", "VARCHAR(500)"),
                    ("dispute_time", "TIMESTAMPTZ"),
                ]
                for _c, _t in overtime_assign_cols:
                    await conn.execute(text(f"ALTER TABLE overtime_assignments ADD COLUMN IF NOT EXISTS {_c} {_t}"))
        except Exception as _e:
            print(f"迁移 补全各表模型字段 失败：{_e}")

        # Migration: 非最低价采购记录表
        try:
            async with conn.begin_nested():
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
        except Exception as _e:
            print(f"迁移 非最低价采购记录表 失败：{_e}")
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

async def initialize():
    # seed() 可能在发现已有管理员时提前返回；补权限必须放在返回之后，
    # 同时覆盖已有数据库和首次初始化生成的账号。
    await seed()
    from app.services.payroll_expense import backfill_payroll_categories
    async with _get_engine().begin() as conn:
        categories = await backfill_payroll_categories(conn)
    print(f"员工工资分类迁移完成，新增分类数：{categories}")
    from app.services.reimbursement_payment import backfill_reimbursement_categories
    async with _get_engine().begin() as conn:
        async with conn.begin_nested():
            reimbursement_categories = await backfill_reimbursement_categories(conn)
    print(f"报销支出分类迁移完成，新增分类数：{reimbursement_categories}")
    from app.services.employee_advance_expense import backfill_advance_categories
    async with _get_engine().begin() as conn:
        async with conn.begin_nested():
            advance_categories = await backfill_advance_categories(conn)
    print(f"员工预支支出分类迁移完成，新增分类数：{advance_categories}")
    from app.services.fund_disbursement import backfill_fund_disbursement_categories
    async with _get_engine().begin() as conn:
        async with conn.begin_nested():
            fund_categories = await backfill_fund_disbursement_categories(conn)
    print(f"备用金拨付支出分类迁移完成，新增分类数：{fund_categories}")
    from app.services.permission_migrations import run_permission_migrations
    async with _get_engine().begin() as conn:
        changed = await run_permission_migrations(conn)
    print(f"菜单权限迁移完成，更新主管/财务账号数：{changed}")


if __name__ == "__main__":
    asyncio.run(initialize())
