// Exercise the real customer/credit pages with retained components still present.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),React=require('react');
const walk=n=>!n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(walk):[n,...walk(n.props?.children)];
const text=n=>n==null||typeof n==='boolean'?'':typeof n!=='object'?String(n):Array.isArray(n)?n.map(text).join(''):text(n.props?.children);
const wait=()=>new Promise(r=>setTimeout(r,0));
const DisabledReceivables=()=>null,DisabledShipments=()=>null,Table=()=>null;
const row={id:1,customer_id:1,customer_name:'测试客户',company_name:'测试客户',credit_limit:10000,current_debt:900,total_shipments:2,total_shipping_cost:900};
function setup(file){
 const state=[],refs=[],deps=[],effects=[],calls=[];let si=0,ri=0,ei=0;
 const react={...React,useState(v){const i=si++;if(!(i in state))state[i]=typeof v==='function'?v():v;return[state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];},useRef(v){const i=ri++;return refs[i]||(refs[i]={current:v});},useEffect(f,d){const i=ei++,k=JSON.stringify(d);if(deps[i]!==k){deps[i]=k;effects.push(f);}}};
 const feature={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync('src/lib/retiredEntries.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText,{module:feature,exports:feature.exports});
 const imports={react,'@/lib/currency':{fmtMoney:()=>''},'@/lib/retiredEntries':feature.exports,'@/hooks/useMenuPermission':{useMenuPermission:()=>true},'@/hooks/useI18n':{useI18n:()=>({t:k=>k})},'@/components/ui/Toast':{useToast:()=>({toast(){}})},'next/navigation':{useRouter:()=>({push(){}})},'@/components/common/DataTable':{__esModule:true,default:Table},'@/components/CustomerReceivable':{__esModule:true,default:DisabledReceivables,ReceivableSummary:()=>null},'@/components/CreditShipments':{__esModule:true,default:DisabledShipments},'@/components/WalletAccountSelect':{__esModule:true,default:()=>null},'@/lib/api':{getToken:()=> 'test',api:{async get(path){calls.push(path);return path.includes('/detail')?{...row,repayments:[],shipments:[]}:{data:[row],total:1};}}}};
 const mod={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{exports:mod.exports,module:mod,require:n=>imports[n]||require(n),Date,console});
 return{calls,async render(){await wait();for(let n=0;n<12;n++){si=ri=ei=0;const t=mod.exports.default();if(!effects.length)return t;effects.splice(0).forEach(f=>f());await wait();}throw Error('unsettled');}};
}
(async()=>{
 const customers=setup('src/app/(dashboard)/customers/page.tsx');let t=await customers.render();const table=walk(t).find(n=>n.type===Table);assert(table);assert(!table.props.columns.some(c=>['total_shipments','total_shipping_cost','receivables'].includes(c.key)));
 const actions=table.props.columns.find(c=>c.key==='id').render(null,row);assert(!text(actions).includes('客户对账'));assert(text(actions).includes('编辑'));assert(text(actions).includes('删除'));assert(walk(t).some(n=>n.type==='button'&&text(n)==='新建客户'));
 const credit=setup('src/app/(dashboard)/credit/page.tsx');t=await credit.render();assert(!walk(t).some(n=>n.type===DisabledShipments||n.type===DisabledReceivables));const detail=walk(t).find(n=>n.type==='tr'&&n.props.onClick);assert(detail);await detail.props.onClick();t=await credit.render();assert(!walk(t).some(n=>n.type===DisabledReceivables));assert(text(t).includes('账期回款登记'));assert(![...customers.calls,...credit.calls].some(p=>p.includes('/receivables')||p.includes('/shipments')));
 console.log('PASS: real customer columns/actions hide receivables and shipment totals; credit list/detail never mount retired entries; customer CRUD and original credit repayment remain');
})().catch(e=>{console.error(e);process.exitCode=1;});
