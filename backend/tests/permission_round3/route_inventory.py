"""Registered route inventory; no application startup or external connections."""
from fixtures import *
import inspect
from fastapi.routing import APIRoute
prefixes={'payroll':'A','reimbursement':'B','employee-advances':'C','cash-advances':'C','payable':'D','employees':'A'}
rows=[]
for route in app.routes:
 if not isinstance(route,APIRoute):continue
 bits=route.path.split('/');module=bits[3] if len(bits)>3 else ''
 if module not in prefixes:continue
 if module=='employees' and route.endpoint.__name__ not in ('resign_employee','delete_employee','update_employee'):continue
 fn=route.endpoint;deps=[]
 def collect(d):
  for x in d.dependencies:
   name=getattr(x.call,'__qualname__',str(x.call))
   if name not in deps:deps.append(name)
   collect(x)
 collect(route.dependant);methods=sorted(route.methods);action=fn.__name__
 if 'revoke' in action:target='停用守卫拒绝；内部遗留代码不代表可用入口'
 elif methods==['GET']:target='原本仓读取授权；主管工资仅本人my-payslip；非全量导出/字段收口'
 elif action in ('confirm_payroll','confirm_all_payroll','batch_confirm_payroll','review_reimb','approve_advance','confirm_advance','approve_bill_payment'):target='管理员独立批准；本人/别名禁止；核验、快照、状态校验'
 elif action in ('disburse_payroll','batch_disburse_payroll','pay_reimb','execute_advance','repay_advance','pay_bill','execute_plan'):target='独立财务执行；财务本人可由管理员独立执行；管理员批准，最多一次资金效果'
 elif action.startswith('verify_'):target='独立财务/管理员核验；不批准、不出款'
 elif module=='payroll':target='管理员/财务核算；主管禁止；草稿可重算删除，已确认限管理员，已付禁止'
 elif action=='return_reimb':target='管理员退回未支付普通单，旧证据失效'
 elif action=='void_bill':target='仅管理员，保留原状态约束'
 else:target='本仓原申请/事实/附件能力；本轮批准失效及角色上限，非全系统改造'
 rows.append({'id':prefixes[module]+'-'+str(len(rows)+1).zfill(3),'module':module,'methods':methods,'path':route.path,'handler':action,'source':str(Path(inspect.getsourcefile(fn)).relative_to(ROOT))+':'+str(inspect.getsourcelines(fn)[1]),'registered_guards':deps,'parameters':str(inspect.signature(fn)),'target':target,'scope':'授权当前仓库、有效账号、对象归属、本人/关联员工别名','ui':'/'+module,'evidence':'requests.json按method/path对照，未匹配仅静态确认'})
(OUT/'registered-actions.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
lines=['# 第三轮动作权限表','','实际应用注册路由；完整参数和依赖见registered-actions.json。页面payable的plans分支位于payment-plans。未直测项见coverage.json，不声称全覆盖。','','|编号|方法与路径|页面|角色、状态及交接|后端位置|','|---|---|---|---|---|']
for r in rows:lines.append('|'+ '|'.join([r['id'],','.join(r['methods'])+' '+r['path'],r['ui'],r['target'],r['source']])+'|')
(OUT/'ACTION-PERMISSIONS.md').write_text('\n'.join(lines)+'\n');print('registered actions',len(rows))
