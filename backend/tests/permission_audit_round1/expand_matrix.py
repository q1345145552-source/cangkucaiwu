"""Expand compound API field/actions, add frontend source candidates and test observations."""
import json,copy,re,html
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'docs/permissions-audit-round1-20261028'
rows=json.loads((OUT/'registered-actions.json').read_text());logs=json.loads((OUT/'requests.json').read_text());byid={r['id']:r for r in logs}
ui=json.loads((OUT/'browser-results.json').read_text())['result']
front=[(str(p.relative_to(ROOT)),p.read_text().splitlines()) for p in (ROOT/'frontend/src').rglob('*') if p.is_file() and p.suffix in ('.ts','.tsx')]
extras=[]
for row in rows:
 path=row['path'].removeprefix('/api/v1');prefix=path.split('{')[0].rstrip('/');calls=[]
 if len(prefix)>3:
  for filename,lines in front:
   for n,l in enumerate(lines,1):
    if prefix in l and any(x in l for x in ('api.','fetch(','API_URL','endpoint','href:')):calls.append({'file':filename+':'+str(n),'line':l.strip()[:500]})
 row['页面及按钮']={'menu_hint':row['页面及按钮'],'static_call_candidates':calls,'warning':'前缀匹配仅为定位候选；具体按钮语义需结合页面分支。下列UI证据只覆盖列明页面。','page_evidence':[x['id'] for x in ui if x.get('url') and path.startswith(x['url'])]}
 row['验证方式、测试编号及证据']['observed']=[{'test':ident,'role':byid[ident]['role'],'status':byid[ident]['status'],'changed_tables':byid[ident]['changed_tables']} for ident in row['验证方式、测试编号及证据']['api']]
 row['验证方式、测试编号及证据']['page']=row['页面及按钮']['page_evidence'] or '未验证'
 # Separate actions sharing one route. No new endpoint is implied.
 splits=[];fn=row['endpoint_name'];method=row['method'];query=row['可读可写字段']['request_fields'].get('query',[])
 if method=='GET' and any(k in query for k in ('name','search','keyword','q')):splits.append(('搜索','使用原查询参数 '+','.join(k for k in query if k in ('name','search','keyword','q'))))
 if method=='GET' and 'format' in query:splits.append(('导出','format=excel；复用该接口，不等同JSON列表已验证'))
 if fn=='update_user':splits += [('重置密码','password'),('启停账号','is_active'),('变更角色','role'),('变更仓库','warehouse_ids / warehouse_id'),('变更扩展权限','extra_permissions'),('员工身份绑定开关','attendance_enabled')]
 if fn=='update_account' and row['module_key']=='payment_accounts':splits += [('账户期初修改','opening_balance / opening_balance_date'),('账户币种修改','currency；已有资金记录等前置约束')]
 if fn=='update_employee':splits += [('员工薪资字段修改','daily_wage / base_salary / salary_template_id'),('员工证件银行字段修改','nationality / passport / work_permit / thai_id_number / sso_number / bank_account_number等')]
 if fn in ('batch_review','review_recharge_request'):splits += [('批准','action=approve'),('驳回','action=reject')]
 if fn=='review_count':splits += [('批准盘点','decision=approve'),('驳回盘点','decision=reject')]
 if fn in ('recalc_payroll','batch_recalc_payroll'):splits += [('作废','mode=void'),('重算','mode=recalc')]
 if fn.startswith(('import_products','import_logistics')):splits += [('预览','mode=preview'),('批量导入','mode=confirm；版本/请求编号/选择参数仍生效')]
 if fn=='update_settings' and row['module_key']=='expense_fund':splits += [('规则修改',f'通用key={key}') for key in ('fund_limit','fund_alert_threshold','purchase_approval_threshold','procurement_price_threshold','supplier_concentration_threshold','overtime_monthly_limit','purchase_duty_separation_v1')]
 for n,(act,selector) in enumerate(splits,1):
  x=copy.deepcopy(row);x['动作编号']+='.'+str(n);x['具体动作']=act+' ['+selector+']';x['参数分支']=selector;x['结论与待确认事项']='同一接口中的独立动作；不能用该接口另一分支成功代替本分支验证。'+row['结论与待确认事项']
  if act in ('账户期初修改','员工薪资字段修改'):
   x['三个角色的目标权限']={'主管':'不允许修改，只提建议','财务':'不允许修改，只提建议','管理员':'本仓/授权仓决定；记录变更依据和历史'}
  if fn=='update_user':x['三个角色的目标权限']={'主管':'不得管理他人账号角色仓库权限','财务':'不得管理他人账号角色仓库权限','管理员':'本仓/授权仓；平台账号及管理员改角色边界待确认'}
  extras.append(x)
rows+=extras
(OUT/'action-matrix.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
columns=list(rows[0])[:18]
head='<html lang="zh"><meta charset="utf-8"><title>权限审计动作矩阵</title><style>body{font:14px system-ui;margin:20px}table{border-collapse:collapse}td,th{border:1px solid #ccd;padding:8px;vertical-align:top;min-width:160px;max-width:480px}th{position:sticky;top:0;background:#edf2fa}pre{white-space:pre-wrap;max-height:320px;overflow:auto}input{width:70%;padding:12px}tr.hide{display:none}</style><h1>现状与目标动作矩阵</h1><p>基线854e389；本地合成测试。'+str(len(rows))+'行包括同接口不同动作分支。注册接口登记全量不代表语义和状态全覆盖。空条件提取不表示无条件允许，必须沿鉴权链和关联服务阅读。详见报告及覆盖缺口。</p><input id="q" placeholder="搜索动作ID、模块、路径、测试编号"><table><thead><tr>'+''.join('<th>'+html.escape(k)+'</th>' for k in columns)+'</tr></thead><tbody>'
body=''
for r in rows:
 body+='<tr>'+''.join('<td><pre>'+html.escape(json.dumps(r[k],ensure_ascii=False,indent=2) if isinstance(r[k],(dict,list)) else str(r[k]))+'</pre></td>' for k in columns)+'</tr>'
(OUT/'action-matrix.html').write_text(head+body+'</tbody></table><script>q.oninput=()=>document.querySelectorAll("tbody tr").forEach(r=>r.classList.toggle("hide",!r.textContent.toLowerCase().includes(q.value.toLowerCase())))</script></html>')
(OUT/'target-matrix.json').write_text(json.dumps([{'动作编号':r['动作编号'],'具体动作':r['具体动作'],'HTTP方法与路径':r['HTTP方法与路径'],'参数分支':r.get('参数分支'),'目标权限':r['三个角色的目标权限']} for r in rows],ensure_ascii=False,indent=2))
print('matrix rows',len(rows),'additional action branches',len(extras))
