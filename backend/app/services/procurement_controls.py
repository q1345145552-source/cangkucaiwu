"""Warehouse-serialized duty policies and explicit atomic one-use exceptions.

These controls govern existing manual actions, not low-value auto-effective creation.
Call begin/finish inside the existing warehouse -> purchase-order transaction lock.
"""
import json,re
from sqlalchemy import select,or_
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from app.core.permissions import Role
from app.core.timezone import thai_now
from app.models import SystemSetting,PurchaseOrder,User,UserWarehouse,AuditLog
from app.models.procurement_control import ProcurementActionException as ExceptionGrant,ProcurementDutyExecution as Execution
from app.services.payable_creation import fingerprint,number
from app.services import purchase_matching as matching
from app.services.data_history import record_history
from app.services.procurement_control_migration import ensure_procurement_controls

KEY='purchase_duty_separation_v1'
ACTIONS={'approve','reject','receive'}

def owner(user):
 if user.role!=Role.WAREHOUSE_ADMIN:raise HTTPException(403,'仅仓库管理员可以管理采购职责和例外授权')

def changed(message,key,status=409):
 return HTTPException(status,{'code':'procurement_duty_changed','message':message,'request_key':key,'not_executed':True})

def reason(value):
 if not isinstance(value,str) or not value.strip():raise HTTPException(400,'请填写原因')
 if len(value.strip())>1000:raise HTTPException(400,'原因不能超过1000字')
 return value.strip()

async def policy(db,wid):
 if type(wid) is not int or wid<=0:raise HTTPException(400,'请选择单个有效仓库，不能使用全局配置')
 rows=(await db.execute(select(SystemSetting).where(SystemSetting.warehouse_id==wid,SystemSetting.key==KEY))).scalars().all()
 if len(rows)>1:raise HTTPException(503,'采购职责配置重复，请管理员核对')
 values={'revision':0,'no_self_approve':False,'no_self_receive':False}
 if rows:
  try:
   stored=json.loads(rows[0].value)
   if not isinstance(stored,dict) or set(stored)!=set(values) or type(stored['revision']) is not int or stored['revision']<1 or any(type(stored[k]) is not bool for k in ('no_self_approve','no_self_receive')):raise ValueError()
   values=stored
  except (ValueError,TypeError,KeyError):raise HTTPException(503,'采购职责配置异常，未假定为关闭，请管理员核对')
 return {**values,'warehouse_id':wid,'version':fingerprint({'warehouse_id':wid,**values}),
  'scope':'不可自批仅控制原人工通过/驳回；低金额自动生效和原应付时点不变。不可自收仅控制真实实收登记，不控制供应商签字回执。默认关闭；历史不回填不追罚。'}

async def history(db,user,wid,action,before,after,record_id=None):
 await record_history(db,module='suppliers',record_id=record_id or wid,operator=user,operation_type=action,before=before,after=after,warehouse_id=wid)
 db.add(AuditLog(user_id=user.id,warehouse_id=wid,module='procurement_controls',action_type=action,target_id=record_id,detail={'before':before,'after':after,'at':thai_now().isoformat()}))

async def cached(db,wid,user,action,key,signature):
 previous=(await db.execute(select(Execution).where(Execution.warehouse_id==wid,Execution.operator_id==user.id,Execution.action==action,Execution.request_key==key))).scalar_one_or_none()
 if previous:
  if previous.request_fingerprint!=signature:raise HTTPException(409,'该操作请求已成功且内容不同，请查看原记录；未重复执行')
  return {**previous.response,'replayed':True}
 return None

async def save_execution(db,wid,user,action,key,signature,version,response,po=None,grant=None):
 row=Execution(warehouse_id=wid,purchase_order_id=po.id if po else None,action=action,operator_id=user.id,request_key=key,request_fingerprint=signature,policy_version=version,exception_id=grant.id if grant else None,response={})
 db.add(row);await db.flush()
 result={**response,'duty_execution_id':row.id,'duty_operator_id':user.id}
 row.response=jsonable_encoder(result)
 if grant:
  grant.status='used';grant.used_at=thai_now();grant.used_request_key=key
 await history(db,user,wid,'duty_'+action,None,{'execution_id':row.id,'request_key':key,'policy_version':version,'exception_id':grant.id if grant else None},po.id if po else None)
 await db.flush();return result

