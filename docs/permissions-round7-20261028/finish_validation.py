"""Compare actual assertions and summarize completed immutable evidence."""
from pathlib import Path
import json,re,ast,hashlib,xml.etree.ElementTree as ET
OUT=Path(__file__).parent;RAW=OUT/'raw-logs';NAME='full-current-final06b'
def cases(path):
 out={}
 for t in ET.parse(path).iter('testcase'):
  f=t.find('failure');e=t.find('error');f=f if f is not None else e
  out[t.get('classname')+'::'+t.get('name')]={'status':'failed' if f is not None else 'skipped' if t.find('skipped') is not None else 'passed','message':f.get('message','') if f is not None else '', 'text':f.text if f is not None else ''}
 return out
current=cases(RAW/(NAME+'.xml'));baseline=cases(RAW/'cost-baseline-final06.xml')
normalize=lambda s:re.sub(r'0x[0-9a-f]+','0xADDRESS',s)
comparison=[]
for k,v in current.items():
 if v['status']!='failed':continue
 b=baseline.get(k)
 def assertions(x):
  if not x:return None
  try:return ast.literal_eval(x['message'].removeprefix('AssertionError: '))
  except (ValueError,SyntaxError):return [{'assertion':'direct','actual_failure':x['message']}]
 a=assertions(v);ba=assertions(b)
 # Preserve complete original strings; compare assertion ids and exact normalized failure content.
 equal=bool(b and b['status']=='failed' and normalize(repr(a))==normalize(repr(ba)))
 comparison.append({'test':k,'current_assertions':a,'baseline_assertions':ba,'same_actual_assertions_after_memory_address_normalization':equal,'current_message':v['message'],'baseline_message':b['message'] if b else None})
(OUT/'COST-ASSERTION-COMPARISON.json').write_text(json.dumps(comparison,ensure_ascii=False,indent=2))
from collections import Counter
freeze=json.loads((RAW/(NAME+'.freeze-check.json')).read_text());assert freeze['matched'];assert freeze['collected']==freeze['executed']==freeze['unique_executed']==len(current)
browser=json.loads((OUT/'browser-final05/results.json').read_text())['results'];assert len(browser)==18 and all(x['passed'] for x in browser)
summary={'suite':NAME,'full':dict(Counter(x['status'] for x in current.values())),'total':len(current),'skipped':sum(x['status']=='skipped' for x in current.values()),'exit':int((RAW/(NAME+'.exit')).read_text()),'freeze':freeze,'exact_baseline_full':{'total':2918,'passed':2149,'failed':769,'skipped':0,'exit':1},'adapted_cost_baseline':{'total':len(baseline),**dict(Counter(x['status'] for x in baseline.values())),'exit':1},'cost_actual_assertion_exact_matches':sum(x['same_actual_assertions_after_memory_address_normalization'] for x in comparison),'browser_scenarios':18,'tsc_exit':int((RAW/'tsc-final05.exit').read_text()),'build_exit':int((RAW/'build-final05.exit').read_text()),'runtime_correspondence':'RUNTIME-EVIDENCE-MATCH.json'}
(OUT/'FINAL-VALIDATION.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary));print('Differences requiring review:',[x['test'] for x in comparison if not x['same_actual_assertions_after_memory_address_normalization']])
