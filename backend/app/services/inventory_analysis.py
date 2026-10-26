"""Read-only warehouse/SKU/unit evidence. Unknown cost is never zero or a quote."""
import csv, io, json
from decimal import Decimal, localcontext, ROUND_HALF_UP
from sqlalchemy import select
from fastapi import HTTPException
from app.models import InventoryAccount, InventoryMovement, InventoryControl, PurchaseOrder, PayableBill
from app.models.payable import MonthlyOrderVolume
from app.services import inventory as stock, procurement_month_report as prices
from app.services.inventory_migration import ensure_inventory
from app.core.timezone import thai_now

VERSION = 'inventory-use-evidence-v1'
DATE_NOTE = '库存按实际变动发生时间的泰国日历月，月初含/次月初不含；原有符号流水与反向流水一起累计。提醒按该月末（本月截至查询时）数量和当前阈值回看，不还原历史阈值。'
NOTICE = '采购、实收、领用和库存分开列证据；备货、分批收货、跨期退回及盘点差异都需人工核实，不认定回扣或自动处罚。成本不是资金支出，不新增任何费用。'


def movement_group(row, by_id):
    original = by_id.get(row.reverses_id) if row.kind=='reversal' else row
    if original is None: return 'unknown'
    return {'receipt':'received', 'issue':'usage', 'return':'usage', 'opening':'opening',
            'stocktake_adjustment':'adjustment'}.get(original.kind, 'unknown')


def per_order(costs, order_count):
    """Only feed independently verified complete issue costs; split currencies, no FX."""
    if order_count is None or order_count<=0: return None
    with localcontext() as context:
        context.prec=64
        return {currency: prices.amount(amount/Decimal(order_count)) for currency,amount in costs.items()}


async def denominator(db, wid, month):
    rows=(await db.execute(select(MonthlyOrderVolume).where(MonthlyOrderVolume.warehouse_id==wid,
                                                            MonthlyOrderVolume.month==month))).scalars().all()
    known=len(rows)==1 and type(rows[0].order_count) is int and rows[0].order_count>0
    return {'order_count':rows[0].order_count if len(rows)==1 else None,
            'available':known, 'source':'monthly_order_volumes', 'record_ids':[r.id for r in rows],
            'reason':'同仓同月已登记订单量（人工业务口径），非采购单数' if known else
                     '同仓同月订单量缺失或重复，不能猜作0' if len(rows)!=1 else '订单量为0或无效，不能除以零'}


