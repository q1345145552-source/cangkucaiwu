// Exercise the actual page handlers. Financial invariants are tested against native PostgreSQL.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const ts=require('typescript'),React=require('react');
const walk=x=>!x||typeof x!=='object'?[]:Array.isArray(x)?x.flatMap(walk):[x,...walk(x.props?.children)];
const text=x=>x==null||typeof x==='boolean'?'':typeof x!=='object'?String(x):Array.isArray(x)?x.map(text).join(''):text(x.props?.children);
const find=(tree,p)=>{const result=walk(tree).find(p);assert(result,'Missing node');return result;};
const button=(tree,name)=>find(tree,n=>n.type==='button'&&text(n).trim()===name);
const titled=(tree,name)=>find(tree,n=>n.type==='button'&&n.props.title===name);
const field=(tree,label)=>find(find(tree,n=>Array.isArray(n.props?.children)&&n.props.children.some(c=>c?.type==='label'&&text(c).startsWith(label))),n=>n.type==='input'||n.type==='select');
const change=(node,value)=>node.props.onChange({target:{value}});
const wait=()=>new Promise(r=>setTimeout(r,0));

function harness({role='warehouse_admin',grant=true,initialRows=[]}={}) {
 let state=[],refs=[],deps=[],effects=[],index=0,ri=0,ei=0;
 const rows=initialRows,writes=[],messages=[],reads=[],flags={failPay:false,dropResponse:false};
 const react={...React,useState(initial){const i=index++;if(!(i in state))state[i]=typeof initial==='function'?initial():initial;return[state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];},
  useRef(initial){const i=ri++;return refs[i]||(refs[i]={current:initial});},useEffect(fn,values){const i=ei++,key=JSON.stringify(values);if(deps[i]!==key){deps[i]=key;effects.push(fn);}}};
 const WalletAccountSelect=()=>null;
 const user={id:1,role};
 const api={async get(route){reads.push(route);if(route.includes('/payment-preview'))return {balance:-1000,amount:200};if(route.includes('/threshold'))return {threshold:500};
   if(route.includes('/summary'))return {pending_count:rows.filter(r=>r.status==='pending').length,approved_count:rows.filter(r=>r.status==='approved').length,paid_by_currency:[]};
   return {data:[...rows]};},
  async post(route,body){writes.push({route,body});await wait();
   if(route==='/expense-approvals') {rows.push({id:rows.length+1,...body,status:body.amount<=500?'approved':'pending'});return {status:rows.at(-1).status,message:body.amount<=500?'免审批，等待确认付款':'费用已提交，等待审批'};}
   const row=rows.find(r=>r.id===Number(route.split('/')[2]));assert(row);
   if(route.endsWith('/pay')) {
    if(flags.failPay)throw Error('公司账户余额不足');
    const already=row.status==='paid';row.status='paid';row.payment_voucher='uploads/payment.png';row.payer_name='测试老板';row.paid_at='2026-10-20T12:00:00+07:00';
    if(flags.dropResponse){flags.dropResponse=false;throw Error('网络响应丢失');}
    return {message:already?'该申请已付款，请勿重复付款':'已付款',already_paid:already};
   }
   if(route.endsWith('/approve'))row.status='approved';
   if(route.endsWith('/reject'))row.status='rejected';
   return {};
  },async put(route,body){writes.push({route,body});return {message:'已重新提交'};}};
 const m={exports:{}};
 const source=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/app/(dashboard)/expense-approvals/page.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const imports={react,'@/components/WalletAccountSelect':{__esModule:true,default:WalletAccountSelect},
  '@/lib/api':{api,getToken:()=> 'synthetic-token'},'@/hooks/useAuth':{useAuth:()=>({user})},
  '@/hooks/useMenuPermission':{useMenuPermission:key=>{assert.equal(key,'expense_approval');return grant;}},
  '@/components/ui/Toast':{useToast:()=>({toast:(...args)=>messages.push(args)})},'next/navigation':{useRouter:()=>({push(){}})}};
 vm.runInNewContext(source,{module:m,exports:m.exports,require:n=>n==='@/lib/balanceWarning'?require('./balance-warning-test-support.cjs'):n==='@/components/CostIdentity'?require('./cost-identity-compat.cjs'):n==='@/lib/registrationRequest'&&!imports[n]?{registrationDraft:()=>null,submitRegistration:async(_k,_r,_p,send)=>send('legacy-regression-key')}:imports[n]||require(n),console,Date,Promise,
  FileReader:class {readAsDataURL(){this.result='data:image/png;base64,test-image';queueMicrotask(()=>this.onload());}}});
 return {rows,writes,messages,reads,flags,WalletAccountSelect,async render(){await wait();for(let i=0;i<20;i++){index=ri=ei=0;const tree=m.exports.default();if(!effects.length)return tree;effects.splice(0).forEach(fn=>fn());await wait();}throw Error('Effects did not settle');}};
}
const row=(source='company')=>({id:1,applicant_id:1,applicant_name:'测试主管',amount:200,currency:'THB',purpose:'耗材',expense_date:'2026-09-30',status:'approved',fund_source:source,payment_account_id:source==='company'?1:null});
function selectPayProof(tree){const inputs=walk(tree).filter(n=>n.type==='input'&&n.props.type==='file');inputs.at(-1).props.onChange({target:{files:[{name:'付款凭证.png'}]}});}

