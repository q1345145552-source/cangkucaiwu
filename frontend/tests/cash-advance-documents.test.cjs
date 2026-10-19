// Execute actual page handlers: multi-selection, amount override, editing and read-only linked details.
const assert=require('node:assert/strict');
const {harness,walk,text,find,button,labelled,field,change}=require('./cash-advances.test.cjs');
const docs=[...[{id:2,amount:3000},{id:4,amount:4000}].map(r=>({document_type:'payroll',document_type_label:'工资单',document_id:r.id,document_number:`工资单 #${r.id}`,title:'员工1 · 2026-10',document_date:'2026-10-15',amount:r.amount,currency:'THB'})),
 {document_type:'payable',document_id:31,document_number:'AP-31',title:'供应商',amount:2000,currency:'THB'},
 {document_type:'reimbursement',document_id:31,document_number:'报销单 #31',title:'主管',amount:1000,currency:'THB'},
 {document_type:'employee_advance',document_id:31,document_number:'预支单 #31',title:'员工1',amount:800,currency:'THB'}];
const submit=async(h,t)=>{await find(t,n=>n.type==='form').props.onSubmit({preventDefault(){}});await new Promise(r=>setTimeout(r,0));return h.render();};
(async()=>{
 let h=harness('supervisor',true,{documents:docs}),t=await h.render();await button(t,'新建垫款单').props.onClick();t=await h.render();
 labelled(t,'关联 工资单 #2').props.onChange();t=await h.render();assert.equal(field(t,'金额').props.value,'3000.00');
 labelled(t,'关联 工资单 #4').props.onChange();t=await h.render();assert.equal(field(t,'金额').props.value,'7000.00');
 assert(text(t).includes('已选 2 张，合计 7,000.00 泰铢'));
 change(field(t,'用途请选择用途工资采购费用其他'),'salary');t=await h.render();change(field(t,'金额'),'6000');t=await h.render();
 await submit(h,t);assert.equal(h.writes.length,0);assert(h.messages.some(m=>m[1].includes('请填写差额备注')));
 change(labelled(t,'差额备注'),'差额1000另行结算');t=await h.render();t=await submit(h,t);
 assert.equal(h.writes[0].body.linked_documents.length,2);assert.equal(h.writes[0].body.amount,'6000');assert.equal(h.rows[0].status,'pending');
 assert(h.messages.some(m=>m[1]==='垫款单已登记，待仓库管理员确认'));
 await button(t,'编辑').props.onClick();t=await h.render();assert.equal(field(t,'金额').props.value,'6000');assert.equal(labelled(t,'差额备注').props.value,'差额1000另行结算');
 assert.equal(labelled(t,'关联 工资单 #2').props.checked,true);assert.equal(labelled(t,'关联 工资单 #4').props.checked,true);
 labelled(t,'移除 工资单 #4').props.onClick();t=await h.render();assert.equal(field(t,'金额').props.value,'3000.00');
 t=await submit(h,t);assert.equal(h.writes[1].method,'PUT');assert.equal(h.rows[0].linked_documents.length,1);
 button(t,'查看 1 张单据').props.onClick({stopPropagation(){}});t=await h.render();
 await button(t,'工资单 #2 · 员工1 · 2026-103,000.00 泰铢 · 查看单据详情').props.onClick();await new Promise(r=>setTimeout(r,0));t=await h.render();
 assert(text(labelled(t,'关联单据详情')).includes('关联时金额：3,000.00 泰铢'));assert(h.reads.includes('/cash-advances/1/documents/1'));
 // Four categories can be selected together without losing prior selections; changing currency clears incompatible choices.
 h=harness('warehouse_admin',true,{documents:docs});t=await h.render();await button(t,'新建垫款单').props.onClick();t=await h.render();
 for(const [kind,name] of [['payroll','工资单 #2'],['payable','AP-31'],['reimbursement','报销单 #31'],['employee_advance','预支单 #31']]){
  change(labelled(t,'关联单据类型'),kind);t=await h.render();labelled(t,`关联 ${name}`).props.onChange();t=await h.render();
 }
 assert.equal(field(t,'金额').props.value,'6800.00');assert(text(t).includes('已选 4 张'));
 change(labelled(t,'垫款币种'),'CNY');t=await h.render();assert(!text(t).includes('已选 4 张'));assert(text(t).includes('暂无本仓同币种'));
 // Empty manual entry keeps amount editable; administrator sees automatic confirmation feedback.
 change(field(t,'金额'),'600');t=await h.render();change(field(t,'用途请选择用途工资采购费用其他'),'expense');t=await h.render();change(field(t,'说明'),'临时耗材');t=await h.render();t=await submit(h,t);
 assert.equal(h.writes[0].body.linked_documents.length,0);assert.equal(h.rows[0].status,'confirmed');assert(h.messages.some(m=>m[1]==='垫款单已登记并确认'));
 // More than one page, load errors, hidden edit on used records and save scrolling structure.
 const many=Array.from({length:51},(_,i)=>({...docs[0],document_id:i+100,document_number:`工资单 #${i+100}`}));
 h=harness('warehouse_admin',true,{documents:many});t=await h.render();await button(t,'新建垫款单').props.onClick();t=await h.render();await button(t,'下一组').props.onClick();t=await h.render();assert(text(t).includes('工资单 #150'));
 change(labelled(t,'搜索关联单据'),'不存在');t=await h.render();assert(text(t).includes('暂无本仓同币种'));
 h=harness('warehouse_admin',true,{documentError:true});t=await h.render();await button(t,'新建垫款单').props.onClick();t=await h.render();assert(text(t).includes('单据加载失败'));
 h=harness();h.rows.push({id:9,payer_name:'主管',amount:1000,currency:'THB',outstanding_amount:1000,status:'confirmed',can_edit:false});t=await h.render();assert(!walk(t).some(n=>n.type==='button'&&text(n)==='编辑'));
 console.log('PASS: 12 linked-document UI scenarios, multi-select totals, difference note, manual entry, admin/supervisor status, edit replay, linked details, currency, pagination, errors and used-record lock');
})().catch(e=>{console.error(e);process.exitCode=1;});
