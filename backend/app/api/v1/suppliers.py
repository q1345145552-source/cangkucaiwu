from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.supplier import Supplier, SupplierCategory, SupplierProduct, SupplierLogisticsPrice, SupplierCrossBorderPrice, PurchaseOrder, ProcurementPriceHistory, ProcurementPriceAnomaly, ProcurementNonLowestRecord
from app.models.user import User
from app.models.payable import PayableBill
from app.models.expense_fund import SystemSetting
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role, check_staff_permission, check_staff_permission_any, require_non_labor
from pydantic import BaseModel, StrictInt, Field, ConfigDict
from decimal import Decimal
from typing import Optional, List
from app.core.timezone import thai_now, thai_today, THAI_TZ
from datetime import datetime, timedelta
from app.schemas.business import SupplierCreate, SupplierUpdate, SupplierResponse, SupplierProductCreate
import io, json
from uuid import uuid4

from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.core.config_access import ensure_config_editor

_CONCENTRATION_PERMISSION = MENU_PERMISSIONS_BY_KEY["concentration"].label

from app.services.supplier_payable_read import current_supplier_warehouse, purchase_detail, checked_link
from app.services import payable_creation as creation
from app.services import purchase_matching as matching
from app.services import sku_catalog as catalog
from app.services import supplier_quotes as quotes
from app.services import purchase_price_review as price_review
from app.services import procurement_controls as duty

router = APIRouter()


class MatchPolicySet(BaseModel):
    strict: bool


@router.get("/purchase-match-policy", dependencies=[Depends(require_non_labor)])
async def get_match_policy(warehouse_id: int = Depends(current_supplier_warehouse),
        current_user: User = Depends(check_staff_permission_any(*(MENU_PERMISSIONS_BY_KEY[k].label
            for k in ("suppliers", "payable", "payment_plans", "config_center")))), db: AsyncSession = Depends(get_db)):
    return await matching.policy(db,warehouse_id)


@router.put("/purchase-match-policy", dependencies=[Depends(require_non_labor)])
async def set_match_policy(req: MatchPolicySet, warehouse_id: int = Depends(current_supplier_warehouse),
        current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["config_center"].label)),
        db: AsyncSession = Depends(get_db)):
    ensure_config_editor(current_user)
    await matching.scope_lock(db,warehouse_id)
    rows=(await db.execute(select(SystemSetting).where(SystemSetting.warehouse_id==warehouse_id,
        SystemSetting.key==matching.POLICY_KEY).with_for_update())).scalars().all()
    if len(rows)>1: raise HTTPException(409,"三单校验配置重复，请管理员核对")
    before=rows[0].value if rows else "false"
    if rows: rows[0].value="true" if req.strict else "false"
    else: db.add(SystemSetting(warehouse_id=warehouse_id,key=matching.POLICY_KEY,value="true" if req.strict else "false"))
    from app.services.data_history import record_history
    await record_history(db,module="suppliers",record_id=warehouse_id,operator=current_user,operation_type="match_policy",
        before={"strict":before},after={"strict":req.strict},warehouse_id=warehouse_id)
    await db.flush()
    return await matching.policy(db,warehouse_id)


def _forbid_super_admin(current_user: User) -> None:
    """供应商模块业务接口统一拒绝超级管理员，需用仓库管理员账号操作。"""
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")


async def _get_boss_contact(db: AsyncSession) -> dict:
    """读取老板联系方式（全局 SystemSetting）。"""
    rows = (await db.execute(
        select(SystemSetting).where(
            SystemSetting.warehouse_id == 0,
            SystemSetting.key.in_(["boss_contact_name", "boss_contact_phone"]),
        )
    )).scalars().all()
    m = {s.key: s.value for s in rows}
    return {"name": m.get("boss_contact_name") or "", "phone": m.get("boss_contact_phone") or ""}


def _build_purchase_order_pdf(po, supplier_name: str, warehouse_name: str, boss: dict) -> bytes:
    """生成采购单 PDF（含单号/供应商/产品明细/总价/日期/仓库/联系人）。"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    title_style = ParagraphStyle('title', fontName='STSong-Light', fontSize=18, leading=24, alignment=1, spaceAfter=10)
    label_style = ParagraphStyle('label', fontName='STSong-Light', fontSize=10, leading=16, textColor=colors.black)
    cell_style = ParagraphStyle('cell', fontName='STSong-Light', fontSize=9, leading=14)
    header_style = ParagraphStyle('header', fontName='STSong-Light', fontSize=9, leading=14, textColor=colors.white)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=16 * mm, bottomMargin=16 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm)

    created_str = po.created_at.astimezone(THAI_TZ).strftime("%Y-%m-%d %H:%M") if po.created_at else ""
    boss_name = boss.get("name") or ""
    boss_phone = boss.get("phone") or ""
    contact = f"{boss_name} {boss_phone}".strip() if (boss_name or boss_phone) else "-"
    cur = po.currency or "THB"
    sym = "¥" if cur == "CNY" else "฿"

    info_rows = [
        [Paragraph("采购单号：", label_style), Paragraph(str(po.order_number), cell_style)],
        [Paragraph("供应商：", label_style), Paragraph(supplier_name or "-", cell_style)],
        [Paragraph("仓库：", label_style), Paragraph(warehouse_name or "-", cell_style)],
        [Paragraph("下单日期：", label_style), Paragraph(created_str, cell_style)],
        [Paragraph("币种：", label_style), Paragraph(f"{cur} ({sym})", cell_style)],
        [Paragraph("联系人：", label_style), Paragraph(contact, cell_style)],
    ]
    info_table = Table(info_rows, colWidths=[30 * mm, 145 * mm])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))

    headers = ["产品名称", "规格", "数量", "单价", "小计"]
    data = [[Paragraph(h, header_style) for h in headers]]
    for it in (po.items or []):
        data.append([
            Paragraph(str(it.get("product_name") or ""), cell_style),
            Paragraph(str(it.get("spec") or "-"), cell_style),
            Paragraph(str(it.get("quantity") or 0), cell_style),
            Paragraph(f"{sym}{it.get('unit_price') or 0}", cell_style),
            Paragraph(f"{sym}{it.get('subtotal') or 0}", cell_style),
        ])
    data.append([
        Paragraph("合计", cell_style), Paragraph("", cell_style), Paragraph("", cell_style),
        Paragraph("", cell_style),
        Paragraph(f"{sym}{po.total_amount}", cell_style),
    ])

    items_table = Table(data, colWidths=[60 * mm, 45 * mm, 20 * mm, 25 * mm, 30 * mm], repeatRows=1)
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563EB')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))

    elements = [
        Paragraph("采 购 单", title_style),
        info_table,
        Spacer(1, 8 * mm),
        items_table,
    ]
    doc.build(elements)
    return buf.getvalue()


async def _require_supplier_owned(db: AsyncSession, current_user: User, supplier_id: int) -> Supplier:
    """校验供应商属于当前用户管理的仓库，否则 403。超级管理员被拒绝。"""
    _forbid_super_admin(current_user)
    sup = (await db.execute(select(Supplier).where(Supplier.id == supplier_id))).scalar_one_or_none()
    if not sup:
        raise HTTPException(404, "供应商不存在")
    if sup.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "无权操作其他仓库的供应商")
    return sup


DEFAULT_PRICE_THRESHOLD = 10.0  # 价格偏高阈值默认 10%


async def _get_price_threshold(db: AsyncSession, wh_id: int) -> float:
    setting = (await db.execute(
        select(SystemSetting).where(
            SystemSetting.warehouse_id == wh_id,
            SystemSetting.key == "procurement_price_threshold",
        )
    )).scalar_one_or_none()
    try:
        return float(setting.value) if setting else DEFAULT_PRICE_THRESHOLD
    except (ValueError, TypeError):
        return DEFAULT_PRICE_THRESHOLD


async def _get_approval_threshold(db: AsyncSession, wh_id: int | None) -> float:
    """采购审批金额门槛（按仓库，回退全局旧设置作为初始值）。0 表示无需审批。"""
    setting = None
    if wh_id is not None:
        setting = (await db.execute(
            select(SystemSetting).where(
                SystemSetting.warehouse_id == wh_id,
                SystemSetting.key == "purchase_approval_threshold",
            )
        )).scalar_one_or_none()
    if setting is None:
        # 回退全局旧设置作为初始值
        setting = (await db.execute(
            select(SystemSetting).where(
                SystemSetting.warehouse_id == 0,
                SystemSetting.key == "purchase_approval_threshold",
            )
        )).scalar_one_or_none()
    try:
        return float(setting.value) if setting else 0.0
    except (ValueError, TypeError):
        return 0.0


async def _get_price_history(db: AsyncSession, wh_id: int, product_name: str, spec: str | None, currency: str | None=None, unit: str | None=None) -> list:
    if not currency or not unit:return []
    rows = (await db.execute(
        select(ProcurementPriceHistory).where(
            ProcurementPriceHistory.warehouse_id == wh_id,
            ProcurementPriceHistory.product_name == product_name,
            ProcurementPriceHistory.currency == currency, ProcurementPriceHistory.unit == unit,
            func.coalesce(ProcurementPriceHistory.spec, "") == (spec or ""),
        ).order_by(ProcurementPriceHistory.created_at.asc())
    )).scalars().all()
    return rows


def _calc_stats(rows: list) -> dict:
    if not rows:
        return {"lowest": None, "avg": None, "last": None, "count": 0}
    prices = [r.unit_price for r in rows]
    return {
        "lowest": round(min(prices), 2),
        "avg": round(sum(prices) / len(prices), 2),
        "last": round(rows[-1].unit_price, 2),
        "count": len(prices),
    }


async def _get_lowest_quote(db: AsyncSession, product_name: str, spec: str | None, wh_id: int, currency: str | None=None, unit: str | None=None) -> dict | None:
    """某产品(名+规格)在本仓库内的最低报价（含最低价供应商名）。仅限本仓库，避免跨仓泄露。"""
    if not currency or not unit:return None
    rows = (await db.execute(
        select(SupplierProduct, Supplier)
        .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
        .where(
            SupplierProduct.product_name == product_name,
            SupplierProduct.currency == currency, SupplierProduct.unit == unit, SupplierProduct.catalog_active.is_not(False),
            func.coalesce(SupplierProduct.spec, "") == (spec or ""),
            Supplier.warehouse_id == wh_id,
        )
    )).all()
    if not rows:
        return None
    best = min(rows, key=lambda x: x[0].unit_price)
    return {
        "lowest_price": best[0].unit_price,
        "lowest_supplier_id": best[0].supplier_id,
        "lowest_supplier_name": best[1].name,
    }


class PurchaseOrderItem(BaseModel):
    model_config=ConfigDict(extra='forbid')
    product_id: int
    quantity: StrictInt = Field(default=1, gt=0, le=2147483647)
    reason: Optional[str] = None  # 非最低价采购原因
    quote_id: Optional[StrictInt] = None

class PurchaseOrderRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    items: List[PurchaseOrderItem]
    remark: Optional[str] = None
    confirm_price_anomaly: bool = False  # 是否确认价格偏高后提交
    request_key: Optional[str] = None
    duplicate_confirmation: Optional[dict] = None
    cost_confirmation: Optional[dict] = None
    pricing_version: Optional[str] = None
    requirements: Optional[dict] = None
    price_review_token: Optional[str] = None


# Parse settlement_cycle string to get number of days
def _parse_settlement_days(settlement_cycle: str | None) -> int:
    if not settlement_cycle:
        return 30
    import re
    nums = re.findall(r'\d+', str(settlement_cycle))
    if nums:
        return int(nums[0])
    return 30


async def _write_price_evidence(db: AsyncSession, po: PurchaseOrder) -> None:
    """订单生效时写入价格历史、价格异常、非最低价记录（直接生效或审批通过后调用）。"""
    wh_id = po.warehouse_id
    supplier = (await db.execute(select(Supplier).where(Supplier.id == po.supplier_id))).scalar_one_or_none()
    supplier_name = supplier.name if supplier else ""
    orderer = (await db.execute(select(User).where(User.id == po.created_by))).scalar_one_or_none() if po.created_by else None
    orderer_id = po.created_by
    orderer_name = orderer.display_name if orderer else ""
    threshold = await _get_price_threshold(db, wh_id)

    # 第一遍：计算异常与非最低价（此时本单尚未写入历史，避免污染历史均价）
    anomalies = []
    non_lowest = []
    for it in (po.items or []):
        product_name = it.get("product_name") or ""
        spec = it.get("spec") or None
        unit_price = float(it.get("unit_price") or 0)
        quantity = int(it.get("quantity") or 0)
        reason = (it.get("reason") or "").strip()

        pricing=it.get('pricing_snapshot')
        if isinstance(pricing,dict):
            historical=pricing.get('historical_price_review') or {}
            if historical.get('is_anomaly'):
                anomalies.append({'product_name':product_name,'spec':spec,'unit_price':float(historical['unit_price']),
                    'historical_avg':float(historical['historical_avg']),'exceed_percent':float(historical['exceed_percent'])})
            if pricing.get('non_lowest') and pricing.get('lowest_comparable_price') is not None:
                lowest=next(v for v in pricing['eligible_candidates'] if v['is_lowest'])
                price=Decimal(pricing['unit_price']);factor=Decimal(pricing['selected_quote']['terms']['base_unit_factor'])
                equivalent=Decimal(pricing['lowest_comparable_price'])*factor
                non_lowest.append({'product_name':product_name,'spec':spec,'unit_price':float(price),'quantity':quantity,
                    'reason':pricing.get('selection_reason') or reason,'lowest_price':float(equivalent),'lowest_supplier_id':lowest['supplier_id'],
                    'lowest_supplier_name':lowest['supplier_name'],'price_diff':float(price-equivalent)})
            continue  # Never recompute a new order against a later quote or same-name guess.

        hist_rows = await _get_price_history(db, wh_id, product_name, spec, po.currency, it.get("unit"))
        if hist_rows:
            avg = sum(r.unit_price for r in hist_rows) / len(hist_rows)
            if avg > 0 and unit_price > avg * (1 + threshold / 100.0):
                exceed = round((unit_price - avg) / avg * 100.0, 1)
                anomalies.append({
                    "product_name": product_name, "spec": spec,
                    "unit_price": unit_price, "historical_avg": round(avg, 2),
                    "exceed_percent": exceed,
                })

        lowest = await _get_lowest_quote(db, product_name, spec, wh_id, po.currency, it.get("unit"))
        if lowest and unit_price > lowest["lowest_price"] + 0.001:
            non_lowest.append({
                "product_name": product_name, "spec": spec,
                "unit_price": unit_price, "quantity": quantity, "reason": reason,
                "lowest_price": lowest["lowest_price"],
                "lowest_supplier_id": lowest["lowest_supplier_id"],
                "lowest_supplier_name": lowest["lowest_supplier_name"],
                "price_diff": round(unit_price - lowest["lowest_price"], 2),
            })

    # 第二遍：写入价格历史
    for it in (po.items or []):
        product_name = it.get("product_name") or ""
        spec = it.get("spec") or None
        unit_price = float(it.get("unit_price") or 0)
        quantity = int(it.get("quantity") or 0)
        db.add(ProcurementPriceHistory(
            warehouse_id=wh_id, supplier_id=po.supplier_id, purchase_order_id=po.id,
            product_name=product_name, spec=spec, unit_price=unit_price,
            quantity=quantity, created_by=orderer_id, currency=po.currency, unit=it.get("unit"), sku_snapshot=it.get("sku_mapping"), pricing_snapshot=it.get("pricing_snapshot"),
        ))

    # 写入价格异常
    for a in anomalies:
        db.add(ProcurementPriceAnomaly(
            warehouse_id=wh_id, product_name=a["product_name"], spec=a["spec"],
            purchase_price=a["unit_price"], historical_avg=a["historical_avg"],
            exceed_percent=a["exceed_percent"], orderer_id=orderer_id,
            orderer_name=orderer_name,
        ))

    # 写入非最低价
    for n in non_lowest:
        db.add(ProcurementNonLowestRecord(
            warehouse_id=wh_id, product_name=n["product_name"], spec=n["spec"],
            selected_supplier_id=po.supplier_id, selected_supplier_name=supplier_name,
            selected_price=n["unit_price"], lowest_supplier_id=n["lowest_supplier_id"],
            lowest_supplier_name=n["lowest_supplier_name"], lowest_price=n["lowest_price"],
            price_diff=n["price_diff"], quantity=n["quantity"], reason=n["reason"],
            orderer_id=orderer_id, orderer_name=orderer_name,
        ))
    await db.flush()

# ═══ Category CRUD ═══════════════════════════════
@router.get("/categories")
async def list_categories(current_user = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("供应商管理"))):
    cats = (await db.execute(select(SupplierCategory).where(SupplierCategory.is_active == "true").order_by(SupplierCategory.sort_order))).scalars().all()
    return {"data": [{"id": c.id, "name": c.name} for c in cats]}

@router.post("/categories")
async def create_category(name: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("供应商管理"))):
    raise HTTPException(403, "供应商分类为统一参考，只读；请使用本仓标签，不改写历史分类")

# ═══ Import Templates ════════════════════════════
@router.get("/import-template/products")
async def download_products_template(current_user: User = Depends(get_current_user),
    _perm=Depends(check_staff_permission("供应商管理"))):
    """下载耗材产品导入模板"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook(); ws = wb.active; ws.title = "耗材产品导入"
    hfill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    hfont = Font(bold=True, color="FFFFFF")
    for c, h in enumerate(["供应商名称", "产品名", "产品规格", "规格报价", "单价", "单位", "币种", "标准SKU编码", "结构化规格JSON", "基本单位换算数"], 1):
        cell = ws.cell(row=1, column=c, value=h); cell.font = hfont; cell.fill = hfill
    for c, v in enumerate(["示例: 耗材商A", "快递袋", "一打80个", 80, 1], 1):
        ws.cell(row=2, column=c, value=v)
    for col, w in [('A',20),('B',16),('C',16),('D',12),('E',12)]:
        ws.column_dimensions[col].width = w
    notes=wb.create_sheet("填写说明")
    for value in ["旧全局5列、单供应商4列仍支持，新增列可留空；先预览再逐行确认，整批成功或整批不导入。", "同规格不同名称只建议，不自动合并；同编码不同规格拒绝。SKU编码请用文本。", "结构化规格示例：{\"material\":\"PE\",\"width\":{\"value\":38,\"unit\":\"cm\"},\"packaging\":\"single\"}", "单位请从目录清单选择；箱/包换算未知留空，不猜箱=多少个。", "每行明确保持未映射或选择本仓SKU、核对版本并填写映射依据；原报价与历史订单不会覆盖。"]:notes.append([value])
    notes.column_dimensions['A'].width=110
    output = io.BytesIO(); wb.save(output); output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": "attachment; filename=products_import_template.xlsx"})

