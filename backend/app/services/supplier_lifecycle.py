"""Supplier deletion/status only; preserve all historical business records."""
from fastapi import HTTPException
from sqlalchemy import select, func, or_
from sqlalchemy.exc import IntegrityError
from app.database import Base
from app.models import Supplier, SupplierProduct, PurchaseOrder
from app.models.procurement_control import ProcurementRiskReview
from app.services.data_history import record_history
from app.services import sku_catalog as catalog

LABELS = {
    'supplier_products': '条产品报价', 'supplier_logistics_prices': '条物流报价',
    'supplier_cross_border_prices': '条跨境物流报价', 'supplier_quotes': '条产品报价版本',
    'supplier_quote_tiers': '条阶梯报价', 'purchase_orders': '张采购单',
    'payable_bills': '张应付账单', 'inventory_receipt_links': '条库存记录',
    'purchase_receipt_events': '条收货记录', 'procurement_non_lowest_records': '条风险看板记录',
    'procurement_price_history': '条采购价格历史', 'supplier_tag_links': '条仓库标签关联',
    'expense_records': '条支出记录', 'cost_identities': '条费用归属记录',
}

def references_supplier(value, supplier_id):
    if isinstance(value, dict):
        return any((k in ('supplier_id', 'selected_supplier_id', 'lowest_supplier_id') and v == supplier_id)
                   or (k == 'supplier_ids' and isinstance(v, list) and supplier_id in v)
                   or references_supplier(v, supplier_id) for k, v in value.items())
    return isinstance(value, list) and any(references_supplier(v, supplier_id) for v in value)

async def dependencies(db, supplier):
    counts = {}
    # Check every actual direct FK, including nullable references before ORM can null them.
    for table in Base.metadata.tables.values():
        columns = [fk.parent for fk in table.foreign_keys if fk.target_fullname == 'suppliers.id']
        if columns:
            n = await db.scalar(select(func.count()).select_from(table).where(or_(*(c == supplier.id for c in columns))))
            if n: counts[LABELS.get(table.name, '条关联业务记录')] = counts.get(LABELS.get(table.name, '条关联业务记录'), 0) + n
    products = select(SupplierProduct.id).where(SupplierProduct.supplier_id == supplier.id)
    orders = select(PurchaseOrder.id).where(PurchaseOrder.supplier_id == supplier.id)
    tables = Base.metadata.tables
    quotes = tables['supplier_quotes']; revisions = tables['supplier_quote_revisions']
    quote_ids = select(quotes.c.id).where(quotes.c.product_id.in_(products))
    revision_ids = select(revisions.c.id).where(revisions.c.quote_id.in_(quote_ids))
    indirect = [('supplier_quotes', quotes.c.product_id.in_(products)),
                ('supplier_quote_tiers', tables['supplier_quote_tiers'].c.revision_id.in_(revision_ids)),
                ('purchase_receipt_events', tables['purchase_receipt_events'].c.purchase_order_id.in_(orders)),
                ('inventory_receipt_links', tables['inventory_receipt_links'].c.purchase_order_id.in_(orders))]
    for name, condition in indirect:
        n = await db.scalar(select(func.count()).select_from(tables[name]).where(condition))
        if n: counts[LABELS[name]] = n
    reviews = (await db.execute(select(ProcurementRiskReview).where(ProcurementRiskReview.warehouse_id == supplier.warehouse_id))).scalars()
    n = sum(references_supplier(row.snapshot, supplier.id) or references_supplier(row.scope, supplier.id) for row in reviews)
    if n: counts['条风险看板记录'] = counts.get('条风险看板记录', 0) + n
    return counts

async def mutate(db, user, supplier_id, warehouse_id, *, changes=None):
    deleting = changes is None
    verb = '删除' if deleting else '更新供应商状态'
    try:
        # Same warehouse lock as supplier/catalog writes, plus row/FK serialization.
        await catalog.lock(db, warehouse_id)
        supplier = (await db.execute(select(Supplier).where(Supplier.id == supplier_id).with_for_update())).scalar_one_or_none()
        if supplier is None: raise HTTPException(400, '供应商不存在，请刷新后重试')
        if supplier.warehouse_id != warehouse_id: raise HTTPException(403, '只能操作当前仓库的供应商')
        if deleting:
            counts = await dependencies(db, supplier)
            if counts:
                detail = '；'.join(f'{n} {label}' for label, n in counts.items())
                raise HTTPException(400, '该供应商已有业务记录，请改用停用；该供应商有 ' + detail)
            await record_history(db, module='suppliers', record_id=supplier.id, operator=user,
                                 operation_type='delete', before={'name': supplier.name}, warehouse_id=warehouse_id)
            await db.delete(supplier)
            result = {'message': '删除成功'}
        else:
            active = changes['is_active']
            if active not in ('true', 'false'): raise HTTPException(400, '供应商状态无效，请选择启用或停用')
            before = supplier.is_active
            for key, value in changes.items(): setattr(supplier, key, value)
            if before != active:
                await record_history(db, module='suppliers', record_id=supplier.id, operator=user,
                                     operation_type='edit', before={'is_active': before},
                                     after={'is_active': active, 'remark': '启用供应商' if active == 'true' else '停用供应商'},
                                     warehouse_id=warehouse_id)
            result = {'message': '已启用' if active == 'true' else '已停用', 'id': supplier.id, 'is_active': active}
        await db.flush()
        # Include commit errors in this operation's rollback and Chinese error boundary.
        await db.commit()
        return result
    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError:
        await db.rollback()
        raise HTTPException(400, '该供应商已有业务记录，请改用停用；关联记录已变化，请刷新后重试') from None
    except Exception:
        await db.rollback()
        raise HTTPException(400, verb + '失败，请刷新确认状态后重试') from None
