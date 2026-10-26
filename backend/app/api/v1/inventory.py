"""Single-warehouse quantity journals; no implicit inventory permission grants."""
from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt
from sqlalchemy import select, func
from app.database import get_db
from app.core.permissions import get_current_user, require_non_labor, check_staff_permission, Role
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.models import InventoryAccount, InventoryMovement, InventoryReceiptLink, StandardSKU
from app.services.warehouse_summary import warehouse_scope
from app.services import inventory as service, sku_catalog as catalog
from app.services.inventory_migration import ensure_inventory

router = APIRouter(dependencies=[Depends(require_non_labor), Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY['inventory'].label))])


async def current_warehouse(request: Request, user=Depends(get_current_user), db=Depends(get_db)):
    if user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, '无权访问库存')
    rows = await warehouse_scope(db, user, request.headers.get('X-Warehouse-ID'))
    if len(rows) != 1:
        raise HTTPException(400, '请选择单个仓库查看库存，不能跨仓或混合基本单位汇总')
    return rows[0].id


class Mutation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_key: str = Field(min_length=1, max_length=100)


class Opening(Mutation):
    sku_id: StrictInt = Field(gt=0)
    base_unit: str = Field(min_length=1, max_length=20)
    opening_quantity: str
    occurred_at: datetime
    confirmed: StrictBool
    expected_version: str = Field(pattern=r'^[a-f0-9]{64}$')
    change_reason: str = Field(min_length=1, max_length=1000)


class Issue(Mutation):
    issued_quantity: str
    expected_version: str = Field(pattern=r'^[a-f0-9]{64}$')
    purpose: str = Field(min_length=1, max_length=1000)


class Return(Mutation):
    returned_quantity: str
    expected_version: str = Field(pattern=r'^[a-f0-9]{64}$')
    return_reason: str = Field(min_length=1, max_length=1000)


class Reversal(Mutation):
    expected_version: str = Field(pattern=r'^[a-f0-9]{64}$')
    reverse_reason: str = Field(min_length=1, max_length=1000)


class Resolve(Mutation):
    expected_sku_version: str = Field(pattern=r'^[a-f0-9]{64}$')
    sku_id: StrictInt = Field(gt=0)
    base_unit_factor: str
    expected_source_fingerprint: str = Field(pattern=r'^[a-f0-9]{64}$')
    confirmation_reason: str = Field(min_length=1, max_length=1000)


class Policy(Mutation):
    valuation_method: Literal['unconfigured', 'quantity_only']
    expected_version: str = Field(pattern=r'^[a-f0-9]{64}$')
    change_reason: str = Field(min_length=1, max_length=1000)


@router.get('')
async def listing(sku_id: int | None = Query(None, gt=0), page: int = Query(1, ge=1),
                  page_size: int = Query(20, ge=1, le=100), user=Depends(get_current_user),
                  wid=Depends(current_warehouse), db=Depends(get_db)):
    await ensure_inventory(await db.connection())
    if sku_id is not None:
        await service.owned(db, StandardSKU, sku_id, wid)
    q = select(InventoryAccount).where(InventoryAccount.warehouse_id == wid)
    if sku_id is not None:
        q = q.where(InventoryAccount.sku_id == sku_id)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await db.execute(q.order_by(InventoryAccount.id).offset((page-1)*page_size).limit(page_size))).scalars()
    pending = (await db.execute(select(func.count()).select_from(InventoryReceiptLink).where(
        InventoryReceiptLink.warehouse_id == wid, InventoryReceiptLink.status == 'pending'))).scalar_one()
    return {'data': [service.account_data(r) for r in rows], 'total': total, 'page': page,
            'pending_receipt_count': pending, 'policy': await service.policy(db, wid),
            'note': '各仓、各SKU、各基本单位独立；未确认期初不视为零，金额待配置；不与资金支出重复记费用'}


