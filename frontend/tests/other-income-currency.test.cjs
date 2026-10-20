// Execute the real page and currency formatter. Financial writes/filters are also tested on native PostgreSQL.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const React=require('react'),ts=require('typescript');
const walk=x=>!x||typeof x!=='object'?[]:Array.isArray(x)?x.flatMap(walk):[x,...walk(x.props?.children)];
const text=x=>x==null||typeof x==='boolean'?'':typeof x!=='object'?String(x):Array.isArray(x)?x.map(text).join(''):text(x.props?.children);
const find=(tree,p)=>{const n=walk(tree).find(p);assert(n,'Missing node');return n;};
const button=(tree,label)=>find(tree,n=>n.type==='button'&&text(n).trim()===label);
const field=(tree,label)=>find(find(tree,n=>Array.isArray(n.props?.children)&&n.props.children.some(c=>c?.type==='label'&&text(c)===label)),n=>n.type==='input'||n.type==='select');
const change=(node,value)=>node.props.onChange({target:{value}});
const wait=()=>new Promise(r=>setTimeout(r,0));
function compile(file,imports,globals={}){const m={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module:m,exports:m.exports,require:n=>imports[n]||require(n),console,...globals});return m.exports;}
const currency=compile('../src/lib/currency.ts',{});
function harness(){
 let state=[],refs=[],deps=[],cleanups=[],effects=[],si=0,ri=0,ei=0;
 const reads=[],writes=[],exports=[],downloads=[],messages=[],held=[],flags={holdCurrency:null,denyExport:false};
 const rows=[{id:1,amount:100,currency:'THB',category_id:1,account_id:1,income_date:'2026-10-20',remark:'THB-100'},
  {id:2,amount:200,currency:'CNY',category_id:1,account_id:3,income_date:'2026-10-20',remark:'CNY-200'}];
 const accounts=[{id:1,currency:'THB',account_name:'现金',status:'active'},{id:3,currency:'CNY',account_name:'人民币现金',status:'active'},
  {id:4,currency:'CNY',account_name:'停用',status:'inactive'}];
 const react={...React,useState(initial){const i=si++;if(!(i in state))state[i]=typeof initial==='function'?initial():initial;return[state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];},
 useRef(initial){const i=ri++;return refs[i]||(refs[i]={current:initial});},useEffect(fn,d){const i=ei++,key=JSON.stringify(d);if(deps[i]!==key){deps[i]=key;effects.push(()=>{cleanups[i]?.();cleanups[i]=fn();});}}};
 const api={async get(route){reads.push(route);if(route==='/accounts')return{data:accounts};if(route.includes('/categories'))return{data:[{id:1,name:'其他收入'}]};
  const p=new URL(route,'http://test').searchParams;
  const filtered=rows.filter(r=>r.income_date>=p.get('start_date')&&r.income_date<=p.get('end_date')&&(!p.get('currency')||r.currency===p.get('currency'))&&(!p.get('category_id')||r.category_id===Number(p.get('category_id')))&&(!p.get('search')||r.remark.includes(p.get('search'))));
  const totals={};filtered.forEach(r=>totals[r.currency]=(totals[r.currency]||0)+r.amount);
  if(flags.holdCurrency&&flags.holdCurrency===p.get('currency'))await new Promise(resolve=>held.push(resolve));
  const first=(Number(p.get('page'))-1)*Number(p.get('page_size'));
  return{data:filtered.slice(first,first+Number(p.get('page_size'))),total:filtered.length,totals_by_currency:totals};},
  async post(route,payload){writes.push({route,payload});rows.push({...payload,id:1000+rows.length,amount:Number(payload.amount)});return{id:rows.at(-1).id};},
  async put(route,payload){writes.push({route,payload});return{};},async delete(){throw Error('Not needed in currency test');}};
 const imports={react,'@/lib/api':{api,getToken:()=> 'synthetic-token',getActiveWarehouseId:()=> '1'},'@/lib/currency':currency,
  '@/components/ui/Toast':{useToast:()=>({toast:(...args)=>messages.push(args)})},'next/navigation':{useRouter:()=>({push(){}})}};
 class FixedDate extends Date{constructor(...args){super(...(args.length?args:['2026-10-20T12:00:00+07:00']));}}
 const page=compile('../src/app/(dashboard)/other-income-expense/page.tsx',imports,{Date:FixedDate,URLSearchParams,process:{env:{}},
  fetch:async(url,options)=>{exports.push({url,headers:options.headers});return{ok:!flags.denyExport,json:async()=>({detail:'无此操作权限'}),blob:async()=>({})};},
  window:{URL:{createObjectURL:()=> 'blob:isolated',revokeObjectURL:url=>assert.equal(url,'blob:isolated')}},
  document:{createElement:()=>{const a={click(){downloads.push({href:a.href,download:a.download});}};return a;}}});
 return{rows,reads,writes,exports,downloads,messages,held,flags,async render(){await wait();for(let n=0;n<20;n++){si=ri=ei=0;const tree=page.default();if(!effects.length)return tree;effects.splice(0).forEach(fn=>fn());await wait();}throw Error('Unsettled effects');}};
}
(async()=>{
 const h=harness();let tree=await h.render();
 assert(text(tree).includes('泰铢 THB฿100'));assert(text(tree).includes('人民币 CNY¥200'));
 assert(!text(tree).includes('฿1,000'));assert(!text(tree).includes('显示为'));assert(!h.reads.some(r=>r.includes('/rates')||r.includes('/monthly-summary')));
 for(const [cur,amount,excluded]of[['THB','฿100','CNY-200'],['CNY','¥200','THB-100']]){
  change(field(tree,'币种'),cur);tree=await h.render();assert(text(tree).includes(amount));assert(!text(tree).includes(excluded));
  await button(tree,'导出Excel').props.onClick();const p=new URL(h.exports.at(-1).url,'http://test').searchParams;
  assert.equal(p.get('currency'),cur);assert.equal(p.get('category_group'),'other');assert.equal(h.exports.at(-1).headers['X-Warehouse-ID'],'1');
  assert.equal(h.exports.at(-1).headers.Authorization,'Bearer synthetic-token');assert(h.downloads.at(-1).download.startsWith('other_income_'+cur+'_'));
 }
 // Different history period has 27 rows, with totals THB26/CNY2 on both pages.
 h.rows.push(...Array.from({length:26},(_,n)=>({id:3+n,amount:1,currency:'THB',category_id:1,account_id:1,income_date:'2026-09-15',remark:'SEPT-'+n})),
  {id:29,amount:2,currency:'CNY',category_id:1,account_id:3,income_date:'2026-09-15',remark:'SEPT-CNY-2'});
 change(field(tree,'币种'),'');tree=await h.render();change(field(tree,'开始日期'),'2026-09-01');tree=await h.render();change(field(tree,'结束日期'),'2026-09-30');tree=await h.render();
 assert(text(tree).includes('泰铢 THB฿26'));assert(text(tree).includes('人民币 CNY¥2'));assert(text(tree).includes('第 1/2 页'));
 button(tree,'下一页').props.onClick();tree=await h.render();assert(text(tree).includes('第 2/2 页'));assert(text(tree).includes('泰铢 THB฿26'));
 h.flags.holdCurrency='THB';change(field(tree,'币种'),'THB');tree=await h.render();assert.equal(h.held.length,1);
 change(field(tree,'币种'),'CNY');tree=await h.render();assert(text(tree).includes('人民币 CNY¥2'));
 h.flags.holdCurrency=null;h.held.splice(0).forEach(resolve=>resolve());tree=await h.render();
 assert(text(tree).includes('人民币 CNY¥2'));assert(!text(tree).includes('SEPT-0'));assert(!text(tree).includes('第 2/2 页'));
 change(field(tree,'搜索'),'missing');tree=await h.render();assert(text(tree).includes('¥0'));assert(text(tree).includes('暂无收入记录'));
 button(tree,'重置').props.onClick();tree=await h.render();button(tree,'新建收入').props.onClick();tree=await h.render();
 let modal=find(tree,n=>n.props?.className==='modal-overlay');let account=field(modal,'收款账户');
 assert(!text(account).includes('人民币现金'));change(account,'1');tree=await h.render();modal=find(tree,n=>n.props?.className==='modal-overlay');
 change(field(modal,'币种'),'CNY');tree=await h.render();modal=find(tree,n=>n.props?.className==='modal-overlay');account=field(modal,'收款账户');
 assert.equal(account.props.value,0);assert(text(account).includes('人民币现金'));assert(!text(account).includes('停用'));
 await button(modal,'保存').props.onClick();assert.equal(h.writes.length,0);assert(h.messages.some(m=>m[1]==='请选择收款账户'));
 change(account,'3');tree=await h.render();modal=find(tree,n=>n.props?.className==='modal-overlay');change(field(modal,'分类'),'1');tree=await h.render();modal=find(tree,n=>n.props?.className==='modal-overlay');change(field(modal,'金额'),'10');tree=await h.render();modal=find(tree,n=>n.props?.className==='modal-overlay');
 await button(modal,'保存').props.onClick();tree=await h.render();assert.equal(h.writes[0].payload.currency,'CNY');assert.equal(h.writes[0].payload.account_id,3);
 assert(text(tree).includes('人民币 CNY¥210'));assert(text(tree).includes('泰铢 THB฿100'));
 h.flags.denyExport=true;await button(tree,'导出Excel').props.onClick();assert(h.messages.some(m=>m[1]==='无此操作权限'));assert.equal(h.downloads.length,2);
 console.log('PASS: actual other-income page shows THB100 and CNY200 separately without rates; filters/page/date/empty totals agree; late response ignored; export shares filters/auth/warehouse; form currency clears incompatible account and only submits matching account');
})().catch(error=>{console.error(error);process.exitCode=1;});
