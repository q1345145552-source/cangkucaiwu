// Real display components/read handlers; requests intercepted and writes forbidden.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const {execFileSync}=require('node:child_process'),ts=require('typescript'),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const root=path.resolve(__dirname,'../..');
const read=p=>fs.readFileSync(path.join(root,p),'utf8');
const dictionaries=Object.fromEntries(['zh','my','th'].map(locale=>[locale,JSON.parse(read(`frontend/src/i18n/${locale}.json`))]));
function load(source,imports){const m={exports:{}};vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module:m,exports:m.exports,require:n=>imports[n]||require(n),Date:TestDate,URLSearchParams,Promise,console});return m.exports;}
class TestDate extends Date {constructor(...args){super(...(args.length?args:['2026-10-18T12:00:00+07:00']));}static now(){return new Date('2026-10-18T12:00:00+07:00').getTime();}}
const display=load(read('frontend/src/components/MakeupDisplay.tsx'),{}),helpers=load(read('frontend/src/lib/makeup-display.ts'),{});
const times={1:'09:00',2:'12:00',3:'13:00',4:'18:00'};
const row=(date,session,makeup=false,batch=null)=>({employee_id:1,user_id:5,clock_date:date,session,clocked_in_at:`${date}T${times[session]}:00+07:00`,status:'normal',photo_path:null,photo_thumb_path:null,is_makeup:makeup,makeup_by:makeup?1:null,makeup_by_name:makeup?'Admin':'',makeup_at:makeup?'2026-10-18T10:15:00+07:00':null,makeup_reason:makeup?'System failure':null,makeup_batch_id:batch});
const normal=[1,2,3,4].map(s=>row('2026-10-16',s));
const mixed=[...normal,row('2026-10-17',1,true),...[1,2,3,4].map(s=>row('2026-10-18',s,s===1||s===4,s===1||s===4?1:null))];
const walk=x=>!x||typeof x!=='object'?[]:Array.isArray(x)?x.flatMap(walk):[x,...walk(x.props?.children)];
const text=x=>x==null||typeof x==='boolean'?'':typeof x!=='object'?String(x):Array.isArray(x)?x.map(text).join(''):text(x.props?.children);
const find=(t,p)=>{const n=walk(t).find(p);assert(n,'Missing node');return n;};
const badges=t=>walk(t).filter(n=>n.props?.['data-makeup-badge']!==undefined);
const expand=n=>{if(n==null||typeof n!=='object')return n;if(Array.isArray(n))return n.map(expand);if(typeof n.type==='function')return expand(n.type(n.props));const children=expand(n.props?.children);return Array.isArray(children)?React.cloneElement(n,{},...children):React.cloneElement(n,{},children);};
const cell=(tree,date)=>find(tree,n=>n.type==='td'&&n.key===date);
function harness(kind,{records=mixed,locale='zh',role='warehouse_admin',baseline=false}={}){
 let state=[],refs=[],deps=[],cleanups=[],effects=[],pending=[],cursor=0,rc=0,ei=0;const reads=[],writes=[];
 const react={...React,useState(initial){const i=cursor++;if(!(i in state))state[i]=typeof initial==='function'?initial():initial;return [state[i],v=>state[i]=typeof v==='function'?v(state[i]):v];},useRef(initial){const i=rc++;if(!refs[i])refs[i]={current:initial};return refs[i];},useMemo:fn=>fn(),useEffect(fn,d){const i=ei++,key=JSON.stringify(d);if(deps[i]!==key){cleanups[i]?.();deps[i]=key;effects.push(()=>{cleanups[i]=fn();});}}};
 const response=route=>{
  if(route.startsWith('/clock-in/records')){const q=new URL('http://local'+route).searchParams;return {employees:[{id:1,name:'Employee1',position:'Worker'}],records:records.filter(r=>(!q.get('start_date')||r.clock_date>=q.get('start_date'))&&(!q.get('end_date')||r.clock_date<=q.get('end_date')))};}
  if(route.startsWith('/attendance/calendar'))return {employees:[{id:1,name:'Employee1',position:'Worker'}],events:['2026-10-16','2026-10-17','2026-10-18'].map(date=>({date,employee_id:1,status:date.endsWith('17')?'partial':'present',session_count:date.endsWith('17')?1:4,work_hours:8}))};
  if(route.startsWith('/clock-in/photos')){const q=new URL('http://local'+route).searchParams,date=q.get('date');return {sessions:[1,2,3,4].map(s=>{const record=records.find(r=>r.clock_date===date&&r.session===s);return {session:s,clocked_in_at:record?.clocked_in_at||null,status:record?'normal':'missing',photo_path:null};})};}
  if(route==='/config/attendance-times')return {morning_start:'09:00',noon_break_start:'12:00',noon_break_end:'13:00',afternoon_end:'18:00'};
  if(route.startsWith('/attendance/'))return {data:[]};
  throw Error('Unexpected read '+route);
 };
 const api={get(route){reads.push(route);const p=Promise.resolve().then(()=>response(route));pending.push(p);return p;},post(){writes.push('post');throw Error('Display must not write');},put(){writes.push('put');throw Error('Display must not write');},delete(){writes.push('delete');throw Error('Display must not write');}};
 const imports={react,'@/lib/api':{api,getToken:()=> 'test',getActiveWarehouseId:()=> '1'},'@/hooks/useAuth':{useAuth:()=>({user:{id:role==='warehouse_labor'?5:1,role,warehouse_id:1}})},'@/hooks/useI18n':{useI18n:()=>({locale,t:key=>dictionaries[locale][key]||key})},'@/hooks/useEmployeeView':{useEmployeeView:()=>({employeeView:role==='warehouse_labor',initialLeave:false})},'next/navigation':{useRouter:()=>({push(){}})},'@/components/ui/Toast':{useToast:()=>({toast(){}})},'@/components/SafeImage':{__esModule:true,default:()=>null},'@/components/EmployeeLanguage':{__esModule:true,default:()=>null},'@/components/BatchMakeupModal':{__esModule:true,default:()=>null},'@/components/ClockRecordsGrid':{__esModule:true,default:()=>null},'@/components/MakeupDisplay':display,'@/lib/makeup-display':helpers};
 const filename=kind==='grid'?'frontend/src/components/ClockRecordsGrid.tsx':'frontend/src/app/(dashboard)/attendance/page.tsx';
 const source=baseline?execFileSync('git',['show','603db93:'+filename],{cwd:root,encoding:'utf8'}):read(filename),Component=load(source,imports).default;
 return {async render(){let tree;for(let i=0;i<8;i++){cursor=rc=ei=0;tree=expand(Component(kind==='grid'?{startDate:'2026-10-16',endDate:'2026-10-18',employeeView:role==='warehouse_labor'}:undefined));for(const fn of effects.splice(0))fn();if(!pending.length)return tree;await Promise.all(pending.splice(0));await new Promise(setImmediate);}return tree;},reads,writes};
}
(async()=>{
 const input=mixed.map(r=>Object.freeze({...r})),grouped=helpers.makeupRecordsByDay(Object.freeze(input));assert.equal(grouped['2026-10-18_1'].length,2);assert.equal(grouped['2026-10-17_1'].length,1);assert(!grouped['2026-10-16_1']);
 assert.deepEqual(Object.keys(helpers.makeupRecordsByDay([{...normal[0],makeup_batch_id:99,makeup_by:1}])).length,0);
 const original=Object.freeze([{session:1,status:'normal',photo_path:'photo',clocked_in_at:'original'},{session:2,status:'normal'}].map(Object.freeze));const attached=helpers.attachMakeupDetails(original,input,1,'2026-10-18');assert.equal(attached[0].photo_path,'photo');assert.equal(attached[0].clocked_in_at,'original');assert.equal(attached[0].makeup_batch_id,1);assert.equal(attached[1],original[1]);assert(!helpers.attachMakeupDetails(original,input,2,'2026-10-18')[0].is_makeup);
 for(const locale of ['zh','my','th']){
  for(const key of ['makeup','makeup_short','makeup_by','makeup_at','makeup_batch','reason'])assert(dictionaries[locale][key],locale+' missing '+key);
  if(locale!=='zh')for(const key of ['makeup_short','makeup_at','makeup_batch'])assert(!/[\u3400-\u9fff]/.test(dictionaries[locale][key]));
  const role=locale==='zh'?'warehouse_admin':'warehouse_labor';let h=harness('grid',{locale,role}),t=await h.render();assert.equal(badges(cell(t,'2026-10-18')).length,2);assert.equal(badges(cell(t,'2026-10-17')).length,1);assert.equal(badges(cell(t,'2026-10-16')).length,0);
  assert(text(cell(t,'2026-10-18')).includes('12:00'));assert(text(cell(t,'2026-10-18')).includes(dictionaries[locale].makeup_short));assert(badges(cell(t,'2026-10-18')).every(n=>n.props.className.includes('shrink-0')&&n.props.className.includes('whitespace-nowrap')));
  cell(t,'2026-10-18').props.onClick();t=await h.render();assert.equal(walk(t).filter(n=>n.props?.['data-makeup-details']!==undefined).length,2);assert(text(t).includes('Admin'));assert(text(t).includes('System failure'));assert(text(t).includes(dictionaries[locale].makeup_at));assert(text(t).includes(dictionaries[locale].makeup_batch+'：#1'));assert.equal(h.writes.length,0);
  h=harness('calendar',{locale,role});t=await h.render();assert.equal(badges(cell(t,'2026-10-18')).length,1);assert.equal(badges(cell(t,'2026-10-16')).length,0);find(cell(t,'2026-10-18'),n=>typeof n.props?.onClick==='function').props.onClick();t=await h.render();assert.equal(walk(t).filter(n=>n.props?.['data-makeup-details']!==undefined).length,2);assert(text(t).includes(dictionaries[locale].makeup_batch+'：#1'));assert(h.reads.filter(p=>p.startsWith('/clock-in/records')).every(p=>role!=='warehouse_labor'||p.includes('view=self')));assert.equal(h.writes.length,0);
  console.log('DISPLAY_LOCALE',locale,dictionaries[locale].makeup_short,dictionaries[locale].makeup_at,dictionaries[locale].makeup_batch);
 }
 for(const kind of ['grid','calendar']){
  const old=harness(kind,{records:normal,baseline:true}),now=harness(kind,{records:normal});let a=await old.render(),b=await now.render();assert.equal(renderToStaticMarkup(a),renderToStaticMarkup(b),kind+' normal days stay identical');
  if(kind==='calendar'){find(cell(a,'2026-10-16'),n=>typeof n.props?.onClick==='function').props.onClick();find(cell(b,'2026-10-16'),n=>typeof n.props?.onClick==='function').props.onClick();a=await old.render();b=await now.render();assert.equal(renderToStaticMarkup(a),renderToStaticMarkup(b),'normal photo details stay identical');}
 }
 console.log('PASS: exact makeup flags, immutable metadata merge, 3 locales, mixed/legacy/normal days, per-session/calendar details, batch display when returned, self reads, zero writes, identical normal DOM');
})().catch(e=>{console.error(e);process.exitCode=1;});
