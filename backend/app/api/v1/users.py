from app.core.action_access import encode_permissions, convert_legacy, permission_state, access_description, legacy_labels
from types import SimpleNamespace
from app.core.round2_access import require_account_manager, mutation_scope, own_scope, login_target_scope
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.employee import Employee
from app.models.user import User
from app.models.user_warehouse import UserWarehouse
from app.models.warehouse import Warehouse
from app.core.security import hash_password
from app.core.permissions import get_current_user, require_role, Role, ROLE_HIERARCHY, check_staff_permission, require_non_labor
from app.core.menu_registry import MENU_PERMISSIONS, MENU_PERMISSIONS_BY_KEY
from app.schemas.user import UserCreate, UserUpdate, UserResponse
from app.services.data_history import record_history
from app.services.attendance_identity import bind_attendance_employee

router = APIRouter()


def prepared_permissions(req, role, target=None):
    if req.action_permissions is not None:
        if req.extra_permissions is not None:
            raise HTTPException(400, '不能同时提交旧菜单和新动作权限')
        if not req.permission_reason or not req.permission_reason.strip():
            raise HTTPException(400, '请填写权限调整原因')
        return encode_permissions(role, req.action_permissions)
    if req.extra_permissions is not None:
        if target is not None and permission_state(target)['version'] != 'legacy':
            raise HTTPException(409, '该账号已使用三档权限，请刷新权限编辑页；不能回退旧菜单授权')
        old = SimpleNamespace(role=role, extra_permissions=req.extra_permissions)
        converted, state = convert_legacy(old)
        if state['unknown']:
            raise HTTPException(400, '包含未识别的旧菜单权限，请先核对')
        return converted
    return encode_permissions(role, []) if target is None else target.extra_permissions



def _attendance_fields(user: User) -> dict:
    return {
        "attendance_enabled": bool(user.attendance_enabled),
        "attendance_employee_id": user.attendance_employee_id,
        "attendance_enabled_at": user.attendance_enabled_at.isoformat() if user.attendance_enabled_at else None,
    }