async def update_policy(db,wid,user,*,no_self_approve,no_self_receive,expected_version,request_key,change_reason):
 owner(user);why=reason(change_reason);key=number(request_key,'请求编号',100)
 if type(no_self_approve) is not bool or type(no_self_receive) is not bool:raise HTTPException(400,'职责开关必须是是或否')
 await matching.scope_lock(db,wid);await ensure_procurement_controls(await db.connection())
 signature=fingerprint({'flags':[no_self_approve,no_self_receive],'expected':expected_version,'reason':why})
 old=await cached(db,wid,user,'policy',key,signature)
 if old:return old
 before=await policy(db,wid)
 if expected_version!=before['version']:raise changed('采购职责配置已变化，请重新读取后确认；原请求未执行',key)
 value={k:v for k,v in before.items() if k in ('revision','no_self_approve','no_self_receive')};value.update(revision=value['revision']+1,no_self_approve=no_self_approve,no_self_receive=no_self_receive)
 row=(await db.execute(select(SystemSetting).where(SystemSetting.warehouse_id==wid,SystemSetting.key==KEY))).scalar_one_or_none()
 if row:row.value=json.dumps(value);row.updated_by=user.id
 else:db.add(SystemSetting(warehouse_id=wid,key=KEY,value=json.dumps(value),updated_by=user.id))
 await db.flush();after=await policy(db,wid)
 await history(db,user,wid,'duty_policy',before,{**after,'reason':why})
 return await save_execution(db,wid,user,'policy',key,signature,after['version'],{'message':'采购职责配置已保存','policy':after})

async def business(db,po,action):
 if action not in ACTIONS:raise HTTPException(400,'采购职责动作不正确')
 values={k:getattr(po,k) for k in ('id','warehouse_id','supplier_id','created_by','status','flow_status','items','total_amount','currency','payable_bill_id','receipt_baseline')}
 if action=='receive':
  state=await matching.receipt_state(db,po)
  values['receipt_events']=[{k:e.get(k) for k in ('id','status','items','operator_id','photo_path','remark','received_at')} for e in state['batches']]
 return fingerprint(values)

async def owned_order(db,wid,po_id,lock=False):
 q=select(PurchaseOrder).where(PurchaseOrder.id==po_id)
 if lock:q=q.with_for_update()
 po=(await db.execute(q)).scalar_one_or_none()
 if po is None:raise HTTPException(404,'当前仓库未找到该采购单')
 if po.warehouse_id!=wid:raise HTTPException(403,'无权操作其他仓库的采购单')
 return po

async def context(db,wid,user,po_id,action,operator_id=None):
 target=user
 if operator_id is not None and operator_id!=user.id:
  owner(user);target=await db.get(User,operator_id)
  member=(await db.execute(select(UserWarehouse.id).where(UserWarehouse.user_id==operator_id,UserWarehouse.warehouse_id==wid))).first()
  if target is None or target.role not in (Role.WAREHOUSE_ADMIN,Role.SUPERVISOR,Role.STAFF) or not (target.warehouse_id==wid or member):raise HTTPException(404,'本仓未找到可执行该动作的管理账号')
 po=await owned_order(db,wid,po_id);p=await policy(db,wid);v=await business(db,po,action);enabled=p['no_self_receive' if action=='receive' else 'no_self_approve']
 return {'purchase_order_id':po.id,'order_number':po.order_number,'action':action,'operator_id':target.id,'creator_id':po.created_by,'policy':p,'policy_version':p['version'],'business_version':v,'needs_exception':bool(enabled and po.created_by==target.id),'unknown_creator':bool(enabled and not po.created_by),'note':'例外只对指定采购/动作/账号/配置与业务版本有效一次；复核结论不是例外授权。'}

async def begin(db,po,user,action,request_key,payload,controls=None):
 await ensure_procurement_controls(await db.connection())
 meta={k:(controls or {}).get(k) for k in ('expected_policy_version','expected_business_version','exception_id')}
 if meta['exception_id'] is not None and (type(meta['exception_id']) is not int or meta['exception_id']<=0):raise HTTPException(400,'例外授权编号必须是正整数')
 for name in ('expected_policy_version','expected_business_version'):
  if meta[name] is not None and (not isinstance(meta[name],str) or not re.fullmatch('[a-f0-9]{64}',meta[name])):raise HTTPException(400,'职责或业务版本格式不正确')
 key=number(request_key if request_key is not None else f'legacy:{po.id}:{action}','请求编号',100);signature=fingerprint({'po_id':po.id,'action':action,'payload':payload,'controls':meta})
 old=await cached(db,po.warehouse_id,user,action,key,signature)
 if old:return {'replay':old}
 p=await policy(db,po.warehouse_id);enabled=p['no_self_receive' if action=='receive' else 'no_self_approve'];is_self=po.created_by==user.id
 if enabled and not po.created_by:raise changed('采购人账号未记录，无法判断职责，请老板核对；原请求未执行',key)
 if enabled and is_self and not meta['exception_id']:raise changed('采购人不能核准自己的采购，请老板明确授权例外' if action!='receive' else '采购人不能登记自己的收货，请老板明确授权例外',key,403)
 if enabled and not request_key:raise changed('职责规则已开启，请重新打开页面取得当前版本和请求编号；原请求未执行',key)
 if (enabled or meta['expected_policy_version'] is not None) and meta['expected_policy_version']!=p['version']:raise changed('采购职责配置已变化，请重新核对；原请求未执行',key)
 version=await business(db,po,action)
 if (enabled or meta['expected_business_version'] is not None) and meta['expected_business_version']!=version:raise changed('采购或收货依据已变化，请重新核对；原请求未执行',key)
 grant=None
 if meta['exception_id'] is not None:
  grant=(await db.execute(select(ExceptionGrant).where(ExceptionGrant.id==meta['exception_id']).with_for_update())).scalar_one_or_none()
  if (grant is None or grant.warehouse_id!=po.warehouse_id or grant.purchase_order_id!=po.id or grant.action!=action or grant.operator_id!=user.id or grant.policy_version!=p['version'] or grant.business_version!=version or grant.status!='active' or grant.expires_at<=thai_now()):raise changed('例外授权不适用、已失效或已使用；未执行操作',key,403)
 return {'po':po,'user':user,'action':action,'key':key,'signature':signature,'policy_version':p['version'],'grant':grant}

