// Run against menu-permissions.fixture.py only; all writes use disposable local accounts.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const base=process.env.TEST_API_URL||'http://127.0.0.1:18080/api/v1';
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
 assert.equal((await login(user.username)).extra_permissions.length,all.length);
 assert.equal((await call('PUT','/users/'+id,token,{display_name:'已编辑',extra_permissions:all,is_active:false})).status,200);
 assert.equal((await call('POST','/auth/login',null,{username:user.username,password:'test-password'})).status,403);
 list=await call('GET','/users?page_size=100',token);user=list.body.data.find(x=>x.id===id);assert.equal(user.display_name,'已编辑');assert.deepEqual(user.extra_permissions,all);
 assert.equal((await call('PUT','/users/'+id,token,{is_active:true})).status,200);await login(user.username);
 assert.equal((await call('DELETE','/users/'+id,token)).status,200);
 assert.equal((await call('POST','/auth/login',null,{username:user.username,password:'test-password'})).status,401);
 const protectedReads=['/recharge','/customers','/accounts','/employees','/payroll','/salary-templates','/deduction-templates','/attendance/calendar','/attendance/leaves','/overtime','/payable','/payable/plans','/suppliers/concentration','/group-order','/users','/efficiency/standard','/reports/previews','/income-expense/ledger','/reconciliation/results'];
 for(const role of ['supervisor','staff']){
  const empty=await login(role+'_none');
  for(const route of protectedReads){const r=await call('GET',route,empty.access_token);assert.equal(r.status,403,role+' '+route+': '+JSON.stringify(r));assert(r.body.detail.startsWith('无此操作权限'));}
 }
 const paths={recharge:'/recharge',customers:'/customers',accounts:'/accounts',employees:'/employees',payroll:'/payroll',salary_templates:'/salary-templates',deduction_templates:'/deduction-templates',attendance:'/attendance/calendar',leave:'/attendance/leaves',overtime:'/overtime',payable:'/payable',payment_plans:'/payable/plans',concentration:'/suppliers/concentration',group_order:'/group-order',config_center:'/config/work-schedule',settings:'/users',labor_efficiency:'/efficiency/standard',reports:'/reports/previews',ledger:'/income-expense/ledger',reconciliation:'/reconciliation/results',expense_approval:'/expense-approvals',market:'/market',incoming:'/incoming',expense_fund:'/expense-fund/accounts',reimbursement:'/reimbursement',operating:'/income-expense/operating-dashboard',credit:'/credit',audit_logs:'/settings/logs',suppliers:'/suppliers/categories',other_income_expense:'/income-expense/income',modification_logs:'/history',employee_deductions:'/employee-deductions',employee_advances:'/employee-advances'};
 paths.cash_advances='/cash-advances';
 // Config reads and modification logs were deliberately opened in later rounds.
 const originalRoleLimits={supervisor:new Set(),staff:new Set()};
 const report=[];
 for(const role of ['supervisor','staff'])for(const p of registry.filter(x=>x.selectable)){
  const u=await login(role+'_'+p.menu_key);const result=await call('GET',paths[p.menu_key],u.access_token);
  assert.equal(result.status,originalRoleLimits[role].has(p.menu_key)?403:200,role+' '+p.menu_key+': '+JSON.stringify(result));
  if(result.status===403)assert(!result.body.detail.startsWith('无此操作权限'),JSON.stringify(result));
  report.push({role,key:p.menu_key,label:p.label,status:result.status,detail:result.status===403?result.body.detail:undefined});
 }
 fs.writeFileSync('/tmp/r7-business-results.json',JSON.stringify(report,null,2));
 console.log(JSON.stringify({accountLifecycle:'PASS',unauthorizedReads:protectedReads.length*2,grantedReads:report.length,originalRoleRestrictions:report.filter(x=>x.status===403)},null,2));
}
main().catch(e=>{console.error(e);process.exitCode=1});