@router.get('/catalog')
async def available_skus(user=Depends(get_current_user), wid=Depends(current_warehouse), db=Depends(get_db)):
    await ensure_inventory(await db.connection())
    skus = (await db.execute(select(StandardSKU).where(StandardSKU.warehouse_id == wid).order_by(StandardSKU.code))).scalars().all()
    accounts = (await db.execute(select(InventoryAccount).where(InventoryAccount.warehouse_id == wid))).scalars().all()
    by_unit = {(a.sku_id, a.base_unit): a for a in accounts}
    return {'data': [{'id': s.id, 'code': s.code, 'name': s.name, 'base_unit': s.base_unit,
                     'unit_label': catalog.UNITS.get(s.base_unit, s.base_unit), 'active': s.active, 'version': catalog.sku_data(s)['version'],
                     'opening_target': service.account_data(by_unit[(s.id, s.base_unit)]) if (s.id, s.base_unit) in by_unit
                     else {'id': None, 'version': service.account_version(wid, s.id, s.base_unit), 'opening_confirmed': False}}
                    for s in skus]}


@router.get('/policy')
async def get_policy(user=Depends(get_current_user), wid=Depends(current_warehouse), db=Depends(get_db)):
    await ensure_inventory(await db.connection())
    return await service.policy(db, wid)


@router.put('/policy')
async def set_policy(req: Policy, user=Depends(get_current_user), wid=Depends(current_warehouse), db=Depends(get_db)):
    return await service.set_policy(db, wid, user, **req.model_dump())


@router.post('/openings')
async def confirm_opening(req: Opening, user=Depends(get_current_user), wid=Depends(current_warehouse), db=Depends(get_db)):
    return await service.opening(db, wid, user, **req.model_dump())


@router.get('/pending-receipts')
async def pending_receipts(status: Literal['pending', 'recorded', 'reversed'] = 'pending',
                           page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                           user=Depends(get_current_user), wid=Depends(current_warehouse), db=Depends(get_db)):
    await ensure_inventory(await db.connection())
    q = select(InventoryReceiptLink).where(InventoryReceiptLink.warehouse_id == wid, InventoryReceiptLink.status == status)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await db.execute(q.order_by(InventoryReceiptLink.id.desc()).offset((page-1)*page_size).limit(page_size))).scalars()
    return {'data': [service.link_data(r) for r in rows], 'total': total, 'page': page,
            'note': '仅新收货，不扫描或补造历史收货；缺可靠SKU/换算必须由老板按证据明确确认'}


@router.post('/pending-receipts/{ident}/resolve')
async def resolve_receipt(ident: int, req: Resolve, user=Depends(get_current_user), wid=Depends(current_warehouse), db=Depends(get_db)):
    return await service.resolve_receipt(db, wid, user, ident, **req.model_dump())


@router.get('/accounts/{account_id}')
async def detail(account_id: int, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                 user=Depends(get_current_user), wid=Depends(current_warehouse), db=Depends(get_db)):
    await ensure_inventory(await db.connection())
    account = await service.owned(db, InventoryAccount, account_id, wid)
    q = select(InventoryMovement).where(InventoryMovement.warehouse_id == wid, InventoryMovement.account_id == account_id)
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    rows = (await db.execute(q.order_by(InventoryMovement.id.desc()).offset((page-1)*page_size).limit(page_size))).scalars()
    return {'account': service.account_data(account), 'data': [service.movement_data(r) for r in rows],
            'total': total, 'page': page,
            'balance_after_basis': '登记后的已知累计，按记录编号排序；补录期初的基准时间不代表当时已登记后的余额。历史时点数量须按发生时间累加原始有符号流水，包括冲销反向流水。'}


@router.post('/accounts/{account_id}/issues')
async def issue(account_id: int, req: Issue, user=Depends(get_current_user), wid=Depends(current_warehouse), db=Depends(get_db)):
    return await service.issue(db, wid, user, account_id, **req.model_dump())


@router.post('/movements/{movement_id}/returns')
async def return_issue(movement_id: int, req: Return, user=Depends(get_current_user), wid=Depends(current_warehouse), db=Depends(get_db)):
    return await service.return_issue(db, wid, user, movement_id, **req.model_dump())


@router.post('/movements/{movement_id}/reverse')
async def reverse(movement_id: int, req: Reversal, user=Depends(get_current_user), wid=Depends(current_warehouse), db=Depends(get_db)):
    return await service.reverse(db, wid, user, movement_id, **req.model_dump())
