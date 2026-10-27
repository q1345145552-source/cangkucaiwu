"""Reproducible registered-route catalogue with real dependency closures and source evidence.
No role/warehouse correctness is inferred from route coverage. Semantic review is tracked separately.
"""
import os,sys,json,inspect,ast,re,html
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'backend'))
assert not Path('.env').exists()
os.environ.setdefault('SECRET_KEY','synthetic-round-one-audit-only-signing-key')
from app.main import app
from app.core.menu_registry import MENU_PERMISSIONS_BY_KEY
from app.core.route_access import MODULE_KEYS
from fastapi.routing import APIRoute
OUT=ROOT/'docs/permissions-audit-round1-20261028'
MODULES={'users':'A01','auth':'A01','warehouses':'A01','payment_accounts':'A02','expense_fund':'A03','payroll':'A04','payable':'A05','reimbursement':'A05','employee_advance':'A05','expense_approval':'A05','cash_advance':'A05','income_expense':'A06','incoming':'A06','reconciliation':'A06','recharge':'A06','employees':'A07','attendance':'A07','clock_in':'A07','overtime':'A07','employee_deduction':'A07','salary_template':'A09','deduction_template':'A09','suppliers':'A08','inventory':'A08','sku_catalog':'A08','supplier_quotes':'A08','procurement_controls':'A08','procurement_risk':'A08','procurement_report':'A08','cost_identity':'A06','config_api':'A09','settings_api':'A09','exchange_rates':'A09','dashboard':'A10','reports':'A10','cost_funds_debt':'A10','history':'A10','efficiency':'A10','customers':'A10','secure_uploads':'A10','upload':'A10','credit':'A05','market':'OUT','group_order':'OUT','main':'OUT'}
SOURCES={}
def location(f):
 try:return str(Path(inspect.getsourcefile(f)).relative_to(ROOT))+':'+str(inspect.getsourcelines(f)[1])
 except:return str(f)
def source(f):
 try:
  key=location(f);SOURCES[key]=inspect.getsource(f);return key
 except:return 'source unavailable'
def deps(d):
 out=[]
 for x in d.dependencies:
  f=x.call;v={}
  if inspect.isfunction(f):
   for k,c in zip(f.__code__.co_freevars,f.__closure__ or ()):
    value=c.cell_contents
    if isinstance(value,(str,int,bool,list,tuple)):v[k]=value
    elif callable(value):v[k]=location(value)
  out.append({'name':getattr(f,'__qualname__',str(f)),'source':source(f),'closure':v,'dependencies':deps(x)})
 return out
def flatten(ds):
 return [d for x in ds for d in [x,*flatten(x['dependencies'])]]
def related(f):
 out=[];code=inspect.getsource(f);mod=inspect.getmodule(f)
 try:tree=ast.parse(code)
 except:return out
 values=dict(vars(mod))
 for n in ast.walk(tree):
  if isinstance(n,ast.ImportFrom) and n.module and n.module.startswith('app.'):
   try:
    m=__import__(n.module,fromlist=[a.name for a in n.names])
    for a in n.names:values[a.asname or a.name]=getattr(m,a.name,None)
   except Exception:pass
 for n in ast.walk(tree):
  if not isinstance(n,ast.Call):continue
  obj=None
  if isinstance(n.func,ast.Name):obj=values.get(n.func.id)
  elif isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name):obj=getattr(values.get(n.func.value.id),n.func.attr,None)
  if inspect.isfunction(obj) and getattr(obj,'__module__','').startswith('app.'):
   loc=source(obj)
   if loc not in out:out.append(loc)
 return out
