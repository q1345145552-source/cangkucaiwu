// Render the real advance form; verify source selection, request contract and failed money checks.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const React=require('react'),ts=require('typescript');
const source=fs.readFileSync(path.resolve(__dirname,'../src/app/(dashboard)/employee-advances/page.tsx'),'utf8');
const options={accounts:[{id:1,account_name:'银行',account_type:'bank',currency:'THB',current_balance:5000},{id:3,account_name:'现金',account_type:'cash',currency:'THB',current_balance:20000},{id:4,account_name:'人民币',account_type:'bank',currency:'CNY',current_balance:3000}],cash_advances:[{id:41,payer_name:'主管甲',currency:'THB',available_amount:8000},{id:42,payer_name:'主管乙',currency:'CNY',available_amount:1000}],funds:[{id:7,employee_name:'备用金主管',currency:'THB',available:10000}]};
const text=n=>n==null||typeof n==='boolean'?'':typeof n!=='object'?String(n):Array.isArray(n)?n.map(text).join(''):text(n.props?.children);
const walk=n=>!n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(walk):[n,...walk(n.props?.children)];
const find=(t,p)=>{let n=walk(t).find(p);assert(n,'Missing node');return n;};
const button=(t,label)=>find(t,n=>n.type==='button'&&text(n).trim()===label);
const field=(t,label)=>find(t,n=>n.props?.['aria-label']===label);
const change=(n,value)=>n.props.onChange({target:{value}});
function harness({optionsError=false,postError='',defer=false}={}){
 let states=[],cursor=0,ei=0,deps=[],effects=[],writes=[],messages=[],release;
 const react={...React,useState(initial){const i=cursor++;if(!(i in states))states[i]=typeof initial==='function'?initial():initial;return[states[i],v=>states[i]=typeof v==='function'?v(states[i]):v];},useEffect(fn,ds){const i=ei++,key=JSON.stringify(ds);if(deps[i]!==key){deps[i]=key;effects.push(fn);}}};
 const api={get:async route=>{if(route==='/employee-advances/funding-options'){if(optionsError)throw Error('来源加载失败');return structuredClone(options);}if(route==='/employee-advances/recipients')return{data:[{value:'employee:1',name:'员工甲',role_label:'员工'}]};return route.includes('/summary')?{}:{data:[]};},post:async(route,body)=>{writes.push({route,body:JSON.parse(JSON.stringify(body))});if(defer)await new Promise(r=>release=r);if(postError)throw Error(postError);return{message:'预支记录已创建'};}};
 const imports={react,'@/lib/api':{api,getToken:()=> 'test'},'@/hooks/useMenuPermission':{useMenuPermission:()=>true},'@/hooks/useAuth':{useAuth:()=>({user:{role:'warehouse_admin'}})},'@/components/ui/Toast':{useToast:()=>({toast:(...args)=>messages.push(args)})},'next/navigation':{useRouter:()=>({push(){}})}};
 const m={exports:{}};vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module:m,exports:m.exports,require:n=>imports[n]||require(n),Date,URLSearchParams,window:{location:{search:''}}});
 return{async render(){let t;for(let i=0;i<5;i++){cursor=ei=0;t=m.exports.default();for(const e of effects.splice(0))e();await new Promise(setImmediate);}return t;},writes,messages,finish(){release();}};
}
async function open(h){let t=await h.render();button(t,'记预支').props.onClick();return h.render();}
async function fill(h,t,source,amount='1000'){
 change(field(t,'资金来源'),source);t=await h.render();change(field(t,'预支对象'),'employee:1');t=await h.render();
 change(find(t,n=>n.type==='input'&&n.props.type==='number'),amount);return h.render();
}
(async()=>{
 let h=harness(),t=await open(h),checks=0;
 assert.equal(field(t,'资金来源').props.value,'');await button(t,'提交').props.onClick();assert.equal(h.messages.at(-1)[1],'请选择资金来源');assert.equal(h.writes.length,0);checks++;
 t=await fill(h,t,'company_account');assert.equal(field(t,'公司付款账户').props.value,3);await button(t,'提交').props.onClick();
 assert.equal(h.writes[0].body.funding_source,'company_account');assert.equal(h.writes[0].body.payment_account_id,3);assert.equal(h.writes[0].body.currency,'THB');checks++;
 h=harness();t=await fill(h,await open(h),'company_account');change(field(t,'公司付款账户'),'');t=await h.render();await button(t,'提交').props.onClick();assert.equal(h.messages.at(-1)[1],'请选择公司付款账户');assert.equal(h.writes.length,0);checks++;
 h=harness();t=await fill(h,await open(h),'company_account','21000');await button(t,'提交').props.onClick();assert.equal(h.messages.at(-1)[1],'公司账户余额不足');assert.equal(h.writes.length,0);checks++;
 h=harness();t=await fill(h,await open(h),'cash_advance');assert(text(t).includes('公司账户不扣款，本次不记运营支出'));assert.equal(walk(field(t,'垫款单')).filter(n=>n.type==='option').length,2);
 await button(t,'提交').props.onClick();assert.equal(h.messages.at(-1)[1],'请选择垫款单');change(field(t,'垫款单'),'41');t=await h.render();await button(t,'提交').props.onClick();assert.equal(h.writes[0].body.cash_advance_id,41);assert.equal(h.writes[0].body.payment_account_id,0);checks++;
 h=harness();t=await fill(h,await open(h),'cash_advance','9000');change(field(t,'垫款单'),'41');t=await h.render();await button(t,'提交').props.onClick();assert.equal(h.messages.at(-1)[1],'垫款单剩余金额不足');assert.equal(h.writes.length,0);checks++;
 h=harness();t=await fill(h,await open(h),'expense_fund');assert.equal(field(t,'备用金账户').props.value,7);assert(text(t).includes('本仓备用金可用余额 10,000 THB'));await button(t,'提交').props.onClick();assert.equal(h.writes[0].body.fund_account_id,7);assert.equal(h.writes[0].body.funding_source,'expense_fund');checks++;
 h=harness();t=await fill(h,await open(h),'expense_fund','10001');await button(t,'提交').props.onClick();assert.equal(h.messages.at(-1)[1],'超出备用金可用余额');assert.equal(h.writes.length,0);checks++;
 h=harness();t=await fill(h,await open(h),'company_account');change(field(t,'预支币种'),'CNY');t=await h.render();assert.equal(field(t,'公司付款账户').props.value,4);assert.equal(walk(field(t,'公司付款账户')).filter(n=>n.type==='option').length,2);checks++;
 h=harness({optionsError:true});t=await open(h);assert(text(t).includes('来源加载失败'));assert(button(t,'提交').props.disabled);assert(field(t,'资金来源').props.disabled);assert.equal(h.writes.length,0);checks++;
 h=harness({postError:'预支合计不能超过当月工资，当前可用 2000.00 元'});t=await fill(h,await open(h),'company_account');await button(t,'提交').props.onClick();t=await h.render();assert.equal(h.messages.at(-1)[1],'预支合计不能超过当月工资，当前可用 2000.00 元');assert.equal(field(t,'预支对象').props.value,'employee:1');checks++;
 h=harness({defer:true});t=await fill(h,await open(h),'company_account');const post=button(t,'提交').props.onClick();t=await h.render();assert(button(t,'提交中...').props.disabled);await button(t,'提交中...').props.onClick();assert.equal(h.writes.length,1);h.finish();await post;checks++;
 assert(source.includes('max-h-[85vh] overflow-y-auto'));
 console.log(JSON.stringify({result:'PASS',scenarios:checks,scope:'source required, cash default, source/currency payloads, insufficient funds, no extra permissions, failure preservation, loading and duplicate submit guards'}));
})().catch(e=>{console.error(e);process.exit(1)});
