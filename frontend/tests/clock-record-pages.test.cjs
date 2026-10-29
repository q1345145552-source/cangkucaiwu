const assert=require('assert/strict'),fs=require('fs'),vm=require('vm'),ts=require('typescript');
const source=fs.readFileSync(require('path').join(__dirname,'../src/lib/clock-record-pages.ts'),'utf8');
function loader(responses){const calls=[],m={exports:{}};vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,{module:m,exports:m.exports,URLSearchParams,Error,require:()=>({api:{get:async url=>{calls.push(url);assert(responses.length);return responses.shift();}}})});return {...m.exports,calls};}
(async()=>{
 const a=loader([{employees:[{id:1}],employees_total:6,total:3,records:[{id:1},{id:2}]},{records:[{id:3}]}]);
 const r=await a.loadClockRecordPages('start_date=2026-10-27&end_date=2026-10-28&employee_page=2&view=self');
 assert.equal(r.records.length,3);assert.equal(r.employees_total,6);assert.equal(a.calls.length,2);
 for(const [i,url] of a.calls.entries()){const q=new URL(url,'http://local').searchParams;assert.equal(q.get('page'),String(i+1));assert.equal(q.get('page_size'),'100');assert.equal(q.get('employee_page'),'2');assert.equal(q.get('view'),'self');assert.equal(q.get('start_date'),'2026-10-27');assert.equal(q.get('end_date'),'2026-10-28');}
 const b=loader([{employees:[],total:3,records:[{id:1}]}]);await assert.rejects(b.loadClockRecordPages('date=2026-10-29',()=>false),/查询已切换/);assert.equal(b.calls.length,1);
 const c=loader([{total:2,records:[{id:1}]},{records:[]}]);await assert.rejects(c.loadClockRecordPages('date=2026-10-29'),/刷新重试/);
 const d=loader([{total:0,records:[]}]);assert.equal((await d.loadClockRecordPages('date=2026-10-29')).records.length,0);assert.equal(d.calls.length,1);
 console.log('PASS 4: explicit scoped pagination, cancellation, incomplete page failure, empty result');
})().catch(e=>{console.error(e);process.exitCode=1});
