// Execute the production warning formatter and confirmation gate with synthetic user decisions.
const fs=require('fs'),path=require('path'),vm=require('vm'),ts=require('typescript');
let allowed=true;const calls=[];const m={exports:{}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/lib/balanceWarning.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}}).outputText,{module:m,exports:m.exports,Number,window:{confirm:message=>{calls.push(message);return allowed;}}});
module.exports={...m.exports,calls,setAllowed(value){allowed=value;calls.length=0;}};
