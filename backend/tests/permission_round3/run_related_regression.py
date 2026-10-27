import os,sys,subprocess,json
from pathlib import Path
label=sys.argv[1];root=Path('/private/tmp/permissions-round3-'+('baseline' if label=='baseline' else '20261028'))
files=['test_procurement_controls_round9.py','test_disabled_financial_reversals.py','test_payroll_labor_boundary.py','test_payroll_expense.py','test_payroll_cash_advance.py','test_reimbursement_payments.py','test_employee_advance_funding.py','test_employee_advance_limit.py','test_employee_advance_void.py','test_cash_advance_repayments.py','test_cash_advance_documents.py','test_advance_payroll_approval_audit.py','test_round18_advance_review.py','test_advance_manager_recipients.py']
url='postgresql+asyncpg://round3@127.0.0.1:65369/'+('r3baseline' if label=='baseline' else 'r3regression')
env={**os.environ,'DATABASE_URL':url,'INCOMING_TEST_DATABASE_URL':url,'SECRET_KEY':'synthetic-round3-regression-key','PYTHONPATH':str(root/'backend'),'PGLITE_NODE':'/Users/xiongliu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node','NODE_PATH':'/private/tmp/import-integration-pglite/node_modules'}
cmd=[sys.executable,'-m','pytest','-q','--tb=short',*[str(root/'backend/tests'/p) for p in files],'--junitxml='+str(Path.cwd()/'logs'/f'regression-{label}-02.xml')]
Path('logs/regression-'+label+'-02'+'.command.json').write_text(json.dumps({'command':cmd,'cwd':str(root/'backend'),'database':url},indent=2))
with open('logs/regression-'+label+'-02'+'.log','w') as out:r=subprocess.run(cmd,cwd=root/'backend',env=env,stdout=out,stderr=subprocess.STDOUT)
Path('logs/regression-'+label+'-02'+'.exit').write_text(str(r.returncode));print(label,r.returncode)
