"""Explicit-connection, read-only preflight. Never fills old identities or releases them."""
import asyncio,json,os
from sqlalchemy import select,func,text
from sqlalchemy.ext.asyncio import create_async_engine
from app.models import PayableBill,ExpenseRecord,ExpenseApproval,ExpenseFundItem,ExpenseFund,CostIdentity

async def report(db,wid=None):
    result={'read_only':True,'historical_backfill':False,'rows_without_registry_reference':{},'known_invoice_conflicts':[]}
    for source,model in [('payable',PayableBill),('approval',ExpenseApproval),('expense',ExpenseRecord),('fund_item',ExpenseFundItem)]:
        q=select(func.count()).select_from(model).where(model.cost_identity_id.is_(None))
        if wid is not None:
            q=q.join(ExpenseFund,ExpenseFund.id==model.fund_id).where(ExpenseFund.warehouse_id==wid) if source=='fund_item' else q.where(model.warehouse_id==wid)
        result['rows_without_registry_reference'][source]=(await db.execute(q)).scalar_one()
    q=select(PayableBill.warehouse_id,PayableBill.invoice_identity_key,func.array_agg(PayableBill.id)).where(
        PayableBill.invoice_identity_key.is_not(None),((PayableBill.status!='voided')|(PayableBill.paid_amount>0)|PayableBill.paid_amount.is_(None)))
    if wid is not None:q=q.where(PayableBill.warehouse_id==wid)
    rows=(await db.execute(q.group_by(PayableBill.warehouse_id,PayableBill.invoice_identity_key).having(func.count()>1))).all()
    result['known_invoice_conflicts']=[{'warehouse_id':w,'invoice_key':key,'payable_ids':ids} for w,key,ids in rows]
    result['condition']='未登记引用的行数包含各业务生成的派生记录，不等于独立费用或重复笔数，不能相加当作费用。历史身份保持未知。已知冲突先核查原票与付款；不得迁移删改或强行释放。其他渠道旧单不能凭金额证明重复，付款未知也不当作零释放。'
    return result

async def main():
    url=os.environ.get('COST_IDENTITY_AUDIT_DATABASE_URL')
    if not url:raise SystemExit('请显式提供COST_IDENTITY_AUDIT_DATABASE_URL；不会读取默认部署配置')
    engine=create_async_engine(url)
    try:
        async with engine.connect() as db:
            await db.execute(text('SET TRANSACTION READ ONLY'))
            print(json.dumps(await report(db),ensure_ascii=False,default=str,indent=2));await db.rollback()
    finally:await engine.dispose()
if __name__=='__main__':asyncio.run(main())
