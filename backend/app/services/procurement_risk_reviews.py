"""Append-only owner conclusions bound to server-calculated month/scope/evidence."""
import csv,io,json
from sqlalchemy import select
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from app.models import ProcurementRiskReview as Review,AuditLog
from app.services import procurement_risk as risk,procurement_month_report as prices,purchase_matching as matching
from app.services.procurement_controls import owner,reason,changed
from app.services.payable_creation import fingerprint,number
from app.services.procurement_control_migration import ensure_procurement_controls
from app.core.timezone import thai_now

CONCLUSIONS={'pending':'待处理','cleared':'已核实无问题','follow_up':'需跟进'}
def scope_of(values):
 month=prices.parse_month(values.get('month'))[0]
 return {'month':month,**{k:values.get(k) for k in ('supplier_id','orderer_id','currency')}}
def subject_key(wid,scope,signal):
 return fingerprint({'warehouse_id':wid,'scope':scope,'rule':signal['rule'],'subject':signal['subject']})
def evidence_version(signal):return fingerprint(signal)
def stored(row):
 return {k:getattr(row,k) for k in ('id','warehouse_id','month','rule','subject_key','signal_id','rule_version','scope','evidence_version','snapshot','conclusion','reason','reviewer_id','created_at')}
async def current(db,wid,signal_id,values):
 scope=scope_of(values);result=await risk.calculate(db,wid,**scope)
 signal=next((r for r in result['observations'] if r['id']==signal_id),None)
 if signal is None:raise HTTPException(404,'当前仓库、月份及范围未找到该线索；不能套用旧结论')
 return signal,scope
async def state(db,wid,signal,scope):
 key=subject_key(wid,scope,signal)
 rows=(await db.execute(select(Review).where(Review.warehouse_id==wid,Review.subject_key==key).order_by(Review.id.desc()))).scalars().all()
 latest=rows[0] if rows else None;version=evidence_version(signal)
 stale=bool(latest and (latest.rule_version!=signal['version'] or latest.evidence_version!=version))
 return {'subject_key':key,'scope':scope,'evidence_version':version,'latest_review_id':latest.id if latest else 0,'status':'pending' if not latest or stale else latest.conclusion,'stale':stale,'message':'证据已变化需重核；旧结论仅作历史' if stale else CONCLUSIONS[latest.conclusion] if latest else '待处理','history':[stored(r) for r in rows]}
async def append(db,wid,user,signal_id,values,*,request_key,expected_evidence_version,expected_latest_review_id,conclusion,review_reason):
 owner(user);why=reason(review_reason)
 if conclusion not in CONCLUSIONS:raise HTTPException(400,'复核结论不正确')
 key=number(request_key,'请求编号',100);scope=scope_of(values)
 signature=fingerprint({'signal_id':signal_id,'scope':scope,'evidence':expected_evidence_version,'latest':expected_latest_review_id,'conclusion':conclusion,'reason':why})
 await matching.scope_lock(db,wid);await ensure_procurement_controls(await db.connection())
 old=(await db.execute(select(Review).where(Review.warehouse_id==wid,Review.reviewer_id==user.id,Review.request_key==key))).scalar_one_or_none()
 if old:
  if old.request_fingerprint!=signature:raise HTTPException(409,'该复核请求已保存且内容不同，请查看原历史')
  return {'data':stored(old),'replayed':True,'message':'原复核已保存，未重复追加；请刷新当前证据状态'}
 try:signal,scope=await current(db,wid,signal_id,scope)
 except HTTPException as e:
  if e.status_code==404:raise changed('当前线索已不在此证据范围，原复核请求未执行；请重新读取',key,404)
  raise
 status=await state(db,wid,signal,scope)
 if expected_evidence_version!=status['evidence_version'] or expected_latest_review_id!=status['latest_review_id']:raise changed('线索证据或复核历史已变化，请重新读取后确认；原请求未执行',key)
 if not signal['evidence'] or conclusion=='cleared' and signal['state']=='unavailable':raise changed('线索依据不足，不能记为已核实无问题；请补齐依据或记录需跟进；原请求未执行',key)
 row=Review(warehouse_id=wid,month=scope['month'],rule=signal['rule'],subject_key=status['subject_key'],signal_id=signal['id'],rule_version=signal['version'],scope=scope,evidence_version=status['evidence_version'],snapshot=jsonable_encoder(signal),conclusion=conclusion,reason=why,reviewer_id=user.id,request_key=key,request_fingerprint=signature)
 db.add(row);await db.flush()
 db.add(AuditLog(user_id=user.id,warehouse_id=wid,module='procurement_risk_review',action_type='review',target_id=row.id,detail={'review_id':row.id,'scope':scope,'rule':signal['rule'],'rule_version':signal['version'],'evidence_version':status['evidence_version'],'conclusion':conclusion,'reason':why,'at':thai_now().isoformat()}))
 await db.flush();return {'data':stored(row),'message':'复核已追加保存；不等于业务例外授权，不改变采购或金额'}
async def listing(db,wid,values,rule=None,all_scopes=False):
 scope=scope_of(values);q=select(Review).where(Review.warehouse_id==wid,Review.month==scope['month'])
 if rule:q=q.where(Review.rule==rule)
 rows=(await db.execute(q.order_by(Review.id.desc()))).scalars().all()
 return [stored(r) for r in rows if all_scopes or r.scope==scope]
def export(rows):
 out=io.StringIO(newline='');writer=csv.writer(out);writer.writerow(['复核编号','月份','规则','规则版本','结论','原因','复核人编号','时间','范围','证据版本','当时服务器证据(历史不等于现状)'])
 for r in rows:
  values=[r['id'],r['month'],r['rule'],r['rule_version'],CONCLUSIONS[r['conclusion']],r['reason'],r['reviewer_id'],r['created_at'].isoformat(),json.dumps(r['scope'],ensure_ascii=False),r['evidence_version'],json.dumps(r['snapshot'],ensure_ascii=False)]
  writer.writerow([prices.cell(v,i in (0,6)) for i,v in enumerate(values)])
 return ('\ufeff'+out.getvalue()).encode()
