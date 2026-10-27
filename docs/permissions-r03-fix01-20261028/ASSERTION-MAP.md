# 124项旧前置失败：逐断言执行映射

每项列出原断言全文、当前测试与行号、是否实际到达及失败。`changed`须结合变更说明；不凭相似文本声称等价。原失败调用点之后的语句列为曾被遮挡，条件分支是否应运行另见当前实际跟踪。完整helper检查见原始assertions-final.json。

## 001 tests.test_disabled_financial_reversals::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[1]

当前 `tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[1]`：**passed**；原失败调用行 61。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|43 `assert reject_disabled_financial_reversal not in app.dependency_overrides`|tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[1] @ test_disabled_financial_reversals.py:45 已到达|exact assertion expression|
|53 `assert response.status_code == 400 and response.json() == {"detail": REVERSAL_DISABLED_MESSAGE}, response.text`|tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[1] @ test_disabled_financial_reversals.py:56 已到达; tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[1] @ test_disabled_financial_reversals.py:57 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|54 `assert await database_snapshot(f) == before`|tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[1] @ test_disabled_financial_reversals.py:59 已到达|exact assertion expression|
|60 `assert more.status_code == 200 and more.json()["advance"]["repaid_amount"] == 1500, more.text`|tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[1] @ test_disabled_financial_reversals.py:65 已到达|exact assertion expression|

## 002 tests.test_disabled_financial_reversals::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[2]

当前 `tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[2]`：**passed**；原失败调用行 61。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|43 `assert reject_disabled_financial_reversal not in app.dependency_overrides`|tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[2] @ test_disabled_financial_reversals.py:45 已到达|exact assertion expression|
|53 `assert response.status_code == 400 and response.json() == {"detail": REVERSAL_DISABLED_MESSAGE}, response.text`|tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[2] @ test_disabled_financial_reversals.py:56 已到达; tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[2] @ test_disabled_financial_reversals.py:57 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|54 `assert await database_snapshot(f) == before`|tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[2] @ test_disabled_financial_reversals.py:59 已到达|exact assertion expression|
|60 `assert more.status_code == 200 and more.json()["advance"]["repaid_amount"] == 1500, more.text`|tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[2] @ test_disabled_financial_reversals.py:65 已到达|exact assertion expression|

## 003 tests.test_disabled_financial_reversals::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[3]

当前 `tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[3]`：**passed**；原失败调用行 61。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|43 `assert reject_disabled_financial_reversal not in app.dependency_overrides`|tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[3] @ test_disabled_financial_reversals.py:45 已到达|exact assertion expression|
|53 `assert response.status_code == 400 and response.json() == {"detail": REVERSAL_DISABLED_MESSAGE}, response.text`|tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[3] @ test_disabled_financial_reversals.py:56 已到达; tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[3] @ test_disabled_financial_reversals.py:57 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|54 `assert await database_snapshot(f) == before`|tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[3] @ test_disabled_financial_reversals.py:59 已到达|exact assertion expression|
|60 `assert more.status_code == 200 and more.json()["advance"]["repaid_amount"] == 1500, more.text`|tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[3] @ test_disabled_financial_reversals.py:65 已到达|exact assertion expression|

## 004 tests.test_disabled_financial_reversals::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[4]

当前 `tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[4]`：**passed**；原失败调用行 61。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|43 `assert reject_disabled_financial_reversal not in app.dependency_overrides`|tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[4] @ test_disabled_financial_reversals.py:45 已到达|exact assertion expression|
|53 `assert response.status_code == 400 and response.json() == {"detail": REVERSAL_DISABLED_MESSAGE}, response.text`|tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[4] @ test_disabled_financial_reversals.py:56 已到达; tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[4] @ test_disabled_financial_reversals.py:57 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|54 `assert await database_snapshot(f) == before`|tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[4] @ test_disabled_financial_reversals.py:59 已到达|exact assertion expression|
|60 `assert more.status_code == 200 and more.json()["advance"]["repaid_amount"] == 1500, more.text`|tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[4] @ test_disabled_financial_reversals.py:65 已到达|exact assertion expression|

## 005 tests.test_disabled_financial_reversals::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[5]

当前 `tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[5]`：**passed**；原失败调用行 61。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|43 `assert reject_disabled_financial_reversal not in app.dependency_overrides`|tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[5] @ test_disabled_financial_reversals.py:45 已到达|exact assertion expression|
|53 `assert response.status_code == 400 and response.json() == {"detail": REVERSAL_DISABLED_MESSAGE}, response.text`|tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[5] @ test_disabled_financial_reversals.py:56 已到达; tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[5] @ test_disabled_financial_reversals.py:57 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|54 `assert await database_snapshot(f) == before`|tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[5] @ test_disabled_financial_reversals.py:59 已到达|exact assertion expression|
|60 `assert more.status_code == 200 and more.json()["advance"]["repaid_amount"] == 1500, more.text`|tests/test_disabled_financial_reversals.py::test_three_endpoints_disabled_for_every_authenticated_role_without_any_write[5] @ test_disabled_financial_reversals.py:65 已到达|exact assertion expression|

## 006 tests.test_disabled_financial_reversals::test_revoked_history_amounts_and_ledger_readback_unchanged

当前 `tests/test_disabled_financial_reversals.py::test_revoked_history_amounts_and_ledger_readback_unchanged`：**passed**；原失败调用行 107。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|97 `assert prior[0]["data"][0]["status"] == prior[1]["data"][0]["status"] == "revoked"`|tests/test_disabled_financial_reversals.py::test_revoked_history_amounts_and_ledger_readback_unchanged @ test_disabled_financial_reversals.py:96 已到达|exact assertion expression|
|98 `assert prior[0]["data"][0]["amount"] == 2000 and prior[1]["data"][0]["amount"] == 1000`|tests/test_disabled_financial_reversals.py::test_revoked_history_amounts_and_ledger_readback_unchanged @ test_disabled_financial_reversals.py:97 已到达|exact assertion expression|
|99 `assert not next(r for r in prior[3]["data"] if r["id"] == 2)["disbursed"]`|tests/test_disabled_financial_reversals.py::test_revoked_history_amounts_and_ledger_readback_unchanged @ test_disabled_financial_reversals.py:98 已到达|exact assertion expression|
|103 `assert response.status_code == 400 and response.json()["detail"] == REVERSAL_DISABLED_MESSAGE`|tests/test_disabled_financial_reversals.py::test_revoked_history_amounts_and_ledger_readback_unchanged @ test_disabled_financial_reversals.py:102 已到达|exact assertion expression|
|105 `assert prior == after and await database_snapshot(f) == before`|tests/test_disabled_financial_reversals.py::test_revoked_history_amounts_and_ledger_readback_unchanged @ test_disabled_financial_reversals.py:104 已到达|exact assertion expression|

## 007 tests.test_payroll_expense::test_disburse_reverse_reissue_and_reports[1]

当前 `tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3]`：**failed**；原失败调用行 85。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|40 `assert accounts.status_code==200,accounts.text`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:52 已到达|exact assertion expression|
|41 `assert any(a['id']==3 and a['account_type']=='cash' for a in accounts.json()['data'])`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:53 已到达|exact assertion expression|
|42 `assert r.status_code==200,r.text`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:54 已到达|exact assertion expression|
|44 `assert r.json()['net_pay']==1234.56 and r.json()['account_id']==3`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:56 已到达|exact assertion expression|
|47 `assert rec.disbursed and rec.expense_record_id==expense.id`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:59 已到达|exact assertion expression|
|48 `assert Decimal(str(rec.net_pay))==Decimal(str(expense.amount))==Decimal('1234.56')`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:60 已到达|exact assertion expression|
|49 `assert expense.account_id==3 and expense.currency=='THB'`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:61 已到达|exact assertion expression|
|50 `assert expense.remark=='仓1 10-01到10-15 1人'`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:62 已到达|exact assertion expression|
|51 `assert expense.expense_date.date()==rec.disbursed_at.date()`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:63 已到达|exact assertion expression|
|53 `assert (cat.name,cat.type,cat.category_group,cat.warehouse_id)==('员工工资','expense','operating',1)`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:65 已到达|exact assertion expression|
|55 `assert next(x for x in paylist if x['id']==2)['expense_record_id']==expense_id`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:67 已到达|exact assertion expression|
|56 `assert exp.status_code==200,exp.text`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:68 已到达|exact assertion expression|
|58 `assert linked['payroll_record_id']==2 and linked['amount']==1234.56`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:70 已到达|exact assertion expression|
|59 `assert ledger.status_code==200,ledger.text`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:71 已到达|exact assertion expression|
|60 `assert ledger.json()['total_expense']==1234.56 and any('员工工资' in x['remark'] for x in ledger.json()['data'])`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:72 已到达; tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:99 已到达 / 行失败|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|62 `assert summary.status_code==200 and summary.json()["total_expense"]==1234.56,summary.text`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:75 已到达|exact assertion expression|
|63 `assert report.status_code==200,report.text`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:76 已到达|exact assertion expression|
|65 `assert again.status_code==400`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:78 已到达|exact assertion expression|
|66 `assert len(await rows(factory,ExpenseRecord))==1`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:79 已到达; tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:98 已到达|exact assertion expression|
|68 `assert update.status_code==400 and '工资联动支出' in update.text`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:81 已到达|exact assertion expression|
|69 `assert delete.status_code==400`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:82 已到达|exact assertion expression|
|70 `assert revoke.status_code==200,revoke.text`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ round3_flow_support.py:71 已到达; tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:84 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|71 `assert revoke.json()['reversed_expense_id']==expense_id`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:84 已到达|historical fixture dictionary replaces HTTP response wrapper|
|74 `assert rec.status=='confirmed' and not rec.disbursed and rec.expense_record_id is None`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:87 已到达|exact assertion expression|
|75 `assert await db.get(ExpenseRecord,expense_id) is None`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:88 已到达|exact assertion expression|
|77 `assert history.before_data['amount']==1234.56 and history.before_data['payroll_record_id']==2`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:90 已到达|exact assertion expression|
|78 `assert '因为撤销发放而冲销' in history.after_data['remark']`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:91 已到达|exact assertion expression|
|79 `assert ledger2.json()['total_expense']==0`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:92 已到达|exact assertion expression|
|80 `assert (await snapshot(factory))[2]==before_old`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:93 已到达|exact assertion expression|
|82 `assert reissue.status_code==200,reissue.text`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:97 已到达|exact assertion expression|
|83 `assert len(await rows(factory,ExpenseRecord))==1`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:79 已到达; tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:98 已到达|exact assertion expression|

## 008 tests.test_payroll_expense::test_disburse_reverse_reissue_and_reports[4]

当前 `tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3]`：**failed**；原失败调用行 85。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|40 `assert accounts.status_code==200,accounts.text`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:52 已到达|exact assertion expression|
|41 `assert any(a['id']==3 and a['account_type']=='cash' for a in accounts.json()['data'])`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:53 已到达|exact assertion expression|
|42 `assert r.status_code==200,r.text`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:54 已到达|exact assertion expression|
|44 `assert r.json()['net_pay']==1234.56 and r.json()['account_id']==3`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:56 已到达|exact assertion expression|
|47 `assert rec.disbursed and rec.expense_record_id==expense.id`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:59 已到达|exact assertion expression|
|48 `assert Decimal(str(rec.net_pay))==Decimal(str(expense.amount))==Decimal('1234.56')`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:60 已到达|exact assertion expression|
|49 `assert expense.account_id==3 and expense.currency=='THB'`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:61 已到达|exact assertion expression|
|50 `assert expense.remark=='仓1 10-01到10-15 1人'`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:62 已到达|exact assertion expression|
|51 `assert expense.expense_date.date()==rec.disbursed_at.date()`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:63 已到达|exact assertion expression|
|53 `assert (cat.name,cat.type,cat.category_group,cat.warehouse_id)==('员工工资','expense','operating',1)`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:65 已到达|exact assertion expression|
|55 `assert next(x for x in paylist if x['id']==2)['expense_record_id']==expense_id`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:67 已到达|exact assertion expression|
|56 `assert exp.status_code==200,exp.text`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:68 已到达|exact assertion expression|
|58 `assert linked['payroll_record_id']==2 and linked['amount']==1234.56`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:70 已到达|exact assertion expression|
|59 `assert ledger.status_code==200,ledger.text`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:71 已到达|exact assertion expression|
|60 `assert ledger.json()['total_expense']==1234.56 and any('员工工资' in x['remark'] for x in ledger.json()['data'])`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:72 已到达; tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:99 已到达 / 行失败|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|62 `assert summary.status_code==200 and summary.json()["total_expense"]==1234.56,summary.text`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:75 已到达|exact assertion expression|
|63 `assert report.status_code==200,report.text`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:76 已到达|exact assertion expression|
|65 `assert again.status_code==400`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:78 已到达|exact assertion expression|
|66 `assert len(await rows(factory,ExpenseRecord))==1`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:79 已到达; tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:98 已到达|exact assertion expression|
|68 `assert update.status_code==400 and '工资联动支出' in update.text`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:81 已到达|exact assertion expression|
|69 `assert delete.status_code==400`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:82 已到达|exact assertion expression|
|70 `assert revoke.status_code==200,revoke.text`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ round3_flow_support.py:71 已到达; tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:84 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|71 `assert revoke.json()['reversed_expense_id']==expense_id`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:84 已到达|historical fixture dictionary replaces HTTP response wrapper|
|74 `assert rec.status=='confirmed' and not rec.disbursed and rec.expense_record_id is None`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:87 已到达|exact assertion expression|
|75 `assert await db.get(ExpenseRecord,expense_id) is None`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:88 已到达|exact assertion expression|
|77 `assert history.before_data['amount']==1234.56 and history.before_data['payroll_record_id']==2`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:90 已到达|exact assertion expression|
|78 `assert '因为撤销发放而冲销' in history.after_data['remark']`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:91 已到达|exact assertion expression|
|79 `assert ledger2.json()['total_expense']==0`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:92 已到达|exact assertion expression|
|80 `assert (await snapshot(factory))[2]==before_old`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:93 已到达|exact assertion expression|
|82 `assert reissue.status_code==200,reissue.text`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:97 已到达|exact assertion expression|
|83 `assert len(await rows(factory,ExpenseRecord))==1`|tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:79 已到达; tests/test_payroll_expense.py::test_disburse_reverse_reissue_and_reports[3] @ test_payroll_expense.py:98 已到达|exact assertion expression|

## 009 tests.test_payroll_expense::test_account_guards_no_writes[missing]

当前 `tests/test_payroll_expense.py::test_account_guards_no_writes[missing]`：**passed**；原失败调用行 103。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|101 `assert r.status_code==400,r.text`|tests/test_payroll_expense.py::test_account_guards_no_writes[missing] @ test_payroll_expense.py:118 已到达|exact assertion expression|
|102 `assert await snapshot(factory)==before and not await rows(factory,ExpenseRecord)`|tests/test_payroll_expense.py::test_account_guards_no_writes[missing] @ test_payroll_expense.py:119 已到达|exact assertion expression|

## 010 tests.test_payroll_expense::test_account_guards_no_writes[foreign]

当前 `tests/test_payroll_expense.py::test_account_guards_no_writes[foreign]`：**passed**；原失败调用行 103。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|101 `assert r.status_code==400,r.text`|tests/test_payroll_expense.py::test_account_guards_no_writes[foreign] @ test_payroll_expense.py:118 已到达|exact assertion expression|
|102 `assert await snapshot(factory)==before and not await rows(factory,ExpenseRecord)`|tests/test_payroll_expense.py::test_account_guards_no_writes[foreign] @ test_payroll_expense.py:119 已到达|exact assertion expression|

## 011 tests.test_payroll_expense::test_account_guards_no_writes[inactive]

当前 `tests/test_payroll_expense.py::test_account_guards_no_writes[inactive]`：**passed**；原失败调用行 103。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|101 `assert r.status_code==400,r.text`|tests/test_payroll_expense.py::test_account_guards_no_writes[inactive] @ test_payroll_expense.py:118 已到达|exact assertion expression|
|102 `assert await snapshot(factory)==before and not await rows(factory,ExpenseRecord)`|tests/test_payroll_expense.py::test_account_guards_no_writes[inactive] @ test_payroll_expense.py:119 已到达|exact assertion expression|

## 012 tests.test_payroll_expense::test_account_guards_no_writes[foreign_currency]

当前 `tests/test_payroll_expense.py::test_account_guards_no_writes[foreign_currency]`：**passed**；原失败调用行 103。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|101 `assert r.status_code==400,r.text`|tests/test_payroll_expense.py::test_account_guards_no_writes[foreign_currency] @ test_payroll_expense.py:118 已到达|exact assertion expression|
|102 `assert await snapshot(factory)==before and not await rows(factory,ExpenseRecord)`|tests/test_payroll_expense.py::test_account_guards_no_writes[foreign_currency] @ test_payroll_expense.py:119 已到达|exact assertion expression|

## 013 tests.test_payroll_expense::test_batch_one_expense_per_payroll_one_account_and_idempotence

当前 `tests/test_payroll_expense.py::test_batch_one_expense_per_payroll_one_account_and_idempotence`：**passed**；原失败调用行 124。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|113 `assert r.status_code==200,r.text`|tests/test_payroll_expense.py::test_batch_one_expense_per_payroll_one_account_and_idempotence @ test_payroll_expense.py:134 已到达|exact assertion expression|
|114 `assert r.json()['count']==2 and r.json()['total_net']==1334.57`|tests/test_payroll_expense.py::test_batch_one_expense_per_payroll_one_account_and_idempotence @ test_payroll_expense.py:135 已到达|exact assertion expression|
|117 `assert len(expenses)==2 and all(e.account_id==3 for e in expenses)`|tests/test_payroll_expense.py::test_batch_one_expense_per_payroll_one_account_and_idempotence @ test_payroll_expense.py:138 已到达|exact assertion expression|
|118 `assert Decimal(str(sum(e.amount for e in expenses)))==Decimal('1334.57')`|tests/test_payroll_expense.py::test_batch_one_expense_per_payroll_one_account_and_idempotence @ test_payroll_expense.py:139 已到达|exact assertion expression|
|119 `assert (await db.get(PayrollRecord,3)).expense_record_id is None`|tests/test_payroll_expense.py::test_batch_one_expense_per_payroll_one_account_and_idempotence @ test_payroll_expense.py:140 已到达|exact assertion expression|
|121 `assert again.status_code==200 and again.json()['count']==0 and len(await rows(factory,ExpenseRecord))==2`|tests/test_payroll_expense.py::test_batch_one_expense_per_payroll_one_account_and_idempotence @ test_payroll_expense.py:142 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|122 `assert cross.status_code==403`|tests/test_payroll_expense.py::test_batch_one_expense_per_payroll_one_account_and_idempotence @ test_payroll_expense.py:143 已到达|exact assertion expression|

## 014 tests.test_payroll_expense::test_failed_expense_rolls_back_whole_payment[False]

当前 `tests/test_payroll_expense.py::test_failed_expense_rolls_back_whole_payment[False]`：**passed**；原失败调用行 146。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|143 `assert r.status_code==500,r.text`|tests/test_payroll_expense.py::test_failed_expense_rolls_back_whole_payment[False] @ test_payroll_expense.py:166 已到达|exact assertion expression|
|144 `assert await snapshot(factory)==before`|tests/test_payroll_expense.py::test_failed_expense_rolls_back_whole_payment[False] @ test_payroll_expense.py:167 已到达|exact assertion expression|
|145 `assert not await rows(factory,ExpenseRecord) and not await rows(factory,DataChangeHistory)`|tests/test_payroll_expense.py::test_failed_expense_rolls_back_whole_payment[False] @ test_payroll_expense.py:168 已到达; tests/test_payroll_expense.py::test_failed_expense_rolls_back_whole_payment[False] @ test_payroll_expense.py:169 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|

## 015 tests.test_payroll_expense::test_failed_expense_rolls_back_whole_payment[True]

当前 `tests/test_payroll_expense.py::test_failed_expense_rolls_back_whole_payment[True]`：**passed**；原失败调用行 146。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|143 `assert r.status_code==500,r.text`|tests/test_payroll_expense.py::test_failed_expense_rolls_back_whole_payment[True] @ test_payroll_expense.py:166 已到达|exact assertion expression|
|144 `assert await snapshot(factory)==before`|tests/test_payroll_expense.py::test_failed_expense_rolls_back_whole_payment[True] @ test_payroll_expense.py:167 已到达|exact assertion expression|
|145 `assert not await rows(factory,ExpenseRecord) and not await rows(factory,DataChangeHistory)`|tests/test_payroll_expense.py::test_failed_expense_rolls_back_whole_payment[True] @ test_payroll_expense.py:168 已到达; tests/test_payroll_expense.py::test_failed_expense_rolls_back_whole_payment[True] @ test_payroll_expense.py:169 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|

## 016 tests.test_payroll_expense::test_failed_revocation_rolls_back_expense_and_payroll

当前 `tests/test_payroll_expense.py::test_failed_revocation_rolls_back_expense_and_payroll`：**passed**；原失败调用行 161。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|153 `assert r.status_code==200,r.text`|tests/test_payroll_expense.py::test_failed_revocation_rolls_back_expense_and_payroll @ test_payroll_expense.py:177 已到达|exact assertion expression|
|159 `assert r.status_code==500,r.text`|tests/test_payroll_expense.py::test_failed_revocation_rolls_back_expense_and_payroll @ test_payroll_expense.py:183 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|160 `assert await snapshot(factory)==before and await rows(factory,ExpenseRecord)==expenses and await rows(factory,DataChangeHistory)==history`|tests/test_payroll_expense.py::test_failed_revocation_rolls_back_expense_and_payroll @ test_payroll_expense.py:184 已到达|exact assertion expression|

## 017 tests.test_payroll_expense::test_exact_cent_amount_or_reject[0-200]

当前 `tests/test_payroll_expense.py::test_exact_cent_amount_or_reject[0-200]`：**passed**；原失败调用行 202。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|197 `assert r.status_code==expected,r.text`|tests/test_payroll_expense.py::test_exact_cent_amount_or_reject[0-200] @ test_payroll_expense.py:222 已到达|exact assertion expression|
|199 `assert await snapshot(factory)==before and not await rows(factory,ExpenseRecord)`|tests/test_payroll_expense.py::test_exact_cent_amount_or_reject[0-200] @ test_payroll_expense.py:224 未到达；对应分支已在 tests/test_payroll_expense.py::test_exact_cent_amount_or_reject[-1-400] @ 224, tests/test_payroll_expense.py::test_exact_cent_amount_or_reject[1234.567-400] @ 224 执行|exact assertion expression|
|201 `assert (await db.get(ExpenseRecord,r.json()['expense_record_id'])).amount==0`|tests/test_payroll_expense.py::test_exact_cent_amount_or_reject[0-200] @ test_payroll_expense.py:226 已到达|exact assertion expression|

## 018 tests.test_payroll_expense::test_exact_cent_amount_or_reject[-1-400]

当前 `tests/test_payroll_expense.py::test_exact_cent_amount_or_reject[-1-400]`：**passed**；原失败调用行 202。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|197 `assert r.status_code==expected,r.text`|tests/test_payroll_expense.py::test_exact_cent_amount_or_reject[-1-400] @ test_payroll_expense.py:222 已到达|exact assertion expression|
|199 `assert await snapshot(factory)==before and not await rows(factory,ExpenseRecord)`|tests/test_payroll_expense.py::test_exact_cent_amount_or_reject[-1-400] @ test_payroll_expense.py:224 已到达|exact assertion expression|
|201 `assert (await db.get(ExpenseRecord,r.json()['expense_record_id'])).amount==0`|tests/test_payroll_expense.py::test_exact_cent_amount_or_reject[-1-400] @ test_payroll_expense.py:226 未到达；对应分支已在 tests/test_payroll_expense.py::test_exact_cent_amount_or_reject[0-200] @ 226 执行|exact assertion expression|

## 019 tests.test_payroll_expense::test_exact_cent_amount_or_reject[1234.567-400]

当前 `tests/test_payroll_expense.py::test_exact_cent_amount_or_reject[1234.567-400]`：**passed**；原失败调用行 202。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|197 `assert r.status_code==expected,r.text`|tests/test_payroll_expense.py::test_exact_cent_amount_or_reject[1234.567-400] @ test_payroll_expense.py:222 已到达|exact assertion expression|
|199 `assert await snapshot(factory)==before and not await rows(factory,ExpenseRecord)`|tests/test_payroll_expense.py::test_exact_cent_amount_or_reject[1234.567-400] @ test_payroll_expense.py:224 已到达|exact assertion expression|
|201 `assert (await db.get(ExpenseRecord,r.json()['expense_record_id'])).amount==0`|tests/test_payroll_expense.py::test_exact_cent_amount_or_reject[1234.567-400] @ test_payroll_expense.py:226 未到达；对应分支已在 tests/test_payroll_expense.py::test_exact_cent_amount_or_reject[0-200] @ 226 执行|exact assertion expression|

## 020 tests.test_payroll_expense::test_missing_category_rejects_without_changing_payroll

