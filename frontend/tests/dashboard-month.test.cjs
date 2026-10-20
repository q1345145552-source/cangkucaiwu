const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript'),React=require('react');
const wait=()=>new Promise(r=>setTimeout(r,0));
function compile(file,imports,extra='',globals={}){const m={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText+extra,{module:m,exports:m.exports,require:n=>imports[n]||require(n),console,...globals});return m.exports;}
const text=n=>n==null||typeof n==='boolean'?'':typeof n==='number'||typeof n==='string'?String(n):Array.isArray(n)?n.map(text).join(''):text(n.props?.children);
const walk=n=>!n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(walk):[n,...walk(n.props?.children)];
const expand=n=>!n||typeof n!=='object'?n:Array.isArray(n)?n.map(expand):typeof n.type==='function'?expand(n.type(n.props)):{...n,props:{...n.props,children:expand(n.props?.children)}};
const monthInput=tree=>walk(tree).find(n=>n.type==='input'&&n.props['aria-label']==='统计月份');
function response(month,warehouse){
 const amount=(value)=>[{currency:'THB',amount:value},{currency:'CNY',amount:value/10}];
 const inc=month==='2026-09'?1000:month==='2026-10'?700:0,exp=month==='2026-09'?200:month==='2026-10'?300:0,mul=warehouse==='2'?2:warehouse==='all'?3:1;
 const period={month,start_date:month+'-01',end_date:month+'-30',timezone:'Asia/Bangkok'};
 const trends={funds:{},income_expense:{},orders:{},expense_categories:{},procurement_suppliers:{}};
 for(const [cur,div] of [['THB',1],['CNY',10]]){trends.funds[cur]=[{date:month+'-15',incoming:inc*mul/div,other_income:0}];trends.income_expense[cur]=[{date:month+'-15',income:inc*mul/div,expense:exp*mul/div}];trends.orders[cur]=[];trends.expense_categories[cur]=[];trends.procurement_suppliers[cur]=[];}
 return{period,warehouses:[{id:Number(warehouse)||1,name:'仓'+warehouse}],trends,
  finance:{month:{income:amount(inc*mul),expense:amount(exp*mul),net:amount((inc-exp)*mul)},receivable_payable:{receivable:[],payable:[],overdue_payable:[]},balances:{payment_accounts:[],expense_funds:[]},procurement:{expense:[],price_anomaly_count:0,non_lowest_count:0},recharge_reconciliation:{recharge:[],incoming:[],unmatched_count:0}},
  people:{attendance:{expected:0,present:0,absent:0},efficiency:null,efficiency_by_warehouse:[],todos:{}},todos:[]};
}
function harness(){
 const state=[],refs=[],deps=[],cleanup=[],effects=[],events=new Map(),reads=[],held=[];let si=0,ri=0,ei=0,wh='1',holdMonth=null,fail=false;
 const react={...React,useState(v){const i=si++;if(!(i in state))state[i]=typeof v==='function'?v():v;return[state[i],x=>state[i]=typeof x==='function'?x(state[i]):x];},useRef(v){const i=ri++;return refs[i]||(refs[i]={current:v});},useEffect(fn,d){const i=ei++,key=JSON.stringify(d);if(deps[i]!==key){deps[i]=key;effects.push(()=>{cleanup[i]?.();cleanup[i]=fn();});}}};
 const window={addEventListener(name,fn){if(!events.has(name))events.set(name,new Set());events.get(name).add(fn);},removeEventListener(name,fn){events.get(name)?.delete(fn);}};
 const router={push(){}};const charts={LineChart:props=>React.createElement('figure',{'data-kind':'line',...props}),BarChart:props=>React.createElement('figure',{'data-kind':'bar',...props}),DonutChart:props=>React.createElement('figure',{'data-kind':'donut',...props})};
 const api={async get(route){reads.push({route,wh});const month=new URL(route,'http://test').searchParams.get('month'),scope=wh;if(month===holdMonth)await new Promise(resolve=>held.push(resolve));if(fail)throw Error('隔离请求失败');return response(month,scope);}};
 class FixedDate extends Date{constructor(...args){super(...(args.length?args:['2026-09-30T18:00:00Z']));}}
 const page=compile('../src/app/(dashboard)/dashboard/page.tsx',{react,'@/lib/api':{api,getToken:()=> 'synthetic'},'@/hooks/useAuth':{useAuth:()=>({user:{role:'warehouse_admin',display_name:'测试'}})},'next/navigation':{useRouter:()=>router},'@/components/TrendCharts':charts,'@/components/BossTodos':{__esModule:true,default:()=>null}},';module.exports.testContent=DashboardContent;module.exports.testBreakdown=PeriodBreakdown;',{window,URLSearchParams,Date:FixedDate,Intl});
 return{reads,held,page,react,setWarehouse(v){wh=v;},hold(v){holdMonth=v;},fail(v){fail=v;},emit(name){for(const fn of events.get(name)||[])fn();},async render(){await wait();for(let n=0;n<15;n++){si=ri=ei=0;const tree=page.testContent();if(!effects.length)return expand(tree);effects.splice(0).forEach(fn=>fn());await wait();}throw Error('Unsettled effects');}};
}
(async()=>{
 const h=harness();let tree=await h.render();assert.equal(monthInput(tree).props.value,'2026-10');assert(text(tree).includes('฿700'));assert(text(tree).includes('฿300'));assert(text(tree).includes('净收支'));assert(!text(tree).includes('盈亏'));
 assert(h.reads.every(r=>r.route.startsWith('/dashboard/cockpit?month=')));assert(!h.reads.some(r=>r.route.includes('/trends')));
 h.hold('2026-09');monthInput(tree).props.onChange({target:{value:'2026-09'}});tree=await h.render();assert(text(tree).includes('加载中'));assert(!text(tree).includes('฿700'));
 h.hold(null);monthInput(tree).props.onChange({target:{value:'2026-10'}});tree=await h.render();assert(text(tree).includes('฿700'));
 h.held.shift()();tree=await h.render();assert.equal(monthInput(tree).props.value,'2026-10');assert(!text(tree).includes('฿1,000'));
 monthInput(tree).props.onChange({target:{value:'2026-09'}});tree=await h.render();assert(text(tree).includes('฿1,000'));assert(text(tree).includes('฿800'));
 let lines=walk(tree).filter(n=>n.type==='figure'&&n.props['data-kind']==='line');assert.equal(lines[0].props.datasets[0].name,'其他实收');assert.equal(lines[0].props.datasets[1].name,'到账收入');assert.deepEqual(Array.from(lines[1].props.datasets[0].values),[1000]);assert.equal(lines[1].props.labels[0],'2026-09-15');
 h.setWarehouse('2');h.emit('warehouse-changed');tree=await h.render();assert(text(tree).includes('仓2'));assert(text(tree).includes('฿2,000'));assert(text(tree).includes('（即时）'));
 const cny=walk(tree).find(n=>n.type==='button'&&text(n)==='人民币');assert(cny);cny.props.onClick();tree=await h.render();lines=walk(tree).filter(n=>n.type==='figure'&&n.props['data-kind']==='line');assert.deepEqual(Array.from(lines[0].props.datasets[1].values),[200]);
 h.fail(true);h.emit('auth-user-refreshed');tree=await h.render();assert(text(tree).includes('隔离请求失败'));assert(!text(tree).includes('฿2,000'));assert(monthInput(tree));
 h.fail(false);walk(tree).find(n=>n.type==='button'&&text(n)==='重试').props.onClick();tree=await h.render();assert(text(tree).includes('฿2,000'));
 monthInput(tree).props.onChange({target:{value:'2028-01'}});tree=await h.render();assert(text(tree).includes('฿0'));
 const signed=expand(h.page.testBreakdown({items:[{name:'正常',amount:300},{name:'冲销',amount:-50}],currency:'THB'}));assert(text(signed).includes('含冲销'));assert(text(signed).includes('฿250'));assert(!walk(signed).some(n=>n.type==='figure'));
 const charts=compile('../src/components/TrendCharts.tsx',{react:{...React,useState:v=>[v,()=>{}]}});
 const negative=charts.LineChart({labels:['a','b'],datasets:[{name:'支出',color:'red',values:[-50,300]}],signed:true});assert(walk(negative).filter(n=>n.type==='circle').every(n=>n.props.cy>=14&&n.props.cy<=190));
 const cfg={labels:['a','b'],datasets:[{name:'正数',color:'red',values:[100,300]}]};
 assert.deepEqual(walk(charts.LineChart({...cfg,signed:true})).filter(n=>n.type==='circle').map(n=>n.props.cy),walk(charts.LineChart(cfg)).filter(n=>n.type==='circle').map(n=>n.props.cy));
 // The real parent layout must preserve dashboard state across a warehouse switch.
 let layoutState=[],cursor=0,route='/dashboard';
 const layout=compile('../src/components/layout/DashboardLayout.tsx',{react:{...React,useState:()=>[layoutState[cursor++],()=>{}],useEffect(){}},
  'next/navigation':{useRouter:()=>({push(){},replace(){}}),usePathname:()=>route},'next/link':{__esModule:true,default:()=>null},
  '@/hooks/useI18n':{useI18n:()=>({t:k=>k,locale:'zh',setLocale(){}})},'@/components/ui/BackToTop':{__esModule:true,default:()=>null},'@/lib/api':{api:{},getToken(){},getActiveWarehouseId(){},setActiveWarehouseId(){}}});
 function wrapperKey(warehouse,pathname){route=pathname;cursor=0;layoutState=[true,false,null,false,false,false,[],warehouse,false,{id:1,role:'warehouse_admin'},false,[]];
  const child=React.createElement('p',null,'month view'),tree=layout.default({children:child});return walk(tree).find(n=>n.props?.children===child).key;}
 assert.equal(wrapperKey(1,'/dashboard'),wrapperKey(2,'/dashboard'));
 assert.notEqual(wrapperKey(1,'/reports'),wrapperKey(2,'/reports'));
 console.log('PASS: actual dashboard defaults to Thai month across UTC boundary, one response feeds all monthly cards/charts, selector and warehouse changes clear stale values, delayed old month ignored, currencies remain separate, instant sections labeled, failures/retry/empty future and signed chart/breakdown behavior validated');
})().catch(error=>{console.error(error);process.exitCode=1;});
