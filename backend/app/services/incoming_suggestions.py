"""只读到账候选；不绑定客户、不改申报和任何余额。"""
from decimal import Decimal
import unicodedata
from sqlalchemy import select
from app.models.customer import Customer
from app.models.recharge import IncomingFlow, RechargeDeclaration, ReconciliationResult
from app.services.customer_receivables import receipt_identity_query, ACTIVE_MATCHES


def normalized(value):
    return ''.join(unicodedata.normalize('NFKC',value or '').split()).casefold()


async def suggestions_for(db, flows):
    result={f.id:[] for f in flows}
    flows=[f for f in flows if f.match_status=='unmatched' and f.amount>0]
    if not flows:return result
    identity=receipt_identity_query()
    identities={r.flow_id:r for r in (await db.execute(select(identity).where(identity.c.flow_id.in_([f.id for f in flows])))).all()}
    active=select(ReconciliationResult.declaration_id).where(ReconciliationResult.match_status.in_(ACTIVE_MATCHES),ReconciliationResult.declaration_id.is_not(None))
    rows=(await db.execute(select(RechargeDeclaration,Customer).join(Customer,Customer.id==RechargeDeclaration.customer_id).where(
        RechargeDeclaration.warehouse_id.in_({f.warehouse_id for f in flows}),
        RechargeDeclaration.is_voided.is_(False),
        Customer.warehouse_id==RechargeDeclaration.warehouse_id,
        RechargeDeclaration.match_status=='unmatched',RechargeDeclaration.amount>0,
        RechargeDeclaration.id.not_in(active)))).all()
    for flow in flows:
        current=identities.get(flow.id)
        if current and current.customer_id is None:continue
        payer=normalized(flow.payer_name)
        for declaration,customer in rows:
            if declaration.warehouse_id!=flow.warehouse_id or (declaration.currency or 'THB')!=(flow.currency or 'THB'):continue
            if current and current.customer_id!=customer.id:continue
            distance=abs((declaration.declare_date.date()-flow.received_date.date()).days)
            reasons=['日期相差不超过3天'] if distance<=3 else []
            if Decimal(str(declaration.amount))==Decimal(str(flow.amount)):reasons.append('金额完全相同')
            if payer and payer in {normalized(customer.company_name),normalized(customer.customer_code)}:reasons.append('付款方与客户名称或编号一致')
            if not reasons:continue
            result[flow.id].append({'declaration_id':declaration.id,'customer_id':customer.id,'customer_code':customer.customer_code,
                'customer_name':customer.company_name,'declare_date':declaration.declare_date.isoformat(),'amount':declaration.amount,
                'currency':declaration.currency or 'THB','matched_count':len(reasons),'matched_conditions':reasons,'date_distance_days':distance})
        result[flow.id].sort(key=lambda s:(-s['matched_count'],s['date_distance_days'],s['declaration_id']))
    return result
