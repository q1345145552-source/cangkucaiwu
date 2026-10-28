"""Unmodified pytest suites on isolated local databases; current and exact baseline."""
import ast,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'docs/permissions-round6-20261028/raw-logs'
label=sys.argv[1];baseline=len(sys.argv)>2 and sys.argv[2]=='baseline';SOURCE=Path('/private/tmp/permissions-round5-20261028') if baseline else Path(os.environ.get('ROUND6_REGRESSION_SOURCE', str(ROOT)))
assert not (SOURCE/'backend/.env').exists() and not (SOURCE/'.env').exists()
if label=='prior':
 tree=ast.parse((SOURCE/'backend/tests/permission_round3/fix01_regression.py').read_text());files=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='files' for t in n.targets))
elif label=='reads':files=['test_dashboard_month.py','test_dashboard_procurement_payments.py','test_report_preview_scope.py','test_report_internal_transfers.py','test_operating_report.py','test_procurement_controls_round9.py','test_modification_log_permissions.py']
else:
 assert label=='related';files=[p.name for p in (SOURCE/'backend/tests').glob('test_*.py') if any(k in p.name for k in ('employee_self','attendance','leave','makeup','overtime','salary_template','deduction_template','income','incoming_operations','reconciliation','manual_wallet','employee_identity','employee_nationality','employee_limit'))]
assert all((SOURCE/'backend/tests'/p).exists() for p in files),files
name='pytest-'+label+('-baseline' if baseline else '-current')+('-'+os.environ['ROUND6_REGRESSION_RUN'] if os.environ.get('ROUND6_REGRESSION_RUN') else '');assert not (OUT/(name+'.log')).exists()
url='postgresql+asyncpg://round6@127.0.0.1:65509/'+('r6baseline' if baseline else 'r6regression')
env={**os.environ,'DATABASE_URL':url,'INCOMING_TEST_DATABASE_URL':url,'SECRET_KEY':'synthetic-round6-local-only-signing-key','PYTHONPATH':str(SOURCE/'backend'),'PGLITE_NODE':'/Users/xiongliu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node','NODE_PATH':'/private/tmp/import-integration-pglite/node_modules'}
cmd=[sys.executable,'-m','pytest','-q','--tb=short',*['tests/'+p for p in sorted(files)],'--junitxml='+str(OUT/(name+'.xml'))]
(OUT/(name+'.command.json')).write_text(json.dumps({'command':cmd,'cwd':str(SOURCE/'backend'),'database':url,'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip()},indent=2))
with (OUT/(name+'.log')).open('w') as log:r=subprocess.run(cmd,cwd=SOURCE/'backend',env=env,stdout=log,stderr=subprocess.STDOUT)
(OUT/(name+'.exit')).write_text(str(r.returncode));print(name,r.returncode);sys.exit(r.returncode)
