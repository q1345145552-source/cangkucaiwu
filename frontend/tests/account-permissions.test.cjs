// Start menu-permissions.fixture.py first. Uses the actual Settings component handlers + real local API.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const ts=require('typescript'),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const base=process.env.TEST_API_URL||'http://127.0.0.1:18080/api/v1';
assert.equal(new URL(base).hostname,'127.0.0.1');
const same=(a,b)=>assert.deepEqual(JSON.parse(JSON.stringify(a)),JSON.parse(JSON.stringify(b)));
async function http(method,route,token,body){const r=await fetch(base+route,{method,headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},...(body?{body:JSON.stringify(body)}:{})});const data=await r.json();return {status:r.status,data};}
async function login(name,password='test-password'){const r=await http('POST','/auth/login',null,{username:name,password});assert.equal(r.status,200,JSON.stringify(r));return r.data;}
const text=node=>node==null||typeof node==='boolean'?'':typeof node==='string'||typeof node==='number'?String(node):Array.isArray(node)?node.map(text).join(''):text(node.props?.children);
function walk(node){if(!node||typeof node!=='object')return [];if(Array.isArray(node))return node.flatMap(walk);return [node,...walk(node.props?.children)];}
function harness(user,token){
 let states=[],cursor=0,effectCursor=0,dependencies=[],effects=[],pending=[],errorMode=false;
 const messages=[];const moduleObject={exports:{}};
 const source=fs.readFileSync(path.resolve(__dirname,'../src/app/(dashboard)/settings/page.tsx'),'utf8');
 assert(!source.includes('PERM_LABELS'));
 const request=async(method,route,body)=>{if(errorMode&&route==='/users/permissions')throw new Error('simulated offline');const r=await http(method,route,token,body);if(r.status!==200)throw new Error(JSON.stringify(r));return r.data;};
 const api=Object.fromEntries(['get','post','put','delete'].map(method=>[method,(route,body)=>{const promise=request(method.toUpperCase(),route,body);pending.push(promise.catch(()=>{}));return promise;}]));
 const code=ts.transpileModule(source+'\nexport { PermissionCheckboxes };',{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
 vm.runInNewContext(code,{module:moduleObject,exports:moduleObject.exports,require(name){
  if(name==='react')return {...React,useState(initial){const i=cursor++;if(!(i in states))states[i]=initial;return [states[i],value=>states[i]=typeof value==='function'?value(states[i]):value];},useEffect(fn,deps){const i=effectCursor++;const key=JSON.stringify(deps);if(dependencies[i]!==key){dependencies[i]=key;effects.push(fn);}}};
  if(name==='@/hooks/useAuth')return {useAuth:()=>({user})};
  if(name==='@/hooks/useI18n')return {useI18n:()=>({t:k=>k})};
  if(name==='@/components/ui/Toast')return {useToast:()=>({toast:(...args)=>messages.push(args)})};
  if(name==='next/navigation')return {useRouter:()=>({push(){}})};
  if(name==='@/lib/api')return {api,getToken:()=>token};
  if(name==='@/components/ui/ConfirmDialog')return {__esModule:true,default:()=>null};
  return require(name);
 }});
 async function render(){cursor=0;effectCursor=0;let tree=moduleObject.exports.default();const work=effects;effects=[];work.forEach(fn=>fn());while(pending.length){const p=pending;pending=[];await Promise.all(p);}cursor=0;effectCursor=0;return moduleObject.exports.default();}
 const find=(tree,predicate)=>{const result=walk(tree).find(predicate);assert(result,'Element not found');return result;};
 const button=(tree,label)=>find(tree,n=>n.type==='button'&&text(n)===label);
 const field=(tree,label)=>{const div=find(tree,n=>n.type==='div'&&Array.isArray(n.props.children)&&n.props.children.some(c=>c?.type==='label'&&text(c).trim().startsWith(label))&&n.props.children.some(c=>['input','select'].includes(c?.type)));return div.props.children.find(c=>['input','select'].includes(c?.type));};
 const blocks=tree=>walk(tree).filter(n=>n.type===moduleObject.exports.PermissionCheckboxes);
 function checkGroups(block,registry){const elements=walk(moduleObject.exports.PermissionCheckboxes(block.props));const boxes=elements.filter(n=>n.type==='input');const groups=elements.filter(n=>n.type==='fieldset');assert.equal(groups.length,2);assert.equal(boxes.length,registry.filter(p=>p.selectable).length);assert.equal(walk(groups[0]).filter(n=>n.type==='input').length,8);same(elements.filter(n=>n.type==='label').map(text).sort(),registry.filter(p=>p.selectable).map(p=>p.label).sort());return boxes;}
 const toggle=(block,label)=>{const tree=moduleObject.exports.PermissionCheckboxes(block.props);const row=find(tree,n=>n.type==='label'&&text(n)===label);find(row,n=>n.type==='input').props.onChange();};
 return {render,button,field,blocks,find,toggle,checkGroups,messages,setOffline:value=>errorMode=value};
}
async function main(){
 const admin=await login('warehouse_admin');const token=admin.access_token;const user=(await http('GET','/auth/me',token)).data;const registry=(await http('GET','/users/permissions',token)).data;
 const h=harness(user,token);let tree=await h.render();h.button(tree,'用户管理').props.onClick();tree=await h.render();
 const change=(field,value)=>field.props.onChange({target:{value}});
 for(const role of ['supervisor','staff','warehouse_labor','warehouse_admin']){change(h.field(tree,'角色'),role);tree=await h.render();if(['staff','supervisor'].includes(role)){const boxes=h.checkGroups(h.blocks(tree)[0],registry);assert(boxes.every(b=>!b.props.checked));}else assert.equal(h.blocks(tree).length,0);}
 const created=[];
 for(const role of ['supervisor','staff']){
  change(h.field(tree,'角色'),role);tree=await h.render();const username='r8-'+role+'-'+Date.now();
  change(h.field(tree,'用户名'),username);tree=await h.render();change(h.field(tree,'显示名称'),'权限回归');tree=await h.render();change(h.field(tree,'密码'),'test-password');tree=await h.render();
  if(role==='supervisor')h.find(tree,n=>n.type==='input'&&n.props.type==='checkbox'&&!n.props.checked).props.onChange({target:{checked:true}});else change(h.field(tree,'所属仓库'),'1');
  tree=await h.render();const keys=['recharge','settings','leave'];const selected=keys.map(k=>registry.find(p=>p.menu_key===k).label);
  for(const label of selected){h.toggle(h.blocks(tree)[0],label);tree=await h.render();}
  await h.button(tree,'创建用户').props.onClick();tree=await h.render();assert(h.messages.some(m=>m[1]==='创建成功'),JSON.stringify(h.messages));
  const loginData=await login(username);same(loginData.extra_permissions,selected);created.push(loginData);
  const row=h.find(tree,n=>n.type==='tr'&&text(n).includes(username));h.find(row,n=>n.type==='button'&&text(n).trim()==='编辑').props.onClick();tree=await h.render();
  const edit=h.blocks(tree).at(-1);h.checkGroups(edit,registry);same(edit.props.selected,selected);
  const added=registry.find(p=>p.menu_key==='customers').label;h.toggle(edit,added);tree=await h.render();await h.button(tree,'保存').props.onClick();tree=await h.render();
  const fresh=await login(username);same(fresh.extra_permissions,[...selected,added]);
  const rowAgain=h.find(tree,n=>n.type==='tr'&&text(n).includes(username));h.find(rowAgain,n=>n.type==='button'&&text(n).trim()==='编辑').props.onClick();tree=await h.render();same(h.blocks(tree).at(-1).props.selected,fresh.extra_permissions);
  await h.button(tree,'保存').props.onClick();tree=await h.render();
  assert(h.checkGroups(h.blocks(tree)[0],registry).every(b=>!b.props.checked),'Creation success must clear all new selections');
 }
 // A failed catalogue fetch must be visible and must prevent saving an incomplete form.
 h.setOffline(true);h.button(tree,'个人设置').props.onClick();tree=await h.render();h.button(tree,'用户管理').props.onClick();tree=await h.render();assert.equal(h.button(tree,'创建用户').props.disabled,true);assert(h.blocks(tree)[0].props.error);
 h.setOffline(false);await h.blocks(tree)[0].props.onRetry();tree=await h.render();assert.equal(h.button(tree,'创建用户').props.disabled,false);
 // Password, warehouse reassignment, activation and deletion retain the existing real handlers/API contract.
 const newWh=await http('POST','/warehouses',token,{name:'权限回归仓',code:'R8-'+Date.now()});assert.equal(newWh.status,200,JSON.stringify(newWh));
 for(const u of created){
  const result=await http('PUT','/users/'+u.user_id,token,{password:'changed-test-password',warehouse_ids:[newWh.data.id],warehouse_id:newWh.data.id,is_active:false});assert.equal(result.status,200);
  assert.equal((await http('POST','/auth/login',null,{username:u.username,password:'changed-test-password'})).status,403);
  assert.equal((await http('PUT','/users/'+u.user_id,token,{is_active:true})).status,200);const moved=await login(u.username,'changed-test-password');assert.equal(moved.warehouse_id,newWh.data.id);
  if(u.role==='staff')assert.equal((await http('DELETE','/users/'+u.user_id,token)).status,200);
 }
 fs.writeFileSync('/tmp/r8-created-accounts.json',JSON.stringify(created.map(u=>({username:u.username,user_id:u.user_id})),null,2));
 console.log(JSON.stringify({selectable:registry.filter(p=>p.selectable).length,finance:8,business:25,roleDefaults:'PASS',createEditRoundtrip:'PASS',loadFailureAndRetry:'PASS',passwordWarehouseActivationDelete:'PASS'},null,2));
}
main().catch(e=>{console.error(e);process.exitCode=1});