@router.get("", response_model=dict, dependencies=[Depends(require_non_labor)])
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: str | None = None,
    warehouse_id: int | None = None,
    current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["settings"].label)),
    db: AsyncSession = Depends(get_db),
):
    query = select(User).options(selectinload(User.warehouse))
    count_query = select(func.count(User.id))

    # Non-superadmin can only see users in warehouses they manage
    if current_user.role != Role.SUPER_ADMIN:
        managed_wh_ids = (await db.execute(
            select(UserWarehouse.warehouse_id).where(UserWarehouse.user_id == current_user.id)
        )).scalars().all()
        managed_wh_ids = list(managed_wh_ids) if managed_wh_ids else []
        if managed_wh_ids:
            # supervisor only sees staff/labor; warehouse_admin sees staff/labor/supervisor (+self)
            if current_user.role == Role.SUPERVISOR:
                role_filter = User.role.in_((Role.STAFF, Role.WAREHOUSE_LABOR))
            else:
                role_filter = (User.role != Role.WAREHOUSE_ADMIN)
            query = query.where(
                (User.warehouse_id.in_(managed_wh_ids) & role_filter)
                | (User.id == current_user.id)
            )
            count_query = count_query.where(
                (User.warehouse_id.in_(managed_wh_ids) & role_filter)
                | (User.id == current_user.id)
            )
        else:
            # New warehouse_admin with no warehouses yet - show only self
            query = query.where(User.id == current_user.id)
            count_query = count_query.where(User.id == current_user.id)

    if role:
        query = query.where(User.role == role)
        count_query = count_query.where(User.role == role)
    if warehouse_id and current_user.role == Role.SUPER_ADMIN:
        query = query.where(User.warehouse_id == warehouse_id)
        count_query = count_query.where(User.warehouse_id == warehouse_id)

    total = (await db.execute(count_query)).scalar()
    result = await db.execute(
        query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    users = result.scalars().all()

    # 批量取每个用户的多仓分配
    uids = [u.id for u in users]
    uw_map: dict[int, list[int]] = {uid: [] for uid in uids}
    if uids:
        uw_rows = (await db.execute(
            select(UserWarehouse).where(UserWarehouse.user_id.in_(uids))
        )).scalars().all()
        for uw in uw_rows:
            uw_map.setdefault(uw.user_id, []).append(uw.warehouse_id)

    return {
        "data": [
            {
                "id": u.id, "username": u.username, "display_name": u.display_name,
                "role": u.role,
                "warehouse_id": u.warehouse_id,
                "warehouse_ids": uw_map.get(u.id, []),
                "warehouse_name": u.warehouse.name if u.warehouse else None,
                "extra_permissions": legacy_labels(u),
                "action_access": access_description(u),
                **_attendance_fields(u),
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None,
            }
            for u in users
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }

@router.get("/permissions")
async def list_available_permissions(current_user: User = Depends(get_current_user)):
    """完整菜单权限清单；原八项 key/label 保持中文值以兼容老账号。"""
    return [item.as_dict() for item in MENU_PERMISSIONS]

@router.post("", dependencies=[Depends(mutation_scope)])
async def create_user(
    req: UserCreate,
    current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["settings"].label)),
    db: AsyncSession = Depends(get_db),
):
    require_account_manager(current_user, platform=True)
    # Role hierarchy check: can only create users with lower role
    from app.core.permissions import ROLE_HIERARCHY
    if ROLE_HIERARCHY.get(current_user.role, 0) <= ROLE_HIERARCHY.get(req.role, 0):
        raise HTTPException(status_code=403, detail="无法创建同级别或更高级别用户")

    # Check username uniqueness
    existing = (await db.execute(select(User).where(User.username == req.username))).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")

    # 确定分配到的仓库列表：多仓 warehouse_ids 优先，其次单仓 warehouse_id
    # 所有角色走同一套逻辑：传了仓库列表就按传的来，没传就是空
    if req.warehouse_ids:
        warehouse_ids = list(req.warehouse_ids)
    elif req.warehouse_id is not None:
        warehouse_ids = [req.warehouse_id]
    else:
        warehouse_ids = []

    # 非超管：校验每个仓库都在自己管理范围内
    if current_user.role != Role.SUPER_ADMIN:
        managed = (await db.execute(
            select(UserWarehouse.warehouse_id).where(UserWarehouse.user_id == current_user.id)
        )).scalars().all()
        managed = list(managed) if managed else []
        for wid in warehouse_ids:
            if wid not in managed:
                raise HTTPException(status_code=403, detail="无权限将用户分配到该仓库")
        if not warehouse_ids:
            fallback = current_user.warehouse_id or (managed[0] if managed else None)
            if fallback:
                warehouse_ids = [fallback]

    # staff / supervisor MUST have at least one warehouse
    if req.role in (Role.STAFF, Role.SUPERVISOR) and not warehouse_ids:
        raise HTTPException(status_code=400, detail="创建该角色用户时必须指定所属仓库")

    if req.role == Role.SUPERVISOR and len(set(warehouse_ids)) > 1:
        raise HTTPException(status_code=400, detail="主管只能分配一个仓库")

    for wid in warehouse_ids:
        own_scope(current_user, wid)
    primary_wh = warehouse_ids[0] if warehouse_ids else None
    req.warehouse_id = primary_wh

    user = User(
        username=req.username,
        password_hash=hash_password(req.password),
        display_name=req.display_name,
        role=req.role,
        warehouse_id=primary_wh,
        created_by=current_user.id,
        extra_permissions=prepared_permissions(req, req.role),
    )
    db.add(user)
    await db.flush()

    for wid in warehouse_ids:
        db.add(UserWarehouse(user_id=user.id, warehouse_id=wid))
    await db.flush()

    await record_history(db, module="user", record_id=user.id, operator=current_user,
                          operation_type="create",
                          after={"username": user.username, "display_name": user.display_name,
                                 "role": user.role, "warehouse_ids": warehouse_ids,
                                 "permissions": user.extra_permissions, "permission_source_version": 1,
                                 "legacy_source": req.extra_permissions,
                                 "permission_reason": req.permission_reason or "新建账号：旧菜单保守转换或最小权限"},
                          warehouse_id=primary_wh)

    return {"id": user.id, "message": "用户创建成功"}