def action(method,path,name):
 text=(path+' '+name).lower(); tail=path.rsplit('/',1)[-1]
 if method=='GET':
  for key,label in [('export','导出'),('/pdf','打印PDF'),('preview','预览'),('summary','汇总'),('stats','汇总'),('analysis','汇总'),('search','搜索'),('query','搜索'),('photo','附件下载'),('screenshot','附件下载'),('/uploads/','附件下载'),('template download','附件下载')]:
   if key in text:return label
  if any(k in text for k in ('threshold','settings','policy','limit','schedule','standard')):return '规则查询'
  return '详情' if '{' in path else '列表'
 for key,label in [('revoke','撤销'),('reverse','冲销'),('void','作废'),('batch-disburse','批量发放'),('batch-confirm','批量确认'),('batch-delete','批量删除'),('batch-recalc','批量重算'),('batch-import','批量导入'),('batch','批量操作'),('preview','预览'),('threshold','规则修改'),('settings','规则修改'),('policy','规则修改'),('/limit','规则修改'),('work-schedule','规则修改'),('reject','驳回'),('approve','批准'),('review','审核'),('verify','核实'),('confirm','确认'),('disburse','发放'),('execute','付款计划执行'),('topup','拨付'),('recalc','重算'),('calculate','核算'),('submit','提交'),('withdraw','撤回'),('toggle','启停'),('import','导入'),('upload','附件上传')]:
  if key in text:return label
 if tail=='pay' or name.startswith('pay_'):return '付款'
 return {'POST':'新建','PUT':'编辑','PATCH':'编辑','DELETE':'删除'}.get(method,method)
def targets(module,act,path,name):
 read=act in ('规则查询','列表','详情','汇总','搜索','预览','导出','打印PDF','附件下载')
 if any(k in name for k in ('my_payslip','get_today','clock_in')) and module in ('clock_in','payroll'):
  return {'主管':'本人且有效员工身份','财务':'本人且有效员工身份','管理员':'本人身份是否纳入需确认'}
 if module=='auth':return {r:'本人自助；登录/密码/附件会话按具体动作' for r in ('主管','财务','管理员')}
 if module in ('users','warehouses') and not read:return {'主管':'禁止管理他人账号、角色、仓库和权限','财务':'禁止管理他人账号、角色、仓库和权限','管理员':'本仓或授权仓范围；跨仓管理员和平台账号边界待确认'}
 rule=act=='规则修改' or module in ('salary_template','deduction_template') and not read
 if rule:return {'主管':'只提建议，不写规则','财务':'只提建议，不写规则','管理员':'决定并修改；受仓库/版本/留痕约束'}
 if read:return {'主管':'限职责必要字段和本人；全仓薪资/资金/成本利润/导出边界待业务确认','财务':'财务核算所需字段及本人；敏感字段与导出范围待业务确认','管理员':'本仓/授权仓所需字段；平台全局资料边界待确认'}
 if module=='payroll':
  if act in ('确认','批量确认'):return {'主管':'不确认工资表','财务':'不确认工资表','管理员':'确认已核算工资表'}
  if act in ('核算','重算','批量重算','发放','批量发放'):return {'主管':'禁止；仅确认考勤事实','财务':'核算；管理员确认后发放；重算回退交接待确认','管理员':'批准与监督；直接代执行范围待确认'}
  return {'主管':'不得借此核算/确认/发放；其他动作待确认','财务':'按P2；删除撤回冲销授权待确认','管理员':'删除撤回冲销前置状态及交接待确认；停用撤销保持拒绝'}
 if module in ('payable','reimbursement','expense_approval','employee_advance','cash_advance','expense_fund','income_expense','payment_accounts'):
  if act in ('付款','付款计划执行','发放','批量发放','拨付'):
   return {'主管':'禁止付款/资金执行','财务':'管理员批准后执行；本人单据不得本人支付','管理员':'批准；财务本人单据由管理员或另一独立授权付款人执行'}
  if act in ('审核','批准','确认','批量确认'):
   return {'主管':'禁止审批资金','财务':'审核依据；本人单据不得自审；不代管理员批准','管理员':'批准；财务本人单据审核批准'}
  if module=='income_expense':return {'主管':'禁止直接记正式账目','财务':'已批准依据后记账；撤回/删除/分类规则待细化','管理员':'批准及规则决定；冲销职责待确认'}
  return {'主管':'可本人申请/提交事实；账户、正式账、资金审批禁止；其余待确认','财务':'本人申请保留；财务登记与依据审核；不得自审自付','管理员':'批准及规则决定；具体撤回/删除/冲销状态待确认'}
 if module in ('attendance','overtime','clock_in','employees','employee_deduction'):
  return {'主管':'确认考勤事实；本人不得自批；不得改薪资标准','财务':'本人自助；依据已确认事实核算；他人事实变更待确认','管理员':'规则决定及监督；主管本人事实由谁核实待确认，不自动指定'}
 return {'主管':'按P1–P5；采购/库存具体事实动作授权待确认，不给资金批准权','财务':'依据审核；采购/库存事实动作授权待确认','管理员':'规则决定/资金批准；具体采购库存状态及职责例外待确认'}
