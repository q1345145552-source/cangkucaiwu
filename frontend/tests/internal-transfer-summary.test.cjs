const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript'),React=require('react');
const {renderToStaticMarkup}=require('react-dom/server');
function compile(file,imports={}){const m={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src',file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{exports:m.exports,module:m,require:n=>imports[n]||require(n)});return m.exports;}
const currency=compile('lib/currency.ts'),Summary=compile('components/InternalTransferSummary.tsx',{'@/lib/currency':currency}).default;
const data={by_currency:{THB:10000,CNY:200},count_by_currency:{THB:1,CNY:1},scope_label:'所选仓库及期间的调拨额'};
const html=renderToStaticMarkup(React.createElement(Summary,{data}));
assert(html.includes('内部转账'));assert(html.includes('不计入收支'));assert(html.includes('THB ฿10,000'));assert(html.includes('CNY ¥200'));assert(!html.includes('20,000'));assert(!html.includes('10,200'));
assert(html.includes('不计入收入、支出、净收支或成本'));assert(html.includes('flex-wrap'));assert(html.includes('whitespace-nowrap'));
assert(renderToStaticMarkup(React.createElement(Summary,{data:{...data,scope_label:'涉及该账户的调拨额'}})).includes('涉及该账户的调拨额'));
assert.equal(renderToStaticMarkup(React.createElement(Summary,{})),'');
const empty=renderToStaticMarkup(React.createElement(Summary,{data:{by_currency:{},count_by_currency:{},scope_label:data.scope_label}}));assert(empty.includes('THB ฿0'));assert(empty.includes('CNY ¥0'));
console.log('PASS: real summary renders THB10000/CNY200 separately, no double count or mixed sum, account scope, non-income/expense note, narrow-screen wrapping, loading and zero cases');
