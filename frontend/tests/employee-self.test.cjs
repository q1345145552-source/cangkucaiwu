// Actual layout rendering: employee links are additive and identity-based on both screen sizes.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const React=require('react'),ts=require('typescript'),{renderToStaticMarkup}=require('react-dom/server');
const {login,http}=require('./account-permissions.test.cjs');
let states=[],cursor=0;
const m={exports:{}};
const source=fs.readFileSync(path.resolve(__dirname,'../src/components/layout/DashboardLayout.tsx'),'utf8');
const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText;
vm.runInNewContext(code,{module:m,exports:m.exports,require(n){
 if(n==='react')return {...React,useState:()=>[states[cursor++],()=>{}],useEffect:()=>{}};
 if(n==='next/navigation')return {useRouter:()=>({push(){}}),usePathname:()=>'/dashboard'};
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
 for(const route of ['my-attendance','my-overtime','my-leave']){
  const s=fs.readFileSync(path.resolve(__dirname,'../src/app/(dashboard)',route,'page.tsx'),'utf8');assert(s.includes('employeeView'));assert(s.includes('../'+(route==='my-overtime'?'overtime':'attendance')+'/page'));
 }
 console.log(JSON.stringify({result:'PASS',identityDesktopMobileCases:checks,employeeEntries:own,managementMenuUnchanged:true}));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