def expressions(code,pattern):
 lines=code.splitlines();return [' '.join(lines[max(0,i-1):min(len(lines),i+2)]).strip() for i,l in enumerate(lines) if re.search(pattern,l)][:40]
def fields(route):
 result={}
 for field in route.dependant.body_params:
  typ=getattr(field,'type_',None)
  if hasattr(typ,'model_fields'):result[field.name]=list(typ.model_fields)
  else:result[field.name]=str(typ)
 result['query']=[f.name for f in route.dependant.query_params]
 return result
rows=[];counts={}
for route in app.routes:
 if not isinstance(route,APIRoute):continue
 f=route.endpoint;module=f.__module__.split('.')[-1];src=inspect.getsource(f);ds=deps(route.dependant);fl=flatten(ds);links=related(f)
 for method in sorted(route.methods):
  mod=MODULES.get(module,'OUT');counts[mod]=counts.get(mod,0)+1;ident=f'{mod}-{counts[mod]:03d}';act=action(method,route.path,f.__name__)
  perm=[{'name':d['name'],'values':d['closure'],'source':d['source']} for d in fl if d['closure'] or any(k in d['name'] for k in ('require_','reject_','employee_access','expense_user'))]
  rolechecks=expressions(src,r'\.role|ROLE_HIERARCHY|ensure_.*(editor|owner)|_check_manage_role')
  pagekey=MODULE_KEYS.get(module,module);menu=MENU_PERMISSIONS_BY_KEY.get(pagekey)
  condition='统一依赖 '+json.dumps(perm,ensure_ascii=False)+'；动作内角色条件 '+json.dumps(rolechecks,ensure_ascii=False)
  rows.append({'动作编号':ident,'模块':mod+' '+module,'具体动作':act+' '+f.__name__,'页面及按钮':(menu.path if menu else '需按调用点核对')+'；按钮映射未逐一页面验证','HTTP方法与路径':method+' '+route.path,'后端鉴权及关联服务位置':{'handler':source(f),'dependencies':ds,'associated_functions':links},'主管当前允许条件':'角色=supervisor；'+condition,'财务当前允许条件':'角色=staff；'+condition,'管理员当前允许条件':'角色=warehouse_admin；'+condition,'三个角色的目标权限':targets(module,act,route.path,f.__name__),'本人／本仓／授权仓库范围':expressions(src,r'warehouse|wh_id|employee_view|own_employee|employee_id.*user|user.*employee_id'),'可读可写字段':{'request_fields':fields(route),'response_keys':sorted(set(re.findall(r'[\"\x27]([a-z][a-z0-9_]+)[\"\x27]\s*:',src))),'note':'静态提取候选字段，动态服务返回见关联源码；不是已验证字段白名单'},'单据前置状态':expressions(src,r'\.status|\.disbursed|\.is_voided|approval_status|review_status'),'申请、审核、批准、执行人的交接':expressions(src,r'applicant|reviewer|approver|payer|operator|created_by|confirmed_by|paid_by'),'自批或本人付款限制':expressions(src,r'本人|自己|self.approv|employee_id.*\.id|applicant_id.*\.id|created_by.*\.id'),'审计记录':{'global':'backend/app/core/audit.py AuditMiddleware：成功写操作通用审计；非逐字段历史，也非全部拒绝/读取审计','local':expressions(src,r'record_history|audit|reviewed_by|reviewed_at|paid_by|payer_id|operator_id|created_by')},'验证方式、测试编号及证据':{'static':'注册路由、真实依赖闭包及处理函数源码已提取；关联服务逐项语义审阅见问题清单','api':[],'page':'未验证'},'结论与待确认事项':'路由登记≠完整语义审计。未在问题清单展开的关联服务、字段与按钮均须继续核对；目标含待确认项。','access_kind':(route.openapi_extra or {}).get('x-access-kind'),'module_key':module,'endpoint_name':f.__name__,'method':method,'path':route.path,'source':source(f)})
