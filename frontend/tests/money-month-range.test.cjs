// Run the existing page handlers: both list and summary must receive the same dates.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const ts=require('typescript'),React=require('react');
const walk=x=>!x||typeof x!=='object'?[]:Array.isArray(x)?x.flatMap(walk):[x,...walk(x.props?.children)];
const text=x=>x==null||typeof x==='boolean'?'':typeof x!=='object'?String(x):Array.isArray(x)?x.map(text).join(''):text(x.props?.children);
const wait=()=>new Promise(r=>setTimeout(r,0));
function harness(){
 let state=[],refs=[],deps=[],cleanups=[],effects=[],index=0,ri=0,ei=0;const reads=[],held=[];const flags={holdStart:null};
 const react={...React,useState(initial){const i=index++;if(!(i in state))state[i]=typeof initial==='function'?initial():initial;return[state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];},
 useRef(initial){const i=ri++;return refs[i]||(refs[i]={current:initial});},
 useEffect(fn,values){const i=ei++,key=JSON.stringify(values);if(deps[i]!==key){deps[i]=key;effects.push(()=>{cleanups[i]?.();cleanups[i]=fn();});}}};
 const DataTable=()=>null;
 const api={async get(route){reads.push(route);const url=new URL(route,'http://test');
  if(url.pathname.includes('categories')||url.pathname==='/accounts')return{data:[]};
  if(flags.holdStart===url.searchParams.get('start_date'))await new Promise(resolve=>held.push(resolve));
  const sept=url.searchParams.get('start_date')==='2026-09-01',amount=sept?200:300;
  if(url.pathname.endsWith('monthly-summary'))return{income_by_currency:{},expense_by_currency:{THB:amount},net:-amount};
  return{data:[{id:sept?1:2,amount,currency:'THB',remark:sept?'SEPTEMBER-200':'OCTOBER-300'}],total:1};}};
 const mod={exports:{}};
 const src=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/app/(dashboard)/income-expense/page.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const imports={react,'@/lib/api':{api,getToken:()=> 'synthetic-token'},'@/hooks/useAuth':{useAuth:()=>({user:{id:1,role:'warehouse_admin'}})},
 '@/lib/manualWallet':{pendingWalletOperation:()=>null,submitWalletOperation:async()=>({})},
 '@/hooks/useI18n':{useI18n:()=>({t:k=>k})},'@/components/ui/Toast':{useToast:()=>({toast(){}})},
 '@/components/common/DataTable':{__esModule:true,default:DataTable},'@/lib/currency':{fmtMoney:(v,c)=>`${c} ${v}`,fmtMoneyByCurrency:v=>JSON.stringify(v)},
 'next/navigation':{useRouter:()=>({push(){}})}};
 vm.runInNewContext(src,{module:mod,exports:mod.exports,require:n=>imports[n]||require(n),Date,Set,URL,console});
 return{reads,DataTable,flags,held,async render(){await wait();for(let n=0;n<20;n++){index=ri=ei=0;const tree=mod.exports.default();if(!effects.length)return tree;effects.splice(0).forEach(fn=>fn());await wait();}throw Error('Unsettled effects');}};
}
(async()=>{
 const h=harness();let tree=await h.render();
 walk(tree).find(n=>n.type==='button'&&text(n)==='付款').props.onClick();tree=await h.render();
 for(const [start,end,amount]of[['2026-09-01','2026-09-30',200],['2026-10-01','2026-10-31',300]]){
  // Move to a later page first; changing dates must reset pagination.
  walk(tree).find(n=>n.type===h.DataTable).props.onPageChange(4);tree=await h.render();
  let inputs=walk(tree).filter(n=>n.type==='input'&&n.props.type==='date');
  inputs[1].props.onChange({target:{value:end}});tree=await h.render();
  inputs=walk(tree).filter(n=>n.type==='input'&&n.props.type==='date');
  inputs[0].props.onChange({target:{value:start}});tree=await h.render();
  const table=walk(tree).find(n=>n.type===h.DataTable);assert.equal(table.props.page,1);
  assert.equal(table.props.data[0].amount,amount);assert(text(tree).includes(`支出: {"THB":${amount}}`));
  for(const prefix of['/income-expense/expense?','/income-expense/monthly-summary?']){
   const route=h.reads.filter(r=>r.startsWith(prefix)).at(-1),p=new URL(route,'http://test').searchParams;
   assert.equal(p.get('start_date'),start);assert.equal(p.get('end_date'),end);
   if(prefix.includes('/expense?'))assert.equal(p.get('page'),'1');
  }
 }
 assert.equal(walk(tree).filter(n=>n.type==='input'&&n.props.type==='date').length,2);
 // A slow September response arriving after October must never overwrite October's list or total.
 h.flags.holdStart='2026-09-01';
 walk(tree).find(n=>n.type==='input'&&n.props.type==='date').props.onChange({target:{value:'2026-09-01'}});tree=await h.render();
 assert.equal(h.held.length,2);
 walk(tree).find(n=>n.type==='input'&&n.props.type==='date').props.onChange({target:{value:'2026-10-01'}});tree=await h.render();
 assert.equal(walk(tree).find(n=>n.type===h.DataTable).props.data[0].amount,300);
 h.flags.holdStart=null;h.held.splice(0).forEach(resolve=>resolve());tree=await h.render();
 assert.equal(walk(tree).find(n=>n.type===h.DataTable).props.data[0].amount,300);
 assert(text(tree).includes('支出: {"THB":300}'));
 console.log('PASS: actual income/expense page sends identical full-month dates to list and summary, resets pagination, renders September 200 / October 300, and ignores late stale responses without changing its layout');
})().catch(error=>{console.error(error);process.exitCode=1;});
