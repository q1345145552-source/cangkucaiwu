const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const ts=require('typescript'),React=require('react'),{execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'../..'),filename='frontend/src/app/(dashboard)/config-center/page.tsx',source=fs.readFileSync(path.join(root,filename),'utf8');
function harness(editable){
 let state=[],cursor=0,ei=0,deps=[],effects=[],writes=[],messages=[];
 const react={...React,useState(v){let i=cursor++;if(!(i in state))state[i]=v;return [state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];},useEffect(fn,d){let i=ei++,key=JSON.stringify(d);if(deps[i]!==key){deps[i]=key;effects.push(fn);}}};
 const schedule={morning_start:'08:30',late_half:'08:35',late_one:'08:50',noon_break_start:'12:00',noon_break_end:'13:00',early_one:'17:00',early_half:'17:30',afternoon_end:'18:00',overtime_limit:65,editable};
 const api={get:async p=>p==='/config/work-schedule'?schedule:{threshold:p.startsWith('/expense')?42:p.includes('purchase')?123:80},put:async(p,b)=>{writes.push({p,b});return {};}};
 const imports={react,'@/lib/api':{api,getToken:()=> 'test'},'@/components/ui/Toast':{useToast:()=>({toast:(...args)=>messages.push(args)})},'next/navigation':{useRouter:()=>({push(){}})}};
 const m={exports:{}};vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module:m,exports:m.exports,require:n=>imports[n]||require(n)});
 async function render(){let t;for(let n=0;n<5;n++){cursor=ei=0;t=m.exports.default();for(let f of effects.splice(0))f();await new Promise(setImmediate);}return t;}
 return {render,writes,messages};
}
const nodes=t=>t==null||typeof t!=='object'?[]:Array.isArray(t)?t.flatMap(nodes):[t,...nodes(t.props?.children)];
const text=t=>t==null||typeof t==='boolean'?'':typeof t!=='object'?String(t):Array.isArray(t)?t.map(text).join(''):text(t.props?.children);
(async()=>{
 let h=harness(false),t=await h.render(),inputs=nodes(t).filter(n=>n.type==='input');assert.equal(inputs.length,12);assert(inputs.every(n=>n.props.disabled));assert(inputs.every(n=>n.props.className.includes('disabled:bg-gray-100')));assert(!nodes(t).some(n=>n.type==='button'&&text(n).includes('保存')));assert(text(t).includes('当前账号只读'));assert(inputs.some(n=>n.props.value==='08:30'));assert(inputs.some(n=>n.props.value==='42'));assert(inputs.some(n=>n.props.value==='123'));assert(inputs.some(n=>n.props.value==='80'));assert.equal(h.writes.length,0);
 h=harness(true);t=await h.render();inputs=nodes(t).filter(n=>n.type==='input');assert(inputs.every(n=>!n.props.disabled));let buttons=nodes(t).filter(n=>n.type==='button');assert.equal(buttons.length,2);await buttons.find(n=>text(n)==='保存作息').props.onClick();t=await h.render();await nodes(t).find(n=>n.type==='button'&&text(n)==='保存审批门槛').props.onClick();assert.equal(h.writes.length,4);assert.equal(h.writes[0].b.overtime_limit,65);assert(h.messages.some(x=>x[1]==='作息设置已保存'));assert(h.messages.some(x=>x[1]==='审批门槛已保存'));
 const printer=ts.createPrinter();function funcs(s){let sf=ts.createSourceFile(filename,s,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),out={};function visit(n){if(ts.isFunctionDeclaration(n)&&n.name&&n.name.text!=='ConfigCenterPage')out[n.name.text]=printer.printNode(ts.EmitHint.Unspecified,n,sf);ts.forEachChild(n,visit);}visit(sf);return out;}
 assert.deepEqual(funcs(source),funcs(execFileSync('git',['show','e970f41:'+filename],{cwd:root,encoding:'utf8'})));
 // Both employee-facing consumers intentionally use the safe shared read endpoint.
 for(const shared of ['frontend/src/app/(dashboard)/attendance/page.tsx','frontend/src/components/ClockRecordsGrid.tsx']){
  const current=fs.readFileSync(path.join(root,shared),'utf8');
  assert(current.includes('"/config/attendance-times"'));assert(!current.includes('"/config/work-schedule"'));
 }
 // Validate the real backend role boundary using the explicit isolated fixture as well.
 const {testBase}=require('./legacy-regression-support.cjs');const base=testBase();
 async function request(route,token){const r=await fetch(base+route,{headers:{Authorization:'Bearer '+token}});return {status:r.status,data:await r.json()};}
 async function auth(name){const r=await fetch(base+'/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:name,password:'test-password'})});assert.equal(r.status,200);return (await r.json()).access_token;}
 for(const name of ['staff_attendance','supervisor_attendance']){const token=await auth(name);assert.equal((await request('/config/attendance-times',token)).status,200);assert.equal((await request('/config/work-schedule',token)).status,403);}
 for(const name of ['staff_none','supervisor_none'])assert.equal((await request('/config/attendance-times',await auth(name))).status,403);
 const laborToken=await auth('labor1');assert.equal((await request('/config/attendance-times',laborToken)).status,403);
 for(const name of ['staff_all','supervisor_all','warehouse_admin']){const r=await request('/config/work-schedule',await auth(name));assert.equal(r.status,200);assert.equal(r.data.editable,name!=='staff_all');}
 console.log('Config center: readonly inputs, saved values, 4 write calls and unchanged handlers passed');
})().catch(e=>{console.error(e);process.exit(1)});
