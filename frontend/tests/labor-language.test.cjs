// Execute the real localization hook: an old Chinese preference must not reopen Chinese for labor.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const ts=require('typescript');
const base=path.resolve(__dirname,'../src');
function harness(role,personal=false){
 let values=[],deps=[],effects=[],cleanups=[],index=0,ei=0;
 const store=new Map([['user',JSON.stringify({role})],['locale','zh']]),listeners=new Map();
 const react={useState(initial){const i=index++;if(!(i in values))values[i]=typeof initial==='function'?initial():initial;return[values[i],v=>values[i]=typeof v==='function'?v(values[i]):v];},
  useEffect(fn,input){const i=ei++,key=JSON.stringify(input);if(deps[i]!==key){deps[i]=key;effects.push(()=>{cleanups[i]?.();cleanups[i]=fn();});}},useCallback:fn=>fn};
 const m={exports:{}};
 const source=ts.transpileModule(fs.readFileSync(path.join(base,'hooks/useI18n.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText;
 const load=n=>n==='react'?react:n.startsWith('@/i18n/')?JSON.parse(fs.readFileSync(path.join(base,n.slice(2)),'utf8')):require(n);
 const window={addEventListener:(key,fn)=>{if(!listeners.has(key))listeners.set(key,new Set());listeners.get(key).add(fn);},removeEventListener:(key,fn)=>listeners.get(key)?.delete(fn),dispatchEvent:e=>listeners.get(e.type)?.forEach(fn=>fn(e))};
 vm.runInNewContext(source,{module:m,exports:m.exports,require:load,window,localStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)},CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail;}}});
 return {window,async render(){for(let n=0;n<10;n++){index=ei=0;const hook=m.exports.useI18n(personal);if(!effects.length)return hook;effects.splice(0).forEach(fn=>fn());await new Promise(r=>setTimeout(r,0));}throw Error('Hook did not settle');}};
}
(async()=>{
 const layoutModule={exports:{}};
 const layoutSource=ts.transpileModule(fs.readFileSync(path.join(base,'app/layout.tsx'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 const layoutRequire=n=>n.endsWith('.css')?{}:n==='./client-shell'?()=>null:n.startsWith('@/i18n/')?JSON.parse(fs.readFileSync(path.join(base,n.slice(2)),'utf8')):require(n);
 vm.runInNewContext(layoutSource,{module:layoutModule,exports:layoutModule.exports,require:layoutRequire});
 const html=layoutModule.exports.default({children:null});
 const script=html.props.children.props.children.find(child=>child?.type==='script').props.dangerouslySetInnerHTML.__html;
 for (const [role,saved,expected] of [['warehouse_labor','zh','my'],['warehouse_labor','th','th'],['warehouse_admin','zh','zh']]) {
  const splash={textContent:'海外仓财务管理系统'},doc={title:'海外仓财务管理系统',documentElement:{lang:'zh'},querySelector:()=>splash};
  vm.runInNewContext(script,{document:doc,localStorage:{getItem:k=>k==='user'?JSON.stringify({role}):saved}});
  assert.equal(doc.documentElement.lang,expected);
  if(role==='warehouse_labor'){assert(!/[\u3400-\u9fff]/.test(splash.textContent));assert.equal(doc.title,splash.textContent);}
  else assert.equal(splash.textContent,'海外仓财务管理系统');
 }
 for(const personal of [false,true]){
  const h=harness('warehouse_labor',personal);let hook=await h.render();assert.equal(hook.locale,'my');
  for(const key of ['app_name','change_password','role_warehouse_labor','attendance','overtime','my_payslip'])assert(!/[\u3400-\u9fff]/.test(hook.t(key)));
  hook.setLocale('zh');hook=await h.render();assert.equal(hook.locale,'my');
  h.window.dispatchEvent({type:personal?'employee-locale-changed':'locale-changed',detail:{locale:'zh'}});hook=await h.render();assert.equal(hook.locale,'my');
  hook.setLocale('th');hook=await h.render();assert.equal(hook.locale,'th');
  hook.toggleLocale();hook=await h.render();assert.equal(hook.locale,'my');
  hook.toggleLocale();hook=await h.render();assert.equal(hook.locale,'th');
 }
 const manager=harness('warehouse_admin');assert.equal((await manager.render()).locale,'zh');
 console.log('PASS: actual launch script and localization hook reject Chinese for labor before hydration, preserve Thai/Myanmar toggles, translate own-page labels and preserve manager Chinese');
})().catch(e=>{console.error(e);process.exitCode=1;});
