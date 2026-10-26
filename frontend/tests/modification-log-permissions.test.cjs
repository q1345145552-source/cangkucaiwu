const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript'),React=require('react'),assert=require('node:assert/strict'),{execFileSync}=require('node:child_process');
const root=path.resolve(__dirname,'../..'),filename='frontend/src/components/layout/DashboardLayout.tsx';
const source=fs.readFileSync(path.join(root,filename),'utf8'),m={exports:{}};
vm.runInNewContext(ts.transpileModule(source+'\nexport { hasAccess, navItems };',{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module:m,exports:m.exports,require:n=>n==='react'?React:n==='next/navigation'?{}:n==='next/link'?{__esModule:true,default:()=>null}:n==='@/hooks/useI18n'?{}:n==='@/lib/api'?{}:n==='@/components/ui/BackToTop'?{__esModule:true,default:()=>null}:require(n)});
const item=m.exports.navItems.find(x=>x.key==='modification_logs');assert(item);assert.equal(item.href,'/modification-logs');
for(const role of ['supervisor','staff','warehouse_admin','super_admin','warehouse_labor'])for(const grant of [false,true]){
 const user={role,extra_permissions:grant?['修改日志']:[]};
 assert.equal(m.exports.hasAccess(item,user,[{menu_key:'modification_logs',label:'修改日志',path:'/modification-logs',selectable:true}]),role==='warehouse_admin'||role==='super_admin'||(grant&&['staff','supervisor'].includes(role)));
}
require('./legacy-regression-support.cjs').menuContract('modification_logs','/modification-logs');
const pageName='frontend/src/app/(dashboard)/modification-logs/page.tsx',page=fs.readFileSync(path.join(root,pageName),'utf8');
assert(page.includes('useMenuPermission("modification_logs")'));assert(page.includes('if (!canView) return'));assert(page.includes('if (!canView) return;'));assert(page.includes('/history/export?'));assert(page.includes('X-Warehouse-ID'));
const printer=ts.createPrinter();function funcs(s){const sf=ts.createSourceFile(pageName,s,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),out={};function walk(n){if(ts.isFunctionDeclaration(n)&&n.name&&!['ModificationLogsPage','handleExport','renderFieldVal'].includes(n.name.text))out[n.name.text]=printer.printNode(ts.EmitHint.Unspecified,n,sf);ts.forEachChild(n,walk);}walk(sf);return out;}
assert.deepEqual(funcs(page),funcs(execFileSync('git',['show','f70e0b6:'+pageName],{cwd:root,encoding:'utf8'})));
const rendered=require('./legacy-regression-support.cjs').compile(page+'\nexport {renderFieldVal,renderVal,diffSummary};',{
 react:React,'next/navigation':{},'@/lib/api':{},'@/hooks/useMenuPermission':{},'@/components/ui/Toast':{},'@/components/common/DataTable':{default:()=>null},
});
for(const key of ['is_voided','cost_record_only']){assert.equal(rendered.renderFieldVal(key,true),'是');assert.equal(rendered.renderFieldVal(key,false),'否');}
for(const [value,label] of [['pending','待审核'],['approved','已通过'],['rejected','已驳回'],['voided','已作废']])assert.equal(rendered.renderFieldVal('review_status',value),label);
assert.equal(rendered.renderFieldVal('review_status','future-state'),'future-state');
assert.equal(rendered.renderVal(null),'-');assert.equal(rendered.renderVal(3000),'3000');
console.log('Modification logs: 10 role/grant cases, export guard and unchanged existing handlers passed');
