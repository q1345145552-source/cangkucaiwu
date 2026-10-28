// Real final UI + disposable local API. Never permits a remote origin.
const {chromium}=require('/Users/xiongliu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const assert=require('assert/strict'),fs=require('fs'),path=require('path');
const base=process.env.TEST_WEB_URL||'http://127.0.0.1:19312',out=path.resolve(__dirname,'../../docs/supplier-templates-tabs-20261028');
assert.equal(new URL(base).hostname,'127.0.0.1');
let lastPage;const collectedErrors=[];
const auth=JSON.parse(fs.readFileSync('/tmp/supplier-templates-auth.json')).admin;
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
 const user=await(await fetch(base+'/api/v1/auth/me',{headers:auth})).json();const ctx=await browser.newContext({viewport:{width:1440,height:1000}});
 await ctx.addInitScript(({user,token})=>{localStorage.setItem('user',JSON.stringify(user));localStorage.setItem('token',token);localStorage.setItem('activeWarehouseId','1');},{user,token:auth.Authorization.replace('Bearer ','')});
 await ctx.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 const page=await ctx.newPage(),errors=[];lastPage=page;page.on('pageerror',e=>{errors.push(e.message);collectedErrors.push(e.message);});
 const nav=()=>page.getByRole('navigation',{name:'供应商功能分组'});
 async function home(){await page.goto(base+'/suppliers');await nav().waitFor();await page.locator('.app-splash-title').waitFor({state:'hidden'});await page.getByRole('cell',{name:'本仓供应商',exact:true}).waitFor();}
 await home();const groups=await nav().locator('section').evaluateAll(nodes=>nodes.map(n=>({name:n.getAttribute('aria-label'),items:[...n.querySelectorAll('button')].map(b=>b.textContent.trim())})));
 assert.deepEqual(groups.map(g=>g.name),['档案','报价','采购','结算','库存','分析']);const names=groups.flatMap(g=>g.items);fs.writeFileSync(out+'/navigation-order.json',JSON.stringify(groups,null,2));
 await page.screenshot({path:out+'/desktop-groups-start.png',fullPage:true});await nav().evaluate(n=>{n.style.scrollBehavior='auto';n.scrollLeft=n.scrollWidth;n.scrollTop=0;});await page.screenshot({path:out+'/desktop-groups-end.png',fullPage:true});
 const headings={'新建供应商':'新建供应商','采购单列表':'采购单列表','采购审批':'采购审批','收货验收':'采购收货验收','收货差异':'收货差异列表','比价':'供应商比价','采购汇总':'采购汇总报表','价格监控':'价格监控'};
 const paths={'应付账单':'/payable','付款计划':'/payment-plans','标准SKU目录':'/supplier-skus','耗材库存':'/inventory','盘点':'/inventory','供应商采购分析':'/concentration','采购价差月报':'/suppliers/monthly-price-report','采购风险看板':'/suppliers/risk'};
 let visited=[];
 for(const name of names){
  await home();const button=nav().getByRole('button',{name,exact:true});await button.scrollIntoViewIfNeeded();
  if(['耗材模板','物流模板','对账单'].includes(name)){const got=page.waitForEvent('download');await button.click();const dl=await got;assert(!await dl.failure());await dl.saveAs('/tmp/supplier-templates-browser/download-'+name+'.xlsx');}
  else {await button.click();if(headings[name])await page.getByRole('heading',{name:headings[name],exact:true}).waitFor();else if(paths[name]){await page.waitForURL('**'+paths[name]);await page.locator('h1').first().waitFor();}else if(['产品报价','物流报价','阶梯与有效期'].includes(name)){await page.getByRole('heading',{name:name+' · 选择供应商',exact:true}).waitFor();await page.getByLabel('报价供应商').selectOption('1');await page.getByRole('button',{name:'打开报价',exact:true}).click();await page.getByRole('heading',{name:name==='物流报价'?'跨境物流报价':/产品定价/}).waitFor();}else if(name.startsWith('多供应商')){const chooser=page.waitForEvent('filechooser');await button.click();await(await chooser).setFiles([]);} }
  visited.push(name);
 }
 // Fill the actual downloaded batch templates, then use each distinct upload entry.
 await home();let chooser=page.waitForEvent('filechooser');await nav().getByRole('button',{name:'多供应商物流导入',exact:true}).click();await(await chooser).setFiles('/tmp/supplier-templates-browser/logistics-filled.xlsx');
 await page.getByLabel('已逐行核对，确认整批保存').check();const savedRoute=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().includes('/import/logistics')&&r.request().postData()?.includes('confirm'));
 await page.getByRole('button',{name:'确认整批保存',exact:true}).click();const logistic=await(await savedRoute).json();assert.equal(logistic.imported,2);
 chooser=page.waitForEvent('filechooser');await nav().getByRole('button',{name:'多供应商耗材导入',exact:true}).click();await(await chooser).setFiles('/tmp/supplier-templates-browser/products-filled.xlsx');
 await page.getByLabel('已逐行核对，按上述选择整批导入').check();const savedProduct=page.waitForResponse(r=>r.request().method()==='POST'&&r.url().includes('/import/products')&&r.request().postData()?.includes('confirm'));
 await page.getByRole('button',{name:'确认导入 1 条',exact:true}).click();const product=await(await savedProduct).json();assert.equal(product.imported,1);
 await nav().getByRole('button',{name:'物流',exact:true}).click();await page.getByRole('cell',{name:'合成物流商',exact:true}).waitFor();await nav().getByRole('button',{name:'物流报价',exact:true}).click();await page.getByLabel('报价供应商').selectOption('4');await page.getByRole('button',{name:'打开报价',exact:true}).click();await page.getByRole('cell',{name:'合成按公斤',exact:true}).waitFor();await page.getByRole('cell',{name:'合成按方',exact:true}).waitFor();await page.screenshot({path:out+'/logistics-route-display.png',fullPage:true});
 // Each item remains horizontally reachable at mobile size, without wrapping the strip.
 await page.setViewportSize({width:390,height:844});await home();const metrics=await nav().evaluate(n=>({width:n.clientWidth,scrollWidth:n.scrollWidth}));assert(metrics.scrollWidth>metrics.width);
 for(const name of names){const b=nav().getByRole('button',{name,exact:true});await b.scrollIntoViewIfNeeded();assert(await b.isVisible());}
 await nav().evaluate(n=>{n.style.scrollBehavior='auto';n.scrollLeft=0;n.scrollTop=0;});await page.screenshot({path:out+'/mobile-groups-start.png',fullPage:true});await nav().evaluate(n=>{n.style.scrollBehavior='auto';n.scrollLeft=n.scrollWidth;n.scrollTop=0;});await page.screenshot({path:out+'/mobile-groups-end.png',fullPage:true});
 await nav().getByRole('button',{name:'采购单列表',exact:true}).click();await page.getByRole('heading',{name:'采购单列表',exact:true}).waitFor();
 assert.equal(errors.length,0,errors.join('\n'));
 fs.writeFileSync(out+'/browser-actual.json',JSON.stringify({groups,visited,logistic,product,mobile:metrics,errors},null,2));await browser.close();console.log(JSON.stringify({passed:true,buttons_opened:visited.length,logistics_imported:logistic.imported,products_imported:product.imported,mobile_all_reachable:names.length,errors},null,2));
})().catch(async e=>{console.error(e);console.error('page errors',collectedErrors);if(lastPage)await lastPage.screenshot({path:out+'/failure-'+path.basename(__filename)+'.png',fullPage:true}).catch(()=>{});process.exit(1);});
