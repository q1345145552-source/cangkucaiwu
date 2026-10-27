const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require('/Users/xiongliu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const ids=JSON.parse(fs.readFileSync('/private/tmp/permissions-round2-env/browser-identities.json','utf8'));
const out='/private/tmp/permissions-round2-20261028/docs/permissions-round2-20261028';
const results=[],errors=[];let browser;
(async()=>{
 browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 for(const uid of [1,2,3])for(const url of ['/accounts','/expense-fund']){
  const context=await browser.newContext({viewport:{width:uid===2?390:1440,height:960}});
  await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await context.addInitScript(identity=>{localStorage.setItem('token',identity.token);localStorage.setItem('activeWarehouseId','1');localStorage.setItem('locale','zh');localStorage.setItem('employee-locale','zh')},ids[uid]);
  const page=await context.newPage(),requests=[];
  page.on('pageerror',e=>errors.push({uid,url,error:e.message}));
  page.on('response',r=>{if(r.url().includes('/api/v1/'))requests.push({path:new URL(r.url()).pathname,status:r.status()})});
  await page.goto('http://127.0.0.1:65342'+url,{waitUntil:'networkidle'});
  const buttons=await page.getByRole('button').allTextContents();
  const titleSize=await page.locator('.page-title').first().evaluate(el=>parseFloat(getComputedStyle(el).fontSize));
  assert(titleSize>=18, 'Local runtime must load the repository Tailwind configuration and CSS');
  const createName=url==='/accounts'?'新建账户':'新建备用金';
  assert.equal(await page.getByRole('button',{name:createName,exact:true}).count(),uid===1?1:0,`${uid} ${url} create`);
  if(url==='/accounts'&&uid!==1){assert.equal(await page.getByTitle('编辑',{exact:true}).count(),0);assert.equal(await page.getByTitle('停用',{exact:true}).count(),0)}
  if(url==='/expense-fund'){
   const review=page.getByRole('button',{name:'审核',exact:true});
   assert.equal(await review.count(),uid===2?0:1);
   if(uid!==2){await review.click();await page.getByRole('button',{name:/充值申请/}).click();await page.waitForLoadState('networkidle');
     await page.getByRole('button',{name:'核验',exact:true}).first().waitFor({state:'visible',timeout:15000});
     assert((await page.getByRole('button',{name:'核验',exact:true}).count())>0);
     assert.equal((await page.getByRole('button',{name:'批准',exact:true}).count())>0,uid===1);
     assert.equal((await page.getByRole('button',{name:'执行拨付',exact:true}).count())>0,uid===3);
   }
  }
  const artifact=`ui-${uid}-${url.slice(1)}`;
  await page.screenshot({path:path.join(out,artifact+'.png'),fullPage:true});
  fs.writeFileSync(path.join(out,artifact+'.txt'),await page.locator('body').innerText());
  results.push({uid,url,buttons,reviewButtons:await page.getByRole('button').allTextContents(),requests,artifact:artifact+'.png',passed:true});
  await context.close();
 }
 // Reuse admin cache deliberately, replace only token, refresh and assert role ceilings.
 const context=await browser.newContext();await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 const page=await context.newPage();await page.goto('http://127.0.0.1:65342/login');
 await page.evaluate(identity=>{localStorage.setItem('token',identity.token);localStorage.setItem('user',JSON.stringify(identity.user));localStorage.setItem('activeWarehouseId','1')},ids[1]);
 await page.goto('http://127.0.0.1:65342/accounts',{waitUntil:'networkidle'});assert.equal(await page.getByRole('button',{name:'新建账户',exact:true}).count(),1);
 for(const uid of [2,3,6]){
  await page.evaluate(({identity,stale})=>{localStorage.setItem('token',identity.token);localStorage.setItem('user',JSON.stringify(stale))},{identity:ids[uid],stale:ids[1].user});
  await page.reload({waitUntil:'networkidle'});
  assert.equal(await page.getByRole('button',{name:'新建账户',exact:true}).count(),0);
  results.push({id:'account-switch-stale-admin-cache',from:1,to:uid,passed:true,body:(await page.locator('body').innerText()).slice(0,1000)});
 }
 await context.close();await browser.close();
 fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({results,errors},null,2));
 assert.equal(errors.length,0);console.log(JSON.stringify({pages:results.length,errors}));
})().catch(async e=>{console.error(e);fs.writeFileSync(path.join(out,'browser-results.json'),JSON.stringify({results,errors,failure:String(e)},null,2));if(browser)await browser.close();process.exitCode=1});
