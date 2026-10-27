const fs=require('node:fs'),assert=require('node:assert/strict');
const {chromium}=require('/Users/xiongliu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const env='/private/tmp/permissions-round5-env',out='/private/tmp/permissions-round5-20261028/docs/permissions-round5-20261028/'+(process.env.ROUND5_RUN||'browser');fs.mkdirSync(out,{recursive:true});
const ids=JSON.parse(fs.readFileSync(env+'/browser-identities.json','utf8')),results=[],errors=[];
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
try{
 for(const uid of [1,2,3,6,11])for(const route of (uid===6||uid===11?['/dashboard','/my-payslip','/my-requests']:['/dashboard','/employees','/customers','/accounts','/payroll','/my-payslip','/my-requests'])){
  const context=await browser.newContext({viewport:{width:uid===2?390:1440,height:960}});await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await context.addInitScript(({identity,stale})=>{localStorage.setItem('token',identity.token);localStorage.setItem('user',JSON.stringify(stale));localStorage.setItem('activeWarehouseId','1');localStorage.setItem('locale','zh');localStorage.setItem('employee-locale','zh')},{identity:ids[uid],stale:ids[1].user});
  const page=await context.newPage(),requests=[],faults=[],bodies=[];
  page.on('pageerror',e=>faults.push(e.message));page.on('response',async r=>{if(r.url().includes('/api/v1/')){requests.push({path:new URL(r.url()).pathname,status:r.status()});try{bodies.push({path:new URL(r.url()).pathname,body:await r.text()})}catch{}}});
  try{
   await page.goto('http://127.0.0.1:65492'+route,{waitUntil:'networkidle'});
   if(route==='/customers'&&uid===2){await page.getByPlaceholder('搜索客户名称或编号...').fill('CUSTOMER-1');await page.waitForResponse(r=>r.url().includes('/api/v1/customers?'));await page.waitForTimeout(300);assert(!await page.getByRole('button',{name:'新建客户',exact:true}).count());}
   if(route==='/employees'){
    assert(requests.some(r=>r.path==='/api/v1/employees'&&r.status===200));
    if(uid===2){assert(!bodies.some(r=>r.body.includes('BANK-SENTINEL')||r.body.includes('PASSPORT-SENTINEL')));const adminHeaders={Authorization:'Bearer '+ids[1].token,'X-Warehouse-ID':'1'};
     const before=(await (await context.request.get('http://127.0.0.1:65492/api/v1/employees',{headers:adminHeaders})).json()).data.find(e=>e.id===1);
     const row=page.getByRole('row').filter({hasText:'SYNTHETIC EMP 1'});const edit=row.getByRole('button',{name:'编辑',exact:true});assert.equal(await edit.count(),1);await edit.click();assert.equal(await page.getByRole('textbox',{name:'银行账号',exact:true}).count(),0);
     const pending=page.waitForResponse(r=>r.url().includes('/api/v1/employees/1')&&r.request().method()==='PUT');await page.getByRole('button',{name:'保存修改',exact:true}).click();const saved=await pending;assert.equal(saved.status(),200,await saved.text());const sent=saved.request().postDataJSON();for(const key of ['bank_account_number','passport_number','daily_wage','salary_template_id'])assert(!(key in sent));
     const after=(await (await context.request.get('http://127.0.0.1:65492/api/v1/employees',{headers:adminHeaders})).json()).data.find(e=>e.id===1);for(const key of ['bank_account_number','passport_number','daily_wage','salary_template_id'])assert.equal(after[key],before[key]);}
    if(uid===3)assert(bodies.some(r=>r.path==='/api/v1/employees'&&r.body.includes('BANK-SENTINEL-1')));
   }
   if(route==='/accounts'&&uid===2){assert.equal(await page.getByRole('columnheader',{name:'当前余额',exact:true}).count(),0);assert.equal(await page.getByRole('button',{name:'新建账户',exact:true}).count(),0);}
   if(route==='/payroll')assert(requests.some(r=>r.path==='/api/v1/payroll'&&r.status===(uid===2?403:200)),JSON.stringify(requests));
   if(route==='/dashboard'&&[2,6,11].includes(uid))assert(!requests.some(r=>r.path.includes('cockpit')));
   if(route.startsWith('/my-')){const calls=requests.filter(r=>/my-payslip|my-debt|reimbursement|expense-fund/.test(r.path));assert(calls.length>0);assert(calls.every(r=>r.status===(uid===1?403:200)),JSON.stringify(calls));}
   assert.deepEqual(faults,[]);const artifact=`ui-${uid}-${route.slice(1)}`;await page.screenshot({path:out+'/'+artifact+'.png',fullPage:true});results.push({uid,route,staleAdminCache:true,requests,passed:true});console.log(uid,route,'PASS');
  }catch(e){errors.push(`${uid} ${route}: ${e}`);console.error(errors.at(-1))}
  await context.close();
 }
 // Same tab changes token while old admin state is present; focus forces live identity refresh.
 const context=await browser.newContext();await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 await context.addInitScript(identity=>{localStorage.setItem('token',identity.token);localStorage.setItem('activeWarehouseId','1')},ids[1]);const page=await context.newPage();
 try{await page.goto('http://127.0.0.1:65492/employees',{waitUntil:'networkidle'});await page.evaluate(identity=>{localStorage.setItem('token',identity.token);window.dispatchEvent(new StorageEvent('storage',{key:'token',newValue:identity.token}))},ids[2]);await page.waitForTimeout(1200);assert(!(await page.locator('body').innerText()).includes('BANK-SENTINEL'));const edit=page.getByRole('button',{name:'编辑',exact:true});await edit.first().click();assert.equal(await page.getByRole('textbox',{name:'银行账号',exact:true}).count(),0);const attachmentStatus=await page.evaluate(async()=> (await fetch('/uploads/1/audit/passport-1.png')).status);assert.equal(attachmentStatus,403);results.push({case:'same-tab-admin-to-supervisor',attachmentStatus,passed:true});}catch(e){errors.push('switch: '+e)}await context.close();
}finally{fs.writeFileSync(out+'/results.json',JSON.stringify({results,errors},null,2));await browser.close();if(errors.length)process.exitCode=1}})();
