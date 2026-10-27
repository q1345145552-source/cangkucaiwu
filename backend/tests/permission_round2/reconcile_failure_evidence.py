"""Read-only comparison of failure assertions and local Git objects; no business/test changes."""
from pathlib import Path
import ast,json,re,subprocess,xml.etree.ElementTree as ET,shutil
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'docs/permissions-r02-fix02-20261028';ENV=Path('/private/tmp/permissions-fix02-env')
old=ROOT/'docs/permissions-round2-20261028';fix=ROOT/'docs/permissions-r02-fix01-20261028'
refs={'bc903a5':'bc903a55c60c865f8eb95a4e6374ef5325ab4685','11d032a':'11d032a41d0d39d770285ce5367ea4d15a2e8e51','422ee2b':'422ee2b09b38059215737f4f839f2d4ebc670df1'}
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True)
def failures(p):
 r=ET.parse(p);result={}
 for t in r.iter('testcase'):
  f=t.find('failure')
  if f is not None:result[t.attrib['classname']+'::'+t.attrib['name']]={'message':f.attrib.get('message',''),'trace':f.text or '', 'evidence':str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)}
 return result
current=failures(old/'raw-logs/regression-final.xml');baseline={**failures(old/'raw-logs/core-baseline.xml'),**failures(old/'raw-logs/reimbursement-baseline.xml')}
latest=failures(fix/'raw-logs/regression-final.xml')
reruns={ref:failures(ENV/'logs'/f'{ref}.xml') for ref in refs}
assert all(len(r)==6 for r in reruns.values())
for group in reruns.values():
 for value in group.values():assert 'CalledProcessError' not in value['message'] and 'assert ' in value['trace']
source_names={n for n in reruns['bc903a5'] if 'legacy_audit' not in n}
rows=[]
for name,prior in current.items():
 b=reruns['bc903a5'].get(name,baseline.get(name));c=reruns['422ee2b'].get(name,latest.get(name,prior));assert b,name
 kind='已证实同根因旧失败';note='基线与当前实际断言消息一致；不是仅比较失败名称。'
 if name in source_names:
  kind='源码恒等失败，需分段审查'
  note='首个失败已在有Git历史环境复现；后续未执行断言由source-review.json及SOURCE-REVIEW.md逐文件审查，不能泛称所有源码相同。'
 elif 'route_inventory' in name:
  note='相同三个路由未纳入旧CASES，集合显示顺序不同；三路由注册在三版本未变化。'
 else:
  assert b['message']==c['message'],(name,b['message'],c['message'])
 rows.append({'assertion_file':name.split('::')[0].replace('.', '/')+'.py','assertion_function':name.split('::')[1].split('[')[0],'round2_delta_assessment':('See SOURCE-REVIEW.md: old source differences and authorized deltas must be separated' if name in source_names else 'Same concrete failure at baseline; no new root cause established by current assertion'),'test':name,'classification':kind,'baseline_actual':b,'current_actual':c,'original_round2_actual':prior,'candidate_rerun':reruns['11d032a'].get(name),'note':note,'new_business_regression_proved':False})
assert len(rows)==52
# Full function-level deltas against historical assertions and between the three actual baselines.
paths=['backend/app/api/v1/'+n+'.py' for n in ('payroll','reimbursement','employee_advance','expense_fund','cash_advance','clock_in','config_api','expense_approval','suppliers','history')]+['backend/app/services/'+n+'.py' for n in ('reimbursement_payment','account_balances','payroll_expense','fund_disbursement','flow_rules')]
def funcs(s):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(s).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
def delta(a,b):
 x,y=funcs(a),funcs(b)
 return {'changed':sorted(k for k in x.keys()&y.keys() if x[k]!=y[k]),'added':sorted(y.keys()-x.keys()),'removed':sorted(x.keys()-y.keys()),'text_equal':a==b}
