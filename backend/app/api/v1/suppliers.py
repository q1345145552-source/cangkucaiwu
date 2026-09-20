from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.models.supplier import Supplier, SupplierCategory, SupplierProduct, SupplierLogisticsPrice, SupplierCrossBorderPrice, PurchaseOrder, ProcurementPriceHistory, ProcurementPriceAnomaly, ProcurementNonLowestRecord
from app.models.user import User
from app.models.payable import PayableBill
from app.models.expense_fund import SystemSetting
from app.core.permissions import get_current_user, get_wh_id, get_wh_ids, Role
from pydantic import BaseModel
from typing import Optional, List
from app.core.timezone import thai_now, thai_today, THAI_TZ
from datetime import datetime, timedelta
from app.schemas.business import SupplierCreate, SupplierUpdate, SupplierResponse, SupplierProductCreate
import io

router = APIRouter()


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


async def _get_approval_threshold(db: AsyncSession) -> float:
    """采购审批金额门槛（全局，老板设置）。0 表示无需审批。"""
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


async def _get_price_history(db: AsyncSession, wh_id: int, product_name: str, spec: str | None) -> list:
    rows = (await db.execute(
        select(ProcurementPriceHistory).where(
            ProcurementPriceHistory.warehouse_id == wh_id,
            ProcurementPriceHistory.product_name == product_name,
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


async def _get_lowest_quote(db: AsyncSession, product_name: str, spec: str | None, wh_id: int) -> dict | None:
    """某产品(名+规格)在本仓库内的最低报价（含最低价供应商名）。仅限本仓库，避免跨仓泄露。"""
    rows = (await db.execute(
        select(SupplierProduct, Supplier)
        .join(Supplier, Supplier.id == SupplierProduct.supplier_id)
        .where(
            SupplierProduct.product_name == product_name,
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
    product_id: int
    quantity: int = 1
    reason: Optional[str] = None  # 非最低价采购原因

class PurchaseOrderRequest(BaseModel):
    items: List[PurchaseOrderItem]
    remark: Optional[str] = None
    confirm_price_anomaly: bool = False  # 是否确认价格偏高后提交


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

        hist_rows = await _get_price_history(db, wh_id, product_name, spec)
        if hist_rows:
            avg = sum(r.unit_price for r in hist_rows) / len(hist_rows)
            if avg > 0 and unit_price > avg * (1 + threshold / 100.0):
                exceed = round((unit_price - avg) / avg * 100.0, 1)
                anomalies.append({
                    "product_name": product_name, "spec": spec,
                    "unit_price": unit_price, "historical_avg": round(avg, 2),
                    "exceed_percent": exceed,
                })

        lowest = await _get_lowest_quote(db, product_name, spec, wh_id)
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
            quantity=quantity, created_by=orderer_id,
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
async def list_categories(current_user = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    cats = (await db.execute(select(SupplierCategory).where(SupplierCategory.is_active == "true").order_by(SupplierCategory.sort_order))).scalars().all()
    return {"data": [{"id": c.id, "name": c.name} for c in cats]}

@router.post("/categories")
async def create_category(name: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    c = SupplierCategory(name=name)
    db.add(c); await db.flush()
    return {"id": c.id, "name": c.name, "message": "创建成功"}

# ═══ Import Templates ════════════════════════════
@router.get("/import-template/products")
async def download_products_template(current_user: User = Depends(get_current_user)):
    """下载耗材产品导入模板"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    wb = Workbook(); ws = wb.active; ws.title = "耗材产品导入"
    hfill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    hfont = Font(bold=True, color="FFFFFF")
    for c, h in enumerate(["供应商名称", "产品名", "产品规格", "规格报价", "单价"], 1):
        cell = ws.cell(row=1, column=c, value=h); cell.font = hfont; cell.fill = hfill
    for c, v in enumerate(["示例: 耗材商A", "快递袋", "一打80个", 80, 1], 1):
        ws.cell(row=2, column=c, value=v)
    for col, w in [('A',20),('B',16),('C',16),('D',12),('E',12)]:
        ws.column_dimensions[col].width = w
    output = io.BytesIO(); wb.save(output); output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            headers={"Content-Disposition": "attachment; filename=products_import_template.xlsx"})

@router.get("/import-template/logistics")
async def download_logistics_template(current_user: User = Depends(get_current_user)):
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
async def import_products(file: UploadFile = File(...), current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    """批量导入耗材产品 Excel"""
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    from openpyxl import load_workbook
    content = await file.read()
    wb = load_workbook(io.BytesIO(content)); ws = wb.active
    imported, skipped, errors = 0, 0, []
    # Resolve supplier name→id for this warehouse
    sups = (await db.execute(select(Supplier).where(Supplier.warehouse_id.in_(get_wh_ids(current_user))))).scalars().all()
    sup_map = {s.name.strip(): s.id for s in sups}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]: continue
        sup_name = str(row[0]).strip()
        if sup_name.startswith("示例"): continue
        if sup_name not in sup_map:
            errors.append(f"供应商「{sup_name}」不存在"); skipped += 1; continue
        try:
            p = SupplierProduct(
                supplier_id=sup_map[sup_name],
                product_name=str(row[1] or "").strip(),
                spec=str(row[2] or "").strip() if row[2] else None,
                spec_price=float(row[3] or 0) if row[3] else None,
                unit_price=float(row[4] or 0),
            )
            db.add(p); imported += 1
        except Exception as e:
            errors.append(f"行解析失败: {e}"); skipped += 1
    await db.flush()
    return {"imported": imported, "skipped": skipped, "errors": errors, "message": f"成功导入 {imported} 条产品"}

@router.post("/import/logistics")
async def import_logistics(file: UploadFile = File(...), current_user: User = Depends(get_current_user),
                            db: AsyncSession = Depends(get_db)):
    """批量导入跨境物流价格 Excel"""
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
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
async def import_products_for_supplier(supplier_id: int, file: UploadFile = File(...),
                                        current_user: User = Depends(get_current_user),
                                        db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    await _require_supplier_owned(db, current_user, supplier_id)
    from openpyxl import load_workbook
    content = await file.read()
    wb = load_workbook(io.BytesIO(content)); ws = wb.active
    imported, skipped, errors = 0, 0, []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or (not row[0] and not row[1]): continue
        pname = str(row[0] or row[1] or "").strip()
        if not pname or pname.startswith("示例"): continue
        try:
            p = SupplierProduct(
                supplier_id=supplier_id,
                product_name=pname,
                spec=str(row[1] or "").strip() if row[1] and len(row)>1 else None,
                spec_price=float(row[2] or 0) if len(row)>2 and row[2] else None,
                unit_price=float(row[3] or 0) if len(row)>3 and row[3] else 0,
            )
            db.add(p); imported += 1
        except Exception as e:
            errors.append(f"行解析失败: {e}"); skipped += 1
    await db.flush()
    return {"imported": imported, "skipped": skipped, "errors": errors, "message": f"成功导入 {imported} 条产品"}

@router.post("/{supplier_id}/import/logistics")
async def import_logistics_for_supplier(supplier_id: int, file: UploadFile = File(...),
                                         current_user: User = Depends(get_current_user),
                                         db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
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
async def list_products(supplier_id: int, current_user = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _require_supplier_owned(db, current_user, supplier_id)
    prods = (await db.execute(select(SupplierProduct).where(SupplierProduct.supplier_id == supplier_id).order_by(SupplierProduct.created_at.desc()))).scalars().all()
    # Price comparison: find lowest price for each product across all suppliers
    price_map = {}
    if prods:
        from collections import defaultdict
        pnames = list(set(p.product_name for p in prods))
        all_prods = (await db.execute(
            select(SupplierProduct)
            .join(Supplier, SupplierProduct.supplier_id == Supplier.id)
            .where(SupplierProduct.product_name.in_(pnames), Supplier.warehouse_id.in_(get_wh_ids(current_user)))
        )).scalars().all()
        grouped = defaultdict(list)
        for ap in all_prods:
            key = (ap.product_name, ap.spec or '')
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
        key = (p.product_name, p.spec or '')
        cmp = price_map.get(key)
        item = {
            'id': p.id, 'product_name': p.product_name, 'spec': p.spec,
            'spec_price': p.spec_price, 'unit_price': p.unit_price,
            'currency': p.currency or "THB",
            'unit': p.unit, 'remark': p.remark,
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
        result.append(item)
    return {'data': result}
@router.post("/{supplier_id}/products")
async def add_product(supplier_id: int, req: SupplierProductCreate, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    await _require_supplier_owned(db, current_user, supplier_id)
    supplier = (await db.execute(select(Supplier).where(Supplier.id == supplier_id))).scalar_one_or_none()
    d = req.model_dump()
    if not d.get("currency"):
        d["currency"] = (supplier.default_currency if supplier and supplier.default_currency else "THB")
    p = SupplierProduct(supplier_id=supplier_id, **d)
    db.add(p); await db.flush()
    return {"id": p.id, "message": "添加成功"}

@router.delete("/{supplier_id}/products/{product_id}")
async def delete_product(supplier_id: int, product_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    await _require_supplier_owned(db, current_user, supplier_id)
    p = (await db.execute(select(SupplierProduct).where(SupplierProduct.id == product_id, SupplierProduct.supplier_id == supplier_id))).scalar_one_or_none()
    if not p: raise HTTPException(404, "产品不存在")
    await db.delete(p); await db.flush()
    return {"message": "删除成功"}
# ═══ Purchase Order ═════════════════════════════
@router.post("/{supplier_id}/purchase-order")
async def create_purchase_order(supplier_id: int, req: PurchaseOrderRequest,
                                 current_user: User = Depends(get_current_user),
                                 db: AsyncSession = Depends(get_db)):
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    supplier = await _require_supplier_owned(db, current_user, supplier_id)
    wh_id = get_wh_id(current_user)
    if not wh_id:
        raise HTTPException(400, "请先选择仓库")
    threshold = await _get_price_threshold(db, wh_id)

    pid_set = {it.product_id for it in req.items}
    products = (await db.execute(
        select(SupplierProduct).where(SupplierProduct.id.in_(pid_set), SupplierProduct.supplier_id == supplier_id)
    )).scalars().all()
    prod_map = {p.id: p for p in products}

    # 币种一致性校验：同一张采购单内产品币种必须一致
    currencies = {p.currency or "THB" for p in prod_map.values()}
    if len(currencies) > 1:
        raise HTTPException(400, "不同币种不能放在同一张采购单，请分开下单")
    order_currency = currencies.pop() if currencies else "THB"

    items_detail = []
    total = 0.0
    anomalies = []
    non_lowest = []
    for it in req.items:
        p = prod_map.get(it.product_id)
        if not p:
            raise HTTPException(400, f"产品 ID={it.product_id} 不属于该供应商")
        if not p.unit_price or p.unit_price <= 0:
            raise HTTPException(400, f"产品「{p.product_name}」尚未录入价格，请先录入价格后再下单")
        qty = max(it.quantity, 1)
        subtotal = p.unit_price * qty
        items_detail.append({
            "product_name": p.product_name, "spec": p.spec,
            "unit_price": p.unit_price, "quantity": qty,
            "subtotal": round(subtotal, 2),
            "currency": order_currency,
            "reason": (it.reason or "").strip(),
        })
        total += subtotal

        # 价格异常检测：对比历史均价（不含本次下单）
        hist_rows = await _get_price_history(db, wh_id, p.product_name, p.spec)
        if hist_rows:
            avg = sum(r.unit_price for r in hist_rows) / len(hist_rows)
            if avg > 0 and p.unit_price > avg * (1 + threshold / 100.0):
                exceed = round((p.unit_price - avg) / avg * 100.0, 1)
                anomalies.append({
                    "product_name": p.product_name, "spec": p.spec,
                    "unit_price": p.unit_price, "historical_avg": round(avg, 2),
                    "exceed_percent": exceed,
                })

        # 非最低价检测：对比该产品(名+规格)在本仓库内的最低报价
        lowest = await _get_lowest_quote(db, p.product_name, p.spec, wh_id)
        if lowest and p.unit_price > lowest["lowest_price"] + 0.001:
            non_lowest.append({
                "product_id": p.id,
                "product_name": p.product_name, "spec": p.spec,
                "unit_price": p.unit_price,
                "lowest_price": lowest["lowest_price"],
                "lowest_supplier_id": lowest["lowest_supplier_id"],
                "lowest_supplier_name": lowest["lowest_supplier_name"],
                "price_diff": round(p.unit_price - lowest["lowest_price"], 2),
                "quantity": qty,
                "reason": (it.reason or "").strip(),
            })

    # 有价格异常且未确认 → 返回提示，不创建订单
    if anomalies and not req.confirm_price_anomaly:
        return {
            "need_confirm": True,
            "message": f"有 {len(anomalies)} 项产品价格高于历史均价 {threshold}%",
            "threshold": threshold,
            "anomalies": anomalies,
        }

    # 有非最低价但未填原因 → 返回提示，不创建订单
    missing_reason = [n for n in non_lowest if not n["reason"]]
    if missing_reason:
        return {
            "need_reason": True,
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
    approval_threshold = await _get_approval_threshold(db)
    is_pending = approval_threshold > 0 and total > approval_threshold
    order_number = f"PO{now.strftime('%Y%m%d%H%M%S%f')}{supplier_id}"
    po = PurchaseOrder(
        warehouse_id=wh_id, supplier_id=supplier_id,
        order_number=order_number, total_amount=total,
        currency=order_currency, items=items_detail,
        status="pending" if is_pending else "confirmed",
        remark=req.remark, created_by=current_user.id,
    )
    db.add(po)
    await db.flush()

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
            created_by=current_user.id,
        )
        db.add(bill)
        await db.flush()
        po.payable_bill_id = bill.id
        bill_id = bill.id
    await db.flush()
    return {
        "message": "采购单已提交审批" if is_pending else "采购单已创建，应付账单已自动生成",
        "order": {"id": po.id, "order_number": order_number, "total_amount": total, "items": items_detail, "status": po.status},
        "pending": is_pending,
        "approval_threshold": approval_threshold,
        "payable_bill_id": bill_id,
        "payable_bill_number": bill_number,
        "anomalies": anomalies,
    }

# ═══ 采购价格监控 ════════════════════════════
class PriceThresholdSet(BaseModel):
    threshold: float


@router.get("/price-threshold")
async def get_price_threshold(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    wh_id = get_wh_id(current_user)
    threshold = await _get_price_threshold(db, wh_id) if wh_id else DEFAULT_PRICE_THRESHOLD
    return {"threshold": threshold}


@router.put("/price-threshold")
async def set_price_threshold(req: PriceThresholdSet, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
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
async def price_stats(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """每个产品(名+规格)的历史最低价/均价/最近采购价"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
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
                      current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """某产品的价格变化趋势（按时间）"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
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
                          current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """价格异常列表（管理员/主管可见）"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
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
                             current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """非最低价采购列表（按差价从大到小）"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
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
async def non_lowest_summary(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """非最低价采购汇总：本期多花的钱合计"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
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


class ApprovalThresholdSet(BaseModel):
    threshold: float


@router.get("/purchase-approval-threshold")
async def get_approval_threshold(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    threshold = await _get_approval_threshold(db)
    return {"threshold": threshold}


@router.put("/purchase-approval-threshold")
async def set_approval_threshold(req: ApprovalThresholdSet, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """门槛金额只有仓库管理员能设置。"""
    _forbid_super_admin(current_user)
    if current_user.role != Role.WAREHOUSE_ADMIN:
        raise HTTPException(403, "只有仓库管理员可以设置门槛金额")
    if req.threshold < 0:
        raise HTTPException(400, "门槛金额不能为负数")
    setting = (await db.execute(
        select(SystemSetting).where(
            SystemSetting.warehouse_id == 0,
            SystemSetting.key == "purchase_approval_threshold",
        )
    )).scalar_one_or_none()
    if setting:
        setting.value = str(req.threshold)
        setting.updated_by = current_user.id
    else:
        db.add(SystemSetting(warehouse_id=0, key="purchase_approval_threshold", value=str(req.threshold), updated_by=current_user.id))
    await db.flush()
    return {"message": f"采购审批门槛已设为 {req.threshold} 泰铢", "threshold": req.threshold}


@router.get("/purchase-approvals")
async def purchase_approvals(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """待审批采购单 + 疑似拆单提示。仓库管理员和主管可见。"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    threshold = await _get_approval_threshold(db)
    wh_ids = get_wh_ids(current_user)

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
async def approve_purchase(po_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """审批通过：采购单生效，生成应付账单，并写入价格历史/异常/非最低价。"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    po = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))).scalar_one_or_none()
    if not po:
        raise HTTPException(404, "采购单不存在")
    if po.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "无权审批其他仓库的采购单")
    if po.status != "pending":
        raise HTTPException(400, "该采购单已处理")
    if po.payable_bill_id:
        raise HTTPException(400, "该采购单已生成账单，不能重复生成")
    supplier = (await db.execute(select(Supplier).where(Supplier.id == po.supplier_id))).scalar_one_or_none()
    if not supplier:
        raise HTTPException(404, "供应商不存在")
    bill_number = f"PO-{po.order_number}"
    detail_lines = [f"- {d.get('product_name')} {d.get('spec') or ''} x{d.get('quantity')} @ {d.get('unit_price')} = {d.get('subtotal')}" for d in (po.items or [])]
    now = thai_now()
    bill = PayableBill(
        warehouse_id=po.warehouse_id, supplier_id=po.supplier_id,
        bill_number=bill_number, bill_date=now.replace(tzinfo=None),
        due_date=(now + timedelta(days=_parse_settlement_days(supplier.settlement_cycle))).replace(tzinfo=None),
        amount=po.total_amount, currency=po.currency or "THB", status="pending",
        detail="\n".join(detail_lines), source="purchase_order", purchase_order_id=po.id,
        created_by=current_user.id,
    )
    db.add(bill)
    await db.flush()
    po.payable_bill_id = bill.id
    po.status = "confirmed"
    await db.flush()
    # 审批通过 = 订单生效，此时才写入价格历史/异常/非最低价
    await _write_price_evidence(db, po)
    return {"message": "审批通过，应付账单已生成", "payable_bill_id": bill.id, "payable_bill_number": bill_number}


@router.put("/purchase-approvals/{po_id}/reject")
async def reject_purchase(po_id: int, req: PurchaseRejectRequest, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """审批驳回：采购单作废，需填原因。"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    po = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))).scalar_one_or_none()
    if not po:
        raise HTTPException(404, "采购单不存在")
    if po.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "无权审批其他仓库的采购单")
    if po.status != "pending":
        raise HTTPException(400, "该采购单已处理")
    if not (req.reason or "").strip():
        raise HTTPException(400, "请填写驳回原因")
    po.status = "rejected"
    po.reject_reason = req.reason.strip()
    await db.flush()
    return {"message": "已驳回"}


# ═══ 采购收货验收 ════════════════════════════
@router.get("/purchase-orders")
async def list_purchase_orders(page: int = 1, page_size: int = 50,
                               current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """采购单列表（含收货状态），供收货录入使用。"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    query = select(PurchaseOrder)
    count_q = select(func.count(PurchaseOrder.id))
    query = query.where(PurchaseOrder.warehouse_id.in_(get_wh_ids(current_user)))
    count_q = count_q.where(PurchaseOrder.warehouse_id.in_(get_wh_ids(current_user)))
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


@router.post("/purchase-orders/{po_id}/receive")
async def receive_purchase(po_id: int, items: str = Form(...), file: UploadFile = File(...),
                           current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """收货验收：逐个产品填实收数量 + 上传到货照片。"""
    import json
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    po = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))).scalar_one_or_none()
    if not po:
        raise HTTPException(404, "采购单不存在")
    if po.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "无权操作其他仓库的采购单")
    if po.status != "confirmed":
        raise HTTPException(400, "仅已生效采购单可收货")
    if po.receipt_status == "received":
        raise HTTPException(400, "该采购单已收货验收")

    try:
        received_list = json.loads(items)
    except Exception:
        raise HTTPException(400, "收货明细格式错误")
    received_map = {}
    for it in received_list:
        key = (str(it.get("product_name", "")), str(it.get("spec") or ""))
        try:
            received_map[key] = max(0, int(it.get("received_quantity") or 0))
        except (ValueError, TypeError):
            received_map[key] = 0

    # 保存到货照片
    import os, uuid
    ext = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "jpg"
    fname = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = "/app/uploads/arrival_photos"
    os.makedirs(upload_dir, exist_ok=True)
    fpath = os.path.join(upload_dir, fname)
    with open(fpath, "wb") as f:
        f.write(await file.read())
    photo_path = f"/uploads/arrival_photos/{fname}"

    # 逐项对比订单数量与实收数量
    updated_items = []
    has_diff = False
    for it in (po.items or []):
        key = (str(it.get("product_name", "")), str(it.get("spec") or ""))
        ordered_qty = int(it.get("quantity") or 0)
        received_qty = received_map.get(key, 0)
        diff_qty = ordered_qty - received_qty
        if diff_qty != 0:
            has_diff = True
        updated_items.append({
            **it,
            "received_quantity": received_qty,
            "diff_quantity": diff_qty,
        })
    po.items = updated_items
    po.receipt_status = "partially_received" if has_diff else "received"
    po.flow_status = "arrived" if has_diff else "completed"
    po.arrival_photo = photo_path
    po.received_by = current_user.id
    po.received_at = thai_now()
    await db.flush()

    # 有差异 → 关联账单标记待老板确认
    if has_diff and po.payable_bill_id:
        bill = (await db.execute(select(PayableBill).where(PayableBill.id == po.payable_bill_id))).scalar_one_or_none()
        if bill:
            bill.need_boss_confirm = "true"
            await db.flush()

    return {
        "message": "收货验收完成" + ("，存在数量差异" if has_diff else ""),
        "receipt_status": po.receipt_status,
        "flow_status": po.flow_status,
        "has_diff": has_diff,
    }


@router.post("/purchase-orders/{po_id}/mark-sent")
async def mark_purchase_sent(po_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """标记采购单已发送给供应商（记录发送时间/发送人）。"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    po = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))).scalar_one_or_none()
    if not po:
        raise HTTPException(404, "采购单不存在")
    if po.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "无权操作其他仓库的采购单")
    po.sent_at = thai_now()
    po.sent_by = current_user.id
    await db.flush()
    return {"message": "已标记发送", "sent_at": po.sent_at.isoformat()}


@router.post("/purchase-orders/{po_id}/receipt")
async def upload_purchase_receipt(po_id: int, file: UploadFile = File(...),
                                  current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """上传供应商签字/盖章回执，流程状态变为「供应商已确认」。"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    po = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))).scalar_one_or_none()
    if not po:
        raise HTTPException(404, "采购单不存在")
    if po.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "无权操作其他仓库的采购单")
    if po.status != "confirmed":
        raise HTTPException(400, "仅已生效采购单可上传回执")
    import os, uuid
    ext = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "jpg"
    fname = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = "/app/uploads/receipt_files"
    os.makedirs(upload_dir, exist_ok=True)
    fpath = os.path.join(upload_dir, fname)
    with open(fpath, "wb") as f:
        f.write(await file.read())
    po.receipt_file = f"/uploads/receipt_files/{fname}"
    po.receipt_uploaded_by = current_user.id
    po.receipt_uploaded_at = thai_now()
    po.flow_status = "supplier_confirmed"
    await db.flush()
    return {"message": "回执已上传，供应商已确认", "receipt_file": po.receipt_file, "flow_status": po.flow_status}


@router.post("/purchase-orders/{po_id}/mark-shipped")
async def mark_purchase_shipped(po_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """标记供应商已发货，流程状态变为「已发货」。"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    po = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))).scalar_one_or_none()
    if not po:
        raise HTTPException(404, "采购单不存在")
    if po.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "无权操作其他仓库的采购单")
    po.shipped_at = thai_now()
    po.shipped_by = current_user.id
    po.flow_status = "shipped"
    await db.flush()
    return {"message": "已标记发货", "flow_status": po.flow_status}


@router.get("/purchase-orders/{po_id}/pdf")
async def download_purchase_order_pdf(po_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """下载采购单 PDF（含单号/供应商/产品明细/总价/日期/仓库/老板联系方式）。"""
    from app.models.warehouse import Warehouse
    from urllib.parse import quote
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR, Role.STAFF):
        raise HTTPException(403, "无权限")
    po = (await db.execute(select(PurchaseOrder).where(PurchaseOrder.id == po_id))).scalar_one_or_none()
    if not po:
        raise HTTPException(404, "采购单不存在")
    if po.warehouse_id not in get_wh_ids(current_user):
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
async def receipt_discrepancies(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """收货差异列表：所有数量不符的采购。"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    query = select(PurchaseOrder).where(PurchaseOrder.receipt_status == "partially_received")
    query = query.where(PurchaseOrder.warehouse_id.in_(get_wh_ids(current_user)))
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
        for it in (po.items or []):
            diff = int(it.get("diff_quantity") or 0)
            if diff == 0:
                continue
            data.append({
                "purchase_order_id": po.id,
                "order_number": po.order_number,
                "supplier_name": sup_map.get(po.supplier_id, ""),
                "product_name": it.get("product_name", ""),
                "spec": it.get("spec") or None,
                "order_quantity": int(it.get("quantity") or 0),
                "received_quantity": int(it.get("received_quantity") or 0),
                "diff_quantity": diff,
                "diff_amount": round(diff * (it.get("unit_price") or 0), 2),
                "receiver_name": user_map.get(po.received_by, ""),
                "received_at": po.received_at.isoformat() if po.received_at else None,
            })
    data.sort(key=lambda x: x.get("received_at") or "", reverse=True)
    return {"data": data}

# ═══ 供应商采购集中度分析 ════════════════════════
DEFAULT_CONCENTRATION_THRESHOLD = 70.0


async def _get_concentration_threshold(db: AsyncSession) -> float:
    """集中度预警阈值（全局，老板设置）。默认 70%。"""
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
async def get_concentration_threshold(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    return {"threshold": await _get_concentration_threshold(db)}


@router.put("/concentration-threshold")
async def set_concentration_threshold(req: ConcentrationThresholdSet,
                                      current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _forbid_super_admin(current_user)
    if current_user.role != Role.WAREHOUSE_ADMIN:
        raise HTTPException(403, "只有仓库管理员可以设置")
    setting = (await db.execute(
        select(SystemSetting).where(
            SystemSetting.warehouse_id == 0,
            SystemSetting.key == "supplier_concentration_threshold",
        )
    )).scalar_one_or_none()
    if setting:
        setting.value = str(req.threshold)
    else:
        db.add(SystemSetting(warehouse_id=0, key="supplier_concentration_threshold",
                             value=str(req.threshold), updated_by=current_user.id))
    await db.flush()
    return {"message": "集中度预警阈值已保存", "threshold": req.threshold}


@router.get("/concentration")
async def concentration_analysis(month: str = None,
                                 current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """供应商采购集中度：按月统计各供应商采购金额/占比/订单数。"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
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
    threshold = await _get_concentration_threshold(db)
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
                              current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """集中度趋势：最近 N 个月最高供应商占比变化。"""
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
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
async def list_logistics_prices(supplier_id: int, current_user = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await _require_supplier_owned(db, current_user, supplier_id)
    prices = (await db.execute(select(SupplierCrossBorderPrice).where(SupplierCrossBorderPrice.supplier_id == supplier_id).order_by(SupplierCrossBorderPrice.transport_method, SupplierCrossBorderPrice.origin_warehouse))).scalars().all()
    return {"data": [{"id": p.id, "transport_method": p.transport_method, "cargo_type": p.cargo_type,
                      "origin_warehouse": p.origin_warehouse, "price_per_cbm": p.price_per_cbm,
                      "estimated_days": p.estimated_days, "currency": p.currency} for p in prices]}

@router.post("/{supplier_id}/logistics-prices")
async def add_logistics_price(supplier_id: int, req: dict, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    await _require_supplier_owned(db, current_user, supplier_id)
    p = SupplierCrossBorderPrice(supplier_id=supplier_id, **req)
    db.add(p); await db.flush()
    return {"id": p.id, "message": "添加成功"}

@router.delete("/{supplier_id}/logistics-prices/{price_id}")
async def delete_logistics_price(supplier_id: int, price_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    await _require_supplier_owned(db, current_user, supplier_id)
    p = (await db.execute(select(SupplierCrossBorderPrice).where(SupplierCrossBorderPrice.id == price_id, SupplierCrossBorderPrice.supplier_id == supplier_id))).scalar_one_or_none()
    if not p: raise HTTPException(404, "不存在")
    await db.delete(p); await db.flush()
    return {"message": "删除成功"}

# ═══ Price Comparison ════════════════════════════
@router.get("/compare-prices")
async def compare_prices(product_name: str = None, spec: str = None, category_id: int = None,
                          current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
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
                             current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
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
async def ai_compare(data: dict, current_user: User = Depends(get_current_user)):
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
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
                         db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    query = select(Supplier); count_q = select(func.count(Supplier.id))
    query = query.where(Supplier.warehouse_id.in_(get_wh_ids(current_user)))
    count_q = count_q.where(Supplier.warehouse_id.in_(get_wh_ids(current_user)))
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
                          db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    if current_user.role not in (Role.SUPER_ADMIN, Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
        raise HTTPException(403, "无权限")
    d = req.model_dump()
    d["default_currency"] = (d.get("default_currency") or "THB")
    s = Supplier(warehouse_id=get_wh_id(current_user), **d)
    db.add(s); await db.flush(); return {"id": s.id, "message": "创建成功"}

@router.put("/{supplier_id}")
async def update_supplier(supplier_id: int, req: SupplierUpdate,
                          current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    s = result.scalar_one_or_none()
    if not s: raise HTTPException(404, "供应商不存在")
    if current_user.role != Role.SUPER_ADMIN and s.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "只能修改自己仓库的供应商")
    for k, v in req.model_dump(exclude_unset=True).items():
        setattr(s, k, v)
    await db.flush(); return {"message": "更新成功"}

@router.delete("/{supplier_id}")
async def delete_supplier(supplier_id: int, current_user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    if current_user.role == Role.SUPER_ADMIN:
        raise HTTPException(403, "超级管理员请使用各仓库管理员账号操作")
    result = await db.execute(select(Supplier).where(Supplier.id == supplier_id))
    s = result.scalar_one_or_none()
    if not s: raise HTTPException(404, "供应商不存在")
    if current_user.role != Role.SUPER_ADMIN and s.warehouse_id not in get_wh_ids(current_user):
        raise HTTPException(403, "只能删除自己仓库的供应商")
    await db.delete(s); await db.flush()
    return {"message": "删除成功"}

@router.get("/procurement-summary")
async def procurement_summary(current_user: User = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    _forbid_super_admin(current_user)
    if current_user.role not in (Role.WAREHOUSE_ADMIN, Role.SUPERVISOR):
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
        return q.where(PayableBill.warehouse_id.in_(get_wh_ids(current_user)))

    def _by_currency(rows):
        out: dict = {}
        for r in rows:
            out[r.currency or "THB"] = float(r.total or 0)
        return out

    # --- 本月支出按币种 ---
    month_q = wh_filter(select(PayableBill.currency, func.sum(PayableBill.amount).label("total"))
        .where(extract("year", PayableBill.bill_date) == today.year, extract("month", PayableBill.bill_date) == today.month)
        .group_by(PayableBill.currency))
    month_total_by_currency = _by_currency((await db.execute(month_q)).all())

    # --- 上月支出按币种 ---
    last_q = wh_filter(select(PayableBill.currency, func.sum(PayableBill.amount).label("total"))
        .where(extract("year", PayableBill.bill_date) == last_month_start.year, extract("month", PayableBill.bill_date) == last_month_start.month)
        .group_by(PayableBill.currency))
    last_month_total_by_currency = _by_currency((await db.execute(last_q)).all())

    # --- 本月分类支出按币种 ---
    cat_month_q = wh_filter(select(Supplier.category_id, PayableBill.currency, func.sum(PayableBill.amount).label("total"))
        .join(Supplier, PayableBill.supplier_id == Supplier.id)
        .where(extract("year", PayableBill.bill_date) == today.year, extract("month", PayableBill.bill_date) == today.month)
        .group_by(Supplier.category_id, PayableBill.currency))
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
    sup_q = wh_filter(select(PayableBill.supplier_id, PayableBill.currency, func.sum(PayableBill.amount).label("total"), func.max(PayableBill.bill_date).label("last_date"))
        .group_by(PayableBill.supplier_id, PayableBill.currency))
    sup_rows = (await db.execute(sup_q)).all()
    sup_month_q = wh_filter(select(PayableBill.supplier_id, PayableBill.currency, func.sum(PayableBill.amount).label("total"))
        .where(extract("year", PayableBill.bill_date) == today.year, extract("month", PayableBill.bill_date) == today.month)
        .group_by(PayableBill.supplier_id, PayableBill.currency))
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
async def get_supplier(supplier_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
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
                      db: AsyncSession = Depends(get_db)):
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
