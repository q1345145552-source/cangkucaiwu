"""One-time reviewed catalogue source: outputs explicit routes, not runtime HTTP heuristics."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
source=json.loads((ROOT/'docs/permissions-round5-20261028/route-catalog.json').read_text())
MODULES={'payment_accounts':'accounts','income_expense':'operating','cost_funds_debt':'reports','cost_identity':'reports','settings_api':'settings','config_api':'config_center','exchange_rates':'settings','employee_advance':'employee_advances','salary_template':'salary_templates','deduction_template':'deduction_templates','employee_deduction':'employee_deductions','cash_advance':'cash_advances','efficiency':'labor_efficiency','clock_in':'attendance','history':'modification_logs','procurement_controls':'suppliers','procurement_risk':'suppliers','procurement_report':'suppliers','supplier_quotes':'suppliers','users':'settings','upload':'uploads','secure_uploads':'attachments'}
APPROVE={
'inventory':{'review_count'},'procurement_controls':{'grant','revoke'},'procurement_risk':{'save_review'},
'suppliers':{'approve_purchase','reject_purchase'},'reimbursement':{'review_reimb'},
'payable':{'confirm_bill','approve_bill_payment'},'market':{'review_item'},
'attendance':{'approve_leave','reject_leave'},'clock_in':{'approve_makeup_request'},
'overtime':{'verify_overtime'},'payroll':{'confirm_payroll','confirm_all_payroll','batch_confirm_payroll'},
'employee_advance':{'approve_advance','reject_advance'},'expense_approval':{'approve_approval','reject_approval'},
'cash_advance':{'confirm_advance','reject_advance'}}
READ_POST={('payroll','preview_payroll'),('supplier_quotes','preview'),('suppliers','ai_compare'),('settings_api','backup_all_data')}
UTILITY={('auth','login'):'public login',('auth','get_me'):'current identity',('auth','change_password'):'self password',('auth','attachment_session'):'file-only cookie; reads recheck current grants',('users','list_available_permissions'):'permission metadata',('warehouses','list_warehouses'):'authorized warehouse selector',('settings_api','get_boss_contact'):'contact utility',('main','root'):'health metadata',('main','health'):'health metadata',('dashboard','dashboard_stats'):'field-filtered home',('dashboard','boss_todos'):'module-filtered home'}
SELF_ALWAYS={('clock_in','clock_in'),('clock_in','get_today'),('clock_in','request_personal_makeup'),('attendance','create_leave'),('overtime','confirm_overtime'),('overtime','dispute_overtime'),('payroll','my_payslip'),('employee_advance','my_debt')}
SELF_OPTIONAL={'clock_in':{'list_records','get_photos','list_makeup_requests'},'attendance':{'list_leaves','list_rest_days','get_calendar'},'overtime':{'list_overtimes','pending_overtimes','monthly_hours','get_overtime_limit'},'reimbursement':{'list_reimbursements','create_reimbursement','list_reimb_categories','get_reimb_detail','edit_reimb','delete_reimb','submit_reimb'},'expense_fund':{'list_accounts','list_items','add_item','upload_receipt','submit_recharge_request','list_recharge_requests','upload_new_item_receipt','list_disbursements'},'employee_advance':{'create_advance','list_funding_options'}}
ADMIN_MODULE_WRITES={'salary_template','deduction_template','employee_deduction','exchange_rates','config_api','procurement_controls'}
ADMIN_ACTIONS={'employees':{'create_employee','bind_existing_accounts','batch_set_templates','set_max_limit'},'payment_accounts':{'create_account','update_account','toggle_account_status','delete_account'},'expense_fund':{'create_account','edit_item','void_item','update_settings'},'suppliers':{'set_match_policy','set_price_threshold','set_approval_threshold','set_concentration_threshold'},'overtime':{'set_overtime_limit'},'expense_approval':{'set_threshold'},'inventory':{'set_policy','confirm_opening','resolve_receipt','reverse','review_count','set_controls'},'efficiency':{'set_standard'}}
FINANCIAL={'payroll','salary_templates','deduction_templates','employee_deductions','reports','operating','incoming','reconciliation','payable','payment_plans','cash_advances','credit','ledger','other_income_expense'}
rows=[]
for item in source:
 module=item['module'].rsplit('.',1)[-1];name=item['handler'];key=(module,name);bucket=MODULES.get(module,module)
 if module=='attendance' and 'leave' in name:bucket='leave'
 if module=='payable' and ('plan' in name or name in {'cashflow_prediction','payable_timeline','get_monthly_order','save_monthly_order'}):bucket='payment_plans'
 if module=='settings_api' and name=='operation_logs':bucket='audit_logs'
 if module=='sku_catalog' and 'GET' not in item['methods']:bucket='sku_catalog_manage'
 if module=='income_expense' and name in ('ledger','ledger_export'):bucket='ledger'
 if module=='income_expense' and 'income' in name:bucket='other_income_expense'
 tier='view' if 'GET' in item['methods'] or key in READ_POST else 'approve' if name in APPROVE.get(module,set()) else 'operate'
 roles=['warehouse_admin','staff','supervisor']
 if bucket in FINANCIAL:roles=['warehouse_admin','staff']
 if tier=='approve':roles=['warehouse_admin','supervisor'] if module in {'attendance','clock_in','overtime'} else ['warehouse_admin']
 if tier!='view' and (module in ADMIN_MODULE_WRITES or name in ADMIN_ACTIONS.get(module,set())):roles=['warehouse_admin']
 if module in ('users','warehouses','settings_api','history','market','group_order'):
  roles.append('super_admin')
 if module in ('users','warehouses') and tier!='view':roles=['warehouse_admin','super_admin']
 if module in ('attendance','clock_in','overtime') and tier!='view':roles=[r for r in roles if r!='staff']
 if module=='suppliers' and name=='ai_evaluate':roles=['super_admin']
 if module=='settings_api' and name=='backup_all_data':roles=['super_admin']
 if module=='settings_api' and name=='set_boss_contact':roles=['warehouse_admin','super_admin']
 if module=='expense_fund' and name in ('topup_account','execute_recharge'):roles=['warehouse_admin','staff']
 reason=UTILITY.get(key)
 mode='utility' if reason else 'self' if key in SELF_ALWAYS else 'attachment' if module=='secure_uploads' else 'upload' if key==('upload','upload_file') else 'business'
 row={**item,'id':module+'.'+name,'module_key':bucket,'tier':tier,'roles':sorted(set(roles)),'mode':mode,'reason':reason or ('formal employee identity and existing self guards' if mode=='self' else 'existing role/object/state guards also required'),'personal_variant':name in SELF_OPTIONAL.get(module,set()),'warehouse_source':'existing verified header/query + object warehouse; role grants never widen scope','object_and_state':'existing handler and associated service; no new financial state or self-approval policy','field_policy':'round5 projections, history module+field scope and actual attachment references remain authoritative','audit':'permission changes audited separately; existing business audit retained','minimal_read_dependencies':[]}
 if module=='expense_fund' and name in ('batch_review','review_recharge_request'):
  row['variants']={'field':'action','values':{'verify':{'tier':'operate','roles':['warehouse_admin','staff']},'approve':{'tier':'approve','roles':['warehouse_admin']},'reject':{'tier':'approve','roles':['warehouse_admin']}}}
 if module=='upload' and name=='upload_recharge_screenshot':row['module_key']='recharge'
 rows.append(row)
(Path('/private/tmp/permissions-round6-env')/'historical-catalogue-draft.json').write_text(json.dumps({'version':1,'routes':rows},ensure_ascii=False,indent=2)+'\n')
print(len(rows))
