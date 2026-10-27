// New acceptance inputs: render the actual shared form with React, no network.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript'),React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
function load(file,imports={}){const m={exports:{}};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src',file),'utf8'),{fileName:file,compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module:m,exports:m.exports,require:n=>imports[n]||require(n),console});return m.exports;}
const spec=load('lib/specifications.ts'),components=load('components/StructuredSpecifications.tsx',{'@/lib/specifications':spec});
const original=JSON.parse('{"__proto__":"历史自定义规格","constructor":"人工填写的型号说明","toString":"印刷内容","material":"BOPP","width":{"value":48,"unit":"mm"},"extra":[true,7,{"note":"旧数据"}]}');
let html;assert.doesNotThrow(()=>{html=renderToStaticMarkup(React.createElement(components.default,{label:'验收规格',value:spec.specDraft(original),onChange(){}}));},'An allowed historical custom key must not crash any of the shared specification forms');
for(const name of ['__proto__','constructor','toString','历史自定义规格','人工填写的型号说明','印刷内容'])assert(html.includes(name),'Expected literal custom field '+name);
assert(!html.includes('function Object')&&!html.includes('[object Object]'));
assert.deepEqual(JSON.parse(JSON.stringify(spec.readSpecDraft(spec.specDraft(original)))),original);
const description=spec.specDescription(original);assert(description.includes('__proto__：历史自定义规格')&&description.includes('constructor：人工填写的型号说明')&&description.includes('toString：印刷内容'));
assert.equal(Object.getPrototypeOf({}),Object.prototype);assert.equal({}.polluted,undefined);
console.log(JSON.stringify({passed:4,checks:['actual React render accepts historical special property names without a blank page','literal labels and values do not resolve through Object.prototype','nested specifications round-trip without dropping custom keys','ordinary object prototypes remain unchanged']},null,2));
