"""默认收支分类。

新建仓库与存量仓库补数据共用的唯一默认分类定义，保证两处口径一致。
每个分类由 (type, category_group, name) 三元组唯一标识，幂等补齐。
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.income_expense import IncomeExpenseCategory

# (type, category_group, name)
#   type:           income(收入) / expense(支出)
#   category_group: operating(运营) / other(其他)
DEFAULT_CATEGORIES = [
    # 运营支出
    ("expense", "operating", "工资"),
    ("expense", "operating", "电费"),
    ("expense", "operating", "房租"),
    ("expense", "operating", "耗材"),
    ("expense", "operating", "物流运费"),
    ("expense", "operating", "办公用品"),
    ("expense", "operating", "设备"),
    ("expense", "operating", "保护费"),
    ("expense", "operating", "其他支出"),
    # 运营收入
    ("income", "operating", "仓储费"),
    ("income", "operating", "操作费"),
    # 其他收入
    ("income", "other", "纸壳销售"),
    ("income", "other", "二手设备"),
    ("income", "other", "杂项收入"),
    # 其他支出
    ("expense", "other", "罚款"),
    ("expense", "other", "赔偿"),
]


async def ensure_default_categories(db: AsyncSession, warehouse_id: int) -> int:
    """为指定仓库补齐默认分类（幂等：按 type+category_group+name 去重）。

    返回本次新创建的分类数量。调用方需自行 commit。
    """
    created = 0
    # 每组内独立编号，保证下拉框按定义顺序展示
    group_order: dict[tuple[str, str], int] = {}
    for type_, group, name in DEFAULT_CATEGORIES:
        key = (type_, group)
        group_order[key] = group_order.get(key, 0) + 1

        exists = (await db.execute(
            select(IncomeExpenseCategory.id).where(
                IncomeExpenseCategory.warehouse_id == warehouse_id,
                IncomeExpenseCategory.type == type_,
                IncomeExpenseCategory.category_group == group,
                IncomeExpenseCategory.name == name,
            )
        )).scalar_one_or_none()
        if exists:
            continue

        db.add(IncomeExpenseCategory(
            warehouse_id=warehouse_id,
            type=type_,
            name=name,
            sort_order=group_order[key],
            category_group=group,
            status="active",
        ))
        created += 1

    return created
