from pathlib import Path
import subprocess,json,hashlib,ast
root=Path('/private/tmp/permissions-round2-20261028');out=root/'docs/permissions-round2-20261028';env=Path('/private/tmp/permissions-round2-env');base='bc903a55c60c865f8eb95a4e6374ef5325ab4685'
def git(*args):return subprocess.check_output(['git',*args],cwd=root,text=True).strip()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
changed=git('diff','--name-only',base).splitlines()
protected=[p for p in changed if p.startswith(('backend/app/models/','backend/app/api/v1/inventory','backend/app/services/inventory','backend/app/services/cost_identity','backend/app/services/account_balances','backend/app/services/fund_disbursement','backend/app/api/v1/payroll.py','backend/app/api/v1/employee_advance.py','backend/scripts/seed','docs/permissions-audit-round1-20261028/','backend/tests/permission_audit_round1/'))]
assert not protected,protected
runtime_mismatches=[]
for p in root.joinpath('frontend/src').rglob('*'):
 if p.is_file() and p.suffix in ('.ts','.tsx','.css','.js'):
  other=env/'frontend'/p.relative_to(root/'frontend')
  if not other.exists() or sha(p)!=sha(other):runtime_mismatches.append(str(p.relative_to(root)))
for name in ('next.config.js','postcss.config.js','tailwind.config.js','tsconfig.json','package.json','package-lock.json'):
 if sha(root/'frontend'/name)!=sha(env/'frontend'/name):runtime_mismatches.append(name)
assert not runtime_mismatches,runtime_mismatches
status=json.loads((out/'target-status.json').read_text());browser=json.loads((out/'browser-results.json').read_text())
manifest={'worktree':str(root),'branch':git('branch','--show-current'),'baseline_head':base,'business_baseline':'854e389c30aa9e62169d746a13f499c7815591ec','final_commit':'See final response or git log -1 --format=%H; no self-referential hash stored in this commit','environment':str(env),'database':'Disposable PostgreSQL 16.2, localhost 127.0.0.1:65339, database round2; no production connection','versions':{'python':'3.12.14','node':'24.19.0','next':'14.2.35','postgres':'16.2'},'identity':{'1':'warehouse_admin, authorized warehouse1 and later synthetic warehouse3','2':'supervisor, legacy all Chinese labels + menu keys','3':'staff A, legacy all grants','4':'staff B, legacy all grants','5':'warehouse_labor','6':'supervisor without extras','7':'disabled staff','8':'warehouse2 admin','90':'staff alias linked to same employee as staff A','91':'staff without extras','92':'synthetic labor for authorized linked-account disable'},'auth':'Real JWT/current user and DB, no always-allow auth replacements; all credentials/records synthetic','target':status,'ui':{'cases':len(browser['results']),'errors':browser['errors'],'failure':browser.get('failure'),'network':'Browser permits only localhost, blocks other hosts','viewport':'390x960 supervisor;1440x960 administrator/finance','note':'Runtime CSS configuration corrected; clean build and styled screenshot verified. Earlier failed browser/setup logs retained.'},'frontend_runtime_source_hashes_match':not runtime_mismatches,'validation_exit_codes':{n:int((env/'logs'/f'{n}.exit').read_text()) for n in ('target-final','regression-final','core-baseline','fund-baseline','reimbursement-baseline','fund-controls-final','tsc-final','tsc-commit','build-clean-final','build-commit','python-compile','browser-clean-final','shutdown')},'commands':[
'LC_ALL=C initdb -D /private/tmp/permissions-round2-env/pgdata -A trust -U round2',
'pg_ctl -D /private/tmp/permissions-round2-env/pgdata -o "-h 127.0.0.1 -p 65339 -k /private/tmp/permissions-round2-env" start; createdb -h 127.0.0.1 -p 65339 -U round2 round2',
'From isolated environment (no .env): ROUND2_DATABASE_URL=postgresql+asyncpg://round2@127.0.0.1:65339/round2 /tmp/supplier01-py312/bin/python <worktree>/backend/tests/permission_round2/run_acceptance.py',
'Explicit synthetic DATABASE_URL/SECRET_KEY/PYTHONPATH and INCOMING_TEST_DATABASE_URL; python -m pytest test_round2_permissions.py test_round3_permissions.py test_config_center_access.py test_procurement_controls_round9.py test_disabled_financial_reversals.py test_fund_disbursement.py test_fund_item_controls.py test_fund_receipts.py test_reimbursement_payments.py --junitxml=logs/regression-final.xml (absolute paths under worktree/backend/tests)',
'Baseline uses original files under /private/tmp/permissions-audit-round1-20261028, with same isolated DB URL, split into core/fund/reimbursement batches; see raw logs/XML',
'Cached node_modules copied into isolated frontend; exact frontend sources/configs copied; node node_modules/typescript/bin/tsc --noEmit',
'Only derived isolated frontend/.next removed for clean build; NEXT_TELEMETRY_DISABLED=1 node node_modules/next/dist/bin/next build',
'python -m compileall -q <worktree>/backend/app',
'ROUND2_DATABASE_URL=<local> python <worktree>/backend/tests/permission_round2/browser_fixture.py; uvicorn app.main:app --host 127.0.0.1 --port 65340 --lifespan off (explicit synthetic environment)',
'next start -H 127.0.0.1 -p 65341; node browser_proxy.cjs (65342); node browser_acceptance.cjs',
'Kill only the isolated API/frontend/proxy PIDs; pg_ctl -D /private/tmp/permissions-round2-env/pgdata stop -m fast'
], 'source_hashes':{p:sha(root/p) for p in changed if p.startswith(('backend/app/','frontend/src/'))},'first_round_evidence_unchanged':True,'local_services_stopped':True}
(out/'validation-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
boundary={'baseline':base,'business_code_files_changed':[p for p in changed if p.startswith(('backend/app/','frontend/src/'))],'protected_paths_changed':protected,'models_or_migrations_changed':False,'first_round_original_evidence_changed':False,'production_access':False,'read_deploy_or_production_credentials':False,'push':False,'deployment':False,'ssh':False,'subagents_or_other_chat_dispatch':False,'automations_created':False,'inventory_valuation_modified':False,'account_balances_cost_identity_fund_disbursement_services_unchanged':True,'other_worktrees_modified':False,'diff_check_exit_code':subprocess.run(['git','diff','--check'],cwd=root,capture_output=True).returncode}
(out/'boundary-verification.json').write_text(json.dumps(boundary,ensure_ascii=False,indent=2)+'\n')
print('target',status,'browser',len(browser['results']),'protected changes',protected,'runtime mismatches',runtime_mismatches)