@router.get("/import-template/logistics")
async def download_logistics_template(current_user: User = Depends(get_current_user),
    _perm=Depends(check_staff_permission("供应商管理"))):
    """下载跨境物流价格导入模板"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook(); ws = wb.active; ws.title = "跨境物流价格导入"
    hfill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    hfont = Font(bold=True, color="FFFFFF")
    for c, h in enumerate(["供应商名称", "运输方式", "货物类型", "发货仓库", "单价(元/方)", "时效", "币种"], 1):
        cell = ws.cell(row=1, column=c, value=h); cell.font = hfont; cell.fill = hfill
    for c, v in enumerate(["示例: 物流公司A", "陆运", "普货", "深圳仓", 800, "5-7天", "CNY"], 1):
        ws.cell(row=2, column=c, value=v)
    for col, w in [('A',22),('B',10),('C',10),('D',10),('E',12),('F',10),('G',8)]:
        ws.column_dimensions[col].width = w
    output = io.BytesIO(); wb.save(output); output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": "attachment; filename=cross_border_logistics_template.xlsx"})

# ═══ Import ══════════════════════════════════════
@router.post("/import/products")
async def import_products(file: UploadFile = File(...), mode: str = Form("preview"),
                          preview_version: str = Form(None), request_key: str = Form(None), choices: str = Form(None),
                          current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
                          warehouse_id: int = Depends(current_supplier_warehouse),
                          _perm=Depends(check_staff_permission("供应商管理"))):
    from app.services import product_import
    content=await file.read()
    if mode=="preview":return await product_import.preview(db,warehouse_id,current_user,content)
    if mode!="confirm":raise HTTPException(400,"请选择预览或明确确认导入")
    return await product_import.confirm(db,warehouse_id,current_user,content,None,request_key,preview_version,choices)

@router.post("/import/logistics")
async def import_logistics(file: UploadFile = File(...), current_user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("供应商管理"))):
    """批量导入跨境物流价格 Excel"""
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    from openpyxl import load_workbook
    data = await file.read()
    wb = load_workbook(io.BytesIO(data)); ws = wb.active
    imported, skipped, errors = 0, 0, []
    sups = (await db.execute(select(Supplier).where(Supplier.warehouse_id.in_(get_wh_ids(current_user))))).scalars().all()
    sup_map = {s.name.strip(): s.id for s in sups}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]: continue
        sup_name = str(row[0]).strip()
        if sup_name.startswith("示例"): continue
        if sup_name not in sup_map:
            errors.append(f"供应商「{sup_name}」不存在"); skipped += 1; continue
        try:
            p = SupplierCrossBorderPrice(
                supplier_id=sup_map[sup_name],
                transport_method=str(row[1] or "").strip(),
                cargo_type=str(row[2] or "").strip(),
                origin_warehouse=str(row[3] or "").strip(),
                price_per_cbm=float(row[4] or 0),
                estimated_days=str(row[5] or "").strip() if row[5] else None,
                currency=str(row[6] or "CNY").strip(),
            )
            db.add(p); imported += 1
        except Exception as e:
            errors.append(f"行解析失败: {e}"); skipped += 1
    await db.flush()
    return {"imported": imported, "skipped": skipped, "errors": errors, "message": f"成功导入 {imported} 条跨境物流价格"}

# ═══ Per-Supplier Import ══════════════════════════
@router.post("/{supplier_id}/import/products")
async def import_products_for_supplier(supplier_id: int, file: UploadFile = File(...), mode: str = Form("preview"),
                          preview_version: str = Form(None), request_key: str = Form(None), choices: str = Form(None),
                          current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
                          warehouse_id: int = Depends(current_supplier_warehouse),
                          _perm=Depends(check_staff_permission("供应商管理"))):
    from app.services import product_import
    content=await file.read()
    if mode=="preview":return await product_import.preview(db,warehouse_id,current_user,content,supplier_id)
    if mode!="confirm":raise HTTPException(400,"请选择预览或明确确认导入")
    return await product_import.confirm(db,warehouse_id,current_user,content,supplier_id,request_key,preview_version,choices)

@router.post("/{supplier_id}/import/logistics")
async def import_logistics_for_supplier(supplier_id: int, file: UploadFile = File(...),
                                         current_user: User = Depends(get_current_user),
                                         db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("供应商管理"))):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    await _require_supplier_owned(db, current_user, supplier_id)
    from openpyxl import load_workbook
    data = await file.read()
    wb = load_workbook(io.BytesIO(data)); ws = wb.active
    imported, skipped, errors = 0, 0, []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]: continue
        tm = str(row[0] or "").strip()
        if tm.startswith("示例"): continue
        try:
            p = SupplierCrossBorderPrice(
                supplier_id=supplier_id,
                transport_method=str(row[0] or "").strip(),
                cargo_type=str(row[1] or "").strip() if len(row)>1 else "",
                origin_warehouse=str(row[2] or "").strip() if len(row)>2 else "",
                price_per_cbm=float(row[3] or 0) if len(row)>3 and row[3] else 0,
                estimated_days=str(row[4] or "").strip() if len(row)>4 and row[4] else None,
                currency=str(row[5] or "CNY").strip() if len(row)>5 else "CNY",
            )
            db.add(p); imported += 1
        except Exception as e:
            errors.append(f"行解析失败: {e}"); skipped += 1
    await db.flush()
    return {"imported": imported, "skipped": skipped, "errors": errors, "message": f"成功导入 {imported} 条跨境物流价格"}

# ═══ Product CRUD ════════════════════════════════
@router.get("/{supplier_id}/products")
async def list_products(supplier_id: int, current_user = Depends(get_current_user), db: AsyncSession = Depends(get_db), warehouse_id: int = Depends(current_supplier_warehouse),
    _perm=Depends(check_staff_permission("供应商管理"))):
    await _require_supplier_owned(db, current_user, supplier_id)
    supplier = await db.get(Supplier,supplier_id)
    if supplier.warehouse_id != warehouse_id:raise HTTPException(403,"只能查看当前仓库产品")
    prods = (await db.execute(select(SupplierProduct).where(SupplierProduct.supplier_id == supplier_id, SupplierProduct.catalog_active.is_not(False)).order_by(SupplierProduct.created_at.desc()))).scalars().all()
    # Price comparison: find lowest price for each product across all suppliers
    price_map = {}
    if prods:
        from collections import defaultdict
        pnames = list(set(p.product_name for p in prods))
        all_prods = (await db.execute(
            select(SupplierProduct)
            .join(Supplier, SupplierProduct.supplier_id == Supplier.id)
            .where(SupplierProduct.product_name.in_(pnames), Supplier.warehouse_id==warehouse_id, SupplierProduct.catalog_active.is_not(False))
        )).scalars().all()
        grouped = defaultdict(list)
        for ap in all_prods:
            key = (ap.product_name, ap.spec or '', ap.currency or 'THB', ap.unit)
            grouped[key].append(ap)
        sids = set()
        for key, aps in grouped.items():
            min_p = min(aps, key=lambda x: x.unit_price)
            price_map[key] = {'min_price': min_p.unit_price, 'min_supplier_id': min_p.supplier_id}
            sids.add(min_p.supplier_id)
        if sids:
            sups = (await db.execute(select(Supplier).where(Supplier.id.in_(sids)))).scalars().all()
            smap = {s.id: s.name for s in sups}
            for k, v in price_map.items():
                v['min_supplier_name'] = smap.get(v['min_supplier_id'], '')
    result = []
    for p in prods:
        key = (p.product_name, p.spec or '', p.currency or 'THB', p.unit)
        cmp = price_map.get(key) if p.unit else None
        item = {
            'id': p.id, 'product_name': p.product_name, 'spec': p.spec,
            'spec_price': p.spec_price, 'unit_price': p.unit_price,
            'currency': p.currency or "THB",
            'unit': p.unit, 'remark': p.remark,
            'comparison_basis': '同仓同名称规格、同币种及原单位参考；不等同于已核实SKU比价',
            'is_lowest': False, 'min_price': None,
            'min_supplier_name': None, 'price_diff': None,
        }
        if cmp:
            item['min_price'] = cmp['min_price']
            item['min_supplier_name'] = cmp.get('min_supplier_name', '')
            if abs(p.unit_price - cmp['min_price']) < 0.001 and p.supplier_id == cmp.get('min_supplier_id'):
                item['is_lowest'] = True
            elif p.unit_price > cmp['min_price']:
                item['price_diff'] = round(p.unit_price - cmp['min_price'], 2)
        item.update(await catalog.mapping_view(db,p,warehouse_id))
        result.append(item)
    return {'data': result}
@router.post("/{supplier_id}/products")
async def add_product(supplier_id: int, req: SupplierProductCreate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), warehouse_id: int = Depends(current_supplier_warehouse),
    _perm=Depends(check_staff_permission("供应商管理"))):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    await _require_supplier_owned(db, current_user, supplier_id)
    supplier = (await db.execute(select(Supplier).where(Supplier.id == supplier_id))).scalar_one_or_none()
    if supplier.warehouse_id != warehouse_id:raise HTTPException(403,"只能添加当前仓库产品")
    await catalog.lock(db,warehouse_id)
    d = req.model_dump()
    d["catalog_attributes"] = catalog.attributes(d.get("catalog_attributes"))
    if not d.get("currency"):
        d["currency"] = (supplier.default_currency if supplier and supplier.default_currency else "THB")
    p = SupplierProduct(supplier_id=supplier_id, **d)
    db.add(p); await db.flush()
    return {"id": p.id, "message": "添加成功"}

@router.delete("/{supplier_id}/products/{product_id}")
async def delete_product(supplier_id: int, product_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db), warehouse_id: int = Depends(current_supplier_warehouse),
    _perm=Depends(check_staff_permission("供应商管理"))):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    await _require_supplier_owned(db, current_user, supplier_id)
    await catalog.lock(db,warehouse_id)
    p = (await db.execute(select(SupplierProduct).where(SupplierProduct.id == product_id, SupplierProduct.supplier_id == supplier_id))).scalar_one_or_none()
    if not p: raise HTTPException(404, "产品不存在")
    supplier=await db.get(Supplier,supplier_id)
    if supplier.warehouse_id != warehouse_id:raise HTTPException(403,"只能停用当前仓库产品")
    before=catalog.product_state(p)
    p.catalog_active=False;p.catalog_revision=(p.catalog_revision or 0)+1
    await db.flush()
    from app.services.data_history import record_history
    await record_history(db,module='sku_catalog',record_id=p.id,operation_type='deactivate_product',operator=current_user,
        before=json.loads(json.dumps(before,default=str)),after=json.loads(json.dumps(catalog.product_state(p),default=str)),warehouse_id=warehouse_id)
    return {"message": "产品已停用，原报价、映射及订单历史保留"}
# ═══ Purchase Order ═════════════════════════════
@router.post("/{supplier_id}/purchase-order")
async def create_purchase_order(supplier_id: int, req: PurchaseOrderRequest,
                                 current_user: User = Depends(get_current_user),
                                 db: AsyncSession = Depends(get_db),
    warehouse_id: int = Depends(current_supplier_warehouse),
    _perm=Depends(check_staff_permission("供应商管理"))):
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    supplier = await _require_supplier_owned(db, current_user, supplier_id)
    wh_id = warehouse_id
    if supplier.warehouse_id != wh_id: raise HTTPException(403, "无权操作其他仓库的供应商")
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    request_key = creation.number(req.request_key, '请求编号', 100)
    await creation.creation_lock(db,wh_id)
    await catalog.lock(db,wh_id)
    request_items=[{k:v for k,v in i.model_dump().items() if k!='quote_id' or v is not None} for i in req.items]
    request_body={'supplier_id':supplier_id,'items':request_items,'remark':req.remark}
    if any(i.quote_id is not None for i in req.items) or req.pricing_version is not None or req.requirements is not None:
        request_body.update(pricing_version=req.pricing_version,requirements=req.requirements)
    signature = creation.fingerprint(request_body)
    previous = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.warehouse_id == wh_id,
        PurchaseOrder.request_key == request_key))).scalars().all()
    if len(previous)>1: raise HTTPException(409,'历史采购请求编号冲突，请管理员核对')
    if previous:
        old=previous[0]
        if old.request_fingerprint != signature: raise HTTPException(409,f'该采购请求已保存且内容不同，请查看原采购 #{old.id}；未重复新增')
        linked=await creation.active_purchase_bill(db,old)
        return {'message':'该采购请求已保存，未重复新增','replayed':True,'pending':old.status=='pending',
            'order':{'id':old.id,'order_number':old.order_number,'total_amount':old.total_amount,'items':old.items,'status':old.status},
            'payable_bill_id':linked.id if linked else None,'payable_bill_number':linked.bill_number if linked else None}
    use_quotes=any(i.quote_id is not None for i in req.items)
    if use_quotes:catalog.require_read(current_user)
    pricing=await quotes.cart_preview(db,wh_id,supplier_id,[i.model_dump() for i in req.items],req.requirements)
    if use_quotes and req.pricing_version!=pricing['version'] or req.pricing_version is not None and req.pricing_version!=pricing['version']:
        raise HTTPException(409,{'code':'quote_preview_changed','message':'数量、需求、报价或有效期已变化，请重新核对推荐；未创建采购','preview':pricing,'request_key':request_key,'not_created':True})
    if not pricing['can_order']:
        raise HTTPException(400,{'code':'quote_not_orderable','message':'所选报价或数量不满足采购条件，未创建采购','preview':pricing})
    prod_map={p.id:p for p in (await db.execute(select(SupplierProduct).where(SupplierProduct.id.in_([i.product_id for i in req.items])))).scalars()}
    order_currency=pricing['currency'];items_detail=[];total_decimal=Decimal('0');anomalies=[];non_lowest=[]
    threshold=await _get_price_threshold(db,wh_id)
    binding=price_review.review_binding(wh_id,current_user.id,request_key,supplier_id,pricing)
    try:
        reviews=price_review.restore(req.price_review_token,binding) if req.price_review_token else await price_review.evaluate(db,wh_id,pricing,prod_map,threshold)
    except HTTPException as error:
        if error.status_code!=409:raise
        # The warehouse lock and original-key lookup above prove that no order exists.
        raise HTTPException(409,{**error.detail,'code':'quote_preview_changed','preview':pricing,'request_key':request_key,'not_created':True})
    review_token=req.price_review_token or price_review.seal(reviews,binding)
    for it,row in zip(req.items,pricing['rows']):
        p=prod_map[it.product_id];price=Decimal(row['unit_price']);subtotal=Decimal(row['subtotal']);total_decimal+=subtotal
        reason=(it.reason or '').strip()
        snapshot={**row,'preview_version':pricing['version'],'evaluated_at':pricing['evaluated_at'],'selection_reason':reason,
            'amount_basis':pricing['amount_basis'],'amount_note':pricing['amount_note'],'historical_price_review':reviews[len(items_detail)]}
        historical=snapshot['historical_price_review']
        historical={**historical,'confirmed':bool(req.confirm_price_anomaly and historical['is_anomaly']),
            'confirmed_by':current_user.id if req.confirm_price_anomaly and historical['is_anomaly'] else None}
        snapshot['historical_price_review']=historical
        if historical['is_anomaly']:
            anomalies.append(historical)
        items_detail.append({'product_name':p.product_name,'spec':p.spec,'line_id':uuid4().hex,'unit':p.unit,'product_id':p.id,
            'sku_mapping':await catalog.purchase_snapshot(db,p,wh_id,it.quantity),'unit_price':row['unit_price'] if it.quote_id is not None else float(price),
            'quantity':it.quantity,'subtotal':float(subtotal),'subtotal_exact':row['subtotal'],'currency':order_currency,'reason':reason,'pricing_snapshot':snapshot})
        if row['requires_reason']:
            lowest=next(v for v in row['eligible_candidates'] if v['is_lowest']);factor=Decimal(row['selected_quote']['terms']['base_unit_factor'])
            equivalent=Decimal(row['lowest_comparable_price'])*factor
            non_lowest.append({'product_id':p.id,'product_name':p.product_name,'spec':p.spec,'unit_price':float(price),
                'lowest_price':float(equivalent),'lowest_supplier_id':lowest['supplier_id'],'lowest_supplier_name':lowest['supplier_name'],
                'price_diff':float(price-equivalent),'quantity':it.quantity,'reason':reason,'lowest_quote_ids':row['lowest']})
    if total_decimal<=0 or Decimal(str(float(total_decimal)))!=total_decimal:
        raise HTTPException(400,'采购金额小于现有金额精度或超过可精确保存范围，请核对数量或拆单')
    total=float(total_decimal)

    # 有价格异常且未确认 → 返回提示，不创建订单
    if anomalies and not req.confirm_price_anomaly:
        return {
            "need_confirm": True,
            "message": f"有 {len(anomalies)} 项产品价格超过历史参考阈值；这不是当前有效最低价或真实损失",
            "threshold": float(reviews[0]['threshold']),
            "anomalies": price_review.public_anomalies(anomalies),
            "price_review_token": review_token,
        }

    # 有非最低价但未填原因 → 返回提示，不创建订单
    missing_reason = [n for n in non_lowest if not n["reason"]]
    if missing_reason:
        return {
            "need_reason": True,
            "price_review_token": review_token,
            "message": f"有 {len(missing_reason)} 项产品非最低价，请填写采购原因",
            "non_lowest_items": [{
                "product_id": n["product_id"],
                "product_name": n["product_name"], "spec": n["spec"],
                "unit_price": n["unit_price"], "lowest_price": n["lowest_price"],
                "lowest_supplier_name": n["lowest_supplier_name"], "price_diff": n["price_diff"],
            } for n in missing_reason],
        }

    total = round(total, 2)
    now = thai_now()
    approval_threshold = await _get_approval_threshold(db, wh_id)
    is_pending = approval_threshold > 0 and total > approval_threshold
    order_number = f"PO{now.strftime('%Y%m%d%H%M%S%f')}{supplier_id}"
    po = PurchaseOrder(
        warehouse_id=wh_id, supplier_id=supplier_id,
        order_number=order_number, total_amount=total,
        currency=order_currency, items=items_detail, receipt_baseline=matching.new_baseline(items_detail),
        status="pending" if is_pending else "confirmed",
        remark=req.remark, created_by=current_user.id,
        request_key=request_key,request_fingerprint=signature,
    )
    db.add(po)
    await creation.flush_unique(db)

    # 价格历史/异常/非最低价：订单生效时才写入（直接生效立即写，待审批的等审批通过后再写）
    if not is_pending:
        await _write_price_evidence(db, po)

    bill_id = None
    bill_number = None
    if not is_pending:
        bill_number = f"PO-{order_number}"
        detail_lines = [f"- {d['product_name']} {d.get('spec') or ''} x{d['quantity']} @ {d['unit_price']} = {d['subtotal']}" for d in items_detail]
        bill = PayableBill(
            warehouse_id=wh_id, supplier_id=supplier_id,
            bill_number=bill_number, bill_date=now.replace(tzinfo=None),
            due_date=(now + timedelta(days=_parse_settlement_days(supplier.settlement_cycle))).replace(tzinfo=None),
            amount=total, currency=order_currency, status="pending",
            detail="\n".join(detail_lines),
            source="purchase_order", purchase_order_id=po.id,
            matching_kind="goods", match_lines=matching.bill_lines(items_detail),
            created_by=current_user.id,
        )
        await creation.register_purchase_bill(db,po,bill,current_user,req.duplicate_confirmation,req.cost_confirmation)
        bill_id = bill.id
    await db.flush()
    return {
        "message": "采购单已提交审批" if is_pending else "采购单已创建，应付账单已自动生成",
        "order": {"id": po.id, "order_number": order_number, "total_amount": total, "items": items_detail, "status": po.status},
        "pending": is_pending,
        "approval_threshold": approval_threshold,
        "payable_bill_id": bill_id,
        "payable_bill_number": bill_number,
        "anomalies": price_review.public_anomalies(anomalies),
    }

# ═══ 采购价格监控 ════════════════════════════
class PriceThresholdSet(BaseModel):
    threshold: float


@router.get("/price-threshold")
async def get_price_threshold(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("供应商管理"))):
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    wh_id = get_wh_id(current_user)
    threshold = await _get_price_threshold(db, wh_id) if wh_id else DEFAULT_PRICE_THRESHOLD
    return {"threshold": threshold}


@router.put("/price-threshold")
async def set_price_threshold(req: PriceThresholdSet, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("供应商管理"))):
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    if req.threshold < 0:
        raise HTTPException(400, "阈值不能为负数")
    setting = (await db.execute(
        select(SystemSetting).where(
            SystemSetting.warehouse_id == wh_id,
            SystemSetting.key == "procurement_price_threshold",
        )
    )).scalar_one_or_none()
    if setting:
        setting.value = str(req.threshold)
        setting.updated_by = current_user.id
    else:
        db.add(SystemSetting(warehouse_id=wh_id, key="procurement_price_threshold", value=str(req.threshold), updated_by=current_user.id))
    await db.flush()
    return {"message": f"价格阈值已设为 {req.threshold}%", "threshold": req.threshold}


@router.get("/price-stats")
async def price_stats(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("供应商管理"))):
    """每个产品(名+规格)的历史最低价/均价/最近采购价"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    wh_ids = get_wh_ids(current_user)
    rows = (await db.execute(
        select(ProcurementPriceHistory).where(ProcurementPriceHistory.warehouse_id.in_(wh_ids))
        .order_by(ProcurementPriceHistory.created_at.asc())
    )).scalars().all()
    grouped: dict = {}
    for r in rows:
        key = (r.product_name, r.spec or "")
        grouped.setdefault(key, []).append(r)
    data = []
    for (name, spec), items in grouped.items():
        prices = [r.unit_price for r in items]
        data.append({
            "product_name": name, "spec": spec or None,
            "lowest": round(min(prices), 2),
            "avg": round(sum(prices) / len(prices), 2),
            "last": round(items[-1].unit_price, 2),
            "count": len(prices),
        })
    data.sort(key=lambda x: x["product_name"])
    return {"data": data}


