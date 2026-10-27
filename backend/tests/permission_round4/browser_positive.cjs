const fs=require('node:fs'),assert=require('node:assert/strict');
const {chromium}=require('/Users/xiongliu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const out='/private/tmp/permissions-round4-20261028/docs/permissions-round4-20261028',ids=JSON.parse(fs.readFileSync('/private/tmp/permissions-round4-env/browser-identities.json'));
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'}),results=[];
try{for(const uid of [1,2,3]){
 const context=await browser.newContext({viewport:{width:390,height:844}});await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 await context.addInitScript(identity=>{localStorage.setItem('token',identity.token);localStorage.setItem('activeWarehouseId','1');localStorage.setItem('locale','zh');},ids[uid]);const page=await context.newPage();
 await page.goto('http://127.0.0.1:65392/operating',{waitUntil:'networkidle'});
 const create=page.getByRole('button',{name:'录入支出',exact:true});assert.equal(await create.count(),1);assert.equal(await create.isEnabled(),uid!==2);results.push({uid,action:'bookkeeping-entry',enabled:uid!==2});
 if(uid!==1){await page.goto('http://127.0.0.1:65392/my-requests',{waitUntil:'networkidle'});await page.getByLabel('金额',{exact:true}).fill('2');await page.getByLabel('说明',{exact:true}).fill('SYNTHETIC BROWSER REQUEST');
 const response=page.waitForResponse(r=>r.url().includes('/reimbursement?view=self')&&r.request().method()==='POST');await page.getByRole('button',{name:'提交本人申请',exact:true}).click();const r=await response;assert.equal(r.status(),200);await page.getByRole('status').filter({hasText:'申请已保存'}).waitFor();
 const body=await r.json();results.push({uid,action:'personal-request-submit',status:r.status(),response:body});await page.screenshot({path:out+`/positive-${uid}-personal-request.png`,fullPage:true});}
 await context.close();}
}finally{fs.writeFileSync(out+'/browser-positive.json',JSON.stringify(results,null,2));await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
