"""补数据脚本：为所有仓库补齐默认收支分类（幂等）。

与 create_warehouse 共用同一套默认分类定义（app/services/default_categories.py），
确保「新建仓库自动分类」与「存量仓库补数据」口径一致。

Run: python scripts/fix_categories.py
"""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select, func
from app.database import async_session_factory
from app.models.warehouse import Warehouse
from app.models.income_expense import IncomeExpenseCategory
from app.services.default_categories import ensure_default_categories


async def fix():
    factory = async_session_factory()
    async with factory() as session:
        whs = (await session.execute(select(Warehouse).order_by(Warehouse.id))).scalars().all()
        if not whs:
            print("没有仓库，无需补数据")
            return

        total_created = 0
        for wh in whs:
            before = (await session.execute(
                select(func.count(IncomeExpenseCategory.id)).where(
                    IncomeExpenseCategory.warehouse_id == wh.id
                )
            )).scalar() or 0
            created = await ensure_default_categories(session, wh.id)
            total_created += created
            after = (await session.execute(
                select(func.count(IncomeExpenseCategory.id)).where(
                    IncomeExpenseCategory.warehouse_id == wh.id
                )
            )).scalar() or 0
            print(f"  仓库 {wh.name}({wh.id}): 原有 {before} 个分类，本次新增 {created} 个，现有 {after} 个")

        await session.commit()
        print(f"\n完成：共检查 {len(whs)} 个仓库，新增 {total_created} 个分类")


if __name__ == "__main__":
    asyncio.run(fix())
