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
 const base='http://127.0.0.1:18080/api/v1';
 const login=await (await fetch(base+'/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:'warehouse_admin',password:'test-password'})})).json();
 const response=await fetch(base+'/payroll?period=2026-10',{headers:{Authorization:'Bearer '+login.access_token}});assert.equal(response.status,200);const data=await response.json();
 let checks=0;for(const r of data.data){assert.equal(r.is_supervisor,r.employee_id===5);for(const jsx of [list,detail]){const html=render(jsx,r);assert.equal(html.includes('>主管</span>'),r.employee_id===5);checks++;}}
 console.log(JSON.stringify({result:'PASS',listAndDetailChecks:checks,historicalRound16HandlersUnchanged:true}));
}
main().catch(e=>{console.error(e);process.exitCode=1;});
