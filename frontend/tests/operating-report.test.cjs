const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),React=require('react');
const wait=()=>new Promise(r=>setTimeout(r,0));
const walk=n=>!n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(walk):[n,...walk(n.props?.children)];
const text=n=>n==null||typeof n==='boolean'?'':typeof n!=='object'?String(n):Array.isArray(n)?n.map(text).join(''):text(n.props?.children);
const find=(t,label)=>walk(t).find(n=>n.props?.['aria-label']===label),button=(t,label)=>walk(t).find(n=>n.type==='button'&&text(n).trim()===label);
function setup(file,makeImports,props={},initialSearch=""){
 const location={search:initialSearch},history={state:null,replaceState(s,t,url){location.search=url.includes("?")?"?"+url.split("?")[1]:"";}};
 const state=[],refs=[],deps=[],effects=[],clean=[],events={};let si=0,ri=0,ei=0;
 const react={...React,useState(v){const i=si++;if(!(i in state))state[i]=typeof v==='function'?v():v;return[state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];},useRef(v){const i=ri++;return refs[i]||(refs[i]={current:v});},useEffect(fn,d){const i=ei++,key=JSON.stringify(d);if(deps[i]!==key){deps[i]=key;effects.push(()=>{clean[i]?.();clean[i]=fn();});}}};
 const m={exports:{}},imports={react,...makeImports(events)};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module:m,exports:m.exports,require:n=>imports[n]||require(n),console,Date,Intl,Number,URLSearchParams,window:{location,history,addEventListener:(n,fn)=>events[n]=fn,removeEventListener:n=>delete events[n]}});
 return{events,props,location,async render(){await wait();for(let n=0;n<20;n++){si=ri=ei=0;const t=m.exports.default(props);if(!effects.length)return t;effects.splice(0).forEach(f=>f());await wait();}throw Error('unsettled effects');}};
}
function fixture(month,cid='',currency='',page=1){
 const cur=currency||'THB',value=month==='2026-09'?1000:0,receipt=month==='2026-10'?1000:0;
 return{customer_options:[{id:1,name:'客户A'}],cost_gaps:['缺少确认的成本归期规则'],cost_references:{data:cid?[]:[{source:'manual_expense',source_id:4,warehouse_id:1,reference_date:'2026-09-02',nominal_amount:400,currency:cur,status:'period_unverified',date_basis:'付款不能证明成本归期'}],total:cid?0:1,page:1,page_size:20},shipments:{data:value?[{source:'shipment',source_id:9,customer_id:1,customer_name:'客户A',warehouse_id:1,date:'2026-09-01',amount:1000,currency:cur,order_count:3}]:[],total:value?23:0,page:page,page_size:20},currencies:[{currency:cur,shipment_income:value,actual_receipts:receipt,receivable_asof:value,prepayment_asof:0,shipment_records:value?23:0,order_count:3,unknown_order_count_records:0,daily:[{date:`${month}-01`,shipment_income:value,actual_receipts:receipt}]}],wallet:cid?null:{income_by_currency:{[cur]:receipt},expense_by_currency:{[cur]:value?400:0},net_by_currency:{[cur]:receipt-(value?400:0)}},wallet_scope_note:cid?'客户成本未分摊':'钱包净收支不是经营利润',review_items:[{customer_id:1,source_id:7,amount:777,currency:cur,message:'历史欠款保留待核对'}],reference_basis:'参考日期不是成本归期'};
}
(async()=>{
 const calls=[],held=[];let fail=false;
 const h=setup('src/components/OperatingReport.tsx',()=>({'@/lib/api':{api:{async get(route){calls.push(route);const q=new URL(route,'http://test').searchParams,month=q.get('start_date').slice(0,7);if(q.get('end_date')==='2026-09-29')await new Promise(r=>held.push(r));if(fail)throw Error('隔离报表错误');return fixture(month,q.get('customer_id'),q.get('currency'),+(q.get('shipment_page')||1));}}}}),{startDate:'2026-09-01',endDate:'2026-09-30'});
 let t=await h.render();assert(text(t).includes('利润暂不可计算'));assert(!text(t).includes('经营利润：฿600'));assert(text(t).includes('归期待核对'));assert(text(t).includes('历史欠款保留待核对'));
 button(t,'手工支出 #4').props.onClick();t=await h.render();assert(text(find(t,'经营报表来源详情')).includes('仓库 #1'));assert(text(t).includes('付款不能证明成本归期'));
 const shipment=find(t,'经营发货明细');button(shipment,'下一页').props.onClick();t=await h.render();assert(calls.at(-1).includes('shipment_page=2'));
 find(t,'经营报表币种').props.onChange({target:{value:'CNY'}});t=await h.render();assert(text(t).includes('¥1,000.00'));assert(calls.at(-1).includes('shipment_page=1'));
 find(t,'经营报表客户').props.onChange({target:{value:'1'}});t=await h.render();assert(text(t).includes('客户成本未分摊'));assert(!text(t).includes('公司钱包对照'));
 h.events['warehouse-changed']();t=await h.render();assert(!calls.at(-1).includes('customer_id='));assert(!find(t,'经营报表来源详情'));
 h.props.endDate='2026-09-29';t=await h.render();assert(text(t).includes('加载中'));
 h.props.startDate='2026-10-01';h.props.endDate='2026-10-31';t=await h.render();held.shift()();t=await h.render();assert(text(t).includes('实际到账'));assert.equal(walk(t).filter(n=>n.type==='button'&&text(n)==='发货 #9').length,0);
 fail=true;h.events['auth-user-refreshed']();t=await h.render();assert(text(t).includes('隔离报表错误'));assert(!text(t).includes('¥1,000.00'));
 fail=false;button(t,'重试').props.onClick();t=await h.render();assert(!text(t).includes('隔离报表错误'));
 let parentRelease,holdParent=false;const parentCalls=[],Child=()=>null,Warehouse=()=>null;
 const parent=setup('src/app/(dashboard)/reports/page.tsx',()=>({'@/lib/api':{getToken:()=> 'isolated',api:{async get(route){parentCalls.push(route);if(holdParent&&route.startsWith('/reports/income-expense'))await new Promise(r=>parentRelease=r);return route.startsWith('/reports/previews')?{previews:{}}:{data:[],total_income_by_currency:{THB:1000},total_expense_by_currency:{THB:400}};}}},'@/components/OperatingReport':{__esModule:true,default:Child},'@/components/WarehouseSummary':{__esModule:true,default:Warehouse},'@/lib/currency':{fmtMoney:()=>'',fmtMoneyByCurrency:()=>''},'@/components/ui/Toast':{useToast:()=>({toast(){}})},'next/navigation':{useRouter:()=>({push(){}})}}));
 t=await parent.render();assert(walk(t).some(n=>n.type===Warehouse));button(t,'经营情况（独立）').props.onClick();t=await parent.render();assert(walk(t).some(n=>n.type===Child));assert(!walk(t).some(n=>n.type===Warehouse));assert(!parentCalls.some(r=>r.startsWith('/reports/operations')));
 find(t,'经营月份').props.onChange({target:{value:'2026-09'}});t=await parent.render();let child=walk(t).find(n=>n.type===Child);assert.equal(child.props.startDate,'2026-09-01');assert.equal(child.props.endDate,'2026-09-30');assert(parent.location.search.includes('view=operations'));assert(parent.location.search.includes('start_date=2026-09-01'));
 button(t,'收支报表').props.onClick();t=await parent.render();assert(walk(t).some(n=>n.type===Warehouse));assert(!walk(t).some(n=>n.type===Child));assert(parentCalls.some(r=>r==='/reports/income-expense?start_date=2026-09-01&end_date=2026-09-30'));
 holdParent=true;button(t,'收支报表').props.onClick();t=await parent.render();button(t,'经营情况（独立）').props.onClick();t=await parent.render();parentRelease();t=await parent.render();assert(walk(t).some(n=>n.type===Child));assert(!button(t,'导出 Excel'));
 console.log('PASS: actual operating component and reports-page integration, missing-cost/null-profit labels, source tracing, separate currencies, customer nonallocation, paging, stale month/warehouse/auth protection, error/retry and unchanged wallet-report entry');
})().catch(e=>{console.error(e);process.exitCode=1;});
