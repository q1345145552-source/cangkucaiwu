const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('/Users/xiongliu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const ids=JSON.parse(fs.readFileSync('/private/tmp/permissions-audit-round1-env/browser-identities.json','utf8'));
const out='/private/tmp/permissions-audit-round1-20261028/docs/permissions-audit-round1-20261028';
const result=[],errors=[];let browser;
(async()=>{
 browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 for(const [uid,url,width] of [[2,'/payroll',1440],[3,'/payroll',1440],[2,'/accounts',1440],[3,'/accounts',1440],[2,'/clock-in',390],[3,'/clock-in',390],[6,'/payroll',1440]]){
  const context=await browser.newContext({viewport:{width,height:960}});
  await context.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
  await context.addInitScript(token=>{localStorage.setItem('token',token);localStorage.setItem('activeWarehouseId','1');localStorage.setItem('locale','zh');localStorage.setItem('employee-locale','zh')},ids[uid].token);
  const page=await context.newPage(),requests=[];
  page.on('pageerror',e=>errors.push({uid,url,error:e.message}));
  page.on('response',r=>{if(r.url().includes('/api/v1/'))requests.push({url:new URL(r.url()).pathname,status:r.status()})});
  await page.goto('http://127.0.0.1:65332'+url,{waitUntil:'networkidle'});
  await page.getByRole('main').count().catch(()=>0);
  const text=await page.locator('body').innerText();
  const buttons=await page.getByRole('button').allTextContents();
  const file=`page-${uid}-${url.slice(1)}-${width}`;
  fs.writeFileSync(path.join(out,file+'.txt'),text.split('\n').map(line=>line.trimEnd()).join('\n')+'\n');
  await page.screenshot({path:path.join(out,file+'.png'),fullPage:true});
  result.push({id:'UI-'+result.length,uid,url,actual_url:page.url(),width,buttons,requests,artifact:file+'.png',text:file+'.txt'});
  await context.close();
 }
 // Same browser storage: switch from authorized supervisor to unprivileged supervisor, then reload.
 const context=await browser.newContext();await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 const page=await context.newPage();await page.goto('http://127.0.0.1:65332/login');
 await page.evaluate(token=>{localStorage.setItem('token',token);localStorage.setItem('activeWarehouseId','1')},ids[2].token);
 await page.goto('http://127.0.0.1:65332/payroll',{waitUntil:'networkidle'});assert((await page.locator('body').innerText()).includes('SYNTHETIC EMP 1'));
 await page.evaluate(token=>localStorage.setItem('token',token),ids[6].token);await page.reload({waitUntil:'networkidle'});
 const after=await page.locator('body').innerText();assert(!after.includes('SYNTHETIC EMP 1'));
 result.push({id:'UI-account-switch',from:2,to:6,reload:true,previous_employee_data_visible:false,limitation:'Does not test multiple tabs, in-flight stale responses, or switching without reload'});
 await context.close();await browser.close();fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({result,errors},null,2));console.log(JSON.stringify({pages:result.length,errors}));
})().catch(async e=>{console.error(e);fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({result,errors,failure:String(e)},null,2));if(browser)await browser.close();process.exitCode=1});
