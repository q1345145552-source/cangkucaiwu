// Execute the actual new components and registration transport with synthetic responses.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript'),React=require('react'),{File}=require('node:buffer');
const compile=(file,imports={},extra={})=>{const m={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src',file),'utf8'),{fileName:file,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module:m,exports:m.exports,require:n=>imports[n]||(require(n)),console,Date,Intl,setInterval:()=>0,clearInterval:()=>{},process:{env:{}},...extra});return m.exports;};
const walk=x=>!x||typeof x!=='object'?[]:Array.isArray(x)?x.flatMap(walk):[x,...walk(x.props?.children)];
const text=x=>x==null||typeof x==='boolean'?'':typeof x!=='object'?String(x):Array.isArray(x)?x.map(text).join(''):text(x.props?.children);
const tick=()=>new Promise(r=>setTimeout(r,0));
function hooks(){let state=[],refs=[],deps=[],effects=[],clean=[],si=0,ri=0,ei=0;return{react:{...React,useState(v){const i=si++;if(!(i in state))state[i]=typeof v==='function'?v():v;return[state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];},useRef(v){const i=ri++;return refs[i]||(refs[i]={current:v});},useEffect(fn,d){const i=ei++,key=JSON.stringify(d);if(deps[i]!==key){deps[i]=key;effects.push(()=>{clean[i]?.();clean[i]=fn();});}}},async render(fn){for(let i=0;i<12;i++){si=ri=ei=0;const t=fn();if(!effects.length)return t;effects.splice(0).forEach(f=>f());await tick();}throw Error('effects did not settle');}};}
const mem=()=>{const d=new Map();return{getItem:k=>d.get(k)||null,setItem:(k,v)=>d.set(k,v),removeItem:k=>d.delete(k),d};};
const by=(t,label)=>{const e=walk(t).find(x=>x.props?.['aria-label']===label);assert(e,'missing '+label);return e;};
const button=(t,label)=>{const e=walk(t).find(x=>x.type==='button'&&text(x)===label);assert(e,'missing '+label);return e;};

const local=mem(),session=mem();let wh='1',uid=1,seq=0,timer;
local.setItem('user',JSON.stringify({id:uid,warehouse_id:1}));
class ApiError extends Error{constructor(status,detail){super(typeof detail==='string'?detail:detail.message);this.status=status;this.detail=detail;}}
const api={ApiError,getActiveWarehouseId:()=>wh,warehouseRequestHeaders:()=>({'X-Warehouse-ID':wh,Authorization:'Bearer synthetic'})};
let transport,downloads=0,revoked=0;
const response=(value,status=200,type='application/json')=>({ok:status>=200&&status<300,status,headers:{get:()=>type},text:async()=>typeof value==='string'?value:JSON.stringify(value),blob:async()=>new Blob([value])});
const excel=compile('lib/excelImport.ts',{'@/lib/api':api},{localStorage:local,fetch:(...args)=>transport(...args),URL:{createObjectURL:()=> 'blob:synthetic',revokeObjectURL:()=>revoked++},document:{createElement:()=>({click:()=>downloads++})}});
const reg=compile('lib/registrationRequest.ts',{'@/lib/api':api},{localStorage:local,sessionStorage:session,crypto:{randomUUID:()=>`excel-test-${++seq}`}});
const modal=h=>compile('components/ExcelImportDialog.tsx',{react:h.react,'@/lib/api':api,'@/lib/excelImport':excel,'@/lib/registrationRequest':reg},{FormData,setInterval:fn=>{timer=fn;return 1;},clearInterval(){},fetch:(...args)=>transport(...args)}).default;
const pre={mode:'preview',preview_version:'v1',valid:true,rows:[{row_number:2,amount:200,currency:'THB',account_id:1}],errors:[],message:'预览成功，尚未登记到账'};
const file=new File(['synthetic bytes'],'receipt.xlsx',{lastModified:42});
let checks=[];const pass=x=>checks.push(x);
(async()=>{
 for(const status of [401,403,500]){transport=async()=>response({detail:{message:'合成错误'}},status);await assert.rejects(excel.downloadExcel('/incoming/template','template.xlsx'),/合成错误/);assert.equal(downloads,0);}
 transport=async()=>response('html error',200,'text/html');await assert.rejects(excel.downloadExcel('/incoming/template','template.xlsx'),/响应类型异常/);
 transport=async()=>response('bad bytes',200,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');await assert.rejects(excel.downloadExcel('/incoming/template','template.xlsx'),/内容异常/);
 transport=async()=>response('PK synthetic',200,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');await excel.downloadExcel('/incoming/template','template.xlsx');assert.equal(downloads,1);assert.equal(revoked,1);pass('401/403/500, wrong content type and non-Excel bytes never download; valid workbook revokes its URL');
 assert.throws(()=>excel.checkExcel(new File(['old'],'old.xls')),/另存为/);assert.throws(()=>excel.checkExcel(new File([],'empty.xlsx')),/非空/);
 assert.throws(()=>excel.checkExcel(new File([new Uint8Array(2*1024*1024+1)],'large.xlsx')),/2MB/);pass('file validation rejects xls, empty and oversized files');
 await assert.rejects(excel.excelResponse(response({detail:{message:'失败',errors:[{row_number:3,message:'账户币种不一致'}]}},422)),/第3行/);
 await assert.rejects(excel.excelResponse(response('<html>error</html>',500)),/HTTP 500/);pass('object/row errors and non-JSON failures remain understandable');
 let calls=[],saved=new Map(),lost=true,done=0;
 transport=async(url,options)=>{const mode=options.body.get('mode'),key=options.body.get('request_key');calls.push({mode,key,version:options.body.get('preview_version'),file:await options.body.get('file').text()});
 if(mode==='preview')return response(pre);
 if(!saved.has(key))saved.set(key,{id:key,mode:'confirmed',imported:1,errors:[],message:'已保存1条'});
 if(lost){lost=false;throw Error('synthetic response lost');}return response(saved.get(key));};
 const h=hooks(),Modal=modal(h),props={file,endpoint:'/incoming/import-excel',title:'合成到账',onClose(){},onImported(){done++;}},render=()=>Modal(props);
 let tree=await h.render(render);assert.equal(calls.length,1);assert(button(tree,'确认整批保存').props.disabled);assert(text(tree).includes('收款账户编号'));
 walk(tree).find(x=>x.type==='input'&&x.props.type==='checkbox').props.onChange({target:{checked:true}});tree=await h.render(render);
 await Promise.all([button(tree,'确认整批保存').props.onClick(),button(tree,'确认整批保存').props.onClick()]);tree=await h.render(render);assert.equal(calls.length,2);assert(text(tree).includes('保存结果待确认'));
 await button(tree,'原请求重试').props.onClick();assert.equal(saved.size,1);assert.equal(done,1);assert.deepEqual(calls[1],calls[2]);pass('actual modal preview/ack, double click guard, lost response and original-request retry save exactly once');
 transport=async()=>response({...pre,valid:false,errors:[{row_number:3,message:'账户不属于当前仓库'}]});const invalid=hooks(),Bad=modal(invalid);tree=await invalid.render(()=>Bad(props));assert(text(tree).includes('第3行：账户不属于当前仓库'));assert(button(tree,'确认整批保存').props.disabled);pass('row failure details render and prevent whole-batch confirmation');
 let incomplete=true;transport=async(_url,o)=>o.body.get('mode')==='preview'?response(pre):response(incomplete?{id:'synthetic',mode:'confirmed',imported:0,errors:[]}:{id:'synthetic',mode:'confirmed',imported:1,errors:[]});const zero=hooks(),Zero=modal(zero);tree=await zero.render(()=>Zero(props));walk(tree).find(x=>x.type==='input'&&x.props.type==='checkbox').props.onChange({target:{checked:true}});tree=await zero.render(()=>Zero(props));await button(tree,'确认整批保存').props.onClick();tree=await zero.render(()=>Zero(props));assert(text(tree).includes('未取得完整保存结果'));assert(text(tree).includes('保存结果待确认'));incomplete=false;await button(tree,'原请求重试').props.onClick();pass('HTTP 200 with zero saved rows never reports success and retains original-request retry');
 transport=async()=>response(pre);const sw=hooks(),Switch=modal(sw);tree=await sw.render(()=>Switch(props));wh='2';timer();tree=await sw.render(()=>Switch(props));assert(text(tree).includes('仓库或账号已切换'));assert(button(tree,'确认整批保存').props.disabled);wh='1';
 const user=hooks(),User=modal(user);tree=await user.render(()=>User(props));local.setItem('user',JSON.stringify({id:2,warehouse_id:1}));timer();tree=await user.render(()=>User(props));assert(button(tree,'确认整批保存').props.disabled);pass('warehouse and account switches invalidate existing preview and confirmation');
 local.setItem('user',JSON.stringify({id:1,warehouse_id:1}));let reads=0;transport=async()=>{reads++;return response(pre);};const reselect=hooks(),Again=modal(reselect);await reselect.render(()=>Again(props));const again=hooks(),Same=modal(again);await again.render(()=>Same(props));assert.equal(reads,2);pass('same File can be previewed again after modal close; parent inputs reset on selection');
 console.log(JSON.stringify({passed:checks.length,checks},null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