@router.get("/price-trend")
async def price_trend(product_name: str, spec: str = None,
                      current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("供应商管理"))):
    """某产品的价格变化趋势（按时间）"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    wh_ids = get_wh_ids(current_user)
    rows = (await db.execute(
        select(ProcurementPriceHistory).where(
            ProcurementPriceHistory.warehouse_id.in_(wh_ids),
            ProcurementPriceHistory.product_name == product_name,
            func.coalesce(ProcurementPriceHistory.spec, "") == (spec or ""),
        ).order_by(ProcurementPriceHistory.created_at.asc())
    )).scalars().all()
    return {"data": [{
        "id": r.id, "unit_price": r.unit_price, "quantity": r.quantity,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]}


@router.get("/price-anomalies")
async def price_anomalies(page: int = 1, page_size: int = 20,
                          current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("供应商管理"))):
    """价格异常列表（管理员/主管可见）"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    query = select(ProcurementPriceAnomaly)
    count_q = select(func.count(ProcurementPriceAnomaly.id))
    query = query.where(ProcurementPriceAnomaly.warehouse_id.in_(get_wh_ids(current_user)))
    count_q = count_q.where(ProcurementPriceAnomaly.warehouse_id.in_(get_wh_ids(current_user)))
    total = (await db.execute(count_q)).scalar()
    rows = (await db.execute(
        query.order_by(ProcurementPriceAnomaly.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {"data": [{
        "id": r.id, "product_name": r.product_name, "spec": r.spec,
        "purchase_price": r.purchase_price, "historical_avg": r.historical_avg,
        "exceed_percent": r.exceed_percent, "orderer_name": r.orderer_name,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/non-lowest-records")
async def non_lowest_records(page: int = 1, page_size: int = 50,
                             current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("供应商管理"))):
    """非最低价采购列表（按差价从大到小）"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    query = select(ProcurementNonLowestRecord)
    count_q = select(func.count(ProcurementNonLowestRecord.id))
    query = query.where(ProcurementNonLowestRecord.warehouse_id.in_(get_wh_ids(current_user)))
    count_q = count_q.where(ProcurementNonLowestRecord.warehouse_id.in_(get_wh_ids(current_user)))
    total = (await db.execute(count_q)).scalar()
    rows = (await db.execute(
        query.order_by(ProcurementNonLowestRecord.price_diff.desc(), ProcurementNonLowestRecord.created_at.desc())
        .offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return {"data": [{
        "id": r.id, "product_name": r.product_name, "spec": r.spec,
        "selected_supplier_name": r.selected_supplier_name, "selected_price": r.selected_price,
        "lowest_supplier_name": r.lowest_supplier_name, "lowest_price": r.lowest_price,
        "price_diff": r.price_diff, "quantity": r.quantity,
        "extra_amount": round(r.price_diff * r.quantity, 2),
        "reason": r.reason, "orderer_name": r.orderer_name,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/non-lowest-summary")
async def non_lowest_summary(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("供应商管理"))):
    """非最低价采购汇总：本期多花的钱合计"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    query = select(ProcurementNonLowestRecord)
    query = query.where(ProcurementNonLowestRecord.warehouse_id.in_(get_wh_ids(current_user)))
    rows = (await db.execute(query)).scalars().all()
    total_extra = round(sum(r.price_diff * r.quantity for r in rows), 2)
    return {
        "total_extra_amount": total_extra,
        "count": len(rows),
    }


# ═══ 采购审批 ════════════════════════════
class PurchaseRejectRequest(BaseModel):
    reason: str
    request_key: Optional[str] = None
    expected_policy_version: Optional[str] = None
    expected_business_version: Optional[str] = None
    exception_id: Optional[int] = None


class ApprovalThresholdSet(BaseModel):
    threshold: float


@router.get("/purchase-approval-threshold")
async def get_approval_threshold(current_user: User = Depends(check_staff_permission_any(MENU_PERMISSIONS_BY_KEY["config_center"].label, MENU_PERMISSIONS_BY_KEY["suppliers"].label)), db: AsyncSession = Depends(get_db)):
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR) and not (
        current_user.role == Role.STAFF
        and MENU_PERMISSIONS_BY_KEY["config_center"].label in (current_user.extra_permissions or [])
    ):
        raise HTTPException(403, "无权限")
    wh_id = get_wh_id(current_user)
    threshold = await _get_approval_threshold(db, wh_id)
    return {"threshold": threshold}


@router.put("/purchase-approval-threshold")
async def set_approval_threshold(req: ApprovalThresholdSet, current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["config_center"].label)), db: AsyncSession = Depends(get_db)):
    """按当前选中仓库，仓库管理员或已授权主管设置门槛。"""
    ensure_config_editor(current_user)
    if req.threshold < 0:
        raise HTTPException(400, "门槛金额不能为负数")
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    setting = (await db.execute(
        select(SystemSetting).where(
            SystemSetting.warehouse_id == wh_id,
            SystemSetting.key == "purchase_approval_threshold",
        )
    )).scalar_one_or_none()
    if setting:
        setting.value = str(req.threshold)
        setting.updated_by = current_user.id
    else:
        db.add(SystemSetting(warehouse_id=wh_id, key="purchase_approval_threshold", value=str(req.threshold), updated_by=current_user.id))
    await db.flush()
    return {"message": f"采购审批门槛已设为 {req.threshold} 泰铢", "threshold": req.threshold}


@router.get("/purchase-approvals")
async def purchase_approvals(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    warehouse_id: int = Depends(current_supplier_warehouse),
    _perm=Depends(check_staff_permission("供应商管理"))):
    """待审批采购单 + 疑似拆单提示。仓库管理员和主管可见。"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    threshold = await _get_approval_threshold(db, warehouse_id)
    wh_ids = [warehouse_id]

    # 待审批
    pquery = select(PurchaseOrder).where(PurchaseOrder.status == "pending")
    pquery = pquery.where(PurchaseOrder.warehouse_id.in_(wh_ids))
    pending_rows = (await db.execute(pquery.order_by(PurchaseOrder.created_at.desc()))).scalars().all()

    # 疑似拆单检测（同一天+同供应商+同下单人，每笔<门槛，合计>门槛）
    split_groups = []
    confirmed_rows = []
    if threshold > 0:
        cquery = select(PurchaseOrder).where(PurchaseOrder.status == "confirmed")
        cquery = cquery.where(PurchaseOrder.warehouse_id.in_(wh_ids))
        confirmed_rows = (await db.execute(cquery)).scalars().all()

    # 供应商/下单人名称映射（覆盖待审批与已确认两种订单）
    sid_set = {po.supplier_id for po in list(pending_rows) + list(confirmed_rows)}
    uid_set = {po.created_by for po in list(pending_rows) + list(confirmed_rows) if po.created_by}
    sup_map = {}
    if sid_set:
        sups = (await db.execute(select(Supplier).where(Supplier.id.in_(sid_set)))).scalars().all()
        sup_map = {s.id: s.name for s in sups}
    user_map = {}
    if uid_set:
        us = (await db.execute(select(User).where(User.id.in_(uid_set)))).scalars().all()
        user_map = {u.id: u.display_name for u in us}

    pending = [{
        "id": po.id, "order_number": po.order_number,
        "supplier_id": po.supplier_id, "supplier_name": sup_map.get(po.supplier_id, ""),
        "items": po.items or [], "total_amount": po.total_amount,
        "orderer_id": po.created_by, "orderer_name": user_map.get(po.created_by, ""),
        "created_at": po.created_at.isoformat() if po.created_at else None,
    } for po in pending_rows]

    if threshold > 0:
        groups: dict = {}
        for po in confirmed_rows:
            d = po.created_at.astimezone(THAI_TZ).date() if po.created_at else None
            key = (po.warehouse_id, d, po.supplier_id, po.created_by)
            groups.setdefault(key, []).append(po)
        for key, pos in groups.items():
            if len(pos) < 2:
                continue
            each_under = all(p.total_amount < threshold for p in pos)
            total_sum = round(sum(p.total_amount for p in pos), 2)
            if each_under and total_sum > threshold:
                sid = key[2]
                split_groups.append({
                    "date": key[1].isoformat() if key[1] else None,
                    "supplier_id": sid,
                    "supplier_name": sup_map.get(sid, ""),
                    "orderer_name": user_map.get(key[3], ""),
                    "order_count": len(pos),
                    "total_amount": total_sum,
                    "orders": [{"id": p.id, "order_number": p.order_number, "total_amount": p.total_amount} for p in pos],
                })

    return {"pending": pending, "split_groups": split_groups, "threshold": threshold}


@router.put("/purchase-approvals/{po_id}/approve")
async def approve_purchase(po_id: int, req: Optional[dict] = Body(None), current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    warehouse_id: int = Depends(current_supplier_warehouse),
    _perm=Depends(check_staff_permission("供应商管理"))):
    """审批通过：采购单生效，生成应付账单，并写入价格历史/异常/非最低价。"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    await creation.creation_lock(db,warehouse_id)
    po = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id).with_for_update())).scalar_one_or_none()
    if not po:
        raise HTTPException(404, "采购单不存在")
    if po.warehouse_id != warehouse_id:
        raise HTTPException(403, "无权审批其他仓库的采购单")
    ticket = await duty.begin(db,po,current_user,'approve',(req or {}).get('request_key'),{},req or {})
    if ticket.get('replay'): return ticket['replay']
    prior = await creation.active_purchase_bill(db,po)
    if po.status == 'confirmed' and prior:
        return {'message':'该采购已审批，未重复生成应付','replayed':True,'payable_bill_id':prior.id,'payable_bill_number':prior.bill_number}
    if po.status != "pending":
        raise HTTPException(400, "该采购单已处理")
    if po.payable_bill_id:
        raise HTTPException(400, "该采购单已生成账单，不能重复生成")
    supplier = (await db.execute(select(Supplier).where(Supplier.id == po.supplier_id))).scalar_one_or_none()
    if not supplier:
        raise HTTPException(404, "供应商不存在")
    if supplier.warehouse_id != warehouse_id: raise HTTPException(409, "采购单关联供应商的仓库不一致，请管理员核对")
    bill_number = f"PO-{po.order_number}"
    detail_lines = [f"- {d.get('product_name')} {d.get('spec') or ''} x{d.get('quantity')} @ {d.get('unit_price')} = {d.get('subtotal')}" for d in (po.items or [])]
    now = thai_now()
    bill = PayableBill(
        warehouse_id=po.warehouse_id, supplier_id=po.supplier_id,
        bill_number=bill_number, bill_date=now.replace(tzinfo=None),
        due_date=(now + timedelta(days=_parse_settlement_days(supplier.settlement_cycle))).replace(tzinfo=None),
        amount=po.total_amount, currency=po.currency or "THB", status="pending",
        detail="\n".join(detail_lines), source="purchase_order", purchase_order_id=po.id,
        matching_kind="goods", match_lines=matching.bill_lines(matching.lines(po)),
        created_by=current_user.id,
    )
    await creation.register_purchase_bill(db,po,bill,current_user,(req or {}).get('duplicate_confirmation'),(req or {}).get('cost_confirmation'))
    po.status = "confirmed"
    await db.flush()
    # 审批通过 = 订单生效，此时才写入价格历史/异常/非最低价
    await _write_price_evidence(db, po)
    return await duty.finish(db,ticket,{"message": "审批通过，应付账单已生成", "payable_bill_id": bill.id, "payable_bill_number": bill_number})


