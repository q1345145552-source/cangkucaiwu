// Execute the real UI handlers; the server suite verifies authentication, balances and persistent audit.
const assert=require('node:assert/strict');
const {harness,walk,text,find,button,change}=require('./fund-disbursement.test.cjs');
const labelled=(t,name)=>find(t,n=>n.props?.['aria-label']===name);
async function ready(){
 const h=harness();let t=await h.render();await button(t,'充值').props.onClick();t=await h.render();change(find(t,n=>n.props?.placeholder==='输入金额'),'10000');t=await h.render();await button(t,'确认充值').props.onClick();t=await h.render();
 await button(t,'开销').props.onClick();t=await h.render();change(find(t,n=>n.type==='input'&&n.props.type==='number'&&n.props.value===''),'2000');t=await h.render();find(t,n=>n.props?.id==='receiptFileInput4').props.onChange({target:{files:[new Blob(['photo'],{type:'image/png'})]}});t=await h.render();await button(t,'保存').props.onClick();t=await h.render();
 await find(t,n=>n.type==='tr'&&typeof n.props?.onClick==='function').props.onClick();t=await h.render();return{h,t};
}
(async()=>{
 let {h,t}=await ready();assert(labelled(t,'编辑开销 #8'));assert(labelled(t,'作废开销 #8'));
 labelled(t,'编辑开销 #8').props.onClick();t=await h.render();assert(text(t).includes('编辑开销'));assert(text(t).includes('已有凭证会保留'));
 const currency=walk(t).find(n=>n.type==='select'&&n.props.value==='THB');assert.equal(currency.props.disabled,true);
 change(find(t,n=>n.type==='input'&&n.props.type==='number'&&n.props.value==='2000'),'1500');t=await h.render();await button(t,'保存').props.onClick();t=await h.render();
 assert.equal(h.writes.at(-1).method,'PUT');assert.equal(h.writes.at(-1).body.amount,1500);assert.equal(h.writes.at(-1).body.receipt,'/uploads/fund_receipts/1/1/test.png');assert.equal(h.uploads.length,1);assert.equal(h.fund.available,8500);
 labelled(t,'作废开销 #8').props.onClick();t=await h.render();assert(text(t).includes('作废后记录保留'));await button(t,'确认作废').props.onClick();assert(h.messages.some(m=>m[1]==='请填写作废原因'));assert.equal(h.writes.filter(w=>w.method==='DELETE').length,0);
 change(labelled(t,'开销作废原因'),'重复登记');t=await h.render();await button(t,'确认作废').props.onClick();t=await h.render();assert.equal(h.writes.at(-1).method,'DELETE');assert.equal(h.writes.at(-1).body.reason,'重复登记');assert.equal(h.fund.available,10000);assert.equal(h.items.length,1);assert(text(t).includes('已作废'));
 assert(!walk(t).some(n=>n.props?.['aria-label']==='编辑开销 #8'||n.props?.['aria-label']==='作废开销 #8'||n.props?.['aria-label']==='查看开销 #8 凭证'));
 // Other roles see no management buttons, even if an untrusted response advertises can_edit/can_void.
 for(const role of ['supervisor','staff','warehouse_labor','super_admin']){
  h=harness({role});h.items.push({id:8,amount:2000,category:'耗材',review_status:'pending',receipt:'/uploads/x.png',can_edit:true,can_void:true});t=await h.render();await find(t,n=>n.type==='tr'&&typeof n.props?.onClick==='function').props.onClick();t=await h.render();assert(!walk(t).some(n=>/^编辑开销|^作废开销/.test(n.props?.['aria-label']||'')),role);
 }
 ({h,t}=await ready());h.items[0].review_status='approved';h.items[0].can_edit=h.items[0].can_void=false;t=await h.render();assert(!walk(t).some(n=>/^编辑开销|^作废开销/.test(n.props?.['aria-label']||'')));
 console.log('PASS: admin edit with retained receipt, unchanged currency, reason-required soft void, balance refresh, gray inactive record and hidden controls for supervisor/staff/labor/super-admin/approved items');
})().catch(e=>{console.error(e);process.exitCode=1;});