async def finish(db,ticket,response):
 return await save_execution(db,ticket['po'].warehouse_id,ticket['user'],ticket['action'],ticket['key'],ticket['signature'],ticket['policy_version'],response,ticket['po'],ticket['grant'])

def grant_value(g):
 return {k:getattr(g,k) for k in ('id','warehouse_id','purchase_order_id','action','operator_id','policy_version','business_version','granted_by','reason','expires_at','created_at','status','used_at','used_request_key','revoked_by','revoked_at','revoke_reason')}

async def grant(db,wid,user,*,po_id,action,operator_id,expected_policy_version,expected_business_version,expires_at,grant_reason,request_key):
 owner(user);why=reason(grant_reason);key=number(request_key,'请求编号',100)
 if expires_at.tzinfo is None:raise HTTPException(400,'请填写带时区的例外到期时间')
 signature=fingerprint({'po':po_id,'action':action,'operator':operator_id,'policy':expected_policy_version,'business':expected_business_version,'expires_at':expires_at.isoformat(),'reason':why})
 await matching.scope_lock(db,wid);await ensure_procurement_controls(await db.connection())
 previous=(await db.execute(select(ExceptionGrant).where(ExceptionGrant.warehouse_id==wid,ExceptionGrant.granted_by==user.id,ExceptionGrant.request_key==key))).scalar_one_or_none()
 if previous:
  if previous.request_fingerprint!=signature:raise HTTPException(409,'该授权请求已保存且内容不同')
  return {'data':grant_value(previous),'replayed':True}
 await owned_order(db,wid,po_id,True);c=await context(db,wid,user,po_id,action,operator_id)
 if expected_policy_version!=c['policy_version'] or expected_business_version!=c['business_version']:raise changed('配置或采购依据已变化，请重新核对后授权；原请求未执行',key)
 if c['unknown_creator']:raise HTTPException(409,'采购人未知，不能猜测后授权')
 if not c['needs_exception']:raise HTTPException(400,'该开关未启用或指定操作者不是采购人，无需本人操作例外')
 if expires_at<=thai_now():raise HTTPException(400,'例外到期时间必须在将来')
 row=ExceptionGrant(warehouse_id=wid,purchase_order_id=po_id,action=action,operator_id=operator_id,policy_version=expected_policy_version,business_version=expected_business_version,request_key=key,request_fingerprint=signature,granted_by=user.id,reason=why,expires_at=expires_at,status='active')
 db.add(row);await db.flush();value=jsonable_encoder(grant_value(row));await history(db,user,wid,'duty_grant',None,value,po_id);await db.flush();return {'data':grant_value(row),'message':'一次性例外已授权；仍须原业务权限，成功一次后失效'}

async def revoke(db,wid,user,ident,request_key,revoke_reason):
 owner(user);why=reason(revoke_reason);key=number(request_key,'请求编号',100);signature=fingerprint({'id':ident,'reason':why})
 await matching.scope_lock(db,wid);await ensure_procurement_controls(await db.connection())
 old=await cached(db,wid,user,'revoke',key,signature)
 if old:return old
 row=(await db.execute(select(ExceptionGrant).where(ExceptionGrant.id==ident).with_for_update())).scalar_one_or_none()
 if row is None or row.warehouse_id!=wid:raise HTTPException(404,'本仓未找到该例外授权')
 if row.status!='active':raise HTTPException(400,'该例外已使用或已撤销，不能再次撤销')
 before=jsonable_encoder(grant_value(row));row.status='revoked';row.revoked_by=user.id;row.revoked_at=thai_now();row.revoke_reason=why
 await history(db,user,wid,'duty_revoke',before,jsonable_encoder(grant_value(row)),row.purchase_order_id)
 p=await policy(db,wid)
 return await save_execution(db,wid,user,'revoke',key,signature,p['version'],{'message':'例外授权已撤销','data':jsonable_encoder(grant_value(row))})