# Link actual observations using registered regex; preserve missing paths separately.
logs=json.loads((OUT/'requests.json').read_text()) if (OUT/'requests.json').exists() else []
unmatched=[]
for log in logs:
 path=log['path'].split('?')[0];path=path if path.startswith('/uploads/') else '/api/v1'+path
 matches=[r for r in app.routes if isinstance(r,APIRoute) and log['method'] in r.methods and r.path_regex.fullmatch(path)]
 if not matches:unmatched.append(log['id']);continue
 route=matches[0]
 for row in rows:
  if row['path']==route.path and row['method']==log['method']:row['验证方式、测试编号及证据']['api'].append(log['id'])
(OUT/'registered-actions.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2,default=str))
(OUT/'source-evidence.json').write_text(json.dumps(SOURCES,ensure_ascii=False,indent=2))
coverage={'registered_http_actions':len(rows),'module_counts':counts,'api_exercised_routes':sum(bool(r['验证方式、测试编号及证据']['api']) for r in rows),'api_unexercised':[{'id':r['动作编号'],'route':r['HTTP方法与路径'],'source':r['source']} for r in rows if not r['验证方式、测试编号及证据']['api']],'out_of_scope':[r['HTTP方法与路径'] for r in rows if r['模块'].startswith('OUT')],'unmatched_requests':unmatched,'warning':'仅登记清单全量；未声称静态语义、角色组合、字段、状态或页面全覆盖。'}
(OUT/'coverage.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2))
# Local readable artifact; no external scripts, network or publish.
columns=list(rows[0])[:18]
head='<html lang="zh"><meta charset="utf-8"><title>第一轮权限现状与目标动作矩阵</title><style>body{font:14px system-ui;margin:20px}table{border-collapse:collapse}td,th{border:1px solid #ccd;padding:8px;vertical-align:top;min-width:180px;max-width:500px}th{position:sticky;top:0;background:#edf2fa}pre{white-space:pre-wrap;max-height:360px;overflow:auto}input{width:70%;padding:12px}tr.hide{display:none}</style><h1>第一轮权限现状与目标动作矩阵</h1><p>基线 854e389；本地合成数据。原始条件按真实依赖与源码展开，不把路由登记当完整语义审计。实际请求见 requests.json，深度审阅见报告。没有页面验证的按钮不推断安全。</p><input id="q" placeholder="搜索模块、路径、动作、测试编号"><table><thead><tr>'+''.join('<th>'+html.escape(k)+'</th>' for k in columns)+'</tr></thead><tbody>'
body=''
for r in rows:
 body+='<tr>'+''.join('<td><pre>'+html.escape(json.dumps(r[k],ensure_ascii=False,indent=2) if isinstance(r[k],(dict,list)) else str(r[k]))+'</pre></td>' for k in columns)+'</tr>'
end='</tbody></table><script>q.oninput=()=>document.querySelectorAll("tbody tr").forEach(r=>r.classList.toggle("hide",!r.textContent.toLowerCase().includes(q.value.toLowerCase())))</script></html>'
(OUT/'action-matrix.html').write_text(head+body+end)
print(json.dumps({k:v for k,v in coverage.items() if k not in ('api_unexercised','out_of_scope')},ensure_ascii=False))
