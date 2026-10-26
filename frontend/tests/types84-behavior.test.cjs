const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript'),React=require('react'),{execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'..'),baseline='adb9024b3706ee7a94cbfe5e219ba47da1eab8d1';
const opts={module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true};
function emitted(source,name){return ts.transpileModule(source,{fileName:name,compilerOptions:opts}).outputText;}
function canonical(js){return ts.createPrinter({removeComments:true}).printFile(ts.createSourceFile('output.js',js,ts.ScriptTarget.ES2020,true,ts.ScriptKind.JS));}
for(const file of['lib/api.ts','components/layout/DashboardLayout.tsx',...['employees','expense-fund','income-expense','operating','payroll','recharge','suppliers'].map(x=>`app/(dashboard)/${x}/page.tsx`)]){
 const current=fs.readFileSync(path.join(root,'src',file),'utf8'),before=execFileSync('git',['show',`${baseline}:frontend/src/${file}`],{cwd:root,encoding:'utf8'});
 assert.equal(canonical(emitted(current,file)),canonical(emitted(before,file)),file+' only gains accurate static types: emitted runtime, requests, handlers and labels must be identical');
}
for(const [page,after,before]of[
 ['payable','<span title={`供应商确认: ${row.confirmed_amount}`}><AlertTriangle size={12} className="inline text-orange-500 ml-1" /></span>','<AlertTriangle size={12} className="inline text-orange-500 ml-1" title={`供应商确认: ${row.confirmed_amount}`} />'],
 ['concentration','<span title={`占比超过 ${threshold}%`}><AlertTriangle size={16} className="text-red-500" /></span>','<AlertTriangle size={16} className="text-red-500" title={`占比超过 ${threshold}%`} />']
]){
 const file=`app/(dashboard)/${page}/page.tsx`,source=fs.readFileSync(path.join(root,'src',file),'utf8'),base=execFileSync('git',['show',`${baseline}:frontend/src/${file}`],{cwd:root,encoding:'utf8'});
 assert(source.includes(after));assert.equal(canonical(emitted(source.replace(after,before),file)),canonical(emitted(base,file)),page+' emitted behavior must match apart from moving the same tooltip to a supported span');
}
const walk=x=>!x||typeof x!=='object'?[]:Array.isArray(x)?x.flatMap(walk):[x,...walk(x.props?.children)],text=x=>x==null||typeof x==='boolean'?'':typeof x!=='object'?String(x):Array.isArray(x)?x.map(text).join(''):text(x.props?.children),tick=()=>new Promise(r=>setImmediate(r));
function overtime({role='warehouse_admin',reject=false}={}){
 const states=[],deps=[],effects=[],reads=[],messages=[],writes=[];let si=0,ei=0;
 const react={...React,useState(v){const i=si++;if(!(i in states))states[i]=typeof v==='function'?v():v;return[states[i],v=>states[i]=typeof v==='function'?v(states[i]):v];},useEffect(fn,d){const i=ei++,k=JSON.stringify(d);if(deps[i]!==k){deps[i]=k;effects.push(fn);}}};
 const dict=JSON.parse(fs.readFileSync(path.join(root,'src/i18n/zh.json'),'utf8'));
 const api={async get(route){reads.push(route);if(route==='/overtime/limit')return{max_hours:50};if(route.includes('/monthly-hours'))return{data:[{employee_name:'合成员工',total_hours:45}]};if(route.includes('work-schedule'))return{afternoon_end:'18:00'};return{data:[],total:0};},async post(route,body){writes.push({route,body});if(reject)throw Error('本人不能核实自己的加班');return{message:'合成确认成功',total_amount:75};}};
 const imports={react,'@/lib/api':{api,getToken:()=> 'synthetic'},'@/hooks/useAuth':{useAuth:()=>({user:{id:1,role}})},'@/hooks/useEmployeeView':{useEmployeeView:()=>({employeeView:false,initialLeave:false})},'@/hooks/useI18n':{useI18n:()=>({t:k=>dict[k]||k,locale:'zh'})},'@/components/EmployeeLanguage':{__esModule:true,default:()=>null},'@/components/ui/Toast':{useToast:()=>({toast:(...args)=>messages.push(args)})},'next/navigation':{useRouter:()=>({push(){}})}};
 const m={exports:{}};vm.runInNewContext(emitted(fs.readFileSync(path.join(root,'src/app/(dashboard)/overtime/page.tsx'),'utf8'),'page.tsx'),{module:m,exports:m.exports,require:n=>imports[n]||require(n),console,Date,URLSearchParams,window:{location:{search:''}}});
 return{reads,messages,writes,async render(){await tick();for(let i=0;i<12;i++){si=ei=0;let tree=m.exports.default();if(!effects.length)return tree;effects.splice(0).forEach(f=>f());await tick();}throw Error('unsettled');}};
}
(async()=>{const h=overtime();const tree=await h.render();assert(h.reads.some(r=>r.startsWith('/overtime/monthly-hours?')),'Loading the limit must not abort on a nonexistent setter');assert(text(tree).includes('合成员工')&&text(tree).includes('45'),'Existing monthly warning must render');console.log('PASS static-only edits emit unchanged behavior; actual overtime limit load continues to monthly warnings.');})().catch(e=>{console.error(e);process.exitCode=1;});