@router.put("/{user_id}", dependencies=[Depends(mutation_scope)])
async def update_user(
    user_id: int,
    req: UserUpdate,
    current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["settings"].label)),
    db: AsyncSession = Depends(get_db),
):
    require_account_manager(current_user, platform=True)
    result = await db.execute(select(User).where(User.id == user_id).with_for_update())
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    own_scope(current_user, user.warehouse_id)
    # 权限：只能编辑比自己级别低的角色
    # - 超管：可编辑除超管外的所有角色
    # - 管理员：可编辑主管/财务/劳工（限自己仓库），不能改角色
    # - 主管/财务/劳工：无编辑权限
    if current_user.role in (Role.STAFF, Role.WAREHOUSE_LABOR, Role.SUPERVISOR):
        raise HTTPException(status_code=403, detail="无权限编辑用户")
    # 身份开关不适用于管理员/超管；本人仅提交该开关时成功忽略，
    # 不放开既有的同级编辑、角色、密码或仓库修改权限。
    if (current_user.id == user_id
            and req.model_fields_set == {"attendance_enabled"}):
        return {"message": "用户更新成功", **_attendance_fields(user)}
    if ROLE_HIERARCHY.get(user.role, 0) >= ROLE_HIERARCHY.get(current_user.role, 0):
        raise HTTPException(status_code=403, detail="只能编辑比自己级别低的角色")
    if current_user.role == Role.WAREHOUSE_ADMIN:
        # 只能编辑自己仓库的用户
        managed_wh_ids = (await db.execute(
            select(UserWarehouse.warehouse_id).where(UserWarehouse.user_id == current_user.id)
        )).scalars().all()
        managed_wh_ids = [w for w in managed_wh_ids] if managed_wh_ids else []
        if not managed_wh_ids or user.warehouse_id not in managed_wh_ids:
            raise HTTPException(status_code=403, detail="只能编辑自己仓库的用户")
        # 角色不能改
        if req.role is not None and req.role != user.role:
            raise HTTPException(status_code=403, detail="无权修改用户角色")

    await login_target_scope(db, current_user, user)
    # Grandfather an existing multi-warehouse supervisor only when warehouse
    # assignment is omitted. A role conversion must validate the retained scope.
    if (req.role or user.role) == Role.SUPERVISOR:
        warehouses_changed = req.warehouse_ids is not None or req.warehouse_id is not None
        becoming_supervisor = req.role is not None and user.role != Role.SUPERVISOR
        if warehouses_changed or becoming_supervisor:
            if req.warehouse_ids is not None:
                supervisor_wh_ids = req.warehouse_ids
            elif req.warehouse_id is not None:
                supervisor_wh_ids = [req.warehouse_id]
            else:
                supervisor_wh_ids = list((await db.execute(select(UserWarehouse.warehouse_id).where(
                    UserWarehouse.user_id == user.id))).scalars())
                if not supervisor_wh_ids and user.warehouse_id is not None:
                    supervisor_wh_ids = [user.warehouse_id]
            if len(set(supervisor_wh_ids)) != 1:
                raise HTTPException(status_code=400, detail="主管只能分配一个仓库")
    if req.role is not None and req.role != user.role and permission_state(user)['version'] != 'legacy' and req.action_permissions is None:
        raise HTTPException(409, '变更角色时请一并核对三档动作权限')
    new_permissions = prepared_permissions(req, req.role or user.role, user)

    # 修改前快照（用于修改日志）
    before_uws = (await db.execute(
        select(UserWarehouse).where(UserWarehouse.user_id == user_id)
    )).scalars().all()
    before_data = {
        "username": user.username, "display_name": user.display_name,
        "role": user.role, "warehouse_ids": sorted([uw.warehouse_id for uw in before_uws]),
        "is_active": user.is_active,
        "permissions": user.extra_permissions,
        "permission_source_version": permission_state(user)["version"],
        **_attendance_fields(user),
    }

    # 修改用户名：校验唯一性
    if req.username is not None and req.username != user.username:
        existing = (await db.execute(
            select(User).where(User.username == req.username, User.id != user_id)
        )).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=400, detail="用户名已存在")
        user.username = req.username

    # 重置密码：加密存储
    if req.password:
        if len(req.password) < 6:
            raise HTTPException(status_code=400, detail="密码至少6位")
        user.password_hash = hash_password(req.password)

    if req.display_name is not None:
        user.display_name = req.display_name
    if req.role is not None:
        user.role = req.role
    # 仓库分配：多仓 warehouse_ids 优先，其次单仓 warehouse_id
    if req.warehouse_ids is not None or req.warehouse_id is not None:
        if req.warehouse_ids is not None:
            new_wh_ids = list(req.warehouse_ids)
        elif req.warehouse_id is not None:
            new_wh_ids = [req.warehouse_id]
        else:
            new_wh_ids = []

        # 非超管：校验新分配的仓库都在自己管理范围内
        if current_user.role != Role.SUPER_ADMIN:
            managed = (await db.execute(
                select(UserWarehouse.warehouse_id).where(UserWarehouse.user_id == current_user.id)
            )).scalars().all()
            managed = list(managed) if managed else []
            for wid in new_wh_ids:
                if wid not in managed:
                    raise HTTPException(status_code=403, detail="无权限将用户分配到该仓库")

        for wid in new_wh_ids:
            own_scope(current_user, wid)
        primary_wh = new_wh_ids[0] if new_wh_ids else None
        user.warehouse_id = primary_wh
        # 同步更新 user_warehouses 关联：只删该删的、只加该加的，避免先插后删触发唯一键冲突
        new_wh_ids = list(dict.fromkeys(new_wh_ids))  # 去重保持顺序
        existing_uw = (await db.execute(
            select(UserWarehouse).where(UserWarehouse.user_id == user_id)
        )).scalars().all()
        old_ids = {uw.warehouse_id for uw in existing_uw}
        new_ids = set(new_wh_ids)
        for uw in existing_uw:
            if uw.warehouse_id not in new_ids:
                await db.delete(uw)
        for wid in new_wh_ids:
            if wid not in old_ids:
                db.add(UserWarehouse(user_id=user_id, warehouse_id=wid))
    if req.is_active is not None:
        user.is_active = req.is_active
    if req.line_user_id is not None:
        user.line_user_id = req.line_user_id
    user.extra_permissions = new_permissions

    attendance_result = {}
    if req.attendance_enabled is not None and user.role in (Role.SUPERVISOR, Role.STAFF):
        if req.attendance_enabled:
            employee, created = await bind_attendance_employee(db, user, current_user)
            notice = None
            if employee.salary_template_id is None or employee.deduction_template_id is None:
                notice = ("档案已建好，" if created else "档案已绑定，") + "请到员工档案里设置薪资模板和扣款模板"
            attendance_result = {"attendance_employee_created": created, "attendance_notice": notice}
            if not user.attendance_enabled:
                user.attendance_enabled_at = datetime.now(timezone.utc)
            user.attendance_enabled = True
        else:
            if user.attendance_employee_id is not None:
                # 只解除该档案对当前账号的绑定，不删除档案或修改业务记录。
                await db.execute(update(Employee).where(
                    Employee.id == user.attendance_employee_id,
                    Employee.user_id == user.id,
                ).values(user_id=None, updated_at=Employee.updated_at))
            user.attendance_enabled = False
            user.attendance_employee_id = None
            user.attendance_enabled_at = None

    # 修改后快照 + 记录日志（密码只记录已重置，不记录内容）
    after_uws = (await db.execute(
        select(UserWarehouse).where(UserWarehouse.user_id == user_id)
    )).scalars().all()
    after_data = {
        "username": user.username, "display_name": user.display_name,
        "role": user.role, "warehouse_ids": sorted([uw.warehouse_id for uw in after_uws]),
        "is_active": user.is_active,
        "permissions": user.extra_permissions,
        "permission_source_version": permission_state(user)["version"],
        **_attendance_fields(user),
    }
    if req.action_permissions is not None or req.extra_permissions is not None:
        after_data["permission_reason"] = req.permission_reason or "旧菜单请求保守转换"
        after_data["permission_source_version"] = 1
        after_data["permission_change_source"] = "explicit action grants" if req.action_permissions is not None else "legacy menu conversion"
    if req.password:
        after_data["password"] = "已重置密码"

    await record_history(db, module="user", record_id=user_id, operator=current_user,
                          operation_type="edit", before=before_data, after=after_data,
                          warehouse_id=user.warehouse_id)

    await db.flush()
    message = "用户更新成功"
    if attendance_result.get("attendance_notice"):
        message += "；" + attendance_result["attendance_notice"]
    return {"message": message, "action_access": access_description(user), **_attendance_fields(user), **attendance_result}

