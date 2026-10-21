// Execute the actual ReportsPage with controlled completion order, not a replica of its state logic.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript'),React=require('react');
const walk=x=>!x||typeof x!=='object'?[]:Array.isArray(x)?x.flatMap(walk):[x,...walk(x.props?.children)];
const text=x=>x==null||typeof x==='boolean'?'':typeof x!=='object'?String(x):Array.isArray(x)?x.map(text).join(''):text(x.props?.children);
const tick=()=>new Promise(r=>setTimeout(r,0));
function compile(file,imports,extra={}){const m={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src',file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module:m,exports:m.exports,require:n=>imports[n]||require(n),console,URLSearchParams,Intl,...extra});return m.exports;}
const money=compile('lib/currency.ts',{});
function harness(){
 const states=[],refs=[],deps=[],cleanups=[],effects=[],listeners={},calls=[],held=[],exports=[],toasts=[];
 let si=0,ri=0,ei=0,warehouse='1',hold=null,fail=false,exportHold=null,exportRelease;
 const react={...React,useState(v){let i=si++;if(!(i in states))states[i]=typeof v==='function'?v():v;return[states[i],v=>states[i]=typeof v==='function'?v(states[i]):v];},useRef(v){let i=ri++;return refs[i]||(refs[i]={current:v});},useEffect(fn,d){let i=ei++,key=JSON.stringify(d);if(key!==deps[i]){deps[i]=key;effects.push(()=>{cleanups[i]?.();cleanups[i]=fn();});}}};
 const window={location:{search:''},history:{replaceState(){}},addEventListener(n,fn){listeners[n]=fn;},removeEventListener(n){delete listeners[n];}};
 const body={appendChild(){},removeChild(){}};
 const document={body,createElement:()=>({click(){exports.push({clicked:true});}})};
 function amounts(w){return w==='all'?{income_by_currency:{THB:300,CNY:120},expense_by_currency:{THB:60,CNY:12},net_by_currency:{THB:240,CNY:108}}:w==='1'?{income_by_currency:{THB:100,CNY:50},expense_by_currency:{THB:20,CNY:5},net_by_currency:{THB:80,CNY:45}}:{income_by_currency:{THB:200,CNY:70},expense_by_currency:{THB:40,CNY:7},net_by_currency:{THB:160,CNY:63}};}
 const api={async get(route){const w=warehouse;calls.push({route,warehouse:w});if(hold?.warehouse===w&&route.startsWith(hold.kind)){await new Promise(resolve=>held.push({w,route,resolve}));}if(fail)throw Error('isolated request failed');const a=amounts(w);if(route.startsWith('/reports/reconciliation-diff'))return{total_diff_by_currency:{THB:3,CNY:1,UNKNOWN:9},total_diff:null,diff_count:1,data:[{'月份':'2026-10','状态':'未匹配','差额':9,'币种':'UNKNOWN','处理说明':'旧记录没有来源币种'}]};return route.startsWith('/reports/previews')?{previews:{'income-expense':{...a,preview_by_currency:a.net_by_currency},'recharge-summary':{preview_by_currency:a.income_by_currency},'expense-fund':{preview_by_currency:{THB:60}},credit:{preview_by_currency:{CNY:11}}}}:{...a,total_income_by_currency:a.income_by_currency,total_expense_by_currency:a.expense_by_currency,data:[],total_debt_by_currency:{THB:50,CNY:11}};}};
 const Child=()=>null,Warehouse=()=>null;
 const imports={react,'@/lib/api':{api,getToken:()=> 'synthetic',getActiveWarehouseId:()=>warehouse},'@/lib/currency':money,'@/lib/retiredEntries':{operatingEntriesEnabled:false},'@/components/OperatingReport':{__esModule:true,default:Child},'@/components/WarehouseSummary':{__esModule:true,default:Warehouse},'@/components/InternalTransferSummary':{__esModule:true,default:()=>null},'@/components/ui/Toast':{useToast:()=>({toast:(...args)=>toasts.push(args)})},'next/navigation':{useRouter:()=>({push(){}})}};
 const FixedDate=class extends Date{constructor(...args){super(...(args.length?args:['2026-10-20T23:30:00Z']));}};
 const page=compile('app/(dashboard)/reports/page.tsx',imports,{window,document,Date:FixedDate,URL:{createObjectURL:()=> 'blob:test',revokeObjectURL(){}},fetch:async(url,options)=>{exports.push({url,headers:options.headers});if(exportHold)await new Promise(r=>exportRelease=r);return{ok:true,blob:async()=>({})};},process:{env:{}}}).default;
 return{calls,held,exports,toasts,warehouse(w){warehouse=w;listeners['warehouse-changed']();},auth(){listeners['auth-user-refreshed']();},hold(w,kind='/reports/previews'){hold={warehouse:w,kind};},unhold(){hold=null;},fail(v){fail=v;},holdExport(){exportHold=true;},releaseExport(){exportHold=false;exportRelease();},Child,async render(){await tick();for(let n=0;n<15;n++){si=ri=ei=0;let t=page();if(!effects.length)return t;effects.splice(0).forEach(f=>f());await tick();}throw Error('unsettled');}};
}
function card(t,key){const n=walk(t).find(x=>x.type==='button'&&x.key===key);assert(n,'Missing card '+key);return n;}
function button(t,label){const n=walk(t).find(x=>x.type==='button'&&text(x).trim()===label);assert(n,'Missing button '+label);return n;}
(async()=>{
 const h=harness();let t=await h.render();assert(text(card(t,'income-expense')).includes('收入 ฿100 + ¥50'));assert(text(card(t,'income-expense')).includes('支出 ฿20 + ¥5'));assert(!walk(t).some(n=>n.type===h.Child));assert(h.calls.every(c=>c.route.includes('start_date=2026-10-01')&&c.route.includes('end_date=2026-10-21')));
 await card(t,'income-expense').props.onClick();t=await h.render();assert(text(t).includes('฿100 + ¥50'));
 h.warehouse('2');t=await h.render();assert(text(card(t,'income-expense')).includes('收入 ฿200 + ¥70'));assert(text(card(t,'income-expense')).includes('支出 ฿40 + ¥7'));
 h.warehouse('1');t=await h.render();assert(text(card(t,'income-expense')).includes('收入 ฿100 + ¥50'));
 h.warehouse('all');t=await h.render();assert(text(card(t,'income-expense')).includes('收入 ฿300 + ¥120'));assert(text(card(t,'income-expense')).includes('支出 ฿60 + ¥12'));
 // Hold an old warehouse request, switch again, then complete the older response last.
 h.hold('1');h.warehouse('1');t=await h.render();assert(text(card(t,'income-expense')).includes('加载中'));assert(!text(card(t,'income-expense')).includes('฿300'));assert(h.held.length===1);
 h.unhold();h.warehouse('2');t=await h.render();h.held.shift().resolve();t=await h.render();assert(text(card(t,'income-expense')).includes('收入 ฿200'));assert(!text(card(t,'income-expense')).includes('收入 ฿100'));
 // The detail request has its own ordering guard.
 h.hold('1','/reports/income-expense');h.warehouse('1');t=await h.render();assert(h.held.length===1);h.unhold();h.warehouse('2');t=await h.render();h.held.shift().resolve();t=await h.render();assert(text(t).includes('฿200 + ¥70'));assert(!text(t).includes('฿100 + ¥50'));
 h.fail(true);h.warehouse('1');t=await h.render();assert(text(t).includes('报表预览加载失败'));assert(text(t).includes('报表加载失败'));assert(!text(card(t,'income-expense')).includes('฿200'));assert(!text(card(t,'income-expense')).includes('0'));
 h.fail(false);await button(t,'重试预览').props.onClick();await button(t,'重试报表').props.onClick();t=await h.render();assert(text(card(t,'income-expense')).includes('收入 ฿100'));assert(!text(t).includes('加载失败'));
 const start=walk(t).find(n=>n.props?.['aria-label']==='开始日期');start.props.onChange({target:{value:'2026-09-01'}});t=await h.render();assert(h.calls.slice(-2).every(c=>c.route.includes('start_date=2026-09-01')));
 await button(t,'导出 Excel').props.onClick();t=await h.render();let request=h.exports.find(x=>x.url);assert.equal(request.headers['X-Warehouse-ID'],'1');assert(request.url.includes('start_date=2026-09-01'));assert(h.exports.some(x=>x.clicked));
 h.holdExport();const exporting=button(t,'导出 Excel').props.onClick();h.warehouse('2');t=await h.render();const clicks=h.exports.filter(x=>x.clicked).length;h.releaseExport();await exporting;assert.equal(h.exports.filter(x=>x.clicked).length,clicks);assert(h.toasts.some(x=>String(x).includes('筛选已变化')));
 h.fail(true);h.auth();t=await h.render();assert(text(t).includes('报表预览加载失败'));assert(!text(card(t,'income-expense')).includes('฿200'));
 h.fail(false);h.auth();t=await h.render();await card(t,'credit').props.onClick();t=await h.render();assert(text(t).includes('总欠款'));assert(text(t).includes('฿50 + ¥11'));
 await card(t,'reconciliation-diff').props.onClick();t=await h.render();assert(text(t).includes('฿3 + ¥1'));assert(text(t).includes('9（币种待核对）'));assert(!text(t).includes('฿9'));
 console.log('PASS: actual report page A100/20 -> B200/40 -> A100/20, all300/60, separate CNY, stale preview/detail ignored, old amounts cleared on failure/revoke, retry, Thai-calendar dates and matching/stale export headers');
})().catch(e=>{console.error(e);process.exitCode=1;});
