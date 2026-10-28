// One-time codemod: resolves existing handlers to the explicit action catalogue.
// Generated gates are reviewed source, not runtime inference. Unresolved handlers are reported.
const fs=require('fs'),path=require('path');
const ts=require('/private/tmp/permissions-round5-env/frontend/node_modules/typescript');
const ROOT=path.resolve(__dirname,'../../..');
const rows=JSON.parse(fs.readFileSync(path.join(ROOT,'backend/app/core/action_catalog.json'))).routes;
function walk(n,fn){fn(n);ts.forEachChild(n,c=>walk(c,fn));}
function files(dir){return fs.readdirSync(dir,{withFileTypes:true}).flatMap(f=>f.isDirectory()?files(path.join(dir,f.name)):f.name.endsWith('.tsx')?[path.join(dir,f.name)]:[]);}
const report=[];
for(const file of [...files(path.join(ROOT,'frontend/src/app/(dashboard)')),...files(path.join(ROOT,'frontend/src/components'))]){
 if(/permissions\/|layout\/|\/my-|\/clock-in\/|\/settings\/|\/EmployeeLanguage|\/SafeImage/.test(file))continue;
 let source=fs.readFileSync(file,'utf8'); if(source.includes('import ActionGate '))continue;
 const ast=ts.createSourceFile(file,source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX), funcs=new Map(), stateActions=new Map();
 walk(ast,n=>{
  if(ts.isFunctionDeclaration(n)&&n.name)funcs.set(n.name.text,n);
  if(ts.isVariableDeclaration(n)&&ts.isIdentifier(n.name)&&n.initializer&&(ts.isArrowFunction(n.initializer)||ts.isFunctionExpression(n.initializer)))funcs.set(n.name.text,n.initializer);
 });
 function pathValue(n){if(ts.isStringLiteralLike(n))return n.text;if(ts.isTemplateExpression(n))return n.head.text+n.templateSpans.map(s=>'{}'+s.literal.text).join('');return null;}
 function direct(n){let found=[];walk(n,x=>{
  if(!ts.isCallExpression(x)||!ts.isPropertyAccessExpression(x.expression)||x.expression.expression.getText(ast)!=='api')return;
  const method=x.expression.name.text.toUpperCase();if(!['POST','PUT','DELETE','GET'].includes(method)||!x.arguments[0])return;
  const url=pathValue(x.arguments[0]);if(!url)return;const p='/api/v1'+url.split('?')[0];
  const matches=rows.filter(r=>r.methods.includes(method)&&new RegExp('^'+r.path.replace(/\{[^}]+\}/g,'[^/]+')+'$').test(p));
  for(const r of matches)if(r.mode==='business'){
   if(method==='GET'&&!/(export|download|preview)/.test(r.id))continue;
   let tier=r.tier;
   if(r.variants){const body=x.arguments[1];let literal; if(body&&ts.isObjectLiteralExpression(body))for(const prop of body.properties)if(ts.isPropertyAssignment(prop)&&prop.name.getText(ast)===r.variants.field&&ts.isStringLiteral(prop.initializer))literal=prop.initializer.text;
    tier=literal?r.variants.values[literal]?.tier:undefined;
   }
   found.push(r.id+(tier?'#'+tier:''));
  }
 });return found;}
 function resolve(n,seen=new Set()){
  let found=direct(n);walk(n,x=>{
   const id=ts.isIdentifier(x)?x.text:null;
   if(id&&funcs.has(id)&&!seen.has(id)){const next=new Set(seen);next.add(id);found.push(...resolve(funcs.get(id),next));}
   if(ts.isCallExpression(x)&&ts.isIdentifier(x.expression)&&stateActions.has(x.expression.text)&&x.arguments[0]?.kind!==ts.SyntaxKind.FalseKeyword&&x.arguments[0]?.kind!==ts.SyntaxKind.NullKeyword)found.push(...stateActions.get(x.expression.text));
  });return [...new Set(found)];
 }
 // Link opening a modal to its guarded submit actions, not its cancel buttons.
 walk(ast,n=>{
  if(!ts.isBinaryExpression(n)||n.operatorToken.kind!==ts.SyntaxKind.AmpersandAmpersandToken||!ts.isIdentifier(n.left))return;
  const key=n.left.text;if(!/^(show|edit|create|open|.*Modal)/.test(key))return;
  let actions=[];walk(n.right,x=>{if(ts.isJsxAttribute(x)&&['onSubmit','onConfirm'].includes(x.name.getText(ast))&&x.initializer)actions.push(...resolve(x.initializer));});
  if(actions.length)stateActions.set('set'+key[0].toUpperCase()+key.slice(1),[...new Set(actions)]);
 });
 const edits=[],entries=[];
 walk(ast,n=>{
  const opening=ts.isJsxElement(n)?n.openingElement:ts.isJsxSelfClosingElement(n)?n:null;if(!opening)return;
  const tag=opening.tagName.getText(ast);
  if(!['button','input','label','FormModal','Modal','ConfirmDialog'].includes(tag))return;
  const attrs=opening.attributes.properties.filter(ts.isJsxAttribute);
  const handlers=attrs.filter(a=>['onClick','onSubmit','onConfirm','onChange'].includes(a.name.getText(ast))&&a.initializer);
  if(!handlers.length)return;
  let actions=[...new Set(handlers.flatMap(a=>resolve(a.initializer)))];
  // Clear/cancel events never require a business grant.
  if(handlers.every(a=>/^\{\(\) => set\w+\((false|null|""|''|\[\])\)\}$/.test(a.initializer.getText(ast))))return;
  if(!actions.length){entries.push({line:ast.getLineAndCharacterOfPosition(n.getStart()).line+1,status:'unresolved',handler:handlers.map(a=>a.initializer.getText(ast)).join(';').slice(0,180)});return;}
  // Inputs may use uploads/personal flows; only explicit known business action gates.
  const start=n.getStart(ast),end=n.end;
  edits.push({pos:start,text:'<ActionGate anyOf={'+JSON.stringify(actions)+'}>'},{pos:end,text:'</ActionGate>'});
  entries.push({line:ast.getLineAndCharacterOfPosition(start).line+1,status:'gated',actions});
 });
 if(edits.length){edits.sort((a,b)=>b.pos-a.pos);for(const e of edits)source=source.slice(0,e.pos)+e.text+source.slice(e.pos);source=source.replace(/(["']use client["'];?)/,'$1\nimport ActionGate from "@/components/permissions/ActionGate";');fs.writeFileSync(file,source);}
 report.push({file:path.relative(ROOT,file),entries});
}
fs.writeFileSync(path.join(ROOT,'docs/permissions-round6-20261028/frontend-gates.json'),JSON.stringify(report,null,2));
console.log(report.reduce((a,r)=>a+r.entries.filter(e=>e.status==='gated').length,0),'gates; unresolved retained for review');
