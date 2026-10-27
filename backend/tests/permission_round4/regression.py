"""Real pytest runner; original assertions and failure exit codes retained."""
import ast,json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=Path('/private/tmp/permissions-round4-env/logs')
label=sys.argv[1]
baseline = len(sys.argv) > 2 and sys.argv[2] == 'baseline'
if baseline: ROOT=Path('/private/tmp/permissions-round4-baseline')
if label=='prior':
 source=ast.parse((ROOT/'backend/tests/permission_round3/fix01_regression.py').read_text())
 files=next(ast.literal_eval(n.value) for n in source.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='files' for t in n.targets))
else:
 assert label=='related'
 files=[p.name for p in (ROOT/'backend/tests').glob('test_*.py') if any(k in p.name for k in ('employee_self','attendance','leave','makeup','overtime','salary_template','deduction_template','income','incoming_operations','reconciliation','manual_wallet','employee_identity','employee_nationality','employee_limit'))]
if baseline: label += '-baseline'
base_label = label
sequence = 1
while (OUT/f'regression-{label}.log').exists():
 label = f'{base_label}-{sequence:02d}';sequence += 1
url='postgresql+asyncpg://round4@127.0.0.1:65389/regression'
env={**os.environ,'DATABASE_URL':url,'INCOMING_TEST_DATABASE_URL':url,'SECRET_KEY':'synthetic-r04-local-only-signing-key','PYTHONPATH':str(ROOT/'backend'),'PGLITE_NODE':'/Users/xiongliu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node','NODE_PATH':'/private/tmp/import-integration-pglite/node_modules'}
cmd=[sys.executable,'-m','pytest','-q','--tb=short',*['tests/'+p for p in sorted(files)],'--junitxml='+str(OUT/f'regression-{label}.xml')]
(OUT/f'regression-{label}.command.json').write_text(json.dumps({'command':cmd,'cwd':str(ROOT/'backend'),'database':url},indent=2))
with (OUT/f'regression-{label}.log').open('w') as log: result=subprocess.run(cmd,cwd=ROOT/'backend',env=env,stdout=log,stderr=subprocess.STDOUT)
(OUT/f'regression-{label}.exit').write_text(str(result.returncode));print(result.returncode);sys.exit(result.returncode)
