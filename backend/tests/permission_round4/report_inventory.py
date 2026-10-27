"""Link registered actions to actual requests; untested actions remain explicit."""
import json,re,inspect
from fixtures import app,OUT
from fastapi.routing import APIRoute
from app.core.round4_access import action_policy
routes=json.loads((OUT/'registered-routes.json').read_text());requests=json.loads((OUT/'requests.json').read_text())
actual={(r.path,m):r for r in app.routes if isinstance(r,APIRoute) for m in r.methods}
pages={'income_expense':'/operating; /other-income-expense','incoming':'/incoming','reconciliation':'/reconciliation','employees':'/employees','attendance':'/attendance; /my-leave; /my-attendance','clock_in':'/clock-in; /attendance','overtime':'/overtime; /my-overtime','salary_template':'/salary-templates','deduction_template':'/deduction-templates','employee_deduction':'/employee-deductions','expense_fund':'/expense-fund; /my-requests','reimbursement':'/reimbursement; /my-requests','employee_advance':'/employee-advances; /my-requests','payroll':'/payroll; /my-payslip'}
rows=[]
for r in routes:
 for method in r['method']:
  path=r['path'];expr='^'+re.sub(r'\{[^}]+\}',r'[^/]+',path)+'$'
  tests=[q for q in requests if q.get('method')==method and re.match(expr,'/api/v1'+q['path'].split('?')[0])]
  policy=action_policy(r['module'],r['handler'],[method]);source=inspect.getsource(actual[(path,method)].endpoint)
  conditions=[{'relative_line':n,'code':line.strip()} for n,line in enumerate(source.splitlines(),1) if any(x in line for x in ('status','warehouse','employee_id','current_user','permission','approved','review','paid','confirm','audit','history','for_update'))]
  category='A' if policy=='bookkeeping' else 'B' if policy in ('rules','audit') else 'C/D' if r['module'] in ('attendance','clock_in','overtime') else 'D' if r['module'] in ('expense_fund','reimbursement','employee_advance','payroll') else 'B/E'
  target={'bookkeeping':'主管禁止；财务/仓库管理员仍须原菜单、对象和状态守卫','rules':'仅授权仓库管理员；财务/主管禁止','audit':'保留前轮专用规则守卫并增加变更审计','scope':'保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助'}.get(policy,'保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出')
  rows.append({**r,'method':method,'action_id':f'R04-{len(rows)+1:03d}','area':category,'page':pages.get(r['module'],'既有页面，见handler/source；本轮未逐按钮核验'),'button':r['handler'],'action_ceiling':policy,'target_roles':target,'object_scope':'授权仓库；选仓头不得扩大范围；本人路径固定正式员工与主仓','fields':r['body'],'preconditions_and_service_checks':conditions,'handoff':'资金沿用二/三轮核验→管理员独立批准→独立执行；现场审批主管/管理员且非本人；本人事实确认不作批准','self_limit':'正式员工user_id、attendance_employee_id及相关用户判断；未改的资金入口保留fund_authorization','audit':'规则/敏感员工变更r04_change字段摘要；资金原审计保持；makeup_request为业务申请不是可忽略日志','tests':[{'id':q['id'],'expected':q['expected'],'actual':q['actual'],'errors':q['errors']} for q in tests],'evidence_level':'本地接口实际验证（只覆盖列出的样本）' if tests else '代码静态盘查；本轮未直接请求验证','unverified':'静态条件不是全路径证明；完整报表/导出/日志/附件管理权限留后轮'})
(OUT/'action-matrix.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
missing=[{k:r[k] for k in ('action_id','method','path','handler')} for r in rows if not r['tests']]
(OUT/'coverage.json').write_text(json.dumps({'registered_action_count':len(rows),'directly_requested':len(rows)-len(missing),'not_directly_requested':missing,'note':'本轮直接请求映射不含二/三轮复跑，未逐按钮/全部状态全覆盖'},ensure_ascii=False,indent=2))
lines=['# 第四轮逐动作权限及证据索引','','每一行一个注册方法/路径。详细输入字段、原守卫嵌套、服务位置和状态检查见同名JSON；未直接请求的项目不算通过。','','|编号|模块/页面|方法与路径|角色上限|本轮请求数|','|---|---|---|---|---|']
for r in rows:lines.append(f"|{r['action_id']}|{r['module']} / {r['page']}|{r['method']} {r['path']}|{r['target_roles']}|{len(r['tests'])}|")
(OUT/'ACTION-MATRIX.md').write_text('\n'.join(lines)+'\n')
print(len(rows),len(missing))
