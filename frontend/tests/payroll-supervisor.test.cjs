// Render the actual two payroll JSX fragments against real local API records.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server'),{execFileSync}=require('node:child_process');
const filename='frontend/src/app/(dashboard)/payroll/page.tsx',source=fs.readFileSync(path.resolve(__dirname,'../../',filename),'utf8');
const before=execFileSync('git',['show','ed3d03b:'+filename],{encoding:'utf8'});
const printer=ts.createPrinter();
function handlers(s){const file=ts.createSourceFile(filename,s,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),out=[];function visit(n){if(ts.isJsxAttribute(n)&&/^on[A-Z]/.test(n.name.getText(file)))out.push(printer.printNode(ts.EmitHint.Unspecified,n,file));ts.forEachChild(n,visit);}visit(file);return out;}
assert.deepEqual(handlers(execFileSync('git',['show','75021e9:'+filename],{encoding:'utf8'})),handlers(before),'Historical round 16 event handlers stayed identical');
const list=source.match(/<span className=\{r\.voided[^\n]+/)[0];
const detail=source.match(/<h3 className="text-lg font-bold">\{showPayslip\.employee_name\}[^\n]+/)[0];
function render(fragment,r){const m={exports:{}};const code=ts.transpileModule('module.exports = (<>'+fragment+'</>);',{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS}}).outputText;vm.runInNewContext(code,{module:m,exports:m.exports,require,r,showPayslip:r});return renderToStaticMarkup(m.exports);}
async function main(){
 const base=require('./legacy-regression-support.cjs').testBase();
 const fixture=JSON.parse(fs.readFileSync(process.env.LEGACY12_FIXTURE_FILE,'utf8'));
 const {login:realLogin,http}=require('./account-permissions.test.cjs');
 const identity=await realLogin('supervisor_all');assert.equal(identity.attendance_employee_id,fixture.supervisor_employee_id);
 const login=await (await fetch(base+'/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:'warehouse_admin',password:'test-password'})})).json();
 const response=await fetch(base+'/payroll?period=2026-10',{headers:{Authorization:'Bearer '+login.access_token}});assert.equal(response.status,200);const data=await response.json();
 assert.deepEqual(data.data.map(r=>r.id).sort((a,b)=>a-b),fixture.warehouse_payroll['1']);
 let supervisorRows=0,checks=0;for(const r of data.data){const expected=r.employee_id===identity.attendance_employee_id;assert.equal(r.is_supervisor,expected);supervisorRows+=Number(expected);for(const jsx of [list,detail]){const html=render(jsx,r);assert.equal(html.includes('>主管</span>'),expected);checks++;}}
 assert.equal(supervisorRows,1);
 for(const name of ['labor1','supervisor_all']){const u=await realLogin(name);const own=await http('GET','/payroll/my-payslip?period=2026-10',u.access_token);assert.equal(own.status,200);assert.deepEqual(own.data.data.map(r=>r.id),[fixture.own_payroll[name]]);assert.equal(own.data.data[0].net_pay,800);}
 const labor=await realLogin('labor1');assert.equal((await http('GET','/payroll?period=2026-10',labor.access_token)).status,403);
 const foreign=await realLogin('foreign_admin');const outside=await http('GET','/payroll?period=2026-10',foreign.access_token);assert.equal(outside.status,200);assert.deepEqual(outside.data.data.map(r=>r.id),fixture.warehouse_payroll['2']);
 console.log(JSON.stringify({result:'PASS',listAndDetailChecks:checks,historicalRound16HandlersUnchanged:true}));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
