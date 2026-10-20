const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
const source=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/lib/manualWallet.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText;
const makeStorage=()=>{const data=new Map();return{getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k),data};};
const storage=makeStorage(),local=makeStorage();local.setItem('user',JSON.stringify({id:1,warehouse_id:1}));
let sequence=0,warehouse='1',calls=[],records=new Map(),flags={drop:false,status:200,hold:null};
const api={getToken:()=> 'synthetic-token',getActiveWarehouseId:()=>warehouse};
async function fetcher(url,options){
 const payload=typeof options.body==='string'?JSON.parse(options.body):Object.fromEntries(options.body.entries());
 calls.push({url,headers:options.headers,payload});
 if(flags.hold)await flags.hold;
 if(flags.status!==200)return{ok:false,status:flags.status,json:async()=>({detail:'isolated rejected'})};
 if(!records.has(payload.request_key))records.set(payload.request_key,{id:records.size+1});
 if(flags.drop){flags.drop=false;throw Error('isolated lost response after commit');}
 return{ok:true,status:200,json:async()=>records.get(payload.request_key)};
}
function load(){const m={exports:{}};vm.runInNewContext(source,{module:m,exports:m.exports,require:n=>n==='@/lib/api'?api:require(n),Map,Number,JSON,FormData,process:{env:{}},localStorage:local,sessionStorage:storage,crypto:{randomUUID:()=> 'isolated-key-'+(++sequence)},fetch:fetcher});return m.exports;}
const income={category_id:1,account_id:3,amount:'1000',currency:'THB',income_date:'2026-10-20',remark:'cash'};
(async()=>{
 let module=load();flags.drop=true;await assert.rejects(module.submitWalletOperation('income',income),/lost response/);
 const pending=module.pendingWalletOperation('income');assert(pending);assert.equal(records.size,1);
 module=load();const recovered=await module.submitWalletOperation('income',{...income,amount:1000});
 assert.equal(recovered.id,1);assert.equal(calls[0].payload.request_key,calls[1].payload.request_key);assert.equal(records.size,1);
 assert.equal(module.pendingWalletOperation('income'),null);
 const second=await module.submitWalletOperation('income',income);assert.equal(second.id,2);assert.equal(records.size,2);
 let release;flags.hold=new Promise(r=>release=r);const before=calls.length;
 const a=module.submitWalletOperation('expense',{...income,expense_date:income.income_date,amount:200});
 const b=module.submitWalletOperation('expense',{...income,expense_date:income.income_date,amount:200});
 assert.equal(calls.length,before+1);assert(calls.at(-1).url.endsWith('/income-expense/expense'));
 assert.equal(calls.at(-1).payload.amount,'200');assert.equal(calls.at(-1).headers.Authorization,'Bearer synthetic-token');assert.equal(calls.at(-1).headers['X-Warehouse-ID'],'1');
 release();await Promise.all([a,b]);flags.hold=null;
 flags.status=500;await assert.rejects(module.submitWalletOperation('transfer',{from_account_id:'3',to_account_id:'4',amount:'300',transfer_date:'2026-10-20'}));
 const transferPending=module.pendingWalletOperation('transfer');const sent=calls.length;
 await assert.rejects(module.submitWalletOperation('transfer',{...transferPending.payload,amount:301}),/结果待确认/);assert.equal(calls.length,sent);
 flags.status=200;await module.submitWalletOperation('transfer',transferPending.payload);assert.equal(module.pendingWalletOperation('transfer'),null);
 flags.status=400;await assert.rejects(module.submitWalletOperation('income',income));assert.equal(module.pendingWalletOperation('income'),null);
 flags.status=200;flags.drop=true;await assert.rejects(module.submitWalletOperation('income',income));const wh1=module.pendingWalletOperation('income');
 warehouse='2';assert.equal(module.pendingWalletOperation('income'),null);await module.submitWalletOperation('income',income);
 warehouse='1';assert.equal(module.pendingWalletOperation('income').key,wh1.key);await module.submitWalletOperation('income',income);
 const original=storage.setItem;storage.setItem=()=>{throw Error('quota');};const count=calls.length;
 await assert.rejects(module.submitWalletOperation('income',income),/无法保存/);assert.equal(calls.length,count);storage.setItem=original;
 assert(!Array.from(storage.data.values()).join('').includes('synthetic-token'));
 console.log('PASS: real manual-wallet transport persists IDs before sending, recovers committed lost response after reload, permits independent equal amounts, coalesces double clicks, retains uncertain transfers, rejects changed pending content, scopes drafts by user/warehouse, and fails closed on storage errors');
})().catch(error=>{console.error(error);process.exitCode=1;});
