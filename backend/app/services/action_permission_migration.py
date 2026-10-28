"""Explicit scoped local migration; no startup backfill and no schema/model changes."""
from fastapi import HTTPException
from sqlalchemy import select
from app.models.user import User
from app.core.round2_access import require_account_manager, login_target_scope
from app.core.action_access import permission_state, convert_legacy, VERSION
from app.services.data_history import record_history


async def migrate_permissions(db, actor, user_ids, reason):
    require_account_manager(actor, platform=True)
    if not reason or not reason.strip():
        raise HTTPException(400, '请填写权限转换原因')
    if len(user_ids) != len(set(user_ids)):
        raise HTTPException(400, "目标账号不能重复")
    targets = (await db.execute(select(User).where(User.id.in_(user_ids)).with_for_update())).scalars().all()
    if len(targets) != len(set(user_ids)):
        raise HTTPException(404, '部分目标账号不存在')
    prepared = []
    for target in targets:
        if target.id == actor.id:
            raise HTTPException(403, '不能转换本人的管理权限')
        await login_target_scope(db, actor, target)
        state = permission_state(target)
        if state['version'] == 1:
            continue  # Never re-grant after later revocation.
        converted, state = convert_legacy(target)
        prepared.append((target, converted, state, target.extra_permissions))
    for target, converted, state, old in prepared:
        target.extra_permissions = converted
        await record_history(db, module='permissions', record_id=target.id, operator=actor,
            operation_type='migrate_actions_v1', warehouse_id=target.warehouse_id,
            before={'source_version':state['version'],'raw_permissions':old},
            after={'version':VERSION,'grants':converted[1:],'reason':reason,
                   'unknown_legacy_values':state['unknown'],'source':'explicit scoped migration'})
    await db.flush()
    return {'converted':len(prepared),'already_versioned':len(targets)-len(prepared)}
