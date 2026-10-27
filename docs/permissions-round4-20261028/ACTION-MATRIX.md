# 第四轮逐动作权限及证据索引

每一行一个注册方法/路径。详细输入字段、原守卫嵌套、服务位置和状态检查见同名JSON；未直接请求的项目不算通过。

|编号|模块/页面|方法与路径|角色上限|本轮请求数|
|---|---|---|---|---|
|R04-001|payment_accounts / 既有页面，见handler/source；本轮未逐按钮核验|POST /api/v1/accounts/transfers|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-002|payment_accounts / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/accounts|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-003|payment_accounts / 既有页面，见handler/source；本轮未逐按钮核验|POST /api/v1/accounts|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-004|payment_accounts / 既有页面，见handler/source；本轮未逐按钮核验|PUT /api/v1/accounts/{account_id}|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-005|payment_accounts / 既有页面，见handler/source；本轮未逐按钮核验|PUT /api/v1/accounts/{account_id}/toggle-status|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-006|payment_accounts / 既有页面，见handler/source；本轮未逐按钮核验|DELETE /api/v1/accounts/{account_id}|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-007|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-008|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|POST /api/v1/suppliers|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-009|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/purchase-match-policy|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-010|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|PUT /api/v1/suppliers/purchase-match-policy|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-011|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/categories|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-012|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|POST /api/v1/suppliers/categories|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-013|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/import-template/products|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-014|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/import-template/logistics|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-015|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|POST /api/v1/suppliers/import/products|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-016|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|POST /api/v1/suppliers/import/logistics|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-017|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/price-threshold|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-018|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|PUT /api/v1/suppliers/price-threshold|保留前轮专用规则守卫并增加变更审计|0|
|R04-019|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/price-stats|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-020|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/price-trend|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-021|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/price-anomalies|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-022|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/non-lowest-records|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-023|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/non-lowest-summary|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-024|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/purchase-approval-threshold|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-025|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|PUT /api/v1/suppliers/purchase-approval-threshold|保留前轮专用规则守卫并增加变更审计|0|
|R04-026|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/purchase-approvals|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-027|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|PUT /api/v1/suppliers/purchase-approvals/{po_id}/approve|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-028|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|PUT /api/v1/suppliers/purchase-approvals/{po_id}/reject|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-029|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/purchase-orders|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-030|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/purchase-orders/{po_id}|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-031|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/purchase-orders/{po_id}/receipts/{event_id}/photo|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-032|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|POST /api/v1/suppliers/purchase-orders/{po_id}/receive|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-033|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|POST /api/v1/suppliers/purchase-orders/{po_id}/mark-sent|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-034|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|POST /api/v1/suppliers/purchase-orders/{po_id}/receipt|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-035|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|POST /api/v1/suppliers/purchase-orders/{po_id}/mark-shipped|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-036|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/purchase-orders/{po_id}/pdf|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-037|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/purchase-receipt-discrepancies|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-038|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/concentration-threshold|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-039|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|PUT /api/v1/suppliers/concentration-threshold|保留前轮专用规则守卫并增加变更审计|0|
|R04-040|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/concentration|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-041|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/concentration-trend|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-042|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/compare-prices|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-043|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/compare-logistics|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-044|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|POST /api/v1/suppliers/ai-compare|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-045|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/procurement-summary|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-046|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|POST /api/v1/suppliers/{supplier_id}/import/products|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-047|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|POST /api/v1/suppliers/{supplier_id}/import/logistics|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-048|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/{supplier_id}/products|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-049|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|POST /api/v1/suppliers/{supplier_id}/products|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-050|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|DELETE /api/v1/suppliers/{supplier_id}/products/{product_id}|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-051|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|POST /api/v1/suppliers/{supplier_id}/purchase-order|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-052|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/{supplier_id}/logistics-prices|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-053|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|POST /api/v1/suppliers/{supplier_id}/logistics-prices|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-054|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|DELETE /api/v1/suppliers/{supplier_id}/logistics-prices/{price_id}|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-055|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|PUT /api/v1/suppliers/{supplier_id}|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-056|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|DELETE /api/v1/suppliers/{supplier_id}|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-057|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/{supplier_id}|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-058|suppliers / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/suppliers/{supplier_id}/ai-evaluation|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-059|incoming / /incoming|GET /api/v1/incoming|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-060|incoming / /incoming|POST /api/v1/incoming|主管禁止；财务/仓库管理员仍须原菜单、对象和状态守卫|6|
|R04-061|incoming / /incoming|GET /api/v1/incoming/by-request/{request_key}|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-062|incoming / /incoming|POST /api/v1/incoming/{incoming_id}/screenshot|主管禁止；财务/仓库管理员仍须原菜单、对象和状态守卫|0|
|R04-063|incoming / /incoming|GET /api/v1/incoming/{incoming_id}/screenshot|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-064|incoming / /incoming|POST /api/v1/incoming/batch-import|主管禁止；财务/仓库管理员仍须原菜单、对象和状态守卫|5|
|R04-065|incoming / /incoming|POST /api/v1/incoming/import-excel|主管禁止；财务/仓库管理员仍须原菜单、对象和状态守卫|0|
|R04-066|incoming / /incoming|GET /api/v1/incoming/template|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-067|reconciliation / /reconciliation|GET /api/v1/reconciliation/unmatched|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-068|reconciliation / /reconciliation|POST /api/v1/reconciliation/manual-match|主管禁止；财务/仓库管理员仍须原菜单、对象和状态守卫|6|
|R04-069|reconciliation / /reconciliation|POST /api/v1/reconciliation/unmatch|主管禁止；财务/仓库管理员仍须原菜单、对象和状态守卫|4|
|R04-070|reconciliation / /reconciliation|GET /api/v1/reconciliation/results|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-071|reconciliation / /reconciliation|GET /api/v1/reconciliation/export|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-072|income_expense / /operating; /other-income-expense|GET /api/v1/income-expense/categories|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-073|income_expense / /operating; /other-income-expense|POST /api/v1/income-expense/categories|主管禁止；财务/仓库管理员仍须原菜单、对象和状态守卫|4|
|R04-074|income_expense / /operating; /other-income-expense|GET /api/v1/income-expense/income|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-075|income_expense / /operating; /other-income-expense|POST /api/v1/income-expense/income|主管禁止；财务/仓库管理员仍须原菜单、对象和状态守卫|9|
|R04-076|income_expense / /operating; /other-income-expense|PUT /api/v1/income-expense/income/{income_id}|主管禁止；财务/仓库管理员仍须原菜单、对象和状态守卫|5|
|R04-077|income_expense / /operating; /other-income-expense|DELETE /api/v1/income-expense/income/{income_id}|主管禁止；财务/仓库管理员仍须原菜单、对象和状态守卫|5|
|R04-078|income_expense / /operating; /other-income-expense|GET /api/v1/income-expense/expense|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-079|income_expense / /operating; /other-income-expense|GET /api/v1/income-expense/expense/export|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-080|income_expense / /operating; /other-income-expense|POST /api/v1/income-expense/expense|主管禁止；财务/仓库管理员仍须原菜单、对象和状态守卫|4|
|R04-081|income_expense / /operating; /other-income-expense|PUT /api/v1/income-expense/expense/{expense_id}|主管禁止；财务/仓库管理员仍须原菜单、对象和状态守卫|3|
|R04-082|income_expense / /operating; /other-income-expense|DELETE /api/v1/income-expense/expense/{expense_id}|主管禁止；财务/仓库管理员仍须原菜单、对象和状态守卫|3|
|R04-083|income_expense / /operating; /other-income-expense|GET /api/v1/income-expense/ledger|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-084|income_expense / /operating; /other-income-expense|GET /api/v1/income-expense/ledger/export|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-085|income_expense / /operating; /other-income-expense|GET /api/v1/income-expense/income/export|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-086|income_expense / /operating; /other-income-expense|GET /api/v1/income-expense/monthly-summary|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-087|income_expense / /operating; /other-income-expense|GET /api/v1/income-expense/operating-dashboard|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-088|expense_fund / /expense-fund; /my-requests|POST /api/v1/expense-fund/accounts|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-089|expense_fund / /expense-fund; /my-requests|GET /api/v1/expense-fund/employees|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-090|expense_fund / /expense-fund; /my-requests|GET /api/v1/expense-fund/accounts|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|5|
|R04-091|expense_fund / /expense-fund; /my-requests|GET /api/v1/expense-fund/payment-accounts|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-092|expense_fund / /expense-fund; /my-requests|GET /api/v1/expense-fund/accounts/{account_id}/disbursements|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-093|expense_fund / /expense-fund; /my-requests|POST /api/v1/expense-fund/accounts/{account_id}/topup|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-094|expense_fund / /expense-fund; /my-requests|GET /api/v1/expense-fund/accounts/{account_id}/items|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|1|
|R04-095|expense_fund / /expense-fund; /my-requests|PUT /api/v1/expense-fund/accounts/{account_id}/items/{item_id}|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-096|expense_fund / /expense-fund; /my-requests|DELETE /api/v1/expense-fund/accounts/{account_id}/items/{item_id}|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-097|expense_fund / /expense-fund; /my-requests|POST /api/v1/expense-fund/accounts/{account_id}/items|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|2|
|R04-098|expense_fund / /expense-fund; /my-requests|POST /api/v1/expense-fund/accounts/{account_id}/upload-receipt|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|1|
|R04-099|expense_fund / /expense-fund; /my-requests|POST /api/v1/expense-fund/accounts/{account_id}/items/{item_id}/upload-receipt|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-100|expense_fund / /expense-fund; /my-requests|GET /api/v1/expense-fund/review/pending|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-101|expense_fund / /expense-fund; /my-requests|POST /api/v1/expense-fund/review/batch|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-102|expense_fund / /expense-fund; /my-requests|POST /api/v1/expense-fund/recharge/request|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|1|
|R04-103|expense_fund / /expense-fund; /my-requests|GET /api/v1/expense-fund/recharge/requests|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-104|expense_fund / /expense-fund; /my-requests|POST /api/v1/expense-fund/recharge/review|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-105|expense_fund / /expense-fund; /my-requests|POST /api/v1/expense-fund/recharge/execute|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-106|expense_fund / /expense-fund; /my-requests|GET /api/v1/expense-fund/settings|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-107|expense_fund / /expense-fund; /my-requests|POST /api/v1/expense-fund/settings|保留前轮专用规则守卫并增加变更审计|13|
|R04-108|expense_fund / /expense-fund; /my-requests|GET /api/v1/expense-fund/balance|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-109|expense_fund / /expense-fund; /my-requests|GET /api/v1/expense-fund/alert|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-110|reimbursement / /reimbursement; /my-requests|GET /api/v1/reimbursement/payment-sources|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-111|reimbursement / /reimbursement; /my-requests|POST /api/v1/reimbursement/payment-voucher|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-112|reimbursement / /reimbursement; /my-requests|GET /api/v1/reimbursement|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|5|
|R04-113|reimbursement / /reimbursement; /my-requests|POST /api/v1/reimbursement|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|4|
|R04-114|reimbursement / /reimbursement; /my-requests|GET /api/v1/reimbursement/export|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-115|reimbursement / /reimbursement; /my-requests|GET /api/v1/reimbursement/categories|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-116|reimbursement / /reimbursement; /my-requests|GET /api/v1/reimbursement/{reimb_id}|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|1|
|R04-117|reimbursement / /reimbursement; /my-requests|PUT /api/v1/reimbursement/{reimb_id}|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-118|reimbursement / /reimbursement; /my-requests|DELETE /api/v1/reimbursement/{reimb_id}|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-119|reimbursement / /reimbursement; /my-requests|POST /api/v1/reimbursement/{reimb_id}/submit|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-120|reimbursement / /reimbursement; /my-requests|POST /api/v1/reimbursement/{reimb_id}/verify|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|1|
|R04-121|reimbursement / /reimbursement; /my-requests|POST /api/v1/reimbursement/{reimb_id}/return-to-draft|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-122|reimbursement / /reimbursement; /my-requests|POST /api/v1/reimbursement/{reimb_id}/review|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-123|reimbursement / /reimbursement; /my-requests|POST /api/v1/reimbursement/{reimb_id}/pay|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-124|reimbursement / /reimbursement; /my-requests|GET /api/v1/reimbursement/{reimb_id}/payments|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-125|reimbursement / /reimbursement; /my-requests|POST /api/v1/reimbursement/{reimb_id}/revoke-payment|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-126|reimbursement / /reimbursement; /my-requests|POST /api/v1/reimbursement/categories|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-127|config_api / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/config/attendance-times|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-128|config_api / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/config/work-schedule|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-129|config_api / 既有页面，见handler/source；本轮未逐按钮核验|PUT /api/v1/config/work-schedule|保留前轮专用规则守卫并增加变更审计|0|
|R04-130|exchange_rates / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/rates|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-131|exchange_rates / 既有页面，见handler/source；本轮未逐按钮核验|POST /api/v1/rates|仅授权仓库管理员；财务/主管禁止|0|
|R04-132|exchange_rates / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/rates/query|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-133|employees / /employees|GET /api/v1/employees/max-limit|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-134|employees / /employees|PUT /api/v1/employees/max-limit|仅授权仓库管理员；财务/主管禁止|6|
|R04-135|employees / /employees|GET /api/v1/employees|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-136|employees / /employees|POST /api/v1/employees|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|0|
|R04-137|employees / /employees|PUT /api/v1/employees/{employee_id}|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|57|
|R04-138|employees / /employees|POST /api/v1/employees/{employee_id}/resign|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|2|
|R04-139|employees / /employees|DELETE /api/v1/employees/{employee_id}|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|0|
|R04-140|employees / /employees|POST /api/v1/employees/bind-existing-accounts|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|0|
|R04-141|employees / /employees|POST /api/v1/employees/batch-set-templates|仅授权仓库管理员；财务/主管禁止|7|
|R04-142|employees / /employees|POST /api/v1/employees/{employee_id}/photo|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|0|
|R04-143|employees / /employees|POST /api/v1/employees/{employee_id}/passport-photo|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|0|
|R04-144|employees / /employees|POST /api/v1/employees/{employee_id}/work-permit-photo|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|0|
|R04-145|employees / /employees|GET /api/v1/employees/{employee_id}/summary|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-146|clock_in / /clock-in; /attendance|POST /api/v1/clock-in|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|6|
|R04-147|clock_in / /clock-in; /attendance|GET /api/v1/clock-in/today|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|12|
|R04-148|clock_in / /clock-in; /attendance|GET /api/v1/clock-in/records|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-149|clock_in / /clock-in; /attendance|POST /api/v1/clock-in/makeup|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|3|
|R04-150|clock_in / /clock-in; /attendance|POST /api/v1/clock-in/batch-makeup|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|0|
|R04-151|clock_in / /clock-in; /attendance|GET /api/v1/clock-in/makeup-batches|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-152|clock_in / /clock-in; /attendance|POST /api/v1/clock-in/makeup-batches/{batch_id}/revoke|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|0|
|R04-153|clock_in / /clock-in; /attendance|GET /api/v1/clock-in/makeup-count|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-154|clock_in / /clock-in; /attendance|GET /api/v1/clock-in/records/export|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-155|clock_in / /clock-in; /attendance|GET /api/v1/clock-in/photos|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-156|clock_in / /clock-in; /attendance|POST /api/v1/clock-in/makeup-requests|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|2|
|R04-157|clock_in / /clock-in; /attendance|GET /api/v1/clock-in/makeup-requests|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-158|clock_in / /clock-in; /attendance|POST /api/v1/clock-in/makeup-requests/{request_id}/approve|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|6|
|R04-159|attendance / /attendance; /my-leave; /my-attendance|POST /api/v1/attendance/leaves|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|10|
|R04-160|attendance / /attendance; /my-leave; /my-attendance|POST /api/v1/attendance/leaves/admin-record|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|2|
|R04-161|attendance / /attendance; /my-leave; /my-attendance|GET /api/v1/attendance/leaves|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|5|
|R04-162|attendance / /attendance; /my-leave; /my-attendance|PUT /api/v1/attendance/leaves/{leave_id}/approve|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|8|
|R04-163|attendance / /attendance; /my-leave; /my-attendance|PUT /api/v1/attendance/leaves/{leave_id}/reject|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|2|
|R04-164|attendance / /attendance; /my-leave; /my-attendance|POST /api/v1/attendance/rest-days|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|0|
|R04-165|attendance / /attendance; /my-leave; /my-attendance|GET /api/v1/attendance/rest-days|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-166|attendance / /attendance; /my-leave; /my-attendance|DELETE /api/v1/attendance/rest-days/{rest_day_id}|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|0|
|R04-167|attendance / /attendance; /my-leave; /my-attendance|POST /api/v1/attendance/absences|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|0|
|R04-168|attendance / /attendance; /my-leave; /my-attendance|DELETE /api/v1/attendance/absences/{absence_id}|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|0|
|R04-169|attendance / /attendance; /my-leave; /my-attendance|GET /api/v1/attendance/calendar|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-170|overtime / /overtime; /my-overtime|POST /api/v1/overtime|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|0|
|R04-171|overtime / /overtime; /my-overtime|POST /api/v1/overtime/{task_id}/verify|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|3|
|R04-172|overtime / /overtime; /my-overtime|POST /api/v1/overtime/{overtime_id}/confirm|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|1|
|R04-173|overtime / /overtime; /my-overtime|POST /api/v1/overtime/{task_id}/dispute|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|0|
|R04-174|overtime / /overtime; /my-overtime|GET /api/v1/overtime|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-175|overtime / /overtime; /my-overtime|GET /api/v1/overtime/pending|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-176|overtime / /overtime; /my-overtime|GET /api/v1/overtime/monthly-hours|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-177|overtime / /overtime; /my-overtime|GET /api/v1/overtime/limit|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-178|overtime / /overtime; /my-overtime|PUT /api/v1/overtime/limit|保留前轮专用规则守卫并增加变更审计|0|
|R04-179|overtime / /overtime; /my-overtime|DELETE /api/v1/overtime/{overtime_id}|保留现场职责；敏感员工字段仅管理员；本人审批由独立人员；有效本人绑定自助|0|
|R04-180|payroll / /payroll; /my-payslip|POST /api/v1/payroll/calculate|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-181|payroll / /payroll; /my-payslip|POST /api/v1/payroll/preview|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-182|payroll / /payroll; /my-payslip|POST /api/v1/payroll/single-settle|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-183|payroll / /payroll; /my-payslip|GET /api/v1/payroll|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-184|payroll / /payroll; /my-payslip|GET /api/v1/payroll/summary|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-185|payroll / /payroll; /my-payslip|GET /api/v1/payroll/export|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-186|payroll / /payroll; /my-payslip|POST /api/v1/payroll/{record_id}/confirm|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-187|payroll / /payroll; /my-payslip|POST /api/v1/payroll/confirm-all|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-188|payroll / /payroll; /my-payslip|POST /api/v1/payroll/batch-confirm|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-189|payroll / /payroll; /my-payslip|GET /api/v1/payroll/cash-advance-sources|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-190|payroll / /payroll; /my-payslip|POST /api/v1/payroll/batch-disburse|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-191|payroll / /payroll; /my-payslip|POST /api/v1/payroll/batch-delete|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-192|payroll / /payroll; /my-payslip|POST /api/v1/payroll/{record_id}/recalc|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-193|payroll / /payroll; /my-payslip|POST /api/v1/payroll/batch-recalc|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-194|payroll / /payroll; /my-payslip|DELETE /api/v1/payroll/{record_id}|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-195|payroll / /payroll; /my-payslip|DELETE /api/v1/payroll/period/{period}|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-196|payroll / /payroll; /my-payslip|POST /api/v1/payroll/{record_id}/disburse|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-197|payroll / /payroll; /my-payslip|POST /api/v1/payroll/{record_id}/revoke-disbursement|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-198|payroll / /payroll; /my-payslip|GET /api/v1/payroll/pending-resignations|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-199|payroll / /payroll; /my-payslip|GET /api/v1/payroll/my-payslip|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|14|
|R04-200|payroll / /payroll; /my-payslip|GET /api/v1/payroll/settlement-progress|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-201|payroll / /payroll; /my-payslip|GET /api/v1/payroll/{record_id}|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|14|
|R04-202|employee_advance / /employee-advances; /my-requests|POST /api/v1/employee-advances|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|4|
|R04-203|employee_advance / /employee-advances; /my-requests|GET /api/v1/employee-advances/funding-options|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|1|
|R04-204|employee_advance / /employee-advances; /my-requests|GET /api/v1/employee-advances/recipients|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-205|employee_advance / /employee-advances; /my-requests|GET /api/v1/employee-advances|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-206|employee_advance / /employee-advances; /my-requests|GET /api/v1/employee-advances/summary|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-207|employee_advance / /employee-advances; /my-requests|GET /api/v1/employee-advances/my-debt|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|5|
|R04-208|employee_advance / /employee-advances; /my-requests|DELETE /api/v1/employee-advances/{advance_id}|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-209|employee_advance / /employee-advances; /my-requests|POST /api/v1/employee-advances/{advance_id}/approve|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-210|employee_advance / /employee-advances; /my-requests|POST /api/v1/employee-advances/{advance_id}/reject|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-211|employee_advance / /employee-advances; /my-requests|GET /api/v1/employee-advances/{advance_id}|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|6|
|R04-212|employee_advance / /employee-advances; /my-requests|POST /api/v1/employee-advances/{advance_id}/verify|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-213|employee_advance / /employee-advances; /my-requests|POST /api/v1/employee-advances/{advance_id}/execute|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-214|salary_template / /salary-templates|GET /api/v1/salary-templates|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-215|salary_template / /salary-templates|POST /api/v1/salary-templates|仅授权仓库管理员；财务/主管禁止|6|
|R04-216|salary_template / /salary-templates|PUT /api/v1/salary-templates/{template_id}|仅授权仓库管理员；财务/主管禁止|10|
|R04-217|salary_template / /salary-templates|DELETE /api/v1/salary-templates/{template_id}|仅授权仓库管理员；财务/主管禁止|6|
|R04-218|deduction_template / /deduction-templates|GET /api/v1/deduction-templates|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-219|deduction_template / /deduction-templates|POST /api/v1/deduction-templates|仅授权仓库管理员；财务/主管禁止|6|
|R04-220|deduction_template / /deduction-templates|PUT /api/v1/deduction-templates/{template_id}|仅授权仓库管理员；财务/主管禁止|0|
|R04-221|deduction_template / /deduction-templates|DELETE /api/v1/deduction-templates/{template_id}|仅授权仓库管理员；财务/主管禁止|0|
|R04-222|employee_deduction / /employee-deductions|POST /api/v1/employee-deductions|仅授权仓库管理员；财务/主管禁止|6|
|R04-223|employee_deduction / /employee-deductions|GET /api/v1/employee-deductions|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-224|employee_deduction / /employee-deductions|DELETE /api/v1/employee-deductions/{deduction_id}|仅授权仓库管理员；财务/主管禁止|0|
|R04-225|employee_deduction / /employee-deductions|GET /api/v1/employee-deductions/fixed|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-226|employee_deduction / /employee-deductions|POST /api/v1/employee-deductions/fixed|仅授权仓库管理员；财务/主管禁止|0|
|R04-227|employee_deduction / /employee-deductions|PUT /api/v1/employee-deductions/fixed/{deduction_id}|仅授权仓库管理员；财务/主管禁止|0|
|R04-228|employee_deduction / /employee-deductions|DELETE /api/v1/employee-deductions/fixed/{deduction_id}|仅授权仓库管理员；财务/主管禁止|0|
|R04-229|expense_approval / 既有页面，见handler/source；本轮未逐按钮核验|POST /api/v1/expense-approvals|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-230|expense_approval / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/expense-approvals|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-231|expense_approval / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/expense-approvals/summary|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-232|expense_approval / 既有页面，见handler/source；本轮未逐按钮核验|GET /api/v1/expense-approvals/threshold|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-233|expense_approval / 既有页面，见handler/source；本轮未逐按钮核验|PUT /api/v1/expense-approvals/threshold|保留前轮专用规则守卫并增加变更审计|0|
|R04-234|expense_approval / 既有页面，见handler/source；本轮未逐按钮核验|PUT /api/v1/expense-approvals/{approval_id}|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-235|expense_approval / 既有页面，见handler/source；本轮未逐按钮核验|POST /api/v1/expense-approvals/{approval_id}/approve|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-236|expense_approval / 既有页面，见handler/source；本轮未逐按钮核验|POST /api/v1/expense-approvals/{approval_id}/reject|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
|R04-237|expense_approval / 既有页面，见handler/source；本轮未逐按钮核验|POST /api/v1/expense-approvals/{approval_id}/pay|保留原管理鉴权；显式本人入口限有效本人，未全量改造读取/导出|0|
