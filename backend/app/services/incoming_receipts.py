"""到账登记幂等与私有附件；不改变金额、收款日期或钱包统计口径。"""
import hashlib
import json
import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from app.models.recharge import IncomingFlow
from app.services.wallet import positive_money, lock_account


def private_directory():
    return Path(os.environ.get("INCOMING_ATTACHMENT_DIR", "/app/incoming-private"))


def screenshot_path(name):
    if not name or Path(name).name != name or name.startswith("."):
        raise HTTPException(404, "到账截图不存在")
    return private_directory() / name


def incoming_dict(row, entrant_name=""):
    return {"id": row.id, "warehouse_id": row.warehouse_id, "received_date": row.received_date.isoformat(),
        "amount": row.amount, "currency": row.currency or "THB", "account_id": row.account_id,
        "payer_name": row.payer_name, "payment_method": row.payment_method, "remark": row.remark,
        "match_status": row.match_status or "unmatched", "entrant_name": entrant_name,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "request_key": row.request_key, "has_screenshot": bool(row.screenshot)}


def request_values(req, context_hash=None):
    try:
        when = datetime.fromisoformat(req.received_date)
    except ValueError:
        raise HTTPException(400, "到账日期格式错误")
    value = positive_money(req.amount)
    values = {"received_date": when, "amount": float(value), "currency": req.currency,
        "account_id": req.account_id, "payer_name": req.payer_name, "payment_method": req.payment_method,
        "remark": req.remark}
    canonical = {**values, "amount": str(value.quantize(Decimal('0.01'))), "received_date": when.isoformat()}
    if context_hash: canonical["batch"] = context_hash
    fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return values, fingerprint


async def create_once(db, req, warehouse_id, operator, *, context_hash=None):
    values, fingerprint = request_values(req, context_hash)
    async def existing():
        return (await db.execute(select(IncomingFlow).where(IncomingFlow.warehouse_id == warehouse_id,
            IncomingFlow.request_key == req.request_key))).scalar_one_or_none()
    def replay(row):
        if row.request_fingerprint != fingerprint:
            raise HTTPException(409, "本次录入已保存，内容不一致；请查看原到账，另一笔到账请重新录入")
        return row, False
    found = await existing()
    if found: return replay(found)
    await lock_account(db, warehouse_id, req.account_id, req.currency)
    insert = sqlite_insert if db.bind.dialect.name == "sqlite" else postgres_insert
    # 冲突不终止事务；批量中的任何一条失败，之前插入的也可整体回滚。
    statement = insert(IncomingFlow).values(warehouse_id=warehouse_id, entrant_id=operator.id,
        request_key=req.request_key, request_fingerprint=fingerprint, **values).on_conflict_do_nothing(
        index_elements=["warehouse_id", "request_key"]).returning(IncomingFlow.id)
    inserted_id = (await db.execute(statement)).scalar_one_or_none()
    if inserted_id is None:
        return replay(await existing())
    return await db.get(IncomingFlow, inserted_id), True