当前 `tests/test_payroll_expense.py::test_missing_category_rejects_without_changing_payroll`：**passed**；原失败调用行 215。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|213 `assert r.status_code==400 and '启动迁移' in r.text`|tests/test_payroll_expense.py::test_missing_category_rejects_without_changing_payroll @ test_payroll_expense.py:239 已到达|exact assertion expression|
|214 `assert await snapshot(factory)==before and not await rows(factory,ExpenseRecord)`|tests/test_payroll_expense.py::test_missing_category_rejects_without_changing_payroll @ test_payroll_expense.py:240 已到达|exact assertion expression|

## 021 tests.test_payroll_cash_advance::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke

当前 `tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke`：**failed**；原失败调用行 124。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|74 `assert paid.status_code == 200, paid.text`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:75 已到达|exact assertion expression|
|76 `assert data["cash_advance_id"] == aid and data["account_id"] is None and data["net_pay"] == 7000`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:77 已到达|exact assertion expression|
|79 `assert (after_costs["count"], after_costs["amount"]) == (3, 7750)`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:82 已到达 / 行失败|exact assertion expression|
|81 `assert expense["category_name"] == "员工工资" and expense["amount"] == 7000 and expense["account_id"] is None`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:85 未到达|exact assertion expression|
|82 `assert expense["cash_advance_id"] == aid and expense["funding_source"] == "cash_advance"`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:86 未到达|exact assertion expression|
|83 `assert await balances(c) == before_balances == {1: 10000, 3: 20000}`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:87 已到达|exact assertion expression|
|84 `assert await ledger(c) == before_ledger`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:88 已到达|exact assertion expression|
|86 `assert used["advance"]["outstanding_amount"] == 10000 and used["advance"]["repaid_amount"] == 0`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:90 已到达|exact assertion expression|
|87 `assert used["payroll_usage"]["payroll_used_amount"] == 7000 and used["payroll_usage"]["payroll_available_amount"] == 3000`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:91 已到达|exact assertion expression|
|88 `assert [(x["payroll_record_id"], x["amount"]) for x in used["payroll_usage"]["data"]] == [(2, 7000)]`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:92 已到达|exact assertion expression|
|90 `assert next(x for x in loan_list if x["id"] == aid)["payroll_used_amount"] == 7000`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:94 已到达|exact assertion expression|
|92 `assert report.status_code == 200 and report.json()["total_expense_by_currency"] == {"THB": 7750}`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:97 已到达 / 行失败|exact assertion expression|
|95 `assert denied.status_code == 400 and "工资联动支出" in denied.text`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:102 未到达|exact assertion expression|
|97 `assert duplicate.status_code == 400`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:104 已到达|exact assertion expression|
|99 `assert revoked.status_code == 200, revoked.text`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ round3_flow_support.py:71 已到达; tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:106 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|100 `assert revoked.json()["reversed_cash_advance_id"] == aid`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:106 已到达|historical fixture dictionary replaces HTTP response wrapper|
|102 `assert after_revoke["payroll_usage"]["data"] == []`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:108 已到达|exact assertion expression|
|103 `assert after_revoke["payroll_usage"]["payroll_used_amount"] == 0`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:109 已到达|exact assertion expression|
|104 `assert after_revoke["payroll_usage"]["payroll_available_amount"] == 10000`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:110 已到达|exact assertion expression|
|105 `assert after_revoke["advance"]["outstanding_amount"] == 10000`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:111 已到达|exact assertion expression|
|106 `assert await costs(c) == before_costs and await ledger(c) == before_ledger and await balances(c) == before_balances`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:112 已到达|exact assertion expression|
|109 `assert r.status == "confirmed" and not r.disbursed and r.cash_advance_id is None and r.expense_record_id is None and r.net_pay == 7000`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:115 已到达|exact assertion expression|
|110 `assert await db.get(ExpenseRecord, expense_id) is None`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:116 已到达|changed assertion; see old/new expressions and policy rationale|
|114 `assert "payroll_use" in operations and "payroll_use_revoke" in operations`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:120 已到达|exact assertion expression|
|117 `assert before[name] == after[name], name`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:123 已到达|exact assertion expression|
|118 `assert [r for r in before["payroll_records"] if r[0] != 2] == [r for r in after["payroll_records"] if r[0] != 2]`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:124 已到达|exact assertion expression|

## 022 tests.test_payroll_cash_advance::test_company_account_deducts_once_and_revoke_restores_with_same_cost_and_flow

当前 `tests/test_payroll_cash_advance.py::test_company_account_deducts_once_and_revoke_restores_with_same_cost_and_flow`：**passed**；原失败调用行 151。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|133 `assert r.status_code == 200, r.text`|tests/test_payroll_cash_advance.py::test_company_account_deducts_once_and_revoke_restores_with_same_cost_and_flow @ test_payroll_cash_advance.py:139 已到达|exact assertion expression|
|134 `assert r.json()["funding_source"] == "company_account" and r.json()["cash_advance_id"] is None`|tests/test_payroll_cash_advance.py::test_company_account_deducts_once_and_revoke_restores_with_same_cost_and_flow @ test_payroll_cash_advance.py:140 已到达|exact assertion expression|
|135 `assert await balances(c) == {1: 3000, 3: 20000}`|tests/test_payroll_cash_advance.py::test_company_account_deducts_once_and_revoke_restores_with_same_cost_and_flow @ test_payroll_cash_advance.py:141 已到达|exact assertion expression|
|139 `assert changed_currency.status_code == 400 and "已发放工资" in changed_currency.text`|tests/test_payroll_cash_advance.py::test_company_account_deducts_once_and_revoke_restores_with_same_cost_and_flow @ test_payroll_cash_advance.py:145 已到达|changed assertion; see old/new expressions and policy rationale|
|140 `assert (await costs(c))["amount"] == 7750`|tests/test_payroll_cash_advance.py::test_company_account_deducts_once_and_revoke_restores_with_same_cost_and_flow @ test_payroll_cash_advance.py:146 已到达|exact assertion expression|
|142 `assert flow["total"] == before_ledger["total"] + 1 and flow["total_expense"] == before_ledger["total_expense"] + 7000`|tests/test_payroll_cash_advance.py::test_company_account_deducts_once_and_revoke_restores_with_same_cost_and_flow @ test_payroll_cash_advance.py:148 已到达|exact assertion expression|
|144 `assert again.status_code == 400 and (await balances(c))[1] == 3000`|tests/test_payroll_cash_advance.py::test_company_account_deducts_once_and_revoke_restores_with_same_cost_and_flow @ test_payroll_cash_advance.py:150 已到达|exact assertion expression|
|146 `assert revoke.status_code == 200 and await balances(c) == {1: 10000, 3: 20000}`|tests/test_payroll_cash_advance.py::test_company_account_deducts_once_and_revoke_restores_with_same_cost_and_flow @ test_payroll_cash_advance.py:152 已到达; tests/test_payroll_cash_advance.py::test_company_account_deducts_once_and_revoke_restores_with_same_cost_and_flow @ round3_flow_support.py:71 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|147 `assert (await costs(c))["amount"] == 750 and await ledger(c) == before_ledger`|tests/test_payroll_cash_advance.py::test_company_account_deducts_once_and_revoke_restores_with_same_cost_and_flow @ test_payroll_cash_advance.py:153 已到达|exact assertion expression|
|149 `assert (await db.get(PaymentAccount, 1)).opening_balance == 10000`|tests/test_payroll_cash_advance.py::test_company_account_deducts_once_and_revoke_restores_with_same_cost_and_flow @ test_payroll_cash_advance.py:155 已到达|changed assertion; see old/new expressions and policy rationale|

## 023 tests.test_payroll_cash_advance::test_invalid_funding_never_changes_any_money[insufficient]

当前 `tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[insufficient]`：**passed**；原失败调用行 175。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|169 `assert r.status_code == 400, r.text`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[insufficient] @ test_payroll_cash_advance.py:175 已到达|exact assertion expression|
|170 `assert r.json()["detail"] == "垫款单剩余金额不足"`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[insufficient] @ test_payroll_cash_advance.py:176 已到达|exact assertion expression|
|172 `assert "币种" in r.json()["detail"]`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[insufficient] @ test_payroll_cash_advance.py:178 未到达；对应分支已在 tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[currency] @ 178 执行|exact assertion expression|
|173 `assert (await usage(c, aid))["payroll_usage"]["payroll_available_amount"] == 0`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[insufficient] @ test_payroll_cash_advance.py:179 未到达；对应分支已在 tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[currency] @ 179 执行|exact assertion expression|
|174 `assert await finance_snapshot(f) == before and await balances(c) == {1: 10000, 3: 20000}`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[insufficient] @ test_payroll_cash_advance.py:180 已到达|exact assertion expression|

## 024 tests.test_payroll_cash_advance::test_invalid_funding_never_changes_any_money[pending]

当前 `tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[pending]`：**passed**；原失败调用行 175。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|169 `assert r.status_code == 400, r.text`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[pending] @ test_payroll_cash_advance.py:175 已到达|exact assertion expression|
|170 `assert r.json()["detail"] == "垫款单剩余金额不足"`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[pending] @ test_payroll_cash_advance.py:176 已到达|exact assertion expression|
|172 `assert "币种" in r.json()["detail"]`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[pending] @ test_payroll_cash_advance.py:178 未到达；对应分支已在 tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[currency] @ 178 执行|exact assertion expression|
|173 `assert (await usage(c, aid))["payroll_usage"]["payroll_available_amount"] == 0`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[pending] @ test_payroll_cash_advance.py:179 未到达；对应分支已在 tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[currency] @ 179 执行|exact assertion expression|
|174 `assert await finance_snapshot(f) == before and await balances(c) == {1: 10000, 3: 20000}`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[pending] @ test_payroll_cash_advance.py:180 已到达|exact assertion expression|

## 025 tests.test_payroll_cash_advance::test_invalid_funding_never_changes_any_money[rejected]

当前 `tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[rejected]`：**passed**；原失败调用行 175。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|169 `assert r.status_code == 400, r.text`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[rejected] @ test_payroll_cash_advance.py:175 已到达|exact assertion expression|
|170 `assert r.json()["detail"] == "垫款单剩余金额不足"`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[rejected] @ test_payroll_cash_advance.py:176 已到达|exact assertion expression|
|172 `assert "币种" in r.json()["detail"]`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[rejected] @ test_payroll_cash_advance.py:178 未到达；对应分支已在 tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[currency] @ 178 执行|exact assertion expression|
|173 `assert (await usage(c, aid))["payroll_usage"]["payroll_available_amount"] == 0`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[rejected] @ test_payroll_cash_advance.py:179 未到达；对应分支已在 tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[currency] @ 179 执行|exact assertion expression|
|174 `assert await finance_snapshot(f) == before and await balances(c) == {1: 10000, 3: 20000}`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[rejected] @ test_payroll_cash_advance.py:180 已到达|exact assertion expression|

## 026 tests.test_payroll_cash_advance::test_invalid_funding_never_changes_any_money[repaid]

当前 `tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[repaid]`：**passed**；原失败调用行 175。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|169 `assert r.status_code == 400, r.text`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[repaid] @ test_payroll_cash_advance.py:175 已到达|exact assertion expression|
|170 `assert r.json()["detail"] == "垫款单剩余金额不足"`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[repaid] @ test_payroll_cash_advance.py:176 已到达|exact assertion expression|
|172 `assert "币种" in r.json()["detail"]`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[repaid] @ test_payroll_cash_advance.py:178 未到达；对应分支已在 tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[currency] @ 178 执行|exact assertion expression|
|173 `assert (await usage(c, aid))["payroll_usage"]["payroll_available_amount"] == 0`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[repaid] @ test_payroll_cash_advance.py:179 未到达；对应分支已在 tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[currency] @ 179 执行|exact assertion expression|
|174 `assert await finance_snapshot(f) == before and await balances(c) == {1: 10000, 3: 20000}`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[repaid] @ test_payroll_cash_advance.py:180 已到达|exact assertion expression|

## 027 tests.test_payroll_cash_advance::test_invalid_funding_never_changes_any_money[currency]

当前 `tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[currency]`：**passed**；原失败调用行 175。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|169 `assert r.status_code == 400, r.text`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[currency] @ test_payroll_cash_advance.py:175 已到达|exact assertion expression|
|170 `assert r.json()["detail"] == "垫款单剩余金额不足"`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[currency] @ test_payroll_cash_advance.py:176 已到达|exact assertion expression|
|172 `assert "币种" in r.json()["detail"]`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[currency] @ test_payroll_cash_advance.py:178 已到达|exact assertion expression|
|173 `assert (await usage(c, aid))["payroll_usage"]["payroll_available_amount"] == 0`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[currency] @ test_payroll_cash_advance.py:179 已到达|exact assertion expression|
|174 `assert await finance_snapshot(f) == before and await balances(c) == {1: 10000, 3: 20000}`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[currency] @ test_payroll_cash_advance.py:180 已到达|exact assertion expression|

## 028 tests.test_payroll_cash_advance::test_invalid_funding_never_changes_any_money[foreign]

当前 `tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[foreign]`：**passed**；原失败调用行 175。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|169 `assert r.status_code == 400, r.text`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[foreign] @ test_payroll_cash_advance.py:175 已到达|exact assertion expression|
|170 `assert r.json()["detail"] == "垫款单剩余金额不足"`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[foreign] @ test_payroll_cash_advance.py:176 已到达|exact assertion expression|
|172 `assert "币种" in r.json()["detail"]`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[foreign] @ test_payroll_cash_advance.py:178 未到达；对应分支已在 tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[currency] @ 178 执行|exact assertion expression|
|173 `assert (await usage(c, aid))["payroll_usage"]["payroll_available_amount"] == 0`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[foreign] @ test_payroll_cash_advance.py:179 未到达；对应分支已在 tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[currency] @ 179 执行|exact assertion expression|
|174 `assert await finance_snapshot(f) == before and await balances(c) == {1: 10000, 3: 20000}`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[foreign] @ test_payroll_cash_advance.py:180 已到达|exact assertion expression|

## 029 tests.test_payroll_cash_advance::test_invalid_funding_never_changes_any_money[missing]

当前 `tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[missing]`：**passed**；原失败调用行 175。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|169 `assert r.status_code == 400, r.text`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[missing] @ test_payroll_cash_advance.py:175 已到达|exact assertion expression|
|170 `assert r.json()["detail"] == "垫款单剩余金额不足"`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[missing] @ test_payroll_cash_advance.py:176 已到达|exact assertion expression|
|172 `assert "币种" in r.json()["detail"]`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[missing] @ test_payroll_cash_advance.py:178 未到达；对应分支已在 tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[currency] @ 178 执行|exact assertion expression|
|173 `assert (await usage(c, aid))["payroll_usage"]["payroll_available_amount"] == 0`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[missing] @ test_payroll_cash_advance.py:179 未到达；对应分支已在 tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[currency] @ 179 执行|exact assertion expression|
|174 `assert await finance_snapshot(f) == before and await balances(c) == {1: 10000, 3: 20000}`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[missing] @ test_payroll_cash_advance.py:180 已到达|exact assertion expression|

## 030 tests.test_payroll_cash_advance::test_invalid_funding_never_changes_any_money[mixed]

当前 `tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[mixed]`：**passed**；原失败调用行 175。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|169 `assert r.status_code == 400, r.text`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[mixed] @ test_payroll_cash_advance.py:175 已到达|exact assertion expression|
|170 `assert r.json()["detail"] == "垫款单剩余金额不足"`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[mixed] @ test_payroll_cash_advance.py:176 已到达|exact assertion expression|
|172 `assert "币种" in r.json()["detail"]`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[mixed] @ test_payroll_cash_advance.py:178 未到达；对应分支已在 tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[currency] @ 178 执行|exact assertion expression|
|173 `assert (await usage(c, aid))["payroll_usage"]["payroll_available_amount"] == 0`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[mixed] @ test_payroll_cash_advance.py:179 未到达；对应分支已在 tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[currency] @ 179 执行|exact assertion expression|
|174 `assert await finance_snapshot(f) == before and await balances(c) == {1: 10000, 3: 20000}`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[mixed] @ test_payroll_cash_advance.py:180 已到达|exact assertion expression|

## 031 tests.test_payroll_cash_advance::test_invalid_funding_never_changes_any_money[company_mixed]

当前 `tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[company_mixed]`：**passed**；原失败调用行 175。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|169 `assert r.status_code == 400, r.text`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[company_mixed] @ test_payroll_cash_advance.py:175 已到达|exact assertion expression|
|170 `assert r.json()["detail"] == "垫款单剩余金额不足"`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[company_mixed] @ test_payroll_cash_advance.py:176 已到达|exact assertion expression|
|172 `assert "币种" in r.json()["detail"]`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[company_mixed] @ test_payroll_cash_advance.py:178 未到达；对应分支已在 tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[currency] @ 178 执行|exact assertion expression|
|173 `assert (await usage(c, aid))["payroll_usage"]["payroll_available_amount"] == 0`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[company_mixed] @ test_payroll_cash_advance.py:179 未到达；对应分支已在 tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[currency] @ 179 执行|exact assertion expression|
|174 `assert await finance_snapshot(f) == before and await balances(c) == {1: 10000, 3: 20000}`|tests/test_payroll_cash_advance.py::test_invalid_funding_never_changes_any_money[company_mixed] @ test_payroll_cash_advance.py:180 已到达|exact assertion expression|

## 032 tests.test_payroll_cash_advance::test_reuse_limit_batch_total_idempotence_and_revoke_releases_capacity

当前 `tests/test_payroll_cash_advance.py::test_reuse_limit_batch_total_idempotence_and_revoke_releases_capacity`：**passed**；原失败调用行 203。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|183 `assert (await disburse(c, aid)).status_code == 200`|tests/test_payroll_cash_advance.py::test_reuse_limit_batch_total_idempotence_and_revoke_releases_capacity @ test_payroll_cash_advance.py:188 已到达|exact assertion expression|
|189 `assert r.status_code == 400 and r.json()["detail"] == "垫款单剩余金额不足"`|tests/test_payroll_cash_advance.py::test_reuse_limit_batch_total_idempotence_and_revoke_releases_capacity @ test_payroll_cash_advance.py:195 已到达|exact assertion expression|
|195 `assert r.status_code == 200 and r.json()["count"] == 1 and r.json()["total_net"] == 3000`|tests/test_payroll_cash_advance.py::test_reuse_limit_batch_total_idempotence_and_revoke_releases_capacity @ test_payroll_cash_advance.py:204 已到达|exact assertion expression|
|196 `assert (await usage(c, aid))["payroll_usage"]["payroll_used_amount"] == 10000`|tests/test_payroll_cash_advance.py::test_reuse_limit_batch_total_idempotence_and_revoke_releases_capacity @ test_payroll_cash_advance.py:205 已到达|exact assertion expression|
|198 `assert retry.status_code == 200 and retry.json()["count"] == 0`|tests/test_payroll_cash_advance.py::test_reuse_limit_batch_total_idempotence_and_revoke_releases_capacity @ test_payroll_cash_advance.py:207 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|199 `assert (await usage(c, aid))["advance"]["outstanding_amount"] == 10000`|tests/test_payroll_cash_advance.py::test_reuse_limit_batch_total_idempotence_and_revoke_releases_capacity @ test_payroll_cash_advance.py:208 已到达|exact assertion expression|
|200 `assert await balances(c) == {1: 10000, 3: 20000}`|tests/test_payroll_cash_advance.py::test_reuse_limit_batch_total_idempotence_and_revoke_releases_capacity @ test_payroll_cash_advance.py:209 已到达|exact assertion expression|
|201 `assert (await c.post("/api/v1/payroll/1/revoke-disbursement", headers=auth(1))).status_code == 200`|tests/test_payroll_cash_advance.py::test_reuse_limit_batch_total_idempotence_and_revoke_releases_capacity @ round3_flow_support.py:71 已到达; tests/test_payroll_cash_advance.py::test_reuse_limit_batch_total_idempotence_and_revoke_releases_capacity @ test_payroll_cash_advance.py:211 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|202 `assert (await usage(c, aid))["payroll_usage"]["payroll_available_amount"] == 3000`|tests/test_payroll_cash_advance.py::test_reuse_limit_batch_total_idempotence_and_revoke_releases_capacity @ test_payroll_cash_advance.py:211 已到达|exact assertion expression|

## 033 tests.test_payroll_cash_advance::test_batch_aggregate_budget_and_atomic_rollback[False]

当前 `tests/test_payroll_cash_advance.py::test_batch_aggregate_budget_and_atomic_rollback[False]`：**passed**；原失败调用行 233。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|229 `assert r.status_code == (500 if fail else 400), r.text`|tests/test_payroll_cash_advance.py::test_batch_aggregate_budget_and_atomic_rollback[False] @ test_payroll_cash_advance.py:239 已到达|exact assertion expression|
|230 `assert await finance_snapshot(f) == before`|tests/test_payroll_cash_advance.py::test_batch_aggregate_budget_and_atomic_rollback[False] @ test_payroll_cash_advance.py:240 已到达|exact assertion expression|
|231 `assert (await usage(c, aid))["payroll_usage"]["payroll_used_amount"] == 0`|tests/test_payroll_cash_advance.py::test_batch_aggregate_budget_and_atomic_rollback[False] @ test_payroll_cash_advance.py:241 已到达|exact assertion expression|
|232 `assert await balances(c) == {1: 10000, 3: 20000}`|tests/test_payroll_cash_advance.py::test_batch_aggregate_budget_and_atomic_rollback[False] @ test_payroll_cash_advance.py:242 已到达|exact assertion expression|

## 034 tests.test_payroll_cash_advance::test_batch_aggregate_budget_and_atomic_rollback[True]

当前 `tests/test_payroll_cash_advance.py::test_batch_aggregate_budget_and_atomic_rollback[True]`：**passed**；原失败调用行 233。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|229 `assert r.status_code == (500 if fail else 400), r.text`|tests/test_payroll_cash_advance.py::test_batch_aggregate_budget_and_atomic_rollback[True] @ test_payroll_cash_advance.py:239 已到达|exact assertion expression|
|230 `assert await finance_snapshot(f) == before`|tests/test_payroll_cash_advance.py::test_batch_aggregate_budget_and_atomic_rollback[True] @ test_payroll_cash_advance.py:240 已到达|exact assertion expression|
|231 `assert (await usage(c, aid))["payroll_usage"]["payroll_used_amount"] == 0`|tests/test_payroll_cash_advance.py::test_batch_aggregate_budget_and_atomic_rollback[True] @ test_payroll_cash_advance.py:241 已到达|exact assertion expression|
|232 `assert await balances(c) == {1: 10000, 3: 20000}`|tests/test_payroll_cash_advance.py::test_batch_aggregate_budget_and_atomic_rollback[True] @ test_payroll_cash_advance.py:242 已到达|exact assertion expression|

## 035 tests.test_payroll_cash_advance::test_failed_revoke_restores_cost_usage_and_loan_link

当前 `tests/test_payroll_cash_advance.py::test_failed_revoke_restores_cost_usage_and_loan_link`：**passed**；原失败调用行 250。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|241 `assert (await disburse(c, aid)).status_code == 200`|tests/test_payroll_cash_advance.py::test_failed_revoke_restores_cost_usage_and_loan_link @ test_payroll_cash_advance.py:250 已到达|exact assertion expression|
|248 `assert r.status_code == 500 and await finance_snapshot(f) == before`|tests/test_payroll_cash_advance.py::test_failed_revoke_restores_cost_usage_and_loan_link @ test_payroll_cash_advance.py:257 已到达|changed assertion; see old/new expressions and policy rationale|
|249 `assert (await usage(c, aid))["payroll_usage"]["payroll_used_amount"] == 7000`|tests/test_payroll_cash_advance.py::test_failed_revoke_restores_cost_usage_and_loan_link @ test_payroll_cash_advance.py:258 已到达|exact assertion expression|

## 036 tests.test_payroll_cash_advance::test_supervisor_with_only_payroll_grant_and_cross_warehouse_rejected

当前 `tests/test_payroll_cash_advance.py::test_supervisor_with_only_payroll_grant_and_cross_warehouse_rejected`：**passed**；原失败调用行 267。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|259 `assert sources.status_code == 200 and [x["id"] for x in sources.json()["data"]] == [aid]`|tests/test_payroll_cash_advance.py::test_supervisor_with_only_payroll_grant_and_cross_warehouse_rejected @ test_payroll_cash_advance.py:268 已到达|exact assertion expression|
|261 `assert foreign.status_code == 404`|tests/test_payroll_cash_advance.py::test_supervisor_with_only_payroll_grant_and_cross_warehouse_rejected @ test_payroll_cash_advance.py:270 已到达|exact assertion expression|
|265 `assert mixed.status_code == 403`|tests/test_payroll_cash_advance.py::test_supervisor_with_only_payroll_grant_and_cross_warehouse_rejected @ test_payroll_cash_advance.py:274 已到达|exact assertion expression|
|266 `assert (await disburse(c, aid, uid=4)).status_code == 200`|tests/test_payroll_cash_advance.py::test_supervisor_with_only_payroll_grant_and_cross_warehouse_rejected @ test_payroll_cash_advance.py:275 已到达|changed assertion; see old/new expressions and policy rationale|

## 037 tests.test_payroll_cash_advance::test_old_disbursement_role_restrictions_preserved[2]

