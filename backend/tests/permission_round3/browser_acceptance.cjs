const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('/Users/xiongliu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const env='/private/tmp/permissions-round3-env',out='/private/tmp/permissions-round3-20261028/docs/permissions-round3-20261028';
const ids=JSON.parse(fs.readFileSync(env+'/browser-identities.json','utf8')),results=[],errors=[];
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
try{
 for(const uid of [1,2,3])for(const route of ['/payroll','/reimbursement','/employee-advances','/cash-advances','/payable','/payment-plans']){
  const context=await browser.newContext({viewport:{width:uid===2?390:1440,height:960}});await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await context.addInitScript(identity=>{localStorage.setItem('token',identity.token);localStorage.setItem('activeWarehouseId','1');localStorage.setItem('locale','zh');localStorage.setItem('employee-locale','zh')},ids[uid]);
  const page=await context.newPage(),requests=[],faults=[];page.on('pageerror',e=>faults.push(e.message));page.on('response',r=>{if(r.url().includes('/api/v1/'))requests.push({path:new URL(r.url()).pathname,status:r.status()})});
  await page.goto('http://127.0.0.1:65372'+route,{waitUntil:'networkidle'});const buttons=await page.getByRole('button').allTextContents(),body=await page.locator('body').innerText();
  const forbidden=uid===2?['发放','确认发放','批量发放','核验','批准','出款','执行付款','付款','归还']:uid===3?['批准','批量确认','全部确认']:[];
  for(const text of forbidden)assert.equal(await page.getByRole('button',{name:text,exact:true}).count(),0,`${uid} ${route} forbidden ${text}`);
  if(route==='/payroll'&&uid===2)assert(body.includes('本人'),body);
  assert.equal(faults.length,0,JSON.stringify(faults));
  const artifact=`ui-${uid}-${route.slice(1)}`;await page.screenshot({path:out+'/'+artifact+'.png',fullPage:true});fs.writeFileSync(out+'/'+artifact+'.txt',body);
  results.push({uid,route,buttons,requests,artifact:artifact+'.png',passed:true});console.log(uid,route,'PASS');await context.close();
 }
 const context=await browser.newContext();await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());const page=await context.newPage();await page.goto('http://127.0.0.1:65372/login');
 for(const uid of [2,3,6])for(const route of ['/payroll','/payable','/payment-plans']){
  await page.evaluate(({identity,stale})=>{localStorage.setItem('token',identity.token);localStorage.setItem('user',JSON.stringify(stale));localStorage.setItem('activeWarehouseId','1')},{identity:ids[uid],stale:ids[1].user});
  await page.goto('http://127.0.0.1:65372'+route,{waitUntil:'networkidle'});const buttons=await page.getByRole('button').allTextContents();
  for(const text of (uid===3?['批准','全部确认']:['付款','发放','核验','批准','新建计划']))assert.equal(await page.getByRole('button',{name:text,exact:true}).count(),0,`stale ${uid} ${route} ${text}`);
  results.push({uid,route,staleAdminCache:true,buttons,passed:true});console.log('stale',uid,route,'PASS');
 }
 await context.close();
}catch(e){errors.push(String(e));process.exitCode=1;console.error(e)}finally{fs.writeFileSync(out+'/browser-results.json',JSON.stringify({results,errors},null,2));await browser.close()}})();