async def _delete_staff_or_labor(db: AsyncSession, user_id: int, username: str):
    """删除财务/劳工账号：解除关联并彻底删除，保留其所在仓库业务数据。"""
    from sqlalchemy import text
    uid = user_id
    # Successful logins now create audit rows. Preserve their immutable facts and
    # actor snapshot while releasing the nullable FK before deleting the account.
    from app.models.audit_log import AuditLog
    from app.models.data_change_history import DataChangeHistory
    actor = await db.get(User, uid)
    audit_rows = (await db.execute(select(AuditLog).where(AuditLog.user_id == uid).with_for_update())).scalars()
    for row in audit_rows:
        row.detail = {**(row.detail if isinstance(row.detail, dict) else {"original_detail": row.detail}), "deleted_user": {
            "id": uid, "username": username, "display_name": actor.display_name,
        }}
        row.user_id = None
    # Modification history already keeps operator_name for deleted accounts.
    await db.execute(update(DataChangeHistory).where(DataChangeHistory.operator_id == uid).values(operator_id=None))
    await db.flush()
    # 解除员工档案与登录账号的关联
    await db.execute(text("UPDATE employees SET user_id = NULL WHERE user_id = :uid"), {"uid": uid})
    # 清除创建人引用
    await db.execute(text("UPDATE users SET created_by = NULL WHERE created_by = :uid"), {"uid": uid})
    # 删除个人数据（打卡、备用金、报销）
    await db.execute(text("DELETE FROM clock_in_records WHERE user_id = :uid"), {"uid": uid})
    await db.execute(text("DELETE FROM expense_fund_items WHERE fund_id IN (SELECT id FROM expense_funds WHERE employee_id = :uid)"), {"uid": uid})
    await db.execute(text("DELETE FROM expense_funds WHERE employee_id = :uid"), {"uid": uid})
    await db.execute(text("DELETE FROM reimbursement_items WHERE reimbursement_id IN (SELECT id FROM reimbursements WHERE employee_id = :uid)"), {"uid": uid})
    await db.execute(text("DELETE FROM reimbursements WHERE employee_id = :uid"), {"uid": uid})
    # 删除用户-仓库关联与用户
    await db.execute(text("DELETE FROM user_warehouses WHERE user_id = :uid"), {"uid": uid})
    await db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": uid})
    await db.commit()