当前 `tests/test_payroll_cash_advance.py::test_old_disbursement_role_restrictions_preserved[2]`：**passed**；原失败调用行 279。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|276 `assert (await disburse(c, aid, uid=uid)).status_code == 403`|tests/test_payroll_cash_advance.py::test_old_disbursement_role_restrictions_preserved[2] @ test_payroll_cash_advance.py:285 已到达|exact assertion expression|
|277 `assert (await c.get("/api/v1/payroll/cash-advance-sources", headers=auth(uid))).status_code == 403`|tests/test_payroll_cash_advance.py::test_old_disbursement_role_restrictions_preserved[2] @ test_payroll_cash_advance.py:286 已到达|exact assertion expression|
|278 `assert await balances(c) == {1: 10000, 3: 20000}`|tests/test_payroll_cash_advance.py::test_old_disbursement_role_restrictions_preserved[2] @ test_payroll_cash_advance.py:287 已到达|exact assertion expression|

## 038 tests.test_payroll_cash_advance::test_old_disbursement_role_restrictions_preserved[3]

当前 `tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke`：**failed**；原失败调用行 279。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|276 `assert (await disburse(c, aid, uid=uid)).status_code == 403`|tests/test_payroll_cash_advance.py::test_supervisor_with_only_payroll_grant_and_cross_warehouse_rejected @ test_payroll_cash_advance.py:275 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|277 `assert (await c.get("/api/v1/payroll/cash-advance-sources", headers=auth(uid))).status_code == 403`|tests/test_payroll_cash_advance.py::test_supervisor_with_only_payroll_grant_and_cross_warehouse_rejected @ test_payroll_cash_advance.py:268 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|278 `assert await balances(c) == {1: 10000, 3: 20000}`|tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:87 已到达; tests/test_payroll_cash_advance.py::test_cost_7000_company_accounts_and_ledger_unchanged_then_revoke @ test_payroll_cash_advance.py:112 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|

## 039 tests.test_payroll_cash_advance::test_old_disbursement_role_restrictions_preserved[5]

当前 `tests/test_payroll_cash_advance.py::test_old_disbursement_role_restrictions_preserved[5]`：**passed**；原失败调用行 279。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|276 `assert (await disburse(c, aid, uid=uid)).status_code == 403`|tests/test_payroll_cash_advance.py::test_old_disbursement_role_restrictions_preserved[5] @ test_payroll_cash_advance.py:285 已到达|exact assertion expression|
|277 `assert (await c.get("/api/v1/payroll/cash-advance-sources", headers=auth(uid))).status_code == 403`|tests/test_payroll_cash_advance.py::test_old_disbursement_role_restrictions_preserved[5] @ test_payroll_cash_advance.py:286 已到达|exact assertion expression|
|278 `assert await balances(c) == {1: 10000, 3: 20000}`|tests/test_payroll_cash_advance.py::test_old_disbursement_role_restrictions_preserved[5] @ test_payroll_cash_advance.py:287 已到达|exact assertion expression|

## 040 tests.test_payroll_cash_advance::test_repay_after_salary_changes_debt_and_funds_but_never_salary_cost

当前 `tests/test_payroll_cash_advance.py::test_repay_after_salary_changes_debt_and_funds_but_never_salary_cost`：**passed**；原失败调用行 296。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|286 `assert (await disburse(c, aid)).status_code == 200`|tests/test_payroll_cash_advance.py::test_repay_after_salary_changes_debt_and_funds_but_never_salary_cost @ test_payroll_cash_advance.py:295 已到达|exact assertion expression|
|289 `assert paid.status_code == 200, paid.text`|tests/test_payroll_cash_advance.py::test_repay_after_salary_changes_debt_and_funds_but_never_salary_cost @ test_payroll_cash_advance.py:298 已到达|exact assertion expression|
|290 `assert paid.json()["advance"]["outstanding_amount"] == 3000`|tests/test_payroll_cash_advance.py::test_repay_after_salary_changes_debt_and_funds_but_never_salary_cost @ test_payroll_cash_advance.py:299 已到达|exact assertion expression|
|291 `assert (await costs(c))["amount"] == 7750`|tests/test_payroll_cash_advance.py::test_repay_after_salary_changes_debt_and_funds_but_never_salary_cost @ test_payroll_cash_advance.py:300 已到达|exact assertion expression|
|292 `assert await balances(c) == {1: 3000, 3: 20000}`|tests/test_payroll_cash_advance.py::test_repay_after_salary_changes_debt_and_funds_but_never_salary_cost @ test_payroll_cash_advance.py:301 已到达|exact assertion expression|
|293 `assert (await ledger(c))["total_expense"] == 7750`|tests/test_payroll_cash_advance.py::test_repay_after_salary_changes_debt_and_funds_but_never_salary_cost @ test_payroll_cash_advance.py:302 已到达|exact assertion expression|
|294 `assert (await usage(c, aid))["payroll_usage"]["payroll_used_amount"] == 7000`|tests/test_payroll_cash_advance.py::test_repay_after_salary_changes_debt_and_funds_but_never_salary_cost @ test_payroll_cash_advance.py:303 已到达|exact assertion expression|
|295 `assert (await usage(c, aid))["payroll_usage"]["payroll_available_amount"] == 3000`|tests/test_payroll_cash_advance.py::test_repay_after_salary_changes_debt_and_funds_but_never_salary_cost @ test_payroll_cash_advance.py:304 已到达|exact assertion expression|

## 041 tests.test_reimbursement_payments::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow

当前 `tests/test_reimbursement_payments.py::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow`：**failed**；原失败调用行 152。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|112 `assert paid.status_code == 200, paid.text`|tests/test_reimbursement_payments.py::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow @ test_reimbursement_payments.py:121 已到达|exact assertion expression|
|114 `assert data["status"] == "paid" and data["account_balance"] == 8000`|tests/test_reimbursement_payments.py::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow @ test_reimbursement_payments.py:123 已到达|exact assertion expression|
|115 `assert data["payment"]["paid_by_id"] == 1 and data["payment"]["payment_voucher_path"] == photo`|tests/test_reimbursement_payments.py::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow @ test_reimbursement_payments.py:124 已到达|changed assertion; see old/new expressions and policy rationale|
|118 `assert (cost["count"], cost["amount"]) == (3, 2750)`|tests/test_reimbursement_payments.py::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow @ test_reimbursement_payments.py:128 已到达 / 行失败|exact assertion expression|
|120 `assert expense["category_name"] == "报销" and expense["amount"] == 2000 and expense["reimbursement_id"] == rid`|tests/test_reimbursement_payments.py::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow @ test_reimbursement_payments.py:130 已到达|exact assertion expression|
|121 `assert await balances(c) == {**before, 1: 8000}`|tests/test_reimbursement_payments.py::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow @ test_reimbursement_payments.py:131 已到达|exact assertion expression|
|123 `assert flows["total"] == old_flows["total"] + 1 and flows["total_expense"] == old_flows["total_expense"] + 2000`|tests/test_reimbursement_payments.py::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow @ test_reimbursement_payments.py:133 已到达|exact assertion expression|
|125 `assert len(linked) == 1 and linked[0]["remark"] == f"报销付款 #{rid}" and linked[0]["amount"] == 2000`|tests/test_reimbursement_payments.py::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow @ test_reimbursement_payments.py:135 已到达|exact assertion expression|
|127 `assert duplicate.status_code == 400 and (await costs(c))["count"] == 3 and (await balances(c))[1] == 8000`|tests/test_reimbursement_payments.py::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow @ test_reimbursement_payments.py:138 已到达 / 行失败|exact assertion expression|
|128 `assert (await c.post(f"{BASE}/{rid}/submit", headers=auth(1))).status_code == 400`|tests/test_reimbursement_payments.py::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow @ test_reimbursement_payments.py:139 已到达|exact assertion expression|
|129 `assert (await c.delete(f"/api/v1/income-expense/expense/{expense_id}", headers=auth(1))).status_code == 400`|tests/test_reimbursement_payments.py::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow @ test_reimbursement_payments.py:140 已到达|exact assertion expression|
|131 `assert report.status_code == 200 and report.json()["total_expense_by_currency"] == {"THB": 2750}`|tests/test_reimbursement_payments.py::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow @ test_reimbursement_payments.py:143 已到达 / 行失败|exact assertion expression|
|133 `assert detail["expense_record_id"] == expense_id and detail["paid_by_id"] == 1 and detail["payment_account_id"] == 1`|tests/test_reimbursement_payments.py::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow @ test_reimbursement_payments.py:145 已到达|changed assertion; see old/new expressions and policy rationale|
|135 `assert revoked.status_code == 200, revoked.text`|tests/test_reimbursement_payments.py::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow @ round3_flow_support.py:71 已到达; tests/test_reimbursement_payments.py::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow @ test_reimbursement_payments.py:147 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|136 `assert revoked.json()["status"] == "approved" and revoked.json()["expense_record_id"] is None and revoked.json()["account_balance"] == 10000`|tests/test_reimbursement_payments.py::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow @ test_reimbursement_payments.py:147 已到达|historical fixture dictionary replaces HTTP response wrapper|
|137 `assert (await costs(c))["amount"] == 750 and await balances(c) == before`|tests/test_reimbursement_payments.py::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow @ test_reimbursement_payments.py:149 已到达 / 行失败|exact assertion expression|
|139 `assert canceled["total"] == old_flows["total"] + 1 and canceled["total_expense"] == old_flows["total_expense"]`|tests/test_reimbursement_payments.py::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow @ test_reimbursement_payments.py:151 已到达|exact assertion expression|
|141 `assert row["status_label"] == "已冲销" and "付款账户选错" in row["remark"]`|tests/test_reimbursement_payments.py::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow @ test_reimbursement_payments.py:153 已到达|exact assertion expression|
|143 `assert hist["total"] == 1 and hist["data"][0]["status"] == "revoked" and hist["data"][0]["revoked_by_id"] == 1`|tests/test_reimbursement_payments.py::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow @ test_reimbursement_payments.py:155 已到达|exact assertion expression|
|144 `assert (await c.post(f"{BASE}/{rid}/revoke-payment", headers=auth(1), json={"reason": "重复"})).status_code == 400`|tests/test_reimbursement_payments.py::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow @ test_reimbursement_payments.py:156 已到达|exact assertion expression|
|147 `assert after_other[name] == old_other[name], name`|tests/test_reimbursement_payments.py::test_company_payment_2000_exactly_one_cost_and_one_flow_revoke_keeps_voided_flow @ test_reimbursement_payments.py:159 已到达|exact assertion expression|

## 042 tests.test_reimbursement_payments::test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost

当前 `tests/test_reimbursement_payments.py::test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost`：**failed**；原失败调用行 194。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|164 `assert paid.status_code == 200, paid.text`|tests/test_reimbursement_payments.py::test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost @ test_reimbursement_payments.py:178 已到达|exact assertion expression|
|166 `assert data["cash_advance_id"] == aid and data["payment"]["payment_account_id"] is None`|tests/test_reimbursement_payments.py::test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost @ test_reimbursement_payments.py:180 已到达|exact assertion expression|
|167 `assert (await costs(c))["amount"] == 2750 and (await costs(c))["count"] == 3`|tests/test_reimbursement_payments.py::test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost @ test_reimbursement_payments.py:182 已到达 / 行失败|exact assertion expression|
|168 `assert await balances(c) == before and await ledger(c) == flows_before`|tests/test_reimbursement_payments.py::test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost @ test_reimbursement_payments.py:183 已到达|exact assertion expression|
|170 `assert used["advance"]["outstanding_amount"] == 10000`|tests/test_reimbursement_payments.py::test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost @ test_reimbursement_payments.py:185 已到达|exact assertion expression|
|171 `assert used["reimbursement_usage"]["reimbursement_used_amount"] == 2000`|tests/test_reimbursement_payments.py::test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost @ test_reimbursement_payments.py:186 已到达|exact assertion expression|
|172 `assert used["payroll_usage"]["available_amount"] == 8000`|tests/test_reimbursement_payments.py::test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost @ test_reimbursement_payments.py:187 已到达|exact assertion expression|
|173 `assert used["reimbursement_usage"]["data"][0]["reimbursement_id"] == rid`|tests/test_reimbursement_payments.py::test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost @ test_reimbursement_payments.py:188 已到达|exact assertion expression|
|179 `assert rejected.status_code == 400 and rejected.json()["detail"] == "垫款单剩余金额不足"`|tests/test_reimbursement_payments.py::test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost @ test_reimbursement_payments.py:195 已到达|exact assertion expression|
|181 `assert revoked.status_code == 200 and revoked.json()["cash_advance_id"] is None`|tests/test_reimbursement_payments.py::test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost @ round3_flow_support.py:71 已到达; tests/test_reimbursement_payments.py::test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost @ test_reimbursement_payments.py:197 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|182 `assert (await costs(c))["amount"] == 750 and await balances(c) == before and await ledger(c) == flows_before`|tests/test_reimbursement_payments.py::test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost @ test_reimbursement_payments.py:199 已到达 / 行失败|exact assertion expression|
|183 `assert (await usage(c, aid))["reimbursement_usage"]["data"] == []`|tests/test_reimbursement_payments.py::test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost @ test_reimbursement_payments.py:200 已到达|exact assertion expression|
|185 `assert again.status_code == 200 and (await costs(c))["amount"] == 2750`|tests/test_reimbursement_payments.py::test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost @ test_reimbursement_payments.py:203 已到达 / 行失败|exact assertion expression|
|188 `assert returned.status_code == 200 and (await costs(c))["amount"] == 2750`|tests/test_reimbursement_payments.py::test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost @ test_reimbursement_payments.py:207 已到达 / 行失败|exact assertion expression|
|189 `assert (await balances(c))[1] == 8000`|tests/test_reimbursement_payments.py::test_cash_advance_cost_only_usage_revoke_and_repay_do_not_duplicate_cost @ test_reimbursement_payments.py:208 已到达|exact assertion expression|

## 043 tests.test_reimbursement_payments::test_validation_no_partial_money_changes[no_voucher]

当前 `tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[no_voucher]`：**passed**；原失败调用行 250。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|246 `assert r.status_code == 400, r.text`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[no_voucher] @ test_reimbursement_payments.py:266 已到达|exact assertion expression|
|247 `assert r.json()["detail"] == "请上传付款凭证"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[no_voucher] @ test_reimbursement_payments.py:267 已到达|exact assertion expression|
|248 `assert r.json()["detail"] == "垫款单剩余金额不足"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[no_voucher] @ test_reimbursement_payments.py:268 已到达|exact assertion expression|
|249 `assert await snapshot(f) == before`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[no_voucher] @ test_reimbursement_payments.py:269 已到达|exact assertion expression|

## 044 tests.test_reimbursement_payments::test_validation_no_partial_money_changes[bad_voucher]

当前 `tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[bad_voucher]`：**passed**；原失败调用行 250。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|246 `assert r.status_code == 400, r.text`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[bad_voucher] @ test_reimbursement_payments.py:266 已到达|exact assertion expression|
|247 `assert r.json()["detail"] == "请上传付款凭证"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[bad_voucher] @ test_reimbursement_payments.py:267 已到达|exact assertion expression|
|248 `assert r.json()["detail"] == "垫款单剩余金额不足"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[bad_voucher] @ test_reimbursement_payments.py:268 已到达|exact assertion expression|
|249 `assert await snapshot(f) == before`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[bad_voucher] @ test_reimbursement_payments.py:269 已到达|exact assertion expression|

## 045 tests.test_reimbursement_payments::test_validation_no_partial_money_changes[no_account]

当前 `tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[no_account]`：**passed**；原失败调用行 250。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|246 `assert r.status_code == 400, r.text`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[no_account] @ test_reimbursement_payments.py:266 已到达|exact assertion expression|
|247 `assert r.json()["detail"] == "请上传付款凭证"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[no_account] @ test_reimbursement_payments.py:267 已到达|exact assertion expression|
|248 `assert r.json()["detail"] == "垫款单剩余金额不足"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[no_account] @ test_reimbursement_payments.py:268 已到达|exact assertion expression|
|249 `assert await snapshot(f) == before`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[no_account] @ test_reimbursement_payments.py:269 已到达|exact assertion expression|

## 046 tests.test_reimbursement_payments::test_validation_no_partial_money_changes[foreign_account]

当前 `tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[foreign_account]`：**passed**；原失败调用行 250。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|246 `assert r.status_code == 400, r.text`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[foreign_account] @ test_reimbursement_payments.py:266 已到达|exact assertion expression|
|247 `assert r.json()["detail"] == "请上传付款凭证"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[foreign_account] @ test_reimbursement_payments.py:267 已到达|exact assertion expression|
|248 `assert r.json()["detail"] == "垫款单剩余金额不足"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[foreign_account] @ test_reimbursement_payments.py:268 已到达|exact assertion expression|
|249 `assert await snapshot(f) == before`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[foreign_account] @ test_reimbursement_payments.py:269 已到达|exact assertion expression|

## 047 tests.test_reimbursement_payments::test_validation_no_partial_money_changes[inactive_account]

当前 `tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[inactive_account]`：**passed**；原失败调用行 250。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|246 `assert r.status_code == 400, r.text`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[inactive_account] @ test_reimbursement_payments.py:266 已到达|exact assertion expression|
|247 `assert r.json()["detail"] == "请上传付款凭证"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[inactive_account] @ test_reimbursement_payments.py:267 已到达|exact assertion expression|
|248 `assert r.json()["detail"] == "垫款单剩余金额不足"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[inactive_account] @ test_reimbursement_payments.py:268 已到达|exact assertion expression|
|249 `assert await snapshot(f) == before`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[inactive_account] @ test_reimbursement_payments.py:269 已到达|exact assertion expression|

## 048 tests.test_reimbursement_payments::test_validation_no_partial_money_changes[currency]

当前 `tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[currency]`：**passed**；原失败调用行 250。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|246 `assert r.status_code == 400, r.text`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[currency] @ test_reimbursement_payments.py:266 已到达|exact assertion expression|
|247 `assert r.json()["detail"] == "请上传付款凭证"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[currency] @ test_reimbursement_payments.py:267 已到达|exact assertion expression|
|248 `assert r.json()["detail"] == "垫款单剩余金额不足"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[currency] @ test_reimbursement_payments.py:268 已到达|exact assertion expression|
|249 `assert await snapshot(f) == before`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[currency] @ test_reimbursement_payments.py:269 已到达|exact assertion expression|

## 049 tests.test_reimbursement_payments::test_validation_no_partial_money_changes[no_advance]

当前 `tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[no_advance]`：**passed**；原失败调用行 250。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|246 `assert r.status_code == 400, r.text`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[no_advance] @ test_reimbursement_payments.py:266 已到达|exact assertion expression|
|247 `assert r.json()["detail"] == "请上传付款凭证"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[no_advance] @ test_reimbursement_payments.py:267 已到达|exact assertion expression|
|248 `assert r.json()["detail"] == "垫款单剩余金额不足"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[no_advance] @ test_reimbursement_payments.py:268 已到达|exact assertion expression|
|249 `assert await snapshot(f) == before`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[no_advance] @ test_reimbursement_payments.py:269 已到达|exact assertion expression|

## 050 tests.test_reimbursement_payments::test_validation_no_partial_money_changes[small_advance]

当前 `tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[small_advance]`：**passed**；原失败调用行 250。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|246 `assert r.status_code == 400, r.text`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[small_advance] @ test_reimbursement_payments.py:266 已到达|exact assertion expression|
|247 `assert r.json()["detail"] == "请上传付款凭证"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[small_advance] @ test_reimbursement_payments.py:267 已到达|exact assertion expression|
|248 `assert r.json()["detail"] == "垫款单剩余金额不足"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[small_advance] @ test_reimbursement_payments.py:268 已到达|exact assertion expression|
|249 `assert await snapshot(f) == before`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[small_advance] @ test_reimbursement_payments.py:269 已到达|exact assertion expression|

## 051 tests.test_reimbursement_payments::test_validation_no_partial_money_changes[foreign_advance]

当前 `tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[foreign_advance]`：**passed**；原失败调用行 250。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|246 `assert r.status_code == 400, r.text`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[foreign_advance] @ test_reimbursement_payments.py:266 已到达|exact assertion expression|
|247 `assert r.json()["detail"] == "请上传付款凭证"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[foreign_advance] @ test_reimbursement_payments.py:267 已到达|exact assertion expression|
|248 `assert r.json()["detail"] == "垫款单剩余金额不足"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[foreign_advance] @ test_reimbursement_payments.py:268 已到达|exact assertion expression|
|249 `assert await snapshot(f) == before`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[foreign_advance] @ test_reimbursement_payments.py:269 已到达|exact assertion expression|

## 052 tests.test_reimbursement_payments::test_validation_no_partial_money_changes[advance_currency]

当前 `tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[advance_currency]`：**passed**；原失败调用行 250。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|246 `assert r.status_code == 400, r.text`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[advance_currency] @ test_reimbursement_payments.py:266 已到达|exact assertion expression|
|247 `assert r.json()["detail"] == "请上传付款凭证"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[advance_currency] @ test_reimbursement_payments.py:267 已到达|exact assertion expression|
|248 `assert r.json()["detail"] == "垫款单剩余金额不足"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[advance_currency] @ test_reimbursement_payments.py:268 已到达|exact assertion expression|
|249 `assert await snapshot(f) == before`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[advance_currency] @ test_reimbursement_payments.py:269 已到达|exact assertion expression|

## 053 tests.test_reimbursement_payments::test_validation_no_partial_money_changes[pending_advance]

当前 `tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[pending_advance]`：**passed**；原失败调用行 250。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|246 `assert r.status_code == 400, r.text`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[pending_advance] @ test_reimbursement_payments.py:266 已到达|exact assertion expression|
|247 `assert r.json()["detail"] == "请上传付款凭证"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[pending_advance] @ test_reimbursement_payments.py:267 已到达|exact assertion expression|
|248 `assert r.json()["detail"] == "垫款单剩余金额不足"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[pending_advance] @ test_reimbursement_payments.py:268 已到达|exact assertion expression|
|249 `assert await snapshot(f) == before`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[pending_advance] @ test_reimbursement_payments.py:269 已到达|exact assertion expression|

## 054 tests.test_reimbursement_payments::test_validation_no_partial_money_changes[mixed]

当前 `tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[mixed]`：**passed**；原失败调用行 250。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|246 `assert r.status_code == 400, r.text`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[mixed] @ test_reimbursement_payments.py:266 已到达|exact assertion expression|
|247 `assert r.json()["detail"] == "请上传付款凭证"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[mixed] @ test_reimbursement_payments.py:267 已到达|exact assertion expression|
|248 `assert r.json()["detail"] == "垫款单剩余金额不足"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[mixed] @ test_reimbursement_payments.py:268 已到达|exact assertion expression|
|249 `assert await snapshot(f) == before`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[mixed] @ test_reimbursement_payments.py:269 已到达|exact assertion expression|

## 055 tests.test_reimbursement_payments::test_validation_no_partial_money_changes[not_linked_fund]

