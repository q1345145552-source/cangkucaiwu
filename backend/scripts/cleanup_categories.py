"""清理旧收支分类：所有仓库统一只保留 16 个标准分类（幂等）。

流程：
1. 对每个仓库，找出 (type, category_group, name) 不在标准集合里的旧分类；
2. 旧分类若被历史收支记录（income_records / expense_records）引用，
   先把记录改挂到对应的标准分类，再删除；
3. 未被引用的旧分类直接删除；
4. 删除后按标准定义重新规范化 sort_order（每组内 1..N）。

说明：
- 旧数据中「仓储费」「操作费」被错误标成支出；正确的收入版本已在前一次修复中创建，
  因此这里直接删除错误的支出版本，最终每个仓库只保留一个「收入」类型的仓储费/操作费。
- 幂等：重复执行不会产生任何变化。

Run: python scripts/cleanup_categories.py
"""
import asyncio, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select, func, update
from app.database import async_session_factory
from app.models.warehouse import Warehouse
from app.models.income_expense import IncomeExpenseCategory, IncomeRecord, ExpenseRecord
from app.services.default_categories import DEFAULT_CATEGORIES

# 标准 16 项分类的 (type, category_group, name) 集合
STANDARD = {(t, g, n) for (t, g, n) in DEFAULT_CATEGORIES}

# 旧分类 -> 标准分类 映射，仅在旧分类被历史记录引用时用于「改挂」。
# 键值均为 (type, category_group, name)。
OLD_TO_STANDARD = {
    ("expense", "operating", "仓储费"): ("income", "operating", "仓储费"),
    ("expense", "operating", "操作费"): ("income", "operating", "操作费"),
    ("expense", "operating", "增值服务费"): ("expense", "operating", "其他支出"),
    ("expense", "operating", "网费"): ("expense", "operating", "其他支出"),
    ("expense", "operating", "快递费"): ("expense", "operating", "物流运费"),
    ("expense", "operating", "保险费"): ("expense", "operating", "其他支出"),
    ("expense", "operating", "税费"): ("expense", "operating", "其他支出"),
    ("income", "other", "仓储费收入"): ("income", "operating", "仓储费"),
    ("income", "other", "其他收入"): ("income", "other", "杂项收入"),
}


async def cleanup():
    factory = async_session_factory()
    async with factory() as session:
        whs = (await session.execute(select(Warehouse).order_by(Warehouse.id))).scalars().all()
        if not whs:
            print("没有仓库")
            return

        total_deleted = 0
        total_reassigned = 0
        for wh in whs:
            cats = (await session.execute(
                select(IncomeExpenseCategory).where(IncomeExpenseCategory.warehouse_id == wh.id)
            )).scalars().all()

            std_cats = [c for c in cats if (c.type, c.category_group, c.name) in STANDARD]
            std_by_key = {(c.type, c.category_group, c.name): c for c in std_cats}

            deleted_names = []
            for c in cats:
                key = (c.type, c.category_group, c.name)
                if key in STANDARD:
                    continue

                inc_n = (await session.execute(
                    select(func.count()).select_from(IncomeRecord)
                    .where(IncomeRecord.category_id == c.id)
                )).scalar() or 0
                exp_n = (await session.execute(
                    select(func.count()).select_from(ExpenseRecord)
                    .where(ExpenseRecord.category_id == c.id)
                )).scalar() or 0

                ref_total = inc_n + exp_n
                if ref_total > 0:
                    target_key = OLD_TO_STANDARD.get(key)
                    if not target_key:
                        print(f"  ⚠️ 仓库{wh.id} 旧分类「{c.name}」被 {ref_total} 条记录引用但无映射，跳过删除")
                        continue
                    target = std_by_key.get(target_key)
                    if not target:
                        print(f"  ⚠️ 仓库{wh.id} 旧分类「{c.name}」的目标标准分类不存在，跳过删除")
                        continue
                    if inc_n:
                        await session.execute(
                            update(IncomeRecord)
                            .where(IncomeRecord.category_id == c.id)
                            .values(category_id=target.id)
                        )
                    if exp_n:
                        await session.execute(
                            update(ExpenseRecord)
                            .where(ExpenseRecord.category_id == c.id)
                            .values(category_id=target.id)
                        )
                    total_reassigned += ref_total
                    print(f"  ↪ 仓库{wh.id} 「{c.name}」→「{target.name}」改挂 {ref_total} 条")

                await session.delete(c)
                deleted_names.append(f"{c.name}({c.type})")
                total_deleted += 1

            await session.flush()

            # 重新规范化 sort_order：按 DEFAULT_CATEGORIES 顺序，每组内从 1 开始
            group_pos: dict[tuple[str, str], int] = {}
            for t, g, n in DEFAULT_CATEGORIES:
                k = (t, g)
                group_pos[k] = group_pos.get(k, 0) + 1
                for c in std_cats:
                    if (c.type, c.category_group, c.name) == (t, g, n):
                        c.sort_order = group_pos[k]
                        break

            if deleted_names:
                print(f"  仓库 {wh.name}({wh.id}): 删除 {len(deleted_names)} 个旧分类 -> {deleted_names}")
            else:
                print(f"  仓库 {wh.name}({wh.id}): 已是标准分类，无需清理")

        await session.commit()
        print(f"\n完成：删除 {total_deleted} 个旧分类，改挂 {total_reassigned} 条历史记录")


if __name__ == "__main__":
    asyncio.run(cleanup())