@router.put("/purchase-approvals/{po_id}/reject")
async def reject_purchase(po_id: int, req: PurchaseRejectRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    warehouse_id: int = Depends(current_supplier_warehouse),
    _perm=Depends(check_staff_permission("供应商管理"))):
    """审批驳回：采购单作废，需填原因。"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    await matching.scope_lock(db,warehouse_id)
    po = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id).with_for_update())).scalar_one_or_none()
    if not po:
        raise HTTPException(404, "采购单不存在")
    if po.warehouse_id != warehouse_id:
        raise HTTPException(403, "无权审批其他仓库的采购单")
    ticket = await duty.begin(db,po,current_user,'reject',req.request_key,{'reason':req.reason},req.model_dump())
    if ticket.get('replay'): return ticket['replay']
    if po.status != "pending":
        raise HTTPException(400, "该采购单已处理")
    if not (req.reason or "").strip():
        raise HTTPException(400, "请填写驳回原因")
    po.status = "rejected"
    po.reject_reason = req.reason.strip()
    await db.flush()
    return await duty.finish(db,ticket,{"message": "已驳回"})


# ═══ 采购收货验收 ════════════════════════════
@router.get("/purchase-orders")
async def list_purchase_orders(page: int = 1, page_size: int = 50,
                               current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    warehouse_id: int = Depends(current_supplier_warehouse),
    _perm=Depends(check_staff_permission("供应商管理"))):
    """采购单列表（含收货状态），供收货录入使用。"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    query = select(PurchaseOrder)
    count_q = select(func.count(PurchaseOrder.id))
    query = query.where(PurchaseOrder.warehouse_id == warehouse_id)
    count_q = count_q.where(PurchaseOrder.warehouse_id == warehouse_id)
    total = (await db.execute(count_q)).scalar()
    rows = (await db.execute(
        query.order_by(PurchaseOrder.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    sid_set = {po.supplier_id for po in rows}
    wid_set = {po.warehouse_id for po in rows}
    sup_map = {}
    if sid_set:
        sups = (await db.execute(select(Supplier).where(Supplier.id.in_(sid_set)))).scalars().all()
        sup_map = {s.id: s.name for s in sups}
    wh_map = {}
    if wid_set:
        from app.models.warehouse import Warehouse
        whs = (await db.execute(select(Warehouse).where(Warehouse.id.in_(wid_set)))).scalars().all()
        wh_map = {w.id: w.name for w in whs}
    return {"data": [{
        "id": po.id, "order_number": po.order_number,
        "supplier_id": po.supplier_id, "supplier_name": sup_map.get(po.supplier_id, ""),
        "warehouse_name": wh_map.get(po.warehouse_id, ""),
        "total_amount": po.total_amount, "currency": po.currency or "THB", "status": po.status,
        "flow_status": po.flow_status or "pending_confirmation",
        "sent_at": po.sent_at.isoformat() if po.sent_at else None, "sent_by": po.sent_by,
        "receipt_file": po.receipt_file,
        "receipt_uploaded_by": po.receipt_uploaded_by,
        "receipt_uploaded_at": po.receipt_uploaded_at.isoformat() if po.receipt_uploaded_at else None,
        "shipped_at": po.shipped_at.isoformat() if po.shipped_at else None, "shipped_by": po.shipped_by,
        "receipt_status": po.receipt_status or "not_received",
        "items": po.items or [], "arrival_photo": po.arrival_photo,
        "received_by": po.received_by, "received_at": po.received_at.isoformat() if po.received_at else None,
        "payable_bill_id": po.payable_bill_id,
        "created_at": po.created_at.isoformat() if po.created_at else None,
    } for po in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/purchase-orders/{po_id}", dependencies=[Depends(require_non_labor)])
async def get_purchase_detail(po_id: int, warehouse_id: int = Depends(current_supplier_warehouse),
        current_user: User = Depends(check_staff_permission_any(*(MENU_PERMISSIONS_BY_KEY[k].label
            for k in ("suppliers", "payable", "payment_plans")))), db: AsyncSession = Depends(get_db)):
    return await purchase_detail(db, po_id, warehouse_id, current_user)


@router.get("/purchase-orders/{po_id}/receipts/{event_id}/photo", dependencies=[Depends(require_non_labor)])
async def read_receipt_photo(po_id: int, event_id: int,
        current_user: User = Depends(check_staff_permission_any(*(MENU_PERMISSIONS_BY_KEY[k].label
            for k in ("suppliers","payable","payment_plans")))), warehouse_id: int = Depends(current_supplier_warehouse),
        db: AsyncSession = Depends(get_db)):
    from pathlib import Path
    from app.models import PurchaseReceiptEvent
    from app.services.supplier_payable_read import owned
    from app.api.secure_uploads import upload_root
    from fastapi.responses import FileResponse
    po=await owned(db,PurchaseOrder,po_id,warehouse_id,"采购单")
    if event_id==0: path=matching.baseline(po).get("photo_path")
    else:
        event=await db.get(PurchaseReceiptEvent,event_id)
        if event is None: raise HTTPException(404,"收货批次不存在")
        if event.warehouse_id!=warehouse_id or event.purchase_order_id!=po.id:
            raise HTTPException(403,"无权查看此收货批次照片")
        path=event.photo_path
    if not isinstance(path,str) or not path.lstrip('/').startswith('uploads/'):
        raise HTTPException(404,"历史照片路径未记录或无法安全读取")
    target=(upload_root()/path.lstrip('/')[len('uploads/'):]).resolve()
    if not target.is_relative_to(upload_root()) or not target.is_file() or target.suffix.lower() not in ('.jpg','.jpeg','.png','.webp','.pdf'):
        raise HTTPException(404,"到货照片不存在")
    return FileResponse(target,headers={"Cache-Control":"private, no-store","X-Content-Type-Options":"nosniff"})


@router.post("/purchase-orders/{po_id}/receive", dependencies=[Depends(require_non_labor)])
async def receive_purchase(po_id: int, items: str = Form(...), file: UploadFile = File(...),
                           request_key: str = Form(None), remark: str = Form(""),
                           expected_policy_version: str = Form(None), expected_business_version: str = Form(None), exception_id: int = Form(None),
                           current_user: User = Depends(check_staff_permission("供应商管理")),
                           db: AsyncSession = Depends(get_db), warehouse_id: int = Depends(current_supplier_warehouse)):
    """本次收货增量，按稳定行编号登记；请求重试不重复累计。"""
    from app.services.purchase_receiving import receive
    return await receive(db,po_id,warehouse_id,current_user,items,await file.read(),file.filename,request_key,remark,
        {'expected_policy_version':expected_policy_version,'expected_business_version':expected_business_version,'exception_id':exception_id})


@router.post("/purchase-orders/{po_id}/mark-sent")
async def mark_purchase_sent(po_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    warehouse_id: int = Depends(current_supplier_warehouse),
    _perm=Depends(check_staff_permission("供应商管理"))):
    """标记采购单已发送给供应商（记录发送时间/发送人）。"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    po = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))).scalar_one_or_none()
    if not po:
        raise HTTPException(404, "采购单不存在")
    if po.warehouse_id != warehouse_id:
        raise HTTPException(403, "无权操作其他仓库的采购单")
    po.sent_at = thai_now()
    po.sent_by = current_user.id
    await db.flush()
    return {"message": "已标记发送", "sent_at": po.sent_at.isoformat()}


@router.post("/purchase-orders/{po_id}/receipt")
async def upload_purchase_receipt(po_id: int, file: UploadFile = File(...),
                                  current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    warehouse_id: int = Depends(current_supplier_warehouse),
    _perm=Depends(check_staff_permission("供应商管理"))):
    """上传供应商签字/盖章回执，流程状态变为「供应商已确认」。"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    po = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))).scalar_one_or_none()
    if not po:
        raise HTTPException(404, "采购单不存在")
    if po.warehouse_id != warehouse_id:
        raise HTTPException(403, "无权操作其他仓库的采购单")
    if po.status != "confirmed":
        raise HTTPException(400, "仅已生效采购单可上传回执")
    import os, uuid
    from app.services.image_utils import save_image
    ext = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "jpg"
    fname = f"{uuid.uuid4().hex}.{ext}"
    result = save_image(await file.read(), "/app/uploads/receipt_files", "/uploads/receipt_files", fname)
    po.receipt_file = result["path"]
    po.receipt_uploaded_by = current_user.id
    po.receipt_uploaded_at = thai_now()
    po.flow_status = "supplier_confirmed"
    await db.flush()
    return {"message": "回执已上传，供应商已确认", "receipt_file": po.receipt_file, "flow_status": po.flow_status}


@router.post("/purchase-orders/{po_id}/mark-shipped")
async def mark_purchase_shipped(po_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    warehouse_id: int = Depends(current_supplier_warehouse),
    _perm=Depends(check_staff_permission("供应商管理"))):
    """标记供应商已发货，流程状态变为「已发货」。"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    po = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))).scalar_one_or_none()
    if not po:
        raise HTTPException(404, "采购单不存在")
    if po.warehouse_id != warehouse_id:
        raise HTTPException(403, "无权操作其他仓库的采购单")
    po.shipped_at = thai_now()
    po.shipped_by = current_user.id
    po.flow_status = "shipped"
    await db.flush()
    return {"message": "已标记发货", "flow_status": po.flow_status}


@router.get("/purchase-orders/{po_id}/pdf")
async def download_purchase_order_pdf(po_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    warehouse_id: int = Depends(current_supplier_warehouse),
    _perm=Depends(check_staff_permission("供应商管理"))):
    """下载采购单 PDF（含单号/供应商/产品明细/总价/日期/仓库/老板联系方式）。"""
    from app.models.warehouse import Warehouse
    from urllib.parse import quote
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    po = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))).scalar_one_or_none()
    if not po:
        raise HTTPException(404, "采购单不存在")
    if po.warehouse_id != warehouse_id:
        raise HTTPException(403, "无权查看其他仓库的采购单")
    supplier = (await db.execute(select(Supplier).where(Supplier.id == po.supplier_id))).scalar_one_or_none()
    wh = (await db.execute(select(Warehouse).where(Warehouse.id == po.warehouse_id))).scalar_one_or_none()
    boss = await _get_boss_contact(db)
    pdf_bytes = _build_purchase_order_pdf(po, supplier.name if supplier else "", wh.name if wh else "", boss)
    filename = f"采购单_{po.order_number}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.get("/purchase-receipt-discrepancies")
async def receipt_discrepancies(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    warehouse_id: int = Depends(current_supplier_warehouse),
    _perm=Depends(check_staff_permission("供应商管理"))):
    """收货差异列表：所有数量不符的采购。"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    query = select(PurchaseOrder).where(PurchaseOrder.receipt_status == "partially_received")
    query = query.where(PurchaseOrder.warehouse_id == warehouse_id)
    rows = (await db.execute(query.order_by(PurchaseOrder.received_at.desc()))).scalars().all()

    sid_set = {po.supplier_id for po in rows}
    uid_set = {po.received_by for po in rows if po.received_by}
    sup_map = {}
    if sid_set:
        sups = (await db.execute(select(Supplier).where(Supplier.id.in_(sid_set)))).scalars().all()
        sup_map = {s.id: s.name for s in sups}
    user_map = {}
    if uid_set:
        us = (await db.execute(select(User).where(User.id.in_(uid_set)))).scalars().all()
        user_map = {u.id: u.display_name for u in us}

    data = []
    for po in rows:
        state=await matching.receipt_state(db,po)
        for it in state['items']:
            diff=it['diff_quantity']
            if diff==0: continue
            price=matching.decimal(it.get('unit_price'))
            value=matching.amount(diff*price) if diff is not None and price is not None else None
            data.append({"purchase_order_id":po.id,"order_number":po.order_number,
                "supplier_name":sup_map.get(po.supplier_id,""),"line_id":it['line_id'],
                "product_name":it.get('product_name',""),"spec":it.get('spec'),"unit":it.get('unit'),
                "order_quantity":it.get('quantity'),"received_quantity":it['received_quantity'],
                "diff_quantity":diff,"diff_amount":float(value) if value is not None else None,
                "currency":po.currency,"quantity_status":it['quantity_status'],
                "receiver_name":user_map.get(po.received_by,""),
                "received_at":po.received_at.isoformat() if po.received_at else None})
    data.sort(key=lambda x: x.get("received_at") or "", reverse=True)
    return {"data": data}

# ═══ 供应商采购集中度分析 ════════════════════════
DEFAULT_CONCENTRATION_THRESHOLD = 70.0


async def _get_concentration_threshold(db: AsyncSession, wh_id: int | None) -> float:
    """集中度预警阈值（按仓库，回退全局旧设置作为初始值）。默认 70%。"""
    setting = None
    if wh_id is not None:
        setting = (await db.execute(
            select(SystemSetting).where(
                SystemSetting.warehouse_id == wh_id,
                SystemSetting.key == "supplier_concentration_threshold",
            )
        )).scalar_one_or_none()
    if setting is None:
        setting = (await db.execute(
            select(SystemSetting).where(
                SystemSetting.warehouse_id == 0,
                SystemSetting.key == "supplier_concentration_threshold",
            )
        )).scalar_one_or_none()
    try:
        return float(setting.value) if setting else DEFAULT_CONCENTRATION_THRESHOLD
    except (ValueError, TypeError):
        return DEFAULT_CONCENTRATION_THRESHOLD


def _month_range(month: str):
    """返回 month(YYYY-MM) 在曼谷时区的起止 datetime。"""
    y, m = map(int, month.split("-"))
    start = datetime(y, m, 1, tzinfo=THAI_TZ)
    if m == 12:
        end = datetime(y + 1, 1, 1, tzinfo=THAI_TZ)
    else:
        end = datetime(y, m + 1, 1, tzinfo=THAI_TZ)
    return start, end


async def _monthly_concentration(db: AsyncSession, wh_ids: list | None, month: str) -> dict:
    """计算某月各供应商采购金额/占比/订单数（含币种），以及总金额。"""
    start, end = _month_range(month)
    q = select(
        PurchaseOrder.supplier_id,
        PurchaseOrder.currency,
        func.sum(PurchaseOrder.total_amount).label("amount"),
        func.count(PurchaseOrder.id).label("orders"),
    ).where(
        PurchaseOrder.status == "confirmed",
        PurchaseOrder.created_at >= start,
        PurchaseOrder.created_at < end,
    )
    q = q.where(PurchaseOrder.warehouse_id.in_(wh_ids or []))
    q = q.group_by(PurchaseOrder.supplier_id, PurchaseOrder.currency)
    rows = (await db.execute(q)).all()
    total = round(sum(float(r.amount or 0) for r in rows), 2)
    sids = list({r.supplier_id for r in rows})
    smap = {}
    if sids:
        sups = (await db.execute(select(Supplier).where(Supplier.id.in_(sids)))).scalars().all()
        smap = {s.id: s.name for s in sups}
    by_sup: dict = {}
    for r in rows:
        acc = by_sup.setdefault(r.supplier_id, {"amount": 0.0, "orders": 0, "currencies": set()})
        acc["amount"] += float(r.amount or 0)
        acc["orders"] += int(r.orders or 0)
        acc["currencies"].add(r.currency or "THB")
    data = []
    for sid, acc in by_sup.items():
        cur = acc["currencies"].pop() if len(acc["currencies"]) == 1 else "mixed"
        pct = round(acc["amount"] / total * 100, 2) if total > 0 else 0.0
        data.append({
            "supplier_id": sid,
            "supplier_name": smap.get(sid, ""),
            "amount": round(acc["amount"], 2),
            "currency": cur,
            "percent": pct,
            "order_count": acc["orders"],
        })
    data.sort(key=lambda x: x["amount"], reverse=True)
    return {"total": total, "data": data}


class ConcentrationThresholdSet(BaseModel):
    threshold: float


@router.get("/concentration-threshold")
async def get_concentration_threshold(current_user: User = Depends(check_staff_permission_any(_CONCENTRATION_PERMISSION, MENU_PERMISSIONS_BY_KEY["config_center"].label)), db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    wh_id = get_wh_id(current_user)
    return {"threshold": await _get_concentration_threshold(db, wh_id)}


@router.put("/concentration-threshold")
async def set_concentration_threshold(req: ConcentrationThresholdSet,
                                      current_user: User = Depends(check_staff_permission(MENU_PERMISSIONS_BY_KEY["config_center"].label)), db: AsyncSession = Depends(get_db)):
    ensure_config_editor(current_user)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    setting = (await db.execute(
        select(SystemSetting).where(
            SystemSetting.warehouse_id == wh_id,
            SystemSetting.key == "supplier_concentration_threshold",
        )
    )).scalar_one_or_none()
    if setting:
        setting.value = str(req.threshold)
    else:
        db.add(SystemSetting(warehouse_id=wh_id, key="supplier_concentration_threshold",
                             value=str(req.threshold), updated_by=current_user.id))
    await db.flush()
    return {"message": "集中度预警阈值已保存", "threshold": req.threshold}


@router.get("/concentration")
async def concentration_analysis(month: str = None,
                                 current_user: User = Depends(check_staff_permission(_CONCENTRATION_PERMISSION)), db: AsyncSession = Depends(get_db)):
    """供应商采购集中度：按月统计各供应商采购金额/占比/订单数。"""
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    if not month:
        month = thai_today().strftime("%Y-%m")
    try:
        _y, _m = map(int, month.split("-"))
        if not (1 <= _m <= 12):
            raise ValueError
    except Exception:
        raise HTTPException(400, "月份格式应为 YYYY-MM")
    wh_ids = get_wh_ids(current_user)
    res = await _monthly_concentration(db, wh_ids, month)
    threshold = await _get_concentration_threshold(db, get_wh_id(current_user))
    top = res["data"][0] if res["data"] else None
    alert = None
    if top and top["percent"] > threshold:
        alert = {
            "supplier_name": top["supplier_name"],
            "percent": top["percent"],
            "threshold": threshold,
            "message": f"{top['supplier_name']} 本月采购占比 {top['percent']}%，超过 {threshold}%，注意核查",
        }
    return {"month": month, "threshold": threshold, "total": res["total"],
            "data": res["data"], "alert": alert}


@router.get("/concentration-trend")
async def concentration_trend(months: int = 6,
                              current_user: User = Depends(check_staff_permission(_CONCENTRATION_PERMISSION)), db: AsyncSession = Depends(get_db)):
    """集中度趋势：最近 N 个月最高供应商占比变化。"""
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    try:
        months = max(1, min(int(months), 24))
    except (ValueError, TypeError):
        months = 6
    wh_ids = get_wh_ids(current_user)
    today = thai_today()
    trend = []
    for i in range(months - 1, -1, -1):
        total_months = today.year * 12 + (today.month - 1) - i
        yy, mm0 = divmod(total_months, 12)
        month_str = f"{yy:04d}-{mm0 + 1:02d}"
        res = await _monthly_concentration(db, wh_ids, month_str)
        top = res["data"][0] if res["data"] else None
        trend.append({
            "month": month_str,
            "total": res["total"],
            "supplier_count": len(res["data"]),
            "top_supplier_name": top["supplier_name"] if top else None,
            "top_percent": top["percent"] if top else 0.0,
            "top_order_count": top["order_count"] if top else 0,
        })
    return {"data": trend}

# ═══ Logistics Price CRUD ════════════════════════
@router.get("/{supplier_id}/logistics-prices")
async def list_logistics_prices(supplier_id: int, current_user = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("供应商管理"))):
    await _require_supplier_owned(db, current_user, supplier_id)
    prices = (await db.execute(select(SupplierCrossBorderPrice).where(SupplierCrossBorderPrice.supplier_id == supplier_id).order_by(SupplierCrossBorderPrice.transport_method, SupplierCrossBorderPrice.origin_warehouse))).scalars().all()
    return {"data": [{"id": p.id, "transport_method": p.transport_method, "cargo_type": p.cargo_type,
                      "origin_warehouse": p.origin_warehouse, "price_per_cbm": p.price_per_cbm,
                      "estimated_days": p.estimated_days, "currency": p.currency} for p in prices]}

@router.post("/{supplier_id}/logistics-prices")
async def add_logistics_price(supplier_id: int, req: dict, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("供应商管理"))):
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    await _require_supplier_owned(db, current_user, supplier_id)
    p = SupplierCrossBorderPrice(supplier_id=supplier_id, **req)
    db.add(p); await db.flush()
    return {"id": p.id, "message": "添加成功"}

@router.delete("/{supplier_id}/logistics-prices/{price_id}")
async def delete_logistics_price(supplier_id: int, price_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("供应商管理"))):
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    await _require_supplier_owned(db, current_user, supplier_id)
    p = (await db.execute(select(SupplierCrossBorderPrice).where(SupplierCrossBorderPrice.id == price_id, SupplierCrossBorderPrice.supplier_id == supplier_id))).scalar_one_or_none()
    if not p: raise HTTPException(404, "不存在")
    await db.delete(p); await db.flush()
    return {"message": "删除成功"}

# ═══ Price Comparison ════════════════════════════
@router.get("/compare-prices")
async def compare_prices(product_name: str = None, spec: str = None, category_id: int = None,
                          current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("供应商管理"))):
    """耗材比价：按产品名称/规格对比同类别供应商报价"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    q = select(SupplierProduct).join(Supplier, SupplierProduct.supplier_id == Supplier.id).where(Supplier.is_active == "true")
    if product_name:
        q = q.where(SupplierProduct.product_name.ilike(f"%{product_name}%"))
    if spec:
        q = q.where(SupplierProduct.spec.ilike(f"%{spec}%"))
    if category_id:
        q = q.where(Supplier.category_id == category_id)
    elif category_id == 0:
        pass
    else:
        # Default: consumables (category 1)
        pass
    q = q.where(Supplier.warehouse_id.in_(get_wh_ids(current_user)))
    prods = (await db.execute(q.order_by(SupplierProduct.unit_price.asc()))).scalars().all()
    sids = list({p.supplier_id for p in prods})
    smap = {}
    if sids:
        sups = (await db.execute(select(Supplier).where(Supplier.id.in_(sids)))).scalars().all()
        smap = {s.id: s for s in sups}
    result = []
    for p in prods:
        s = smap.get(p.supplier_id)
        cat_name = ""
        if s and s.category_id:
            cat = (await db.execute(select(SupplierCategory).where(SupplierCategory.id == s.category_id))).scalar_one_or_none()
            if cat: cat_name = cat.name
        result.append({
            "product_id": p.id, "supplier_id": p.supplier_id, "supplier_name": s.name if s else "",
            "category_name": cat_name, "product_name": p.product_name, "spec": p.spec,
            "spec_price": p.spec_price, "unit_price": p.unit_price, "currency": p.currency or "THB", "unit": p.unit, "remark": p.remark,
        })
    return {"data": result, "total": len(result)}

@router.get("/compare-logistics")
async def compare_logistics(transport_method: str = None, cargo_type: str = None, origin_warehouse: str = None,
                             category_id: int = None,
                             current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("供应商管理"))):
    """跨境物流比价：运输方式×货物类型×发货仓库，含义乌加价和最低消费"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    # 海运最低0.5方，陆运最低0.3方
    MIN_CBM = {"海运": 0.5, "陆运": 0.3}
    YIWU_MARKUP = 120  # 义乌仓加价每方120元
    HEAVY_CARGO_THRESHOLD = 500  # 单方超500kg算重货

    q = select(SupplierCrossBorderPrice).join(Supplier, SupplierCrossBorderPrice.supplier_id == Supplier.id).where(Supplier.is_active == "true")
    if transport_method:
        q = q.where(SupplierCrossBorderPrice.transport_method == transport_method)
    if cargo_type:
        q = q.where(SupplierCrossBorderPrice.cargo_type == cargo_type)
    # 查询时：如果筛选义乌仓，同时查深圳仓和广州仓（做加价计算用）
    is_yiwu = origin_warehouse and "义乌" in origin_warehouse
    if origin_warehouse:
        if is_yiwu:
            # 查义乌+深圳+广州的所有报价
            q = q.where(SupplierCrossBorderPrice.origin_warehouse.in_(["深圳仓", "广州仓", "义乌仓"]))
        else:
            q = q.where(SupplierCrossBorderPrice.origin_warehouse == origin_warehouse)
    if category_id:
        q = q.where(Supplier.category_id == category_id)
    q = q.where(Supplier.warehouse_id.in_(get_wh_ids(current_user)))
    prices = (await db.execute(q.order_by(SupplierCrossBorderPrice.price_per_cbm.asc()))).scalars().all()
    sids = list({p.supplier_id for p in prices})
    smap = {}
    if sids:
        sups = (await db.execute(select(Supplier).where(Supplier.id.in_(sids)))).scalars().all()
        smap = {s.id: s for s in sups}

    # 构建按 supplier 分组的价格映射
    # key: (supplier_id, transport_method, cargo_type)
    price_map = {}  # {(sid, tm, ct): {warehouse: price}}
    for p in prices:
        key = (p.supplier_id, p.transport_method, p.cargo_type)
        if key not in price_map:
            price_map[key] = {}
        price_map[key][p.origin_warehouse] = {"price_per_cbm": p.price_per_cbm, "price_id": p.id, "estimated_days": p.estimated_days}

    # Build results
    min_cbm = MIN_CBM.get(transport_method or "陆运", 0.3)
    seen = set()
    result = []
    for p in prices:
        key = (p.supplier_id, p.transport_method, p.cargo_type)
        if key in seen: continue
        seen.add(key)
        s = smap.get(p.supplier_id)
        if not s: continue

        # Determine final price
        final_price = p.price_per_cbm
        price_note = ""
        actual_warehouse = p.origin_warehouse

        if is_yiwu:
            pw_map = price_map.get(key, {})
            if "义乌仓" in pw_map:
                final_price = pw_map["义乌仓"]["price_per_cbm"]
                actual_warehouse = "义乌仓"
            elif "深圳仓" in pw_map:
                final_price = pw_map["深圳仓"]["price_per_cbm"] + YIWU_MARKUP
                actual_warehouse = "义乌仓(深圳仓+120)"
                price_note = f"无义乌仓报价，用深圳仓价格+{YIWU_MARKUP}元/方"
            elif "广州仓" in pw_map:
                final_price = pw_map["广州仓"]["price_per_cbm"] + YIWU_MARKUP
                actual_warehouse = "义乌仓(广州仓+120)"
                price_note = f"无义乌仓报价，用广州仓价格+{YIWU_MARKUP}元/方"

        min_amount = round(final_price * min_cbm, 2)
        cat_name = ""
        if s.category_id:
            cat = (await db.execute(select(SupplierCategory).where(SupplierCategory.id == s.category_id))).scalar_one_or_none()
            if cat: cat_name = cat.name
        result.append({
            "price_id": p.id, "supplier_id": p.supplier_id, "supplier_name": s.name,
            "category_name": cat_name,
            "transport_method": p.transport_method, "cargo_type": p.cargo_type,
            "origin_warehouse": actual_warehouse,
            "price_per_cbm": final_price, "price_note": price_note,
            "min_cbm": min_cbm, "min_amount": min_amount,
            "estimated_days": p.estimated_days, "currency": p.currency,
            "heavy_cargo_warning": "单方超500kg按重货计费" if transport_method == "陆运" else "",
        })

    # Sort by final price
    result.sort(key=lambda x: x["price_per_cbm"])
    return {"data": result, "total": len(result), "yiwu_markup": YIWU_MARKUP, "min_cbm": min_cbm}

# ═══ AI Price Analysis ═══════════════════════════
@router.post("/ai-compare")
async def ai_compare(data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(check_staff_permission("供应商管理"))):
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    from app.config import get_settings
    settings = get_settings()
    if not settings.DEEPSEEK_API_KEY:
        return {"result": "DeepSeek API Key 未配置，无法执行AI比价分析"}
    compare_data = data.get("compare_data", [])
    mode = data.get("mode", "product")  # product or logistics
    if not compare_data:
        return {"result": "无比价数据，请先执行比价查询"}
    if mode == "logistics":
        rows_text = "\n".join([f"- {r['supplier_name']}: {r['route_name']} {r['cargo_type']} 起步价{r['starting_price']} 每公斤{r['price_per_kg']} 时效{r.get('estimated_days','?')}" for r in compare_data])
    else:
        rows_text = "\n".join([f"- {r['supplier_name']}: {r['product_name']} {r['spec'] or ''} 单价{r['unit_price']}{r.get('unit','个')}" for r in compare_data])
    prompt = f"""请对以下供应商报价进行比价分析：
{rows_text}

请从以下维度分析：
1. 价格排名：从低到高列出各供应商
2. 性价比评估：综合考虑价格和已知信息
3. 推荐结论：建议选择哪家供应商及理由"""
    try:
        import httpx
        from openai import AsyncOpenAI
        client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            http_client=httpx.AsyncClient(timeout=60.0),
        )
        resp = await client.chat.completions.create(model="deepseek-chat", messages=[{"role":"user","content": prompt}])
        return {"result": resp.choices[0].message.content}
    except Exception as e:
        return {"result": f"AI分析失败: {str(e)}"}

# ═══ Supplier CRUD ══════════════════════════════
@router.get("")
async def list_suppliers(page: int = 1, page_size: int = 20, search: str = None,
                         category_id: int = None,
                         current_user: User = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db), warehouse_id: int = Depends(current_supplier_warehouse)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(Supplier); count_q = select(func.count(Supplier.id))
    query = query.where(Supplier.warehouse_id == warehouse_id)
    count_q = count_q.where(Supplier.warehouse_id == warehouse_id)
    if search:
        query = query.where(Supplier.name.ilike(f"%{search}%")); count_q = count_q.where(Supplier.name.ilike(f"%{search}%"))
    if category_id:
        query = query.where(Supplier.category_id == category_id)
        count_q = count_q.where(Supplier.category_id == category_id)
    total = (await db.execute(count_q)).scalar()
    result = await db.execute(query.order_by(Supplier.created_at.desc()).offset((page-1)*page_size).limit(page_size))
    suppliers = result.scalars().all()
    cat_ids = {s.category_id for s in suppliers if s.category_id}
    cat_map = {}
    if cat_ids:
        cats = (await db.execute(select(SupplierCategory).where(SupplierCategory.id.in_(cat_ids)))).scalars().all()
        cat_map = {c.id: c.name for c in cats}
    return {"data": [{"id": s.id, "name": s.name, "contact_person": s.contact_person, "contact_info": s.contact_info,
                      "address": s.address, "payment_terms": s.payment_terms,
                      "cooperation_content": s.cooperation_content,
                      "settlement_cycle": s.settlement_cycle,
                      "default_currency": s.default_currency or "THB",
                      "history_notes": s.history_notes,
                      "ai_evaluation": s.ai_evaluation,
                      "category_id": s.category_id,
                      "category_name": cat_map.get(s.category_id, ""),
                      "is_active": s.is_active} for s in suppliers],
            "total": total, "page": page, "page_size": page_size}

@router.post("")
async def create_supplier(req: SupplierCreate, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("供应商管理"))):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    d = req.model_dump()
    d["default_currency"] = (d.get("default_currency") or "THB")
    s = Supplier(warehouse_id=get_wh_id(current_user), **d)
    db.add(s); await db.flush(); return {"id": s.id, "message": "创建成功"}

