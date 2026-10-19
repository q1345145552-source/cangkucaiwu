// Load the actual shared policy rather than mocking the disabled flag in tests.
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm'), ts = require('typescript');
const m = {exports:{}};
const filename = path.join(__dirname, '../src/lib/financial-reversals.ts');
vm.runInNewContext(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020}
}).outputText, {module:m,exports:m.exports});
module.exports = m.exports;