当前 `tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[not_linked_fund]`：**passed**；原失败调用行 250。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|246 `assert r.status_code == 400, r.text`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[not_linked_fund] @ test_reimbursement_payments.py:266 已到达|exact assertion expression|
|247 `assert r.json()["detail"] == "请上传付款凭证"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[not_linked_fund] @ test_reimbursement_payments.py:267 已到达|exact assertion expression|
|248 `assert r.json()["detail"] == "垫款单剩余金额不足"`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[not_linked_fund] @ test_reimbursement_payments.py:268 已到达|exact assertion expression|
|249 `assert await snapshot(f) == before`|tests/test_reimbursement_payments.py::test_validation_no_partial_money_changes[not_linked_fund] @ test_reimbursement_payments.py:269 已到达|exact assertion expression|

## 056 tests.test_reimbursement_payments::test_payment_and_revoke_failures_rollback_everything[company_account]

当前 `tests/test_reimbursement_payments.py::test_payment_and_revoke_failures_rollback_everything[company_account]`：**passed**；原失败调用行 278。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|270 `assert (await pay(c, rid, path, **fields)).status_code == 500`|tests/test_reimbursement_payments.py::test_payment_and_revoke_failures_rollback_everything[company_account] @ test_reimbursement_payments.py:289 已到达|exact assertion expression|
|271 `assert await snapshot(f) == before`|tests/test_reimbursement_payments.py::test_payment_and_revoke_failures_rollback_everything[company_account] @ test_reimbursement_payments.py:290 已到达|exact assertion expression|
|273 `assert (await pay(c, rid, path, **fields)).status_code == 200`|tests/test_reimbursement_payments.py::test_payment_and_revoke_failures_rollback_everything[company_account] @ test_reimbursement_payments.py:292 已到达|exact assertion expression|
|277 `assert r.status_code == 500 and await snapshot(f) == before`|tests/test_reimbursement_payments.py::test_payment_and_revoke_failures_rollback_everything[company_account] @ test_reimbursement_payments.py:296 已到达|changed assertion; see old/new expressions and policy rationale|

## 057 tests.test_reimbursement_payments::test_payment_and_revoke_failures_rollback_everything[cash_advance]

当前 `tests/test_reimbursement_payments.py::test_payment_and_revoke_failures_rollback_everything[cash_advance]`：**passed**；原失败调用行 278。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|270 `assert (await pay(c, rid, path, **fields)).status_code == 500`|tests/test_reimbursement_payments.py::test_payment_and_revoke_failures_rollback_everything[cash_advance] @ test_reimbursement_payments.py:289 已到达|exact assertion expression|
|271 `assert await snapshot(f) == before`|tests/test_reimbursement_payments.py::test_payment_and_revoke_failures_rollback_everything[cash_advance] @ test_reimbursement_payments.py:290 已到达|exact assertion expression|
|273 `assert (await pay(c, rid, path, **fields)).status_code == 200`|tests/test_reimbursement_payments.py::test_payment_and_revoke_failures_rollback_everything[cash_advance] @ test_reimbursement_payments.py:292 已到达|exact assertion expression|
|277 `assert r.status_code == 500 and await snapshot(f) == before`|tests/test_reimbursement_payments.py::test_payment_and_revoke_failures_rollback_everything[cash_advance] @ test_reimbursement_payments.py:296 已到达|changed assertion; see old/new expressions and policy rationale|

## 058 tests.test_reimbursement_payments::test_only_warehouse_admin_can_revoke[3]

当前 `tests/test_reimbursement_payments.py::test_only_warehouse_admin_can_revoke[3]`：**passed**；原失败调用行 294。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|288 `assert (await pay(c, rid, path)).status_code == 200`|tests/test_reimbursement_payments.py::test_only_warehouse_admin_can_revoke[3] @ test_reimbursement_payments.py:306 已到达|exact assertion expression|
|292 `assert r.status_code == 403 and await snapshot(f) == before`|tests/test_reimbursement_payments.py::test_only_warehouse_admin_can_revoke[3] @ test_reimbursement_payments.py:310 已到达|changed assertion; see old/new expressions and policy rationale|
|293 `assert r.json()["detail"] == "只有仓库管理员可以撤销报销付款"`|tests/test_reimbursement_payments.py::test_only_warehouse_admin_can_revoke[3] @ test_reimbursement_payments.py:311 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|

## 059 tests.test_reimbursement_payments::test_only_warehouse_admin_can_revoke[4]

当前 `tests/test_reimbursement_payments.py::test_only_warehouse_admin_can_revoke[4]`：**passed**；原失败调用行 294。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|288 `assert (await pay(c, rid, path)).status_code == 200`|tests/test_reimbursement_payments.py::test_only_warehouse_admin_can_revoke[4] @ test_reimbursement_payments.py:306 已到达|exact assertion expression|
|292 `assert r.status_code == 403 and await snapshot(f) == before`|tests/test_reimbursement_payments.py::test_only_warehouse_admin_can_revoke[4] @ test_reimbursement_payments.py:310 已到达|changed assertion; see old/new expressions and policy rationale|
|293 `assert r.json()["detail"] == "只有仓库管理员可以撤销报销付款"`|tests/test_reimbursement_payments.py::test_only_warehouse_admin_can_revoke[4] @ test_reimbursement_payments.py:311 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|

## 060 tests.test_reimbursement_payments::test_only_warehouse_admin_can_revoke[5]

当前 `tests/test_reimbursement_payments.py::test_only_warehouse_admin_can_revoke[5]`：**passed**；原失败调用行 294。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|288 `assert (await pay(c, rid, path)).status_code == 200`|tests/test_reimbursement_payments.py::test_only_warehouse_admin_can_revoke[5] @ test_reimbursement_payments.py:306 已到达|exact assertion expression|
|292 `assert r.status_code == 403 and await snapshot(f) == before`|tests/test_reimbursement_payments.py::test_only_warehouse_admin_can_revoke[5] @ test_reimbursement_payments.py:310 已到达|changed assertion; see old/new expressions and policy rationale|
|293 `assert r.json()["detail"] == "只有仓库管理员可以撤销报销付款"`|tests/test_reimbursement_payments.py::test_only_warehouse_admin_can_revoke[5] @ test_reimbursement_payments.py:311 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|

## 061 tests.test_reimbursement_payments::test_only_warehouse_admin_can_revoke[2]

当前 `tests/test_reimbursement_payments.py::test_only_warehouse_admin_can_revoke[2]`：**passed**；原失败调用行 294。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|288 `assert (await pay(c, rid, path)).status_code == 200`|tests/test_reimbursement_payments.py::test_only_warehouse_admin_can_revoke[2] @ test_reimbursement_payments.py:306 已到达|exact assertion expression|
|292 `assert r.status_code == 403 and await snapshot(f) == before`|tests/test_reimbursement_payments.py::test_only_warehouse_admin_can_revoke[2] @ test_reimbursement_payments.py:310 已到达|changed assertion; see old/new expressions and policy rationale|
|293 `assert r.json()["detail"] == "只有仓库管理员可以撤销报销付款"`|tests/test_reimbursement_payments.py::test_only_warehouse_admin_can_revoke[2] @ test_reimbursement_payments.py:311 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|

## 062 tests.test_reimbursement_payments::test_cny_account_and_advance_are_independent_from_thb

当前 `tests/test_reimbursement_payments.py::test_cny_account_and_advance_are_independent_from_thb`：**passed**；原失败调用行 314。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|303 `assert [a["id"] for a in sources["accounts"]] == [4]`|tests/test_reimbursement_payments.py::test_cny_account_and_advance_are_independent_from_thb @ test_reimbursement_payments.py:321 已到达|exact assertion expression|
|305 `assert r.status_code == 200 and r.json()["account_balance"] == 28000`|tests/test_reimbursement_payments.py::test_cny_account_and_advance_are_independent_from_thb @ test_reimbursement_payments.py:323 已到达|exact assertion expression|
|306 `assert (await balances(c))[1] == 10000`|tests/test_reimbursement_payments.py::test_cny_account_and_advance_are_independent_from_thb @ test_reimbursement_payments.py:324 已到达|exact assertion expression|
|312 `assert r.status_code == 200 and await balances(c) == before`|tests/test_reimbursement_payments.py::test_cny_account_and_advance_are_independent_from_thb @ test_reimbursement_payments.py:330 已到达|exact assertion expression|
|313 `assert (await usage(c, aid))["reimbursement_usage"]["reimbursement_used_amount"] == 2000`|tests/test_reimbursement_payments.py::test_cny_account_and_advance_are_independent_from_thb @ test_reimbursement_payments.py:331 已到达|exact assertion expression|

## 063 tests.test_reimbursement_payments::test_loan_quota_already_used_by_payroll_blocks_reimbursement_and_category_backfill_idempotent

当前 `tests/test_reimbursement_payments.py::test_loan_quota_already_used_by_payroll_blocks_reimbursement_and_category_backfill_idempotent`：**passed**；原失败调用行 365。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|355 `assert await service.backfill_reimbursement_categories(conn) == 0`|tests/test_reimbursement_payments.py::test_loan_quota_already_used_by_payroll_blocks_reimbursement_and_category_backfill_idempotent @ test_reimbursement_payments.py:373 已到达|exact assertion expression|
|358 `assert r.status_code == 200, r.text`|tests/test_reimbursement_payments.py::test_loan_quota_already_used_by_payroll_blocks_reimbursement_and_category_backfill_idempotent @ test_reimbursement_payments.py:377 已到达|exact assertion expression|
|363 `assert r.status_code == 400 and r.json()["detail"] == "垫款单剩余金额不足"`|tests/test_reimbursement_payments.py::test_loan_quota_already_used_by_payroll_blocks_reimbursement_and_category_backfill_idempotent @ test_reimbursement_payments.py:382 已到达|exact assertion expression|
|364 `assert await snapshot(f) == before`|tests/test_reimbursement_payments.py::test_loan_quota_already_used_by_payroll_blocks_reimbursement_and_category_backfill_idempotent @ test_reimbursement_payments.py:383 已到达|exact assertion expression|

## 064 tests.test_reimbursement_payments::test_decimal_item_sums_and_partially_approved_total_used_for_payment

当前 `tests/test_reimbursement_payments.py::test_decimal_item_sums_and_partially_approved_total_used_for_payment`：**failed**；原失败调用行 387。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|374 `assert r.status_code == 200`|tests/test_reimbursement_payments.py::test_decimal_item_sums_and_partially_approved_total_used_for_payment @ test_reimbursement_payments.py:393 已到达; tests/test_reimbursement_payments.py::test_decimal_item_sums_and_partially_approved_total_used_for_payment @ test_reimbursement_payments.py:402 已到达|exact assertion expression|
|379 `assert r.status_code == 200 and r.json()["status"] == "partially_approved"`|tests/test_reimbursement_payments.py::test_decimal_item_sums_and_partially_approved_total_used_for_payment @ test_reimbursement_payments.py:399 已到达|exact assertion expression|
|382 `assert r.status_code == 200, r.text`|tests/test_reimbursement_payments.py::test_decimal_item_sums_and_partially_approved_total_used_for_payment @ test_reimbursement_payments.py:393 已到达; tests/test_reimbursement_payments.py::test_decimal_item_sums_and_partially_approved_total_used_for_payment @ test_reimbursement_payments.py:402 已到达|exact assertion expression|
|383 `assert r.json()["payment"]["amount"] == .3 and r.json()["account_balance"] == 9999.7`|tests/test_reimbursement_payments.py::test_decimal_item_sums_and_partially_approved_total_used_for_payment @ test_reimbursement_payments.py:403 已到达|exact assertion expression|
|384 `assert (await costs(c))["amount"] == 750.3`|tests/test_reimbursement_payments.py::test_decimal_item_sums_and_partially_approved_total_used_for_payment @ test_reimbursement_payments.py:405 已到达 / 行失败|exact assertion expression|
|386 `assert r.status_code == 200 and r.json()["status"] == "partially_approved" and r.json()["account_balance"] == 10000`|tests/test_reimbursement_payments.py::test_decimal_item_sums_and_partially_approved_total_used_for_payment @ test_reimbursement_payments.py:407 已到达; tests/test_reimbursement_payments.py::test_decimal_item_sums_and_partially_approved_total_used_for_payment @ round3_flow_support.py:71 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|

## 065 tests.test_reimbursement_payments::test_legacy_paid_untouched_warehouse_scope_permissions_and_required_revoke_reason

当前 `tests/test_reimbursement_payments.py::test_legacy_paid_untouched_warehouse_scope_permissions_and_required_revoke_reason`：**passed**；原失败调用行 426。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|401 `assert hist.status_code == 200 and hist.json()["is_legacy_payment"] and hist.json()["data"] == []`|tests/test_reimbursement_payments.py::test_legacy_paid_untouched_warehouse_scope_permissions_and_required_revoke_reason @ test_reimbursement_payments.py:422 已到达|exact assertion expression|
|403 `assert revoke.status_code == 400 and await snapshot(f) == before`|tests/test_reimbursement_payments.py::test_legacy_paid_untouched_warehouse_scope_permissions_and_required_revoke_reason @ test_reimbursement_payments.py:424 已到达|exact assertion expression|
|410 `assert response.status_code == 403, response.text`|tests/test_reimbursement_payments.py::test_legacy_paid_untouched_warehouse_scope_permissions_and_required_revoke_reason @ test_reimbursement_payments.py:431 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|414 `assert (await c.get(BASE + f"/payment-sources?reimbursement_id={rid}", headers=auth(uid))).status_code == 403`|tests/test_reimbursement_payments.py::test_legacy_paid_untouched_warehouse_scope_permissions_and_required_revoke_reason @ test_reimbursement_payments.py:436 已到达; tests/test_reimbursement_payments.py::test_legacy_paid_untouched_warehouse_scope_permissions_and_required_revoke_reason @ test_reimbursement_payments.py:440 已到达|exact assertion expression|
|415 `assert (await c.post(f"{BASE}/{rid}/pay", headers=auth(uid), json={})).json()["detail"].startswith("无此操作权限")`|tests/test_reimbursement_payments.py::test_legacy_paid_untouched_warehouse_scope_permissions_and_required_revoke_reason @ test_reimbursement_payments.py:437 已到达|exact assertion expression|
|418 `assert (await c.get(BASE + f"/payment-sources?reimbursement_id={rid}", headers=auth(uid))).status_code == 403`|tests/test_reimbursement_payments.py::test_legacy_paid_untouched_warehouse_scope_permissions_and_required_revoke_reason @ test_reimbursement_payments.py:436 已到达; tests/test_reimbursement_payments.py::test_legacy_paid_untouched_warehouse_scope_permissions_and_required_revoke_reason @ test_reimbursement_payments.py:440 已到达|exact assertion expression|
|420 `assert (await pay(c, rid, photo, uid=3)).status_code == 200`|tests/test_reimbursement_payments.py::test_legacy_paid_untouched_warehouse_scope_permissions_and_required_revoke_reason @ test_reimbursement_payments.py:442 已到达|exact assertion expression|
|423 `assert resp.status_code == 400 and resp.json()["detail"] == "请填写撤销原因"`|tests/test_reimbursement_payments.py::test_legacy_paid_untouched_warehouse_scope_permissions_and_required_revoke_reason @ test_reimbursement_payments.py:445 已到达|changed assertion; see old/new expressions and policy rationale|
|424 `assert (await c.post(f"{BASE}/{rid}/revoke-payment", headers=auth(1), json={"reason": "测试后恢复"})).status_code == 200`|tests/test_reimbursement_payments.py::test_legacy_paid_untouched_warehouse_scope_permissions_and_required_revoke_reason @ test_reimbursement_payments.py:447 已到达|changed assertion; see old/new expressions and policy rationale|
|425 `assert (await pay(c, rid, photo, uid=4)).status_code == 200`|tests/test_reimbursement_payments.py::test_legacy_paid_untouched_warehouse_scope_permissions_and_required_revoke_reason @ test_reimbursement_payments.py:448 已到达; tests/test_reimbursement_payments.py::test_legacy_paid_untouched_warehouse_scope_permissions_and_required_revoke_reason @ test_reimbursement_payments.py:449 已到达; tests/test_reimbursement_payments.py::test_legacy_paid_untouched_warehouse_scope_permissions_and_required_revoke_reason @ test_reimbursement_payments.py:432 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|

## 066 tests.test_employee_advance_funding::test_source_money_cost_ledger_and_void[company_account]

当前 `tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[company_account]`：**failed**；原失败调用行 117。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|85 `assert r.status_code == 200, r.text`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[company_account] @ test_employee_advance_funding.py:95 已到达|exact assertion expression|
|88 `assert after['balance'] == before['balance'] - (1000 if source == 'company_account' else 0)`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[company_account] @ test_employee_advance_funding.py:100 已到达|exact assertion expression|
|89 `assert after['expenses'] == before['expenses'] + (1 if source == 'company_account' else 0)`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[company_account] @ test_employee_advance_funding.py:101 已到达|exact assertion expression|
|90 `assert after['expense_amount'] == before['expense_amount'] + (1000 if source == 'company_account' else 0)`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[company_account] @ test_employee_advance_funding.py:102 已到达|exact assertion expression|
|91 `assert after['fund_available'] == before['fund_available'] - (1000 if source == 'expense_fund' else 0)`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[company_account] @ test_employee_advance_funding.py:103 已到达|exact assertion expression|
|92 `assert flows_after['total'] == flows_before['total'] + (1 if source == 'company_account' else 0)`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[company_account] @ test_employee_advance_funding.py:104 已到达|exact assertion expression|
|95 `assert row['amount'] == 1000 and row['account_id'] == 1 and '员工1' in row['remark']`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[company_account] @ test_employee_advance_funding.py:107 已到达|exact assertion expression|
|98 `assert len(costs['data']) == 1 and costs['data'][0]['category_name'] == '员工预支'`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[company_account] @ test_employee_advance_funding.py:111 已到达 / 行失败|exact assertion expression|
|102 `assert (loan['employee_advance_used_amount'], loan['available_amount'], loan['outstanding_amount']) == (1000,9000,10000)`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[company_account] @ test_employee_advance_funding.py:115 未到达；对应分支已在 tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[cash_advance] @ 115 执行|exact assertion expression|
|104 `assert history['data'][0]['employee_advance_id'] == aid and history['employee_advance_used_amount'] == 1000`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[company_account] @ test_employee_advance_funding.py:117 未到达；对应分支已在 tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[cash_advance] @ 117 执行|exact assertion expression|
|109 `assert item.cost_record_only and item.review_status == 'approved' and a.expense_record_id is None`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[company_account] @ test_employee_advance_funding.py:122 未到达；对应分支已在 tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[expense_fund] @ 122 执行|exact assertion expression|
|110 `assert await snapshot(f) == old`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[company_account] @ test_employee_advance_funding.py:123 已到达; tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[company_account] @ test_employee_advance_funding.py:129 已到达|exact assertion expression|
|114 `assert result.status_code == 200, result.text`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[company_account] @ test_employee_advance_funding.py:127 已到达|exact assertion expression|
|115 `assert await state(f) == before and (await ledger(c))['total'] == flows_before['total']`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[company_account] @ test_employee_advance_funding.py:128 已到达|exact assertion expression|
|116 `assert await snapshot(f) == old`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[company_account] @ test_employee_advance_funding.py:123 已到达; tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[company_account] @ test_employee_advance_funding.py:129 已到达|exact assertion expression|

## 067 tests.test_employee_advance_funding::test_source_money_cost_ledger_and_void[cash_advance]

当前 `tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[cash_advance]`：**passed**；原失败调用行 117。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|85 `assert r.status_code == 200, r.text`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[cash_advance] @ test_employee_advance_funding.py:95 已到达|exact assertion expression|
|88 `assert after['balance'] == before['balance'] - (1000 if source == 'company_account' else 0)`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[cash_advance] @ test_employee_advance_funding.py:100 已到达|exact assertion expression|
|89 `assert after['expenses'] == before['expenses'] + (1 if source == 'company_account' else 0)`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[cash_advance] @ test_employee_advance_funding.py:101 已到达|exact assertion expression|
|90 `assert after['expense_amount'] == before['expense_amount'] + (1000 if source == 'company_account' else 0)`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[cash_advance] @ test_employee_advance_funding.py:102 已到达|exact assertion expression|
|91 `assert after['fund_available'] == before['fund_available'] - (1000 if source == 'expense_fund' else 0)`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[cash_advance] @ test_employee_advance_funding.py:103 已到达|exact assertion expression|
|92 `assert flows_after['total'] == flows_before['total'] + (1 if source == 'company_account' else 0)`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[cash_advance] @ test_employee_advance_funding.py:104 已到达|exact assertion expression|
|95 `assert row['amount'] == 1000 and row['account_id'] == 1 and '员工1' in row['remark']`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[cash_advance] @ test_employee_advance_funding.py:107 未到达；对应分支已在 tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[company_account] @ 107 执行|exact assertion expression|
|98 `assert len(costs['data']) == 1 and costs['data'][0]['category_name'] == '员工预支'`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[cash_advance] @ test_employee_advance_funding.py:111 未到达；对应分支已在 tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[company_account] @ 111 执行|exact assertion expression|
|102 `assert (loan['employee_advance_used_amount'], loan['available_amount'], loan['outstanding_amount']) == (1000,9000,10000)`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[cash_advance] @ test_employee_advance_funding.py:115 已到达|exact assertion expression|
|104 `assert history['data'][0]['employee_advance_id'] == aid and history['employee_advance_used_amount'] == 1000`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[cash_advance] @ test_employee_advance_funding.py:117 已到达|exact assertion expression|
|109 `assert item.cost_record_only and item.review_status == 'approved' and a.expense_record_id is None`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[cash_advance] @ test_employee_advance_funding.py:122 未到达；对应分支已在 tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[expense_fund] @ 122 执行|exact assertion expression|
|110 `assert await snapshot(f) == old`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[cash_advance] @ test_employee_advance_funding.py:123 已到达; tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[cash_advance] @ test_employee_advance_funding.py:129 已到达|exact assertion expression|
|114 `assert result.status_code == 200, result.text`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[cash_advance] @ test_employee_advance_funding.py:127 已到达|exact assertion expression|
|115 `assert await state(f) == before and (await ledger(c))['total'] == flows_before['total']`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[cash_advance] @ test_employee_advance_funding.py:128 已到达|exact assertion expression|
|116 `assert await snapshot(f) == old`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[cash_advance] @ test_employee_advance_funding.py:123 已到达; tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[cash_advance] @ test_employee_advance_funding.py:129 已到达|exact assertion expression|

## 068 tests.test_employee_advance_funding::test_source_money_cost_ledger_and_void[expense_fund]

当前 `tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[expense_fund]`：**passed**；原失败调用行 117。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|85 `assert r.status_code == 200, r.text`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[expense_fund] @ test_employee_advance_funding.py:95 已到达|exact assertion expression|
|88 `assert after['balance'] == before['balance'] - (1000 if source == 'company_account' else 0)`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[expense_fund] @ test_employee_advance_funding.py:100 已到达|exact assertion expression|
|89 `assert after['expenses'] == before['expenses'] + (1 if source == 'company_account' else 0)`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[expense_fund] @ test_employee_advance_funding.py:101 已到达|exact assertion expression|
|90 `assert after['expense_amount'] == before['expense_amount'] + (1000 if source == 'company_account' else 0)`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[expense_fund] @ test_employee_advance_funding.py:102 已到达|exact assertion expression|
|91 `assert after['fund_available'] == before['fund_available'] - (1000 if source == 'expense_fund' else 0)`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[expense_fund] @ test_employee_advance_funding.py:103 已到达|exact assertion expression|
|92 `assert flows_after['total'] == flows_before['total'] + (1 if source == 'company_account' else 0)`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[expense_fund] @ test_employee_advance_funding.py:104 已到达|exact assertion expression|
|95 `assert row['amount'] == 1000 and row['account_id'] == 1 and '员工1' in row['remark']`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[expense_fund] @ test_employee_advance_funding.py:107 未到达；对应分支已在 tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[company_account] @ 107 执行|exact assertion expression|
|98 `assert len(costs['data']) == 1 and costs['data'][0]['category_name'] == '员工预支'`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[expense_fund] @ test_employee_advance_funding.py:111 未到达；对应分支已在 tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[company_account] @ 111 执行|exact assertion expression|
|102 `assert (loan['employee_advance_used_amount'], loan['available_amount'], loan['outstanding_amount']) == (1000,9000,10000)`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[expense_fund] @ test_employee_advance_funding.py:115 未到达；对应分支已在 tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[cash_advance] @ 115 执行|exact assertion expression|
|104 `assert history['data'][0]['employee_advance_id'] == aid and history['employee_advance_used_amount'] == 1000`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[expense_fund] @ test_employee_advance_funding.py:117 未到达；对应分支已在 tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[cash_advance] @ 117 执行|exact assertion expression|
|109 `assert item.cost_record_only and item.review_status == 'approved' and a.expense_record_id is None`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[expense_fund] @ test_employee_advance_funding.py:122 已到达|exact assertion expression|
|110 `assert await snapshot(f) == old`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[expense_fund] @ test_employee_advance_funding.py:123 已到达; tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[expense_fund] @ test_employee_advance_funding.py:129 已到达|exact assertion expression|
|114 `assert result.status_code == 200, result.text`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[expense_fund] @ test_employee_advance_funding.py:127 已到达|exact assertion expression|
|115 `assert await state(f) == before and (await ledger(c))['total'] == flows_before['total']`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[expense_fund] @ test_employee_advance_funding.py:128 已到达|exact assertion expression|
|116 `assert await snapshot(f) == old`|tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[expense_fund] @ test_employee_advance_funding.py:123 已到达; tests/test_employee_advance_funding.py::test_source_money_cost_ledger_and_void[expense_fund] @ test_employee_advance_funding.py:129 已到达|exact assertion expression|

## 069 tests.test_employee_advance_funding::test_pending_no_money_then_approval_once_and_rejection[company_account]

当前 `tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[company_account]`：**passed**；原失败调用行 144。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|127 `assert r.status_code == 200 and r.json()['approval_status'] == 'pending', r.text`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[company_account] @ test_employee_advance_funding.py:141 已到达|exact assertion expression|
|128 `assert await state(f) == before`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[company_account] @ test_employee_advance_funding.py:142 已到达; tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[company_account] @ test_employee_advance_funding.py:146 已到达|exact assertion expression|
|130 `assert next(x for x in opts['cash_advances'] if x['id'] == 1)['available_amount'] == 10000`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[company_account] @ test_employee_advance_funding.py:144 已到达|exact assertion expression|
|132 `assert approved.status_code == 200, approved.text`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[company_account] @ test_employee_advance_funding.py:148 已到达|changed assertion; see old/new expressions and policy rationale|
|134 `assert saved['balance'] == 20000 - (1000 if source == 'company_account' else 0)`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[company_account] @ test_employee_advance_funding.py:150 已到达|exact assertion expression|
|135 `assert saved['fund_available'] == 10000 - (1000 if source == 'expense_fund' else 0)`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[company_account] @ test_employee_advance_funding.py:151 已到达|exact assertion expression|
|138 `assert next(x for x in opts['cash_advances'] if x['id'] == 1)['available_amount'] == 9000`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[company_account] @ test_employee_advance_funding.py:154 未到达；对应分支已在 tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[cash_advance] @ 154 执行|exact assertion expression|
|140 `assert repeat.status_code == 400 and await state(f) == saved`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[company_account] @ test_employee_advance_funding.py:156 已到达|exact assertion expression|
|143 `assert rejected.status_code == 200 and await state(f) == saved`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[company_account] @ test_employee_advance_funding.py:159 已到达|exact assertion expression|

## 070 tests.test_employee_advance_funding::test_pending_no_money_then_approval_once_and_rejection[cash_advance]

当前 `tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[cash_advance]`：**passed**；原失败调用行 144。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|127 `assert r.status_code == 200 and r.json()['approval_status'] == 'pending', r.text`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[cash_advance] @ test_employee_advance_funding.py:141 已到达|exact assertion expression|
|128 `assert await state(f) == before`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[cash_advance] @ test_employee_advance_funding.py:142 已到达; tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[cash_advance] @ test_employee_advance_funding.py:146 已到达|exact assertion expression|
|130 `assert next(x for x in opts['cash_advances'] if x['id'] == 1)['available_amount'] == 10000`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[cash_advance] @ test_employee_advance_funding.py:144 已到达|exact assertion expression|
|132 `assert approved.status_code == 200, approved.text`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[cash_advance] @ test_employee_advance_funding.py:148 已到达|changed assertion; see old/new expressions and policy rationale|
|134 `assert saved['balance'] == 20000 - (1000 if source == 'company_account' else 0)`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[cash_advance] @ test_employee_advance_funding.py:150 已到达|exact assertion expression|
|135 `assert saved['fund_available'] == 10000 - (1000 if source == 'expense_fund' else 0)`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[cash_advance] @ test_employee_advance_funding.py:151 已到达|exact assertion expression|
|138 `assert next(x for x in opts['cash_advances'] if x['id'] == 1)['available_amount'] == 9000`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[cash_advance] @ test_employee_advance_funding.py:154 已到达|exact assertion expression|
|140 `assert repeat.status_code == 400 and await state(f) == saved`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[cash_advance] @ test_employee_advance_funding.py:156 已到达|exact assertion expression|
|143 `assert rejected.status_code == 200 and await state(f) == saved`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[cash_advance] @ test_employee_advance_funding.py:159 已到达|exact assertion expression|

## 071 tests.test_employee_advance_funding::test_pending_no_money_then_approval_once_and_rejection[expense_fund]

当前 `tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[expense_fund]`：**passed**；原失败调用行 144。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|127 `assert r.status_code == 200 and r.json()['approval_status'] == 'pending', r.text`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[expense_fund] @ test_employee_advance_funding.py:141 已到达|exact assertion expression|
|128 `assert await state(f) == before`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[expense_fund] @ test_employee_advance_funding.py:142 已到达; tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[expense_fund] @ test_employee_advance_funding.py:146 已到达|exact assertion expression|
|130 `assert next(x for x in opts['cash_advances'] if x['id'] == 1)['available_amount'] == 10000`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[expense_fund] @ test_employee_advance_funding.py:144 已到达|exact assertion expression|
|132 `assert approved.status_code == 200, approved.text`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[expense_fund] @ test_employee_advance_funding.py:148 已到达|changed assertion; see old/new expressions and policy rationale|
|134 `assert saved['balance'] == 20000 - (1000 if source == 'company_account' else 0)`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[expense_fund] @ test_employee_advance_funding.py:150 已到达|exact assertion expression|
|135 `assert saved['fund_available'] == 10000 - (1000 if source == 'expense_fund' else 0)`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[expense_fund] @ test_employee_advance_funding.py:151 已到达|exact assertion expression|
|138 `assert next(x for x in opts['cash_advances'] if x['id'] == 1)['available_amount'] == 9000`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[expense_fund] @ test_employee_advance_funding.py:154 未到达；对应分支已在 tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[cash_advance] @ 154 执行|exact assertion expression|
|140 `assert repeat.status_code == 400 and await state(f) == saved`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[expense_fund] @ test_employee_advance_funding.py:156 已到达|exact assertion expression|
|143 `assert rejected.status_code == 200 and await state(f) == saved`|tests/test_employee_advance_funding.py::test_pending_no_money_then_approval_once_and_rejection[expense_fund] @ test_employee_advance_funding.py:159 已到达|exact assertion expression|

## 072 tests.test_employee_advance_funding::test_validation_no_partial_writes[values8-\u53ea\u80fd\u4f7f\u7528\u5df2\u786e\u8ba4\u7684\u57ab\u6b3e\u5355]

当前 `tests/test_employee_advance_funding.py::test_validation_no_partial_writes[values8-\u7f3a\u5c11\u6709\u6548\u6838\u9a8c]`：**passed**；原失败调用行 170。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|165 `assert r.status_code == 400 and r.json()['detail'].startswith(message), r.text`|tests/test_employee_advance_funding.py::test_validation_no_partial_writes[values8-\u7f3a\u5c11\u6709\u6548\u6838\u9a8c] @ test_employee_advance_funding.py:181 已到达|changed assertion; see old/new expressions and policy rationale|
|166 `assert await state(f) == before`|tests/test_employee_advance_funding.py::test_validation_no_partial_writes[values8-\u7f3a\u5c11\u6709\u6548\u6838\u9a8c] @ test_employee_advance_funding.py:182 已到达|exact assertion expression|
|168 `assert (await db.execute(select(func.count()).select_from(EmployeeAdvance))).scalar_one() == 0`|tests/test_employee_advance_funding.py::test_validation_no_partial_writes[values8-\u7f3a\u5c11\u6709\u6548\u6838\u9a8c] @ test_employee_advance_funding.py:184 已到达|exact assertion expression|

## 073 tests.test_employee_advance_funding::test_validation_no_partial_writes[values9-\u57ab\u6b3e\u5355\u5e01\u79cd\u4e0e\u9884\u652f\u4e0d\u4e00\u81f4]

当前 `tests/test_employee_advance_funding.py::test_validation_no_partial_writes[values9-\u57ab\u6b3e\u5355\u5e01\u79cd\u4e0e\u9884\u652f\u4e0d\u4e00\u81f4]`：**passed**；原失败调用行 170。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|165 `assert r.status_code == 400 and r.json()['detail'].startswith(message), r.text`|tests/test_employee_advance_funding.py::test_validation_no_partial_writes[values9-\u57ab\u6b3e\u5355\u5e01\u79cd\u4e0e\u9884\u652f\u4e0d\u4e00\u81f4] @ test_employee_advance_funding.py:181 已到达|changed assertion; see old/new expressions and policy rationale|
|166 `assert await state(f) == before`|tests/test_employee_advance_funding.py::test_validation_no_partial_writes[values9-\u57ab\u6b3e\u5355\u5e01\u79cd\u4e0e\u9884\u652f\u4e0d\u4e00\u81f4] @ test_employee_advance_funding.py:182 已到达|exact assertion expression|
|168 `assert (await db.execute(select(func.count()).select_from(EmployeeAdvance))).scalar_one() == 0`|tests/test_employee_advance_funding.py::test_validation_no_partial_writes[values9-\u57ab\u6b3e\u5355\u5e01\u79cd\u4e0e\u9884\u652f\u4e0d\u4e00\u81f4] @ test_employee_advance_funding.py:184 已到达|exact assertion expression|

## 074 tests.test_employee_advance_funding::test_validation_no_partial_writes[values10-\u57ab\u6b3e\u5355\u5269\u4f59\u91d1\u989d\u4e0d\u8db3]

当前 `tests/test_employee_advance_funding.py::test_validation_no_partial_writes[values10-\u57ab\u6b3e\u5355\u5269\u4f59\u91d1\u989d\u4e0d\u8db3]`：**passed**；原失败调用行 170。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|165 `assert r.status_code == 400 and r.json()['detail'].startswith(message), r.text`|tests/test_employee_advance_funding.py::test_validation_no_partial_writes[values10-\u57ab\u6b3e\u5355\u5269\u4f59\u91d1\u989d\u4e0d\u8db3] @ test_employee_advance_funding.py:181 已到达|changed assertion; see old/new expressions and policy rationale|
|166 `assert await state(f) == before`|tests/test_employee_advance_funding.py::test_validation_no_partial_writes[values10-\u57ab\u6b3e\u5355\u5269\u4f59\u91d1\u989d\u4e0d\u8db3] @ test_employee_advance_funding.py:182 已到达|exact assertion expression|
|168 `assert (await db.execute(select(func.count()).select_from(EmployeeAdvance))).scalar_one() == 0`|tests/test_employee_advance_funding.py::test_validation_no_partial_writes[values10-\u57ab\u6b3e\u5355\u5269\u4f59\u91d1\u989d\u4e0d\u8db3] @ test_employee_advance_funding.py:184 已到达|exact assertion expression|

## 075 tests.test_employee_advance_funding::test_approval_rechecks_resources_and_keeps_pending_on_failure[company_account]

当前 `tests/test_employee_advance_funding.py::test_approval_rechecks_resources_and_keeps_pending_on_failure[company_account]`：**passed**；原失败调用行 192。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|187 `assert r.status_code == 400, r.text`|tests/test_employee_advance_funding.py::test_approval_rechecks_resources_and_keeps_pending_on_failure[company_account] @ test_employee_advance_funding.py:204 已到达|exact assertion expression|
|190 `assert a.approval_status == 'pending' and a.reviewer_id is None and a.reviewed_at is None`|tests/test_employee_advance_funding.py::test_approval_rechecks_resources_and_keeps_pending_on_failure[company_account] @ test_employee_advance_funding.py:207 已到达|changed assertion; see old/new expressions and policy rationale|
|191 `assert await state(f) == before`|tests/test_employee_advance_funding.py::test_approval_rechecks_resources_and_keeps_pending_on_failure[company_account] @ test_employee_advance_funding.py:208 已到达|exact assertion expression|

## 076 tests.test_employee_advance_funding::test_approval_rechecks_resources_and_keeps_pending_on_failure[cash_advance]

当前 `tests/test_employee_advance_funding.py::test_approval_rechecks_resources_and_keeps_pending_on_failure[cash_advance]`：**passed**；原失败调用行 192。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|187 `assert r.status_code == 400, r.text`|tests/test_employee_advance_funding.py::test_approval_rechecks_resources_and_keeps_pending_on_failure[cash_advance] @ test_employee_advance_funding.py:204 已到达|exact assertion expression|
|190 `assert a.approval_status == 'pending' and a.reviewer_id is None and a.reviewed_at is None`|tests/test_employee_advance_funding.py::test_approval_rechecks_resources_and_keeps_pending_on_failure[cash_advance] @ test_employee_advance_funding.py:207 已到达|changed assertion; see old/new expressions and policy rationale|
|191 `assert await state(f) == before`|tests/test_employee_advance_funding.py::test_approval_rechecks_resources_and_keeps_pending_on_failure[cash_advance] @ test_employee_advance_funding.py:208 已到达|exact assertion expression|

## 077 tests.test_employee_advance_funding::test_approval_rechecks_resources_and_keeps_pending_on_failure[expense_fund]

当前 `tests/test_employee_advance_funding.py::test_approval_rechecks_resources_and_keeps_pending_on_failure[expense_fund]`：**passed**；原失败调用行 192。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|187 `assert r.status_code == 400, r.text`|tests/test_employee_advance_funding.py::test_approval_rechecks_resources_and_keeps_pending_on_failure[expense_fund] @ test_employee_advance_funding.py:204 已到达|exact assertion expression|
|190 `assert a.approval_status == 'pending' and a.reviewer_id is None and a.reviewed_at is None`|tests/test_employee_advance_funding.py::test_approval_rechecks_resources_and_keeps_pending_on_failure[expense_fund] @ test_employee_advance_funding.py:207 已到达|changed assertion; see old/new expressions and policy rationale|
|191 `assert await state(f) == before`|tests/test_employee_advance_funding.py::test_approval_rechecks_resources_and_keeps_pending_on_failure[expense_fund] @ test_employee_advance_funding.py:208 已到达|exact assertion expression|

## 078 tests.test_employee_advance_funding::test_history_failure_rolls_back_all_money_and_records[company_account]

当前 `tests/test_employee_advance_funding.py::test_history_failure_rolls_back_all_money_and_records[company_account]`：**passed**；原失败调用行 207。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|204 `assert await state(f) == before`|tests/test_employee_advance_funding.py::test_history_failure_rolls_back_all_money_and_records[company_account] @ test_employee_advance_funding.py:224 已到达|exact assertion expression|
|206 `assert (await db.execute(select(func.count()).select_from(EmployeeAdvance))).scalar_one() == 0`|tests/test_employee_advance_funding.py::test_history_failure_rolls_back_all_money_and_records[company_account] @ test_employee_advance_funding.py:226 已到达|changed assertion; see old/new expressions and policy rationale|

## 079 tests.test_employee_advance_funding::test_history_failure_rolls_back_all_money_and_records[cash_advance]

当前 `tests/test_employee_advance_funding.py::test_history_failure_rolls_back_all_money_and_records[cash_advance]`：**passed**；原失败调用行 207。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|204 `assert await state(f) == before`|tests/test_employee_advance_funding.py::test_history_failure_rolls_back_all_money_and_records[cash_advance] @ test_employee_advance_funding.py:224 已到达|exact assertion expression|
|206 `assert (await db.execute(select(func.count()).select_from(EmployeeAdvance))).scalar_one() == 0`|tests/test_employee_advance_funding.py::test_history_failure_rolls_back_all_money_and_records[cash_advance] @ test_employee_advance_funding.py:226 已到达|changed assertion; see old/new expressions and policy rationale|

## 080 tests.test_employee_advance_funding::test_history_failure_rolls_back_all_money_and_records[expense_fund]

当前 `tests/test_employee_advance_funding.py::test_history_failure_rolls_back_all_money_and_records[expense_fund]`：**passed**；原失败调用行 207。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|204 `assert await state(f) == before`|tests/test_employee_advance_funding.py::test_history_failure_rolls_back_all_money_and_records[expense_fund] @ test_employee_advance_funding.py:224 已到达|exact assertion expression|
|206 `assert (await db.execute(select(func.count()).select_from(EmployeeAdvance))).scalar_one() == 0`|tests/test_employee_advance_funding.py::test_history_failure_rolls_back_all_money_and_records[expense_fund] @ test_employee_advance_funding.py:226 已到达|changed assertion; see old/new expressions and policy rationale|

## 081 tests.test_employee_advance_funding::test_shared_cash_capacity_cannot_be_reused

当前 `tests/test_employee_advance_funding.py::test_shared_cash_capacity_cannot_be_reused`：**passed**；原失败调用行 225。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|214 `assert r.status_code == 200, r.text`|tests/test_employee_advance_funding.py::test_shared_cash_capacity_cannot_be_reused @ test_employee_advance_funding.py:236 已到达|exact assertion expression|
|216 `assert again.status_code == 400 and again.json()['detail'] == '垫款单剩余金额不足'`|tests/test_employee_advance_funding.py::test_shared_cash_capacity_cannot_be_reused @ test_employee_advance_funding.py:239 已到达|exact assertion expression|
|224 `assert next(x for x in rows if x['id'] == 1)['available_amount'] == 0`|tests/test_employee_advance_funding.py::test_shared_cash_capacity_cannot_be_reused @ test_employee_advance_funding.py:247 已到达|exact assertion expression|

## 082 tests.test_employee_advance_funding::test_three_sources_share_original_salary_cap[1]

当前 `tests/test_employee_advance_funding.py::test_three_sources_share_original_salary_cap[1]`：**passed**；原失败调用行 245。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|241 `assert r.status_code == 200, r.text`|tests/test_employee_advance_funding.py::test_three_sources_share_original_salary_cap[1] @ test_employee_advance_funding.py:264 已到达|exact assertion expression|
|243 `assert r.status_code == 400 and '当前可用 0.00 元' in r.json()['detail']`|tests/test_employee_advance_funding.py::test_three_sources_share_original_salary_cap[1] @ test_employee_advance_funding.py:266 已到达|exact assertion expression|

## 083 tests.test_employee_advance_funding::test_three_sources_share_original_salary_cap[4]

当前 `tests/test_employee_advance_funding.py::test_three_sources_share_original_salary_cap[4]`：**passed**；原失败调用行 245。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|241 `assert r.status_code == 200, r.text`|tests/test_employee_advance_funding.py::test_three_sources_share_original_salary_cap[4] @ test_employee_advance_funding.py:264 已到达|exact assertion expression|
|243 `assert r.status_code == 400 and '当前可用 0.00 元' in r.json()['detail']`|tests/test_employee_advance_funding.py::test_three_sources_share_original_salary_cap[4] @ test_employee_advance_funding.py:266 已到达|exact assertion expression|

## 084 tests.test_employee_advance_funding::test_fund_review_cannot_refund_an_approved_advance

当前 `tests/test_employee_advance_funding.py::test_fund_review_cannot_refund_an_approved_advance`：**passed**；原失败调用行 311。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|303 `assert r.status_code == 200, r.text`|tests/test_employee_advance_funding.py::test_fund_review_cannot_refund_an_approved_advance @ test_employee_advance_funding.py:323 已到达|exact assertion expression|
|309 `assert r.status_code == 400 and r.json()['detail'] == '员工预支关联开销请在员工预支中处理'`|tests/test_employee_advance_funding.py::test_fund_review_cannot_refund_an_approved_advance @ test_employee_advance_funding.py:330 已到达|exact assertion expression|
|310 `assert await state(f) == before`|tests/test_employee_advance_funding.py::test_fund_review_cannot_refund_an_approved_advance @ test_employee_advance_funding.py:331 已到达|exact assertion expression|

## 085 tests.test_employee_advance_funding::test_cny_sources_keep_original_exchange_rate_cap

当前 `tests/test_employee_advance_funding.py::test_cny_sources_keep_original_exchange_rate_cap`：**passed**；原失败调用行 330。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|327 `assert a.status_code == b.status_code == 200, (a.text,b.text)`|tests/test_employee_advance_funding.py::test_cny_sources_keep_original_exchange_rate_cap @ test_employee_advance_funding.py:348 已到达|exact assertion expression|
|329 `assert r.status_code == 400 and '当前可用 0.00 元' in r.json()['detail']`|tests/test_employee_advance_funding.py::test_cny_sources_keep_original_exchange_rate_cap @ test_employee_advance_funding.py:350 已到达|exact assertion expression|

## 086 tests.test_employee_advance_funding::test_company_balance_keeps_cent_precision_after_fractional_advances

当前 `tests/test_employee_advance_funding.py::test_company_balance_keeps_cent_precision_after_fractional_advances`：**passed**；原失败调用行 361。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|359 `assert r.status_code == 200, r.text`|tests/test_employee_advance_funding.py::test_company_balance_keeps_cent_precision_after_fractional_advances @ test_employee_advance_funding.py:380 已到达|exact assertion expression|
|360 `assert (await state(f))['balance'] == 0`|tests/test_employee_advance_funding.py::test_company_balance_keeps_cent_precision_after_fractional_advances @ test_employee_advance_funding.py:382 已到达|exact assertion expression|

## 087 tests.test_employee_advance_funding::test_locked_validation_refreshes_previously_loaded_resource[cash_advance-\u53ea\u80fd\u4f7f\u7528\u5df2\u786e\u8ba4\u7684\u57ab\u6b3e\u5355]

当前 `tests/test_employee_advance_funding.py::test_locked_validation_refreshes_previously_loaded_resource[cash_advance-\u53ea\u80fd\u4f7f\u7528\u5df2\u786e\u8ba4\u7684\u57ab\u6b3e\u5355]`：**passed**；原失败调用行 386。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|374 `assert cached.id == 1`|tests/test_employee_advance_funding.py::test_locked_validation_refreshes_previously_loaded_resource[cash_advance-\u53ea\u80fd\u4f7f\u7528\u5df2\u786e\u8ba4\u7684\u57ab\u6b3e\u5355] @ test_employee_advance_funding.py:396 已到达|exact assertion expression|
|385 `assert rejected.value.status_code == 400 and rejected.value.detail.startswith(message)`|tests/test_employee_advance_funding.py::test_locked_validation_refreshes_previously_loaded_resource[cash_advance-\u53ea\u80fd\u4f7f\u7528\u5df2\u786e\u8ba4\u7684\u57ab\u6b3e\u5355] @ test_employee_advance_funding.py:407 已到达|exact assertion expression|

## 088 tests.test_employee_advance_limit::test_requested_monthly_10000_workflow_and_pending_reservation

当前 `tests/test_employee_advance_limit.py::test_requested_monthly_10000_workflow_and_pending_reservation`：**passed**；原失败调用行 106。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|68 `assert first.status_code == 200, first.text`|tests/test_employee_advance_limit.py::test_requested_monthly_10000_workflow_and_pending_reservation @ test_employee_advance_limit.py:69 已到达|exact assertion expression|
|69 `assert first.json()["approval_status"] == "approved"`|tests/test_employee_advance_limit.py::test_requested_monthly_10000_workflow_and_pending_reservation @ test_employee_advance_limit.py:70 已到达|changed assertion; see old/new expressions and policy rationale|
|70 `assert first.json()["limit_check"] == {                 "checked": True, "currency": "THB", "monthly_salary": 10000,                 "occupied_amount": 0, "requested_amount": 8000,                 "available_amount": 10000, "remaining_amount": 2000,             }`|tests/test_employee_advance_limit.py::test_requested_monthly_10000_workflow_and_pending_reservation @ test_employee_advance_limit.py:71 已到达|exact assertion expression|
|77 `assert exceeded.status_code == 400`|tests/test_employee_advance_limit.py::test_requested_monthly_10000_workflow_and_pending_reservation @ test_employee_advance_limit.py:78 已到达|exact assertion expression|
|78 `assert exceeded.json() == {"detail": "预支合计不能超过当月工资，当前可用 2000.00 元"}`|tests/test_employee_advance_limit.py::test_requested_monthly_10000_workflow_and_pending_reservation @ test_employee_advance_limit.py:79 已到达|exact assertion expression|
|79 `assert await advances_and_costs(factory) == before`|tests/test_employee_advance_limit.py::test_requested_monthly_10000_workflow_and_pending_reservation @ test_employee_advance_limit.py:80 已到达; tests/test_employee_advance_limit.py::test_requested_monthly_10000_workflow_and_pending_reservation @ test_employee_advance_limit.py:91 已到达|exact assertion expression|
|81 `assert pending.status_code == 200 and pending.json()["approval_status"] == "pending", pending.text`|tests/test_employee_advance_limit.py::test_requested_monthly_10000_workflow_and_pending_reservation @ test_employee_advance_limit.py:82 已到达|exact assertion expression|
|82 `assert pending.json()["limit_check"]["remaining_amount"] == 1000`|tests/test_employee_advance_limit.py::test_requested_monthly_10000_workflow_and_pending_reservation @ test_employee_advance_limit.py:83 已到达|exact assertion expression|
|84 `assert boundary.status_code == 200 and boundary.json()["approval_status"] == "pending", boundary.text`|tests/test_employee_advance_limit.py::test_requested_monthly_10000_workflow_and_pending_reservation @ test_employee_advance_limit.py:85 已到达|exact assertion expression|
|85 `assert boundary.json()["limit_check"]["remaining_amount"] == 0`|tests/test_employee_advance_limit.py::test_requested_monthly_10000_workflow_and_pending_reservation @ test_employee_advance_limit.py:86 已到达|exact assertion expression|
|88 `assert exhausted.status_code == 400`|tests/test_employee_advance_limit.py::test_requested_monthly_10000_workflow_and_pending_reservation @ test_employee_advance_limit.py:89 已到达|exact assertion expression|
|89 `assert exhausted.json() == {"detail": "预支合计不能超过当月工资，当前可用 0.00 元"}`|tests/test_employee_advance_limit.py::test_requested_monthly_10000_workflow_and_pending_reservation @ test_employee_advance_limit.py:90 已到达|exact assertion expression|
|90 `assert await advances_and_costs(factory) == before`|tests/test_employee_advance_limit.py::test_requested_monthly_10000_workflow_and_pending_reservation @ test_employee_advance_limit.py:80 已到达; tests/test_employee_advance_limit.py::test_requested_monthly_10000_workflow_and_pending_reservation @ test_employee_advance_limit.py:91 已到达|exact assertion expression|
|98 `assert after_settled.status_code == 200, after_settled.text`|tests/test_employee_advance_limit.py::test_requested_monthly_10000_workflow_and_pending_reservation @ test_employee_advance_limit.py:101 已到达|exact assertion expression|
|99 `assert after_settled.json()["limit_check"]["occupied_amount"] == 0`|tests/test_employee_advance_limit.py::test_requested_monthly_10000_workflow_and_pending_reservation @ test_employee_advance_limit.py:102 已到达|exact assertion expression|
|100 `assert await snapshot(factory) == old_payroll`|tests/test_employee_advance_limit.py::test_requested_monthly_10000_workflow_and_pending_reservation @ test_employee_advance_limit.py:103 已到达|exact assertion expression|

## 089 tests.test_employee_advance_limit::test_actual_payroll_settlement_restores_quota_without_formula_changes

当前 `tests/test_employee_advance_limit.py::test_actual_payroll_settlement_restores_quota_without_formula_changes`：**passed**；原失败调用行 286。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|275 `assert response.status_code == 200`|tests/test_employee_advance_limit.py::test_actual_payroll_settlement_restores_quota_without_formula_changes @ test_employee_advance_limit.py:278 已到达|exact assertion expression|
|276 `assert (await create(client, 10400)).status_code == 400`|tests/test_employee_advance_limit.py::test_actual_payroll_settlement_restores_quota_without_formula_changes @ test_employee_advance_limit.py:279 已到达|exact assertion expression|
|279 `assert (pay.base_pay, pay.advance_deduction, pay.net_pay) == (1200, 1000, 200)`|tests/test_employee_advance_limit.py::test_actual_payroll_settlement_restores_quota_without_formula_changes @ test_employee_advance_limit.py:283 已到达|exact assertion expression|
|281 `assert response.status_code == 200 and response.json()["limit_check"]["occupied_amount"] == 0`|tests/test_employee_advance_limit.py::test_actual_payroll_settlement_restores_quota_without_formula_changes @ test_employee_advance_limit.py:285 已到达|exact assertion expression|
|283 `assert [r for r in current if r[0] in {v[0] for v in old}] == old`|tests/test_employee_advance_limit.py::test_actual_payroll_settlement_restores_quota_without_formula_changes @ test_employee_advance_limit.py:287 已到达|exact assertion expression|

## 090 tests.test_employee_advance_void::test_void_keeps_row_deletes_cost_releases_quota_and_never_recalculates

当前 `tests/test_employee_advance_void.py::test_void_keeps_row_deletes_cost_releases_quota_and_never_recalculates`：**passed**；原失败调用行 89。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|55 `assert eid`|tests/test_employee_advance_void.py::test_void_keeps_row_deletes_cost_releases_quota_and_never_recalculates @ test_employee_advance_void.py:60 已到达|exact assertion expression|
|57 `assert (await db.execute(select(func.count()).select_from(ExpenseRecord))).scalar_one() == 1`|tests/test_employee_advance_void.py::test_void_keeps_row_deletes_cost_releases_quota_and_never_recalculates @ test_employee_advance_void.py:62 已到达|exact assertion expression|
|59 `assert response.status_code == 200, response.text`|tests/test_employee_advance_void.py::test_void_keeps_row_deletes_cost_releases_quota_and_never_recalculates @ test_employee_advance_void.py:64 已到达|exact assertion expression|
|61 `assert data["status"] == "voided" and data["voided_by"] == 1 and data["voided_at"]`|tests/test_employee_advance_void.py::test_void_keeps_row_deletes_cost_releases_quota_and_never_recalculates @ test_employee_advance_void.py:66 已到达|exact assertion expression|
|62 `assert data["void_reason"] == "测试登记有误" and data["remaining_amount"] == 0`|tests/test_employee_advance_void.py::test_void_keeps_row_deletes_cost_releases_quota_and_never_recalculates @ test_employee_advance_void.py:67 已到达|exact assertion expression|
|63 `assert data["approval_status"] == "approved" and data["expense_record_id"] is None`|tests/test_employee_advance_void.py::test_void_keeps_row_deletes_cost_releases_quota_and_never_recalculates @ test_employee_advance_void.py:68 已到达|exact assertion expression|
|66 `assert row and row.amount == 1000 and row.status == "voided" and row.void_reason == "测试登记有误"`|tests/test_employee_advance_void.py::test_void_keeps_row_deletes_cost_releases_quota_and_never_recalculates @ test_employee_advance_void.py:71 已到达|exact assertion expression|
|67 `assert row.voided_by == 1 and row.voided_at and row.deducted_amount == 0`|tests/test_employee_advance_void.py::test_void_keeps_row_deletes_cost_releases_quota_and_never_recalculates @ test_employee_advance_void.py:72 已到达|exact assertion expression|
|68 `assert await db.get(ExpenseRecord, eid) is None`|tests/test_employee_advance_void.py::test_void_keeps_row_deletes_cost_releases_quota_and_never_recalculates @ test_employee_advance_void.py:73 已到达|exact assertion expression|
|69 `assert (await db.execute(select(func.count()).select_from(EmployeeAdvance))).scalar_one() == 1`|tests/test_employee_advance_void.py::test_void_keeps_row_deletes_cost_releases_quota_and_never_recalculates @ test_employee_advance_void.py:74 已到达|exact assertion expression|
|70 `assert (await db.execute(select(func.count()).select_from(ExpenseRecord))).scalar_one() == 0`|tests/test_employee_advance_void.py::test_void_keeps_row_deletes_cost_releases_quota_and_never_recalculates @ test_employee_advance_void.py:75 已到达|exact assertion expression|
|73 `assert removed.before_data["amount"] == 1000 and removed.before_data["employee_advance_id"] == aid`|tests/test_employee_advance_void.py::test_void_keeps_row_deletes_cost_releases_quota_and_never_recalculates @ test_employee_advance_void.py:78 已到达|exact assertion expression|
|74 `assert removed.after_data["reason"] == "作废预支：测试登记有误"`|tests/test_employee_advance_void.py::test_void_keeps_row_deletes_cost_releases_quota_and_never_recalculates @ test_employee_advance_void.py:79 已到达|exact assertion expression|
|76 `assert log.before_data["expense_record_id"] == eid and log.after_data["voided_by"] == 1`|tests/test_employee_advance_void.py::test_void_keeps_row_deletes_cost_releases_quota_and_never_recalculates @ test_employee_advance_void.py:81 已到达|exact assertion expression|
|78 `assert len(listing) == 1 and listing[0]["is_voided"] and not listing[0]["can_void"]`|tests/test_employee_advance_void.py::test_void_keeps_row_deletes_cost_releases_quota_and_never_recalculates @ test_employee_advance_void.py:83 已到达|exact assertion expression|
|79 `assert listing[0]["remaining_amount"] == 0 and listing[0]["voided_by_name"] == "warehouse_admin"`|tests/test_employee_advance_void.py::test_void_keeps_row_deletes_cost_releases_quota_and_never_recalculates @ test_employee_advance_void.py:84 已到达|exact assertion expression|
|81 `assert summary == {"total_by_currency": [], "debtor_count": 0}`|tests/test_employee_advance_void.py::test_void_keeps_row_deletes_cost_releases_quota_and_never_recalculates @ test_employee_advance_void.py:86 已到达|exact assertion expression|
|83 `assert next_advance["limit_check"]["occupied_amount"] == 0`|tests/test_employee_advance_void.py::test_void_keeps_row_deletes_cost_releases_quota_and_never_recalculates @ test_employee_advance_void.py:88 已到达|exact assertion expression|
|84 `assert next_advance["limit_check"]["available_amount"] == 10000`|tests/test_employee_advance_void.py::test_void_keeps_row_deletes_cost_releases_quota_and_never_recalculates @ test_employee_advance_void.py:89 已到达|exact assertion expression|
|85 `assert await snapshot(factory) == old_salary`|tests/test_employee_advance_void.py::test_void_keeps_row_deletes_cost_releases_quota_and_never_recalculates @ test_employee_advance_void.py:90 已到达|exact assertion expression|

## 091 tests.test_employee_advance_void::test_real_full_and_partial_payroll_deductions_cannot_be_voided[1000-\u8be5\u9884\u652f\u5df2\u968f\u5de5\u8d44\u7ed3\u6e05 \u4e0d\u80fd\u4f5c\u5e9f]

当前 `tests/test_employee_advance_void.py::test_real_full_and_partial_payroll_deductions_cannot_be_voided[1000-\u8be5\u9884\u652f\u5df2\u968f\u5de5\u8d44\u7ed3\u6e05 \u4e0d\u80fd\u4f5c\u5e9f]`：**passed**；原失败调用行 183。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|180 `assert response.status_code == 400 and response.json()["detail"] == expected`|tests/test_employee_advance_void.py::test_real_full_and_partial_payroll_deductions_cannot_be_voided[1000-\u8be5\u9884\u652f\u5df2\u968f\u5de5\u8d44\u7ed3\u6e05 \u4e0d\u80fd\u4f5c\u5e9f] @ test_employee_advance_void.py:186 已到达|exact assertion expression|
|181 `assert await all_money(factory) == before`|tests/test_employee_advance_void.py::test_real_full_and_partial_payroll_deductions_cannot_be_voided[1000-\u8be5\u9884\u652f\u5df2\u968f\u5de5\u8d44\u7ed3\u6e05 \u4e0d\u80fd\u4f5c\u5e9f] @ test_employee_advance_void.py:187 已到达|exact assertion expression|

## 092 tests.test_employee_advance_void::test_real_full_and_partial_payroll_deductions_cannot_be_voided[2000-\u8be5\u9884\u652f\u5df2\u968f\u5de5\u8d44\u62b5\u6263 \u4e0d\u80fd\u4f5c\u5e9f]

当前 `tests/test_employee_advance_void.py::test_real_full_and_partial_payroll_deductions_cannot_be_voided[2000-\u8be5\u9884\u652f\u5df2\u968f\u5de5\u8d44\u62b5\u6263 \u4e0d\u80fd\u4f5c\u5e9f]`：**passed**；原失败调用行 183。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|180 `assert response.status_code == 400 and response.json()["detail"] == expected`|tests/test_employee_advance_void.py::test_real_full_and_partial_payroll_deductions_cannot_be_voided[2000-\u8be5\u9884\u652f\u5df2\u968f\u5de5\u8d44\u62b5\u6263 \u4e0d\u80fd\u4f5c\u5e9f] @ test_employee_advance_void.py:186 已到达|exact assertion expression|
|181 `assert await all_money(factory) == before`|tests/test_employee_advance_void.py::test_real_full_and_partial_payroll_deductions_cannot_be_voided[2000-\u8be5\u9884\u652f\u5df2\u968f\u5de5\u8d44\u62b5\u6263 \u4e0d\u80fd\u4f5c\u5e9f] @ test_employee_advance_void.py:187 已到达|exact assertion expression|

## 093 tests.test_employee_advance_void::test_void_transaction_rolls_back_cost_and_metadata_on_failure[expense_log]

当前 `tests/test_employee_advance_void.py::test_void_transaction_rolls_back_cost_and_metadata_on_failure[expense_log]`：**passed**；原失败调用行 216。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|214 `assert response.status_code == 500`|tests/test_employee_advance_void.py::test_void_transaction_rolls_back_cost_and_metadata_on_failure[expense_log] @ test_employee_advance_void.py:220 已到达|exact assertion expression|
|215 `assert await all_money(factory) == before`|tests/test_employee_advance_void.py::test_void_transaction_rolls_back_cost_and_metadata_on_failure[expense_log] @ test_employee_advance_void.py:221 已到达|exact assertion expression|

## 094 tests.test_cash_advance_repayments::test_full_repayment_money_ledger_and_costs_exactly_unchanged

当前 `tests/test_cash_advance_repayments.py::test_full_repayment_money_ledger_and_costs_exactly_unchanged`：**failed**；原失败调用行 115。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|84 `assert r.status_code == 200, r.text`|tests/test_cash_advance_repayments.py::test_full_repayment_money_ledger_and_costs_exactly_unchanged @ test_cash_advance_repayments.py:92 已到达|exact assertion expression|
|86 `assert data["repayment"]["amount"] == 3000 and data["repayment"]["account_id"] == 1 and data["repayment"]["status"] == "active"`|tests/test_cash_advance_repayments.py::test_full_repayment_money_ledger_and_costs_exactly_unchanged @ test_cash_advance_repayments.py:94 已到达|exact assertion expression|
|87 `assert data["advance"]["status"] == "repaid" and data["advance"]["repaid_amount"] == 3000 and data["advance"]["outstanding_amount"] == 0`|tests/test_cash_advance_repayments.py::test_full_repayment_money_ledger_and_costs_exactly_unchanged @ test_cash_advance_repayments.py:95 已到达|exact assertion expression|
|88 `assert data["account"]["current_balance"] == 7000`|tests/test_cash_advance_repayments.py::test_full_repayment_money_ledger_and_costs_exactly_unchanged @ test_cash_advance_repayments.py:96 已到达|exact assertion expression|
|90 `assert old_balance["current_balance"] == 10000 and after["current_balance"] == 7000`|tests/test_cash_advance_repayments.py::test_full_repayment_money_ledger_and_costs_exactly_unchanged @ test_cash_advance_repayments.py:98 已到达|exact assertion expression|
|91 `assert after["opening_balance"] == old_balance["opening_balance"] == 10000`|tests/test_cash_advance_repayments.py::test_full_repayment_money_ledger_and_costs_exactly_unchanged @ test_cash_advance_repayments.py:99 已到达|changed assertion; see old/new expressions and policy rationale|
|93 `assert flows["total"] == 1 and flows["total_expense"] == 3000 and len(flows["data"]) == 1`|tests/test_cash_advance_repayments.py::test_full_repayment_money_ledger_and_costs_exactly_unchanged @ test_cash_advance_repayments.py:101 已到达|exact assertion expression|
|94 `assert flows["data"][0]["amount"] == 3000 and flows["data"][0]["is_non_cost_flow"] is True`|tests/test_cash_advance_repayments.py::test_full_repayment_money_ledger_and_costs_exactly_unchanged @ test_cash_advance_repayments.py:103 已到达 / 行失败|exact assertion expression|
|95 `assert flows["data"][0]["remark"] == f"归还垫款 #{aid}" and flows["data"][0]["account_name"] == "测试现金"`|tests/test_cash_advance_repayments.py::test_full_repayment_money_ledger_and_costs_exactly_unchanged @ test_cash_advance_repayments.py:104 已到达|exact assertion expression|
|97 `assert same_day.status_code == 200 and same_day.json()["total"] == 1 and same_day.json()["total_expense"] == 3000`|tests/test_cash_advance_repayments.py::test_full_repayment_money_ledger_and_costs_exactly_unchanged @ test_cash_advance_repayments.py:106 已到达|exact assertion expression|
|98 `assert await cost_totals(c) == costs and await finance_snapshot(f) == before`|tests/test_cash_advance_repayments.py::test_full_repayment_money_ledger_and_costs_exactly_unchanged @ test_cash_advance_repayments.py:108 已到达 / 行失败|exact assertion expression|
|99 `assert (await c.get(URL + "/summary", headers=auth(1))).json()["total_outstanding"] == 0`|tests/test_cash_advance_repayments.py::test_full_repayment_money_ledger_and_costs_exactly_unchanged @ test_cash_advance_repayments.py:109 已到达|exact assertion expression|
|100 `assert (await c.get(URL + "/summary", headers=auth(1))).json()["payer_count"] == 0`|tests/test_cash_advance_repayments.py::test_full_repayment_money_ledger_and_costs_exactly_unchanged @ test_cash_advance_repayments.py:110 已到达|exact assertion expression|
|103 `assert retry.status_code == 200 and retry.json()["repayment"]["id"] == data["repayment"]["id"]`|tests/test_cash_advance_repayments.py::test_full_repayment_money_ledger_and_costs_exactly_unchanged @ test_cash_advance_repayments.py:113 已到达|exact assertion expression|
|104 `assert (await ledger(c))["total"] == 1`|tests/test_cash_advance_repayments.py::test_full_repayment_money_ledger_and_costs_exactly_unchanged @ test_cash_advance_repayments.py:114 已到达|exact assertion expression|
|106 `assert paid.status_code == 400 and paid.json()["detail"] == "该垫款单已还清"`|tests/test_cash_advance_repayments.py::test_full_repayment_money_ledger_and_costs_exactly_unchanged @ test_cash_advance_repayments.py:116 已到达|exact assertion expression|
|109 `assert len(logs) == 1 and logs[0].after_data["repayment"]["amount"] == 3000 and logs[0].operator_id == 1`|tests/test_cash_advance_repayments.py::test_full_repayment_money_ledger_and_costs_exactly_unchanged @ test_cash_advance_repayments.py:119 已到达|changed assertion; see old/new expressions and policy rationale|
|111 `assert report_expense == {"THB": 750}`|tests/test_cash_advance_repayments.py::test_full_repayment_money_ledger_and_costs_exactly_unchanged @ test_cash_advance_repayments.py:122 已到达|exact assertion expression|
|113 `assert counts["total"] == 2 and sum(x["amount"] for x in counts["data"]) == 750`|tests/test_cash_advance_repayments.py::test_full_repayment_money_ledger_and_costs_exactly_unchanged @ test_cash_advance_repayments.py:125 已到达|exact assertion expression|

## 095 tests.test_cash_advance_repayments::test_partial_repayment_reversal_keeps_voided_flow_and_restores_balance

当前 `tests/test_cash_advance_repayments.py::test_partial_repayment_reversal_keeps_voided_flow_and_restores_balance`：**passed**；原失败调用行 149。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|123 `assert r.status_code == 200, r.text`|tests/test_cash_advance_repayments.py::test_partial_repayment_reversal_keeps_voided_flow_and_restores_balance @ test_cash_advance_repayments.py:135 已到达|exact assertion expression|
|125 `assert part["advance"]["status"] == "confirmed" and part["advance"]["status_label"] == "部分归还" and part["advance"]["outstanding_amount"] == 2000`|tests/test_cash_advance_repayments.py::test_partial_repayment_reversal_keeps_voided_flow_and_restores_balance @ test_cash_advance_repayments.py:137 已到达|exact assertion expression|
|126 `assert part["account"]["current_balance"] == 9000`|tests/test_cash_advance_repayments.py::test_partial_repayment_reversal_keeps_voided_flow_and_restores_balance @ test_cash_advance_repayments.py:138 已到达|exact assertion expression|
|127 `assert (await ledger(c))["total_expense"] == 1000`|tests/test_cash_advance_repayments.py::test_partial_repayment_reversal_keeps_voided_flow_and_restores_balance @ test_cash_advance_repayments.py:139 已到达|exact assertion expression|
|128 `assert filtered.json()["total"] == 1`|tests/test_cash_advance_repayments.py::test_partial_repayment_reversal_keeps_voided_flow_and_restores_balance @ test_cash_advance_repayments.py:140 已到达|exact assertion expression|
|129 `assert (await c.get(URL + "/summary", headers=auth(1))).json()["total_outstanding"] == 2000`|tests/test_cash_advance_repayments.py::test_partial_repayment_reversal_keeps_voided_flow_and_restores_balance @ test_cash_advance_repayments.py:141 已到达|exact assertion expression|
|131 `assert r.status_code == 200, r.text`|tests/test_cash_advance_repayments.py::test_partial_repayment_reversal_keeps_voided_flow_and_restores_balance @ test_cash_advance_repayments.py:135 已到达|exact assertion expression|
|133 `assert revoked["advance"]["status"] == "confirmed" and revoked["advance"]["status_label"] == "已确认"`|tests/test_cash_advance_repayments.py::test_partial_repayment_reversal_keeps_voided_flow_and_restores_balance @ test_cash_advance_repayments.py:143 已到达|exact assertion expression|
|134 `assert revoked["advance"]["repaid_amount"] == 0 and revoked["advance"]["outstanding_amount"] == 3000`|tests/test_cash_advance_repayments.py::test_partial_repayment_reversal_keeps_voided_flow_and_restores_balance @ test_cash_advance_repayments.py:144 已到达|exact assertion expression|
|135 `assert revoked["account"]["current_balance"] == 10000`|tests/test_cash_advance_repayments.py::test_partial_repayment_reversal_keeps_voided_flow_and_restores_balance @ test_cash_advance_repayments.py:145 已到达|exact assertion expression|
|136 `assert revoked["repayment"]["status"] == "revoked" and revoked["repayment"]["revoked_by_id"] == 1 and revoked["repayment"]["revoked_at"]`|tests/test_cash_advance_repayments.py::test_partial_repayment_reversal_keeps_voided_flow_and_restores_balance @ test_cash_advance_repayments.py:146 已到达|exact assertion expression|
|138 `assert flows["total"] == 1 and flows["total_expense"] == 0 and flows["card_expense"] == 0`|tests/test_cash_advance_repayments.py::test_partial_repayment_reversal_keeps_voided_flow_and_restores_balance @ test_cash_advance_repayments.py:148 已到达|exact assertion expression|
|139 `assert flows["data"][0]["status_label"] == "已冲销" and "账户选错" in flows["data"][0]["remark"]`|tests/test_cash_advance_repayments.py::test_partial_repayment_reversal_keeps_voided_flow_and_restores_balance @ test_cash_advance_repayments.py:149 已到达|exact assertion expression|
|140 `assert await cost_totals(c) == costs and await finance_snapshot(f) == original`|tests/test_cash_advance_repayments.py::test_partial_repayment_reversal_keeps_voided_flow_and_restores_balance @ test_cash_advance_repayments.py:150 已到达|exact assertion expression|
|142 `assert history["total"] == 1 and history["active_count"] == 0 and history["data"][0]["status"] == "revoked"`|tests/test_cash_advance_repayments.py::test_partial_repayment_reversal_keeps_voided_flow_and_restores_balance @ test_cash_advance_repayments.py:152 已到达|exact assertion expression|
|144 `assert duplicate.status_code == 400 and duplicate.json()["detail"] == "该笔归还已撤销"`|tests/test_cash_advance_repayments.py::test_partial_repayment_reversal_keeps_voided_flow_and_restores_balance @ test_cash_advance_repayments.py:154 已到达|changed assertion; see old/new expressions and policy rationale|
|146 `assert retry.status_code == 400 and "已撤销" in retry.json()["detail"]`|tests/test_cash_advance_repayments.py::test_partial_repayment_reversal_keeps_voided_flow_and_restores_balance @ test_cash_advance_repayments.py:156 已到达|exact assertion expression|
|147 `assert (await balance(c))["current_balance"] == 10000`|tests/test_cash_advance_repayments.py::test_partial_repayment_reversal_keeps_voided_flow_and_restores_balance @ test_cash_advance_repayments.py:157 已到达|exact assertion expression|

## 096 tests.test_cash_advance_repayments::test_admin_only_repayment_upload_accounts_and_revoke[2]

当前 `tests/test_cash_advance_repayments.py::test_admin_only_repayment_upload_accounts_and_revoke[2]`：**passed**；原失败调用行 171。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|167 `assert r.status_code == 403 and r.json()["detail"] == "只有仓库管理员可以归还垫款", r.text`|tests/test_cash_advance_repayments.py::test_admin_only_repayment_upload_accounts_and_revoke[2] @ test_cash_advance_repayments.py:177 已到达; tests/test_cash_advance_repayments.py::test_admin_only_repayment_upload_accounts_and_revoke[2] @ test_cash_advance_repayments.py:181 已到达; tests/test_cash_advance_repayments.py::test_admin_only_repayment_upload_accounts_and_revoke[2] @ test_cash_advance_repayments.py:178 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|169 `assert listing.status_code == (200 if uid in (3, 4) else 403)`|tests/test_cash_advance_repayments.py::test_admin_only_repayment_upload_accounts_and_revoke[2] @ test_cash_advance_repayments.py:183 已到达|exact assertion expression|
|170 `assert (await balance(c))["current_balance"] == 9000`|tests/test_cash_advance_repayments.py::test_admin_only_repayment_upload_accounts_and_revoke[2] @ test_cash_advance_repayments.py:184 已到达|changed assertion; see old/new expressions and policy rationale|

## 097 tests.test_cash_advance_repayments::test_admin_only_repayment_upload_accounts_and_revoke[3]

当前 `tests/test_cash_advance_repayments.py::test_admin_only_repayment_upload_accounts_and_revoke[3]`：**passed**；原失败调用行 171。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|167 `assert r.status_code == 403 and r.json()["detail"] == "只有仓库管理员可以归还垫款", r.text`|tests/test_cash_advance_repayments.py::test_admin_only_repayment_upload_accounts_and_revoke[3] @ test_cash_advance_repayments.py:177 已到达; tests/test_cash_advance_repayments.py::test_admin_only_repayment_upload_accounts_and_revoke[3] @ test_cash_advance_repayments.py:181 未到达; tests/test_cash_advance_repayments.py::test_admin_only_repayment_upload_accounts_and_revoke[3] @ test_cash_advance_repayments.py:178 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|169 `assert listing.status_code == (200 if uid in (3, 4) else 403)`|tests/test_cash_advance_repayments.py::test_admin_only_repayment_upload_accounts_and_revoke[3] @ test_cash_advance_repayments.py:183 已到达|exact assertion expression|
|170 `assert (await balance(c))["current_balance"] == 9000`|tests/test_cash_advance_repayments.py::test_admin_only_repayment_upload_accounts_and_revoke[3] @ test_cash_advance_repayments.py:184 已到达|changed assertion; see old/new expressions and policy rationale|

## 098 tests.test_cash_advance_repayments::test_admin_only_repayment_upload_accounts_and_revoke[4]

当前 `tests/test_cash_advance_repayments.py::test_admin_only_repayment_upload_accounts_and_revoke[4]`：**passed**；原失败调用行 171。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|167 `assert r.status_code == 403 and r.json()["detail"] == "只有仓库管理员可以归还垫款", r.text`|tests/test_cash_advance_repayments.py::test_admin_only_repayment_upload_accounts_and_revoke[4] @ test_cash_advance_repayments.py:177 已到达; tests/test_cash_advance_repayments.py::test_admin_only_repayment_upload_accounts_and_revoke[4] @ test_cash_advance_repayments.py:181 已到达; tests/test_cash_advance_repayments.py::test_admin_only_repayment_upload_accounts_and_revoke[4] @ test_cash_advance_repayments.py:178 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|169 `assert listing.status_code == (200 if uid in (3, 4) else 403)`|tests/test_cash_advance_repayments.py::test_admin_only_repayment_upload_accounts_and_revoke[4] @ test_cash_advance_repayments.py:183 已到达|exact assertion expression|
|170 `assert (await balance(c))["current_balance"] == 9000`|tests/test_cash_advance_repayments.py::test_admin_only_repayment_upload_accounts_and_revoke[4] @ test_cash_advance_repayments.py:184 已到达|changed assertion; see old/new expressions and policy rationale|

## 099 tests.test_cash_advance_repayments::test_admin_only_repayment_upload_accounts_and_revoke[5]

当前 `tests/test_cash_advance_repayments.py::test_admin_only_repayment_upload_accounts_and_revoke[5]`：**passed**；原失败调用行 171。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|167 `assert r.status_code == 403 and r.json()["detail"] == "只有仓库管理员可以归还垫款", r.text`|tests/test_cash_advance_repayments.py::test_admin_only_repayment_upload_accounts_and_revoke[5] @ test_cash_advance_repayments.py:177 已到达; tests/test_cash_advance_repayments.py::test_admin_only_repayment_upload_accounts_and_revoke[5] @ test_cash_advance_repayments.py:181 已到达; tests/test_cash_advance_repayments.py::test_admin_only_repayment_upload_accounts_and_revoke[5] @ test_cash_advance_repayments.py:178 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|169 `assert listing.status_code == (200 if uid in (3, 4) else 403)`|tests/test_cash_advance_repayments.py::test_admin_only_repayment_upload_accounts_and_revoke[5] @ test_cash_advance_repayments.py:183 已到达|exact assertion expression|
|170 `assert (await balance(c))["current_balance"] == 9000`|tests/test_cash_advance_repayments.py::test_admin_only_repayment_upload_accounts_and_revoke[5] @ test_cash_advance_repayments.py:184 已到达|changed assertion; see old/new expressions and policy rationale|

## 100 tests.test_cash_advance_repayments::test_repayment_validation_no_partial_financial_writes[fields0-\u4e0d\u80fd\u8d85\u8fc7\u5269\u4f59\u672a\u8fd8]

当前 `tests/test_cash_advance_repayments.py::test_repayment_validation_no_partial_financial_writes[fields0-\u4e0d\u80fd\u8d85\u8fc7\u5269\u4f59\u672a\u8fd8]`：**passed**；原失败调用行 184。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|181 `assert r.status_code == 400 and r.json()["detail"] == message, r.text`|tests/test_cash_advance_repayments.py::test_repayment_validation_no_partial_financial_writes[fields0-\u4e0d\u80fd\u8d85\u8fc7\u5269\u4f59\u672a\u8fd8] @ test_cash_advance_repayments.py:195 已到达|exact assertion expression|
|182 `assert (await ledger(c))["total"] == 0 and (await balance(c))["current_balance"] == 10000`|tests/test_cash_advance_repayments.py::test_repayment_validation_no_partial_financial_writes[fields0-\u4e0d\u80fd\u8d85\u8fc7\u5269\u4f59\u672a\u8fd8] @ test_cash_advance_repayments.py:196 已到达|exact assertion expression|
|183 `assert await finance_snapshot(f) == before`|tests/test_cash_advance_repayments.py::test_repayment_validation_no_partial_financial_writes[fields0-\u4e0d\u80fd\u8d85\u8fc7\u5269\u4f59\u672a\u8fd8] @ test_cash_advance_repayments.py:197 已到达|exact assertion expression|

## 101 tests.test_cash_advance_repayments::test_repayment_validation_no_partial_financial_writes[fields1-\u8bf7\u9009\u62e9\u5f52\u8fd8\u8d26\u6237]

当前 `tests/test_cash_advance_repayments.py::test_repayment_validation_no_partial_financial_writes[fields1-\u8bf7\u9009\u62e9\u5f52\u8fd8\u8d26\u6237]`：**passed**；原失败调用行 184。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|181 `assert r.status_code == 400 and r.json()["detail"] == message, r.text`|tests/test_cash_advance_repayments.py::test_repayment_validation_no_partial_financial_writes[fields1-\u8bf7\u9009\u62e9\u5f52\u8fd8\u8d26\u6237] @ test_cash_advance_repayments.py:195 已到达|exact assertion expression|
|182 `assert (await ledger(c))["total"] == 0 and (await balance(c))["current_balance"] == 10000`|tests/test_cash_advance_repayments.py::test_repayment_validation_no_partial_financial_writes[fields1-\u8bf7\u9009\u62e9\u5f52\u8fd8\u8d26\u6237] @ test_cash_advance_repayments.py:196 已到达|exact assertion expression|
|183 `assert await finance_snapshot(f) == before`|tests/test_cash_advance_repayments.py::test_repayment_validation_no_partial_financial_writes[fields1-\u8bf7\u9009\u62e9\u5f52\u8fd8\u8d26\u6237] @ test_cash_advance_repayments.py:197 已到达|exact assertion expression|

## 102 tests.test_cash_advance_repayments::test_repayment_validation_no_partial_financial_writes[fields2-\u8bf7\u4e0a\u4f20\u5f52\u8fd8\u51ed\u8bc1\u7167\u7247]

当前 `tests/test_cash_advance_repayments.py::test_repayment_validation_no_partial_financial_writes[fields2-\u8bf7\u4e0a\u4f20\u5f52\u8fd8\u51ed\u8bc1\u7167\u7247]`：**passed**；原失败调用行 184。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|181 `assert r.status_code == 400 and r.json()["detail"] == message, r.text`|tests/test_cash_advance_repayments.py::test_repayment_validation_no_partial_financial_writes[fields2-\u8bf7\u4e0a\u4f20\u5f52\u8fd8\u51ed\u8bc1\u7167\u7247] @ test_cash_advance_repayments.py:195 已到达|exact assertion expression|
|182 `assert (await ledger(c))["total"] == 0 and (await balance(c))["current_balance"] == 10000`|tests/test_cash_advance_repayments.py::test_repayment_validation_no_partial_financial_writes[fields2-\u8bf7\u4e0a\u4f20\u5f52\u8fd8\u51ed\u8bc1\u7167\u7247] @ test_cash_advance_repayments.py:196 已到达|exact assertion expression|
|183 `assert await finance_snapshot(f) == before`|tests/test_cash_advance_repayments.py::test_repayment_validation_no_partial_financial_writes[fields2-\u8bf7\u4e0a\u4f20\u5f52\u8fd8\u51ed\u8bc1\u7167\u7247] @ test_cash_advance_repayments.py:197 已到达|exact assertion expression|

## 103 tests.test_cash_advance_repayments::test_repayment_validation_no_partial_financial_writes[fields3-\u8bf7\u4e0a\u4f20\u5f52\u8fd8\u51ed\u8bc1\u7167\u7247]

当前 `tests/test_cash_advance_repayments.py::test_repayment_validation_no_partial_financial_writes[fields3-\u8bf7\u4e0a\u4f20\u5f52\u8fd8\u51ed\u8bc1\u7167\u7247]`：**passed**；原失败调用行 184。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|181 `assert r.status_code == 400 and r.json()["detail"] == message, r.text`|tests/test_cash_advance_repayments.py::test_repayment_validation_no_partial_financial_writes[fields3-\u8bf7\u4e0a\u4f20\u5f52\u8fd8\u51ed\u8bc1\u7167\u7247] @ test_cash_advance_repayments.py:195 已到达|exact assertion expression|
|182 `assert (await ledger(c))["total"] == 0 and (await balance(c))["current_balance"] == 10000`|tests/test_cash_advance_repayments.py::test_repayment_validation_no_partial_financial_writes[fields3-\u8bf7\u4e0a\u4f20\u5f52\u8fd8\u51ed\u8bc1\u7167\u7247] @ test_cash_advance_repayments.py:196 已到达|exact assertion expression|
|183 `assert await finance_snapshot(f) == before`|tests/test_cash_advance_repayments.py::test_repayment_validation_no_partial_financial_writes[fields3-\u8bf7\u4e0a\u4f20\u5f52\u8fd8\u51ed\u8bc1\u7167\u7247] @ test_cash_advance_repayments.py:197 已到达|exact assertion expression|

## 104 tests.test_cash_advance_repayments::test_repayment_validation_no_partial_financial_writes[fields4-\u51ed\u8bc1\u7167\u7247\u4e0d\u5c5e\u4e8e\u5f53\u524d\u4ed3\u5e93\u7684\u57ab\u6b3e\u5355]

当前 `tests/test_cash_advance_repayments.py::test_repayment_validation_no_partial_financial_writes[fields4-\u51ed\u8bc1\u7167\u7247\u4e0d\u5c5e\u4e8e\u5f53\u524d\u4ed3\u5e93\u7684\u57ab\u6b3e\u5355]`：**passed**；原失败调用行 184。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|181 `assert r.status_code == 400 and r.json()["detail"] == message, r.text`|tests/test_cash_advance_repayments.py::test_repayment_validation_no_partial_financial_writes[fields4-\u51ed\u8bc1\u7167\u7247\u4e0d\u5c5e\u4e8e\u5f53\u524d\u4ed3\u5e93\u7684\u57ab\u6b3e\u5355] @ test_cash_advance_repayments.py:195 已到达|exact assertion expression|
|182 `assert (await ledger(c))["total"] == 0 and (await balance(c))["current_balance"] == 10000`|tests/test_cash_advance_repayments.py::test_repayment_validation_no_partial_financial_writes[fields4-\u51ed\u8bc1\u7167\u7247\u4e0d\u5c5e\u4e8e\u5f53\u524d\u4ed3\u5e93\u7684\u57ab\u6b3e\u5355] @ test_cash_advance_repayments.py:196 已到达|exact assertion expression|
|183 `assert await finance_snapshot(f) == before`|tests/test_cash_advance_repayments.py::test_repayment_validation_no_partial_financial_writes[fields4-\u51ed\u8bc1\u7167\u7247\u4e0d\u5c5e\u4e8e\u5f53\u524d\u4ed3\u5e93\u7684\u57ab\u6b3e\u5355] @ test_cash_advance_repayments.py:197 已到达|exact assertion expression|

## 105 tests.test_cash_advance_repayments::test_repayment_validation_no_partial_financial_writes[fields5-\u5f52\u8fd8\u51ed\u8bc1\u7167\u7247\u4e0d\u5b58\u5728\uff0c\u8bf7\u91cd\u65b0\u4e0a\u4f20]

当前 `tests/test_cash_advance_repayments.py::test_repayment_validation_no_partial_financial_writes[fields5-\u5f52\u8fd8\u51ed\u8bc1\u7167\u7247\u4e0d\u5b58\u5728\uff0c\u8bf7\u91cd\u65b0\u4e0a\u4f20]`：**passed**；原失败调用行 184。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|181 `assert r.status_code == 400 and r.json()["detail"] == message, r.text`|tests/test_cash_advance_repayments.py::test_repayment_validation_no_partial_financial_writes[fields5-\u5f52\u8fd8\u51ed\u8bc1\u7167\u7247\u4e0d\u5b58\u5728\uff0c\u8bf7\u91cd\u65b0\u4e0a\u4f20] @ test_cash_advance_repayments.py:195 已到达|exact assertion expression|
|182 `assert (await ledger(c))["total"] == 0 and (await balance(c))["current_balance"] == 10000`|tests/test_cash_advance_repayments.py::test_repayment_validation_no_partial_financial_writes[fields5-\u5f52\u8fd8\u51ed\u8bc1\u7167\u7247\u4e0d\u5b58\u5728\uff0c\u8bf7\u91cd\u65b0\u4e0a\u4f20] @ test_cash_advance_repayments.py:196 已到达|exact assertion expression|
|183 `assert await finance_snapshot(f) == before`|tests/test_cash_advance_repayments.py::test_repayment_validation_no_partial_financial_writes[fields5-\u5f52\u8fd8\u51ed\u8bc1\u7167\u7247\u4e0d\u5b58\u5728\uff0c\u8bf7\u91cd\u65b0\u4e0a\u4f20] @ test_cash_advance_repayments.py:197 已到达|exact assertion expression|

## 106 tests.test_cash_advance_repayments::test_pending_rejected_inactive_cross_warehouse_and_currency_are_blocked

当前 `tests/test_cash_advance_repayments.py::test_pending_rejected_inactive_cross_warehouse_and_currency_are_blocked`：**passed**；原失败调用行 209。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|193 `assert r.status_code == 400 and "不能归还" in r.json()["detail"]`|tests/test_cash_advance_repayments.py::test_pending_rejected_inactive_cross_warehouse_and_currency_are_blocked @ test_cash_advance_repayments.py:207 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|195 `assert (await repay(c, pending, path)).status_code == 400`|tests/test_cash_advance_repayments.py::test_pending_rejected_inactive_cross_warehouse_and_currency_are_blocked @ test_cash_advance_repayments.py:209 已到达|changed assertion; see old/new expressions and policy rationale|
|197 `assert (await repay(c, aid, path, account_id=2)).status_code == 400`|tests/test_cash_advance_repayments.py::test_pending_rejected_inactive_cross_warehouse_and_currency_are_blocked @ test_cash_advance_repayments.py:211 已到达|exact assertion expression|
|200 `assert r.status_code == 400 and r.json()["detail"] == "归还账户已停用"`|tests/test_cash_advance_repayments.py::test_pending_rejected_inactive_cross_warehouse_and_currency_are_blocked @ test_cash_advance_repayments.py:214 已到达|exact assertion expression|
|204 `assert r.status_code == 400 and "币种必须与垫款单一致" in r.json()["detail"]`|tests/test_cash_advance_repayments.py::test_pending_rejected_inactive_cross_warehouse_and_currency_are_blocked @ test_cash_advance_repayments.py:218 已到达|exact assertion expression|
|206 `assert r.status_code == 404`|tests/test_cash_advance_repayments.py::test_pending_rejected_inactive_cross_warehouse_and_currency_are_blocked @ test_cash_advance_repayments.py:220 已到达|exact assertion expression|
|207 `assert (await c.get(f"{URL}/{aid}/repayments", headers=auth(7))).status_code == 404`|tests/test_cash_advance_repayments.py::test_pending_rejected_inactive_cross_warehouse_and_currency_are_blocked @ test_cash_advance_repayments.py:221 已到达|exact assertion expression|
|208 `assert (await c.get(URL + "/repayment-accounts", headers=auth(7))).json()["data"][0]["id"] == 2`|tests/test_cash_advance_repayments.py::test_pending_rejected_inactive_cross_warehouse_and_currency_are_blocked @ test_cash_advance_repayments.py:222 已到达|exact assertion expression|

## 107 tests.test_cash_advance_repayments::test_full_reversal_inactive_account_and_multiple_payments

当前 `tests/test_cash_advance_repayments.py::test_full_reversal_inactive_account_and_multiple_payments`：**passed**；原失败调用行 226。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|219 `assert b["advance"]["status"] == "repaid" and b["account"]["current_balance"] == 7000`|tests/test_cash_advance_repayments.py::test_full_reversal_inactive_account_and_multiple_payments @ test_cash_advance_repayments.py:232 已到达|exact assertion expression|
|224 `assert r.status_code == 200 and r.json()["advance"]["status"] == "confirmed" and r.json()["advance"]["outstanding_amount"] == remaining and r.json()["account"]["current_balance"] == expected`|tests/test_cash_advance_repayments.py::test_full_reversal_inactive_account_and_multiple_payments @ test_cash_advance_repayments.py:237 已到达; tests/test_cash_advance_repayments.py::test_full_reversal_inactive_account_and_multiple_payments @ round3_flow_support.py:71 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|225 `assert (await ledger(c))["total_expense"] == 0`|tests/test_cash_advance_repayments.py::test_full_reversal_inactive_account_and_multiple_payments @ test_cash_advance_repayments.py:238 已到达|exact assertion expression|

## 108 tests.test_cash_advance_repayments::test_history_failure_rolls_back_repayment_and_revoke

当前 `tests/test_cash_advance_repayments.py::test_history_failure_rolls_back_repayment_and_revoke`：**passed**；原失败调用行 243。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|238 `assert (await repay(c, aid, path, amount="500")).status_code == 500`|tests/test_cash_advance_repayments.py::test_history_failure_rolls_back_repayment_and_revoke @ test_cash_advance_repayments.py:250 已到达|exact assertion expression|
|239 `assert (await c.post(f'{URL}/repayments/{row["repayment"]["id"]}/revoke', headers=auth(1), json={"reason": "回滚"})).status_code == 500`|tests/test_cash_advance_repayments.py::test_history_failure_rolls_back_repayment_and_revoke @ test_cash_advance_repayments.py:251 已到达|changed assertion; see old/new expressions and policy rationale|
|240 `assert (await ledger(c))["total_expense"] == 1000 and (await balance(c))["current_balance"] == 9000`|tests/test_cash_advance_repayments.py::test_history_failure_rolls_back_repayment_and_revoke @ test_cash_advance_repayments.py:252 已到达|exact assertion expression|
|241 `assert (await c.get(URL + "/summary", headers=auth(1))).json()["total_outstanding"] == 2000`|tests/test_cash_advance_repayments.py::test_history_failure_rolls_back_repayment_and_revoke @ test_cash_advance_repayments.py:253 已到达|exact assertion expression|
|242 `assert await finance_snapshot(f) == before`|tests/test_cash_advance_repayments.py::test_history_failure_rolls_back_repayment_and_revoke @ test_cash_advance_repayments.py:254 已到达|exact assertion expression|

## 109 tests.test_cash_advance_repayments::test_repayment_never_recalculates_and_manual_payroll_amount_stays_same

当前 `tests/test_cash_advance_repayments.py::test_repayment_never_recalculates_and_manual_payroll_amount_stays_same`：**passed**；原失败调用行 261。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|253 `assert old.net_pay == 800`|tests/test_cash_advance_repayments.py::test_repayment_never_recalculates_and_manual_payroll_amount_stays_same @ test_cash_advance_repayments.py:265 已到达|exact assertion expression|
|256 `assert (await repay(c, aid, path)).status_code == 200`|tests/test_cash_advance_repayments.py::test_repayment_never_recalculates_and_manual_payroll_amount_stays_same @ test_cash_advance_repayments.py:268 已到达|exact assertion expression|
|257 `assert await snapshot(f) == before`|tests/test_cash_advance_repayments.py::test_repayment_never_recalculates_and_manual_payroll_amount_stays_same @ test_cash_advance_repayments.py:269 已到达|exact assertion expression|
|259 `assert r.status_code == 200 and (await period_record(f)).net_pay == 800`|tests/test_cash_advance_repayments.py::test_repayment_never_recalculates_and_manual_payroll_amount_stays_same @ test_cash_advance_repayments.py:271 已到达|exact assertion expression|

## 110 tests.test_cash_advance_repayments::test_currency_is_explicit_account_must_match_and_summary_never_adds_currencies

当前 `tests/test_cash_advance_repayments.py::test_currency_is_explicit_account_must_match_and_summary_never_adds_currencies`：**failed**；原失败调用行 291。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|273 `assert summary["payer_count"] == 1 and len(summary["data"]) == 1`|tests/test_cash_advance_repayments.py::test_currency_is_explicit_account_must_match_and_summary_never_adds_currencies @ test_cash_advance_repayments.py:286 已到达|exact assertion expression|
|274 `assert summary["total_outstanding"] is None and summary["data"][0]["outstanding_amount"] is None`|tests/test_cash_advance_repayments.py::test_currency_is_explicit_account_must_match_and_summary_never_adds_currencies @ test_cash_advance_repayments.py:287 已到达|exact assertion expression|
|275 `assert summary["totals_by_currency"] == [{"currency": "CNY", "amount": 3000}, {"currency": "THB", "amount": 3000}]`|tests/test_cash_advance_repayments.py::test_currency_is_explicit_account_must_match_and_summary_never_adds_currencies @ test_cash_advance_repayments.py:288 已到达|exact assertion expression|
|278 `assert wrong.status_code == 400 and "币种必须与垫款单一致" in wrong.json()["detail"]`|tests/test_cash_advance_repayments.py::test_currency_is_explicit_account_must_match_and_summary_never_adds_currencies @ test_cash_advance_repayments.py:291 已到达|exact assertion expression|
|280 `assert paid.status_code == 200 and paid.json()["repayment"]["currency"] == "CNY" and paid.json()["repayment"]["payment_method"] == "transfer" and paid.json()["account"]["current_balance"] == 17000`|tests/test_cash_advance_repayments.py::test_currency_is_explicit_account_must_match_and_summary_never_adds_currencies @ test_cash_advance_repayments.py:293 已到达|exact assertion expression|
|281 `assert (await balance(c))["current_balance"] == 10000`|tests/test_cash_advance_repayments.py::test_currency_is_explicit_account_must_match_and_summary_never_adds_currencies @ test_cash_advance_repayments.py:294 已到达|exact assertion expression|
|284 `assert edit.status_code == 400 and "不能修改币种" in edit.json()["detail"]`|tests/test_cash_advance_repayments.py::test_currency_is_explicit_account_must_match_and_summary_never_adds_currencies @ test_cash_advance_repayments.py:297 已到达|exact assertion expression|
|286 `assert delete.status_code == 400 and "不能删除" in delete.json()["detail"]`|tests/test_cash_advance_repayments.py::test_currency_is_explicit_account_must_match_and_summary_never_adds_currencies @ test_cash_advance_repayments.py:299 已到达|exact assertion expression|
|288 `assert summary["totals_by_currency"] == [{"currency": "THB", "amount": 3000}]`|tests/test_cash_advance_repayments.py::test_currency_is_explicit_account_must_match_and_summary_never_adds_currencies @ test_cash_advance_repayments.py:301 已到达|exact assertion expression|
|289 `assert await cost_totals(c) == costs`|tests/test_cash_advance_repayments.py::test_currency_is_explicit_account_must_match_and_summary_never_adds_currencies @ test_cash_advance_repayments.py:303 已到达 / 行失败|exact assertion expression|

## 111 tests.test_cash_advance_repayments::test_invalid_money_does_not_change_balance_or_create_flows[0]

当前 `tests/test_cash_advance_repayments.py::test_invalid_money_does_not_change_balance_or_create_flows[0]`：**passed**；原失败调用行 301。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|299 `assert (await repay(c, aid, path, amount=amount)).status_code == 422`|tests/test_cash_advance_repayments.py::test_invalid_money_does_not_change_balance_or_create_flows[0] @ test_cash_advance_repayments.py:314 已到达|exact assertion expression|
|300 `assert (await ledger(c))["total"] == 0 and (await balance(c))["current_balance"] == 10000`|tests/test_cash_advance_repayments.py::test_invalid_money_does_not_change_balance_or_create_flows[0] @ test_cash_advance_repayments.py:315 已到达|exact assertion expression|

## 112 tests.test_cash_advance_repayments::test_invalid_money_does_not_change_balance_or_create_flows[-1]

当前 `tests/test_cash_advance_repayments.py::test_invalid_money_does_not_change_balance_or_create_flows[-1]`：**passed**；原失败调用行 301。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|299 `assert (await repay(c, aid, path, amount=amount)).status_code == 422`|tests/test_cash_advance_repayments.py::test_invalid_money_does_not_change_balance_or_create_flows[-1] @ test_cash_advance_repayments.py:314 已到达|exact assertion expression|
|300 `assert (await ledger(c))["total"] == 0 and (await balance(c))["current_balance"] == 10000`|tests/test_cash_advance_repayments.py::test_invalid_money_does_not_change_balance_or_create_flows[-1] @ test_cash_advance_repayments.py:315 已到达|exact assertion expression|

## 113 tests.test_cash_advance_repayments::test_invalid_money_does_not_change_balance_or_create_flows[NaN]

当前 `tests/test_cash_advance_repayments.py::test_invalid_money_does_not_change_balance_or_create_flows[NaN]`：**passed**；原失败调用行 301。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|299 `assert (await repay(c, aid, path, amount=amount)).status_code == 422`|tests/test_cash_advance_repayments.py::test_invalid_money_does_not_change_balance_or_create_flows[NaN] @ test_cash_advance_repayments.py:314 已到达|exact assertion expression|
|300 `assert (await ledger(c))["total"] == 0 and (await balance(c))["current_balance"] == 10000`|tests/test_cash_advance_repayments.py::test_invalid_money_does_not_change_balance_or_create_flows[NaN] @ test_cash_advance_repayments.py:315 已到达|exact assertion expression|

## 114 tests.test_cash_advance_repayments::test_invalid_money_does_not_change_balance_or_create_flows[Infinity]

当前 `tests/test_cash_advance_repayments.py::test_invalid_money_does_not_change_balance_or_create_flows[Infinity]`：**passed**；原失败调用行 301。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|299 `assert (await repay(c, aid, path, amount=amount)).status_code == 422`|tests/test_cash_advance_repayments.py::test_invalid_money_does_not_change_balance_or_create_flows[Infinity] @ test_cash_advance_repayments.py:314 已到达|exact assertion expression|
|300 `assert (await ledger(c))["total"] == 0 and (await balance(c))["current_balance"] == 10000`|tests/test_cash_advance_repayments.py::test_invalid_money_does_not_change_balance_or_create_flows[Infinity] @ test_cash_advance_repayments.py:315 已到达|exact assertion expression|

## 115 tests.test_cash_advance_repayments::test_invalid_money_does_not_change_balance_or_create_flows[1.001]

当前 `tests/test_cash_advance_repayments.py::test_invalid_money_does_not_change_balance_or_create_flows[1.001]`：**passed**；原失败调用行 301。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|299 `assert (await repay(c, aid, path, amount=amount)).status_code == 422`|tests/test_cash_advance_repayments.py::test_invalid_money_does_not_change_balance_or_create_flows[1.001] @ test_cash_advance_repayments.py:314 已到达|exact assertion expression|
|300 `assert (await ledger(c))["total"] == 0 and (await balance(c))["current_balance"] == 10000`|tests/test_cash_advance_repayments.py::test_invalid_money_does_not_change_balance_or_create_flows[1.001] @ test_cash_advance_repayments.py:315 已到达|exact assertion expression|

## 116 tests.test_cash_advance_documents::test_two_wages_difference_manual_status_detail_and_other_books_unchanged

当前 `tests/test_cash_advance_documents.py::test_two_wages_difference_manual_status_detail_and_other_books_unchanged`：**passed**；原失败调用行 79。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|49 `assert {r["document_id"] for r in choices["data"]} == {2,4}`|tests/test_cash_advance_documents.py::test_two_wages_difference_manual_status_detail_and_other_books_unchanged @ test_cash_advance_documents.py:50 已到达|exact assertion expression|
|50 `assert sum(r["amount"] for r in choices["data"]) == 7000`|tests/test_cash_advance_documents.py::test_two_wages_difference_manual_status_detail_and_other_books_unchanged @ test_cash_advance_documents.py:51 已到达|exact assertion expression|
|52 `assert r.status_code == 200, r.text`|tests/test_cash_advance_documents.py::test_two_wages_difference_manual_status_detail_and_other_books_unchanged @ test_cash_advance_documents.py:53 已到达|exact assertion expression|
|54 `assert made["status"] == "pending" and made["linked_documents_total"] == 7000`|tests/test_cash_advance_documents.py::test_two_wages_difference_manual_status_detail_and_other_books_unchanged @ test_cash_advance_documents.py:55 已到达|exact assertion expression|
|55 `assert {d["document_id"] for d in made["linked_documents"]} == {2,4}`|tests/test_cash_advance_documents.py::test_two_wages_difference_manual_status_detail_and_other_books_unchanged @ test_cash_advance_documents.py:56 已到达|exact assertion expression|
|56 `assert made["reviewed_by_id"] is None`|tests/test_cash_advance_documents.py::test_two_wages_difference_manual_status_detail_and_other_books_unchanged @ test_cash_advance_documents.py:57 已到达|exact assertion expression|
|58 `assert bad.status_code == 400 and "差额备注" in bad.json()["detail"]`|tests/test_cash_advance_documents.py::test_two_wages_difference_manual_status_detail_and_other_books_unchanged @ test_cash_advance_documents.py:59 已到达|exact assertion expression|
|60 `assert changed["amount"] == 6000 and changed["amount_difference_note"] == "差额1000另行结算"`|tests/test_cash_advance_documents.py::test_two_wages_difference_manual_status_detail_and_other_books_unchanged @ test_cash_advance_documents.py:61 已到达|exact assertion expression|
|62 `assert manual["status"] == "confirmed" and manual["linked_documents"] == []`|tests/test_cash_advance_documents.py::test_two_wages_difference_manual_status_detail_and_other_books_unchanged @ test_cash_advance_documents.py:63 已到达|changed assertion; see old/new expressions and policy rationale|
|63 `assert manual["reviewed_by_id"] == 1 and manual["reviewed_at"] == manual["created_at"]`|tests/test_cash_advance_documents.py::test_two_wages_difference_manual_status_detail_and_other_books_unchanged @ test_cash_advance_documents.py:64 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|65 `assert admin["status"] == "confirmed" and admin["outstanding_amount"] == 7000`|tests/test_cash_advance_documents.py::test_two_wages_difference_manual_status_detail_and_other_books_unchanged @ test_cash_advance_documents.py:66 已到达|changed assertion; see old/new expressions and policy rationale|
|66 `assert (await c.post(f'{URL}/{admin["id"]}/confirm', headers=auth(1))).status_code == 400`|tests/test_cash_advance_documents.py::test_two_wages_difference_manual_status_detail_and_other_books_unchanged @ test_cash_advance_documents.py:67 已到达|changed assertion; see old/new expressions and policy rationale|
|68 `assert next(r for r in listing if r["id"] == made["id"])["linked_documents_total"] == 7000`|tests/test_cash_advance_documents.py::test_two_wages_difference_manual_status_detail_and_other_books_unchanged @ test_cash_advance_documents.py:69 已到达|exact assertion expression|
|72 `assert detail.status_code == 200, detail.text`|tests/test_cash_advance_documents.py::test_two_wages_difference_manual_status_detail_and_other_books_unchanged @ test_cash_advance_documents.py:73 已到达|exact assertion expression|
|73 `assert data["current"]["document_id"] == link["document_id"]`|tests/test_cash_advance_documents.py::test_two_wages_difference_manual_status_detail_and_other_books_unchanged @ test_cash_advance_documents.py:74 已到达|exact assertion expression|
|74 `assert data["current"]["detail"]["disbursed"] is False`|tests/test_cash_advance_documents.py::test_two_wages_difference_manual_status_detail_and_other_books_unchanged @ test_cash_advance_documents.py:75 已到达|exact assertion expression|
|76 `assert await finance_snapshot(f) == before`|tests/test_cash_advance_documents.py::test_two_wages_difference_manual_status_detail_and_other_books_unchanged @ test_cash_advance_documents.py:77 已到达|exact assertion expression|

## 117 tests.test_cash_advance_documents::test_edit_pending_confirmed_permissions_and_warehouse

当前 `tests/test_cash_advance_documents.py::test_edit_pending_confirmed_permissions_and_warehouse`：**passed**；原失败调用行 148。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|131 `assert r.status_code==200 and r.json()["status"]=="pending" and r.json()["amount"]==6000, r.text`|tests/test_cash_advance_documents.py::test_edit_pending_confirmed_permissions_and_warehouse @ test_cash_advance_documents.py:132 已到达|exact assertion expression|
|132 `assert len(r.json()["linked_documents"])==2`|tests/test_cash_advance_documents.py::test_edit_pending_confirmed_permissions_and_warehouse @ test_cash_advance_documents.py:133 已到达|exact assertion expression|
|133 `assert (await c.put(f'{URL}/{pending["id"]}',headers=auth(1),json={**body,"amount_difference_note":None})).status_code==400`|tests/test_cash_advance_documents.py::test_edit_pending_confirmed_permissions_and_warehouse @ test_cash_advance_documents.py:134 已到达|exact assertion expression|
|135 `assert (await c.put(f'{URL}/{confirmed["id"]}',headers=auth(4),json=body)).status_code==400`|tests/test_cash_advance_documents.py::test_edit_pending_confirmed_permissions_and_warehouse @ test_cash_advance_documents.py:137 已到达|exact assertion expression|
|137 `assert r.status_code==200 and r.json()["status"]=="confirmed" and r.json()["reviewed_by_id"]==1`|tests/test_cash_advance_documents.py::test_edit_pending_confirmed_permissions_and_warehouse @ test_cash_advance_documents.py:139 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|139 `assert (await c.put(f'{URL}/{pending["id"]}',headers=auth(uid),json=body)).status_code==403`|tests/test_cash_advance_documents.py::test_edit_pending_confirmed_permissions_and_warehouse @ test_cash_advance_documents.py:141 已到达|exact assertion expression|
|140 `assert (await c.get(URL+"/document-options?document_type=payroll",headers=auth(uid))).status_code==403`|tests/test_cash_advance_documents.py::test_edit_pending_confirmed_permissions_and_warehouse @ test_cash_advance_documents.py:142 已到达|exact assertion expression|
|144 `assert (await c.put(f'{URL}/{pending["id"]}',headers=auth(7),json=body)).status_code==404`|tests/test_cash_advance_documents.py::test_edit_pending_confirmed_permissions_and_warehouse @ test_cash_advance_documents.py:148 已到达|exact assertion expression|
|146 `assert (await c.get(f'{URL}/{pending["id"]}/documents/{link["id"]}',headers=auth(7))).status_code==404`|tests/test_cash_advance_documents.py::test_edit_pending_confirmed_permissions_and_warehouse @ test_cash_advance_documents.py:150 已到达|exact assertion expression|
|147 `assert (await c.get(URL+"/document-options?document_type=payroll",headers=auth(7))).json()["data"]==[]`|tests/test_cash_advance_documents.py::test_edit_pending_confirmed_permissions_and_warehouse @ test_cash_advance_documents.py:151 已到达|exact assertion expression|

## 118 tests.test_round18_advance_review::test_admin_review_reject_state_guards_and_history

当前 `tests/test_round18_advance_review.py::test_admin_review_reject_state_guards_and_history`：**passed**；原失败调用行 49。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|34 `assert approved.status_code==200,approved.text`|tests/test_round18_advance_review.py::test_admin_review_reject_state_guards_and_history @ round3_flow_support.py:27 已到达; tests/test_round18_advance_review.py::test_admin_review_reject_state_guards_and_history @ round3_flow_support.py:58 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|35 `assert a['approval_status']=='approved' and a['reviewer_id']==1 and a['reviewed_at'] and a['reject_reason'] is None`|tests/test_round18_advance_review.py::test_admin_review_reject_state_guards_and_history @ test_round18_advance_review.py:36 已到达|changed assertion; see old/new expressions and policy rationale|
|36 `assert rejected.status_code==200,rejected.text`|tests/test_round18_advance_review.py::test_admin_review_reject_state_guards_and_history @ test_round18_advance_review.py:38 已到达|exact assertion expression|
|37 `assert b['approval_status']=='rejected' and b['reviewer_id']==1 and b['reviewed_at'] and b['reject_reason']=='不符合本次预支规则'`|tests/test_round18_advance_review.py::test_admin_review_reject_state_guards_and_history @ test_round18_advance_review.py:39 已到达|exact assertion expression|
|39 `assert r.status_code==400 and r.json()['detail']==message`|tests/test_round18_advance_review.py::test_admin_review_reject_state_guards_and_history @ test_round18_advance_review.py:41 已到达|exact assertion expression|
|40 `assert listing.status_code==200`|tests/test_round18_advance_review.py::test_admin_review_reject_state_guards_and_history @ test_round18_advance_review.py:42 已到达|exact assertion expression|
|41 `assert {x['approval_status'] for x in listing.json()['data']}=={'approved','rejected'}`|tests/test_round18_advance_review.py::test_admin_review_reject_state_guards_and_history @ test_round18_advance_review.py:43 已到达|exact assertion expression|
|42 `assert logs.status_code==200,logs.text`|tests/test_round18_advance_review.py::test_admin_review_reject_state_guards_and_history @ test_round18_advance_review.py:44 已到达|exact assertion expression|
|43 `assert logs.json()['total']==2`|tests/test_round18_advance_review.py::test_admin_review_reject_state_guards_and_history @ test_round18_advance_review.py:45 已到达|changed assertion; see old/new expressions and policy rationale|
|45 `assert h['operator_id']==1 and h['created_at'] and h['after_data']['amount']==100 and h['after_data']['reviewed_at']`|tests/test_round18_advance_review.py::test_admin_review_reject_state_guards_and_history @ test_round18_advance_review.py:51 已到达|exact assertion expression|
|46 `assert h['operation_type'] in ('approve','reject') and h['warehouse_id']==1`|tests/test_round18_advance_review.py::test_admin_review_reject_state_guards_and_history @ test_round18_advance_review.py:52 已到达|exact assertion expression|
|47 `assert await snapshot(factory)==old`|tests/test_round18_advance_review.py::test_admin_review_reject_state_guards_and_history @ test_round18_advance_review.py:53 已到达|exact assertion expression|

## 119 tests.test_round18_advance_review::test_pending_approved_manual_recalc_exactly_100_and_carry

当前 `tests/test_round18_advance_review.py::test_pending_approved_manual_recalc_exactly_100_and_carry`：**passed**；原失败调用行 127。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|113 `assert first.base_pay==800 and first.advance_deduction==0 and first.net_pay==800`|tests/test_round18_advance_review.py::test_pending_approved_manual_recalc_exactly_100_and_carry @ test_round18_advance_review.py:120 已到达|exact assertion expression|
|115 `assert r.status_code==200,r.text`|tests/test_round18_advance_review.py::test_pending_approved_manual_recalc_exactly_100_and_carry @ test_round18_advance_review.py:124 已到达; tests/test_round18_advance_review.py::test_pending_approved_manual_recalc_exactly_100_and_carry @ test_round18_advance_review.py:130 已到达|exact assertion expression|
|116 `assert await snapshot(factory)==saved`|tests/test_round18_advance_review.py::test_pending_approved_manual_recalc_exactly_100_and_carry @ test_round18_advance_review.py:123 已到达|exact assertion expression|
|117 `assert r.status_code==200,r.text`|tests/test_round18_advance_review.py::test_pending_approved_manual_recalc_exactly_100_and_carry @ test_round18_advance_review.py:124 已到达; tests/test_round18_advance_review.py::test_pending_approved_manual_recalc_exactly_100_and_carry @ test_round18_advance_review.py:130 已到达|exact assertion expression|
|119 `assert second.base_pay==800 and second.advance_deduction==100 and second.net_pay==700`|tests/test_round18_advance_review.py::test_pending_approved_manual_recalc_exactly_100_and_carry @ test_round18_advance_review.py:126 已到达|exact assertion expression|
|120 `assert first.net_pay-second.net_pay==100`|tests/test_round18_advance_review.py::test_pending_approved_manual_recalc_exactly_100_and_carry @ test_round18_advance_review.py:127 已到达|exact assertion expression|
|121 `assert (await get(factory,rejected))['deducted_amount']==0`|tests/test_round18_advance_review.py::test_pending_approved_manual_recalc_exactly_100_and_carry @ test_round18_advance_review.py:128 已到达|exact assertion expression|
|123 `assert r.status_code==200,r.text`|tests/test_round18_advance_review.py::test_pending_approved_manual_recalc_exactly_100_and_carry @ test_round18_advance_review.py:124 已到达; tests/test_round18_advance_review.py::test_pending_approved_manual_recalc_exactly_100_and_carry @ test_round18_advance_review.py:130 已到达|exact assertion expression|
|124 `assert (await period_record(factory)).net_pay==700`|tests/test_round18_advance_review.py::test_pending_approved_manual_recalc_exactly_100_and_carry @ test_round18_advance_review.py:131 已到达|exact assertion expression|
|125 `assert [row for row in current if row[0] in {x[0] for x in legacy}]==legacy`|tests/test_round18_advance_review.py::test_pending_approved_manual_recalc_exactly_100_and_carry @ test_round18_advance_review.py:132 已到达|exact assertion expression|

## 120 tests.test_round18_advance_review::test_review_history_failure_rolls_back

当前 `tests/test_round18_advance_review.py::test_review_history_failure_rolls_back`：**passed**；原失败调用行 156。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|154 `assert r.status_code==500,r.text`|tests/test_round18_advance_review.py::test_review_history_failure_rolls_back @ test_round18_advance_review.py:163 已到达|exact assertion expression|
|155 `assert await get(factory,aid)==before`|tests/test_round18_advance_review.py::test_review_history_failure_rolls_back @ test_round18_advance_review.py:164 已到达|exact assertion expression|

## 121 tests.test_round18_advance_review::test_supervisor_self_advance_end_to_end

当前 `tests/test_round18_advance_review.py::test_supervisor_self_advance_end_to_end`：**passed**；原失败调用行 199。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|191 `assert r.status_code==200 and r.json()['approval_status']=='pending',r.text`|tests/test_round18_advance_review.py::test_supervisor_self_advance_end_to_end @ test_round18_advance_review.py:200 已到达|exact assertion expression|
|193 `assert first.net_pay==800 and first.advance_deduction==0`|tests/test_round18_advance_review.py::test_supervisor_self_advance_end_to_end @ test_round18_advance_review.py:202 已到达|exact assertion expression|
|194 `assert denied.status_code==403`|tests/test_round18_advance_review.py::test_supervisor_self_advance_end_to_end @ test_round18_advance_review.py:203 已到达|exact assertion expression|
|195 `assert approved.status_code==200`|tests/test_round18_advance_review.py::test_supervisor_self_advance_end_to_end @ round3_flow_support.py:27 已到达; tests/test_round18_advance_review.py::test_supervisor_self_advance_end_to_end @ round3_flow_support.py:58 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|197 `assert r.status_code==200,r.text`|tests/test_round18_advance_review.py::test_supervisor_self_advance_end_to_end @ test_round18_advance_review.py:206 已到达|exact assertion expression|
|198 `assert second.net_pay==700 and second.advance_deduction==100`|tests/test_round18_advance_review.py::test_supervisor_self_advance_end_to_end @ test_round18_advance_review.py:207 已到达|exact assertion expression|

## 122 tests.test_advance_manager_recipients::test_options_auto_archive_reuse_and_labor

当前 `tests/test_advance_manager_recipients.py::test_options_auto_archive_reuse_and_labor`：**passed**；原失败调用行 73。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|41 `assert {x['value'] for x in choices} == {'employee:1', 'user:1', 'user:4'}`|tests/test_advance_manager_recipients.py::test_options_auto_archive_reuse_and_labor @ test_advance_manager_recipients.py:41 已到达|exact assertion expression|
|42 `assert next(x for x in choices if x['user_id'] == 4)['role_label'] == '主管'`|tests/test_advance_manager_recipients.py::test_options_auto_archive_reuse_and_labor @ test_advance_manager_recipients.py:42 已到达|exact assertion expression|
|43 `assert await employee_count(f) == initial`|tests/test_advance_manager_recipients.py::test_options_auto_archive_reuse_and_labor @ test_advance_manager_recipients.py:43 已到达|exact assertion expression|
|46 `assert first.status_code == 200 and first.json()['approval_status'] == 'approved', first.text`|tests/test_advance_manager_recipients.py::test_options_auto_archive_reuse_and_labor @ test_advance_manager_recipients.py:46 已到达|changed assertion; see old/new expressions and policy rationale|
|57 `assert actual['position']=='仓库主管' and actual['name']=='supervisor' and actual['employee_no']=='supervisor'`|tests/test_advance_manager_recipients.py::test_options_auto_archive_reuse_and_labor @ test_advance_manager_recipients.py:57 已到达|exact assertion expression|
|58 `assert actual['warehouse_id']==1 and actual['status']=='regular' and actual['hire_date']=='2026-10-17T00:00:00'`|tests/test_advance_manager_recipients.py::test_options_auto_archive_reuse_and_labor @ test_advance_manager_recipients.py:58 已到达|exact assertion expression|
|59 `assert emp.salary_template_id is emp.deduction_template_id is None`|tests/test_advance_manager_recipients.py::test_options_auto_archive_reuse_and_labor @ test_advance_manager_recipients.py:59 已到达|exact assertion expression|
|60 `assert not user.attendance_enabled and user.attendance_employee_id is None and user.attendance_enabled_at is None`|tests/test_advance_manager_recipients.py::test_options_auto_archive_reuse_and_labor @ test_advance_manager_recipients.py:60 已到达|exact assertion expression|
|61 `assert advance.employee_id==emp.id and advance.approval_status=='approved'`|tests/test_advance_manager_recipients.py::test_options_auto_archive_reuse_and_labor @ test_advance_manager_recipients.py:61 已到达|changed assertion; see old/new expressions and policy rationale|
|63 `assert (await db.execute(select(DataChangeHistory).where(DataChangeHistory.module=='employee',DataChangeHistory.record_id==eid))).scalar_one().after_data['source']=='employee_advances'`|tests/test_advance_manager_recipients.py::test_options_auto_archive_reuse_and_labor @ test_advance_manager_recipients.py:63 已到达|exact assertion expression|
|64 `assert second.status_code==200,second.text`|tests/test_advance_manager_recipients.py::test_options_auto_archive_reuse_and_labor @ test_advance_manager_recipients.py:64 已到达|exact assertion expression|
|65 `assert await employee_count(f)==initial+1`|tests/test_advance_manager_recipients.py::test_options_auto_archive_reuse_and_labor @ test_advance_manager_recipients.py:65 已到达|exact assertion expression|
|67 `assert sum(x['user_id']==4 for x in choices_after)==1`|tests/test_advance_manager_recipients.py::test_options_auto_archive_reuse_and_labor @ test_advance_manager_recipients.py:67 已到达|exact assertion expression|
|68 `assert next(x for x in choices_after if x['user_id']==4)['value']==f'employee:{eid}'`|tests/test_advance_manager_recipients.py::test_options_auto_archive_reuse_and_labor @ test_advance_manager_recipients.py:68 已到达|exact assertion expression|
|69 `assert third.status_code==200`|tests/test_advance_manager_recipients.py::test_options_auto_archive_reuse_and_labor @ test_advance_manager_recipients.py:69 已到达|exact assertion expression|
|70 `assert labor.status_code==200 and labor.json()['approval_status']=='approved'`|tests/test_advance_manager_recipients.py::test_options_auto_archive_reuse_and_labor @ test_advance_manager_recipients.py:70 已到达|changed assertion; see old/new expressions and policy rationale|
|71 `assert await snapshot(f)==old`|tests/test_advance_manager_recipients.py::test_options_auto_archive_reuse_and_labor @ test_advance_manager_recipients.py:71 已到达|exact assertion expression|

## 123 tests.test_advance_manager_recipients::test_existing_enabled_archive_and_self_approval_preserved

当前 `tests/test_advance_manager_recipients.py::test_existing_enabled_archive_and_self_approval_preserved`：**passed**；原失败调用行 90。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|80 `assert sum(x['user_id']==4 for x in opts)==1`|tests/test_advance_manager_recipients.py::test_existing_enabled_archive_and_self_approval_preserved @ test_advance_manager_recipients.py:80 已到达|exact assertion expression|
|81 `assert next(x for x in opts if x['user_id']==4)['value']=='employee:5'`|tests/test_advance_manager_recipients.py::test_existing_enabled_archive_and_self_approval_preserved @ test_advance_manager_recipients.py:81 已到达|exact assertion expression|
|82 `assert (await create(c,user_id=4)).status_code==200`|tests/test_advance_manager_recipients.py::test_existing_enabled_archive_and_self_approval_preserved @ test_advance_manager_recipients.py:82 已到达|exact assertion expression|
|84 `assert own.status_code==200 and own.json()['approval_status']=='pending'`|tests/test_advance_manager_recipients.py::test_existing_enabled_archive_and_self_approval_preserved @ test_advance_manager_recipients.py:84 已到达|exact assertion expression|
|85 `assert other.status_code==200 and other.json()['approval_status']=='approved'`|tests/test_advance_manager_recipients.py::test_existing_enabled_archive_and_self_approval_preserved @ test_advance_manager_recipients.py:85 已到达|changed assertion; see old/new expressions and policy rationale|
|86 `assert await employee_count(f)==initial`|tests/test_advance_manager_recipients.py::test_existing_enabled_archive_and_self_approval_preserved @ test_advance_manager_recipients.py:86 已到达|exact assertion expression|
|89 `assert u.attendance_enabled and u.attendance_employee_id==5 and e.salary_template_id==1 and e.deduction_template_id==1`|tests/test_advance_manager_recipients.py::test_existing_enabled_archive_and_self_approval_preserved @ test_advance_manager_recipients.py:89 已到达|exact assertion expression|

## 124 tests.test_advance_manager_recipients::test_recipient_role_and_warehouse_scope

当前 `tests/test_advance_manager_recipients.py::test_recipient_role_and_warehouse_scope`：**passed**；原失败调用行 153。

|原行及断言|当前行/实际执行|映射说明|
|---|---|---|
|146 `assert r.status_code==403`|tests/test_advance_manager_recipients.py::test_recipient_role_and_warehouse_scope @ test_advance_manager_recipients.py:149 已到达; tests/test_advance_manager_recipients.py::test_recipient_role_and_warehouse_scope @ test_advance_manager_recipients.py:146 已到达|exact assertion expression|
|148 `assert await options(c,uid)==await options(c)`|tests/test_advance_manager_recipients.py::test_recipient_role_and_warehouse_scope @ test_advance_manager_recipients.py:148 已到达|exact assertion expression|
|149 `assert r.status_code==403`|tests/test_advance_manager_recipients.py::test_recipient_role_and_warehouse_scope @ test_advance_manager_recipients.py:149 已到达; tests/test_advance_manager_recipients.py::test_recipient_role_and_warehouse_scope @ test_advance_manager_recipients.py:146 已到达|exact assertion expression|
|151 `assert r.status_code==200 and all(x['employee_id']!=2 for x in r.json()['data'])`|tests/test_advance_manager_recipients.py::test_recipient_role_and_warehouse_scope @ test_advance_manager_recipients.py:151 已到达|explicitly reviewed split/state/role/historical mapping; see CHANGE-RATIONALE.md|
|152 `assert r.status_code==200 and r.json()['approval_status']=='approved'`|tests/test_advance_manager_recipients.py::test_recipient_role_and_warehouse_scope @ test_advance_manager_recipients.py:152 已到达|changed assertion; see old/new expressions and policy rationale|
