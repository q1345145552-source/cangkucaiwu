"""Produce coverage/evidence indexes; enumeration is never counted as verification."""
import json,re,hashlib,subprocess,shutil,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'docs/permissions-round5-20261028';ENV=Path('/private/tmp/permissions-round5-env')
rows=json.loads((OUT/'read-inventory.json').read_text());original=json.loads((ROOT/'docs/permissions-audit-round1-20261028/action-matrix.json').read_text())
requests=[]
for label,file in [('r05','target-07/target-requests.json'),('r05-attachments','attachments-final-03/requests.json'),('r04','prior/round4-final/requests.json'),('r04-media','prior/round4-final/media-requests.json'),('r03','prior/round3-final/requests.json'),('r02','prior/round2-01/target-requests.json'),('r02-partial','prior/partial-01/requests.json')]:
 p=OUT/file
 if p.exists():
  for r in json.loads(p.read_text()):requests.append({**r,'evidence_file':file,'round':label})
def match(route,request):
 path=request.get('path','').split('?')[0]
 if not path.startswith(('/api/','/uploads/')):path='/api/v1'+path
 pattern=re.sub(r'\{[^}]+\}',r'[^/]+',route['path'].replace('{file_path:path}', '.+'))
 return re.fullmatch(pattern,path) and request.get('method','GET') in route['methods']
financial={'reports','cost_funds_debt','income_expense','incoming','reconciliation','payable','credit','cash_advance','cost_identity','salary_template','deduction_template','employee_deduction','payroll'}
menu={'employees':'employees','payroll':'payroll','customers':'customers','payment_accounts':'accounts','recharge':'recharge','employee_advance':'employee_advances','expense_approval':'expense_approval','expense_fund':'expense_fund','reimbursement':'reimbursement','efficiency':'labor_efficiency','history':'modification_logs','reports':'reports','cost_funds_debt':'reports','income_expense':'operating','incoming':'incoming','reconciliation':'reconciliation','payable':'payable','credit':'credit','cash_advance':'cash_advances','suppliers':'suppliers','salary_template':'salary_templates','deduction_template':'deduction_templates'}
policies={
'employees':('现场档案最小字段；不含薪资、银行、证件号码与扫描件','有工资菜单的财务可读必要薪资/银行；他人证件号码及扫描件不返回','管理员本仓档案','PAY_FIELDS、DOCUMENT_FIELDS服务端递归投影；原姓名/国籍/工作状态/有效期/现场事实保留'),
'efficiency':('保留工时/订单/人效，去人工成本与充值交叉统计','报表权限决定是否包含成本','授权仓库','去labor_cost/cost_per_order/cross_check；计算函数不改'),
'customers':('至少2字符具体搜索，拒绝通配符及第二页，最多20条；详情同最小字段','原客户/账期菜单范围','授权仓库','仅id/warehouse_id/customer_code/company_name/cargo_type/logistics_channel；财务对账主管拒绝'),
'payment_accounts':('仅账户选择元数据','原合法账户读取；无配置写权','授权仓库','主管仅id/warehouse_id/account_name/currency/status；无余额、银行账号'),
'history':('仅已授权现场模块，字段白名单','对应模块菜单；敏感凭证和身份字段脱敏','授权仓库；敏感凭证字段仍脱敏','SQL先过滤模块与仓库再分页/统计/导出；makeup_request排除且不删除'),
'dashboard':('现场stats及本人/现场待办；财务cockpit/trends/summary拒绝','财务+报表菜单；待办再按模块菜单','授权仓库','主管首页不返回全仓金额；boss-todos预支财务、加班现场职责分离'),
'secure_uploads':('本人正式绑定或现场职责实际引用；无他人工资/报销/证件权限','实际业务引用+对应财务菜单；本人单独绑定校验','实际授权对象仓库；临时上传仅真实上传者','每个实际引用均校验；缩略图同规则；安全响应不含真实路径'),
}
original_by_route={x['HTTP方法与路径']:x for x in original}
matrix=[]
for i,r in enumerate(rows,1):
 old_action=original_by_route.get(r['methods'][0]+' '+r['path'],{})
 mod=r['module'];e=[{'id':x.get('id',x.get('name')),'round':x['round'],'file':x['evidence_file'],'expected':x.get('expected'),'actual':x.get('actual',x.get('status')),'errors':x.get('errors',[])} for x in requests if match(r,x)]
 p=policies.get(mod)
 if p is None:
  p=('主管拒绝敏感财务管理读取；工资本人专用例外' if mod in financial else '沿用模块角色/菜单与对象限制；本人资金读取自动收窄', '原财务菜单+角色上限；本人功能正式绑定','管理员授权仓库；平台超管原限制保留','详见本行源码；未逐字段验证的接口不能称全覆盖')
 matrix.append({'动作编号':f'R05-{i:03}','模块':mod,'HTTP方法':r['methods'],'路径':r['path'],'参数筛选分页':r['query'],'请求体':r['body'],'后端位置':f"{Path(r['source']).relative_to(ROOT)}:{r['line']}",'后端守卫':r['guards'],'菜单':menu.get(mod,'见本行现有守卫及第一轮页面映射'),'主管':p[0],'财务':p[1],'管理员':p[2],'可见字段':p[3],'继承静态字段候选':old_action.get('可读可写字段',{'note':'新接口，见当前源码；没有声称全字段实测'}),'继承关联服务位置':old_action.get('后端鉴权及关联服务位置',{}).get('associated_functions',[]),'继承状态条件候选':old_action.get('单据前置状态',[]),'仓库本人对象范围':'真实授权仓库+选择范围；个人数据以唯一有效正式绑定和实际对象受益人校验；公共集市保留既有明确共享规则','允许状态':'读取不改变既有单据状态规则；本人失效绑定拒绝；不可把读取变为批准/执行','批准执行':'本轮无新资金状态、批准人或执行人政策；前四轮守卫保持','导出元信息':'实际导出内容见测试附件；所有API/上传no-store；异步导出任务未发现真实注册入口','页面':'前端静态映射见第一轮action-matrix；本轮实际页面见browser结果，非逐页全覆盖','验证方式':'本地实际接口' if e else '代码静态清单；本轮未直接请求','测试证据':e,'结论':'仅以上请求组合有证据；其他角色、状态、筛选组合未全覆盖'})