@router.put("/{supplier_id}", dependencies=[Depends(require_non_labor)])
async def update_supplier(supplier_id: int, req: SupplierUpdate,
                          current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("供应商管理"))):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    s = result.scalar_one_or_none()
    if not s: raise HTTPException(404, "供应商不存在")
    if current_user.role != Role.SUPER_ADMIN and s.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "只能修改自己仓库的供应商")
    await catalog.lock(db,s.warehouse_id)
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    await db.flush(); return {"message": "更新成功"}

@router.delete("/{supplier_id}", dependencies=[Depends(require_non_labor)])
async def delete_supplier(supplier_id: int, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("供应商管理"))):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    s = result.scalar_one_or_none()
    if not s: raise HTTPException(404, "供应商不存在")
    if current_user.role != Role.SUPER_ADMIN and s.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "只能删除自己仓库的供应商")
    await catalog.lock(db,s.warehouse_id)
    from app.models import ProductSkuMappingEvent,SupplierTagLink,SupplierQuote
    quoted=(await db.execute(select(SupplierQuote.id).join(SupplierProduct,SupplierQuote.product_id==SupplierProduct.id).where(SupplierProduct.supplier_id==s.id).limit(1))).first()
    mapped=(await db.execute(select(ProductSkuMappingEvent.id).join(SupplierProduct,ProductSkuMappingEvent.product_id==SupplierProduct.id).where(SupplierProduct.supplier_id==s.id).limit(1))).first()
    tagged=(await db.execute(select(SupplierTagLink.id).where(SupplierTagLink.supplier_id==s.id).limit(1))).first()
    if mapped or tagged or quoted:raise HTTPException(409,"供应商存在SKU映射、报价或仓内标签引用，不能硬删除；请保留历史并停用")
    await db.delete(s); await db.flush()
    return {"message": "删除成功"}

