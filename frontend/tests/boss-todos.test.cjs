const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const ts=require('typescript'),React=require('react'),{execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'../..');
const source=fs.readFileSync(path.join(root,'frontend/src/components/BossTodos.tsx'),'utf8');
function harness(role='warehouse_admin'){
 let state=[],i=0,deps=[],ei=0,effects=[],cleanups=[],listeners={},calls=0;
 let response={advances:{count:3,items:[]},overtime:{count:2,items:[]}},failure=false;
 const m={exports:{}};
 const imports={react:{...React,useState(v){let k=i++;if(!(k in state))state[k]=v;return [state[k],v=>{state[k]=v;}];},useEffect(fn,d){let k=ei++;let key=JSON.stringify(d);if(deps[k]!==key){deps[k]=key;effects.push(fn);}}},'@/hooks/useAuth':{useAuth:()=>({user:{id:1,role}})},'@/lib/api':{api:{get:async route=>{calls++;assert.equal(route,'/dashboard/boss-todos');if(failure)throw Error('网络失败');return response;}}},'next/link':{__esModule:true,default:()=>null}};
 const events={addEventListener:(n,f)=>listeners[n]=f,removeEventListener:(n,f)=>{if(listeners[n]===f)delete listeners[n];}};
 vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module:m,exports:m.exports,require:n=>imports[n]||require(n),window:events,document:{...events,visibilityState:'visible'}});
 async function render(){i=ei=0;let out=m.exports.default();for(let f of effects.splice(0)){let cleanup=f();if(cleanup)cleanups.push(cleanup);}await new Promise(setImmediate);i=ei=0;return m.exports.default();}
 return {render,listeners,get calls(){return calls},set:(a,o)=>response={advances:{count:a,items:[]},overtime:{count:o,items:[]}},fail:()=>failure=true,cleanup:()=>cleanups.forEach(f=>f())};
}
function nodes(n){if(n==null||typeof n!=='object')return [];if(Array.isArray(n))return n.flatMap(nodes);return [n,...nodes(n.props?.children)];}
function text(n){if(n==null)return '';if(typeof n!=='object')return String(n);return Array.isArray(n)?n.map(text).join(''):text(n.props?.children);}
(async()=>{
 let count=0;
 for(let role of ['warehouse_admin','supervisor','staff']){
  let h=harness(role),tree=await h.render();assert(text(tree).includes('待批预支 3 笔'),text(tree));assert(text(tree).includes('待核实加班 2 条'));
  assert.deepEqual(nodes(tree).filter(n=>n.props?.href).map(n=>n.props.href),['/employee-advances?approval_status=pending','/overtime?pending_verification=true']);
  assert(text(tree).includes('待办（即时）'));h.set(4,2);await h.listeners['warehouse-changed']();tree=await h.render();assert(text(tree).includes('待批预支 4 笔'));
  h.set(2,1);await h.listeners.focus();tree=await h.render();assert(text(tree).includes('待批预支 2 笔'));assert(text(tree).includes('待核实加班 1 条'));
  h.set(0,0);await h.listeners.pageshow();tree=await h.render();assert(text(tree).includes('暂无待办'));
  h.fail();await h.listeners.visibilitychange();tree=await h.render();assert(text(tree).includes('网络失败'));assert(!text(tree).includes('暂无待办'));
  h.cleanup();assert.equal(Object.keys(h.listeners).length,0);count+=6;
 }
 for(let role of ['super_admin','warehouse_labor']){let h=harness(role);assert.equal(await h.render(),null);assert.equal(h.calls,0);count++;}
 // Existing write handlers are identical to round 19; new review calls reuse existing APIs.
 const emittedRuntime=(source,file)=>ts.transpileModule(source,{fileName:file,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const printer=ts.createPrinter();
 for(let file of ['employee-advances','overtime']){
  let name=`frontend/src/app/(dashboard)/${file}/page.tsx`;
  function functions(s){let out={};let sf=ts.createSourceFile(name,emittedRuntime(s,name),ts.ScriptTarget.Latest,true,ts.ScriptKind.JS);function visit(n){if(ts.isFunctionDeclaration(n)&&n.name&&!['load','review','handleCreate','loadRefs','EmployeeAdvancePage','OvertimePage'].includes(n.name.text))out[n.name.text]=printer.printNode(ts.EmitHint.Unspecified,n,sf);ts.forEachChild(n,visit);}visit(sf);return out;}
  assert.deepEqual(functions(fs.readFileSync(path.join(root,name),'utf8')),functions(execFileSync('git',['show','8dfc03f608f1c76927825d30da3838e3d4720244:'+name],{cwd:root,encoding:'utf8'})));count++;
 }
 console.log(`Boss todos: ${count} checks passed`);
})().catch(e=>{console.error(e);process.exit(1)});
