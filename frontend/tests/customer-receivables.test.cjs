const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),React=require('react');
const wait=()=>new Promise(r=>setTimeout(r,0));
const walk=n=>!n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(walk):[n,...walk(n.props?.children)];
const text=n=>n==null||typeof n==='boolean'?'':typeof n!=='object'?String(n):Array.isArray(n)?n.map(text).join(''):text(n.props?.children);
const find=(t,label)=>walk(t).find(n=>n.props?.['aria-label']===label),button=(t,label)=>walk(t).find(n=>n.type==='button'&&text(n)===label);
function harness(writable=true){
 const state=[],refs=[],deps=[],effects=[],clean=[],calls=[],messages=[],held=[];let si=0,ri=0,ei=0,cid=1,release,hold=false,fail=false;
 const react={...React,useState(v){const i=si++;if(!(i in state))state[i]=typeof v==='function'?v():v;return[state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];},useRef(v){const i=ri++;return refs[i]||(refs[i]={current:v});},useEffect(fn,d){const i=ei++,key=JSON.stringify(d);if(deps[i]!==key){deps[i]=key;effects.push(()=>{clean[i]?.();clean[i]=fn();});}}};
 const make=empty=>({customer_id:cid,by_currency:{THB:{shipped:empty?0:1000,received:empty?0:1100,applied:empty?0:1000,outstanding:0,prepayment:empty?0:100,opening_signed_balance:0,period_shipped:empty?0:1000,period_received:empty?0:1100,events:empty?[]:[{date:'2026-10-20',source:'incoming',source_id:88,warehouse_id:1,amount:1100,currency:'THB',outstanding_after:0,prepayment_after:100,remark:'明确客户来源'}]},CNY:{shipped:0,received:200,applied:0,outstanding:0,prepayment:200,opening_signed_balance:0,period_shipped:0,period_received:200,events:[]}},needs_review:true,review_items:[{source_id:99,amount:777,currency:'THB',message:'历史手填欠款待核对'}]});
 const api={async get(route){calls.push({method:'get',route});if(route.startsWith('/incoming')){const page=new URL(route,'http://test').searchParams.get('page');return{data:page==='1'?[{id:88,received_date:'2026-10-20',amount:100,currency:'THB',payer_name:'同名客户'},{id:89,customer_identity_conflict:true,received_date:'2026-10-20',amount:200,currency:'THB'}]:[{id:90,received_date:'2026-10-20',amount:300,currency:'CNY'}],total:3};}const m=new URL(route,'http://test').searchParams.get('month');if(m==='2026-09')await new Promise(r=>held.push(r));return make(m==='2028-01');},async post(route,data){calls.push({method:'post',route,data});if(hold)await new Promise(r=>release=r);if(fail)throw Error('隔离关联失败');return{message:'钱包未重复入账'};}};
 const m={exports:{}},imports={react,'@/lib/api':{api},'@/hooks/useMenuPermission':{useMenuPermission:()=>writable},'@/components/ui/Toast':{useToast:()=>({toast:(...v)=>messages.push(v)})}};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync('src/components/CustomerReceivable.tsx','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module:m,exports:m.exports,require:n=>imports[n]||require(n),console,Date,Number,URLSearchParams});
 return{calls,messages,held,hold:v=>hold=v,fail:v=>fail=v,release:()=>release(),customer:v=>cid=v,async render(){await wait();for(let n=0;n<15;n++){si=ri=ei=0;const t=m.exports.default({customerId:cid});if(!effects.length)return t;effects.splice(0).forEach(f=>f());await wait();}throw Error('unsettled');}};
}
(async()=>{
 const h=harness();let t=await h.render();assert(text(t).includes('฿1,100.00'));assert(text(t).includes('¥200.00'));assert(text(t).includes('历史手填欠款待核对'));
 button(t,'到账 #88').props.onClick();t=await h.render();assert(text(find(t,'客户对账来源详情')).includes('原实际到账流水 #88'));assert(text(t).includes('明确客户来源'));
 await button(t,'关联已有到账').props.onClick();t=await h.render();assert.equal(h.calls.filter(r=>r.route.startsWith('/incoming')).length,2);
 const select=find(t,'待关联实际到账');assert.equal(walk(select).filter(n=>n.type==='option').length,3);assert(!text(select).includes('#89'));
 await button(t,'确认关联到账').props.onClick();assert.equal(h.messages.at(-1)[1],'请选择实际到账记录');
 select.props.onChange({target:{value:'88'}});t=await h.render();h.hold(true);const submit=button(t,'确认关联到账').props.onClick;
 const saving=submit();submit();t=await h.render();assert(button(t,'关联中…').props.disabled);assert.equal(h.calls.filter(r=>r.method==='post').length,1);
 h.fail(true);h.release();await saving;t=await h.render();assert(find(t,'关联客户实际到账'));assert.equal(h.messages.at(-1)[1],'隔离关联失败');
 h.fail(false);h.hold(false);await button(t,'确认关联到账').props.onClick();t=await h.render();assert(!find(t,'关联客户实际到账'));assert.equal(h.calls.at(-2).data.incoming_flow_id,88);
 find(t,'客户对账截至月份').props.onChange({target:{value:'2026-09'}});t=await h.render();assert(text(t).includes('加载对账'));
 find(t,'客户对账截至月份').props.onChange({target:{value:'2028-01'}});t=await h.render();h.held.shift()();t=await h.render();assert(!text(t).includes('฿1,100.00'),text(t));
 await button(t,'关联已有到账').props.onClick();h.customer(3);t=await h.render();assert(!find(t,'关联客户实际到账'));
 t=await harness(false).render();assert(!button(t,'关联已有到账'));assert(find(t,'客户应收实收预收对账'));
 console.log('PASS: real receivables component currencies, quarantine warnings, original source detail, paged receipt-ID selection, validation, double clicks, failed/retried link, stale month/customer protection and read-only role');
})().catch(e=>{console.error(e);process.exitCode=1;});
