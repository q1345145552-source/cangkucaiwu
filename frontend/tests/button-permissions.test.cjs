// Real page rendering and original handlers against the isolated local test backend.
// Start menu-permissions.fixture.py; set NODE_PATH to the installed frontend dependencies.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {execFileSync}=require('node:child_process');
const ts=require('typescript'),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const base=require('./legacy-regression-support.cjs').testBase();
assert.equal(new URL(base).hostname,'127.0.0.1','Only isolated local test backends');
const root=path.resolve(__dirname,'..');
const pages={employees:'employees','salary-templates':'salary_templates','deduction-templates':'deduction_templates','labor-efficiency':'labor_efficiency','employee-deductions':'employee_deductions','employee-advances':'employee_advances',concentration:'concentration'};
async function http(method,route,token,body){const r=await fetch(base+route,{method,headers:{'Content-Type':'application/json',Authorization:'Bearer '+token,'X-Warehouse-ID':'1'},...(body!==undefined?{body:JSON.stringify(body)}:{})});return {status:r.status,data:await r.json()};}
async function login(username){const r=await http('POST','/auth/login','',{username,password:'test-password'});assert.equal(r.status,200);const me=await http('GET','/auth/me',r.data.access_token);return {token:r.data.access_token,user:me.data};}
function load(source,imports,extra={}){const m={exports:{}};vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module:m,exports:m.exports,require:n=>imports[n]||require(n),console,Date,URL,URLSearchParams,confirm:()=>true,alert(){},window:{location:{search:''}},...extra});return m.exports;}
const hookSource=fs.readFileSync(path.join(root,'src/hooks/useMenuPermission.ts'),'utf8');
function harness(page,identity,readToken=identity.token,{offline=false,registryOverride}={}){
 let states=[],cursor=0,ec=0,deps=[],effects=[],pending=[],dirty=false;const messages=[],writes=[];
 const react={...React,useState(initial){const i=cursor++;if(!(i in states))states[i]=typeof initial==='function'?initial():initial;return [states[i],v=>{states[i]=typeof v==='function'?v(states[i]):v;dirty=true;}];},useEffect(fn,ds){const i=ec++,key=JSON.stringify(ds);if(deps[i]!==key){deps[i]=key;effects.push(fn);}},useRef:()=>({current:null}),useCallback:fn=>fn};
 const request=async(method,route,body)=>{if(route==='/users/permissions'&&offline)throw Error('offline');if(route==='/users/permissions'&&registryOverride)return registryOverride;const r=await http(method,route,method==='GET'?readToken:identity.token,body);if(method!=='GET')writes.push({method,route,...r});if(r.status!==200)throw Error(JSON.stringify(r));return r.data;};
 const api=Object.fromEntries(['get','post','put','delete'].map(method=>[method,(route,body)=>{const p=request(method.toUpperCase(),route,body);pending.push(p.catch(()=>{}));return p;}]));
 const imports={react,'@/lib/balanceWarning':require('./balance-warning-test-support.cjs'),'next/navigation':{useRouter:()=>({push(){}})},'@/lib/api':{api,getToken:()=>identity.token,getActiveWarehouseId:()=>1},'@/hooks/useAuth':{useAuth:()=>({user:identity.user})},'@/hooks/useI18n':{useI18n:()=>({t:k=>k})},'@/components/ui/Toast':{useToast:()=>({toast:(...args)=>messages.push(args)})},'@/components/SafeImage':{__esModule:true,default:()=>null},'@/lib/image':{compressImage:async file=>file},'@/lib/currency':requireCurrency(),'@/components/CashAdvanceLink':require('./cash-advance-link-test-support.cjs'),'@/lib/thai-time':load(fs.readFileSync(path.join(root,'src/lib/thai-time.ts'),'utf8'),{})};
 const hook=load(hookSource,imports);imports['@/hooks/useMenuPermission']=hook;
 const source=fs.readFileSync(path.join(root,'src/app/(dashboard)',page,'page.tsx'),'utf8');const Component=load(source,imports).default;
 const expand=n=>n==null||typeof n!=='object'?n:Array.isArray(n)?n.map(expand):typeof n.type==='function'?expand(n.type(n.props)):React.cloneElement(n,{},...React.Children.toArray(n.props?.children).map(expand));
 async function render(){let tree;for(let round=0;round<12;round++){dirty=false;cursor=0;ec=0;tree=expand(Component());const work=effects;effects=[];work.forEach(fn=>fn());while(pending.length){const work=pending;pending=[];await Promise.all(work);await new Promise(resolve=>setImmediate(resolve));}if(!dirty&&!effects.length)break;}return tree;}
 return {render,messages,writes,identity};
}
function requireCurrency(){return load(fs.readFileSync(path.join(root,'src/lib/currency.ts'),'utf8'),{});}
const text=n=>n==null||typeof n==='boolean'?'':typeof n==='string'||typeof n==='number'?String(n):Array.isArray(n)?n.map(text).join(''):text(n.props?.children);
const walk=n=>!n||typeof n!=='object'?[]:Array.isArray(n)?n.flatMap(walk):[n,...walk(n.props?.children)];
const find=(tree,pred)=>{const n=walk(tree).find(pred);assert(n,'Element not found');return n;};
const button=(tree,label)=>find(tree,n=>n.type==='button'&&(n.props.title===label||text(n).trim()===label));
const field=(tree,label)=>{const div=find(tree,n=>n.type==='div'&&Array.isArray(n.props.children)&&n.props.children.some(c=>c?.type==='label'&&text(c).trim().startsWith(label))&&n.props.children.some(c=>['input','select'].includes(c?.type)));return div.props.children.find(c=>['input','select'].includes(c?.type));};
const change=(el,value)=>el.props.onChange({target:{value}});
function actionCount(tree,page){return walk(tree).filter(n=>n.type==='button'&&n.props.onClick&&(/openCreate|openEdit|handleDelete|setShowForm|editEmployee|openResignModal|setDeleteTarget|saveStandard|openOrderModal|openSupplement/.test(n.props.onClick.toString()))).length;}
async function main(){
 const admin=await login('warehouse_admin');const registry=(await http('GET','/users/permissions',admin.token)).data;
 const pure=load(hookSource,{'react':React,'@/lib/api':{},'@/hooks/useAuth':{}}).hasMenuPermission;
 assert.equal(pure({role:'super_admin'},'employees',registry),false,'Ordinary super-admin must not receive business buttons when the backend refuses the module');
 for(const key of ['settings','audit_logs','modification_logs','market','group_order'])assert(pure({role:'super_admin'},key,registry),key+' platform exception must remain');
 assert(!pure({role:'super_admin'},'settings',[]),'Catalogue outage must fail closed');
 for(const role of ['staff','supervisor'])for(const [page,key]of Object.entries(pages)){
  const renamed=registry.map(p=>p.menu_key===key?{...p,label:'后端临时改名测试'}:p);
  assert(pure({role,extra_permissions:['后端临时改名测试']},key,renamed));
  assert(!pure({role,extra_permissions:[registry.find(p=>p.menu_key===key).label]},key,renamed));
 }
 let scenarios=0;const report=[];
 for(const username of ['supervisor_all','staff_all','supervisor_none','staff_none','warehouse_admin','super_admin','labor1']){
  const who=await login(username),allowed=['supervisor_all','staff_all','warehouse_admin'].includes(username);
  for(const page of Object.keys(pages)){
   // Admin read snapshots deliberately leave data visible even for denied identities:
   // hidden menus or a denied list request must not be the reason buttons disappear.
   const h=harness(page,who,admin.token),tree=await h.render(),count=actionCount(tree,page);
   if(page==='concentration')assert.equal(count,0);else if(allowed)assert(count>0,username+' '+page+' buttons missing');else assert.equal(count,0,username+' '+page+' leaked write buttons');
   if(page==='employees'){
    if(allowed){for(const label of ['新建员工','编辑','离职','删除'])button(tree,label);}
    const row=find(tree,n=>n.type==='tr'&&text(n).includes('员工1')&&n.props.onClick);row.props.onClick();const detail=await h.render();
    assert.equal(walk(detail).filter(n=>n.type==='input'&&n.props.type==='file').length,allowed?3:0,username+' photo upload');
    assert.equal(walk(detail).filter(n=>n.props?.placeholder==='添加标签...').length,allowed?1:0);
    assert.equal(walk(detail).filter(n=>n.props?.placeholder==='项目名称（如 宿舍费）').length,allowed?1:0);
   }
   if(page==='labor-efficiency')assert.equal(walk(tree).filter(n=>n.type==='input'&&n.props.onBlur).length,allowed?13:0,'Monthly standards must not be editable without permission');
   renderToStaticMarkup(tree);scenarios++;report.push({username,page,buttons:count,status:'PASS'});
  }
 }
 for(const opts of [{offline:true},{registryOverride:[]}])for(const page of Object.keys(pages).filter(p=>p!=='concentration')){
  const h=harness(page,await login('staff_all'),admin.token,opts);assert.equal(actionCount(await h.render(),page),0,'Fail closed '+page);scenarios++;
 }
 // Each permission alone enables only its own page; revoke blocks original HTTP writes.
 for(const role of ['staff','supervisor'])for(const [page,key]of Object.entries(pages).filter(([p])=>p!=='concentration')){
  const who=await login(role+'_'+key),h=harness(page,who,admin.token);assert(actionCount(await h.render(),page)>0);
  const wrong=harness(page,await login(role+'_concentration'),admin.token);assert.equal(actionCount(await wrong.render(),page),0);scenarios+=2;
 }
 const staff=await login('staff_all');
 const deniedWrites={employees:['POST','/employees',{}],'salary-templates':['POST','/salary-templates',{}],'deduction-templates':['POST','/deduction-templates',{}],'labor-efficiency':['PUT','/efficiency/standard',{standard:450}],'employee-deductions':['POST','/employee-deductions',{}],'employee-advances':['POST','/employee-advances',{}]};
 try {
  for(const [page,[method,route,body]] of Object.entries(deniedWrites)){
   const label=registry.find(p=>p.menu_key===pages[page]).label;
   const changed=await http('PUT','/users/'+staff.user.id,admin.token,{extra_permissions:staff.user.extra_permissions.filter(p=>p!==label)});assert.equal(changed.status,200);
   const revoked=await login('staff_all'),h=harness(page,revoked,admin.token);assert.equal(actionCount(await h.render(),page),0,'Revoked button '+page);
   const denied=await http(method,route,staff.token,body);assert.equal(denied.status,403);assert(denied.data.detail.startsWith('无此操作权限'));scenarios++;
  }
 } finally {assert.equal((await http('PUT','/users/'+staff.user.id,admin.token,{extra_permissions:staff.user.extra_permissions})).status,200);}
 fs.writeFileSync(process.env.LEGACY_TEST_REPORT,JSON.stringify(report,null,2));
 console.log(JSON.stringify({status:'PASS',renderScenarios:scenarios,report},null,2));
 await exerciseWrites(admin);
}
async function exerciseWrites(admin){
 const report=[],employeeId=JSON.parse(fs.readFileSync(process.env.LEGACY12_FIXTURE_FILE,'utf8')).labor_employee_id;
 for(const username of ['supervisor_all','staff_all']){
  const who=await login(username),suffix=String(Date.now());
  for(const page of ['salary-templates','deduction-templates']){
   const h=harness(page,who);let tree=await h.render();button(tree,'新建模板').props.onClick();tree=await h.render();change(field(tree,'模板名称'),'R11-'+username+page+suffix);tree=await h.render();if(page==='salary-templates'){change(field(tree,'金额'),'400');tree=await h.render();}await button(tree,'保存').props.onClick();tree=await h.render();assert.equal(h.writes.at(-1)?.status,200,JSON.stringify(h.messages));
   const row=find(tree,n=>n.type==='tr'&&text(n).includes('R11-'+username+page+suffix));button(row,'编辑').props.onClick();tree=await h.render();change(field(tree,'模板名称'),'R11-edit-'+suffix);tree=await h.render();await button(tree,'保存').props.onClick();tree=await h.render();const edited=find(tree,n=>n.type==='tr'&&text(n).includes('R11-edit-'+suffix));await button(edited,'删除').props.onClick();await h.render();assert(h.writes.every(w=>w.status===200),JSON.stringify(h.writes));assert.equal(h.writes.length,3);report.push({username,page,create:'PASS',edit:'PASS',delete:'PASS'});
  }
  for(const page of ['employee-deductions','employee-advances']){
   const h=harness(page,who);let tree=await h.render();const create=find(tree,n=>n.type==='button'&&/setShowForm/.test(n.props.onClick?.toString()));create.props.onClick();tree=await h.render();
   if(page==='employee-advances'){change(field(tree,'资金来源'),'company_account');tree=await h.render();}
   change(field(tree,'员工'),page==='employee-advances'?'employee:'+employeeId:String(employeeId));tree=await h.render();change(field(tree,'金额'),'12');tree=await h.render();if(page==='employee-deductions'){change(field(tree,'扣款原因'),'R11-test');tree=await h.render();}
   await button(tree,'提交').props.onClick();tree=await h.render();assert.equal(h.writes.at(-1)?.status,200,JSON.stringify(h.messages));
   if(page==='employee-deductions'){
    const row=find(tree,n=>n.type==='tr'&&walk(n).some(c=>c.type==='button'&&c.props.onClick?.toString().includes('handleDelete'))&&text(n).includes('12'));await button(row,'删除').props.onClick();await h.render();assert(h.writes.every(w=>w.status===200));report.push({username,page,create:'PASS',delete:'PASS'});
   }else{
    const id=h.writes.at(-1).data.id;assert(!walk(tree).some(n=>n.type==='button'&&text(n).includes('作废')),'Staff/supervisor cannot void advances');
    const refused=await http('DELETE','/employee-advances/'+id,who.token,{void_reason:'不得由本人作废'});assert.equal(refused.status,403);
    const owner=harness(page,admin);let t=await owner.render();const row=find(t,n=>n.type==='tr'&&text(n).includes('12')&&walk(n).some(c=>c.type==='button'&&text(c).includes('作废')));button(row,'作废').props.onClick();t=await owner.render();
    change(find(t,n=>n.props?.['aria-label']==='作废原因'),'合成权限回归作废');t=await owner.render();await button(t,'确认作废').props.onClick();t=await owner.render();assert.equal(owner.writes.at(-1).status,200);assert(text(t).includes('已作废'));report.push({username,page,create:'PASS',nonOwnerVoidDenied:403,ownerVoidWithReason:'PASS'});
   }
  }
  {
   const h=harness('employees',who);let tree=await h.render();button(tree,'新建员工').props.onClick();tree=await h.render();
   const name='R11-员工-'+username+suffix;
   for(const [label,value] of [['姓名',name],['工号','r11'+username+suffix],['密码','test-password'],['薪资模板','1'],['扣款模板','1'],['入职日期','2026-10-01']]){change(field(tree,label),value);tree=await h.render();}
   await button(tree,'创建员工').props.onClick();tree=await h.render();assert.equal(h.writes.at(-1)?.status,200,JSON.stringify(h.messages));
   let row=find(tree,n=>n.type==='tr'&&text(n).includes(name));button(row,'编辑').props.onClick();tree=await h.render();change(field(tree,'联系电话'),'123456789');tree=await h.render();await button(tree,'保存修改').props.onClick();tree=await h.render();assert.equal(h.writes.at(-1)?.status,200,JSON.stringify(h.messages));
   row=find(tree,n=>n.type==='tr'&&text(n).includes(name));button(row,'离职').props.onClick();tree=await h.render();change(field(tree,'离职日期'),new Date(Date.now()-86400000).toISOString().slice(0,10));tree=await h.render();await button(tree,'确认离职').props.onClick();tree=await h.render();assert.equal(h.writes.at(-1)?.status,200,JSON.stringify(h.messages));
   // Create a second disposable employee to test the active-list delete confirmation.
   button(tree,'新建员工').props.onClick();tree=await h.render();
   for(const [label,value] of [['姓名',name+'删除'],['工号','r11d'+username+suffix],['密码','test-password'],['薪资模板','1']]){change(field(tree,label),value);tree=await h.render();}
   await button(tree,'创建员工').props.onClick();tree=await h.render();row=find(tree,n=>n.type==='tr'&&text(n).includes(name+'删除'));button(row,'删除').props.onClick();tree=await h.render();await button(tree,'确认删除').props.onClick();tree=await h.render();assert(h.writes.every(w=>w.status===200),JSON.stringify(h.writes));assert.equal(h.writes.length,5);
   report.push({username,page:'employees',create:'PASS',edit:'PASS',resign:'PASS',delete:'PASS'});
  }
  const h=harness('labor-efficiency',who);let tree=await h.render();const input=find(tree,n=>n.type==='input'&&n.props.placeholder==='默认 450');change(input,'460');tree=await h.render();await button(tree,'保存').props.onClick();tree=await h.render();const day=find(tree,n=>n.type==='button'&&n.props.onClick?.toString().includes('openOrderModal'));day.props.onClick();tree=await h.render();change(find(tree,n=>n.type==='input'&&n.props.value===''),'123');tree=await h.render();await button(tree,'保存').props.onClick();await h.render();assert.equal(h.writes.length,2,JSON.stringify(h.messages));assert(h.writes.every(w=>w.status===200));report.push({username,page:'labor-efficiency',standard:'PASS',order:'PASS'});
 }
 console.log(JSON.stringify({handlerWrites:'PASS',report},null,2));
}
main().catch(e=>{console.error(e);process.exit(1);});
