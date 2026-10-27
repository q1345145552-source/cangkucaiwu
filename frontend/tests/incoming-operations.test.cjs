// Execute the actual page and submission state machine, including reload recovery.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const ts=require('typescript'),React=require('react');
const root=path.resolve(__dirname,'../src');
function compile(file,imports,globals={}) {
 const m={exports:{}};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(root,file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,
  {module:m,exports:m.exports,require:n=>imports[n]||(n==='@/components/ExcelImportDialog'?{__esModule:true,default:()=>null}:n==='@/lib/excelImport'?compile('lib/excelImport.ts',imports,{process:{env:{}}}):require(n)),Date,JSON,Number,Promise,URLSearchParams,FormData,Blob,console,...globals});
 return m.exports;
}
const submission=compile('lib/incomingSubmission.ts',{});
const walk=x=>!x||typeof x!=='object'?[]:Array.isArray(x)?x.flatMap(walk):[x,...walk(x.props?.children)];
const text=x=>x==null||typeof x==='boolean'?'':typeof x!=='object'?String(x):Array.isArray(x)?x.map(text).join(''):text(x.props?.children);
const find=(tree,p)=>{const n=walk(tree).find(p);assert(n,'Missing node');return n;};
const button=(tree,name)=>find(tree,n=>n.type==='button'&&text(n).trim()===name);
function field(tree,label) {
 const parent=find(tree,n=>Array.isArray(n.props?.children)&&n.props.children.some(c=>c?.type==='label'&&text(c)===label));
 return find(parent,n=>n.type==='input'||n.type==='select');
}
const change=(node,value)=>node.props.onChange({target:{value}});

function server() {
 const rows=[],keys=new Map(),writes=[],reads=[],uploads=[],flags={uploadFail:false,dropCreateResponse:false,lookupOffline:false,rejectCreate:false};
 function response(data,status=200){return {ok:status===200,status,json:async()=>data,blob:async()=>new Blob(['image'],{type:'image/png'})};}
 return {rows,keys,writes,reads,uploads,flags,async fetch(url,options={}){
  const route=url.replace('/api/v1','');reads.push({route,method:options.method||'GET',headers:options.headers});
  if(route==='/incoming'&&options.method==='POST') {
   const payload=JSON.parse(options.body);writes.push(payload);
   if(flags.rejectCreate)return response({detail:'请选择付款或收款账户'},400);
   let row=keys.get(payload.request_key);
   if(!row){row={...payload,id:rows.length+1,has_screenshot:false,entrant_name:'测试老板'};rows.push(row);keys.set(payload.request_key,row);}
   if(flags.dropCreateResponse)throw new TypeError('simulated response lost');
   return response(row);
  }
  if(route.startsWith('/incoming/by-request/')){
   if(flags.lookupOffline)throw new TypeError('simulated lookup offline');
   const row=keys.get(route.split('/').pop());return row?response(row):response({detail:'尚未找到本次到账'},404);
  }
  if(/^\/incoming\/\d+\/screenshot$/.test(route)){
   const row=rows.find(r=>r.id===+route.split('/')[2]);assert(row);
   if(options.method==='POST'){
    uploads.push({id:row.id,headers:options.headers});
    if(flags.uploadFail)return response({detail:'截图保存失败；到账已入账，请仅补传截图'},500);
    row.has_screenshot=true;return response({id:row.id,has_screenshot:true});
   }
   return response({});
  }
  throw Error('Unexpected request '+route);
 }};
}

function harness(s,storage=new Map([['user',JSON.stringify({id:1,warehouse_id:1})]])) {
 let state=[],refs=[],deps=[],effects=[],index=0,ri=0,ei=0;
 const messages=[];
 const react={...React,useState(initial){const i=index++;if(!(i in state))state[i]=typeof initial==='function'?initial():initial;return[state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];},
 useRef(initial){const i=ri++;return refs[i]||(refs[i]={current:initial});},useEffect(fn,values){const i=ei++,key=JSON.stringify(values);if(deps[i]!==key){deps[i]=key;effects.push(fn);}}};
 const WalletAccountSelect=()=>null,DataTable=()=>null;
 const api={get:async route=>route.startsWith('/customers')?{data:[{id:1,company_name:'测试客户'}]}:{data:s.rows,total:s.rows.length}};
 let nextKey=0;
 const mod=compile('app/(dashboard)/incoming/page.tsx',{
  react,'@/components/WalletAccountSelect':{__esModule:true,default:WalletAccountSelect},'@/components/common/DataTable':{__esModule:true,default:DataTable},
  '@/lib/incomingSubmission':submission,'@/lib/api':{api,getToken:()=> 'synthetic-token',getActiveWarehouseId:()=> '1'},
  '@/components/ui/Toast':{useToast:()=>({toast:(...args)=>messages.push(args)})},'next/navigation':{useRouter:()=>({push(){}})},
 },{process:{env:{}},fetch:s.fetch.bind(s),crypto:{randomUUID:()=>`request-${Date.now()}-${++nextKey}`},
  localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},URL:{createObjectURL:()=> 'blob:synthetic-image',revokeObjectURL(){}},
 });
 return {storage,messages,WalletAccountSelect,DataTable,async render(){await new Promise(r=>setTimeout(r,0));for(let i=0;i<20;i++){index=ri=ei=0;const tree=mod.default();if(!effects.length)return tree;effects.splice(0).forEach(fn=>fn());await new Promise(r=>setTimeout(r,0));}throw Error('Effects did not settle');}};
}
async function fill(h) {
 let tree=await h.render();change(field(tree,'金额'),'1000');tree=await h.render();change(field(tree,'付款方'),'1');tree=await h.render();
 find(tree,n=>n.type===h.WalletAccountSelect).props.onChange(1);return h.render();
}
function selectScreenshot(tree) {
 const input=find(tree,n=>n.type==='input'&&n.props.type==='file'&&!n.props['aria-label']);
 input.props.onChange({target:{files:[new Blob(['photo'],{type:'image/png'})]}});
}

