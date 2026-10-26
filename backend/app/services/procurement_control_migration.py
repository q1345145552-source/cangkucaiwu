"""New empty tables only; never fill historical approvals or change policies."""
from sqlalchemy import inspect
from fastapi import HTTPException
from app.models.procurement_control import ProcurementActionException,ProcurementDutyExecution,ProcurementRiskReview
MODELS=(ProcurementActionException,ProcurementDutyExecution,ProcurementRiskReview)
GUARDS={
 'procurement_action_exceptions':('uq_procurement_exception_request',['warehouse_id','granted_by','request_key']),
 'procurement_duty_executions':('uq_procurement_duty_execution',['warehouse_id','action','operator_id','request_key']),
 'procurement_risk_reviews':('uq_procurement_risk_review_request',['warehouse_id','reviewer_id','request_key']),
}
async def ensure_procurement_controls(conn):
 def check(c):
  i=inspect(c);missing=[]
  for m in MODELS:
   table=m.__table__;name=table.name
   if not i.has_table(name):missing.append(name);continue
   columns={r['name']:r for r in i.get_columns(name)}
   missing.extend(name+'.'+p.name for p in table.columns if p.name not in columns or (not p.nullable and columns[p.name]['nullable']))
   guard,fields=GUARDS[name]
   if not any(v['name']==guard and v['column_names']==fields for v in i.get_unique_constraints(name)):missing.append(guard)
   fks=i.get_foreign_keys(name)
   for fk in table.foreign_keys:
    if not any(v['constrained_columns']==[fk.parent.name] and v['referred_table']==fk.column.table.name and v['referred_columns']==[fk.column.name] for v in fks):missing.append(name+'.'+fk.parent.name+'_fk')
  return missing
 missing=await conn.run_sync(check)
 if missing:raise HTTPException(503,{'code':'procurement_control_migration_missing','message':'采购职责与复核结构未就绪，请管理员核对迁移','missing':missing})
async def migrate_procurement_controls(conn):
 for model in MODELS:
  async with conn.begin_nested():await conn.run_sync(lambda c,m=model:m.__table__.create(c,checkfirst=True))
 await ensure_procurement_controls(conn)
 print('采购职责与复核迁移 READY：3张空表；默认开关关闭，未回填历史审批或改动采购账目')
