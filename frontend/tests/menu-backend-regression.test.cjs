// Run against menu-permissions.fixture.py only; all writes use disposable local accounts.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const base=require('./legacy-regression-support.cjs').testBase();
assert.equal(new URL(base).hostname,'127.0.0.1','Only local isolated test backends are allowed');
async function call(method,route,token,body){
 const r=await fetch(base+route,{method,headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})},...(body?{body:JSON.stringify(body)}:{})});
 const text=await r.text();assert(text.startsWith('{')||text.startsWith('['),method+' '+route+': HTTP '+r.status+' '+text.slice(0,80));
 return {status:r.status,body:JSON.parse(text)};
}
async function login(username){const r=await call('POST','/auth/login',null,{username,password:'test-password'});assert.equal(r.status,200,JSON.stringify(r));return r.body;}
async function main(){
 const admin=await login('warehouse_admin');const token=admin.access_token;
 // Confirm and restore the account disabled through the mobile UI, if that check was run.
 const users=await call('GET','/users?page_size=100',token);
 const none=users.body.data.find(x=>x.username==='staff_none');
 if(!none.is_active){assert.equal((await call('POST','/auth/login',null,{username:'staff_none',password:'test-password'})).status,403);assert.equal((await call('PUT','/users/'+none.id,token,{is_active:true,display_name:'staff_none'})).status,200);}
 const registry=(await call('GET','/users/permissions',token)).body;
 const all=registry.filter(p=>p.selectable).map(p=>p.label);
 const created=await call('POST','/users',token,{username:'r7-disposable-'+Date.now(),password:'test-password',display_name:'回归账号',role:'staff',warehouse_ids:[1],extra_permissions:all});
 assert.equal(created.status,200,JSON.stringify(created));const id=created.body.id;
 let list=await call('GET','/users?page_size=100',token);let user=list.body.data.find(x=>x.id===id);assert(user);
 const createdToken=(await login(user.username)).access_token;assert.equal((await login(user.username)).extra_permissions.length,all.length);
 assert.equal((await call('PUT','/users/'+id,token,{display_name:'已编辑',extra_permissions:all,is_active:false})).status,200);
 assert.equal((await call('POST','/auth/login',null,{username:user.username,password:'test-password'})).status,403);
 assert.equal((await call('GET','/auth/me',createdToken)).status,401);
 list=await call('GET','/users?page_size=100',token);user=list.body.data.find(x=>x.id===id);assert.equal(user.display_name,'已编辑');assert.deepEqual(user.extra_permissions,all);
 assert.equal((await call('PUT','/users/'+id,token,{is_active:true})).status,200);await login(user.username);
 assert.equal((await call('DELETE','/users/'+id,token)).status,200);
 assert.equal((await call('POST','/auth/login',null,{username:user.username,password:'test-password'})).status,401);
 // A pre-existing account with both audit and modification-history foreign keys
 // must delete cleanly while keeping original log facts and readable actor name.
 const candidate=await login('delete_candidate');
 const logsBefore=(await call('GET','/settings/logs?user_id='+candidate.user_id+'&page_size=100',token)).body.data;
 assert(logsBefore.length>=2);const oldHistory=(await call('GET','/history?operator_id='+candidate.user_id,token)).body.data;assert(oldHistory.length>0);
 assert.equal((await call('DELETE','/users/'+candidate.user_id,token)).status,200);
 const logsAfter=(await call('GET','/settings/logs?page_size=1000',token)).body.data;
 for(const log of logsBefore){const kept=logsAfter.find(x=>x.id===log.id);assert(kept);assert.deepEqual(kept,log);}
 const historyAfter=(await call('GET','/history?module=user&record_id='+candidate.user_id,token)).body.data;for(const old of oldHistory){const kept=historyAfter.find(x=>x.id===old.id);assert(kept);assert.equal(kept.operator_name,old.operator_name);assert.deepEqual(kept.before_data,old.before_data);assert.deepEqual(kept.after_data,old.after_data);}
 assert.equal((await call('GET','/auth/me',candidate.access_token)).status,401);
 const protectedReads=['/recharge','/customers','/accounts','/employees','/payroll','/salary-templates','/deduction-templates','/attendance/calendar','/attendance/leaves','/overtime','/payable','/payable/plans','/suppliers/concentration','/group-order','/users','/efficiency/standard','/reports/previews','/income-expense/ledger','/reconciliation/results'];
 for(const role of ['supervisor','staff']){
  const empty=await login(role+'_none');
  for(const route of protectedReads){const r=await call('GET',route,empty.access_token);assert.equal(r.status,403,role+' '+route+': '+JSON.stringify(r));assert(r.body.detail.startsWith('无此操作权限'));}
 }
 const paths={recharge:'/recharge',customers:'/customers',accounts:'/accounts',employees:'/employees',payroll:'/payroll',salary_templates:'/salary-templates',deduction_templates:'/deduction-templates',attendance:'/attendance/calendar',leave:'/attendance/leaves',overtime:'/overtime',payable:'/payable',payment_plans:'/payable/plans',concentration:'/suppliers/concentration',group_order:'/group-order',config_center:'/config/work-schedule',settings:'/users',labor_efficiency:'/efficiency/standard',reports:'/reports/previews',ledger:'/income-expense/ledger',reconciliation:'/reconciliation/results',expense_approval:'/expense-approvals',market:'/market',incoming:'/incoming',expense_fund:'/expense-fund/accounts',reimbursement:'/reimbursement',operating:'/income-expense/operating-dashboard',credit:'/credit',audit_logs:'/settings/logs',suppliers:'/suppliers/categories',other_income_expense:'/income-expense/income',modification_logs:'/history',employee_deductions:'/employee-deductions',employee_advances:'/employee-advances'};
 paths.cash_advances='/cash-advances';paths.inventory='/inventory';paths.sku_catalog='/sku-catalog';paths.sku_catalog_manage='/sku-catalog/reference';
 // Config reads and modification logs were deliberately opened in later rounds.
 const originalRoleLimits={supervisor:new Set(['sku_catalog_manage']),staff:new Set(['sku_catalog_manage'])}; // Manage also requires catalogue read; a write grant cannot reveal data alone.
 const report=[];
 for(const role of ['supervisor','staff'])for(const p of registry.filter(x=>x.selectable)){
  const u=await login(role+'_'+p.menu_key);const result=await call('GET',paths[p.menu_key],u.access_token);
  assert.equal(result.status,originalRoleLimits[role].has(p.menu_key)?403:200,role+' '+p.menu_key+': '+JSON.stringify(result));
  if(result.status===403)assert(result.body.detail.startsWith('无此操作权限'),JSON.stringify(result));
  report.push({role,key:p.menu_key,label:p.label,status:result.status,detail:result.status===403?result.body.detail:undefined});
 }
 const fixture=JSON.parse(fs.readFileSync(process.env.LEGACY12_FIXTURE_FILE,'utf8'));
 for(const route of Object.values(paths))assert(fixture.routes.some(r=>r.path===route&&r.methods.includes('GET')),'Registered GET missing '+route);
 const roleMatrix=[];
 for(const name of ['warehouse_admin','super_admin','labor1']){
  const u=await login(name);
  for(const p of registry.filter(x=>x.selectable)){
   const endpoint=paths[p.menu_key],r=await call('GET',endpoint,u.access_token);
   const allowed=name==='warehouse_admin'||name==='super_admin'&&['settings','audit_logs','modification_logs','market','group_order'].includes(p.menu_key)||name==='labor1'&&['attendance','leave','overtime'].includes(p.menu_key);
   assert.equal(r.status,allowed?200:403,name+' '+p.menu_key+': '+JSON.stringify(r));
   roleMatrix.push({role:u.role,key:p.menu_key,path:endpoint,status:r.status});
  }
 }
 const writes=[['POST','/employees',{}],['POST','/salary-templates',{}],['POST','/deduction-templates',{}],['PUT','/efficiency/standard',{standard:450}],['POST','/employee-deductions',{}],['POST','/employee-advances',{}]];
 for(const name of ['supervisor_none','staff_none','super_admin','labor1']){
  const u=await login(name);for(const [method,route,body]of writes){const r=await call(method,route,u.access_token,body);assert.equal(r.status,403,name+' '+method+' '+route);roleMatrix.push({role:name,method,path:route,status:r.status});}
 }
 const foreign=await login('foreign_admin'),foreignId=fixture.account_ids.foreign_staff;
 const foreignBefore=(await call('GET','/employees?include_deleted=true&page_size=200',foreign.access_token)).body;
 for(const [method,route,body]of [['PUT','/employees/52',{name:'must not change'}],['PUT','/salary-templates/2',{name:'must not change'}],['PUT','/deduction-templates/2',{name:'must not change'}],['PUT','/users/'+foreignId,{display_name:'must not change'}],['POST','/payroll/104/confirm',{}]]){
  const r=await call(method,route,token,body);assert([403,404].includes(r.status),JSON.stringify(r));roleMatrix.push({role:'warehouse_admin',crossWarehouse:true,method,path:route,status:r.status});
 }
 assert.deepEqual((await call('GET','/employees?include_deleted=true&page_size=200',foreign.access_token)).body,foreignBefore);
 // Both read and management grants are required by the established SKU policy.
 for(const role of ['supervisor','staff']){
  const u=await login(role+'_sku_catalog_manage');const labels=['sku_catalog','sku_catalog_manage'].map(key=>registry.find(p=>p.menu_key===key).label);
  assert.equal((await call('PUT','/users/'+u.user_id,token,{extra_permissions:labels})).status,200);
  const ref=await call('GET','/sku-catalog/reference',u.access_token);assert.equal(ref.status,200);assert(ref.body.can_manage);
 }
 fs.writeFileSync(process.env.LEGACY_TEST_REPORT,JSON.stringify({singleGrantReads:report,roleMatrix},null,2));
 console.log(JSON.stringify({accountLifecycle:'PASS',unauthorizedReads:protectedReads.length*2,grantedReads:report.length,originalRoleRestrictions:report.filter(x=>x.status===403),otherRoleAndBoundaryChecks:roleMatrix.length},null,2));
}
main().catch(e=>{console.error(e);process.exitCode=1});