async def _calculate(db, wid, month=None):
    await ensure_inventory(await db.connection())
    month,start,end=prices.parse_month(month); now=thai_now(); cutoff=min(end,now)
    if start>now: raise HTTPException(400,'库存分析月份不能晚于当前月份')
    accounts=(await db.execute(select(InventoryAccount).where(InventoryAccount.warehouse_id==wid).order_by(InventoryAccount.id))).scalars().all()
    movements=(await db.execute(select(InventoryMovement).where(InventoryMovement.warehouse_id==wid).order_by(InventoryMovement.id))).scalars().all()
    settings={r.account_id:r for r in (await db.execute(select(InventoryControl).where(InventoryControl.warehouse_id==wid))).scalars()}
    by_id={r.id:r for r in movements}; volume=await denominator(db,wid,month)
    policy=await stock.policy(db,wid)
    pos=(await db.execute(select(PurchaseOrder).where(PurchaseOrder.warehouse_id==wid,
              PurchaseOrder.created_at>=start,PurchaseOrder.created_at<end))).scalars().all()
    bills={r.id:r for r in (await db.execute(select(PayableBill).where(PayableBill.warehouse_id==wid,
                     PayableBill.id.in_([p.payable_bill_id for p in pos if p.payable_bill_id])))).scalars()}
    ordered={}; unresolved=0
    for po in pos:
        if prices.order_state_exclusion(po,bills): continue
        for item in po.items or []:
            try:
                sid,unit,factor,_=stock.frozen_mapping(po,{'line_id':item.get('line_id'),'unit':item.get('unit')})
                with localcontext() as context:
                    context.prec=64
                    amount=stock.quantity(item.get('quantity'))*factor
                key=(sid,unit); ordered[key]=ordered.get(key,Decimal(0))+amount
            except (HTTPException,TypeError,KeyError): unresolved+=1
    rows=[]
    for account in accounts:
        all_rows=[r for r in movements if r.account_id==account.id]
        at_opening=lambda r:r.kind=='opening' and r.occurred_at==start
        prior=[r for r in all_rows if r.occurred_at<start or at_opening(r)]
        period=[r for r in all_rows if start<=r.occurred_at<cutoff and not at_opening(r)]
        # Recorded at exactly 'now' is still part of the current snapshot.
        if cutoff==now: period=[r for r in all_rows if start<=r.occurred_at<=cutoff and not at_opening(r)]
        before_end=[r for r in all_rows if r.occurred_at<cutoff or cutoff==now and r.occurred_at==cutoff]
        with localcontext() as context:
            context.prec=64
            groups={k:sum((r.quantity for r in period if movement_group(r,by_id)==k),Decimal(0))
                    for k in ('received','usage','adjustment','opening','unknown')}
            opening=sum((r.quantity for r in prior),Decimal(0)); closing=sum((r.quantity for r in before_end),Decimal(0))
            coherent=sum((r.quantity for r in all_rows),Decimal(0))==account.recorded_quantity
            covered=bool(coherent and account.opening_confirmed and account.opening_at<=start)
            closing_known=bool(coherent and account.opening_confirmed and account.opening_at<cutoff and closing>=0)
            used=-groups['usage']; received=groups['received']; setting=settings.get(account.id)
            minimum=setting.minimum_quantity if setting else None; ratio=setting.receipt_usage_ratio if setting else None
            ratio_value=received/used if used>0 else None
            ratio_text=(format(ratio_value.quantize(Decimal('.00000001'),rounding=ROUND_HALF_UP),'f').rstrip('0').rstrip('.')) if ratio_value is not None else None
        low_state='unavailable' if not closing_known or minimum is None else 'attention' if closing<minimum else 'normal'
        if not covered or groups['unknown']:
            usage_state='unavailable'; explanation='月初真实期初/完整流水覆盖不足，不把已知变动当整月用量结论'
        elif ratio is None:
            usage_state='unavailable'; explanation='老板未设置本仓该SKU收货/净领用比较阈值，不擅定异常标准'
        elif used<=0:
            usage_state='info'; explanation='本月净领用为零或跨期退回抵减为负，不除以零，不把收货直接认定违规'
        elif ratio_value>ratio and closing>opening:
            usage_state='attention'; explanation='已知收货/净领用比超过设定值且库存上升；请结合备货说明、订购未到货及盘点差异核实'
        else:
            usage_state='normal'; explanation='未同时出现设定比例越线及库存上升，不代表其他风险已排除'
        currencies=sorted({r.cost_currency for r in period if r.cost_currency in ('THB','CNY')})
        # R10 deliberately has no configured cost layers. Non-NULL legacy/test amounts
        # alone do not prove valued consumption, and must never become an invented zero.
        cost_reason='库存计价/可核实领用成本尚未配置，不借用采购价或资金支出' if volume['available'] else volume['reason']
        row={'account_id':account.id,'warehouse_id':wid,'sku_id':account.sku_id,'sku':account.sku_snapshot,
             'base_unit':account.base_unit,'unit_label':stock.account_data(account)['unit_label'],
             'opening_quantity':stock.qty(opening) if covered else None,
             'closing_quantity':stock.qty(closing) if closing_known else None,
             'coverage_complete':covered,'opening_at':account.opening_at,
             'received_quantity':stock.qty(received),'net_issued_quantity':stock.qty(used),
             'ordered_quantity':stock.qty(ordered.get((account.sku_id,account.base_unit),Decimal(0))),
             'stocktake_adjustment':stock.qty(groups['adjustment']),
             'opening_added_in_period':stock.qty(groups['opening']),
             'unknown_change':stock.qty(groups['unknown']),
             'minimum_quantity':stock.qty(minimum) if minimum is not None else None,
             'low_stock_state':low_state,'low_stock_reason':'低于当前设定安全库存' if low_state=='attention' else
                 '期末（本月当前）数量不低于安全库存' if low_state=='normal' else '期初/流水或安全库存设置不足，不能判断',
             'receipt_usage_ratio':ratio_text,
             'configured_ratio':stock.qty(ratio) if ratio is not None else None,
             'stockpiling_note':setting.stockpiling_note if setting else '',
             'usage_state':usage_state,'usage_explanation':explanation,
             'movement_ids':[r.id for r in period],
             'cost':{'available':False,'per_order_by_currency':None,'verified_totals_by_currency':None,
                     'observed_currencies':currencies,'reason':cost_reason,
                     'note':'不同币种不相加；未配置成本不显示0；盘点调整不冒充实际领用成本'}}
        rows.append(row)
    return {'warehouse_id':wid,'month':month,'as_of':cutoff,'version':VERSION,'date_basis':DATE_NOTE,
            'notice':NOTICE,'data':rows,'total':len(rows),'order_volume':volume,'valuation_policy':policy,
            'unmapped_purchase_lines':unresolved,'message':f'库存盘点/用量证据已接入，共{len(rows)}个SKU基本单位台账；成本缺依据明确不可算，不认定回扣'}


async def calculate(db, wid, month=None):
    # Risk-board callers also use a Decimal context. Do not let caller context
    # change quantities, ratios or evidence hashes between list/detail/export.
    with localcontext() as context:
        context.prec=64
        return await _calculate(db, wid, month)


def export(result):
    out=io.StringIO(newline=''); writer=csv.writer(out)
    writer.writerow(['月份','仓库','台账','SKU','名称','基本单位','月初数量','订购数量(非入库)','实收入库净变动',
        '净领用','盘点调整','月末/当前数量','覆盖完整','安全下限','库存提醒','收货用量比','设定比','用量结论',
        '说明','备货说明','同月订单量','成本状态','单票成本(分币种)','来源流水编号'])
    for row in result['data']:
        values=[result['month'],result['warehouse_id'],row['account_id'],row['sku']['code'],row['sku']['name'],row['base_unit'],
            row['opening_quantity'],row['ordered_quantity'],row['received_quantity'],row['net_issued_quantity'],
            row['stocktake_adjustment'],row['closing_quantity'],str(row['coverage_complete']),row['minimum_quantity'],
            row['low_stock_state'],row['receipt_usage_ratio'],row['configured_ratio'],row['usage_state'],row['usage_explanation'],
            row['stockpiling_note'],result['order_volume']['order_count'],row['cost']['reason'],
            json.dumps(row['cost']['per_order_by_currency'],ensure_ascii=False),json.dumps(row['movement_ids'])]
        writer.writerow([prices.cell(v,i in (1,2,6,7,8,9,10,11,13,15,16,20)) for i,v in enumerate(values)])
    return ('\ufeff'+out.getvalue()).encode()
