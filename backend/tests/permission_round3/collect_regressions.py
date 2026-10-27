"""Compare actual assertions; never equate matching test names with matching causes."""
from pathlib import Path
import xml.etree.ElementTree as ET,json,re,collections,subprocess,ast
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'docs/permissions-round3-20261028';ENV=Path('/private/tmp/permissions-round3-env')
def read(name):
 rows={}
 for t in ET.parse(ENV/'logs'/name).findall('.//testcase'):
  f=t.find('failure');e=t.find('error');skip=t.find('skipped');node=f if f is not None else e
  rows[t.attrib['classname']+'::'+t.attrib['name']]={'result':'fail' if f is not None else 'error' if e is not None else 'skip' if skip is not None else 'pass','message':node.attrib.get('message','') if node is not None else '', 'trace':node.text if node is not None else ''}
 return rows
current=read('regression-current-02.xml');base=read('regression-baseline-02.xml');final=read('guard-regression-final.xml');rows=[]
for name,c in current.items():
 b=base.get(name,{'result':'not-collected','message':'','trace':''});latest=final.get(name,c)
 if c['result']=='pass':continue
 msg=c['message'];reason='';evidence=''
 if latest['result']=='pass':kind='已按新授权更新有效断言并定向通过';reason='主管管理工资改为拒绝；新增离职待核算接口仍受劳工守卫；保留原本人查询、其他角色、无副作用断言。';evidence='guard-regression-final.xml'
 elif c['message']==b['message'] and c['trace'].split('E   ')[-1]==b['trace'].split('E   ')[-1]:kind='基线存在相同首个断言';reason='对照实际返回/数值及失败断言相同；仅证明首个失败，不能推断之后未执行断言。';evidence='baseline/current-02 XML全文'
 elif any(x in name for x in ('test_original_handlers_and_calculations_are_byte_identical','test_no_payroll_calculation_or_other_financial_module_changes','test_salary_functions_and_cap_unchanged','test_payment_and_repayment_business_functions_unchanged','test_unchanged_review_and_payroll_math')):kind='源码恒等断言含历史差异及授权变更';reason='基线与当前均有各自源码差异，不能说同根因；本轮新增守卫、阶段、能力与批准证据使恒等要求不成立。纯工资计算函数另做AST对照。';evidence='formula-preservation.json'
 else:
  kind='第三轮授权变化使旧流程断言不再成立'
  if 'pending' in msg and any(x in msg for x in ('confirmed','approved')):reason='旧用例期待新建即确认/批准；现在仅申请待核验，不能恢复自动资金授权。'
  elif '缺少有效核验' in msg or '409' in msg:reason='旧合成已确认/已批准对象未走独立核验及管理员批准快照，安全拒绝；不能伪造批准以保留旧200。'
  elif '仅获授权财务' in msg or '无权查看工资数据' in msg:reason='旧主管/管理员直接付款或主管全仓工资行为被职责上限拒绝。'
  elif '不重复' in msg:reason='批量重复ID由旧去重改为整批拒绝；新批量有效和混合非法测试分别验证。'
  elif 'KeyError' in msg:reason='旧垫款来源没有有效批准，创建预支已拒绝，旧测试继续取id导致KeyError；后续金额断言未执行。'
  elif 'DID NOT RAISE' in msg or '500' in msg:reason='原故障注入点位于新建/批准即付款旧路径，新流程不执行该写入；已在真实执行阶段补故障回滚与重试。'
  elif '400' in msg or '422' in msg or '403' in msg:reason='新状态/角色/对象范围检查使旧入口更早拒绝，或旧未执行预支没有扣款可阻止作废；详见保留的具体请求和断言。'
  else:reason='旧用例金额/关联记录断言依赖创建或批准立即出款；现在资金效果仅发生在独立execute。原断言未删除，不把此运行称通过。'
  evidence='requests.json A/B/C/D 成功、金额、自付、并发、回滚分组；旧后续断言未跑到'
 rows.append({'test':name,'current':c,'baseline':b,'latest_targeted':latest if name in final else None,'classification':kind,'reason':reason,'replacement_evidence':evidence})
(OUT/'regression-comparison.json').write_text(json.dumps({'current_counts':dict(collections.Counter(x['result'] for x in current.values())),'baseline_counts':dict(collections.Counter(x['result'] for x in base.values())),'targeted_counts':dict(collections.Counter(x['result'] for x in final.values())),'rows':rows},ensure_ascii=False,indent=2))
lines=['# 相关回归：实际断言对照','','完整当前运行284项（139通过、145失败），基线283项（211通过、72失败）；0跳过。数量差异来自新增离职待核算路由被动态劳工守卫测试收集。最终守卫定向结果见下。不能把新增失败全部称历史失败，也不能把旧流程失败称通过。','','初次运行从隔离环境目录启动，1项git show提前失败且2项缺PGlite跳过；已完整从各自有Git历史的backend目录重跑并提供本地PGlite，第二次全部到达测试断言。原日志保留，不使用首次环境错误作为基线证据。','','|类别|数量|','|---|---|']
for k,v in collections.Counter(x['classification'] for x in rows).items():lines.append(f'|{k}|{v}|')
lines+=['',f'最终劳工边界及采购职责定向：{dict(collections.Counter(x["result"] for x in final.values()))}。原失败逐项保留，增加的新拒绝并非删除有效断言。','','|用例|具体归因|替代/复核证据|','|---|---|---|']
for r in rows:lines.append('|'+r['test'].replace('|','/')+'|'+r['reason']+'|'+r['replacement_evidence']+'|')
(OUT/'REGRESSION.md').write_text('\n'.join(lines)+'\n')
# Formula check is scoped to the actual computation function, not whole-module source identity.
path='backend/app/api/v1/payroll.py';old=subprocess.check_output(['git','show','e6cc888:'+path],cwd=ROOT,text=True);new=(ROOT/path).read_text()
def function(s,n):return ast.dump(next(x for x in ast.parse(s).body if isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef)) and x.name==n),include_attributes=False)
checks={n:function(old,n)==function(new,n) for n in ('_compute_employee_records','_rollback_advance_deductions')}
(OUT/'formula-preservation.json').write_text(json.dumps({'baseline':'e6cc888187d8ecf21abe56118565879edc4c0312','AST_equal':checks,'limits':'_prepare_payroll含角色/员工范围/离职事实守卫，不宣称整个模块源码相同；库存计价与金额公式文件未改。'},ensure_ascii=False,indent=2))
assert all(checks.values()),checks
print(collections.Counter(x['classification'] for x in rows))
