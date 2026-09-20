"""员工档案 <-> 登录账号 匹配工具。

用于考勤日历、打卡记录等场景：即使员工档案未绑定登录账号，
只要员工手机号==账号用户名 或 姓名==账号显示名（限同一仓库的仓库劳工账号），
也能把打卡记录正确归到员工头上。
"""
from sqlalchemy import select
from app.models.user import User


async def resolve_employee_user_map(db, employees):
    """返回 (emp_to_user, user_to_emp) 两个映射。

    emp_to_user: employee_id -> user_id（该员工对应的打卡账号）
    user_to_emp: user_id -> employee_id（反向，用于把打卡记录归到员工）

    匹配优先级：
      1. 员工档案绑定的账号 (Employee.user_id)
      2. 员工手机号 == 账号用户名
      3. 员工姓名 == 账号显示名
    兜底匹配限定在同一个仓库、角色为仓库劳工。
    """
    emp_to_user: dict[int, int] = {}
    user_to_emp: dict[int, int] = {}
    unbound = []

    for e in employees:
        if e.user_id:
            emp_to_user[e.id] = e.user_id
            user_to_emp[e.user_id] = e.id
        else:
            unbound.append(e)

    if unbound:
        wh_ids = {e.warehouse_id for e in unbound}
        users = (await db.execute(
            select(User).where(
                User.role == "warehouse_labor",
                User.warehouse_id.in_(wh_ids),
            )
        )).scalars().all()

        by_username: dict[tuple, User] = {}
        by_display: dict[tuple, User] = {}
        for u in users:
            by_username.setdefault((u.warehouse_id, u.username), u)
            by_display.setdefault((u.warehouse_id, u.display_name), u)

        for e in unbound:
            uid = None
            if e.phone:
                u = by_username.get((e.warehouse_id, e.phone))
                if u:
                    uid = u.id
            if not uid and e.name:
                u = by_display.get((e.warehouse_id, e.name))
                if u:
                    uid = u.id
            if uid is not None:
                emp_to_user[e.id] = uid
                # 反向映射：一个账号只归属一个员工，且不覆盖已绑定账号
                if uid not in user_to_emp:
                    user_to_emp[uid] = e.id

    return emp_to_user, user_to_emp
