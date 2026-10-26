// Execute the real modal handlers with intercepted requests; no production connection.
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const ts = require('typescript'), React = require('react'), {execFileSync} = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const source = fs.readFileSync(path.join(root, 'frontend/src/components/BatchMakeupModal.tsx'), 'utf8');
const people = [{id:1,name:'员工甲'},{id:3,name:'员工乙'},{id:4,name:'请假A'},{id:5,name:'请假B'},{id:6,name:'休息员工'}];
const nodes = x => !x || typeof x !== 'object' ? [] : Array.isArray(x) ? x.flatMap(nodes) : [x,...nodes(x.props?.children)];
const text = x => x == null || typeof x === 'boolean' ? '' : typeof x !== 'object' ? String(x) : Array.isArray(x) ? x.map(text).join('') : text(x.props?.children);
const find = (t, fn) => {const n = nodes(t).find(fn); assert(n, 'Missing node'); return n;};
const button = (t, name) => find(t, n => n.type === 'button' && text(n) === name);
const checkbox = (t, name) => find(find(t,n=>n.type==='label'&&text(n).startsWith(name)),n=>n.type==='input');
const change = (n, value) => n.props.onChange({target:{value}});
function harness({employees=people,error=false}={}) {
  let state=[],cursor=0,closed=0,refreshed=0;const writes=[],messages=[];
  const react={...React,useState(initial){const i=cursor++;if(!(i in state))state[i]=initial;return [state[i],v=>{state[i]=typeof v==='function'?v(state[i]):v;}];}};
  const imports={react,'@/components/MakeupBatchHistory':{__esModule:true,default:()=>null},'@/lib/api':{api:{post:async(route,body)=>{writes.push({route,body});if(error)throw Error('员工不存在或不属于当前仓库');return {created_count:8,skipped_count:0};}}},'@/components/ui/Toast':{useToast:()=>({toast:(...v)=>messages.push(v)})}};
  const m={exports:{}};
  vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module:m,exports:m.exports,require:n=>imports[n]||require(n),Intl,Date});
  return {render(){cursor=0;return m.exports.default({employees,scheduleTimes:{1:'08:30',2:'11:30',3:'12:30',4:'17:30'},onClose(){closed++;},onSuccess(){refreshed++;}});},writes,messages,get closed(){return closed;},get refreshed(){return refreshed;}};
}
(async()=>{
  let h=harness(),t=h.render();
  assert.equal(nodes(t).filter(n=>n.type==='input'&&n.props.type==='checkbox'&&n.props.checked).length,9);
  assert.equal(find(t,n=>n.type==='textarea').props.value,'系统故障');assert(text(t).includes('08:30'));
  const today=find(t,n=>n.props?.['aria-label']==='补卡日期').props.value;assert.match(today,/^\d{4}-\d{2}-\d{2}$/);
  for(const name of ['请假A','请假B','休息员工']){checkbox(t,name).props.onChange();t=h.render();}
  assert.equal(nodes(t).filter(n=>n.type==='input'&&n.props.type==='checkbox'&&n.props.checked).length,6);
  await button(t,'确认补卡').props.onClick();assert.equal(h.writes.length,1);assert.equal(h.writes[0].route,'/clock-in/batch-makeup');assert.deepEqual(Array.from(h.writes[0].body.employee_ids),[1,3]);assert.equal(h.closed,1);assert.equal(h.refreshed,1);assert.deepEqual(h.messages.at(-1),['success','批量补卡完成：建了8条，跳过0条']);
  h=harness();t=h.render();button(t,'时点全不选').props.onClick();t=h.render();for(const name of ['早上上班','下午下班']){checkbox(t,name).props.onChange();t=h.render();}await button(t,'确认补卡').props.onClick();assert.deepEqual(Array.from(h.writes[0].body.sessions),[1,4]);
  for(const [control,message] of [['员工全不选','请选择员工'],['时点全不选','请选择打卡时点']]){h=harness();t=h.render();button(t,control).props.onClick();t=h.render();await button(t,'确认补卡').props.onClick();assert.equal(h.writes.length,0);assert.equal(h.messages.at(-1)[1],message);button(t,control.replace('全不选','全选')).props.onClick();t=h.render();await button(t,'确认补卡').props.onClick();assert.equal(h.writes.length,1);}
  for(const [field,value,message] of [['补卡原因','  ','请填写补卡原因'],['补卡日期','2999-01-01','请选择今天或以前的日期']]){h=harness();t=h.render();change(find(t,n=>n.props?.['aria-label']===field),value);t=h.render();await button(t,'确认补卡').props.onClick();assert.equal(h.writes.length,0);assert.equal(h.messages.at(-1)[1],message);}
  h=harness({error:true});t=h.render();await button(t,'确认补卡').props.onClick();assert.equal(h.closed,0);assert.equal(h.refreshed,0);assert.equal(h.messages.at(-1)[1],'员工不存在或不属于当前仓库');
  h=harness({employees:[]});t=h.render();assert(button(t,'确认补卡').props.disabled);assert(text(t).includes('暂无可选员工'));
  h=harness();t=h.render();button(t,'取消').props.onClick();assert.equal(h.closed,1);assert.equal(h.writes.length,0);
  const filename='frontend/src/app/(dashboard)/attendance/page.tsx',page=fs.readFileSync(path.join(root,filename),'utf8'),old=execFileSync('git',['show','c515151:'+filename],{cwd:root,encoding:'utf8'});
  assert(page.includes('!employeeView && role === "warehouse_admin"'));
  const printer=ts.createPrinter();function handlers(s){const sf=ts.createSourceFile(filename,s,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),result={};function visit(n){if(ts.isFunctionDeclaration(n)&&n.name&&!['AttendancePage','openPhotoPopup','loadCalendar','loadMakeupMarkers','approveLeave','submitProxyLeave'].includes(n.name.text))result[n.name.text]=printer.printNode(ts.EmitHint.Unspecified,n,sf);ts.forEachChild(n,visit);}visit(sf);return result;}
  assert.deepEqual(handlers(page),handlers(old));
  // Full-day leave warnings were intentionally added later. Execute those actual handlers
  // instead of demanding that valid subsequent work equal the pre-batch source snapshot.
  const {actualFunction}=require('./legacy-regression-support.cjs');
  for(const name of ['approveLeave','submitProxyLeave']) {
    const calls=[],alerts=[],toasts=[],refresh=[];
    const globals={api:{post:async(route,body)=>{calls.push({route,body});return {warning:'该员工当天已有打卡记录'};},put:async(route,body)=>{calls.push({route,body});return {warning:'该员工当天已有打卡记录'};}},window:{alert:message=>alerts.push(message)},toast:(...v)=>toasts.push(v),t:key=>key,
      proxyEmpId:3,proxyStartDate:'2026-10-10',proxyEndDate:'2026-10-10',proxyType:'sick',proxyDuration:'full',proxyHours:'',proxyReason:'系统测试',proxyNotifiedAt:'2026-10-09',todayStr:'2026-10-10',loadLeaves:()=>refresh.push('leaves'),loadCalendar:()=>refresh.push('calendar')};
    for(const setter of ['setShowProxyLeaveForm','setProxyEmpId','setProxyStartDate','setProxyEndDate','setProxyType','setProxyDuration','setProxyHours','setProxyReason','setProxyNotifiedAt'])globals[setter]=()=>{};
    await actualFunction(page,filename,name,globals)(19);
    assert.equal(calls.length,1);assert.deepEqual(alerts,['该员工当天已有打卡记录']);assert.deepEqual(refresh,['leaves','calendar']);
    assert.equal(calls[0].route,name==='approveLeave'?'/attendance/leaves/19/approve':'/attendance/leaves/admin-record');
    if(name==='submitProxyLeave'){assert.equal(calls[0].body.employee_id,3);assert.equal(calls[0].body.duration_type,'full');}
  }
  console.log('PASS: defaults, person/session selection, select all/none, date/reason checks, success/error/cancel, empty employees, admin-only gate, original write handlers unchanged');
})().catch(error=>{console.error(error);process.exitCode=1;});
