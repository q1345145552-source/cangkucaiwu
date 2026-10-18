// Uses the real layout, React rendering, and an isolated running backend.
// NODE_PATH=/path/to/node_modules node tests/menu-permissions.test.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const same = (a,b,message) => assert.deepEqual(JSON.parse(JSON.stringify(a)),JSON.parse(JSON.stringify(b)),message);
const path = require('node:path');
const vm = require('node:vm');
const { execFileSync } = require('node:child_process');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');
const sourcePath = path.resolve(__dirname, '../src/components/layout/DashboardLayout.tsx');
const source = fs.readFileSync(sourcePath, 'utf8');
const baseline = execFileSync('git', ['show', '03dd578:frontend/src/components/layout/DashboardLayout.tsx'], {encoding:'utf8'});
const navDeclaration = s => s.slice(s.indexOf('const navItems:'), s.indexOf('\n];', s.indexOf('const navItems:')) + 3);
const normalizeHistoryRoles = s => s.split('\n').filter(line=>!line.includes('key: "cash_advances"')).join('\n').replace('href: "/modification-logs", roles: ["warehouse_admin", "super_admin", "supervisor", "staff"]', 'href: "/modification-logs", roles: ["warehouse_admin"]');
assert.equal(navDeclaration(normalizeHistoryRoles(source)), navDeclaration(baseline), 'Menu paths, icons, order, labels and role rules must remain unchanged');
assert(!source.includes('STAFF_EXTRA_MAP'));
assert(source.includes('"/users/permissions"'));
let states = [], cursor = 0;
const moduleObject = {exports:{}};
const code = ts.transpileModule(source + '\nexport { filterNavItems, navItems };', {
 compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}
}).outputText;
vm.runInNewContext(code, {module:moduleObject,exports:moduleObject.exports,require(name) {
 if(name==='react')return {...React,useState:()=>[states[cursor++],()=>{}],useEffect:()=>{}};
 if(name==='next/navigation')return {useRouter:()=>({push(){}}),usePathname:()=>'/dashboard'};
 if(name==='next/link')return {__esModule:true,default:({children,...props})=>React.createElement('a',props,children)};
 if(name==='@/hooks/useI18n')return {useI18n:()=>({t:k=>k,locale:'zh',setLocale(){}})};
 if(name==='@/components/ui/BackToTop')return {__esModule:true,default:()=>null};
 if(name==='@/lib/api')return {api:{},getToken(){},getActiveWarehouseId(){},setActiveWarehouseId(){}};
 return require(name);
}});
const {default:Layout,filterNavItems,navItems} = moduleObject.exports;
const leaves = tree => tree.flatMap(item=>item.children?leaves(item.children):[item]);
const legacy = (tree,role)=>tree.filter(x=>x.roles.includes(role)).map(x=>x.children?{...x,children:legacy(x.children,role)}:x);
const hrefs = tree=>leaves(tree).map(x=>x.href);
function render(user,permissions,mobile,group=null,dropdown=false) {
 states=[true,mobile,group,dropdown,false,false,[],null,false,user,mobile,permissions];cursor=0;
 return renderToStaticMarkup(React.createElement(Layout,null,React.createElement('p',null,'page content')));
}
function renderedHrefs(html) {
 const nav=html.match(/<nav\b[^>]*>([\s\S]*?)<\/nav>/);assert(nav,'Sidebar must render');
 return [...nav[1].matchAll(/<a\b[^>]*href="([^"]+)"/g)].map(x=>x[1]);
}
function checkRendered(user,registry,mobile) {
 const filtered=filterNavItems(navItems,user,registry);
 for(const group of [null,...filtered.filter(x=>x.children).map(x=>x.key)]) {
  const expected=filtered.flatMap(x=>x.children?(x.key===group?hrefs(x.children):[]):[x.href]);
  same(renderedHrefs(render(user,registry,mobile,group)),expected);
 }
 const html=render(user,registry,mobile,null,true);
 if(['staff','supervisor'].includes(user.role))assert.equal(html.includes('users_management'),user.extra_permissions.includes(registry.find(x=>x.menu_key==='settings').label));
 assert(html.includes('change_password'),'Personal change-password entry stays available');
 return hrefs(filtered);
}
const base=process.env.TEST_API_URL||'http://127.0.0.1:18080/api/v1';
assert.equal(new URL(base).hostname,'127.0.0.1','Only local isolated test backends are allowed');
async function request(route,token,body) {
 const r=await fetch(base+route,{method:body?'POST':'GET',headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},...(body?{body:JSON.stringify(body)}:{})});
 assert.equal(r.status,200,route+': '+await r.clone().text());return r.json();
}
async function main(){
 const admin=await request('/auth/login',null,{username:'warehouse_admin',password:'test-password'});
 const registry=await request('/users/permissions',admin.access_token);
 const selectable=registry.filter(p=>p.selectable);
 let scenarios=0;const report=[];
 for(const role of ['supervisor','staff']) {
  for(const p of [{menu_key:'none'},{menu_key:'all'},...selectable]) {
   // Real fresh login for each individual permission; /me supplies the current DB permissions.
   const login=await request('/auth/login',null,{username:role+'_'+p.menu_key,password:'test-password'});
   const user=await request('/auth/me',login.access_token);
   const list=await request('/users/permissions',login.access_token);
   const actual=hrefs(filterNavItems(navItems,user,list));
   const expected=leaves(navItems).filter(item=>{
    if(item.roles.every(r=>r==='warehouse_labor'))return false;
    const meta=list.find(m=>m.menu_key===item.key);
    if(!meta)return false;
    if(!meta.selectable)return item.roles.includes(role);
    return p.menu_key==='all'||(p.menu_key!=='none'&&meta.path===p.path);
   }).map(x=>x.href);
   same(actual,expected,role+': '+p.menu_key);
   for(const mobile of [false,true]){same(checkRendered(user,list,mobile),expected);scenarios++;}
   report.push({role,key:p.menu_key,label:p.label||p.menu_key,menus:actual,status:'PASS'});
  }
 }
 for(const [username,role] of [['warehouse_admin','warehouse_admin'],['super_admin','super_admin'],['labor1','warehouse_labor']]) {
  const login=await request('/auth/login',null,{username,password:'test-password'});
  const user=await request('/auth/me',login.access_token);
  const expected=hrefs(legacy(navItems,role));
  for(const perms of [[],selectable.map(p=>p.label)]) {
   user.extra_permissions=perms;
   same(hrefs(filterNavItems(navItems,user,[])),expected,'Registry outage must not change '+role+' menus');
   for(const mobile of [false,true]){same(checkRendered(user,registry,mobile),expected);scenarios++;}
  }
 }
 for(const role of ['staff','supervisor'])assert.equal(filterNavItems(navItems,{role,extra_permissions:selectable.map(x=>x.label)},[]).length,0,'Unknown registry must not reveal menus');
 fs.writeFileSync('/tmp/r7-menu-results.json',JSON.stringify(report,null,2));
 console.log(JSON.stringify({selectablePermissions:selectable.length,freshLogins:report.length,desktopMobileScenarios:scenarios,result:'PASS'},null,2));
}
main().catch(error=>{console.error(error);process.exitCode=1});