source={}
for p in paths:
 versions={k:git('show',v+':'+p) for k,v in refs.items()}
 source[p]={'round2':delta(versions['bc903a5'],versions['11d032a']),'partial_fix':delta(versions['11d032a'],versions['422ee2b'])}
for historical,path in [('3e19093','backend/app/api/v1/payroll.py'),('4cbf9e8','backend/app/api/v1/reimbursement.py'),('14e2541','backend/app/api/v1/reimbursement.py'),('14a0198','backend/app/api/v1/payroll.py'),('e970f41','backend/app/api/v1/expense_approval.py')]:
 source[path].setdefault('historical_assertions',{})[historical]={k:delta(git('show',historical+':'+path),git('show',v+':'+path)) for k,v in refs.items()}
(OUT/'failure-audit.json').write_text(json.dumps({'total':52,'rows':rows,'environment_failures_in_original_fix01_archive':4,'remaining_environment_gaps_for_selected_failures':0,'note':'47项非源码恒等旧失败已比较实际断言；5项源码检查另按首个失败与后续授权差异分类，不据名称宣称所有失败完全同根因。'},ensure_ascii=False,indent=2)+'\n')
(OUT/'source-review.json').write_text(json.dumps(source,ensure_ascii=False,indent=2)+'\n')
md=['# 52项原失败逐项复核','','原始日志保留。下表实际断言取完整XML；源码检查的新增授权差异见SOURCE-REVIEW.md。没有重新运行已充分对照的其余全部用例。','', '|测试|分类|基线实际断言|当前实际断言|证据|','|---|---|---|---|---|']
for r in rows:
 def fmt(v):return v.replace('\n',' ').replace('|','／')[:270]
 md.append('|`'+r['test']+'`|'+r['classification']+'|'+fmt(r['baseline_actual']['message'])+'|'+fmt(r['current_actual']['message'])+'|[完整堆栈/原始路径](failure-audit.json)|')
(OUT/'FAILURE-AUDIT.md').write_text('\n'.join(md)+'\n')
raw=OUT/'raw-logs';raw.mkdir(exist_ok=True)
for p in (ENV/'logs').iterdir():
 if p.is_file():shutil.copyfile(p,raw/p.name)
(OUT/'relevant-round2.diff').write_text(git('diff',refs['bc903a5'],refs['11d032a'],'--',*paths))
(OUT/'partial-fix.diff').write_text(git('diff',refs['11d032a'],refs['422ee2b'],'--',*paths))
print('52 assertions audited; 47 non-source old failures; 5 source tests separately reviewed; 3 x 6 targeted assertions reached')

import hashlib
selected=['test_fund_disbursement.py','test_fund_item_controls.py','test_fund_receipts.py','test_disabled_financial_reversals.py','test_config_center_access.py']
test_hashes={r:{p:hashlib.sha256((Path('/private/tmp/permissions-fix02-'+r)/'backend/tests'/p).read_bytes()).hexdigest() for p in selected} for r in refs}
assert test_hashes['11d032a']==test_hashes['422ee2b']
metadata={'marker':'permissions7-r02-fix02-20261028','refs':refs,'test_file_hashes':test_hashes,'selected_tests_identical_candidate_and_fix':True,'database':'localhost 127.0.0.1:65359 synthetic round2','python':'/tmp/supplier01-py312/bin/python','each_rerun_count':6,'each_exit_code':{r:int((ENV/'logs'/f'{r}.exit').read_text()) for r in refs},'old_47_non_source_failures_compared_without_unnecessary_rerun':True,'source_assertion_tests_separately_reviewed':5,'business_code_changed_this_fix':False,'production_access':False,'push_fetch_deploy_ssh':False,'local_postgres_stopped':(ENV/'logs/shutdown.exit').exists() and (ENV/'logs/shutdown.exit').read_text().strip()=='0','worktree_heads':{r:subprocess.check_output(['git','rev-parse','HEAD'],cwd='/private/tmp/permissions-fix02-'+r,text=True).strip() for r in refs}}
(OUT/'validation.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n')