@router.delete("/{user_id}", dependencies=[Depends(mutation_scope)])
async def delete_user(
    user_id: int,
    current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["settings"].label)),
    db: AsyncSession = Depends(get_db),
):
    """删除用户：仓库管理员可删除自己仓库的财务/劳工；超级管理员删除仓库管理员（级联）。"""
    require_account_manager(current_user, platform=True)
    import traceback
    import logging
    logger = logging.getLogger("delete_user")
    
    try:
        if current_user.id == user_id:
            raise HTTPException(status_code=400, detail="不能删除自己")

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")

        own_scope(current_user, user.warehouse_id)
        await login_target_scope(db, current_user, user)
        # 删除前快照（用于修改日志）
        before_uws = (await db.execute(
            select(UserWarehouse).where(UserWarehouse.user_id == user_id)
        )).scalars().all()
        before_data = {
            "username": user.username, "display_name": user.display_name,
            "role": user.role, "warehouse_ids": sorted([uw.warehouse_id for uw in before_uws]),
            "is_active": user.is_active,
        }
        await record_history(db, module="user", record_id=user_id, operator=current_user,
                              operation_type="delete", before=before_data,
                              warehouse_id=user.warehouse_id)

        # 仓库管理员/主管：删除自己仓库的财务/劳工
        if current_user.role in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
            if user.role not in (Role.STAFF.value, Role.WAREHOUSE_LABOR.value):
                raise HTTPException(status_code=403, detail="只能删除财务/劳工账号")
            managed_wh_ids = (await db.execute(
                select(UserWarehouse.warehouse_id).where(UserWarehouse.user_id == current_user.id)
            )).scalars().all()
            managed_wh_ids = list(managed_wh_ids) if managed_wh_ids else []
            if not managed_wh_ids or user.warehouse_id not in managed_wh_ids:
                raise HTTPException(status_code=403, detail="只能删除自己仓库的用户")
            await _delete_staff_or_labor(db, user_id, user.username)
            return {"message": f"已删除用户 {user.username}"}

        if current_user.role != Role.SUPER_ADMIN:
            raise HTTPException(status_code=403, detail="只有超级管理员可以删除用户")

        if user.role != Role.WAREHOUSE_ADMIN:
            raise HTTPException(status_code=400, detail="只能删除仓库管理员")

        from sqlalchemy import text
        username = user.username

        # 1. Nullify FK references to this user BEFORE deleting anything
        await db.execute(text("UPDATE users SET created_by = NULL WHERE created_by = :uid"), {"uid": user_id})
        await db.execute(text("UPDATE warehouses SET created_by = NULL WHERE created_by = :uid"), {"uid": user_id})

        # 2. Find warehouses managed by this user (via UserWarehouse association)
        uw_result = await db.execute(
            select(UserWarehouse.warehouse_id).where(UserWarehouse.user_id == user_id)
        )
        owned_wh_ids = [r for r in uw_result.scalars().all()]

        if owned_wh_ids:
            # 3. Cascade delete all business data in these warehouses
            await db.execute(text("DELETE FROM credit_shipments WHERE credit_customer_id IN (SELECT id FROM credit_customers WHERE warehouse_id = ANY(:wids))"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM credit_repayments WHERE credit_customer_id IN (SELECT id FROM credit_customers WHERE warehouse_id = ANY(:wids))"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM credit_customers WHERE warehouse_id = ANY(:wids)"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM reimbursement_items WHERE reimbursement_id IN (SELECT id FROM reimbursements WHERE warehouse_id = ANY(:wids))"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM reimbursements WHERE warehouse_id = ANY(:wids)"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM expense_fund_items WHERE fund_id IN (SELECT id FROM expense_funds WHERE warehouse_id = ANY(:wids))"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM expense_funds WHERE warehouse_id = ANY(:wids)"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM group_order_participants WHERE warehouse_id = ANY(:wids)"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM group_orders WHERE warehouse_id = ANY(:wids)"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM payable_bills WHERE warehouse_id = ANY(:wids)"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM payable_plans WHERE warehouse_id = ANY(:wids)"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM plan_templates WHERE warehouse_id = ANY(:wids)"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM monthly_order_volumes WHERE warehouse_id = ANY(:wids)"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM income_records WHERE warehouse_id = ANY(:wids)"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM expense_records WHERE warehouse_id = ANY(:wids)"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM income_expense_categories WHERE warehouse_id = ANY(:wids)"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM reconciliation_results WHERE warehouse_id = ANY(:wids)"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM recharge_declarations WHERE warehouse_id = ANY(:wids)"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM incoming_flows WHERE warehouse_id = ANY(:wids)"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM market_items WHERE warehouse_id = ANY(:wids)"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM exchange_rates WHERE warehouse_id = ANY(:wids)"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM system_settings WHERE warehouse_id = ANY(:wids)"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM reimb_categories WHERE warehouse_id = ANY(:wids)"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM suppliers WHERE warehouse_id = ANY(:wids)"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM customers WHERE warehouse_id = ANY(:wids)"), {"wids": owned_wh_ids})
            await db.execute(text("DELETE FROM payment_accounts WHERE warehouse_id = ANY(:wids)"), {"wids": owned_wh_ids})

            # Clear warehouse_id from users referencing these warehouses
            await db.execute(text("UPDATE users SET warehouse_id = NULL WHERE warehouse_id = ANY(:wids)"), {"wids": owned_wh_ids})

        # 4. Delete UserWarehouse associations
        await db.execute(text("DELETE FROM user_warehouses WHERE user_id = :uid"), {"uid": user_id})
        if owned_wh_ids:
            await db.execute(text("DELETE FROM user_warehouses WHERE warehouse_id = ANY(:wids)"), {"wids": owned_wh_ids})

        # 5. Clear audit logs
        await db.execute(text("DELETE FROM audit_logs WHERE user_id = :uid"), {"uid": user_id})

        # 6. Delete owned warehouses
        if owned_wh_ids:
            await db.execute(text("DELETE FROM warehouses WHERE id = ANY(:wids)"), {"wids": owned_wh_ids})

        # 7. Delete the user
        await db.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": user_id})

        await db.commit()
        return {"message": f"已删除用户 {username} 及其所有数据"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete user {user_id} failed: {e}\n{traceback.format_exc()}")
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")