@router.get("/procurement-summary")
async def procurement_summary(current_user: User = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("供应商管理"))):
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    from app.models.payable import PayableBill
    from app.models.warehouse import Warehouse
    from datetime import date, timedelta
    from sqlalchemy import extract

    today = thai_today()
    this_month_start = today.replace(day=1)
    last_month_start = (this_month_start - timedelta(days=1)).replace(day=1)
    last_month_end = this_month_start - timedelta(days=1)

    def wh_filter(q):
        return q.where(PayableBill.warehouse_id.in_(get_wh_ids(current_user)),
                       PayableBill.status != "voided")

    def bill_filter(q):
        # 采购金额口径：排除已作废账单，且只统计已生效(confirmed)采购单对应的账单（手动账单无采购单，保留）
        return (q.outerjoin(PurchaseOrder, PayableBill.purchase_order_id == PurchaseOrder.id)
                 .where((PayableBill.purchase_order_id.is_(None)) | (PurchaseOrder.status == "confirmed")))

    def _by_currency(rows):
        out: dict = {}
        for r in rows:
            out[r.currency or "THB"] = float(r.total or 0)
        return out

    # --- 本月支出按币种 ---
    month_q = wh_filter(bill_filter(select(PayableBill.currency, func.sum(PayableBill.amount).label("total"))
        .where(extract("year", PayableBill.bill_date) == today.year, extract("month", PayableBill.bill_date) == today.month)
        .group_by(PayableBill.currency)))
    month_total_by_currency = _by_currency((await db.execute(month_q)).all())

    # --- 上月支出按币种 ---
    last_q = wh_filter(bill_filter(select(PayableBill.currency, func.sum(PayableBill.amount).label("total"))
        .where(extract("year", PayableBill.bill_date) == last_month_start.year, extract("month", PayableBill.bill_date) == last_month_start.month)
        .group_by(PayableBill.currency)))
    last_month_total_by_currency = _by_currency((await db.execute(last_q)).all())

    # --- 本月分类支出按币种 ---
    cat_month_q = wh_filter(bill_filter(select(Supplier.category_id, PayableBill.currency, func.sum(PayableBill.amount).label("total"))
        .join(Supplier, PayableBill.supplier_id == Supplier.id)
        .where(extract("year", PayableBill.bill_date) == today.year, extract("month", PayableBill.bill_date) == today.month)
        .group_by(Supplier.category_id, PayableBill.currency)))
    cat_rows = (await db.execute(cat_month_q)).all()
    cat_map = {}
    cat_ids = [r.category_id for r in cat_rows if r.category_id]
    if cat_ids:
        cats = (await db.execute(select(SupplierCategory).where(SupplierCategory.id.in_(cat_ids)))).scalars().all()
        cat_map = {c.id: c.name for c in cats}
    cat_spending: dict = {}
    for r in cat_rows:
        name = cat_map.get(r.category_id, "未分类")
        cat_spending.setdefault(name, {})[r.currency or "THB"] = float(r.total or 0)

    # --- 供应商排名按币种 ---
    sup_q = wh_filter(bill_filter(select(PayableBill.supplier_id, PayableBill.currency, func.sum(PayableBill.amount).label("total"), func.max(PayableBill.bill_date).label("last_date"))
        .group_by(PayableBill.supplier_id, PayableBill.currency)))
    sup_rows = (await db.execute(sup_q)).all()
    sup_month_q = wh_filter(bill_filter(select(PayableBill.supplier_id, PayableBill.currency, func.sum(PayableBill.amount).label("total"))
        .where(extract("year", PayableBill.bill_date) == today.year, extract("month", PayableBill.bill_date) == today.month)
        .group_by(PayableBill.supplier_id, PayableBill.currency)))
    sup_month_rows = (await db.execute(sup_month_q)).all()

    sids = list({r.supplier_id for r in sup_rows})
    smap = {}
    if sids:
        sups = (await db.execute(select(Supplier).where(Supplier.id.in_(sids)))).scalars().all()
        cat_ids2 = {s.category_id for s in sups if s.category_id}
        cat2 = {}
        if cat_ids2:
            crows = (await db.execute(select(SupplierCategory).where(SupplierCategory.id.in_(cat_ids2)))).scalars().all()
            cat2 = {c.id: c.name for c in crows}
        smap = {s.id: {"name": s.name, "category": cat2.get(s.category_id, "")} for s in sups}

    sup_total: dict = {}
    sup_last: dict = {}
    for r in sup_rows:
        sup_total.setdefault(r.supplier_id, {})[r.currency or "THB"] = float(r.total or 0)
        if r.last_date and (r.supplier_id not in sup_last or r.last_date > sup_last[r.supplier_id]):
            sup_last[r.supplier_id] = r.last_date
    sup_month: dict = {}
    for r in sup_month_rows:
        sup_month.setdefault(r.supplier_id, {})[r.currency or "THB"] = float(r.total or 0)

    supplier_ranking = []
    for sid in sorted(sup_total, key=lambda x: -sum(sup_total[x].values())):
        info = smap.get(sid, {"name": "", "category": ""})
        supplier_ranking.append({
            "supplier_id": sid, "supplier_name": info["name"], "category_name": info["category"],
            "month_amount_by_currency": sup_month.get(sid, {}),
            "total_amount_by_currency": sup_total.get(sid, {}),
            "last_bill_date": sup_last.get(sid).isoformat()[:10] if sup_last.get(sid) else None,
        })

    # --- 产品比价汇总按币种 ---
    prod_q = wh_filter(select(SupplierProduct.product_name, SupplierProduct.spec, SupplierProduct.currency,
        func.count(SupplierProduct.supplier_id.distinct()).label("supplier_count"),
        func.min(SupplierProduct.unit_price).label("min_price"),
        func.max(SupplierProduct.unit_price).label("max_price"))
        .join(Supplier, SupplierProduct.supplier_id == Supplier.id)
        .group_by(SupplierProduct.product_name, SupplierProduct.spec, SupplierProduct.currency)
        .order_by(SupplierProduct.product_name))
    prod_rows = (await db.execute(prod_q)).all()
    product_compare = []
    for p in prod_rows:
        if not p.product_name:
            continue
        cur = p.currency or "THB"
        min_sup_q = wh_filter(select(SupplierProduct.supplier_id, Supplier.name)
            .join(Supplier, SupplierProduct.supplier_id == Supplier.id)
            .where(SupplierProduct.product_name == p.product_name, SupplierProduct.spec == p.spec,
                   func.coalesce(SupplierProduct.currency, "THB") == cur,
                   SupplierProduct.unit_price == p.min_price))
        min_sup = (await db.execute(min_sup_q)).first()
        product_compare.append({
            "product_name": p.product_name, "spec": p.spec, "currency": cur,
            "supplier_count": p.supplier_count,
            "min_price": float(p.min_price) if p.min_price else 0,
            "max_price": float(p.max_price) if p.max_price else 0,
            "min_supplier": min_sup[1] if min_sup else "",
        })

    # --- 省钱提示按币种 ---
    savings_tips = []
    for prod in product_compare:
        if prod["supplier_count"] >= 2 and prod["max_price"] > prod["min_price"]:
            diff = round(prod["max_price"] - prod["min_price"], 2)
            sym = "¥" if prod["currency"] == "CNY" else "฿"
            savings_tips.append({
                "product_name": prod["product_name"], "spec": prod["spec"], "currency": prod["currency"],
                "cheapest_price": prod["min_price"], "cheapest_supplier": prod["min_supplier"],
                "highest_price": prod["max_price"],
                "savings_per_unit": diff,
                "tip": f"{prod['product_name']}{prod['spec'] or ''}：最便宜 {prod['min_supplier']} {sym}{prod['min_price']}，最贵 {sym}{prod['max_price']}，用便宜的可省 {sym}{diff}/件",
            })

    return {
        "overview": {
            "month_total_by_currency": month_total_by_currency,
            "last_month_total_by_currency": last_month_total_by_currency,
            "cat_spending": cat_spending,
        },
        "supplier_ranking": supplier_ranking,
        "product_compare": product_compare,
        "savings_tips": savings_tips,
    }