(OUT/'action-matrix.json').write_text(json.dumps(matrix,ensure_ascii=False,indent=2))
coverage={'registered_routes':len(json.loads((OUT/'route-catalog.json').read_text())),'read_query_export_attachment_routes':len(rows),'with_direct_request_evidence':sum(bool(x['测试证据']) for x in matrix),'uncovered':[{'id':x['动作编号'],'methods':x['HTTP方法'],'path':x['路径']} for x in matrix if not x['测试证据']],'not_present':['未发现客户专用批量导出接口（风险入口为列表大分页）','未发现独立异步导出任务创建/结果存储接口','未发现供应商资质/合同专用附件字段或路由；已有采购单PDF与收货图片','未发现通用全局搜索接口；模块搜索分别保留原菜单并收窄作用域'],'ai':'supplier ai_compare/ai_evaluate已纳入清单；未实际调用外部AI服务；供应商缓存ai_evaluation对非管理员不返回','warning':'路由枚举不是行为通过；清单中未覆盖项明确未测，原始source/guards保留在read-inventory.json'}
(OUT/'coverage.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2))
lines=['# 第五轮动作与覆盖索引','完整字段、参数、守卫、角色、范围、状态及证据见 action-matrix.json；下表仅便于检索。','', '|编号|模块|方法与路径|直接请求证据条数|','|---|---|---|---|']
for r in matrix:lines.append(f"|{r['动作编号']}|{r['模块']}|{'/'.join(r['HTTP方法'])} `{r['路径']}`|{len(r['测试证据'])}|")
(OUT/'ACTION-MATRIX.md').write_text('\n'.join(lines)+'\n')
# Full failures retained; compare actual assertion text, never merely equal names.
def xml(path):
 tree=ET.parse(path);suite=next(tree.iter('testsuite'));fail={}
 for c in tree.iter('testcase'):
  f=c.find('failure')
  if f is None:f=c.find('error')
  if f is not None:fail[c.attrib['classname']+'::'+c.attrib['name']]=f.text or f.attrib.get('message','')
 return {'summary':suite.attrib,'failures':fail}
inherited=json.loads((ROOT/'docs/permissions-r04-fix01-20261028/failure-comparison.json').read_text());comparisons={}
for group,filename in [('prior','regression-prior-02.xml'),('related','regression-related-01.xml')]:
 p=ENV/'logs'/filename
 if not p.exists():continue
 cur=xml(p);old={x['test']:x['current'] for x in inherited[group]['failures']}
 comparison=[]
 for name,actual in cur['failures'].items():
  previous=old.get(name)
  comparison.append({'test':name,'current':actual,'round4_actual':previous,'exact_text_equal':actual==previous,'conclusion':'原失败断言及当前全文并列；金额差异未修复。字典截断/顺序及新增行号不视为完全等价；静态恒等断言也叠加本轮合法读取变化。' if previous else '新增或待单独解释，不作为历史失败自动豁免'})
 comparisons[group]={'summary':cur['summary'],'previous_summary':inherited[group]['current_summary'],'comparisons':comparison}
for label in ('reads','reads-baseline','reads-01','reads-02','reads-dashboard-target','prior-cash-target'):
 p=ENV/'logs'/('regression-'+label+'.xml' if label.startswith('reads') and label!='reads-dashboard-target' else label+'.xml')
 if p.exists():comparisons[label]=xml(p)
(OUT/'failure-comparison.json').write_text(json.dumps(comparisons,ensure_ascii=False,indent=2))
raw=OUT/'raw-logs';raw.mkdir(exist_ok=True)
for p in (ENV/'logs').iterdir():
 if p.is_file() and p.suffix in ('.log','.exit','.xml','.json') and p.name not in ('postgres.log',):shutil.copy2(p,raw/p.name)
changed=subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True).splitlines();new=subprocess.check_output(['git','ls-files','--others','--exclude-standard','backend','frontend'],cwd=ROOT,text=True).splitlines()
source={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in changed+new if (ROOT/p).is_file() and p.startswith(('backend/','frontend/')) and 'node_modules' not in p}
manifest={'marker':'permissions7-r05-resume02-20261028','worktree':str(ROOT),'branch':subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),'baseline':'a28717065b9752e70094b06ad26660463b7d7a4f','head_at_collection':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'environment':str(ENV),'database':'127.0.0.1:65489, role round5, synthetic independent databases only','source_sha256':source,'exit_codes':{p.stem:p.read_text().strip() for p in (ENV/'logs').glob('*.exit')},'auth':'Real application JWT, routing, permission dependencies, PostgreSQL; no permissive auth substitutes','commands':['ROUND5_RUN=target-07 ROUND5_DATABASE_URL=postgresql+asyncpg://round5@127.0.0.1:65489/round5 /tmp/supplier01-py312/bin/python <worktree>/backend/tests/permission_round5/acceptance.py (cwd isolated environment)','ROUND5_RUN=<label> python <worktree>/backend/tests/permission_round5/prior_targets.py round4|round3|round2|partial (cwd isolated environment)','pytest commands/cwd/database recorded in raw-logs/regression-*.command.json','node frontend/node_modules/typescript/bin/tsc --noEmit --project frontend/tsconfig.json','node node_modules/next/dist/bin/next build (frontend copy matches tracked sources; no relaxed config)','ROUND5_RUN=browser-03 node backend/tests/permission_round5/browser_acceptance.cjs (real Chromium, localhost only)','python -m compileall -q backend/app backend/tests/permission_round5','git diff --check -- backend frontend'],'boundaries':{'models_changed':False,'migration':False,'inventory_cost_or_opening_changed':False,'production_access':False,'production_credentials_read':False,'push_fetch_deploy_ssh':False,'other_chat_dispatch':False,'automations_created':False},'evidence_gap':'target-01/02 initially shared target-requests.json: 01 per-request JSON overwritten by 02; both raw logs retained. No claim of complete 01 JSON. All later runs use separate output directories.'}
manifest['boundary_evidence']=json.loads((OUT/'boundary-verification.json').read_text())
manifest['shutdown_evidence']='raw-logs/shutdown.json'
(OUT/'validation-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps({k:v for k,v in coverage.items() if k not in ('uncovered',)},ensure_ascii=False,indent=2))
