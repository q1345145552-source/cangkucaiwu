"""Actual registered routes and nested guards, without connecting to a database."""
import json, inspect
from fixtures import app, OUT
from fastapi.routing import APIRoute
modules={'income_expense','incoming','reconciliation','salary_template','deduction_template','employee_deduction','exchange_rates','employees','attendance','clock_in','overtime','expense_fund','reimbursement','employee_advance','payroll','config_api','suppliers','expense_approval','payment_accounts'}
def deps(d):
 return [{'name':getattr(x.call,'__qualname__',str(x.call)), 'module':getattr(x.call,'__module__',''), 'nested':deps(x)} for x in d.dependencies]
rows=[]
for r in app.routes:
 if not isinstance(r,APIRoute):continue
 mod=r.endpoint.__module__.rsplit('.',1)[-1]
 if mod not in modules:continue
 rows.append({'module':mod,'method':sorted(r.methods),'path':r.path,'handler':r.endpoint.__name__,'source':inspect.getsourcefile(r.endpoint).split('/backend/')[-1], 'line':inspect.getsourcelines(r.endpoint)[1], 'guards':deps(r.dependant), 'query':[x.name for x in r.dependant.query_params], 'body':[{'name':x.name,'required':x.required,'schema':x.type_.model_json_schema() if hasattr(x.type_,'model_json_schema') else str(x.type_)} for x in r.dependant.body_params]})
(OUT/'registered-routes.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2));print(len(rows))
