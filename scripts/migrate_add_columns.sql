-- customers: 新增字段
ALTER TABLE customers ADD COLUMN IF NOT EXISTS line_id VARCHAR(100);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS cargo_type VARCHAR(50);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS logistics_channel VARCHAR(100);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS total_shipments INTEGER DEFAULT 0;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS total_shipping_cost DOUBLE PRECISION DEFAULT 0;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS last_ship_date TIMESTAMP;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS debt_amount DOUBLE PRECISION DEFAULT 0;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS registration_date TIMESTAMP WITH TIME ZONE DEFAULT NOW();
ALTER TABLE customers ADD COLUMN IF NOT EXISTS default_currency VARCHAR(5) DEFAULT 'THB';
ALTER TABLE customers ADD COLUMN IF NOT EXISTS default_payment_method VARCHAR(30);

-- expense_funds: 新增字段
ALTER TABLE expense_funds ADD COLUMN IF NOT EXISTS fund_number VARCHAR(30);
ALTER TABLE expense_funds ADD COLUMN IF NOT EXISTS fund_limit DOUBLE PRECISION DEFAULT 5000;

-- expense_fund_items: 新增字段
ALTER TABLE expense_fund_items ADD COLUMN IF NOT EXISTS currency VARCHAR(5) DEFAULT 'THB';

-- suppliers: 新增字段
ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS category_id INTEGER;
ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS cooperation_content VARCHAR(500);
ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS settlement_cycle VARCHAR(100);
ALTER TABLE suppliers ADD COLUMN IF NOT EXISTS history_notes JSON;
-- payable_bills: 新增字段（大版本升级）
ALTER TABLE payable_bills ADD COLUMN IF NOT EXISTS confirmed_amount DOUBLE PRECISION;
ALTER TABLE payable_bills ADD COLUMN IF NOT EXISTS payment_commitment_days INTEGER;
ALTER TABLE payable_bills ADD COLUMN IF NOT EXISTS payment_voucher VARCHAR(500);
ALTER TABLE payable_bills ADD COLUMN IF NOT EXISTS payment_method VARCHAR(50);
ALTER TABLE payable_bills ADD COLUMN IF NOT EXISTS is_fund_linked VARCHAR(10);
ALTER TABLE payable_bills ADD COLUMN IF NOT EXISTS is_duplicate_warned VARCHAR(10);
ALTER TABLE payable_bills ADD COLUMN IF NOT EXISTS detail VARCHAR(1000);
ALTER TABLE payable_bills ADD COLUMN IF NOT EXISTS bill_attachment VARCHAR(500);
ALTER TABLE payable_bills ADD COLUMN IF NOT EXISTS diff_note VARCHAR(1000);

-- payable_plans: 新增字段
ALTER TABLE payable_plans ADD COLUMN IF NOT EXISTS detail VARCHAR(1000);
ALTER TABLE payable_plans ADD COLUMN IF NOT EXISTS bill_attachment VARCHAR(500);

-- reimbursements: 新增字段
ALTER TABLE reimbursements ADD COLUMN IF NOT EXISTS is_fund_linked VARCHAR(5) DEFAULT '0';
ALTER TABLE reimbursements ADD COLUMN IF NOT EXISTS fund_item_id INTEGER;
