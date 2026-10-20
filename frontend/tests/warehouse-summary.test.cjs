const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript'),React=require('react');
const text=x=>x==null||typeof x==='boolean'?'':typeof x==='string'||typeof x==='number'?String(x):Array.isArray(x)?x.map(text).join(''):text(x.props?.children);
const walk=x=>!x||typeof x!=='object'?[]:Array.isArray(x)?x.flatMap(walk):[x,...walk(x.props?.children)];
function compile(file,imports,globals={}){const m={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module:m,exports:m.exports,require:n=>imports[n]||require(n),console,...globals});return m.exports;}
const currency=compile('../src/lib/currency.ts',{}),wait=()=>new Promise(r=>setTimeout(r,0));
function harness(){
 const states=[],refs=[],deps=[],cleanups=[],effects=[],events=new Map(),reads=[],held=[];
 let si=0,ri=0,ei=0,warehouse='1',fail=false,hold=false,empty=false;
 const react={...React,useState(v){const i=si++;if(!(i in states))states[i]=typeof v==='function'?v():v;return[states[i],x=>states[i]=typeof x==='function'?x(states[i]):x];},useRef(v){const i=ri++;return refs[i]||(refs[i]={current:v});},useEffect(fn,d){const i=ei++,key=JSON.stringify(d);if(deps[i]!==key){deps[i]=key;effects.push(()=>{cleanups[i]?.();cleanups[i]=fn();});}}};
 const window={addEventListener(name,fn){if(!events.has(name))events.set(name,new Set());events.get(name).add(fn);},removeEventListener(name,fn){events.get(name)?.delete(fn);}};
 const api={async get(route){const scope=warehouse;reads.push({route,scope});const wasEmpty=empty;if(hold)await new Promise(resolve=>held.push(resolve));if(fail)throw Error('无此操作权限');
  const n=scope==='all'?300:scope==='1'?100:200,c=scope==='all'?2:1;
  const totals={income_by_currency:wasEmpty?{}:{THB:n,CNY:scope==='all'?120:50},expense_by_currency:wasEmpty?{}:{THB:n/5,CNY:5},net_by_currency:wasEmpty?{}:{THB:n*.8,CNY:45},income_count:wasEmpty?0:c,expense_count:wasEmpty?0:c};
  return{data:wasEmpty?[]:[{...totals,warehouse_id:Number(scope)||1,warehouse_name:'仓'+scope}],totals,basis:'公司钱包实际收付，内部转账不计收支'};}};
 const page=compile('../src/components/WarehouseSummary.tsx',{react,'@/lib/api':{api},'@/lib/currency':currency},{window,URLSearchParams});
 return{reads,held,emit(name){for(const fn of events.get(name)||[])fn();},setWarehouse(v){warehouse=v;},setHold(v){hold=v;},setFail(v){fail=v;},setEmpty(v){empty=v;},async render(props={startDate:'2026-10-01',endDate:'2026-10-31'}){await wait();for(let n=0;n<15;n++){si=ri=ei=0;const tree=page.default(props);if(!effects.length)return tree;effects.splice(0).forEach(fn=>fn());await wait();}throw Error('Unsettled effects');}};
}
(async()=>{
 const h=harness();let tree=await h.render();assert(text(tree).includes('仓1'));assert(text(tree).includes('฿100'));assert(text(tree).includes('¥50'));assert(h.reads[0].route.includes('start_date=2026-10-01'));
 h.setHold(true);h.emit('warehouse-changed');tree=await h.render();assert(text(tree).includes('加载中'));assert(!text(tree).includes('฿100'));assert.equal(h.held.length,1);
 h.setWarehouse('2');h.setHold(false);h.emit('warehouse-changed');tree=await h.render();assert(text(tree).includes('仓2'));assert(text(tree).includes('฿200'));
 h.held.shift()();tree=await h.render();assert(text(tree).includes('仓2'));assert(!text(tree).includes('仓1'));
 h.setWarehouse('all');h.emit('warehouse-changed');tree=await h.render();assert(text(tree).includes('฿300'));assert(text(tree).includes('¥120'));assert(!text(tree).includes('฿420'));
 h.setFail(true);h.emit('auth-user-refreshed');tree=await h.render();assert(text(tree).includes('仓库汇总加载失败：无此操作权限'));assert(!text(tree).includes('合计'));assert(!text(tree).includes('฿300'));
 h.setFail(false);const retry=walk(tree).find(n=>n.type==='button'&&text(n)==='重试');assert(retry);retry.props.onClick();tree=await h.render();assert(text(tree).includes('฿300'));
 h.setEmpty(true);tree=await h.render({startDate:'2026-09-01',endDate:'2026-09-30'});assert(text(tree).includes('暂无可查看的启用仓库'));assert(text(tree).includes('收入 0'));assert(h.reads.at(-1).route.includes('end_date=2026-09-30'));
 console.log('PASS: actual warehouse summary component renders separate currencies, clears old scope while switching, ignores delayed previous-warehouse data, sends date bounds, never renders errors as zero, handles permission revocation, retry and legitimate empty scopes');
})().catch(error=>{console.error(error);process.exitCode=1;});
