"""报表及三张账的只读下钻；不借用业务写权限，不写数据库。"""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.permissions import Role, check_staff_permission, get_wh_id
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.database import get_db
from app.services import cost_funds_debt as service

router = APIRouter()


async def report_user(request: Request, db: AsyncSession = Depends(get_db), user=Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["reports"].label))):
    if user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无此操作权限")
    if getattr(user, "_all_warehouses", False) or get_wh_id(user) is None:
        raise HTTPException(400, "请先选择一个仓库")
    from app.services.warehouse_summary import warehouse_scope
    await warehouse_scope(db, user, request.headers.get("X-Warehouse-ID"))
    return user


@router.get("")
async def get_report(start_date: str | None = None, end_date: str | None = None,
                     month: str | None = None, year: str | None = None,
                     user=Depends(report_user), db: AsyncSession = Depends(get_db)):
    start, end = service.dates(start_date, end_date, month=month, year=year)
    return await service.report(db, [get_wh_id(user)], start, end)


@router.get("/costs")
async def costs(start_date: str | None = None, end_date: str | None = None,
                month: str | None = None, year: str | None = None,
                category_id: int | None = None, cost_category: str | None = Query(default=None, max_length=100),
                account_id: int | None = None, currency: Literal["THB", "CNY"] | None = None,
                page: int = Query(default=1, ge=1), page_size: int = Query(default=25, ge=1, le=200),
                user=Depends(report_user), db: AsyncSession = Depends(get_db)):
    start, end = service.dates(start_date, end_date, month=month, year=year)
    return await service.cost_list(db, [get_wh_id(user)], start, end, page=page, page_size=page_size,
        category_id=category_id, cost_category=cost_category, account_id=account_id, currency_code=currency)


@router.get("/flows")
async def flows(start_date: str | None = None, end_date: str | None = None,
                month: str | None = None, year: str | None = None,
                account_id: int | None = None, currency: Literal["THB", "CNY"] | None = None,
                source: str | None = None, flow_type: Literal["income", "expense"] | None = None, unassigned: bool = False,
                page: int = Query(default=1, ge=1), page_size: int = Query(default=30, ge=1, le=200),
                user=Depends(report_user), db: AsyncSession = Depends(get_db)):
    start, end = service.dates(start_date, end_date, month=month, year=year)
    return await service.flow_list(db, [get_wh_id(user)], start, end, page=page, page_size=page_size,
        account_id=account_id, currency_code=currency, source=source, flow_type=flow_type, unassigned=unassigned)


@router.get("/advances")
async def advances(start_date: str | None = None, end_date: str | None = None,
                   month: str | None = None, year: str | None = None,
                   payer_id: int | None = None, payer_name: str | None = Query(default=None, max_length=100),
                   currency: Literal["THB", "CNY"] | None = None,
                   page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=200),
                   user=Depends(report_user), db: AsyncSession = Depends(get_db)):
    start, end = service.dates(start_date, end_date, month=month, year=year)
    return await service.advance_list(db, [get_wh_id(user)], start, end, page=page, page_size=page_size,
        payer_id=payer_id, payer_name=payer_name, currency_code=currency)