(async()=>{
 // Screenshot failure happens after money is saved. Reload can only resume that record.
 let s=server(),h=harness(s),tree=await fill(h);s.flags.uploadFail=true;selectScreenshot(tree);tree=await h.render();
 await button(tree,'录入').props.onClick();tree=await h.render();
 assert.equal(s.rows.length,1);assert.equal(s.writes.length,1);assert.equal(s.writes[0].customer_id,1);assert(text(tree).includes('到账 #1 已入账，截图待补传'));
 assert(h.messages.some(m=>m[1].includes('已入账')&&m[1].includes('仅补传截图')));
 assert(find(tree,n=>n.type==='fieldset').props.disabled);
 const stored=JSON.parse(h.storage.get('incoming-operation:1:1'));assert.equal(stored.savedId,1);
 h=harness(s,h.storage);tree=await h.render();assert(text(tree).includes('到账 #1 已入账'));
 selectScreenshot(tree);tree=await h.render();s.flags.uploadFail=false;
 await button(tree,'补传截图').props.onClick();tree=await h.render();
 assert.equal(s.writes.length,1);assert.equal(s.rows.length,1);assert(s.rows[0].has_screenshot);
 assert.equal(h.storage.has('incoming-operation:1:1'),false);
 assert(s.uploads.every(u=>u.headers['X-Warehouse-ID']==='1'));
 // An explicitly independent new payment of the same amount is allowed.
 tree=await fill(h);await button(tree,'录入').props.onClick();assert.equal(s.rows.length,2);assert.equal(s.rows.reduce((n,r)=>n+r.amount,0),2000);
 assert.notEqual(s.writes[0].request_key,s.writes[1].request_key);

 // Lost create response and unavailable lookup retain the operation identifier across reload.
 s=server();h=harness(s);tree=await fill(h);s.flags.dropCreateResponse=true;s.flags.lookupOffline=true;
 await button(tree,'录入').props.onClick();assert.equal(s.rows.length,1);const key=s.writes[0].request_key;
 s.flags.dropCreateResponse=false;s.flags.lookupOffline=false;
 h=harness(s,h.storage);tree=await h.render();assert(text(tree).includes('到账 #1 已入账'));
 await button(tree,'完成本次').props.onClick();assert.equal(s.writes.length,1);
 assert.equal(s.rows[0].request_key,key);

 // Double click cannot start two page requests; backend tests separately cover independent concurrent clients.
 s=server();h=harness(s);tree=await fill(h);const submit=button(tree,'录入').props.onClick;
 await Promise.all([submit(),submit()]);assert.equal(s.writes.length,1);assert.equal(s.rows.length,1);

 // Known validation rejection leaves editable fields; ambiguous failures retain their original operation.
 s=server();h=harness(s);tree=await fill(h);s.flags.rejectCreate=true;await button(tree,'录入').props.onClick();tree=await h.render();
 assert.equal(s.rows.length,0);assert.equal(h.storage.has('incoming-operation:1:1'),false);assert(!find(tree,n=>n.type==='fieldset').props.disabled);

 // Existing rows upload by receipt ID, never call the recharge attachment route or create another income.
 s=server();h=harness(s);tree=await fill(h);await button(tree,'录入').props.onClick();tree=await h.render();
 const table=find(tree,n=>n.type===h.DataTable);const screenshot=table.props.columns.find(c=>c.key==='has_screenshot').render(false,s.rows[0]);
 button(screenshot,'补传截图').props.onClick();tree=await h.render();
 const hidden=find(tree,n=>n.props?.['aria-label']==='补传到账截图');
 await hidden.props.onChange({target:{files:[new Blob(['photo'])],value:'chosen'}});await new Promise(r=>setTimeout(r,0));
 assert.equal(s.writes.length,1);assert.equal(s.uploads.length,1);assert(s.rows[0].has_screenshot);
 assert(!s.reads.some(r=>r.route.includes('recharge-screenshot')));
 console.log('PASS: actual incoming page, screenshot-failure states, reload recovery, original request identifiers, double click, separate same-amount income, validation recovery, existing-row attachment and warehouse header');
})().catch(error=>{console.error(error);process.exitCode=1;});
