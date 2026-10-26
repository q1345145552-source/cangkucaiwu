// Actual UI/hook and transport modules; financial effects are covered separately in PostgreSQL.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript'),React=require('react'),{File}=require('node:buffer');
const compile=(file,imports={},extra={})=>{const m={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src',file),'utf8'),{fileName:file,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module:m,exports:m.exports,require:n=>imports[n]||require(n),console,Date,Intl,process:{env:{}},...extra});return m.exports;};
const walk=x=>!x||typeof x!=='object'?[]:Array.isArray(x)?x.flatMap(walk):[x,...walk(x.props?.children)];
const text=x=>x==null||typeof x==='boolean'?'':typeof x!=='object'?String(x):Array.isArray(x)?x.map(text).join(''):text(x.props?.children);
const tick=()=>new Promise(r=>setTimeout(r,0));
const mem=()=>{const d=new Map();return {getItem:k=>d.get(k)||null,setItem:(k,v)=>d.set(k,v),removeItem:k=>d.delete(k),d};};
function hooks(){let state=[],refs=[],deps=[],effects=[],clean=[],si=0,ri=0,ei=0;return {react:{...React,useState(v){const i=si++;if(!(i in state))state[i]=typeof v==='function'?v():v;return [state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];},useRef(v){const i=ri++;return refs[i]||(refs[i]={current:v});},useEffect(fn,d){const i=ei++,key=JSON.stringify(d);if(deps[i]!==key){deps[i]=key;effects.push(()=>{clean[i]?.();clean[i]=fn();});}}},async render(fn){for(let i=0;i<12;i++){si=ri=ei=0;const t=fn();if(!effects.length)return t;effects.splice(0).forEach(f=>f());await tick();}throw Error('effects did not settle');}};}
const money=compile('lib/currency.ts'),local=mem(),session=mem();let wh='1',seq=0,held=null;
local.setItem('user',JSON.stringify({id:1,warehouse_id:1}));
class ApiError extends Error{constructor(status,detail){super(typeof detail==='string'?detail:detail.message);this.status=status;this.detail=detail;}}
const api={ApiError,getToken:()=> 'synthetic-token',getActiveWarehouseId:()=>wh,warehouseRequestHeaders:()=>({'X-Warehouse-ID':wh,Authorization:'Bearer synthetic-token'}),api:{get:async url=>held?await held:url.endsWith('/suppliers')?{data:[{id:1,name:'本仓供应商'}]}:{identity:{supplier_id:1,invoice_identity:{issuer_identifier:'TAX',series:'VAT',number:'N-1'}}}}};
const moduleFor=h=>compile('components/CostIdentity.tsx',{react:h.react,'@/lib/api':api,'@/lib/currency':money,'next/link':{__esModule:true,default:'a'}});
const by=(tree,label)=>{const x=walk(tree).find(v=>v.props?.['aria-label']===label);assert(x,'missing '+label);return x;};
const button=(tree,label)=>{const x=walk(tree).find(v=>v.type==='button'&&text(v)===label);assert(x,'missing '+label);return x;};
(async()=>{
 const fieldsHook=hooks(),fields=moduleFor(fieldsHook);let value=fields.emptyCost();const form=()=>fields.CostIdentityFields({value,onChange:v=>value=v});let tree=await fieldsHook.render(form);
 assert(text(tree).includes('本仓供应商'));by(tree,'费用供应商').props.onChange({target:{value:'1'}});
 for(const [label,v] of [['开票方官方识别号','TAX'],['发票类型／系列','VAT'],['完整发票号码','N-1']]){tree=await fieldsHook.render(form);by(tree,label).props.onChange({target:{value:v}});}
 tree=await fieldsHook.render(form);walk(tree).find(v=>v.type==='input'&&v.props.type==='checkbox').props.onChange({target:{checked:true}});assert(value.invoice.verified);
 const h=hooks(),mod=moduleFor(h);let control;const render=()=>{control=mod.useCostIdentity();return control.dialog;};await h.render(render);control.setValue(value);await h.render(render);assert.equal(control.payload().invoice_identity.number,'N-1');
 control.setValue({...value,invoice:{...value.invoice,verified:false}});await h.render(render);assert.throws(()=>control.payload(),/核对完整发票/);
 assert.equal(control.capture(new ApiError(503,{code:'cost_identity_guards_missing',message:'约束缺失'}),async()=>{}),false);
 // A delayed original-record read cannot populate a different selected warehouse.
 let release;held=new Promise(r=>release=r);const delayed=control.edit('expense',1);wh='2';release({identity:{supplier_id:999,invoice_identity:{issuer_identifier:'OLD',series:'OLD',number:'OLD'}}});await delayed;held=null;await h.render(render);assert.notEqual(control.value.supplier_id,999);wh='1';
 const candidate={ref:'expense:7',source_label:'运营支出',id:7,date:'2026-10-26',amount:100,currency:'THB',status:'paid',href:'/expense-identities/expense/7',reason:'同供应商、币种、金额'};
 const hard={hard_duplicate:true,message:'同一真实发票不能重复',candidates:[candidate],version:'v1'};
 const hardHook=hooks(),hardModule=moduleFor(hardHook);tree=await hardHook.render(()=>hardModule.CostDuplicateDialog({challenge:hard,onClose(){},onConfirm:async()=>{throw Error('hard duplicate bypass');}}));
 assert(!walk(tree).some(v=>v.type==='button'&&text(v)==='说明后继续登记'));assert.equal(walk(tree).find(v=>v.type==='a').props.href,candidate.href);
 const hidden={permission_required:true,message:'需有原单权限人员核查'};tree=await hardHook.render(()=>hardModule.CostDuplicateDialog({challenge:hidden,onClose(){},onConfirm:async()=>{}}));assert(!walk(tree).some(v=>v.type==='a'||v.type==='textarea'||v.type==='button'&&text(v)==='说明后继续登记'));
 const dialogHook=hooks(),dialog=moduleFor(dialogHook);let submitted=[];const challenge={hard_duplicate:false,message:'疑似',candidates:[candidate],version:'candidate-current',target_ref:'fund_item:9'};
 const renderDialog=()=>dialog.CostDuplicateDialog({challenge,onClose(){},onConfirm:async v=>submitted.push(v)});
 tree=await dialogHook.render(renderDialog);await button(tree,'说明后继续登记').props.onClick();assert.equal(submitted.length,0);tree=await dialogHook.render(renderDialog);assert(text(tree).includes('请填写本次继续登记的原因'));
 by(tree,'跨渠道继续登记原因').props.onChange({target:{value:'第二张独立原票，已核对'}});tree=await dialogHook.render(renderDialog);await button(tree,'说明后继续登记').props.onClick();assert.deepEqual(JSON.parse(JSON.stringify(submitted[0])),{candidate_refs:['expense:7'],version:'candidate-current',reason:'第二张独立原票，已核对',target_ref:'fund_item:9'});
 let calls=[],records=new Map(),drop=true,reject=null;
 async function fetcher(url,o){const key=o.body.get('request_key');calls.push({key,headers:o.headers,invoice:o.body.get('invoice_identity'),confirmation:o.body.get('cost_confirmation'),file:await o.body.get('files').text()});if(reject)return {ok:false,status:409,json:async()=>({detail:reject})};if(!records.has(key))records.set(key,{id:records.size+1});if(drop){drop=false;throw Error('lost response after isolated commit');}return {ok:true,status:200,json:async()=>records.get(key)};}
 const transport=()=>compile('lib/manualWallet.ts',{'@/lib/api':api},{localStorage:local,sessionStorage:session,FormData,crypto:{randomUUID:()=>`cost-test-${++seq}`},fetch:fetcher});
 let wallet=transport();const source={category_id:1,account_id:1,supplier_id:1,amount:100,currency:'THB',expense_date:'2026-10-26',invoice_identity:{issuer_identifier:'TAX',series:'VAT',number:'N-1',verified:true}},file=new File(['original synthetic proof'],'proof.png',{type:'image/png',lastModified:1});
 await assert.rejects(wallet.submitWalletOperation('expense',source,[file]),/lost response/);const pending=wallet.pendingWalletOperation('expense');assert(pending);wallet=transport();await wallet.submitWalletOperation('expense',source,[file]);assert.equal(records.size,1);assert.equal(calls[0].key,calls[1].key);assert.equal(calls[0].file,calls[1].file);assert.equal(calls[0].invoice,calls[1].invoice);assert.equal(calls[0].headers['X-Warehouse-ID'],'1');
 reject={code:'cost_duplicate_confirmation',message:'疑似',candidates:[candidate],version:'current'};await assert.rejects(wallet.submitWalletOperation('expense',source,[file]),e=>e.detail.code==='cost_duplicate_confirmation');assert.equal(wallet.pendingWalletOperation('expense'),null);reject=null;await wallet.submitWalletOperation('expense',source,[file],submitted[0]);assert.equal(JSON.parse(calls.at(-1).confirmation).version,'candidate-current');
 assert(!Array.from(session.d.values()).join('').includes('synthetic-token'));
 console.log('PASS: actual supplier/invoice fields and verified validation; hard/restricted UI has no bypass or private link; explicit current refs/version/reason; scoped delayed reads and guard errors; actual wallet transport preserves invoice, original file and request after lost response, structured challenges and confirmed retry');
})().catch(e=>{console.error(e);process.exitCode=1;});
