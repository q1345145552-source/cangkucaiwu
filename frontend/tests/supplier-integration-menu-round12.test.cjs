const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript'),React=require('react'),{execFileSync}=require('node:child_process');
const file='frontend/src/components/layout/DashboardLayout.tsx',root=path.resolve(__dirname,'../..'),source=fs.readFileSync(path.join(root,file),'utf8'),baseline=execFileSync('git',['show','4be718d0ce258d6818c58a927e3fcdb9b65fb760:'+file],{cwd:root,encoding:'utf8'});
const emittedRuntime=(source,file)=>ts.transpileModule(source,{fileName:file,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
assert.equal(emittedRuntime(source,file),emittedRuntime(execFileSync('git',['show','b20c6c848f68c23098149f1d920f35baa6546d75:'+file],{cwd:root,encoding:'utf8'}),file),'R12 must not change navigation layout or menu order');
const added=source.split('\n').filter(x=>x.includes('key: "inventory"'));assert.equal(added.length,1);assert.equal(emittedRuntime(source.replace(added[0]+'\n',''),file),emittedRuntime(baseline,file),'Only the new inventory entry may alter the existing navigation');
const registry=JSON.parse(fs.readFileSync(process.env.INVENTORY_REGISTRY_FILE||'/tmp/supplier12-menu-registry.json','utf8')),entry=registry.find(x=>x.menu_key==='inventory');assert(entry&&entry.selectable&&entry.path==='/inventory');assert.deepEqual(entry.default_roles,['warehouse_admin']);
const m={exports:{}},code=ts.transpileModule(source+'\nexport {filterNavItems,navItems};',{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
vm.runInNewContext(code,{module:m,exports:m.exports,require:n=>n==='react'?React:n==='next/navigation'?{}:n==='next/link'?{__esModule:true,default:'a'}:n==='@/components/ui/BackToTop'?{__esModule:true,default:()=>null}:n==='@/hooks/useI18n'?{}:n==='@/lib/api'?{}:require(n),console,process:{env:{}}});
const {filterNavItems,navItems}=m.exports,leaves=x=>x.flatMap(i=>i.children?leaves(i.children):[i]),has=(role,perms,meta=registry)=>leaves(filterNavItems(navItems,{id:1,role,extra_permissions:perms},meta)).some(x=>x.key==='inventory');
assert(has('warehouse_admin',[]));for(const role of ['supervisor','staff']){assert(!has(role,[]));assert(has(role,[entry.label]));assert(!has(role,['供应商管理']));assert(!has(role,[entry.label],[]));}assert(!has('warehouse_labor',[entry.label]));assert(!has('super_admin',[entry.label]));

const all=registry.filter(p=>p.selectable).map(p=>p.label),visible=(role,perms)=>Array.from(leaves(filterNavItems(navItems,{id:1,role,extra_permissions:perms},registry)));
const proof={};
for(const role of ['warehouse_admin','super_admin','supervisor','staff','warehouse_labor']){
 const empty=visible(role,[]),full=visible(role,all);
 assert(!full.some(x=>/operations|receivables|shipments/.test(x.href||'')));
 proof[role]={none:empty.map(x=>({key:x.key,path:x.href})),all:full.map(x=>({key:x.key,path:x.href}))};
 if(['staff','supervisor'].includes(role)){
  assert.deepEqual(empty.map(x=>x.href),['/dashboard']);
  for(const key of ['suppliers','sku_catalog','inventory','payable','payment_plans']){
   const meta=registry.find(x=>x.menu_key===key),one=visible(role,[meta.label]);
   assert.deepEqual(one.map(x=>x.href),['/dashboard',meta.path]);
  }
  assert(full.some(x=>x.key==='payable')&&full.some(x=>x.key==='payment_plans'));
 }else assert.deepEqual(empty.map(x=>x.href),full.map(x=>x.href),'Extra grants must not expand other roles');
 if(role==='warehouse_labor')assert.deepEqual(full.map(x=>x.href).filter(x=>x!=='/dashboard'),['/attendance','/overtime','/clock-in','/my-payslip']);
 if(role==='super_admin')assert(!full.some(x=>['suppliers','inventory','sku_catalog','payable','payment_plans'].includes(x.key)));
}
const daily=filterNavItems(navItems,{id:1,role:'warehouse_admin',extra_permissions:[]},registry).find(x=>x.key==='finance_daily_group');assert.deepEqual(Array.from(daily.children.slice(0,2),x=>x.key),['payable','payment_plans']);
fs.writeFileSync(process.env.SUPPLIER12_MENU_REPORT||'/tmp/supplier12-menu-actual.json',JSON.stringify(proof,null,2));
console.log('PASS R12 actual registry/current unchanged navigation: 5 roles, empty/full grants, each supplier/SKU/inventory/payable/plan alone, retired entries absent, personal 4 pages, daily finance grouping.');
