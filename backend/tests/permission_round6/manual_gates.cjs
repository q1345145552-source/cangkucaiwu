// Explicit mapping for modal openers, indirect request clients and dynamic paths.
const fs=require('fs'),path=require('path'),ts=require('/private/tmp/permissions-round5-env/frontend/node_modules/typescript');
const root=path.resolve(__dirname,'../../..');
const maps={
'accounts': {'openEdit':'payment_accounts.update_account','openCreate':'payment_accounts.create_account','saveTransfer':'payment_accounts.create_transfer'},
'attendance':{'setShowRestForm':'attendance.set_rest_days','setShowAbsenceForm':'attendance.mark_absence','setShowBatchMakeup':'clock_in.batch_makeup_clock_in'},
'cash-advances':{'setRejectId':'cash_advance.reject_advance','setRepayAdvance':'cash_advance.repay_advance'},
'credit':{'setShowForm':'credit.create_credit','openPayment':'credit.record_repayment'},
'customers':{'openEdit':'customers.update_customer','openCreate':'customers.create_customer'},
'deduction-templates':{'openCreate':'deduction_template.create_deduction_template','openEdit':'deduction_template.update_deduction_template'},
'employee-advances':{'setShowForm':'employee_advance.create_advance','executeStage':'employee_advance.verify_advance','setRejectId':'employee_advance.reject_advance','review':'employee_advance.approve_advance'},
'employee-deductions':{'setShowForm':'employee_deduction.create_deduction'},
'employees':{'setShowForm':'employees.create_employee','openBatchModal':'employees.batch_set_templates','editEmployee':'employees.update_employee','setDeleteTarget':'employees.delete_employee','openFixedEdit':'employee_deduction.update_fixed_deduction','uploadPhoto':'employees.upload_employee_photo','uploadPassportPhoto':'employees.upload_passport_photo','uploadWorkPermitPhoto':'employees.upload_work_permit_photo'},
'expense-approvals':{'openCreate':'expense_approval.create_approval','openEdit':'expense_approval.update_approval','setRejectId':'expense_approval.reject_approval','openPay':'expense_approval.pay_approval'},
'expense-fund':{'setShowCreate':'expense_fund.create_account','openEditExpense':'expense_fund.edit_item','executeRecharge':'expense_fund.execute_recharge'},
'group-order':{'setShowCreate':'group_order.create_group_order'},
'income-expense':{'openCreate':'income_expense.create_expense','handleCreate':'income_expense.create_expense'},
'incoming':{'handleCreate':'incoming.create_incoming','uploadForRow':'incoming.upload_incoming_screenshot'},
'market':{'setShowForm':'market.create_item','uploadImage':'market.create_item'},
'operating':{'openCreate':'income_expense.create_expense','openEdit':'income_expense.update_expense','handleCreate':'income_expense.create_expense','handleEditSave':'income_expense.update_expense','doConfirmDeleteVoucher':'income_expense.update_expense'},
'other-income-expense':{'openCreate':'income_expense.create_income','openEdit':'income_expense.update_income'},
'overtime':{'setShowForm':'overtime.create_overtime','openVerify':'overtime.verify_overtime'},
'payable':{'openBillForm':'payable.create_bill','confirmBoss':'payable.confirm_bill','openPayModal':'payable.pay_bill','openEditModal':'payable.update_bill','handleCreate':'payable.create_bill','handlePay':'payable.pay_bill'},
'payment-plans':{'setShowForm':'payable.create_plan','handleUploadAttachment':'payable.upload_plan_attachment'},
'payroll':{'handleBatchDisburse':'payroll.batch_disburse_payroll','openBatchRecalc':'payroll.batch_recalc_payroll','openRecalcOne':'payroll.recalc_payroll','handleDisburse':'payroll.disburse_payroll'},
'recharge':{'openEdit':'recharge.edit_recharge'},
'reimbursement':{'openEdit':'reimbursement.edit_reimb','workflowAction':'reimbursement.verify_reimb','setItemDecision':'reimbursement.review_reimb'},
'salary-templates':{'openCreate':'salary_template.create_salary_template','openEdit':'salary_template.update_salary_template'},
'supplier-skus':{'setShowForm':'sku_catalog.create','edit':'sku_catalog.update','setImportFile':'suppliers.import_products'},
'suppliers':{'handleSupplierImport':'suppliers.import_products','setImportMode':'suppliers.import_products','handleReceiptUpload':'suppliers.upload_purchase_receipt','setShowForm':'suppliers.create_supplier','approveOrder':'suppliers.approve_purchase','startDuty':'suppliers.reject_purchase','confirmApprove':'suppliers.approve_purchase','confirmReject':'suppliers.reject_purchase','openReceiveForm':'suppliers.receive_purchase','submitReceive':'suppliers.receive_purchase','triggerReceiptUpload':'suppliers.upload_purchase_receipt'},
'warehouses':{'setShowForm':'warehouses.create_warehouse','openEdit':'warehouses.update_warehouse'},
'ClockRecordsGrid':{'openMakeupForm':'clock_in.makeup_clock_in'},
'CreditShipments':{'openForm':'credit.create_shipment'},
'MakeupBatchHistory':{'setConfirmBatch':'clock_in.revoke_makeup_batch'},
'PayableDetail':{'onConfirm':'payable.confirm_bill','upload':'payable.upload_bill_attachment','onPay':'payable.pay_bill'},
'ProcurementControls':{'savePolicy':'procurement_controls.set_policy','saveGrant':'procurement_controls.grant'},
'ProcurementRiskReview':{'submit':'procurement_risk.save_review'},
'PurchaseReceiptInfo':{'photo':'suppliers.upload_purchase_receipt'},
};
const rows=JSON.parse(fs.readFileSync(path.join(root,'backend/app/core/action_catalog.json'))).routes;
const ids=new Set(rows.map(r=>r.id));const missing=[];
for(const [page,mapping] of Object.entries(maps))for(const [handler,id] of Object.entries(mapping))if(!ids.has(id))missing.push({page,handler,id,candidates:rows.filter(r=>r.id.startsWith(id.split('.')[0]+'.')&&r.tier!=='view').map(r=>r.id)});
if(missing.length){fs.writeFileSync(path.join(root,'docs/permissions-round6-20261028/manual-gates-missing.json'),JSON.stringify(missing,null,2));console.log('Missing IDs',missing.length);process.exit(1);}
function walk(n,f){f(n);ts.forEachChild(n,c=>walk(c,f));}
let report=[];
for(const [key,mapping] of Object.entries(maps)){
 const f=key[0]===key[0].toUpperCase()?`frontend/src/components/${key}.tsx`:`frontend/src/app/(dashboard)/${key}/page.tsx`;const p=path.join(root,f);let source=fs.readFileSync(p,'utf8');const ast=ts.createSourceFile(p,source,ts.ScriptTarget.Latest,true,ts.ScriptKind.TSX),edits=[];
 walk(ast,n=>{
  const o=ts.isJsxElement(n)?n.openingElement:ts.isJsxSelfClosingElement(n)?n:null;if(!o||o.tagName.getText(ast)!=='button')return;
  const a=o.attributes.properties.find(a=>ts.isJsxAttribute(a)&&a.name.getText(ast)==='onClick');if(!a?.initializer)return;const h=a.initializer.getText(ast);
  if(/set\w+\((false|null|""|'')\)/.test(h)&&!/(true|editEmployee)/.test(h))return;
  let parent=n.parent;while(parent){if(ts.isJsxElement(parent)&&parent.openingElement.tagName.getText(ast)==='ActionGate')return;parent=parent.parent;}
  const actions=[...new Set(Object.entries(mapping).filter(([name])=>new RegExp('\\b'+name+'\\b').test(h)).map(([,id])=>id))];if(!actions.length)return;
  edits.push({pos:n.getStart(),text:'<ActionGate anyOf={'+JSON.stringify(actions)+'}>'},{pos:n.end,text:'</ActionGate>'});report.push({file:f,handler:h,actions});
 });
 if(edits.length){for(const e of edits.sort((a,b)=>b.pos-a.pos))source=source.slice(0,e.pos)+e.text+source.slice(e.pos);if(!source.includes('import ActionGate '))source=source.replace(/(["']use client["'];?)/,'$1\nimport ActionGate from "@/components/permissions/ActionGate";');fs.writeFileSync(p,source);}
}
fs.writeFileSync(path.join(root,'docs/permissions-round6-20261028/frontend-manual-gates.json'),JSON.stringify(report,null,2));console.log(report.length,'manual gates');
