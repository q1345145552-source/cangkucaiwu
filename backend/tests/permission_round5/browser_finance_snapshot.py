from fixtures import *
async def main():
 engine=create_async_engine(URL);factory=async_sessionmaker(engine,expire_on_commit=False)
 out=ROOT/'docs/permissions-round5-20261028'/os.environ.get('ROUND5_FINANCE_RUN','finance-02');out.mkdir(exist_ok=True);phase=sys.argv[1];assert phase in ('before','after')
 data=await snapshot(factory);(out/f'browser-finance-{phase}.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
 if phase=='after':
  before=json.loads((out/'browser-finance-before.json').read_text());diff={k:{'before':before[k],'after':data[k]} for k in data if before[k]!=data[k]}
  (out/'browser-finance-diff.json').write_text(json.dumps(diff,ensure_ascii=False,indent=2))
  assert set(diff)<= {'payroll_records','data_change_history','audit_logs'},list(diff)
  assert len(data['payroll_records'])>len(before['payroll_records'])
  assert all(not r['disbursed'] and r['status']=='pending' for r in data['payroll_records'] if r['id'] not in {x['id'] for x in before['payroll_records']})
 print(phase,'PASS');await engine.dispose()
asyncio.run(main())
