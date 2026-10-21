// Execute the actual legacy page handlers and source renderer, including authorised exports.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const React=require('react'),ts=require('typescript');
const walk=x=>!x||typeof x!=='object'?[]:Array.isArray(x)?x.flatMap(walk):[x,...walk(x.props?.children)];
const text=x=>x==null||typeof x==='boolean'?'':typeof x!=='object'?String(x):Array.isArray(x)?x.map(text).join(''):text(x.props?.children);
const wait=()=>new Promise(r=>setTimeout(r,0));
function harness(){
 let state=[],refs=[],deps=[],cleanups=[],effects=[],index=0,ri=0,ei=0;
 const reads=[],exports=[],downloads=[],messages=[],flags={fail:false};
 const react={...React,useState(initial){const i=index++;if(!(i in state))state[i]=typeof initial==='function'?initial():initial;return[state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];},
 useRef(initial){const i=ri++;return refs[i]||(refs[i]={current:initial});},
 useEffect(fn,d){const i=ei++,key=JSON.stringify(d);if(deps[i]!==key){deps[i]=key;effects.push(()=>{cleanups[i]?.();cleanups[i]=fn();});}}};
 const rows=[{id:'incoming-1',amount:1000,currency:'THB',source:'incoming',source_label:'到账流水',ref_no:'FL-1',source_link:'/incoming',is_read_only:true},
 {id:1,amount:200,currency:'THB',source:'manual',source_label:'手工收入',ref_no:'IN-1',source_link:'',is_read_only:false}];
 const DataTable=()=>null;
 const api={async get(route){reads.push(route);
  if(route.includes('monthly-summary'))return{income_by_currency:{THB:1200},expense_by_currency:{THB:300},net:900};
  if(route.includes('categories')||route==='/accounts')return{data:[]};
  return{data:route.includes('/expense?')?[{id:3,amount:300,currency:'THB'}]:rows,total:route.includes('/expense?')?1:2};}};
 const imports={react,'@/lib/api':{api,getToken:()=> 'synthetic-test-token',getActiveWarehouseId:()=> '1'},
 '@/lib/manualWallet':{pendingWalletOperation:()=>null,submitWalletOperation:async()=>({})},
 '@/hooks/useAuth':{useAuth:()=>({user:{role:'warehouse_admin'}})},'@/hooks/useI18n':{useI18n:()=>({t:k=>k})},
 '@/components/ui/Toast':{useToast:()=>({toast:(...args)=>messages.push(args)})},'@/components/common/DataTable':{__esModule:true,default:DataTable},
 '@/lib/currency':{fmtMoney:(n,c)=>`${c} ${n}`,fmtMoneyByCurrency:v=>JSON.stringify(v)},'next/navigation':{useRouter:()=>({push(){}})}};
 const mod={exports:{}};
 const src=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/app/(dashboard)/income-expense/page.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 vm.runInNewContext(src,{module:mod,exports:mod.exports,require:n=>n==='@/components/InternalTransferSummary'?{__esModule:true,default:()=>null}:imports[n]||require(n),Date,Set,Promise,process:{env:{}},console,
  URL:{createObjectURL:()=> 'blob:isolated-test',revokeObjectURL:url=>assert.equal(url,'blob:isolated-test')},
  document:{createElement:()=>{const a={click(){downloads.push({href:a.href,download:a.download});}};return a;}},
  fetch:async(url,options)=>{exports.push({url,headers:options.headers});return{ok:!flags.fail,json:async()=>({detail:'无此操作权限'}),blob:async()=>({})};}});
 return{reads,exports,downloads,messages,flags,DataTable,async render(){await wait();for(let i=0;i<20;i++){index=ri=ei=0;const tree=mod.exports.default();if(!effects.length)return tree;effects.splice(0).forEach(fn=>fn());await wait();}throw Error('Unsettled effects');}};
}
(async()=>{
 const h=harness();let tree=await h.render();
 assert(text(tree).includes('公司钱包实际收付款，内部转账不计收支'));assert(text(tree).includes('收入: {"THB":1200}'));
 const table=walk(tree).find(n=>n.type===h.DataTable);assert.equal(table.props.data.length,2);
 const source=table.props.columns.find(c=>c.key==='ref_no');assert(source);
 const incoming=source.render('',table.props.data[0]),manual=source.render('',table.props.data[1]);
 assert(text(incoming).includes('到账流水 FL-1'));assert(text(incoming).includes('业务联动，只读'));
 assert.equal(walk(incoming).find(n=>n.type==='a').props.href,'/incoming');
 assert(text(manual).includes('手工收入 IN-1'));assert(!text(manual).includes('只读'));
 for(const kind of['income','expense']){
  if(kind==='expense'){walk(tree).find(n=>n.type==='button'&&text(n)==='付款').props.onClick();tree=await h.render();}
  await walk(tree).find(n=>n.type==='button'&&text(n)==='导出').props.onClick();
  const e=h.exports.at(-1),p=new URL(e.url,'http://test');assert.equal(p.pathname,`/api/v1/income-expense/${kind}/export`);
  const input=walk(tree).filter(n=>n.type==='input'&&n.props.type==='date');
  assert.equal(p.searchParams.get('start_date'),input[0].props.value);assert.equal(p.searchParams.get('end_date'),input[1].props.value);
  assert.equal(e.headers.Authorization,'Bearer synthetic-test-token');assert.equal(e.headers['X-Warehouse-ID'],'1');
  assert(h.downloads.at(-1).download.startsWith('wallet_'+kind+'_'));assert(h.messages.some(m=>m[1]==='导出成功'));
 }
 h.flags.fail=true;await walk(tree).find(n=>n.type==='button'&&text(n)==='导出').props.onClick();
 assert(h.messages.some(m=>m[1]==='无此操作权限'));assert.equal(h.downloads.length,2);
 console.log('PASS: actual page renders company-wallet scope, receipt 1000 + manual 200, source/ID/read-only details and source link; income/expense exports share dates and warehouse/auth headers; denied exports do not download');
})().catch(error=>{console.error(error);process.exitCode=1;});
