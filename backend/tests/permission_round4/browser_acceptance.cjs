const fs=require('node:fs'),assert=require('node:assert/strict');
const {chromium}=require('/Users/xiongliu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const env='/private/tmp/permissions-round4-env',out='/private/tmp/permissions-round4-20261028/docs/permissions-round4-20261028';
const ids=JSON.parse(fs.readFileSync(env+'/browser-identities.json','utf8')),results=[],errors=[];
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
try {
 for(const uid of [1,2,3])for(const route of ['/operating','/other-income-expense','/incoming','/reconciliation','/employees','/salary-templates','/deduction-templates']){
  const context=await browser.newContext({viewport:{width:uid===2?390:1440,height:960}});await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await context.addInitScript(identity=>{localStorage.setItem('token',identity.token);localStorage.setItem('activeWarehouseId','1');localStorage.setItem('locale','zh');localStorage.setItem('employee-locale','zh')},ids[uid]);
  const page=await context.newPage(),requests=[],faults=[];page.on('pageerror',e=>faults.push(e.message));page.on('response',r=>{if(r.url().includes('/api/v1/'))requests.push({path:new URL(r.url()).pathname,status:r.status()})});
  try {
   await page.goto('http://127.0.0.1:65392'+route,{waitUntil:'networkidle'});const body=await page.locator('body').innerText();
   const names=route.includes('templates')&&uid!==1?['新增模板','新建模板','编辑','删除']:uid===2&&route!=='/employees'?['录入支出','录入收款','新增收入','录入','保存','编辑','删除','确认匹配','解除匹配']:[];
   for(const name of names){const buttons=page.getByRole('button',{name,exact:true});for(let i=0;i<await buttons.count();i++)assert.equal(await buttons.nth(i).isEnabled(),false,`${uid} ${route} enabled ${name}`)}
   if(route==='/employees'&&uid!==1){
    const edit=page.getByRole('button',{name:'编辑',exact:true});if(await edit.count()){
     await edit.first().click();const bank=page.getByRole('textbox',{name:'银行账号',exact:true});if(await bank.count())assert.equal(await bank.isEnabled(),false);
    }
   }
   assert.deepEqual(faults,[]);const artifact=`final-ui-${uid}-${route.slice(1)}`;
   await page.screenshot({path:out+'/'+artifact+'.png',fullPage:true});fs.writeFileSync(out+'/'+artifact+'.txt',body);
   results.push({uid,route,requests,passed:true,artifact:artifact+'.png'});console.log(uid,route,'PASS');
  } catch(e){errors.push(`${uid} ${route}: ${e}`);console.error(errors.at(-1));}
  await context.close();
 }
 for(const uid of [2,3,6])for(const route of ['/my-attendance','/my-leave','/my-overtime','/my-payslip','/my-requests','/clock-in']){
  const context=await browser.newContext({viewport:{width:390,height:844}});await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await context.addInitScript(({identity,stale})=>{localStorage.setItem('token',identity.token);localStorage.setItem('user',JSON.stringify(stale));localStorage.setItem('activeWarehouseId','1');localStorage.setItem('employee-locale','zh')},{identity:ids[uid],stale:ids[1].user});
  const page=await context.newPage(),requests=[];page.on('response',r=>{if(r.url().includes('/api/v1/'))requests.push({path:new URL(r.url()).pathname,status:r.status()})});
  try{await page.goto('http://127.0.0.1:65392'+route,{waitUntil:'networkidle'});
   const selfRequests=requests.filter(r=>/clock-in|attendance|overtime|my-payslip|my-debt|reimbursement|expense-fund/.test(r.path));
   assert(selfRequests.length>0,JSON.stringify(requests));assert(selfRequests.every(r=>r.status===200),JSON.stringify(selfRequests));
   const artifact=`final-self-${uid}-${route.slice(1)}`;await page.screenshot({path:out+'/'+artifact+'.png',fullPage:true});
   results.push({uid,route,staleAdminCache:true,requests,passed:true,artifact:artifact+'.png'});console.log(uid,route,'PASS');
  }catch(e){errors.push(`${uid} ${route}: ${e}`);console.error(errors.at(-1))}await context.close();
 }
}finally{fs.writeFileSync(out+'/browser-results-final.json',JSON.stringify({results,errors},null,2));await browser.close();if(errors.length)process.exitCode=1}})();
