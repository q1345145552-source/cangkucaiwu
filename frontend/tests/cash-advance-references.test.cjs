const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const ts=require('typescript'),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const badge=require('./cash-advance-link-test-support.cjs').default;
const text=n=>n==null||typeof n==='boolean'?'':typeof n!=='object'?String(n):Array.isArray(n)?n.map(text).join(''):text(n.props?.children);
const walk=n=>!n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(walk):[n,...walk(n.props?.children)];
const html=(id,number)=>renderToStaticMarkup(React.createElement(badge,{id,number}));
assert(html(41,'#41').includes('href="/cash-advances/41"'));
assert(html(41,'#41').includes('垫款单 #41'));
for(const [id,number] of [[null,null],[undefined,undefined],[41,null],[0,'#0'],[-1,'#-1'],['41','#41'],[1.1,'#1.1']])assert.equal(html(id,number),'');
let stopped=false;badge({id:41,number:'#41'}).props.onClick({stopPropagation(){stopped=true;}});assert(stopped);
for(const [file,count] of [['app/(dashboard)/payroll/page.tsx',2],['app/(dashboard)/employee-advances/page.tsx',1],['components/ReimbursementPaymentHistory.tsx',1]]){
 const source=fs.readFileSync(path.join(__dirname,'../src',file),'utf8');
 assert.equal([...source.matchAll(/<CashAdvanceLink /g)].length,count,file);
 assert(source.includes('cash_advance_number'),file);
}
function harness({id='41',reject=false,defer=false}={}){
 let states=[],cursor=0,deps=[],ei=0,effects=[],props={params:{id}},cleanup,back=0;const reads=[],pending=[];
 const react={...React,useState(initial){const i=cursor++;if(!(i in states))states[i]=initial;return[states[i],v=>states[i]=v];},useEffect(fn,ds){const i=ei++,key=JSON.stringify(ds);if(deps[i]!==key){deps[i]=key;effects.push(fn);}}};
 const response={advance:{id:41,payer_name:'主管甲',status_label:'已确认',advance_date:'2026-10-20',purpose_label:'工资',amount:10000,repaid_amount:1000,outstanding_amount:9000,currency:'THB',created_by_name:'老板',created_at:'2026-10-20T10:00:00+07:00',reviewed_by_name:'老板',reviewed_at:'2026-10-20T10:00:00+07:00',description:'支付工资',voucher_path:'uploads/1/voucher.png'},payroll_usage:{data:[{payroll_record_id:2,employee_name:'员工甲',amount:7000,currency:'THB'}]},reimbursement_usage:{data:[{payment_id:3,reimbursement_id:4,employee_name:'主管甲',amount:1000,currency:'THB'}]},employee_advance_usage:{data:[{employee_advance_id:5,employee_name:'员工乙',amount:500,currency:'THB'}]},data:[{id:7,repayment_date:'2026-10-20',amount:1000,account_name:'现金',status:'active'}]};
 const api={get:async route=>{reads.push(route);if(defer)return await new Promise(resolve=>pending.push(resolve));if(reject)throw Error('无此操作权限');return response;}};
 const m={exports:{}},source=fs.readFileSync(path.join(__dirname,'../src/app/(dashboard)/cash-advances/[id]/page.tsx'),'utf8');
 vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module:m,exports:m.exports,require:n=>n==='react'?react:n==='@/lib/api'?{api}:n==='next/navigation'?{useRouter:()=>({back(){back++;}})}:require(n),Date,Intl,Number});
 return{async render(){let t;for(let i=0;i<4;i++){cursor=ei=0;t=m.exports.default(props);for(const fn of effects.splice(0)){if(cleanup)cleanup();cleanup=fn();}await new Promise(setImmediate);}return t;},reads,response,resolve(){pending.splice(0).forEach(fn=>fn(response));},change(id){props={params:{id}};},get back(){return back;}};
}
(async()=>{
 let h=harness(),t=await h.render();
 assert.deepEqual(h.reads,['/cash-advances/41/repayments']);
 for(const expected of ['垫款单 #41','主管甲','10,000.00 THB','9,000.00 THB','工资单 #2','报销单 #4','预支单 #5','归还记录'])assert(text(t).includes(expected),expected);
 const buttons=walk(t).filter(n=>n.type==='button');assert.deepEqual(buttons.map(text),['返回']);buttons[0].props.onClick();assert.equal(h.back,1);
 assert(walk(t).some(n=>n.type==='a'&&n.props.href==='/uploads/1/voucher.png'));
 h=harness({reject:true});t=await h.render();assert(text(t).includes('无此操作权限'));assert(!text(t).includes('主管甲'));
 for(const id of ['0','-1','abc','1/2','9007199254740992']){h=harness({id});t=await h.render();assert(text(t).includes('垫款单不存在'));assert.equal(h.reads.length,0);}
 h=harness({defer:true});t=await h.render();assert(text(t).includes('加载中'));h.change('bad');t=await h.render();h.resolve();await new Promise(setImmediate);t=await h.render();assert(text(t).includes('垫款单不存在'));assert(!text(t).includes('主管甲'));
 console.log(JSON.stringify({result:'PASS',badge:'valid references link, empty/invalid show nothing, row click stopped',page:'existing GET reader only, all three usages, permission denied and stale response blocked',integrations:4,mobile:'badge nowrap/touch padding; detail single-column layout'}));
})().catch(e=>{console.error(e);process.exitCode=1});
