const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const React=require('react'),ts=require('typescript');
const source=fs.readFileSync(path.resolve(__dirname,'../src/app/(dashboard)/employee-advances/page.tsx'),'utf8');
const rows=[
 {id:1,employee_name:'可作废员工',amount:1000,status:'unpaid',approval_status:'approved',can_void:true},
 {id:2,employee_name:'待审批员工',amount:1000,status:'unpaid',approval_status:'pending',can_void:true},
 {id:3,employee_name:'已作废员工',amount:1000,status:'voided',is_voided:true,approval_status:'pending',void_reason:'登记有误',can_void:false},
 {id:4,employee_name:'已结清员工',amount:1000,status:'deducted',deducted_amount:1000,approval_status:'approved',can_void:false},
 {id:5,employee_name:'部分抵扣员工',amount:2000,status:'partial',deducted_amount:1200,approval_status:'approved',can_void:false},
];
const text=n=>n==null||typeof n==='boolean'?'':typeof n!=='object'?String(n):Array.isArray(n)?n.map(text).join(''):text(n.props?.children);
const walk=n=>n==null||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(walk):[n,...walk(n.props?.children)];
const find=(t,p)=>{const n=walk(t).find(p);assert(n);return n;};
const button=(t,label)=>find(t,n=>n.type==='button'&&text(n).trim()===label);
const row=(t,name)=>find(t,n=>n.type==='tr'&&text(n).includes(name));
function harness(role='warehouse_admin',fail=false){
 let state=[],cursor=0,ei=0,deps=[],effects=[],writes=[],messages=[],data=structuredClone(rows);
 const react={...React,useState(initial){const i=cursor++;if(!(i in state))state[i]=initial;return[state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];},useEffect(fn,d){const i=ei++,s=JSON.stringify(d);if(deps[i]!==s){deps[i]=s;effects.push(fn);}}};
 const api={get:async r=>r.includes('/summary')?{}:{data:r.startsWith('/employee-advances?')?structuredClone(data):[]},delete:async(r,body)=>{writes.push({route:r,body});if(fail)throw Error('作废失败，原记录未改变');const id=Number(r.split('/').at(-1));data=data.map(x=>x.id===id?{...x,status:'voided',is_voided:true,void_reason:body.void_reason,can_void:false}:x);return{message:'预支已作废'};}};
 const imports={react,'@/lib/api':{api,getToken:()=> 'test'},'@/hooks/useMenuPermission':{useMenuPermission:()=>true},'@/hooks/useAuth':{useAuth:()=>({user:{role}})},'@/components/ui/Toast':{useToast:()=>({toast:(...args)=>messages.push(args)})},'next/navigation':{useRouter:()=>({push(){}})}};
 const m={exports:{}};vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module:m,exports:m.exports,require:n=>imports[n]||require(n),Date,URLSearchParams,window:{location:{search:''}}});
 return{async render(){let tree;for(let i=0;i<5;i++){cursor=ei=0;tree=m.exports.default();for(const effect of effects.splice(0))effect();await new Promise(setImmediate);}return tree;},writes,messages};
}
(async()=>{
 let h=harness(),tree=await h.render();
 assert(!walk(tree).some(n=>n.type==='button'&&(n.props.title==='删除'||text(n).includes('删除'))));
 assert(button(row(tree,'已结清员工'),'作废').props.disabled);
 assert(button(row(tree,'部分抵扣员工'),'作废').props.disabled);
 assert(!walk(row(tree,'已作废员工')).some(n=>n.type==='button'));
 assert(text(row(tree,'已作废员工')).includes('已作废')&&row(tree,'已作废员工').props.className.includes('text-gray-400'));
 button(row(tree,'可作废员工'),'作废').props.onClick();tree=await h.render();
 const dialog=find(tree,n=>n.props?.['aria-label']==='作废预支');
 assert(text(dialog).includes('作废后当作没预支过 关联的支出也会删除'));
 assert(dialog.props.className.includes('overflow-y-auto')&&dialog.props.className.includes('max-h-[85vh]'));
 await button(tree,'确认作废').props.onClick();assert.equal(h.writes.length,0);assert.equal(h.messages.at(-1)[1],'请填写作废原因');
 find(tree,n=>n.props?.['aria-label']==='作废原因').props.onChange({target:{value:' 登记有误 '}});tree=await h.render();await button(tree,'确认作废').props.onClick();tree=await h.render();
 assert.deepEqual(JSON.parse(JSON.stringify(h.writes)),[{route:'/employee-advances/1',body:{void_reason:'登记有误'}}]);
 assert.equal(h.messages.at(-1)[1],'预支已作废');assert(text(row(tree,'可作废员工')).includes('已作废'));
 assert(!walk(tree).some(n=>n.props?.['aria-label']==='作废预支'));
 for(const role of ['supervisor','staff','warehouse_labor','super_admin']){h=harness(role);tree=await h.render();assert(!walk(tree).some(n=>n.type==='button'&&text(n).trim()==='作废'));}
 h=harness('warehouse_admin',true);tree=await h.render();button(row(tree,'可作废员工'),'作废').props.onClick();tree=await h.render();find(tree,n=>n.props?.['aria-label']==='作废原因').props.onChange({target:{value:'原因保留'}});tree=await h.render();await button(tree,'确认作废').props.onClick();tree=await h.render();assert.equal(h.messages.at(-1)[1],'作废失败，原记录未改变');assert.equal(find(tree,n=>n.props?.['aria-label']==='作废原因').props.value,'原因保留');
 const apiSource=fs.readFileSync(path.resolve(__dirname,'../src/lib/api.ts'),'utf8'),m={exports:{}},requests=[];
 vm.runInNewContext(ts.transpileModule(apiSource,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS}}).outputText,{module:m,exports:m.exports,process:{env:{}},fetch:async(url,options)=>{requests.push({url,options});return{ok:true,status:200,json:async()=>({})};}});
 await m.exports.api.delete('/customers/7');await m.exports.api.delete('/employee-advances/1',{void_reason:'原因'});
 assert.equal(requests[0].options.body,undefined);assert.equal(requests[1].options.method,'DELETE');assert.equal(requests[1].options.body,JSON.stringify({void_reason:'原因'}));
 console.log('Advance void UI: role gates, reason, state, retained history and DELETE payload passed');
})().catch(error=>{console.error(error);process.exit(1)});
