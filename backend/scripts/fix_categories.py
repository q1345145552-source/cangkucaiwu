"""Fix script: backfill default categories for existing warehouses.
Run: python scripts/fix_categories.py"""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.database import async_session_factory
from app.models.warehouse import Warehouse
from app.models.income_expense import IncomeExpenseCategory
from sqlalchemy import select, func

DEFAULT_CATEGORIES = [
    "仓储费", "操作费", "增值服务费", "工资", "电费", "网费",
    "房租", "耗材", "物流运费", "快递费", "保险费", "税费",
]

async def fix():
    factory = async_session_factory()
    async with factory() as session:
        whs = (await session.execute(select(Warehouse))).scalars().all()
        total_created = 0
        for wh in whs:
            # Check if this warehouse already has categories
            count = (await session.execute(
                select(func.count(IncomeExpenseCategory.id)).where(
                    IncomeExpenseCategory.warehouse_id == wh.id
                )
            )).scalar()
            if count > 0:
                print(f"  Warehouse {wh.name}({wh.id}): {count} categories exist, skipping")
                continue
            
            for idx, name in enumerate(DEFAULT_CATEGORIES):
                session.add(IncomeExpenseCategory(
                    warehouse_id=wh.id, type="expense", name=name,
                    sort_order=idx + 1, category_group="operating",
                ))
            session.add(IncomeExpenseCategory(
                warehouse_id=wh.id, type="income", name="仓储费收入",
                sort_order=1, category_group="other",
            ))
            session.add(IncomeExpenseCategory(
                warehouse_id=wh.id, type="income", name="其他收入",
                sort_order=2, category_group="other",
            ))
            total_created += len(DEFAULT_CATEGORIES) + 2
            print(f"  Warehouse {wh.name}({wh.id}): created {len(DEFAULT_CATEGORIES) + 2} categories")
        
        await session.commit()
        print(f"\nDone: {total_created} categories created across {len(whs)} warehouses")

if __name__ == "__main__":
    asyncio.run(fix())