(async()=>{
 // Low amounts remain unpaid, and the page shows the server's precise message.
 let h=harness(),tree=await h.render();button(tree,'提申请').props.onClick();tree=await h.render();
 change(field(tree,'金额'),'200');tree=await h.render();change(field(tree,'用途说明'),'购买耗材');tree=await h.render();
 find(tree,n=>n.type===h.WalletAccountSelect).props.onChange(1);tree=await h.render();
 const submit=button(tree,'提交').props.onClick;await Promise.all([submit(),submit()]);tree=await h.render();
 assert.equal(h.writes.filter(r=>r.route==='/expense-approvals').length,1);
 assert.equal(h.rows[0].status,'approved');assert(h.messages.some(m=>m[1]==='免审批，等待确认付款'));
 assert(text(tree).includes('待付款'));assert(!text(tree).includes('费用已直接生效'));

 // Company payment: account, voucher and one request despite double click.
 h=harness({initialRows:[row()]});tree=await h.render();titled(tree,'付款').props.onClick();tree=await h.render();
 assert(text(tree).includes('本次付款：200 THB'));assert(text(tree).includes('从所选公司账户付款'));
 assert(button(tree,'确认付款').props.disabled);
 find(tree,n=>n.type===h.WalletAccountSelect).props.onChange(0);selectPayProof(tree);tree=await h.render();
 await button(tree,'确认付款').props.onClick();assert(h.messages.some(m=>m[1]==='请选择付款账户'));assert.equal(h.writes.length,0);
 find(tree,n=>n.type===h.WalletAccountSelect).props.onChange(1);tree=await h.render();
 const confirm=button(tree,'确认付款').props.onClick;await Promise.all([confirm(),confirm()]);tree=await h.render();
 assert.equal(h.writes.length,1);assert.equal(h.writes[0].body.payment_account_id,1);assert(h.writes[0].body.voucher_base64);
 assert(text(tree).includes('付款人：测试老板'));assert(text(tree).includes('2026/10/20 12:00:00'));
 assert(!walk(tree).some(n=>n.props?.title==='付款'));

 // Insufficient balance: cancellation writes nothing; accepted retry writes once.
 h=harness({initialRows:[row()]});tree=await h.render();titled(tree,'付款').props.onClick();tree=await h.render();selectPayProof(tree);tree=await h.render();
 const gate=require('./balance-warning-test-support.cjs');gate.setAllowed(false);await button(tree,'确认付款').props.onClick();assert.equal(h.writes.length,0);assert.equal(gate.calls[0],'当前账户余额不足（可用 -1,000.00，本次 200.00），确认继续吗');gate.setAllowed(true);await button(tree,'确认付款').props.onClick();assert.equal(h.writes.length,1);

 // Petty-cash payment never submits a company account, even if an older dialog selected one.
 h=harness({initialRows:[row('fund')]});tree=await h.render();titled(tree,'付款').props.onClick();tree=await h.render();
 assert(!walk(tree).some(n=>n.type===h.WalletAccountSelect));assert(text(tree).includes('从备用金支付并记录开销'));
 selectPayProof(tree);tree=await h.render();await button(tree,'确认付款').props.onClick();
 assert.equal(h.writes[0].body.payment_account_id,null);

 // Validation and backend failure leave the dialog available for a safe retry.
 h=harness({initialRows:[row()]});tree=await h.render();titled(tree,'付款').props.onClick();tree=await h.render();
 await button(tree,'确认付款').props.onClick();assert(h.messages.some(m=>m[1]==='请上传付款凭证'));assert.equal(h.writes.length,0);
 selectPayProof(tree);tree=await h.render();h.flags.failPay=true;await button(tree,'确认付款').props.onClick();tree=await h.render();
 assert(h.messages.some(m=>m[1]==='公司账户余额不足'));assert(!button(tree,'确认付款').props.disabled);
 h.flags.failPay=false;await button(tree,'确认付款').props.onClick();assert.equal(h.rows[0].status,'paid');

 // Ambiguous response: a retry uses the same approval ID and gets the existing payment.
 h=harness({initialRows:[row()]});tree=await h.render();titled(tree,'付款').props.onClick();tree=await h.render();
 selectPayProof(tree);tree=await h.render();h.flags.dropResponse=true;await button(tree,'确认付款').props.onClick();tree=await h.render();
 await button(tree,'确认付款').props.onClick();assert.equal(new Set(h.writes.map(r=>r.route)).size,1);
 assert(h.messages.some(m=>m[1]==='该申请已付款，请勿重复付款'));

 // Permission controls: staff and supervisors submit only with permission and never pay.
 for(const role of ['supervisor','staff','warehouse_labor','super_admin'])for(const grant of [false,true]){
  h=harness({role,grant,initialRows:[row()]});tree=await h.render();
  assert(!walk(tree).some(n=>n.props?.title==='付款'));
  assert.equal(walk(tree).some(n=>n.type==='button'&&text(n).trim()==='提申请'),grant&&['supervisor','staff'].includes(role));
 }
 console.log('PASS: actual fee page low-amount unpaid message, account/voucher validation, company/fund payloads, double-click protection, failure retry, lost-response retry, payer/Thai time, summary refresh and role/permission controls');
})().catch(error=>{console.error(error);process.exitCode=1;});
