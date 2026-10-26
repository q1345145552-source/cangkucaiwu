const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript'),React=require('react');
const root=path.resolve(__dirname,'../src');
function compile(file,imports={},globals={}){const m={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(root,file),'utf8'),{fileName:file,compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module:m,exports:m.exports,require:n=>imports[n]||require(n),console,...globals});return m.exports;}
const authTypes=compile('types/auth.ts');
const roles=['warehouse_admin','super_admin','supervisor','staff','warehouse_labor'];
function user(role='supervisor'){return{id:4,username:'synthetic-user',display_name:'测试账号',role,warehouse_id:1,warehouse_name:'合成仓',warehouses:[{id:1,name:'合成仓',code:'LOCAL'}],extra_permissions:['供应商管理','耗材库存'],is_active:true,attendance_enabled:role==='supervisor',attendance_employee_id:role==='supervisor'?20:null};}
for(const role of roles)assert(authTypes.isAuthUser(user(role)));
for(const bad of[null,[],{},'null', {...user(),role:'owner'}, {...user(),id:1.5}, {...user(),warehouse_id:'1'}, {...user(),warehouses:[{id:2,name:'缺编号'}]}, {...user(),extra_permissions:[1]}, {...user(),attendance_enabled:'false'}, {...user(),attendance_employee_id:'20'}])assert(!authTypes.isAuthUser(bad),JSON.stringify(bad));
function harness({cached,token:initialToken=null}={}){
 const local=new Map();if(cached!==undefined)local.set('user',typeof cached==='string'?cached:JSON.stringify(cached));if(initialToken)local.set('token',initialToken);
 const storage={getItem:k=>local.get(k)||null,setItem:(k,v)=>local.set(k,String(v)),removeItem:k=>local.delete(k)};
 const events=new EventTarget(),effects=[],cleanups=[],state=[],calls=[],routes=[];let index=0,initialized=false,value=null,context;let token=initialToken,failLogin=false,failLogout=false;
 const react={...React,createContext(initial){context={Provider:'auth-provider',value:initial};return context;},useContext:()=>value,useState(initial){const i=index++;if(!(i in state))state[i]=initial;return[state[i],next=>state[i]=typeof next==='function'?next(state[i]):next];},useEffect(fn){if(!initialized)effects.push(fn);}};
 let response={...user(),user_id:4,access_token:'synthetic-only-token',token_type:'bearer'};
 const api={async post(route,body){calls.push({route,body});if(route==='/auth/login'){if(failLogin)throw Error('账号已被禁用');return response;}if(failLogout)throw Error('附件会话清理失败');return{ok:true};}};
 const module=compile('hooks/useAuth.tsx',{'react':react,'next/navigation':{useRouter:()=>({push:p=>routes.push(p)})},'@/types/auth':authTypes,'@/lib/api':{api,getToken:()=>token,setToken:t=>{token=t;storage.setItem('token',t);},clearToken:()=>{token=null;for(const key of['token','user','activeWarehouseId'])storage.removeItem(key);},setActiveWarehouseId:id=>storage.setItem('activeWarehouseId',id)}},{localStorage:storage,window:events});
 function render(){index=0;const tree=module.AuthProvider({children:'child'});value=tree.props.value;initialized=true;return value;}
 render();effects.splice(0).forEach(f=>{const cleanup=f();if(cleanup)cleanups.push(cleanup);});
 return{render,get auth(){return module.useAuth();},outside(){value=null;return module.useAuth();},get token(){return token;},local,calls,routes,event(detail){events.dispatchEvent(new CustomEvent('auth-user-refreshed',{detail}));},response(v){response=v;},failLogin(){failLogin=true;},failLogout(){failLogout=true;},cleanup(){cleanups.forEach(f=>f());}};
}
(async()=>{
 const valid=user();const cached=harness({cached:valid,token:'old-synthetic'});assert.deepEqual(JSON.parse(JSON.stringify(cached.render().user)),valid);assert.equal(cached.auth.loading,false);assert(cached.auth.isAuthenticated);
 cached.event({...valid,extra_permissions:[]});assert.deepEqual(cached.render().user.extra_permissions,[],'Live revocation must replace cached grants');
 cached.event({...valid,attendance_enabled:false,attendance_employee_id:null});assert.equal(cached.render().user.attendance_enabled,false);
 cached.event({...valid,role:'made-up-role'});assert.equal(cached.render().user.attendance_enabled,false,'Malformed event must not replace valid identity');
 cached.event(null);assert.equal(cached.render().user,null);assert.equal(cached.auth.isAuthenticated,false);
 cached.cleanup();cached.event(valid);assert.equal(cached.render().user,null,'Unmount removes refresh listener');
 assert.throws(()=>cached.outside(),/AuthProvider/);
 for(const bad of['{broken',JSON.stringify({...valid,role:'invalid'}),'null']){const h=harness({cached:bad,token:'old-synthetic'});assert.equal(h.render().user,null);assert(!h.auth.isAuthenticated);}
 const withoutToken=harness({cached:valid});assert.equal(withoutToken.render().user,null);
 for(const role of roles){const h=harness();h.response({...user(role),user_id:4,access_token:'synthetic-only-token',token_type:'bearer'});await h.auth.login('synthetic-user','synthetic-password');const context=h.render();assert.equal(context.user.role,role);assert.equal(context.user.attendance_enabled,role==='supervisor');assert.equal(h.local.get('activeWarehouseId'),'1');assert.equal(JSON.parse(h.local.get('user')).role,role);assert.equal(h.routes.at(-1),role==='warehouse_labor'?'/clock-in':'/dashboard');assert.equal(h.calls[0].route,'/auth/login');h.failLogout();await h.auth.logout();assert.equal(h.render().user,null);assert.equal(h.token,null);assert.equal(h.local.get('user'),undefined);assert.equal(h.local.get('activeWarehouseId'),undefined);assert.equal(h.routes.at(-1),'/login');}
 const denied=harness();denied.failLogin();await assert.rejects(denied.auth.login('synthetic-user','wrong'),/账号已被禁用/);assert.equal(denied.render().user,null);assert.equal(denied.token,null);assert.equal(denied.routes.length,0);
 console.log('PASS typed AuthProvider: 5 roles login/logout, employee redirect and flags, warehouses, cached identity, missing/corrupt cache, live permission revocation/attendance disabling, malformed event, listener cleanup, context misuse, rejected login and failed cookie cleanup.');
})().catch(e=>{console.error(e);process.exitCode=1;});
