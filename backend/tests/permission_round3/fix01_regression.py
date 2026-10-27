"""Reproducible real regression command and unmodified output/exit capture."""
import json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
ENV=Path('/private/tmp/permissions-r03-fix01-env');OUT=ENV/'logs'
label=sys.argv[1]
assert label.replace('-','').isalnum()
files=['test_procurement_controls_round9.py','test_disabled_financial_reversals.py','test_payroll_labor_boundary.py','test_payroll_expense.py','test_payroll_cash_advance.py','test_reimbursement_payments.py','test_employee_advance_funding.py','test_employee_advance_limit.py','test_employee_advance_void.py','test_cash_advance_repayments.py','test_cash_advance_documents.py','test_advance_payroll_approval_audit.py','test_round18_advance_review.py','test_advance_manager_recipients.py']
url='postgresql+asyncpg://round3@127.0.0.1:65379/r3regression'
env={**os.environ,'DATABASE_URL':url,'INCOMING_TEST_DATABASE_URL':url,'SECRET_KEY':'synthetic-r03-fix01','PYTHONPATH':str(ROOT/'backend'),'PGLITE_NODE':'/Users/xiongliu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node','NODE_PATH':'/private/tmp/import-integration-pglite/node_modules','ASSERTION_TRACE_OUT':str(OUT/f'assertions-{label}.json')}
cmd=[sys.executable,'-m','pytest','-q','-s','--tb=short','-p','tests.permission_round3.assertion_trace',*['tests/'+p for p in files],'--junitxml='+str(OUT/f'regression-{label}.xml')]
(OUT/f'regression-{label}.command.json').write_text(json.dumps({'command':cmd,'cwd':str(ROOT/'backend'),'synthetic_database':url,'environment_keys':list(env)},indent=2))
with (OUT/f'regression-{label}.log').open('w') as log:
    result=subprocess.run(cmd,cwd=ROOT/'backend',env=env,stdout=log,stderr=subprocess.STDOUT)
(OUT/f'regression-{label}.exit').write_text(str(result.returncode))
print(result.returncode)
sys.exit(result.returncode)
