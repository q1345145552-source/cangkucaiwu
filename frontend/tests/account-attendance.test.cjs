// Run through run-legacy-regressions.py; actual Settings switches and isolated native HTTP API.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const ts=require('typescript'),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const {harness,http,login,text,walk}=require('./account-permissions.test.cjs');
const change=(field,value)=>field.props.onChange({target:{value}});
const component=(h,tree,id)=>h.find(tree,n=>n.type===h.attendance.default&&n.props.id===id);
const markup=(h,node)=>renderToStaticMarkup(h.attendance.default(node.props));
async function open(h,tree,name){const row=h.find(tree,n=>n.type==='tr'&&walk(n).some(c=>c.type==='td'&&text(c)===name));h.find(row,n=>n.type==='button'&&text(n).trim()==='编辑').props.onClick();return h.render();}
async function main(){
 const identity=await login('warehouse_admin'),token=identity.access_token,user=(await http('GET','/auth/me',token)).data;
 const h=harness(user,token);let tree=await h.render();h.button(tree,'用户管理').props.onClick();tree=await h.render();
 for(const role of ['supervisor','staff','warehouse_admin','super_admin','warehouse_labor']){
  change(h.field(tree,'角色'),role);tree=await h.render();const nodes=walk(tree).filter(n=>n.type===h.attendance.default&&n.props.id==='new-attendance-enabled');
  assert.equal(nodes.length,['supervisor','staff'].includes(role)?1:0);
  if(nodes.length){assert.equal(nodes[0].props.enabled,false);const html=markup(h,nodes[0]);assert(html.includes('档案和历史记录会保留'));nodes[0].props.onChange(true);tree=await h.render();assert(markup(h,component(h,tree,'new-attendance-enabled')).includes('保存后会自动建档案'));}
 }
 const report=[];
 for(const name of ['supervisor','staff']){
  tree=await open(h,tree,name);let toggle=component(h,tree,'edit-attendance-enabled');assert.equal(toggle.props.enabled,false);assert(!toggle.props.employee);
  toggle.props.onChange(true);tree=await h.render();assert(markup(h,component(h,tree,'edit-attendance-enabled')).includes('保存后会自动建档案'));
  await h.button(tree,'保存').props.onClick();tree=await h.render();assert(h.messages.at(-1)[1].includes('档案已建好'));
  tree=await open(h,tree,name);toggle=component(h,tree,'edit-attendance-enabled');assert(toggle.props.enabled);assert(toggle.props.employee);let html=markup(h,toggle);assert(html.includes(`工号：${name}`)&&html.includes('已关联员工档案')&&html.includes('档案已建好'));
  const eid=toggle.props.employee.id;toggle.props.onChange(false);tree=await h.render();assert(markup(h,component(h,tree,'edit-attendance-enabled')).includes('关掉后不纳入考勤'));
  await h.button(tree,'保存').props.onClick();tree=await h.render();tree=await open(h,tree,name);toggle=component(h,tree,'edit-attendance-enabled');assert(!toggle.props.enabled);assert.equal(toggle.props.employee.id,eid);assert(markup(h,toggle).includes('档案和历史记录会保留'));
  toggle.props.onChange(true);tree=await h.render();assert(markup(h,component(h,tree,'edit-attendance-enabled')).includes('将绑定到已有的那条档案'));
  await h.button(tree,'保存').props.onClick();tree=await h.render();tree=await open(h,tree,name);toggle=component(h,tree,'edit-attendance-enabled');assert.equal(toggle.props.employee.id,eid);
  // Saving other fields with unchanged attendance must not invoke binding again.
  const before=h.requests.length;await h.button(tree,'保存').props.onClick();tree=await h.render();const put=h.requests.slice(before).find(r=>r.method==='PUT'&&r.route.startsWith('/users/'));assert(!('attendance_enabled' in put.body));
  report.push({role:name,onSave:'PASS',linkedNameNumber:'PASS',offSave:'PASS',reopenSameProfile:'PASS'});
 }
 for(const [name,label]of [['r14-existing','已有主管档案'],['r14-return','保留的主管档案']]){
  tree=await open(h,tree,name);let toggle=component(h,tree,'edit-attendance-enabled');assert.equal(toggle.props.employee.name,label);toggle.props.onChange(true);tree=await h.render();assert(markup(h,component(h,tree,'edit-attendance-enabled')).includes('将绑定到已有的那条档案'));await h.button(tree,'保存').props.onClick();tree=await h.render();report.push({name,existingProfileHint:'PASS'});
 }
 tree=await open(h,tree,'r14-conflict');component(h,tree,'edit-attendance-enabled').props.onChange(true);tree=await h.render();await h.button(tree,'保存').props.onClick();tree=await h.render();assert.deepEqual(h.messages.at(-1),['error','该员工档案已绑定其他账号']);const alert=h.find(tree,n=>n.props?.role==='alert'&&text(n)==='该员工档案已绑定其他账号');assert(alert.props.className.includes('text-red-600'));assert(component(h,tree,'edit-attendance-enabled'));h.button(tree,'取消').props.onClick();tree=await h.render();
 // Labor edit has no identity switch.
 tree=await open(h,tree,'labor1');assert(!walk(tree).some(n=>n.type===h.attendance.default&&n.props.id==='edit-attendance-enabled'));h.button(tree,'取消').props.onClick();tree=await h.render();
 for(const [role,enabled,failSecond] of [['supervisor',false,false],['staff',false,false],['supervisor',true,false],['staff',true,false],['staff',true,true]]){
  change(h.field(tree,'角色'),role);tree=await h.render();const name='r14-'+role+'-'+Date.now();for(const [label,value]of [['用户名',name],['显示名称','新账号考勤验证'],['密码','test-password']]){change(h.field(tree,label),value);tree=await h.render();}
  if(role==='supervisor')h.find(tree,n=>n.type==='input'&&n.props.type==='checkbox'&&!n.props.checked).props.onChange({target:{checked:true}});else change(h.field(tree,'所属仓库'),'1');tree=await h.render();component(h,tree,'new-attendance-enabled').props.onChange(enabled);tree=await h.render();
  h.setFailure((method,route,body)=>failSecond&&method==='PUT'&&body?.attendance_enabled===true);
  const start=h.requests.length;await h.button(tree,'创建用户').props.onClick();tree=await h.render();const requests=h.requests.slice(start),posts=requests.filter(r=>r.method==='POST'&&r.route==='/users'),puts=requests.filter(r=>r.method==='PUT'&&r.body?.attendance_enabled===true);assert.equal(posts.length,1);assert.equal(puts.length,enabled?1:0);assert(!('attendance_enabled' in posts[0].body));
  const created=(await http('GET','/users?page_size=100',token)).data.data.find(u=>u.username===name);assert(created);assert.equal(created.attendance_enabled,enabled&&!failSecond);
  if(enabled&&!failSecond){assert(created.attendance_employee_id);assert(h.messages.at(-1)[1].includes('设置薪资模板和扣款模板'));}
  if(failSecond){assert(h.messages.at(-1)[0]==='error');assert(walk(tree).some(n=>n.props?.role==='alert'&&text(n).includes('账号 '+name+' 已创建')));assert.equal(h.field(tree,'用户名').props.value,'');}
  assert.equal(component(h,tree,'new-attendance-enabled').props.enabled,false);h.setFailure(null);report.push({role,enabled,partialFailure:failSecond,status:'PASS'});
 }
 // Read failure is visible and retry restores the real information.
 h.setFailure((method,route)=>route.startsWith('/employees?'));tree=await open(h,tree,'supervisor');let toggle=component(h,tree,'edit-attendance-enabled');assert(toggle.props.error);assert(!markup(h,toggle).includes('保存后会自动建档案'));h.setFailure(null);toggle.props.onRetry();tree=await h.render();assert(component(h,tree,'edit-attendance-enabled').props.employee);
 // The same pre-existing bearer token observes the switch immediately; closing
 // it retains the seeded archive, attendance and calculated 800 payroll record.
 const self=await login('supervisor_all'),before=(await http('GET','/payroll/my-payslip?period=2026-10',self.access_token)).data;
 const clockBefore=(await http('GET','/clock-in/records?view=self&start_date=2026-10-01&end_date=2026-10-31',self.access_token)).data;
 assert.equal((await http('PUT','/users/'+self.user_id,token,{attendance_enabled:false})).status,200);
 assert.equal((await http('GET','/clock-in/today',self.access_token)).status,403);
 assert.equal((await http('GET','/payroll/my-payslip',self.access_token)).status,403);
 const kept=(await http('GET','/employees?include_deleted=true&page_size=200',token));assert.equal(kept.status,200);assert.equal(kept.data.data.find(e=>e.id===self.attendance_employee_id).user_id,null);
 assert.equal((await http('PUT','/users/'+self.user_id,token,{attendance_enabled:true})).status,200);
 const after=(await http('GET','/payroll/my-payslip?period=2026-10',self.access_token)).data;assert.deepEqual(after,before);assert.equal(after.data[0].net_pay,800);
 const clockAfter=(await http('GET','/clock-in/records?view=self&start_date=2026-10-01&end_date=2026-10-31',self.access_token)).data;assert.deepEqual(clockAfter.records,clockBefore.records);
 report.push({oldTokenSwitchAndHistoricalRecords:'PASS',retainedEmployee:self.attendance_employee_id,netPay:800});
 fs.writeFileSync(process.env.LEGACY_TEST_REPORT,JSON.stringify(report,null,2));
 console.log(JSON.stringify({status:'PASS',report,conflictRawRed:'PASS',lookupRetry:'PASS'},null,2));
 await testPaginationAndHistoryOrder();
}
async function testPaginationAndHistoryOrder(){
 // Target may be beyond page 1; historical records sharing timestamps must use the latest id.
 const source=fs.readFileSync(path.resolve(__dirname,'../src/components/settings/AttendanceToggle.tsx'),'utf8');let scenario=0;const calls=[];
 const api={get:async route=>{calls.push(route);if(route.startsWith('/employees?')){const page=+new URL('http://test'+route).searchParams.get('page');return page===1?{data:[{id:1,name:'same name',user_id:99}],total:2}:{data:[{id:2,name:'target',user_id:scenario?null:4}],total:2};}const page=+new URL('http://test'+route).searchParams.get('page');return page===1?{data:[{id:1,before_data:{attendance_employee_id:1}}],total:101}:{data:[{id:2,before_data:{attendance_employee_id:2}}],total:101};}};
 const m={exports:{}};vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2020,module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module:m,exports:m.exports,require:n=>n==='@/lib/api'?{api}:require(n)});
 assert.equal((await m.exports.findAttendanceEmployee({id:4})).id,2);scenario=1;assert.equal((await m.exports.findAttendanceEmployee({id:4})).id,2);assert(calls.some(c=>c.includes('page=2')));console.log('paginationAndLatestHistory: PASS');
}
main().catch(e=>{console.error(e);process.exitCode=1});
