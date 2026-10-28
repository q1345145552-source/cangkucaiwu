const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),ts=require('typescript');
const path=require('node:path');
const file=path.join(__dirname,'../src/app/(dashboard)/employee-advances/page.tsx');
const source=ts.createSourceFile(file,fs.readFileSync(file,'utf8'),ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX);let fn;
function walk(n){if(ts.isFunctionDeclaration(n)&&n.name?.text==='executeStage')fn=n.getText(source);ts.forEachChild(n,walk)}walk(source);assert(fn);
(async()=>{const results=[];
for(const kind of ['company_account','cash_advance','expense_fund'])for(const accept of [false,true]){
 const writes=[],reads=[],prompts=[],toasts=[];let loads=0;
 const ctx={rows:[{id:7,funding_source:kind,amount:500,payment_account_id:1,cash_advance_id:2,fund_account_id:3}],api:{async get(p){reads.push(p);return {accounts:[{id:1,current_balance:-100}],cash_advances:[{id:2,available_amount:100}],funds:[{id:3,available:50}]}},async post(p,b){writes.push({p,b})}},confirmBalanceWarning(b,a){prompts.push({b,a});return accept},toast(...x){toasts.push(x)},load(){loads++}};
 vm.createContext(ctx);vm.runInContext(ts.transpileModule(fn,{compilerOptions:{target:ts.ScriptTarget.ES2020}}).outputText,ctx);await ctx.executeStage(7,'execute');
 assert.equal(reads.length,1);assert.equal(prompts.length,1);assert.equal(prompts[0].a,500);assert.equal(prompts[0].b,{company_account:-100,cash_advance:100,expense_fund:50}[kind]);assert.equal(writes.length,accept?1:0);assert.equal(loads,accept?1:0);if(accept)assert.equal(writes[0].p,'/employee-advances/7/execute');
 results.push({kind,accept,reads:reads.length,prompts,writes:writes.length});
}
for(const missing of [false,true]){const writes=[],prompts=[];const ctx={rows:missing?[]:[{id:7,funding_source:'company_account',amount:500,payment_account_id:1}],api:{async get(){return {accounts:[]}},async post(p){writes.push(p)}},confirmBalanceWarning(){prompts.push(true);return true},toast(){},load(){}};vm.createContext(ctx);vm.runInContext(ts.transpileModule(fn,{compilerOptions:{target:ts.ScriptTarget.ES2020}}).outputText,ctx);await ctx.executeStage(7,'execute');assert.equal(writes.length,0);assert.equal(prompts.length,0);results.push({missingRecord:missing,unavailableSource:true,writes:0})}
console.log(JSON.stringify({passed:results.length,results},null,2));})().catch(e=>{console.error(e);process.exitCode=1});
