"""Manually reviewed mappings for split assertions and intentionally changed permissions.

Keys are original e51b636 test source lines. Values select actual new assertions;
this table never changes test outcomes. Helper selectors begin with @.
"""
OVERRIDES={
('test_disabled_financial_reversals.py',53):['response.status_code == expected','response.json()=='],
('test_payroll_expense.py',60):["ledger.json()['total_expense']==1234.56",'assert legacy_ledger_label'],
('test_payroll_expense.py',70):['@assert_disabled:response.status_code==400',"revoke['reversed_expense_id']"],
('test_payroll_expense.py',121):['again.status_code==409'],
('test_payroll_expense.py',145):['not await rows(factory,ExpenseRecord)','rows(factory,DataChangeHistory)==history_before'],
('test_payroll_expense.py',159):['r.status_code==400 and'],
('test_payroll_cash_advance.py',99):['@assert_disabled:response.status_code==400',"revoked[\"reversed_cash_advance_id\"]"],
('test_payroll_cash_advance.py',146):['await balances(c) == {1: 10000, 3: 20000}','@assert_disabled:response.status_code==400'],
('test_payroll_cash_advance.py',198):['retry.status_code == 409'],
('test_payroll_cash_advance.py',201):['@assert_disabled:response.status_code==400','["payroll_available_amount"] == 3000'],
('test_reimbursement_payments.py',135):['@assert_disabled:response.status_code==400','revoked["status"] == "approved"'],
('test_reimbursement_payments.py',181):['@assert_disabled:response.status_code==400','revoked["cash_advance_id"] is None'],
('test_reimbursement_payments.py',293):['"撤销功能已停用" in r.text'],
('test_reimbursement_payments.py',386):['r["status"] == "partially_approved"','@assert_disabled:response.status_code==400'],
('test_reimbursement_payments.py',410):['response.status_code == (400 if route.endswith'],
('test_reimbursement_payments.py',425):['pay(c, rid, photo, uid=4)).status_code == 403','await snapshot(f)==before'],
('test_cash_advance_repayments.py',167):['r.status_code == expected','r.json()=={"detail":message}','"撤销功能已停用" in r.text'],
('test_cash_advance_repayments.py',193):['r.status_code == 409 and "缺少有效核验'],
('test_cash_advance_repayments.py',224):['r["advance"]["status"] == "confirmed"','@assert_disabled:response.status_code==400'],
('test_cash_advance_documents.py',63):['manual["reviewed_by_id"] is None'],
('test_cash_advance_documents.py',137):['r.json()["status"]=="pending" and r.json()["reviewed_by_id"] is None'],
('test_round18_advance_review.py',34):['@post_ok:response.status_code==200','@approve_advance:response.json()[\'approval_status\']==\'approved_ready\''],
('test_round18_advance_review.py',195):['@post_ok:response.status_code==200','@approve_advance:response.json()[\'approval_status\']==\'approved_ready\''],
('test_advance_manager_recipients.py',151):["r.status_code==403 and r.json()=={'detail':'无权访问所选仓库'}"],
}
