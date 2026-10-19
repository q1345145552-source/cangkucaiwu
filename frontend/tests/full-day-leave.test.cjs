// Exercise the actual clock page with changing leave status and all three dictionaries.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript'),React=require('react');
const source=fs.readFileSync(path.join(__dirname,'../src/app/(dashboard)/clock-in/page.tsx'),'utf8');
const walk=x=>!x||typeof x!=='object'?[]:Array.isArray(x)?x.flatMap(walk):[x,...walk(x.props?.children)];
const text=x=>x==null||typeof x==='boolean'?'':typeof x!=='object'?String(x):Array.isArray(x)?x.map(text).join(''):text(x.props?.children);
function harness(locale,approved){
 let state=[],deps=[],effects=[],index=0,ei=0,reads=0,camera=0,posts=0;const messages=[];
 const dict=JSON.parse(fs.readFileSync(path.join(__dirname,'../src/i18n',locale+'.json'),'utf8'));
 const mock={...React,useState(v){const i=index++;if(!(i in state))state[i]=typeof v==='function'?v():v;return[state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];},useRef:()=>({current:{click(){camera++;},value:''}}),useEffect(fn,d){const i=ei++,key=JSON.stringify(d);if(deps[i]!==key){deps[i]=key;effects.push(fn);}}};
 const api={get:async()=>{reads++;return{completed:{},sessions:[1,2,3,4].map(session=>({session,time:'09:00'})),full_day_leave:approved}}};
 const imports={react:mock,'@/lib/api':{api,getToken:()=> 'test-token'},'@/hooks/useAuth':{useAuth:()=>({user:{display_name:'测试员工'}})},'@/hooks/useI18n':{useI18n:()=>({t:k=>dict[k]||k,locale,setLocale(){}})},'@/components/ui/Toast':{useToast:()=>({toast:(...x)=>messages.push(x)})},'next/navigation':{useRouter:()=>({push(){}})},'@/lib/thai-time':{formatThaiTime:()=> '09:00:00'},'@/components/SafeImage':{__esModule:true,default:()=>null}};
 const module={exports:{}};vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module,exports:module.exports,require:n=>imports[n]||require(n),console,Date,FormData,setInterval:()=>1,clearInterval(){},FileReader:class {readAsDataURL(){this.result='data:image/png;base64,AA==';this.onload();}},fetch:async()=>{posts++;approved=true;return{ok:false,json:async()=>({detail:'已请全天假'})};}});
 return {dict,messages,get camera(){return camera;},get posts(){return posts;},get reads(){return reads;},async render(){await new Promise(resolve=>setTimeout(resolve,0));for(let i=0;i<8;i++){index=ei=0;const tree=module.exports.default();if(!effects.length)return tree;await Promise.all(effects.splice(0).map(f=>f()));await new Promise(resolve=>setTimeout(resolve,0));}throw Error('Effects did not settle');}};
}
(async()=>{
 for(const locale of ['zh','my','th']){
  const h=harness(locale,true),tree=await h.render();
  const buttons=walk(tree).filter(n=>n.type==='button'&&n.props.title===h.dict.clock_full_day_leave);
  assert.equal(buttons.length,4);assert(buttons.every(n=>n.props.disabled&&n.props.className.includes('bg-gray-400')));
  for(const b of buttons)b.props.onClick();assert.equal(h.camera,0);assert.equal(h.posts,0);
  assert(text(tree).includes(h.dict.clock_full_day_leave));assert(!h.dict.clock_full_day_leave.includes('今日')||locale==='zh');
 }
 const h=harness('th',false);let tree=await h.render();
 const camera=walk(tree).find(n=>n.type==='button'&&n.props.title===h.dict.clock_take_photo);assert.equal(Boolean(camera.props.disabled),false);camera.props.onClick();
 tree=await h.render();walk(tree).find(n=>n.type==='input'&&n.props.type==='file').props.onChange({target:{files:[{}]}});
 tree=await h.render();await walk(tree).find(n=>n.type==='button'&&text(n)===h.dict.clock_confirm).props.onClick();tree=await h.render();
 assert.equal(h.posts,1);assert(h.reads>=2,'A server rejection refreshes the leave guard');
 assert.equal(walk(tree).filter(n=>n.type==='button'&&n.props.title===h.dict.clock_full_day_leave&&n.props.disabled).length,4);
 const attendance=fs.readFileSync(path.join(__dirname,'../src/app/(dashboard)/attendance/page.tsx'),'utf8');assert.equal((attendance.match(/if \(r\.warning\) window\.alert\(r\.warning\)/g)||[]).length,2);
 console.log('PASS: zh/my/th full-day notice, four grey disabled buttons, no camera or post while blocked, half/pending enabled, approval after page load rejected and refreshed, approval/proxy warnings displayed');
})().catch(e=>{console.error(e);process.exitCode=1;});
