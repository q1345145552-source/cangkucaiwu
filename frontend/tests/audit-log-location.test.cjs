// Render the real page and DataTable; legacy nulls, unknowns and mobile visibility.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const React=require('react'),ts=require('typescript'),{renderToStaticMarkup}=require('react-dom/server');
function load(file,imports,suffix=''){
 const m={exports:{}};
 vm.runInNewContext(ts.transpileModule(fs.readFileSync(file,'utf8')+suffix,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true}}).outputText,{module:m,exports:m.exports,require:n=>imports[n]||require(n)});
 return m.exports;
}
const table=load(path.resolve(__dirname,'../src/components/common/DataTable.tsx'),{}).default;
const rows=[{id:1,user_name:'旧记录',ip_country:null,ip_region:null,ip_city:null},{id:2,user_name:'未知IP',ip_country:'',ip_region:'',ip_city:''},{id:3,user_name:'地区验收',ip_country:'泰国',ip_region:'曼谷',ip_city:'旺通朗'},{id:4,user_name:'中国样本',ip_country:'中国',ip_region:'北京',ip_city:'北京'}];
let states=[rows,4,1,''],cursor=0;
const page=load(path.resolve(__dirname,'../src/app/(dashboard)/audit-logs/page.tsx'),{
 react:{...React,useState:()=>[states[cursor++],()=>{}],useEffect:()=>{}},
 '@/components/common/DataTable':{__esModule:true,default:table},'@/lib/api':{api:{},getToken:()=> 'test'},
 '@/hooks/useI18n':{useI18n:()=>({t:k=>k})},'next/navigation':{useRouter:()=>({push(){}})},
 '@/hooks/useAuth':{useAuth:()=>({user:{role:'warehouse_admin'}})},
},'\nexport { locationText };');
assert.equal(page.locationText(rows[0]),'');
assert.equal(page.locationText(rows[1]),'未知');
assert.equal(page.locationText(rows[2]),'泰国 曼谷 旺通朗');
assert.equal(page.locationText(rows[3]),'中国 北京');
const html=renderToStaticMarkup(React.createElement(page.default));
assert(html.includes('地区</th>')&&html.includes('泰国 曼谷 旺通朗')&&html.includes('中国 北京'));
assert(!html.match(/hidden[^<]*>地区</));
assert(html.includes('https://db-ip.com')&&html.includes('IP Geolocation by DB-IP'));
assert(!html.includes('undefined')&&!html.includes('null'));
console.log(JSON.stringify({result:'PASS',checks:8,legacy:'empty',unknown:'未知',thai:'泰国 曼谷 旺通朗',china:'中国 北京',mobile:'column is not hidden; shared table scrolls horizontally'}));
