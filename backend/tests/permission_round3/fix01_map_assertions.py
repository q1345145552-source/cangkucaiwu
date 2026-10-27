"""Inventory original assertions and map exact current source + observed execution, never infer coverage from test names."""
import ast,json,re,subprocess,sys,difflib
from fix01_assertion_overrides import OVERRIDES
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'docs/permissions-r03-fix01-20261028'
trace=json.loads(Path(sys.argv[1]).read_text())['tests']
prior=json.loads((ROOT/'docs/permissions-round3-20261028/regression-comparison.json').read_text())
rows=[r for r in prior['rows'] if r['classification']=='第三轮授权变化使旧流程断言不再成立']
assert len(rows)==124,len(rows)
cache={}
def functions(source):return {n.name:n for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
def assertions(source,node):
 return [{'line':n.lineno,'text':ast.get_source_segment(source,n),'ast':ast.dump(n.test,include_attributes=False)} for n in ast.walk(node) if isinstance(n,ast.Assert)]
def normalize(s):
 for var in ['revoked','revoke']:s=s.replace(var+'.json()',var)
 return ast.dump(ast.parse(s),include_attributes=False)
result=[]
for row in rows:
 module,test=row['test'].split('::');file=module.split('.')[-1]+'.py';name=test.split('[')[0]
 path='backend/tests/'+file
 if file not in cache:
  old=subprocess.check_output(['git','show','e51b636:'+path],cwd=ROOT,text=True);new=(ROOT/path).read_text()
  cache[file]=(old,new,functions(old),functions(new))
 old,new,oldfunc,newfunc=cache[file]
 nodeid='tests/'+file+'::'+test
 actualid=nodeid
 if name=='test_disburse_reverse_reissue_and_reports':actualid='tests/'+file+'::'+name+'[3]'
 if name=='test_old_disbursement_role_restrictions_preserved' and test.endswith('[3]'):actualid='tests/'+file+'::test_supervisor_with_only_payroll_grant_and_cross_warehouse_rejected'
 if actualid not in trace and '[values8-' in actualid:
  actualid=next(k for k in trace if k.startswith(actualid.split('[values8-')[0]+'[values8-'))
 observed=trace.get(actualid,{})
 current_name=actualid.split('::')[-1].split('[')[0]
 candidates=assertions(new,newfunc[current_name]) if current_name in newfunc else []
 # The traceback records the call-site that failed in the original outer test/run.
 frames=[int(n) for f,n in re.findall(r'tests/(test_[^:]+):(\d+): in (?:run|'+re.escape(name)+r')',row['current']['trace']) if f==file]
 cutoff=max(frames) if frames else oldfunc[name].lineno
 mapping=[]
 for a in sorted(assertions(old,oldfunc[name]),key=lambda a:a['line']):
  matches=[b for b in candidates if b['ast']==a['ast']]
  relation='exact assertion expression'
  if not matches:
   matches=[b for b in candidates if normalize(b['text'])==normalize(a['text'])]
   relation='historical fixture dictionary replaces HTTP response wrapper'
  if not matches:
   # A changed assertion is explicitly displayed for review, never called equivalent based on similarity.
   ranked=sorted(candidates,key=lambda b:difflib.SequenceMatcher(None,a['ast'],b['ast']).ratio(),reverse=True)
   matches=ranked[:1] if ranked and difflib.SequenceMatcher(None,a['ast'],ranked[0]['ast']).ratio()>.55 else []
   relation='changed assertion; see old/new expressions and policy rationale'
  for b in matches:b['file']=file
  override=OVERRIDES.get((file,a['line']))
  if name=='test_old_disbursement_role_restrictions_preserved' and test.endswith('[3]'):
   override=['disburse(c, aid, uid=3)).status_code == 200'] if a['line']==276 else ['sources.status_code == 200'] if a['line']==277 else ['@money_state:NEVER']
   if a['line']==278:
    # Same balances are verified on the complete cash salary scenario; do not map to an unrelated denial.
    target='tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke'
    observed=trace[target];actualid=target
    candidates=assertions(new,newfunc['test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke'])
    override=['await balances(c) == before_balances']
  if override:
   matches=[];relation='explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md'
   for selector in override:
    pool=candidates;target_file=file
    if selector.startswith('@'):
     helper,selector=selector[1:].split(':',1);target_file='round3_flow_support.py'
     helper_source=(ROOT/'backend/tests'/target_file).read_text();pool=assertions(helper_source,functions(helper_source)[helper])
    selected=[b for b in pool if selector in b['text']]
    assert selected,(file,a['line'],selector)
    for b in selected:matches.append({**b,'file':target_file})
  mapped=[]
  for b in matches:
   key=b.get('file',file)+':'+str(b['line']);reached=key in observed.get('reached_assertions',{});failed=key in observed.get('failed_assertion_lines',{})
   mapped.append({'test':actualid,'file':b.get('file',file),'line':b['line'],'assertion':b['text'],'reached':reached,'line_failed':failed,'failure':observed.get('failed_assertion_lines',{}).get(key),'test_outcome':observed.get('outcome')})
  siblings=[]
  if mapped and not any(x['reached'] for x in mapped):
   for candidate_id,other in trace.items():
    if candidate_id.split('[')[0]!=actualid.split('[')[0]:continue
    for x in mapped:
     key=x['file']+':'+str(x['line'])
     if key in other.get('reached_assertions',{}):siblings.append({'test':candidate_id,'file':x['file'],'line':x['line'],'outcome':other.get('outcome'),'line_failed':key in other.get('failed_assertion_lines',{})})
  mapping.append({'sibling_parameter_execution':siblings,'old_line':a['line'],'old_assertion':a['text'],'position_relative_to_original_failure':'at_or_after_failed_call' if a['line']>=cutoff else 'before_failed_call_or_branch_dependent','mapping_kind':relation if mapped else 'no direct current assertion; requires explicit rationale','current':mapped})
 result.append({'old_test':row['test'],'old_first_failure':row['current'],'old_failed_call_line':cutoff,'current_test':actualid,'current_outcome':observed.get('outcome'),'assertions':mapping,'all_current_reached_assertions':observed.get('reached_assertions',{}),'current_failed_assertion_lines':observed.get('failed_assertion_lines',{})})
(OUT/'assertion-map.json').write_text(json.dumps({'original_obscured_tests':len(rows),'method':'Source AST plus actual pytest tracing; reaching a line is not proof that every short-circuit operand ran. Changed expressions explicitly not assumed equivalent. Historical monetary failures remain failures.','tests':result},ensure_ascii=False,indent=2))
lines=['# 124项旧前置失败：逐断言执行映射','', '每项列出原断言全文、当前测试与行号、是否实际到达及失败。`changed`须结合变更说明；不凭相似文本声称等价。原失败调用点之后的语句列为曾被遮挡，条件分支是否应运行另见当前实际跟踪。完整helper检查见原始assertions-final.json。','']
for i,r in enumerate(result,1):
 lines+=['## %03d %s'%(i,r['old_test']),'','当前 `%s`：**%s**；原失败调用行 %s。'%(r['current_test'],r['current_outcome'],r['old_failed_call_line']),'','|原行及断言|当前行/实际执行|映射说明|','|---|---|---|']
 for a in r['assertions']:
  text=a['old_assertion'].replace('|','\\|').replace('\n',' ')
  new='; '.join('%s @ %s:%s %s%s'%(x['test'],x['file'],x['line'],'已到达' if x['reached'] else '未到达',' / 行失败' if x['line_failed'] else '') for x in a['current']) or '无直接断言'
  if a['sibling_parameter_execution']:new+='；对应分支已在 '+', '.join(x['test']+' @ '+str(x['line']) for x in a['sibling_parameter_execution'])+' 执行'
  lines+=['|%s `%s`|%s|%s|'%(a['old_line'],text,new,a['mapping_kind'])]
 lines+=['']
(OUT/'ASSERTION-MAP.md').write_text('\n'.join(lines))
print('mapped tests',len(result),'missing current tests',[r['current_test'] for r in result if r['current_outcome'] is None])
