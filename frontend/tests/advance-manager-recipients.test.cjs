const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {execFileSync}=require('node:child_process'),React=require('react'),ts=require('typescript');
const root=path.resolve(__dirname,'../..'),name='frontend/src/app/(dashboard)/employee-advances/page.tsx';
const source=fs.readFileSync(path.join(root,name),'utf8');
const choices=[{value:'employee:1',name:'普通员工',role_label:'员工'},{value:'user:1',name:'老板',role_label:'仓库管理员'},{value:'user:4',name:'主管甲',role_label:'主管'}];
function harness(fail=false,creationMessage='成功'){
 let state=[],cursor=0,ei=0,deps=[],effects=[],reads=[],writes=[],messages=[];
 const react={...React,useState(initial){const k=cursor++;if(!(k in state))state[k]=initial;return [state[k],v=>{state[k]=typeof v==='function'?v(state[k]):v;}];},useEffect(fn,d){const k=ei++,key=JSON.stringify(d);if(deps[k]!==key){deps[k]=key;effects.push(fn);}}};
 const api={get:async route=>{reads.push(route);if(route==='/employee-advances/funding-options')return {accounts:[{id:1,account_name:'现金',account_type:'cash',currency:'THB',current_balance:10000}],cash_advances:[],funds:[]};if(route==='/employee-advances/recipients')return {data:choices};if(route.startsWith('/employees?'))return {data:[{id:1,name:'普通员工'}]};if(route==='/employee-advances/summary')return {};return {data:[]};},post:async(route,body)=>{writes.push({route,body:JSON.parse(JSON.stringify(body))});if(fail)throw Error(fail===true?'绑定冲突':fail);return {message:creationMessage};}};
 const imports={react,'@/lib/api':{api,getToken:()=> 'test'},'@/hooks/useMenuPermission':{useMenuPermission:()=>true},'@/hooks/useAuth':{useAuth:()=>({user:{role:'warehouse_admin'}})},'@/components/ui/Toast':{useToast:()=>({toast:(...args)=>messages.push(args)})},'next/navigation':{useRouter:()=>({push(){}})}};
 const m={exports:{}};vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module:m,exports:m.exports,require:n=>imports[n]||require(n),Date,URLSearchParams,window:{location:{search:''}}});
 async function render(){let tree;for(let i=0;i<5;i++){cursor=ei=0;tree=m.exports.default();for(const f of effects.splice(0))f();await new Promise(setImmediate);}return tree;}
 return {render,reads,writes,messages};
}
const text=n=>n==null||typeof n==='boolean'?'':typeof n!=='object'?String(n):Array.isArray(n)?n.map(text).join(''):text(n.props?.children);
const nodes=n=>n==null||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(nodes):[n,...nodes(n.props?.children)];
const find=(t,p)=>{let n=nodes(t).find(p);assert(n);return n;};
const button=(t,label)=>find(t,n=>n.type==='button'&&text(n).trim()===label);
const change=(n,value)=>n.props.onChange({target:{value}});
(async()=>{
 let h=harness(),t=await h.render();assert(h.reads.includes('/employee-advances/recipients'));
 button(t,'记预支').props.onClick();t=await h.render();change(find(t,n=>n.props?.['aria-label']==='资金来源'),'company_account');t=await h.render();let dropdown=find(t,n=>n.type==='select'&&n.props['aria-label']==='预支对象');
 assert(text(dropdown).includes('主管甲（主管）'));assert(text(dropdown).includes('老板（仓库管理员）'));assert(text(dropdown).includes('普通员工（员工）'));
 await button(t,'提交').props.onClick();assert.equal(h.writes.length,0);assert.equal(h.messages.at(-1)[1],'请选择员工');
 change(dropdown,'user:4');change(find(t,n=>n.type==='input'&&n.props.type==='number'),'100');t=await h.render();await button(t,'提交').props.onClick();t=await h.render();
 assert.equal(h.writes[0].body.user_id,4);assert(!('employee_id' in h.writes[0].body));assert.equal(h.writes[0].body.amount,100);
 button(t,'记预支').props.onClick();t=await h.render();change(find(t,n=>n.props?.['aria-label']==='资金来源'),'company_account');t=await h.render();dropdown=find(t,n=>n.type==='select'&&n.props['aria-label']==='预支对象');assert.equal(dropdown.props.value,'');
 change(dropdown,'employee:1');change(find(t,n=>n.type==='input'&&n.props.type==='number'),'50');t=await h.render();await button(t,'提交').props.onClick();assert.equal(h.writes[1].body.employee_id,1);assert(!('user_id' in h.writes[1].body));
 h=harness(true);t=await h.render();button(t,'记预支').props.onClick();t=await h.render();change(find(t,n=>n.props?.['aria-label']==='资金来源'),'company_account');t=await h.render();change(find(t,n=>n.type==='select'&&n.props['aria-label']==='预支对象'),'user:4');change(find(t,n=>n.type==='input'&&n.props.type==='number'),'100');t=await h.render();await button(t,'提交').props.onClick();t=await h.render();assert.equal(h.messages.at(-1)[1],'绑定冲突');assert.equal(find(t,n=>n.type==='select'&&n.props['aria-label']==='预支对象').props.value,'user:4');
 const warning='预支记录已创建；该员工没有薪资模板 无法校验预支上限';
 h=harness(false,warning);t=await h.render();button(t,'记预支').props.onClick();t=await h.render();change(find(t,n=>n.props?.['aria-label']==='资金来源'),'company_account');t=await h.render();change(find(t,n=>n.type==='select'&&n.props['aria-label']==='预支对象'),'employee:1');change(find(t,n=>n.type==='input'&&n.props.type==='number'),'100');t=await h.render();await button(t,'提交').props.onClick();assert.equal(h.messages.at(-1)[1],warning);
 const quotaError='预支合计不能超过当月工资，当前可用 2000.00 元';
 h=harness(quotaError);t=await h.render();button(t,'记预支').props.onClick();t=await h.render();change(find(t,n=>n.props?.['aria-label']==='资金来源'),'company_account');t=await h.render();change(find(t,n=>n.type==='select'&&n.props['aria-label']==='预支对象'),'employee:1');change(find(t,n=>n.type==='input'&&n.props.type==='number'),'3000');t=await h.render();await button(t,'提交').props.onClick();t=await h.render();assert.equal(h.messages.at(-1)[1],quotaError);assert.equal(find(t,n=>n.type==='select'&&n.props['aria-label']==='预支对象').props.value,'employee:1');
 const before=execFileSync('git',['show','cbaddcb:'+name],{cwd:root,encoding:'utf8'}),printer=ts.createPrinter();
 function funcs(s){const out={},sf=ts.createSourceFile(name,s,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);function visit(n){if(ts.isFunctionDeclaration(n)&&n.name&&!['EmployeeAdvancePage','loadRefs','handleCreate','handleDelete','handleVoid','loadFundingOptions','chooseFunding'].includes(n.name.text))out[n.name.text]=printer.printNode(ts.EmitHint.Unspecified,n,sf);ts.forEachChild(n,visit);}visit(sf);return out;}
 assert.deepEqual(funcs(source),funcs(before));
 console.log('Advance recipient dropdown and quota messages: 15 checks passed');
})().catch(e=>{console.error(e);process.exit(1)});