@router.get("/{supplier_id}")
async def get_supplier(supplier_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("供应商管理"))):
    _forbid_super_admin(current_user)
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    s = result.scalar_one_or_none()
    if not s: raise HTTPException(404, "供应商不存在")
    if s.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "只能查看自己仓库的供应商")
    cat_name = ""
    if s.category_id:
        cat = (await db.execute(select(SupplierCategory).where(SupplierCategory.id == s.category_id))).scalar_one_or_none()
        if cat: cat_name = cat.name
    return {"id": s.id, "name": s.name, "contact_person": s.contact_person, "contact_info": s.contact_info,
            "address": s.address, "payment_terms": s.payment_terms,
            "cooperation_content": s.cooperation_content,
            "settlement_cycle": s.settlement_cycle,
            "default_currency": s.default_currency or "THB",
            "history_notes": s.history_notes,
            "ai_evaluation": s.ai_evaluation,
            "category_id": s.category_id, "category_name": cat_name}

@router.get("/{supplier_id}/ai-evaluation")
async def ai_evaluate(supplier_id: int, current_user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db),
    _perm=Depends(check_staff_permission("供应商管理"))):
    if current_user.role != Role.SUPER_ADMIN:
        raise HTTPException(403, "仅超级管理员可用")
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    s = result.scalar_one_or_none()
    if not s: raise HTTPException(404, "供应商不存在")
    from app.config import get_settings
    settings = get_settings()
    if settings.DEEPSEEK_API_KEY:
        try:
            import httpx
            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=settings.DEEPSEEK_API_KEY,
                base_url=settings.DEEPSEEK_BASE_URL,
                http_client=httpx.AsyncClient(timeout=60.0),
            )
            resp = await client.chat.completions.create(model="deepseek-chat", messages=[{"role":"user",
                "content":f"评估供应商：{s.name}，联系方式：{s.contact_info or '无'}，地址：{s.address or '无'}。请从信誉、价格竞争力、交付及时性三个维度简要评估。"}])
            evaluation = {"result": resp.choices[0].message.content}
            s.ai_evaluation = evaluation
        except Exception as e:
            evaluation = {"error": str(e)}
    else:
        evaluation = {"result": "DeepSeek API Key 未配置，无法执行AI评估"}
    if not s.ai_evaluation:
        s.ai_evaluation = evaluation
    await db.flush()
    return evaluation
