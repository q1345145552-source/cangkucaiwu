const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript'),React=require('react');
const compile=(file,imports={},extra={})=>{const m={exports:{}};const output=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src',file),'utf8'),{fileName:file,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}});vm.runInNewContext(output.outputText,{module:m,exports:m.exports,require:n=>({'@/lib/procurementControlRequest':'lib/procurementControlRequest.ts','@/components/ProcurementDutyFields':'components/ProcurementDutyFields.tsx','@/components/ProcurementRiskReview':'components/ProcurementRiskReview.tsx'}[n])?compile(({'@/lib/procurementControlRequest':'lib/procurementControlRequest.ts','@/components/ProcurementDutyFields':'components/ProcurementDutyFields.tsx','@/components/ProcurementRiskReview':'components/ProcurementRiskReview.tsx'})[n],imports,extra):['@/components/SkuProductMapping','@/components/ProductImportDialog','@/components/SupplierQuoteEditor','@/components/PurchaseQuotePreview'].includes(n)?{__esModule:true,default:()=>null}:n==='@/components/CostIdentity'?require('./cost-identity-compat.cjs'):n==='@/lib/registrationRequest'&&!imports[n]?{registrationDraft:()=>null,submitRegistration:async(_k,_r,_p,send)=>send('legacy-regression-key')}:imports[n]||require(n),console,URLSearchParams,Date,Intl,process:{env:{}},...extra});return m.exports;};
const walk=x=>!x||typeof x!=='object'?[]:Array.isArray(x)?x.flatMap(walk):[x,...walk(x.props?.children)];
const text=x=>x==null||typeof x==='boolean'?'':typeof x!=='object'?String(x):Array.isArray(x)?x.map(text).join(''):text(x.props?.children);
const tick=()=>new Promise(r=>setTimeout(r,0));
function storage(){const d=new Map();return{getItem:k=>d.get(k)||null,setItem:(k,v)=>d.set(k,v),removeItem:k=>d.delete(k),d};}
function hooks(){const state=[],refs=[],deps=[],effects=[],cleanups=[];let si=0,ri=0,ei=0;return{
  react:{...React,useState(v){const i=si++;if(!(i in state))state[i]=typeof v==='function'?v():v;return[state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];},useRef(v){const i=ri++;return refs[i]||(refs[i]={current:v});},useEffect(fn,d){const i=ei++,key=JSON.stringify(d);if(deps[i]!==key){deps[i]=key;effects.push(()=>{cleanups[i]?.();cleanups[i]=fn();});}}},
  async render(fn){await tick();for(let n=0;n<12;n++){si=ri=ei=0;const tree=fn();if(!effects.length)return tree;effects.splice(0).forEach(f=>f());await tick();}throw Error('unsettled');}
};}
const money=compile('lib/currency.ts'),local=storage(),session=storage();local.setItem('user',JSON.stringify({id:1,warehouse_id:1}));local.setItem('token','synthetic-token');
let warehouse='1',sequence=0,drop=false,voucherFail=false,rejectStatus=0,calls=[],payments=new Map(),uploads=0;
const realApi=compile('lib/api.ts',{}, {window:{},localStorage:local});
function setWarehouse(id){warehouse=id;local.setItem('activeWarehouseId',id);}setWarehouse('1');
const bill={id:1,bill_number:'OLD-BILL-1',supplier_name:'供应商',amount:1000,paid_amount:0,currency:'THB',status:'pending',need_boss_confirm:'false',purchase_order_id:201,payments:[],remaining_amount:1000,legacy_paid_amount:0,recorded_payment_total:0,warnings:[],voucher_scope:'账单级凭证，不代表某一次逐笔付款'};
const api={getToken:()=> 'synthetic-token',getActiveWarehouseId:()=>warehouse,warehouseRequestHeaders:realApi.warehouseRequestHeaders,api:{async get(url){calls.push({get:url});if(url.startsWith('/payable/stats'))return{month_total_by_currency:{THB:1000},month_paid_by_currency:{THB:bill.paid_amount},month_unpaid_by_currency:{THB:bill.remaining_amount},overdue_by_currency:{THB:0},supplier_summary:[{supplier_id:1,supplier_name:'供应商',currency:'THB',bill_count:1,total_amount:1000,paid_amount:bill.paid_amount,unpaid_amount:bill.remaining_amount,overdue_amount:0}]};if(url.startsWith('/payable/monthly-order'))return{data:[]};if(url.startsWith('/payable?'))return{data:[{...bill}],total:1};if(url.startsWith('/payable/1/detail'))return{...bill};return{data:[]};}}};
api.ApiError=realApi.ApiError;
async function fetcher(url,options){calls.push({url,method:options.method,headers:options.headers,body:options.body});if(url==='/api/v1/payable')return{ok:true,status:200,json:async()=>({id:9})};if(options.method==='PUT'){
 if(rejectStatus)return{ok:false,status:rejectStatus,json:async()=>({detail:'isolated permission revoked'})};
 const query=new URL(url,'http://isolated').searchParams,key=query.get('request_key'),amount=Number(query.get('paid_amount'));
 if(!payments.has(key)){const p={payment_id:payments.size+1,amount,account_id:1};payments.set(key,p);bill.paid_amount+=amount;bill.remaining_amount=1000-bill.paid_amount;bill.status=bill.remaining_amount?'partially_paid':'paid';}
 if(drop){drop=false;throw Error('isolated response lost after commit');}return{ok:true,status:200,json:async()=>payments.get(key)};
 }uploads++;return{ok:!voucherFail,status:voucherFail?500:200,json:async()=>voucherFail?{detail:'isolated upload failure'}:{path:'/uploads/isolated.png'}};}
function transport(){return compile('lib/payablePayment.ts',{'@/lib/api':api},{localStorage:local,sessionStorage:session,crypto:{randomUUID:()=>`supplier-key-${++sequence}`},fetch:fetcher,FormData});}
const button=(tree,label)=>{const n=walk(tree).find(x=>x.type==='button'&&text(x).trim()===label);assert(n,'missing '+label);return n;};
(async()=>{
 let module=transport();drop=true;await assert.rejects(module.submitPayablePayment(1,{paid_amount:300,account_id:1,payment_method:'现金'}),/结果待确认/);
 assert.equal(payments.size,1);const saved=module.pendingPayablePayment(1);assert(saved);
 module=transport();rejectStatus=403;await assert.rejects(module.submitPayablePayment(1,saved.payload));assert.equal(module.pendingPayablePayment(1).key,saved.key);
 rejectStatus=0;await module.submitPayablePayment(1,saved.payload);assert.equal(payments.size,1);assert.equal(module.pendingPayablePayment(1),null);
 const sent=calls.filter(c=>c.method==='PUT');assert.equal(new URL(sent[0].url,'http://t').searchParams.get('request_key'),new URL(sent[1].url,'http://t').searchParams.get('request_key'));
 assert.equal(sent[0].headers['X-Warehouse-ID'],'1');assert.equal(sent[0].headers.Authorization,'Bearer synthetic-token');
 drop=true;await assert.rejects(module.submitPayablePayment(1,{paid_amount:100,account_id:1,payment_method:'现金'}));const count=calls.length;
 await assert.rejects(module.submitPayablePayment(1,{paid_amount:200,account_id:1,payment_method:'现金'}),/结果待确认/);assert.equal(calls.length,count);
 setWarehouse('2');assert.equal(module.pendingPayablePayment(1),null);setWarehouse('1');await module.submitPayablePayment(1,module.pendingPayablePayment(1).payload);
 voucherFail=true;await assert.rejects(module.uploadPayableVoucher(1,new Blob(['proof'])),/upload failure/);const paymentCount=payments.size;voucherFail=false;await module.uploadPayableVoucher(1,new Blob(['proof']));assert.equal(payments.size,paymentCount);
 const oldSet=session.setItem;session.setItem=()=>{throw Error('unavailable');};const requests=calls.length;await assert.rejects(module.submitPayablePayment(2,{paid_amount:1,account_id:1,payment_method:'现金'}),/无法保存/);assert.equal(calls.length,requests);session.setItem=oldSet;
 // Actual PayablePage: successful payment + failed voucher refreshes the row and opens detail, then only retries upload.
 payments=new Map();bill.paid_amount=0;bill.remaining_amount=1000;bill.status='pending';calls=[];uploads=0;
 const h=hooks(),toasts=[],Wallet=()=>null,Detail=()=>null;module=transport();
 const imports={react:h.react,'@/lib/api':api,'@/lib/currency':money,'@/lib/payablePayment':module,'@/hooks/useAuth':{useAuth:()=>({user:{id:1,role:'warehouse_admin'}})},'@/hooks/useMenuPermission':{useMenuPermission:()=>true},'@/hooks/useI18n':{useI18n:()=>({t:k=>k})},'@/components/ui/Toast':{useToast:()=>({toast:(...x)=>toasts.push(x)})},'next/navigation':{useRouter:()=>({push(){}})},'@/components/WalletAccountSelect':{__esModule:true,default:Wallet},'@/components/PayableDetail':{__esModule:true,default:Detail},'@/components/common/DataTable':{__esModule:true,default:()=>null}};
 imports['@/lib/registrationRequest']=compile('lib/registrationRequest.ts',{'@/lib/api':api},{localStorage:local,sessionStorage:session,crypto:{randomUUID:()=>`registration-${++sequence}`}});
 imports['@/components/PayableDuplicateDialog']={__esModule:true,default:()=>null};
 const Page=compile('app/(dashboard)/payable/page.tsx',imports,{window:{location:{search:''}},crypto:{randomUUID:()=>`page-key-${++sequence}`},fetch:fetcher,FormData,localStorage:local,sessionStorage:session}).default;
 let tree=await h.render(()=>Page());assert(text(tree).includes('应付总表（供应商 × 币种）'));assert(text(tree).includes('逾期属于剩余'));
 button(tree,'查看对应明细').props.onClick();tree=await h.render(()=>Page());assert(calls.some(c=>c.get?.startsWith('/payable?')&&c.get.includes('currency=THB')&&c.get.includes('effective_only=true')));
 const table=walk(tree).find(x=>x.props?.columns);const actions=table.props.columns.find(x=>x.label==='操作').render(null,bill);
 button(actions,'付款').props.onClick();tree=await h.render(()=>Page());walk(tree).find(x=>x.type===Wallet).props.onChange(1);
 const amount=walk(tree).find(x=>x.type==='input'&&x.props.className?.includes('text-lg font-semibold'));amount.props.onChange({target:{value:'300'}});
 const fileInput=walk(tree).find(x=>x.type==='input'&&x.props.type==='file');fileInput.props.onChange({target:{files:[new Blob(['proof-A'])]}});
 tree=await h.render(()=>Page());voucherFail=true;await button(tree,'确认付款').props.onClick();tree=await h.render(()=>Page());
 assert.equal(bill.paid_amount,300);assert.equal(bill.remaining_amount,700);assert.equal(payments.size,1);assert.equal(uploads,1);
 assert(toasts.some(x=>x[1].startsWith('付款已记录，凭证上传失败')));assert(walk(tree).some(x=>x.type===Detail&&x.props.billId===1));
 // A's failed file must survive selecting B's file and cancelling B's payment.
 const b={...bill,id:2,bill_number:'B',paid_amount:0,remaining_amount:1000,status:'pending'};
 button(table.props.columns.find(x=>x.label==='操作').render(null,b),'付款').props.onClick();tree=await h.render(()=>Page());
 walk(tree).find(x=>x.type==='input'&&x.props.type==='file').props.onChange({target:{files:[new Blob(['proof-B'])]}});
 tree=await h.render(()=>Page());button(tree,'取消').props.onClick();tree=await h.render(()=>Page());
 voucherFail=false;setWarehouse('2');await button(tree,'仅重传付款凭证').props.onClick();assert.equal(uploads,1);
 setWarehouse('1');local.setItem('user',JSON.stringify({id:2,warehouse_id:1}));await button(tree,'仅重传付款凭证').props.onClick();assert.equal(uploads,1);
 local.setItem('user',JSON.stringify({id:1,warehouse_id:1}));await button(tree,'仅重传付款凭证').props.onClick();assert.equal(uploads,2);assert.equal(payments.size,1);
 const retry=calls.filter(c=>c.url?.includes('/upload-voucher')).at(-1);assert(retry.url.includes('/payable/1/'));assert.equal(retry.headers['X-Warehouse-ID'],'1');assert.equal(await retry.body.get('file').text(),'proof-A');
 // Actual native create request uses B, not the user's primary warehouse A, without JSON Content-Type.
 setWarehouse('2');tree=await h.render(()=>Page());button(tree,'新建账单').props.onClick();tree=await h.render(()=>Page());
 for(const [label,value] of [['账单编号（登记号）','HEADER-B'],['账单日期','2026-10-26'],['到期日期','2026-12-01'],['金额','250']]){
   const group=walk(tree).find(x=>x.type==='div'&&x.props.className==='form-group'&&walk(x.props.children).some(y=>y.type==='label'&&text(y)===label));
   assert(group,label);walk(group).find(x=>x.type==='input').props.onChange({target:{value}});tree=await h.render(()=>Page());
 }
 walk(tree).find(x=>x.type==='input'&&x.props.type==='file').props.onChange({target:{files:[new Blob(['B-manual'])]}});
 tree=await h.render(()=>Page());await walk(tree).findLast(x=>x.type==='button'&&text(x).trim()==='保存').props.onClick();
 const create=calls.findLast(c=>c.url==='/api/v1/payable');assert.equal(create.headers['X-Warehouse-ID'],'2');assert.equal(create.headers['Content-Type'],undefined);setWarehouse('1');
 // Actual read-only detail: currency, historical amount, exact reverse link, and paid/null are shown distinctly.
 const d=hooks();let detailData={...bill,payments:[{id:1,amount:300,currency:'THB',account_name:'现金',paid_at:'2026-10-26T03:00:00+07:00',payment_method:'现金',operator_name:'老板'}],recorded_payment_total:300,legacy_paid_amount:0};
 const DetailPage=compile('components/PayableDetail.tsx',{react:d.react,'@/lib/api':{api:{get:async()=>detailData}},'@/lib/currency':money,'@/components/ProcurementInfo':{billStatus:{partially_paid:'部分付款'}},'@/components/PurchaseReceiptInfo':{ThreeWayMatch:()=>null},'@/lib/payablePayment':module,'@/hooks/useAuth':{useAuth:()=>({user:{role:'warehouse_admin'}})},'@/hooks/useMenuPermission':{useMenuPermission:()=>true},'next/link':{__esModule:true,default:'a'}}).default;
 let rev=0;tree=await d.render(()=>DetailPage({billId:1,revision:rev,onClose(){},onPay(){}}));assert(text(tree).includes('累计已付 ฿300'));assert(text(tree).includes('剩余应付 ฿700'));assert(walk(tree).some(x=>x.props?.href==='/suppliers/purchase-orders/201'));assert(text(tree).includes('账单级凭证'));
 detailData={...detailData,paid_amount:null,remaining_amount:null,legacy_paid_amount:null,warnings:['累计已付未记录']};rev++;tree=await d.render(()=>DetailPage({billId:1,revision:rev,onClose(){},onPay(){}}));assert(text(tree).includes('累计已付 未记录'));assert(text(tree).includes('剩余应付 待核对'));
 const procurement=compile('components/ProcurementInfo.tsx',{'@/lib/currency':money,'next/link':{__esModule:true,default:'a'}});
 assert(text(procurement.PurchaseQuantities({order:{items:[{product_name:'材料',quantity:10}]}})).includes('尚未记录实收'));
 assert(text(procurement.LinkedPayable({order:{bill:null,bill_message:'没有应付读取权限'}})).includes('没有应付读取权限'));
 // Unknown summary and drilled row must not invent paid=0 / remaining=1000.
 bill.paid_amount=null;bill.remaining_amount=null;tree=await h.render(()=>Page());button(tree,'全部账单日期').props.onClick();tree=await h.render(()=>Page());
 assert(text(tree).includes('待核实（已知单据小计'));const unknownTable=walk(tree).find(x=>x.props?.columns);
 assert.equal(text(unknownTable.props.columns.find(x=>x.key==='paid_amount').render(null,bill)),'未记录，待核实');
 // Run SuppliersPage native PDF + receipt handlers with the common real header function in selected B.
 const sh=hooks(),order={id:22,order_number:'B-PO',items:[],total_amount:1000,status:'confirmed',flow_status:'pending_confirmation',bill:null};
 const supplierApi={...api,api:{get:async url=>url.startsWith('/suppliers/purchase-orders/')?order:url.startsWith('/suppliers/purchase-orders')?{data:[order]}:{data:[]}}};
 const SupplierPage=compile('app/(dashboard)/suppliers/page.tsx',{...imports,react:sh.react,'@/lib/api':supplierApi,'@/components/ProcurementInfo':procurement,'@/components/PurchaseReceiptInfo':{ReceiptHistory:()=>null,ThreeWayMatch:()=>null}},{setTimeout,window:{},document:{createElement:()=>({click(){},remove(){}}),body:{appendChild(){}}},URL:{createObjectURL:()=> 'blob:isolated',revokeObjectURL(){}},FormData,fetch:async(url,options)=>{calls.push({url,...options});return{ok:true,json:async()=>({}),blob:async()=>new Blob(['%PDF'])};}}).default;
 setWarehouse('2');tree=await sh.render(()=>SupplierPage());button(tree,'采购单列表').props.onClick();tree=await sh.render(()=>SupplierPage());
 await button(tree,'PDF').props.onClick();tree=await sh.render(()=>SupplierPage());await button(tree,'明细').props.onClick();tree=await sh.render(()=>SupplierPage());
 button(tree,'上传回执').props.onClick();tree=await sh.render(()=>SupplierPage());
 walk(tree).find(x=>x.props?.['aria-label']==='上传采购回执').props.onChange({target:{files:[new Blob(['receipt-B'])]}});await tick();
 for(const suffix of ['/22/pdf','/22/receipt']){const sent=calls.findLast(c=>c.url?.endsWith(suffix));assert(sent,'native '+suffix);assert.equal(sent.headers['X-Warehouse-ID'],'2');assert.equal(sent.headers.Authorization,'Bearer synthetic-token');assert.equal(sent.headers['Content-Type'],undefined);}
 console.log('PASS: real transport unknown-result key recovery, scope and storage failures; actual payable component A-failure/B-file/cancel/A-retry preserves A file and bill with one payment; switched warehouse/user blocks upload; native create/PDF/receipt headers use selected B without JSON Content-Type; null summary/drill/detail explicit; currency/effective drill and exact links');
})().catch(e=>{console.error(e);process.exitCode=1;});
