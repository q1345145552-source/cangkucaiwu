// Actual layout rendering: employee links are additive and identity-based on both screen sizes.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const React=require('react'),ts=require('typescript'),{renderToStaticMarkup}=require('react-dom/server');
const {login,http}=require('./account-permissions.test.cjs');
let states=[],cursor=0,pathname='/clock-in';
const m={exports:{}};
const source=fs.readFileSync(path.resolve(__dirname,'../src/components/layout/DashboardLayout.tsx'),'utf8');
const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
vm.runInNewContext(code,{module:m,exports:m.exports,require(n){
 if(n==='react')return {...React,useState:()=>[states[cursor++],()=>{}],useEffect:()=>{}};
 if(n==='next/navigation')return {useRouter:()=>({push(){}}),usePathname:()=>pathname};
 if(n==='next/link')return {__esModule:true,default:({children,...props})=>React.createElement('a',props,children)};
 if(n==='@/hooks/useI18n')return {useI18n:()=>({t:k=>k})};
 if(n==='@/components/ui/BackToTop')return {__esModule:true,default:()=>null};
 if(n==='@/lib/api')return {};
 return require(n);
}});
const own=['/clock-in','/my-attendance','/my-overtime','/my-payslip','/my-leave'];
function render(user,registry,mobile,group){states=[true,mobile,group,false,false,false,[],null,false,user,mobile,registry];cursor=0;return renderToStaticMarkup(React.createElement(m.exports.default,null,'page'));}
function hrefs(html){const nav=html.match(/<nav\b[^>]*>([\s\S]*?)<\/nav>/);return [...nav[1].matchAll(/href="([^"]+)"/g)].map(x=>x[1]);}
async function main(){
 require('./legacy-regression-support.cjs').testBase();
 const fixture=JSON.parse(fs.readFileSync(process.env.LEGACY12_FIXTURE_FILE,'utf8'));
 const a=await login('warehouse_admin'),registry=(await http('GET','/users/permissions',a.access_token)).data;
 let checks=0;
 for(const username of ['supervisor_all','supervisor_none','staff_all','warehouse_admin','super_admin','labor1']){
  const res=await login(username),user=(await http('GET','/auth/me',res.access_token)).data;
  for(const enabled of [false,true])for(const mobile of [false,true]){
   const u={...user,attendance_enabled:enabled};
   const html=render(u,registry,mobile,'employee_self'),links=hrefs(html);
   if(u.role==='supervisor'&&enabled)for(const link of own)assert(links.includes(link),username+': missing '+link);
   else for(const link of ['/my-attendance','/my-overtime','/my-leave'])assert(!links.includes(link),username+': leaked '+link);
   if(u.role!=='warehouse_labor'&&u.role!=='supervisor')for(const link of own)assert(!links.includes(link),username+': leaked '+link);
   for(const group of ['finance_ops_group','finance_daily_group','supplier_group','hr_group','settings_group']){
    assert.deepEqual(hrefs(render({...user,attendance_enabled:false},registry,mobile,group)),hrefs(render({...user,attendance_enabled:true},registry,mobile,group)),'Management/labor menu changed '+username+' '+group);
   }
   checks++;
  }
 }
 // Actual API responses supplement the UI identity matrix: self-only records are
 // tested against another employee in the same warehouse and another warehouse.
 for(const name of ['labor1','supervisor_all']){
  const u=await login(name),token=u.access_token;
  const clock=await http('GET','/clock-in/records?view=self&start_date=2026-10-01&end_date=2026-10-31',token);
  assert.equal(clock.status,200);assert(clock.data.records.length>0);assert(clock.data.records.every(r=>r.user_id===u.user_id));
  for(const route of ['/clock-in/today','/attendance/calendar?view=self&start_date=2026-10-01&end_date=2026-10-31','/overtime/pending'])assert.equal((await http('GET',route,token)).status,200,name+' '+route);
  const payslip=await http('GET','/payroll/my-payslip?period=2026-10',token);assert.equal(payslip.status,200);assert.deepEqual(payslip.data.data.map(r=>r.id),[fixture.own_payroll[name]]);
  const foreignPhoto=await http('GET','/clock-in/photos?employee_id=52&date=2026-10-10&view=self',token);assert.equal(foreignPhoto.status,403);
 }
 for(const name of ['warehouse_admin','super_admin','staff_all','supervisor_none']){const u=await login(name);for(const route of ['/clock-in/today','/payroll/my-payslip'])assert.equal((await http('GET',route,u.access_token)).status,403,name+' '+route);}
 const worker=(await http('GET','/auth/me',(await login('labor1')).access_token)).data;
 const workerLinks=hrefs(render(worker,registry,false,'settings_group'));for(const path of ['/clock-in','/attendance','/overtime','/my-payslip'])assert(workerLinks.includes(path));
 pathname='/dashboard';assert.equal(render(worker,registry,false,null),'','Labor management route must remain blocked');pathname='/clock-in';
 for(const route of ['my-attendance','my-overtime','my-leave']){
  const s=fs.readFileSync(path.resolve(__dirname,'../src/app/(dashboard)',route,'page.tsx'),'utf8');assert(s.includes('employeeView'));assert(s.includes('../'+(route==='my-overtime'?'overtime':'attendance')+'/page'));
 }
 console.log(JSON.stringify({result:'PASS',identityDesktopMobileCases:checks,employeeEntries:own,managementMenuUnchanged:true}));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
