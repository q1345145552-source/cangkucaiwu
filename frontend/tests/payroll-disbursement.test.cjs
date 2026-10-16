// Render the actual payroll page against API-shaped fixtures; writes are intercepted.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {execFileSync}=require('node:child_process'),ts=require('typescript'),React=require('react');
const root=path.resolve(__dirname,'../..'),filename='frontend/src/app/(dashboard)/payroll/page.tsx',source=fs.readFileSync(path.join(root,filename),'utf8');
const before=execFileSync('git',['show','2102711:'+filename],{cwd:root,encoding:'utf8'});
function load(s,imports){const m={exports:{}};vm.runInNewContext(ts.transpileModule(s,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module:m,exports:m.exports,require:n=>imports[n]||require(n),console,Date,URL,URLSearchParams,Set,Math});return m.exports;}
const records=[{id:2,employee_id:1,employee_name:'员工甲',status:'confirmed',net_pay:1234.56,settle_start_date:'2026-10-01',settle_end_date:'2026-10-15'}, {id:11,employee_id:3,employee_name:'员工乙',status:'confirmed',net_pay:100.01}, {id:12,employee_id:4,employee_name:'员工丙',status:'confirmed',net_pay:200.02}, {id:3,employee_id:1,employee_name:'历史单',status:'confirmed',disbursed:true,net_pay:9}];
const accounts=[{id:1,warehouse_id:1,account_name:'银行',account_type:'bank',currency:'THB',status:'active'},{id:3,warehouse_id:1,account_name:'现金',account_type:'cash',currency:'THB',status:'active'},{id:4,warehouse_id:1,account_name:'停用',currency:'THB',status:'inactive'},{id:5,warehouse_id:1,account_name:'美元',currency:'USD',status:'active'},{id:6,warehouse_id:2,account_name:'外仓',currency:'THB',status:'active'}];
function harness({accountRows=accounts,accountError=false,postError=false}={}){
 let states=[],refs=[],deps=[],cursor=0,rc=0,ec=0,pending=[],effects=[];const writes=[],messages=[];
 const react={...React,useState(initial){const i=cursor++;if(!(i in states))states[i]=typeof initial==='function'?initial():initial;return [states[i],v=>{states[i]=typeof v==='function'?v(states[i]):v;}];},useRef(initial){const i=rc++;if(!refs[i])refs[i]={current:initial};return refs[i];},useCallback:fn=>fn,useEffect(fn,ds){const i=ec++,key=JSON.stringify(ds);if(deps[i]!==key){deps[i]=key;effects.push(fn);}}};
 const read=async route=>{if(route==='/accounts'){if(accountError)throw Error('账户请求失败');return {data:accountRows};}if(route.startsWith('/payroll/settlement-progress'))return {data:[]};if(route.startsWith('/payroll/summary'))return {};if(route.startsWith('/payroll'))return {months:['2026-10'],data:records};throw Error('Unexpected read '+route);};
 const api={get(route){const p=read(route);pending.push(p.catch(()=>{}));return p;},post(route,body){writes.push({route,body});const p=postError?Promise.reject(Error('后端拒绝')):Promise.resolve({message:'已发放',count:body.record_ids?.length||1});pending.push(p.catch(()=>{}));return p;}};
 const Component=load(source,{react,'@/lib/api':{api,getToken:()=> 'test',getActiveWarehouseId:()=> '1'},'@/hooks/useAuth':{useAuth:()=>({user:{role:'warehouse_admin',warehouse_id:1}})},'next/navigation':{useRouter:()=>({push(){}})},'@/components/ui/Toast':{useToast:()=>({toast:(...args)=>messages.push(args)})},'@/components/SafeImage':{__esModule:true,default:()=>null},'@/lib/thai-time':{thaiNow:()=>new Date('2026-10-16T12:00:00')}}).default;
 const expand=n=>n==null||typeof n!=='object'?n:Array.isArray(n)?n.map(expand):typeof n.type==='function'?expand(n.type(n.props)):React.cloneElement(n,{},expand(n.props?.children));
 async function render(){let tree;for(let i=0;i<5;i++){cursor=0;rc=0;ec=0;tree=expand(Component());const work=effects;effects=[];work.forEach(fn=>fn());if(!pending.length&&!effects.length)return tree;while(pending.length){const jobs=pending;pending=[];await Promise.all(jobs);await new Promise(resolve=>setImmediate(resolve));} }return tree;}
 return {render,writes,messages};
}
const text=n=>n==null||typeof n==='boolean'?'':typeof n==='string'||typeof n==='number'?String(n):Array.isArray(n)?n.map(text).join(''):text(n.props?.children);
const walk=n=>!n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(walk):[n,...walk(n.props?.children)];
const find=(n,p)=>{const v=walk(n).find(p);assert(v,'Missing node');return v;};
const button=(t,label)=>find(t,n=>n.type==='button'&&(n.props.title===label||text(n).trim()===label));
const row=(t,name)=>find(t,n=>n.type==='tr'&&text(n).includes(name));
const select=t=>find(t,n=>n.type==='select'&&n.props.id==='payroll-disburse-account');
const change=(n,value)=>n.props.onChange({target:{value}});
function scope(){
 const printer=ts.createPrinter();
 const funcs=s=>{const sf=ts.createSourceFile(filename,s,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),out={};function visit(n){if(ts.isFunctionDeclaration(n)&&n.name&&!['PayrollPage','handleDisburse','openDisburseModal','confirmDisburse','handleBatchDisburse'].includes(n.name.text))out[n.name.text]=printer.printNode(ts.EmitHint.Unspecified,n,sf);ts.forEachChild(n,visit);}visit(sf);return out;};
 assert.deepEqual(funcs(source),funcs(before),'All other handlers, including revocation, stay identical');
 const strip=s=>s.slice(0,s.indexOf('      {/* 发放工资 Modal'))+s.slice(s.indexOf('      {/* 撤销发放 Modal'));
 const handlers=s=>{const sf=ts.createSourceFile(filename,strip(s),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),out=[];function visit(n){if(ts.isJsxAttribute(n)&&/^on[A-Z]/.test(n.name.getText(sf)))out.push(printer.printNode(ts.EmitHint.Unspecified,n,sf));ts.forEachChild(n,visit);}visit(sf);return out;};
 assert.deepEqual(handlers(source),handlers(before),'Buttons outside the disbursement modal stay identical');
 assert.equal(execFileSync('git',['diff','2102711','--','backend'],{cwd:root,encoding:'utf8'}),'','Backend untouched');
 const changed=execFileSync('git',['diff','--name-only','2102711','--','frontend/src'],{cwd:root,encoding:'utf8'}).trim().split('\n');assert.deepEqual(changed,[filename]);
}
async function main(){
 scope();let cases=0;
 let h=harness(),t=await h.render();await button(row(t,'员工甲'),'发放').props.onClick();t=await h.render();assert(text(t).includes('1,234.56'));assert.equal(select(t).props.value,'3');assert.equal(walk(select(t)).filter(n=>n.type==='option').length,3);cases++;
 change(select(t),'');t=await h.render();await button(t,'确认发放').props.onClick();assert.deepEqual(h.messages.at(-1),['error','请选择工资发放账户']);assert.equal(h.writes.length,0);cases++;
 change(select(t),'1');t=await h.render();await button(t,'确认发放').props.onClick();t=await h.render();assert.equal(h.writes[0].route,'/payroll/2/disburse');assert.equal(h.writes[0].body.account_id,1);assert(h.messages.at(-1)[1].includes('已记入运营支出'));cases++;
 h=harness();t=await h.render();for(const name of ['员工乙','员工丙'])find(row(t,name),n=>n.type==='input'&&n.props.type==='checkbox').props.onChange();t=await h.render();await button(t,'批量发放').props.onClick();t=await h.render();assert(text(t).includes('300.03'));assert(text(t).includes('人数2 人'));assert(text(t).includes('本次发放 2 张'));await button(t,'确认发放').props.onClick();t=await h.render();assert.equal(h.writes[0].route,'/payroll/batch-disburse');assert.deepEqual(Array.from(h.writes[0].body.record_ids),[11,12]);assert.equal(h.writes[0].body.account_id,3);cases++;
 for(const accountRows of [[],accounts.map(a=>({...a,status:'inactive'})),accounts.filter(a=>a.warehouse_id===2),accounts.filter(a=>a.currency==='USD')]){h=harness({accountRows});t=await h.render();await button(row(t,'员工甲'),'发放').props.onClick();t=await h.render();assert(text(t).includes('还没有可用的泰铢收款账户'));assert(button(t,'确认发放').props.disabled);assert.equal(h.writes.length,0);cases++;}
 h=harness({accountRows:[accounts[0]]});t=await h.render();await button(row(t,'员工甲'),'发放').props.onClick();t=await h.render();assert.equal(select(t).props.value,'1');cases++;
 h=harness({accountError:true});t=await h.render();await button(row(t,'员工甲'),'发放').props.onClick();t=await h.render();assert(text(t).includes('账户请求失败'));assert(button(t,'确认发放').props.disabled);cases++;
 h=harness({postError:true});t=await h.render();await button(row(t,'员工甲'),'发放').props.onClick();t=await h.render();await button(t,'确认发放').props.onClick();t=await h.render();assert.equal(h.messages.at(-1)[0],'error');assert(!h.messages.at(-1)[1].includes('已记入运营支出'));assert.equal(select(t).props.value,'3');cases++;
 h=harness();t=await h.render();await button(row(t,'员工甲'),'查看工资单').props.onClick();t=await h.render();const direct=find(t,n=>n.type==='button'&&text(n).includes('现金发放'));await direct.props.onClick();t=await h.render();assert.equal(select(t).props.value,'3');assert.equal(h.writes.length,0);cases++;
 console.log(JSON.stringify({result:'PASS',scenarios:cases,scope:'Only disbursement modal and its handlers; backend and revoke unchanged'}));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
