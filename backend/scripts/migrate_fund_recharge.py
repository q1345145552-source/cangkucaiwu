"""Migration: create fund_recharge_requests table."""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.database import _get_engine
from sqlalchemy import text

async def migrate():
    engine = _get_engine()
    async with engine.begin() as conn:
        r = await conn.execute(text(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='fund_recharge_requests')"
        ))
        exists = r.scalar()
        if exists:
            print("Table fund_recharge_requests already exists, skipping")
            return

        await conn.execute(text("""
            CREATE TABLE fund_recharge_requests (
                id SERIAL PRIMARY KEY,
                fund_id INTEGER NOT NULL REFERENCES expense_funds(id),
                warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
                applicant_id INTEGER NOT NULL REFERENCES users(id),
                amount DOUBLE PRECISION NOT NULL,
                reason VARCHAR(500),
                status VARCHAR(20) DEFAULT 'pending',
                reviewer_id INTEGER REFERENCES users(id),
                review_remark VARCHAR(500),
                reviewed_at TIMESTAMP WITH TIME ZONE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_fund_recharge_requests_fund_id ON fund_recharge_requests(fund_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_fund_recharge_requests_warehouse_id ON fund_recharge_requests(warehouse_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_fund_recharge_requests_status ON fund_recharge_requests(status)"))
        print("Table fund_recharge_requests created successfully")

if __name__ == "__main__":
    asyncio.run(migrate())
