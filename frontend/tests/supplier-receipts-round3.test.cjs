
function newImports(n,imports,extra){
 if(n==='@/lib/specifications')return compile('lib/specifications.ts',imports,extra);
 if(n==='@/components/StructuredSpecifications')return compile('components/StructuredSpecifications.tsx',imports,extra);
 if(n==='@/hooks/useSupplierAccess')return {useSupplierAccess:()=>({scope:'synthetic-existing-permission',loading:false,error:'',retry(){},can:imports['@/hooks/useMenuPermission'].useMenuPermission})};
}
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript'),React=require('react');
const compile=(file,imports={},extra={})=>{const m={exports:{}};const output=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src',file),'utf8'),{fileName:file,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}});vm.runInNewContext(output.outputText,{module:m,exports:m.exports,require:n=>({'@/lib/procurementControlRequest':'lib/procurementControlRequest.ts','@/components/ProcurementDutyFields':'components/ProcurementDutyFields.tsx','@/components/ProcurementRiskReview':'components/ProcurementRiskReview.tsx'}[n])?compile(({'@/lib/procurementControlRequest':'lib/procurementControlRequest.ts','@/components/ProcurementDutyFields':'components/ProcurementDutyFields.tsx','@/components/ProcurementRiskReview':'components/ProcurementRiskReview.tsx'})[n],imports,extra):['@/components/ExcelImportDialog','@/components/SkuProductMapping','@/components/ProductImportDialog','@/components/SupplierQuoteEditor','@/components/PurchaseQuotePreview'].includes(n)?{__esModule:true,default:()=>null}:n==='@/components/CostIdentity'?require('./cost-identity-compat.cjs'):n==='@/lib/registrationRequest'&&!imports[n]?{registrationDraft:()=>null,submitRegistration:async(_k,_r,_p,send)=>send('legacy-regression-key')}:imports[n]||newImports(n,imports,extra)||(n==='@/lib/excelImport'?compile('lib/excelImport.ts',imports):require(n)),console,URLSearchParams,Date,Intl,process:{env:{}},...extra});return m.exports;};
const walk=x=>!x||typeof x!=='object'?[]:Array.isArray(x)?x.flatMap(walk):[x,...walk(x.props?.children)];
const text=x=>x==null||typeof x==='boolean'?'':typeof x!=='object'?String(x):Array.isArray(x)?x.map(text).join(''):text(x.props?.children);
const tick=()=>new Promise(r=>setTimeout(r,0));
function storage(){const d=new Map();return{getItem:k=>d.get(k)||null,setItem:(k,v)=>d.set(k,v),removeItem:k=>d.delete(k),d};}
function hooks(){const state=[],refs=[],deps=[],effects=[],cleanups=[];let si=0,ri=0,ei=0;return{
  react:{...React,useState(v){const i=si++;if(!(i in state))state[i]=typeof v==='function'?v():v;return[state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];},useRef(v){const i=ri++;return refs[i]||(refs[i]={current:v});},useEffect(fn,d){const i=ei++,key=JSON.stringify(d);if(deps[i]!==key){deps[i]=key;effects.push(()=>{cleanups[i]?.();cleanups[i]=fn();});}}},
  async render(fn){await tick();for(let n=0;n<12;n++){si=ri=ei=0;const tree=fn();if(!effects.length)return tree;effects.splice(0).forEach(f=>f());await tick();}throw Error('unsettled');}
};}

const money=compile('lib/currency.ts'),local=storage(),session=storage();
local.setItem('user',JSON.stringify({id:1,warehouse_id:1}));local.setItem('token','synthetic');local.setItem('activeWarehouseId','2');
const realApi=compile('lib/api.ts',{}, {window:{},localStorage:local});let seq=0,calls=[],toasts=[],records=new Map(),drop=true;
const line={line_id:'stable-line-a',product_name:'同名材料',spec:'相同规格',unit:'件',quantity:100,received_quantity:0,remaining_quantity:100};
const order={id:33,warehouse_id:2,order_number:'LOCAL-33',items:[line],total_amount:1000,currency:'THB',status:'confirmed',receipt_status:'not_received',receipt_batches:[]};
const api={...realApi,api:{get:async url=>url.startsWith('/supplier-controls/orders/')?{creator_id:1,operator_id:1,policy_version:'a'.repeat(64),business_version:'b'.repeat(64),needs_exception:false,unknown_creator:false}:url.startsWith('/suppliers/purchase-receipt-discrepancies')?{data:[{purchase_order_id:33,line_id:'bad-history',order_number:'UNKNOWN',product_name:'旧行',order_quantity:10,received_quantity:null,diff_quantity:null,diff_amount:null,currency:'THB'},{purchase_order_id:34,line_id:'known',order_number:'KNOWN',product_name:'材料',order_quantity:10,received_quantity:8,diff_quantity:2,diff_amount:20,currency:'CNY'}]}:url.startsWith('/suppliers/purchase-orders/')?structuredClone(order):url.startsWith('/suppliers/purchase-orders')?{data:[structuredClone(order)]}:{data:[]}},getToken:()=> 'synthetic'};
const reg=compile('lib/registrationRequest.ts',{'@/lib/api':api},{localStorage:local,sessionStorage:session,crypto:{randomUUID:()=>`receipt-request-${++seq}`}});
async function fetcher(url,options){
 const key=options.body.get('request_key'),rows=JSON.parse(options.body.get('items'));calls.push({url,headers:options.headers,key,rows});
 if(!records.has(key)){records.set(key,{id:records.size+1,receipt_event_id:records.size+1,has_diff:records.size===0});line.received_quantity+=rows[0].received_quantity;line.remaining_quantity=100-line.received_quantity;}
 if(drop){drop=false;throw Error('local response lost after commit');}return{ok:true,status:200,json:async()=>records.get(key)};
}
const h=hooks(),imports={react:h.react,'@/lib/api':api,'@/lib/currency':money,'@/hooks/useI18n':{useI18n:()=>({t:k=>k})},'@/hooks/useAuth':{useAuth:()=>({user:{id:1,role:'warehouse_admin'}})},'@/hooks/useMenuPermission':{useMenuPermission:()=>true},'next/navigation':{useRouter:()=>({push(){}})},'@/components/ui/Toast':{useToast:()=>({toast:(...x)=>toasts.push(x)})},'@/components/common/DataTable':{__esModule:true,default:()=>null},'@/components/ProcurementInfo':{LinkedPayable:()=>null,PurchaseQuantities:()=>null},'@/components/PurchaseReceiptInfo':{ReceiptHistory:()=>null,ThreeWayMatch:()=>null},'@/lib/registrationRequest':reg,'@/components/PayableDuplicateDialog':{__esModule:true,default:()=>null}};
const Page=compile('app/(dashboard)/suppliers/page.tsx',imports,{window:{},localStorage:local,sessionStorage:session,FormData,fetch:fetcher,setTimeout}).default;
const button=(tree,label)=>{const found=walk(tree).find(x=>x.type==='button'&&text(x).trim()===label);assert(found,'missing '+label);return found;};
(async()=>{
 let tree=await h.render(()=>Page());await button(tree,'收货验收').props.onClick();tree=await h.render(()=>Page());await button(tree,'登记本次收货').props.onClick();tree=await h.render(()=>Page());
 let field=walk(tree).find(x=>x.props?.['aria-label']==='本次收货数量-stable-line-a');assert(field);assert.equal(field.props.value,'100');
 field.props.onChange({target:{value:'1.5'}});walk(walk(tree).find(x=>x.props?.role==='dialog'&&x.props['aria-label']==='登记本次收货')).find(x=>x.type==='input'&&x.props.type==='file').props.onChange({target:{files:[new Blob(['synthetic-photo'])]}});
 tree=await h.render(()=>Page());await button(tree,'确认本次收货').props.onClick();assert.equal(calls.length,0);assert(toasts.some(x=>x[1].includes('不支持小数')));
 tree=await h.render(()=>Page());field=walk(tree).find(x=>x.props?.['aria-label']==='本次收货数量-stable-line-a');assert.equal(field.props.value,'1.5');field.props.onChange({target:{value:'80'}});
 tree=await h.render(()=>Page());await button(tree,'确认本次收货').props.onClick();tree=await h.render(()=>Page());assert.equal(records.size,1);assert(reg.registrationDraft('purchase_receipt',33).unknown);
 await button(tree,'确认本次收货').props.onClick();tree=await h.render(()=>Page());assert.equal(calls[0].key,calls[1].key);assert.equal(records.size,1);assert.equal(line.received_quantity,80);
 await button(tree,'登记本次收货').props.onClick();tree=await h.render(()=>Page());field=walk(tree).find(x=>x.props?.['aria-label']==='本次收货数量-stable-line-a');assert.equal(field.props.value,'20');
 walk(walk(tree).find(x=>x.props?.role==='dialog'&&x.props['aria-label']==='登记本次收货')).find(x=>x.type==='input'&&x.props.type==='file').props.onChange({target:{files:[new Blob(['synthetic-second-photo'])]}});
 tree=await h.render(()=>Page());await button(tree,'确认本次收货').props.onClick();tree=await h.render(()=>Page());assert.equal(records.size,2);assert.equal(line.received_quantity,100);assert.notEqual(calls[2].key,calls[0].key);
 assert(calls.every(c=>c.headers['X-Warehouse-ID']==='2'&&c.headers['Content-Type']===undefined&&c.headers.Authorization==='Bearer synthetic'));
 assert.deepEqual(calls[2].rows,[{line_id:'stable-line-a',received_quantity:20}]);
 await button(tree,'关闭').props.onClick();tree=await h.render(()=>Page());await button(tree,'收货差异').props.onClick();tree=await h.render(()=>Page());assert(text(tree).includes('未知')&&text(tree).includes('待核对')&&text(tree).includes('¥20'));assert(!text(tree).includes('多 0'));
 // Render actual matching/history components. Scope changes prevent displaying a delayed photo.
 const rh=hooks();let release;const response=new Promise(r=>release=r);let photoHeaders;
 const info=compile('components/PurchaseReceiptInfo.tsx',{react:rh.react,'@/lib/api':api,'@/lib/currency':money},{fetch:async(_url,options)=>{photoHeaders=options.headers;return response;},URL:{createObjectURL:()=> 'blob:synthetic',revokeObjectURL(){}}});
 const state={...order,receipt_baseline:{source:'legacy_recorded_fields',note:'真实旧累计，不造批次'},receipt_batches:[{id:7,items:[{line_id:'a',product_name:'材料',quantity:80,unit:'件'}],operator_name:'合成操作人',received_at:'2026-10-26T03:00:00Z',request_key:'k7',remark:'第一批'}]};
 let history=await rh.render(()=>info.ReceiptHistory({order:state}));assert(text(history).includes('本次 80件'));const pending=button(history,'查看批次7照片').props.onClick();local.setItem('activeWarehouseId','1');release({ok:true,blob:async()=>new Blob(['synthetic'],{type:'image/png'})});await pending;history=await rh.render(()=>info.ReceiptHistory({order:state}));assert.equal(photoHeaders['X-Warehouse-ID'],'2');assert(text(history).includes('账号、仓库或采购单已变化'));assert(!walk(history).some(x=>x.type==='img'));
 const m=info.ThreeWayMatch({value:{kind_label:'商品采购',status:'different',quantity_match:'unknown',receipt_quantity_match:'different',amount_match:'matched',line_amount_match:'unknown',policy:{strict:false},review_status:'stale',notes:['无结构化行，未知不猜配'],review:{operator_name:'老板',confirmed_at:'2026-10-26T03:00:00Z',reason:'核实旧单',snapshot_hash:'local-snapshot'}}});
 assert(text(m).includes('依据未知')&&text(m).includes('复核已失效')&&text(m).includes('泰国时间')&&text(m).includes('严格校验未开启'));

 const ph=hooks(),putReviews=[],reviewBill={id:7,supplier_id:1,bill_number:'REVIEW-7',currency:'THB',amount:1000,paid_amount:0,remaining_amount:1000,status:'pending',need_boss_confirm:'true'};
 const reviewApi={...api,api:{get:async url=>url.startsWith('/payable?')?{data:[reviewBill],total:1}:url.startsWith('/payable/stats')?{supplier_summary:[]}: {data:[]},put:async(url,body)=>{putReviews.push({url,body});return{message:'saved'};}}};
 const payment=compile('lib/payablePayment.ts',{'@/lib/api':reviewApi},{localStorage:local,sessionStorage:session,crypto:{randomUUID:()=>`review-${++seq}`}});
 const Payable=compile('app/(dashboard)/payable/page.tsx',{...imports,react:ph.react,'@/lib/api':reviewApi,'@/lib/payablePayment':payment,'@/components/WalletAccountSelect':{__esModule:true,default:()=>null},'@/components/PayableDetail':{__esModule:true,default:()=>null}},{window:{location:{search:''}},localStorage:local,sessionStorage:session,URLSearchParams}).default;
 let payable=await ph.render(()=>Payable());const table=walk(payable).find(x=>x.props?.columns);assert(table);
 const actions=table.props.columns.find(x=>x.label==='操作').render(null,reviewBill);await button(actions,'确认').props.onClick();payable=await ph.render(()=>Payable());
 assert(walk(payable).some(x=>x.props?.role==='dialog'&&x.props['aria-label']==='匹配复核'));
 await button(payable,'保存本次复核').props.onClick();assert.equal(putReviews.length,0);
 const reason=walk(walk(payable).find(x=>x.props?.role==='dialog'&&x.props['aria-label']==='匹配复核')).find(x=>x.type==='textarea');reason.props.onChange({target:{value:'原始凭据已核实，少20件待补收'}});
 payable=await ph.render(()=>Payable());await button(payable,'保存本次复核').props.onClick();assert.equal(putReviews.length,1);assert.equal(putReviews[0].url,'/payable/7/confirm');assert.equal(putReviews[0].body.reason,'原始凭据已核实，少20件待补收');
 // R9: an old context arriving after a warehouse switch must not reopen old receipt data.
 local.setItem('activeWarehouseId','2');tree=await h.render(()=>Page());
 await button(tree,'收货验收').props.onClick();tree=await h.render(()=>Page());
 const priorGet=api.api.get;let releaseContext;api.api.get=async url=>url.startsWith('/supplier-controls/orders/')?new Promise(r=>releaseContext=r):priorGet(url);
 const oldOpen=button(tree,'登记本次收货').props.onClick();await tick();local.setItem('activeWarehouseId','1');tree=await h.render(()=>Page());
 releaseContext({creator_id:1,operator_id:1,policy_version:'a'.repeat(64),business_version:'b'.repeat(64),needs_exception:false,unknown_creator:false});await oldOpen;
 tree=await h.render(()=>Page());assert(!walk(tree).some(x=>x.props?.role==='dialog'&&x.props['aria-label']==='登记本次收货'));api.api.get=priorGet;
 console.log('PASS: actual receipt page rejects decimals without truncation, line IDs stay distinct, unknown response retry reuses request, 80+20=100 in two events, scope headers correct; actual matching/history render unknown and stale review, private photo request cannot display after warehouse switch; in-page review dialog rejects empty reason and sends exact current reason');
})().catch(e=>{console.error(e);process.exitCode=1;});
