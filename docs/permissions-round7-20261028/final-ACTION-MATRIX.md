# 第七轮动作与实测分支矩阵
本表的角色是上限，不代替本人、父子单、仓库和业务状态限制。成功响应数不是业务验收数。完整输入字段、状态表达式、关联服务、权限交接、审计和分支见同名 JSON；每次请求见压缩索引。

|动作|方法与路径|角色/三档|页面入口（静态）|实测请求/2xx/拒绝/有断言2xx|
|---|---|---|---|---|
|inventory.listing|GET /api/v1/inventory|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|28/17/11/17|
|inventory.available_skus|GET /api/v1/inventory/catalog|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|61/56/5/56|
|inventory.get_policy|GET /api/v1/inventory/policy|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|8/3/5/3|
|inventory.set_policy|PUT /api/v1/inventory/policy|{"operate": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|11/2/9/2|
|inventory.confirm_opening|POST /api/v1/inventory/openings|{"operate": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|61/52/9/52|
|inventory.pending_receipts|GET /api/v1/inventory/pending-receipts|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|10/5/5/5|
|inventory.resolve_receipt|POST /api/v1/inventory/pending-receipts/{ident}/resolve|{"operate": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|11/3/8/3|
|inventory.detail|GET /api/v1/inventory/accounts/{account_id}|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|25/15/10/15|
|inventory.issue|POST /api/v1/inventory/accounts/{account_id}/issues|{"operate": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|39/21/18/21|
|inventory.return_issue|POST /api/v1/inventory/movements/{movement_id}/returns|{"operate": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|12/6/6/6|
|inventory.reverse|POST /api/v1/inventory/movements/{movement_id}/reverse|{"operate": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|19/6/13/6|
|inventory.counts|GET /api/v1/inventory/counts|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|10/3/7/3|
|inventory.submit_count|POST /api/v1/inventory/accounts/{account_id}/counts|{"operate": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|23/14/9/14|
|inventory.review_count|POST /api/v1/inventory/counts/{count_id}/review|{"approve": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|23/11/12/11|
|inventory.get_controls|GET /api/v1/inventory/accounts/{account_id}/controls|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|16/10/6/10|
|inventory.set_controls|PUT /api/v1/inventory/accounts/{account_id}/controls|{"operate": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|18/9/9/9|
|inventory.get_analysis|GET /api/v1/inventory/analysis|{"view": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|28/20/8/20|
|inventory.export_analysis|GET /api/v1/inventory/analysis/export|{"view": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|9/2/7/2|
|procurement_controls.get_policy|GET /api/v1/supplier-controls/policy|{"view": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|18/15/3/15|
|procurement_controls.set_policy|PUT /api/v1/supplier-controls/policy|{"operate": ["warehouse_admin"]}|frontend/src/components/ProcurementControls.tsx|23/14/9/14|
|procurement_controls.get_context|GET /api/v1/supplier-controls/orders/{po_id}/context|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|24/21/3/21|
|procurement_controls.list_exceptions|GET /api/v1/supplier-controls/exceptions|{"view": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|10/1/9/1|
|procurement_controls.grant|POST /api/v1/supplier-controls/exceptions|{"approve": ["warehouse_admin"]}|frontend/src/components/ProcurementControls.tsx|14/11/3/11|
|procurement_controls.revoke|POST /api/v1/supplier-controls/exceptions/{ident}/revoke|{"approve": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|4/1/3/1|
|procurement_controls.exception_detail|GET /api/v1/supplier-controls/exceptions/{ident}|{"view": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|8/1/7/1|
|procurement_risk.board|GET /api/v1/supplier-risk|{"view": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|46/37/9/37|
|procurement_risk.download|GET /api/v1/supplier-risk/export|{"view": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|13/5/8/5|
|procurement_risk.detail|GET /api/v1/supplier-risk/signals/{signal_id}|{"view": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|13/4/9/4|
|procurement_risk.save_review|POST /api/v1/supplier-risk/signals/{signal_id}/reviews|{"approve": ["warehouse_admin"]}|frontend/src/components/ProcurementRiskReview.tsx|19/6/13/6|
|procurement_risk.review_history|GET /api/v1/supplier-risk/reviews|{"view": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|12/1/11/1|
|procurement_risk.export_reviews|GET /api/v1/supplier-risk/reviews/export|{"view": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|8/1/7/1|
|procurement_report.monthly|GET /api/v1/supplier-price-report|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|37/26/11/26|
|procurement_report.download|GET /api/v1/supplier-price-report/export|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|12/3/9/3|
|procurement_report.detail|GET /api/v1/supplier-price-report/orders/{order_id}/lines/{line_ref}|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|12/3/9/3|
|supplier_quotes.listing|GET /api/v1/supplier-quotes/suppliers/{supplier_id}|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|14/5/9/5|
|supplier_quotes.create|POST /api/v1/supplier-quotes/products/{product_id}|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/components/SupplierQuoteEditor.tsx|169/153/16/153|
|supplier_quotes.revise|PUT /api/v1/supplier-quotes/{quote_id}|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/components/SupplierQuoteEditor.tsx|71/67/4/67|
|supplier_quotes.history|GET /api/v1/supplier-quotes/{quote_id}/revisions|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|9/1/8/1|
|supplier_quotes.preview|POST /api/v1/supplier-quotes/purchase-preview|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|172/167/5/167|
|sku_catalog.reference|GET /api/v1/sku-catalog/reference|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|6/1/5/1|
|sku_catalog.listing|GET /api/v1/sku-catalog|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|15/8/7/8|
|sku_catalog.create|POST /api/v1/sku-catalog|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/supplier-skus/page.tsx|156/142/14/142|
|sku_catalog.update|PUT /api/v1/sku-catalog/{sku_id}|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/supplier-skus/page.tsx|12/7/5/7|
|sku_catalog.candidates|GET /api/v1/sku-catalog/products/{product_id}/candidates|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|318/314/4/314|
|sku_catalog.mapping|POST /api/v1/sku-catalog/products/{product_id}/mapping|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/components/SkuProductMapping.tsx|164/153/11/153|
|sku_catalog.mapping_history|GET /api/v1/sku-catalog/products/{product_id}/mapping-history|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|6/1/5/1|
|sku_catalog.history_candidates|GET /api/v1/sku-catalog/history-candidates|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|5/2/3/2|
|sku_catalog.tags|GET /api/v1/sku-catalog/tags|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|6/1/5/1|
|sku_catalog.create_tag|POST /api/v1/sku-catalog/tags|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/supplier-skus/page.tsx|10/2/8/2|
|sku_catalog.update_tag|PUT /api/v1/sku-catalog/tags/{tag_id}|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/supplier-skus/page.tsx|4/1/3/1|
|sku_catalog.supplier_tags|GET /api/v1/sku-catalog/suppliers/{supplier_id}/tags|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|5/2/3/2|
|sku_catalog.assign_tags|PUT /api/v1/sku-catalog/suppliers/{supplier_id}/tags|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/supplier-skus/page.tsx|6/1/5/1|
|cost_identity.suppliers|GET /api/v1/expense-identities/suppliers|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|8/1/7/1|
|cost_identity.origin|GET /api/v1/expense-identities/{source}/{source_id}|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|25/8/17/8|
|auth.attachment_session|POST /api/v1/auth/attachment-session|{"operate": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|4/4/0/4|
|auth.login|POST /api/v1/auth/login|{"operate": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|14/13/1/13|
|auth.get_me|GET /api/v1/auth/me|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|3/3/0/3|
|auth.change_password|POST /api/v1/auth/change-password|{"operate": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|2/2/0/2|
|users.list_users|GET /api/v1/users|{"view": ["staff", "super_admin", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|54/38/16/38|
|users.list_available_permissions|GET /api/v1/users/permissions|{"view": ["staff", "super_admin", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|10/6/4/6|
|users.create_user|POST /api/v1/users|{"operate": ["super_admin", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|21/5/16/5|
|users.update_user|PUT /api/v1/users/{user_id}|{"operate": ["super_admin", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|116/74/42/74|
|users.delete_user|DELETE /api/v1/users/{user_id}|{"operate": ["super_admin", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|17/3/14/3|
|dashboard.dashboard_stats|GET /api/v1/dashboard/stats|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|28/18/10/18|
|dashboard.pending_tasks|GET /api/v1/dashboard/pending-tasks|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|25/7/18/7|
|dashboard.warehouse_summary|GET /api/v1/dashboard/warehouse-summary|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|66/25/41/25|
|dashboard.dashboard_trends|GET /api/v1/dashboard/trends|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|27/9/18/9|
|dashboard.dashboard_cockpit|GET /api/v1/dashboard/cockpit|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|71/38/33/38|
|dashboard.boss_todos|GET /api/v1/dashboard/boss-todos|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|30/22/8/22|
|customers.customer_receivables|GET /api/v1/customers/{customer_id}/receivables|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|10/0/10/0|
|customers.link_customer_receipt|POST /api/v1/customers/{customer_id}/receipts/link|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/components/CustomerReceivable.tsx|9/0/9/0|
|customers.list_customers|GET /api/v1/customers|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|93/46/47/46|
|customers.create_customer|POST /api/v1/customers|{"operate": ["supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/customers/page.tsx|9/2/7/2|
|customers.get_customer|GET /api/v1/customers/{customer_id}|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|50/14/36/14|
|customers.update_customer|PUT /api/v1/customers/{customer_id}|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/customers/page.tsx|53/31/22/31|
|customers.delete_customer|DELETE /api/v1/customers/{customer_id}|{"operate": ["supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/customers/page.tsx|12/2/10/2|
|warehouses.list_warehouses|GET /api/v1/warehouses|{"view": ["staff", "super_admin", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|4/2/2/2|
|warehouses.create_warehouse|POST /api/v1/warehouses|{"operate": ["super_admin", "warehouse_admin"]}|frontend/src/app/(dashboard)/warehouses/page.tsx|4/1/3/1|
|warehouses.update_warehouse|PUT /api/v1/warehouses/{warehouse_id}|{"operate": ["super_admin", "warehouse_admin"]}|frontend/src/app/(dashboard)/warehouses/page.tsx|4/1/3/1|
|payment_accounts.create_transfer|POST /api/v1/accounts/transfers|{"operate": ["warehouse_admin", "staff"]}|frontend/src/app/(dashboard)/accounts/page.tsx|44/25/19/25|
|payment_accounts.list_accounts|GET /api/v1/accounts|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|210/176/34/164|
|payment_accounts.create_account|POST /api/v1/accounts|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/accounts/page.tsx|56/37/19/37|
|payment_accounts.update_account|PUT /api/v1/accounts/{account_id}|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/accounts/page.tsx|61/10/51/10|
|payment_accounts.toggle_account_status|PUT /api/v1/accounts/{account_id}/toggle-status|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/accounts/page.tsx|32/5/27/5|
|payment_accounts.delete_account|DELETE /api/v1/accounts/{account_id}|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/accounts/page.tsx|22/2/20/2|
|suppliers.list_suppliers|GET /api/v1/suppliers|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|20/15/5/15|
|suppliers.create_supplier|POST /api/v1/suppliers|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/suppliers/page.tsx|6/1/5/1|
|suppliers.get_match_policy|GET /api/v1/suppliers/purchase-match-policy|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|5/2/3/2|
|suppliers.set_match_policy|PUT /api/v1/suppliers/purchase-match-policy|{"operate": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|16/7/9/7|
|suppliers.list_categories|GET /api/v1/suppliers/categories|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|7/2/5/2|
|suppliers.create_category|POST /api/v1/suppliers/categories|{"operate": []}|最小办理或原业务上下文；须参照页面实测清单|4/0/4/0|
|suppliers.download_products_template|GET /api/v1/suppliers/import-template/products|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|8/5/3/5|
|suppliers.download_logistics_template|GET /api/v1/suppliers/import-template/logistics|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|25/22/3/22|
|suppliers.import_products|POST /api/v1/suppliers/import/products|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/suppliers/page.tsx|35/19/16/19|
|suppliers.import_logistics|POST /api/v1/suppliers/import/logistics|{"operate": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|9/4/5/4|
|suppliers.get_price_threshold|GET /api/v1/suppliers/price-threshold|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|6/1/5/1|
|suppliers.set_price_threshold|PUT /api/v1/suppliers/price-threshold|{"operate": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|8/3/5/3|
|suppliers.price_stats|GET /api/v1/suppliers/price-stats|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|6/1/5/1|
|suppliers.price_trend|GET /api/v1/suppliers/price-trend|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|6/1/5/1|
|suppliers.price_anomalies|GET /api/v1/suppliers/price-anomalies|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|6/1/5/1|
|suppliers.non_lowest_records|GET /api/v1/suppliers/non-lowest-records|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|6/1/5/1|
|suppliers.non_lowest_summary|GET /api/v1/suppliers/non-lowest-summary|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|6/1/5/1|
|suppliers.get_approval_threshold|GET /api/v1/suppliers/purchase-approval-threshold|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|21/9/12/9|
|suppliers.set_approval_threshold|PUT /api/v1/suppliers/purchase-approval-threshold|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/config-center/page.tsx|25/3/22/3|
|suppliers.purchase_approvals|GET /api/v1/suppliers/purchase-approvals|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|5/2/3/2|
|suppliers.approve_purchase|PUT /api/v1/suppliers/purchase-approvals/{po_id}/approve|{"approve": ["warehouse_admin", "supervisor", "staff"]}|frontend/src/app/(dashboard)/suppliers/page.tsx|21/14/7/14|
|suppliers.reject_purchase|PUT /api/v1/suppliers/purchase-approvals/{po_id}/reject|{"approve": ["warehouse_admin", "supervisor", "staff"]}|frontend/src/app/(dashboard)/suppliers/page.tsx|7/1/6/1|
|suppliers.list_purchase_orders|GET /api/v1/suppliers/purchase-orders|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|7/3/4/3|
|suppliers.get_purchase_detail|GET /api/v1/suppliers/purchase-orders/{po_id}|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|70/60/10/60|
|suppliers.read_receipt_photo|GET /api/v1/suppliers/purchase-orders/{po_id}/receipts/{event_id}/photo|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|11/3/8/3|
|suppliers.receive_purchase|POST /api/v1/suppliers/purchase-orders/{po_id}/receive|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/suppliers/page.tsx|95/58/37/58|
|suppliers.mark_purchase_sent|POST /api/v1/suppliers/purchase-orders/{po_id}/mark-sent|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/suppliers/page.tsx|7/2/5/2|
|suppliers.upload_purchase_receipt|POST /api/v1/suppliers/purchase-orders/{po_id}/receipt|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/suppliers/page.tsx<br>frontend/src/components/PurchaseReceiptInfo.tsx|5/1/4/1|
|suppliers.mark_purchase_shipped|POST /api/v1/suppliers/purchase-orders/{po_id}/mark-shipped|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/suppliers/page.tsx|6/1/5/1|
|suppliers.download_purchase_order_pdf|GET /api/v1/suppliers/purchase-orders/{po_id}/pdf|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|23/7/16/7|
|suppliers.receipt_discrepancies|GET /api/v1/suppliers/purchase-receipt-discrepancies|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|5/2/3/2|
|suppliers.get_concentration_threshold|GET /api/v1/suppliers/concentration-threshold|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|38/21/17/21|
|suppliers.set_concentration_threshold|PUT /api/v1/suppliers/concentration-threshold|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/config-center/page.tsx|32/4/28/4|
|suppliers.concentration_analysis|GET /api/v1/suppliers/concentration|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|20/8/12/8|
|suppliers.concentration_trend|GET /api/v1/suppliers/concentration-trend|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|16/6/10/6|
|suppliers.compare_prices|GET /api/v1/suppliers/compare-prices|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|7/3/4/3|
|suppliers.compare_logistics|GET /api/v1/suppliers/compare-logistics|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|5/2/3/2|
|suppliers.ai_compare|POST /api/v1/suppliers/ai-compare|{"view": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/suppliers/page.tsx|5/1/4/1|
|suppliers.procurement_summary|GET /api/v1/suppliers/procurement-summary|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|4/1/3/1|
|suppliers.import_products_for_supplier|POST /api/v1/suppliers/{supplier_id}/import/products|{"operate": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|78/47/31/47|
|suppliers.import_logistics_for_supplier|POST /api/v1/suppliers/{supplier_id}/import/logistics|{"operate": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|78/52/26/52|
|suppliers.list_products|GET /api/v1/suppliers/{supplier_id}/products|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|6/3/3/3|
|suppliers.add_product|POST /api/v1/suppliers/{supplier_id}/products|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/suppliers/page.tsx|163/160/3/160|
|suppliers.delete_product|DELETE /api/v1/suppliers/{supplier_id}/products/{product_id}|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/suppliers/page.tsx|5/2/3/2|
|suppliers.create_purchase_order|POST /api/v1/suppliers/{supplier_id}/purchase-order|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/suppliers/page.tsx|191/176/15/176|
|suppliers.list_logistics_prices|GET /api/v1/suppliers/{supplier_id}/logistics-prices|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|6/1/5/1|
|suppliers.add_logistics_price|POST /api/v1/suppliers/{supplier_id}/logistics-prices|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/suppliers/page.tsx|4/1/3/1|
|suppliers.delete_logistics_price|DELETE /api/v1/suppliers/{supplier_id}/logistics-prices/{price_id}|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/suppliers/page.tsx|5/1/4/1|
|suppliers.update_supplier|PUT /api/v1/suppliers/{supplier_id}|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/config-center/page.tsx|28/8/20/8|
|suppliers.delete_supplier|DELETE /api/v1/suppliers/{supplier_id}|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/suppliers/page.tsx|16/4/12/4|
|suppliers.get_supplier|GET /api/v1/suppliers/{supplier_id}|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|6/1/5/1|
|suppliers.ai_evaluate|GET /api/v1/suppliers/{supplier_id}/ai-evaluation|{"view": []}|最小办理或原业务上下文；须参照页面实测清单|9/0/9/0|
|recharge.list_recharges|GET /api/v1/recharge|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|24/10/14/10|
|recharge.create_recharge|POST /api/v1/recharge|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/recharge/page.tsx|24/7/17/7|
|recharge.get_recharge|GET /api/v1/recharge/{recharge_id}|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|14/2/12/2|
|recharge.edit_recharge|PUT /api/v1/recharge/{recharge_id}|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/recharge/page.tsx|15/3/12/3|
|recharge.delete_recharge|DELETE /api/v1/recharge/{recharge_id}|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/recharge/page.tsx|12/3/9/3|
|incoming.list_incoming|GET /api/v1/incoming|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|18/7/11/7|
|incoming.create_incoming|POST /api/v1/incoming|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/incoming/page.tsx|41/26/15/26|
|incoming.lookup_incoming|GET /api/v1/incoming/by-request/{request_key}|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|7/1/6/1|
|incoming.upload_incoming_screenshot|POST /api/v1/incoming/{incoming_id}/screenshot|{"operate": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|10/1/9/1|
|incoming.read_incoming_screenshot|GET /api/v1/incoming/{incoming_id}/screenshot|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|12/2/10/2|
|incoming.batch_import|POST /api/v1/incoming/batch-import|{"operate": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|15/3/12/3|
|incoming.import_excel|POST /api/v1/incoming/import-excel|{"operate": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|65/39/26/39|
|incoming.download_template|GET /api/v1/incoming/template|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|21/18/3/18|
|reconciliation.get_unmatched|GET /api/v1/reconciliation/unmatched|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|12/2/10/2|
|reconciliation.manual_match|POST /api/v1/reconciliation/manual-match|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/reconciliation/page.tsx|18/3/15/3|
|reconciliation.unmatch_record|POST /api/v1/reconciliation/unmatch|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/reconciliation/page.tsx|34/8/26/8|
|reconciliation.list_results|GET /api/v1/reconciliation/results|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|22/4/18/4|
|reconciliation.export_reconciliation|GET /api/v1/reconciliation/export|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|12/2/10/2|
|income_expense.list_categories|GET /api/v1/income-expense/categories|{"view": ["warehouse_admin", "staff", "supervisor"]}|最小办理或原业务上下文；须参照页面实测清单|7/2/5/2|
|income_expense.create_category|POST /api/v1/income-expense/categories|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/categories/page.tsx|10/1/9/1|
|income_expense.list_income|GET /api/v1/income-expense/income|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|83/51/32/51|
|income_expense.create_income|POST /api/v1/income-expense/income|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/other-income-expense/page.tsx|55/31/24/31|
|income_expense.update_income|PUT /api/v1/income-expense/income/{income_id}|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/other-income-expense/page.tsx|22/5/17/5|
|income_expense.delete_income|DELETE /api/v1/income-expense/income/{income_id}|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/other-income-expense/page.tsx|20/4/16/4|
|income_expense.list_expense|GET /api/v1/income-expense/expense|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|160/122/38/95|
|income_expense.export_expense|GET /api/v1/income-expense/expense/export|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|23/15/8/15|
|income_expense.create_expense|POST /api/v1/income-expense/expense|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/income-expense/page.tsx<br>frontend/src/app/(dashboard)/operating/page.tsx|60/32/28/32|
|income_expense.update_expense|PUT /api/v1/income-expense/expense/{expense_id}|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/operating/page.tsx|12/1/11/1|
|income_expense.delete_expense|DELETE /api/v1/income-expense/expense/{expense_id}|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/operating/page.tsx|12/1/11/1|
|income_expense.ledger|GET /api/v1/income-expense/ledger|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|221/181/40/164|
|income_expense.ledger_export|GET /api/v1/income-expense/ledger/export|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|33/6/27/6|
|income_expense.export_income|GET /api/v1/income-expense/income/export|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|71/43/28/43|
|income_expense.monthly_summary|GET /api/v1/income-expense/monthly-summary|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|122/86/36/79|
|income_expense.operating_dashboard|GET /api/v1/income-expense/operating-dashboard|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|45/17/28/17|
|expense_fund.create_account|POST /api/v1/expense-fund/accounts|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/expense-fund/page.tsx|54/48/6/47|
|expense_fund.list_employees|GET /api/v1/expense-fund/employees|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|6/1/5/1|
|expense_fund.list_accounts|GET /api/v1/expense-fund/accounts|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|119/113/6/110|
|expense_fund.disbursement_accounts|GET /api/v1/expense-fund/payment-accounts|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|6/1/5/1|
|expense_fund.list_disbursements|GET /api/v1/expense-fund/accounts/{account_id}/disbursements|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|10/4/6/4|
|expense_fund.topup_account|POST /api/v1/expense-fund/accounts/{account_id}/topup|{"operate": []}|最小办理或原业务上下文；须参照页面实测清单|11/0/11/0|
|expense_fund.list_items|GET /api/v1/expense-fund/accounts/{account_id}/items|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|12/5/7/4|
|expense_fund.edit_item|PUT /api/v1/expense-fund/accounts/{account_id}/items/{item_id}|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/expense-fund/page.tsx|25/4/21/4|
|expense_fund.void_item|DELETE /api/v1/expense-fund/accounts/{account_id}/items/{item_id}|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/expense-fund/page.tsx|20/4/16/4|
|expense_fund.add_item|POST /api/v1/expense-fund/accounts/{account_id}/items|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/expense-fund/page.tsx|74/33/41/32|
|expense_fund.upload_new_item_receipt|POST /api/v1/expense-fund/accounts/{account_id}/upload-receipt|{"operate": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|192/182/10/181|
|expense_fund.upload_receipt|POST /api/v1/expense-fund/accounts/{account_id}/items/{item_id}/upload-receipt|{"operate": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|8/2/6/2|
|expense_fund.list_pending_reviews|GET /api/v1/expense-fund/review/pending|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|6/1/5/1|
|expense_fund.batch_review|POST /api/v1/expense-fund/review/batch|{"field": "action", "values": {"verify": {"tier": "operate", "roles": ["warehouse_admin", "staff"]}, "approve": {"tier": "approve", "roles": ["warehouse_admin"]}, "reject": {"tier": "approve", "roles": ["warehouse_admin"]}}}|frontend/src/app/(dashboard)/expense-fund/page.tsx<br>frontend/src/app/(dashboard)/fund-review/page.tsx|68/39/29/39|
|expense_fund.submit_recharge_request|POST /api/v1/expense-fund/recharge/request|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/expense-fund/page.tsx|59/56/3/55|
|expense_fund.list_recharge_requests|GET /api/v1/expense-fund/recharge/requests|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|9/4/5/4|
|expense_fund.review_recharge_request|POST /api/v1/expense-fund/recharge/review|{"field": "action", "values": {"verify": {"tier": "operate", "roles": ["warehouse_admin", "staff"]}, "approve": {"tier": "approve", "roles": ["warehouse_admin"]}, "reject": {"tier": "approve", "roles": ["warehouse_admin"]}}}|frontend/src/app/(dashboard)/expense-fund/page.tsx<br>frontend/src/app/(dashboard)/fund-review/page.tsx|117/102/15/100|
|expense_fund.execute_recharge|POST /api/v1/expense-fund/recharge/execute|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/expense-fund/page.tsx|67/42/25/41|
|expense_fund.fund_settings|GET /api/v1/expense-fund/settings|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|6/1/5/1|
|expense_fund.update_settings|POST /api/v1/expense-fund/settings|{"operate": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|27/2/25/2|
|expense_fund.balance_summary|GET /api/v1/expense-fund/balance|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|6/1/5/1|
|expense_fund.alert_list|GET /api/v1/expense-fund/alert|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|6/1/5/1|
|reimbursement.payment_sources|GET /api/v1/reimbursement/payment-sources|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|9/1/8/1|
|reimbursement.payment_voucher|POST /api/v1/reimbursement/payment-voucher|{"operate": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|71/67/4/58|
|reimbursement.list_reimbursements|GET /api/v1/reimbursement|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|14/8/6/8|
|reimbursement.create_reimbursement|POST /api/v1/reimbursement|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/reimbursement/page.tsx|220/116/104/107|
|reimbursement.export_reimbursements|GET /api/v1/reimbursement/export|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|6/1/5/1|
|reimbursement.list_reimb_categories|GET /api/v1/reimbursement/categories|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|25/7/18/7|
|reimbursement.get_reimb_detail|GET /api/v1/reimbursement/{reimb_id}|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|104/97/7/87|
|reimbursement.edit_reimb|PUT /api/v1/reimbursement/{reimb_id}|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/reimbursement/page.tsx|132/23/109/23|
|reimbursement.delete_reimb|DELETE /api/v1/reimbursement/{reimb_id}|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/reimbursement/page.tsx|8/1/7/1|
|reimbursement.submit_reimb|POST /api/v1/reimbursement/{reimb_id}/submit|{"operate": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|21/2/19/2|
|reimbursement.verify_reimb|POST /api/v1/reimbursement/{reimb_id}/verify|{"operate": ["warehouse_admin", "staff"]}|frontend/src/app/(dashboard)/reimbursement/page.tsx|93/85/8/76|
|reimbursement.return_reimb|POST /api/v1/reimbursement/{reimb_id}/return-to-draft|{"operate": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|5/2/3/2|
|reimbursement.review_reimb|POST /api/v1/reimbursement/{reimb_id}/review|{"approve": ["warehouse_admin"]}|frontend/src/app/(dashboard)/reimbursement/page.tsx|134/101/33/92|
|reimbursement.pay_reimb|POST /api/v1/reimbursement/{reimb_id}/pay|{"operate": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|149/72/77/62|
|reimbursement.payment_history|GET /api/v1/reimbursement/{reimb_id}/payments|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|14/9/5/8|
|reimbursement.revoke_payment|POST /api/v1/reimbursement/{reimb_id}/revoke-payment|{"operate": []}|最小办理或原业务上下文；须参照页面实测清单|48/0/48/0|
|reimbursement.create_reimb_category|POST /api/v1/reimbursement/categories|{"operate": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|6/1/5/1|
|payable.list_bills|GET /api/v1/payable|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|53/17/36/17|
|payable.create_bill|POST /api/v1/payable|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/payable/page.tsx|85/37/48/37|
|payable.upload_voucher|POST /api/v1/payable/{bill_id}/upload-voucher|{"operate": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|13/2/11/2|
|payable.upload_bill_attachment|POST /api/v1/payable/{bill_id}/upload-attachment|{"operate": ["warehouse_admin"]}|frontend/src/components/PayableDetail.tsx|11/1/10/1|
|payable.pay_bill|PUT /api/v1/payable/{bill_id}/pay|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/payable/page.tsx<br>frontend/src/components/PayableDetail.tsx|85/37/48/37|
|payable.confirm_bill|PUT /api/v1/payable/{bill_id}/confirm|{"approve": ["warehouse_admin"]}|frontend/src/app/(dashboard)/payable/page.tsx<br>frontend/src/components/PayableDetail.tsx|27/14/13/14|
|payable.void_bill|PUT /api/v1/payable/{bill_id}/void|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/payable/page.tsx|25/11/14/11|
|payable.update_bill|PUT /api/v1/payable/{bill_id}|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/payable/page.tsx|39/8/31/8|
|payable.payable_stats|GET /api/v1/payable/stats|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|19/9/10/9|
|payable.get_bill_detail|GET /api/v1/payable/{bill_id}/detail|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|34/20/14/20|
|payable.list_plans|GET /api/v1/payable/plans|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|39/12/27/12|
|payable.create_plan|POST /api/v1/payable/plans|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/payment-plans/page.tsx|43/18/25/18|
|payable.cashflow_prediction|GET /api/v1/payable/cashflow-prediction|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|11/4/7/4|
|payable.batch_export|GET /api/v1/payable/batch-export|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|36/13/23/13|
|payable.supplier_statement|GET /api/v1/payable/supplier-statement|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|12/5/7/5|
|payable.list_templates|GET /api/v1/payable/plan-templates|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|11/2/9/2|
|payable.delete_template|DELETE /api/v1/payable/plan-templates/{template_id}|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/payment-plans/page.tsx|23/5/18/5|
|payable.payable_timeline|GET /api/v1/payable/timeline|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|11/4/7/4|
|payable.execute_plan|PUT /api/v1/payable/plans/{plan_id}/execute|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/payment-plans/page.tsx|54/7/47/7|
|payable.plan_detail|GET /api/v1/payable/plans/{plan_id}/detail|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|11/2/9/2|
|payable.upload_plan_attachment|POST /api/v1/payable/plans/{plan_id}/upload-attachment|{"operate": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|11/1/10/1|
|payable.export_plans|GET /api/v1/payable/plans/export|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|12/4/8/4|
|payable.get_monthly_order|GET /api/v1/payable/monthly-order|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|9/2/7/2|
|payable.save_monthly_order|POST /api/v1/payable/monthly-order|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/payable/page.tsx|9/1/8/1|
|payable.payable_trend|GET /api/v1/payable/trend|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|11/4/7/4|
|payable.verify_bill_payment|POST /api/v1/payable/{bill_id}/verify-payment|{"operate": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|52/47/5/47|
|payable.approve_bill_payment|POST /api/v1/payable/{bill_id}/approve-payment|{"approve": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|50/47/3/47|
|credit.list_shipments|GET /api/v1/credit/shipments|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|10/0/10/0|
|credit.list_credit_customers|GET /api/v1/credit|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|14/5/9/5|
|credit.create_credit|POST /api/v1/credit|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/credit/page.tsx|7/1/6/1|
|credit.update_credit|PUT /api/v1/credit/{credit_id}|{"operate": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|7/1/6/1|
|credit.credit_detail|GET /api/v1/credit/{credit_id}/detail|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|6/1/5/1|
|credit.create_shipment|POST /api/v1/credit/{credit_id}/shipment|{"operate": ["staff", "warehouse_admin"]}|frontend/src/components/CreditShipments.tsx|9/0/9/0|
|credit.update_shipment|PUT /api/v1/credit/{credit_id}/shipment/{shipment_id}|{"operate": ["staff", "warehouse_admin"]}|frontend/src/components/CreditShipments.tsx|9/0/9/0|
|credit.void_shipment|POST /api/v1/credit/{credit_id}/shipment/{shipment_id}/void|{"operate": ["staff", "warehouse_admin"]}|frontend/src/components/CreditShipments.tsx|9/0/9/0|
|credit.record_repayment|POST /api/v1/credit/{credit_id}/payment|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/credit/page.tsx|29/9/20/9|
|credit.credit_dashboard|GET /api/v1/credit/dashboard|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|7/1/6/1|
|credit.credit_assessment|GET /api/v1/credit/assessment|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|6/1/5/1|
|credit.export_assessment|GET /api/v1/credit/assessment/export|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|6/1/5/1|
|credit.credit_alerts|GET /api/v1/credit/alerts|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|7/1/6/1|
|market.upload_market_image|POST /api/v1/market/image|{"operate": ["staff", "super_admin", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|9/1/8/1|
|market.list_items|GET /api/v1/market|{"view": ["staff", "super_admin", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|16/11/5/11|
|market.create_item|POST /api/v1/market|{"operate": ["staff", "super_admin", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/market/page.tsx|12/1/11/1|
|market.review_list|GET /api/v1/market/review-list|{"view": ["staff", "super_admin", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|7/1/6/1|
|market.review_item|PUT /api/v1/market/{item_id}/review|{"approve": ["super_admin", "warehouse_admin"]}|frontend/src/app/(dashboard)/market/page.tsx|8/1/7/1|
|market.purchase|POST /api/v1/market/{item_id}/purchase|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/market/page.tsx|15/5/10/5|
|market.confirm_trade|PUT /api/v1/market/{item_id}/confirm|{"operate": ["super_admin"]}|frontend/src/app/(dashboard)/market/page.tsx|16/2/14/2|
|group_order.list_group_orders|GET /api/v1/group-order|{"view": ["staff", "super_admin", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|18/12/6/12|
|group_order.create_group_order|POST /api/v1/group-order|{"operate": ["staff", "super_admin", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/group-order/page.tsx|15/2/13/2|
|group_order.join_group_order|POST /api/v1/group-order/{go_id}/join|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/group-order/page.tsx|26/11/15/11|
|group_order.list_participants|GET /api/v1/group-order/{go_id}/participants|{"view": ["staff", "super_admin", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|15/11/4/11|
|group_order.history|GET /api/v1/group-order/history|{"view": ["staff", "super_admin", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|9/5/4/5|
|group_order.get_order_detail|GET /api/v1/group-order/{go_id}|{"view": ["staff", "super_admin", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|12/8/4/8|
|group_order.close_order|PUT /api/v1/group-order/{go_id}/close|{"operate": ["super_admin"]}|frontend/src/app/(dashboard)/group-order/page.tsx|15/2/13/2|
|group_order.complete_order|PUT /api/v1/group-order/{go_id}/complete|{"operate": ["super_admin"]}|frontend/src/app/(dashboard)/group-order/page.tsx|15/2/13/2|
|group_order.cancel_order|PUT /api/v1/group-order/{go_id}/cancel|{"operate": ["super_admin"]}|frontend/src/app/(dashboard)/group-order/page.tsx|14/1/13/1|
|group_order.ban_participant|PUT /api/v1/group-order/participant/{participant_id}/ban|{"operate": ["staff", "super_admin", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|15/2/13/2|
|cost_funds_debt.get_report|GET /api/v1/reports/cost-funds-debt|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|111/71/40/68|
|cost_funds_debt.costs|GET /api/v1/reports/cost-funds-debt/costs|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|51/22/29/12|
|cost_funds_debt.flows|GET /api/v1/reports/cost-funds-debt/flows|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|46/16/30/10|
|cost_funds_debt.advances|GET /api/v1/reports/cost-funds-debt/advances|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|38/8/30/4|
|reports.report_previews|GET /api/v1/reports/previews|{"view": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/reports/page.tsx|62/22/40/22|
|reports.recharge_summary|GET /api/v1/reports/recharge-summary|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|57/23/34/23|
|reports.incoming_summary|GET /api/v1/reports/incoming-summary|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|46/15/31/15|
|reports.income_expense_report|GET /api/v1/reports/income-expense|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|144/86/58/77|
|reports.payable_report|GET /api/v1/reports/payable|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|44/16/28/16|
|reports.expense_fund_report|GET /api/v1/reports/expense-fund|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|44/16/28/16|
|reports.reimbursement_report|GET /api/v1/reports/reimbursement|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|43/15/28/15|
|reports.credit_report|GET /api/v1/reports/credit|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|45/15/30/15|
|reports.reconciliation_diff_report|GET /api/v1/reports/reconciliation-diff|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|47/16/31/16|
|reports.operating_report|GET /api/v1/reports/operations|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|11/0/11/0|
|upload.upload_file|POST /api/v1/upload|{"operate": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|21/15/6/15|
|upload.upload_recharge_screenshot|POST /api/v1/upload/recharge-screenshot|{"operate": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|31/9/22/9|
|settings_api.get_boss_contact|GET /api/v1/settings/boss-contact|{"view": ["staff", "super_admin", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|9/3/6/3|
|settings_api.set_boss_contact|PUT /api/v1/settings/boss-contact|{"operate": ["super_admin", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|8/2/6/2|
|settings_api.operation_logs|GET /api/v1/settings/logs|{"view": ["staff", "super_admin", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|13/9/4/9|
|settings_api.backup_all_data|POST /api/v1/settings/backup|{"view": ["super_admin"]}|最小办理或原业务上下文；须参照页面实测清单|8/1/7/1|
|config_api.get_attendance_times|GET /api/v1/config/attendance-times|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|11/2/9/2|
|config_api.get_work_schedule_settings|GET /api/v1/config/work-schedule|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|23/11/12/11|
|config_api.set_work_schedule_settings|PUT /api/v1/config/work-schedule|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/config-center/page.tsx|36/7/29/7|
|exchange_rates.list_rates|GET /api/v1/rates|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|14/6/8/6|
|exchange_rates.create_rate|POST /api/v1/rates|{"operate": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|11/2/9/2|
|exchange_rates.query_rate|GET /api/v1/rates/query|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|8/1/7/1|
|employees.get_max_limit|GET /api/v1/employees/max-limit|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|18/8/10/8|
|employees.set_max_limit|PUT /api/v1/employees/max-limit|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/employees/page.tsx|30/5/25/5|
|employees.list_employees|GET /api/v1/employees|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|130/65/65/65|
|employees.create_employee|POST /api/v1/employees|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/employees/page.tsx|42/10/32/10|
|employees.update_employee|PUT /api/v1/employees/{employee_id}|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/employees/page.tsx|302/83/219/83|
|employees.resign_employee|POST /api/v1/employees/{employee_id}/resign|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/employees/page.tsx|30/12/18/12|
|employees.delete_employee|DELETE /api/v1/employees/{employee_id}|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/employees/page.tsx|25/9/16/9|
|employees.bind_existing_accounts|POST /api/v1/employees/bind-existing-accounts|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/employees/page.tsx|18/2/16/2|
|employees.batch_set_templates|POST /api/v1/employees/batch-set-templates|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/employees/page.tsx|44/2/42/2|
|employees.upload_employee_photo|POST /api/v1/employees/{employee_id}/photo|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/employees/page.tsx|30/14/16/14|
|employees.upload_passport_photo|POST /api/v1/employees/{employee_id}/passport-photo|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/employees/page.tsx|30/14/16/14|
|employees.upload_work_permit_photo|POST /api/v1/employees/{employee_id}/work-permit-photo|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/employees/page.tsx|30/14/16/14|
|employees.employee_summary|GET /api/v1/employees/{employee_id}/summary|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|34/13/21/13|
|clock_in.clock_in|POST /api/v1/clock-in|{"operate": ["warehouse_admin", "supervisor", "staff", "warehouse_labor"]}|最小办理或原业务上下文；须参照页面实测清单|82/23/59/23|
|clock_in.get_today|GET /api/v1/clock-in/today|{"view": ["warehouse_admin", "supervisor", "staff", "warehouse_labor"]}|最小办理或原业务上下文；须参照页面实测清单|61/34/27/34|
|clock_in.list_records|GET /api/v1/clock-in/records|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|38/20/18/20|
|clock_in.makeup_clock_in|POST /api/v1/clock-in/makeup|{"operate": ["supervisor", "warehouse_admin"]}|frontend/src/components/ClockRecordsGrid.tsx|23/8/15/8|
|clock_in.batch_makeup_clock_in|POST /api/v1/clock-in/batch-makeup|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/attendance/page.tsx<br>frontend/src/components/BatchMakeupModal.tsx|49/20/29/20|
|clock_in.list_makeup_batches|GET /api/v1/clock-in/makeup-batches|{"view": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|20/9/11/9|
|clock_in.revoke_makeup_batch|POST /api/v1/clock-in/makeup-batches/{batch_id}/revoke|{"operate": ["warehouse_admin"]}|frontend/src/components/MakeupBatchHistory.tsx|21/5/16/5|
|clock_in.makeup_count|GET /api/v1/clock-in/makeup-count|{"view": ["supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|23/12/11/12|
|clock_in.export_records|GET /api/v1/clock-in/records/export|{"view": ["supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|13/4/9/4|
|clock_in.get_photos|GET /api/v1/clock-in/photos|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|24/9/15/9|
|clock_in.request_personal_makeup|POST /api/v1/clock-in/makeup-requests|{"operate": ["warehouse_admin", "supervisor", "staff", "warehouse_labor"]}|最小办理或原业务上下文；须参照页面实测清单|2/2/0/2|
|clock_in.list_makeup_requests|GET /api/v1/clock-in/makeup-requests|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|3/2/1/2|
|clock_in.approve_makeup_request|POST /api/v1/clock-in/makeup-requests/{request_id}/approve|{"approve": ["supervisor", "warehouse_admin"]}|frontend/src/components/MakeupRequests.tsx|9/2/7/2|
|attendance.create_leave|POST /api/v1/attendance/leaves|{"operate": ["warehouse_admin", "supervisor", "staff", "warehouse_labor"]}|最小办理或原业务上下文；须参照页面实测清单|27/12/15/12|
|attendance.admin_record_leave|POST /api/v1/attendance/leaves/admin-record|{"approve": ["warehouse_admin", "supervisor"]}|frontend/src/app/(dashboard)/attendance/page.tsx|44/20/24/20|
|attendance.list_leaves|GET /api/v1/attendance/leaves|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|50/31/19/31|
|attendance.approve_leave|PUT /api/v1/attendance/leaves/{leave_id}/approve|{"approve": ["supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/attendance/page.tsx|43/12/31/12|
|attendance.reject_leave|PUT /api/v1/attendance/leaves/{leave_id}/reject|{"approve": ["supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/attendance/page.tsx|23/11/12/11|
|attendance.set_rest_days|POST /api/v1/attendance/rest-days|{"operate": ["supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/attendance/page.tsx|15/2/13/2|
|attendance.list_rest_days|GET /api/v1/attendance/rest-days|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|33/17/16/17|
|attendance.delete_rest_day|DELETE /api/v1/attendance/rest-days/{rest_day_id}|{"operate": ["supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/attendance/page.tsx|13/2/11/2|
|attendance.mark_absence|POST /api/v1/attendance/absences|{"operate": ["supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/attendance/page.tsx|15/2/13/2|
|attendance.remove_absence|DELETE /api/v1/attendance/absences/{absence_id}|{"operate": ["supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|13/2/11/2|
|attendance.get_calendar|GET /api/v1/attendance/calendar|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|138/119/19/119|
|overtime.create_overtime|POST /api/v1/overtime|{"operate": ["supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/overtime/page.tsx|40/27/13/27|
|overtime.verify_overtime|POST /api/v1/overtime/{task_id}/verify|{"approve": ["supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/overtime/page.tsx|44/19/25/19|
|overtime.confirm_overtime|POST /api/v1/overtime/{overtime_id}/confirm|{"operate": ["warehouse_admin", "supervisor", "staff", "warehouse_labor"]}|最小办理或原业务上下文；须参照页面实测清单|28/11/17/11|
|overtime.dispute_overtime|POST /api/v1/overtime/{task_id}/dispute|{"operate": ["warehouse_admin", "supervisor", "staff", "warehouse_labor"]}|最小办理或原业务上下文；须参照页面实测清单|24/7/17/7|
|overtime.list_overtimes|GET /api/v1/overtime|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|44/24/20/24|
|overtime.pending_overtimes|GET /api/v1/overtime/pending|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|26/7/19/7|
|overtime.monthly_hours|GET /api/v1/overtime/monthly-hours|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|20/9/11/9|
|overtime.get_overtime_limit|GET /api/v1/overtime/limit|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|19/8/11/8|
|overtime.set_overtime_limit|PUT /api/v1/overtime/limit|{"operate": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|15/2/13/2|
|overtime.delete_overtime|DELETE /api/v1/overtime/{overtime_id}|{"operate": ["supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/overtime/page.tsx|14/3/11/3|
|payroll.calculate_payroll|POST /api/v1/payroll/calculate|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/payroll/page.tsx|152/118/34/118|
|payroll.preview_payroll|POST /api/v1/payroll/preview|{"view": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/payroll/page.tsx|33/9/24/9|
|payroll.single_settle|POST /api/v1/payroll/single-settle|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/payroll/page.tsx|21/2/19/2|
|payroll.list_payroll|GET /api/v1/payroll|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|72/36/36/36|
|payroll.payroll_summary|GET /api/v1/payroll/summary|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|22/3/19/3|
|payroll.export_payroll|GET /api/v1/payroll/export|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|28/7/21/7|
|payroll.confirm_payroll|POST /api/v1/payroll/{record_id}/confirm|{"approve": ["warehouse_admin"]}|frontend/src/app/(dashboard)/payroll/page.tsx|141/107/34/102|
|payroll.confirm_all_payroll|POST /api/v1/payroll/confirm-all|{"approve": ["warehouse_admin"]}|frontend/src/app/(dashboard)/payroll/page.tsx|19/1/18/1|
|payroll.batch_confirm_payroll|POST /api/v1/payroll/batch-confirm|{"approve": ["warehouse_admin"]}|frontend/src/app/(dashboard)/payroll/page.tsx|26/3/23/3|
|payroll.payroll_cash_advance_sources|GET /api/v1/payroll/cash-advance-sources|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|22/4/18/4|
|payroll.batch_disburse_payroll|POST /api/v1/payroll/batch-disburse|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/payroll/page.tsx|41/4/37/4|
|payroll.batch_delete_payroll|POST /api/v1/payroll/batch-delete|{"operate": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|24/2/22/2|
|payroll.recalc_payroll|POST /api/v1/payroll/{record_id}/recalc|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/payroll/page.tsx|56/30/26/30|
|payroll.batch_recalc_payroll|POST /api/v1/payroll/batch-recalc|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/payroll/page.tsx|28/4/24/4|
|payroll.delete_payroll|DELETE /api/v1/payroll/{record_id}|{"operate": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|27/4/23/4|
|payroll.delete_period_payroll|DELETE /api/v1/payroll/period/{period}|{"operate": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|23/1/22/1|
|payroll.disburse_payroll|POST /api/v1/payroll/{record_id}/disburse|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/payroll/page.tsx|135/60/75/56|
|payroll.revoke_disbursement|POST /api/v1/payroll/{record_id}/revoke-disbursement|{"operate": []}|frontend/src/app/(dashboard)/payroll/page.tsx|51/0/51/0|
|payroll.pending_resignations|GET /api/v1/payroll/pending-resignations|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|13/2/11/2|
|payroll.my_payslip|GET /api/v1/payroll/my-payslip|{"view": ["warehouse_admin", "supervisor", "staff", "warehouse_labor"]}|最小办理或原业务上下文；须参照页面实测清单|82/37/45/37|
|payroll.settlement_progress|GET /api/v1/payroll/settlement-progress|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|18/2/16/2|
|payroll.payroll_detail|GET /api/v1/payroll/{record_id}|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|37/7/30/7|
|history.list_operators|GET /api/v1/history/operators|{"view": ["staff", "super_admin", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|14/7/7/7|
|history.list_history|GET /api/v1/history|{"view": ["staff", "super_admin", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|82/55/27/55|
|history.export_history|GET /api/v1/history/export|{"view": ["staff", "super_admin", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|63/42/21/42|
|efficiency.get_summary|GET /api/v1/efficiency/summary|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|18/8/10/8|
|efficiency.get_trend|GET /api/v1/efficiency/trend|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|16/6/10/6|
|efficiency.get_compare|GET /api/v1/efficiency/compare|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|16/6/10/6|
|efficiency.get_daily_orders|GET /api/v1/efficiency/daily-orders|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|16/6/10/6|
|efficiency.set_order_count|PUT /api/v1/efficiency/order-count|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/labor-efficiency/page.tsx|27/9/18/9|
|efficiency.get_standard|GET /api/v1/efficiency/standard|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|25/11/14/11|
|efficiency.get_standards|GET /api/v1/efficiency/standards|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|16/6/10/6|
|efficiency.set_standard|PUT /api/v1/efficiency/standard|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/labor-efficiency/page.tsx|21/3/18/3|
|efficiency.set_manual_hour|PUT /api/v1/efficiency/manual-hour|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/labor-efficiency/page.tsx|24/7/17/7|
|efficiency.delete_manual_hour|DELETE /api/v1/efficiency/manual-hour|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/labor-efficiency/page.tsx|16/6/10/6|
|employee_advance.create_advance|POST /api/v1/employee-advances|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/employee-advances/page.tsx|242/151/91/149|
|employee_advance.list_funding_options|GET /api/v1/employee-advances/funding-options|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|20/15/5/15|
|employee_advance.list_advance_recipients|GET /api/v1/employee-advances/recipients|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|15/8/7/8|
|employee_advance.list_advances|GET /api/v1/employee-advances|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|49/25/24/25|
|employee_advance.advance_summary|GET /api/v1/employee-advances/summary|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|11/3/8/3|
|employee_advance.my_debt|GET /api/v1/employee-advances/my-debt|{"view": ["warehouse_admin", "supervisor", "staff", "warehouse_labor"]}|最小办理或原业务上下文；须参照页面实测清单|45/25/20/25|
|employee_advance.delete_advance|DELETE /api/v1/employee-advances/{advance_id}|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/employee-advances/page.tsx|58/14/44/13|
|employee_advance.approve_advance|POST /api/v1/employee-advances/{advance_id}/approve|{"approve": ["warehouse_admin"]}|frontend/src/app/(dashboard)/employee-advances/page.tsx|118/93/25/91|
|employee_advance.reject_advance|POST /api/v1/employee-advances/{advance_id}/reject|{"approve": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|36/14/22/14|
|employee_advance.advance_detail|GET /api/v1/employee-advances/{advance_id}|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|22/4/18/4|
|employee_advance.verify_advance|POST /api/v1/employee-advances/{advance_id}/verify|{"operate": ["warehouse_admin", "staff"]}|frontend/src/app/(dashboard)/employee-advances/page.tsx|99/94/5/92|
|employee_advance.execute_advance|POST /api/v1/employee-advances/{advance_id}/execute|{"operate": ["warehouse_admin", "staff"]}|最小办理或原业务上下文；须参照页面实测清单|116/78/38/76|
|salary_template.list_salary_templates|GET /api/v1/salary-templates|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|27/8/19/8|
|salary_template.create_salary_template|POST /api/v1/salary-templates|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/salary-templates/page.tsx|22/2/20/2|
|salary_template.update_salary_template|PUT /api/v1/salary-templates/{template_id}|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/salary-templates/page.tsx|42/4/38/4|
|salary_template.delete_salary_template|DELETE /api/v1/salary-templates/{template_id}|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/salary-templates/page.tsx|28/2/26/2|
|deduction_template.list_deduction_templates|GET /api/v1/deduction-templates|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|27/8/19/8|
|deduction_template.create_deduction_template|POST /api/v1/deduction-templates|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/deduction-templates/page.tsx|22/2/20/2|
|deduction_template.update_deduction_template|PUT /api/v1/deduction-templates/{template_id}|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/deduction-templates/page.tsx|32/3/29/3|
|deduction_template.delete_deduction_template|DELETE /api/v1/deduction-templates/{template_id}|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/deduction-templates/page.tsx|22/2/20/2|
|employee_deduction.create_deduction|POST /api/v1/employee-deductions|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/employee-deductions/page.tsx|20/1/19/1|
|employee_deduction.list_deductions|GET /api/v1/employee-deductions|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|26/5/21/5|
|employee_deduction.delete_deduction|DELETE /api/v1/employee-deductions/{deduction_id}|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/employee-deductions/page.tsx|14/1/13/1|
|employee_deduction.list_fixed_deductions|GET /api/v1/employee-deductions/fixed|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|16/3/13/3|
|employee_deduction.create_fixed_deduction|POST /api/v1/employee-deductions/fixed|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/employees/page.tsx|16/1/15/1|
|employee_deduction.update_fixed_deduction|PUT /api/v1/employee-deductions/fixed/{deduction_id}|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/employees/page.tsx|16/1/15/1|
|employee_deduction.delete_fixed_deduction|DELETE /api/v1/employee-deductions/fixed/{deduction_id}|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/employees/page.tsx|16/1/15/1|
|expense_approval.create_approval|POST /api/v1/expense-approvals|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/expense-approvals/page.tsx|33/24/9/24|
|expense_approval.list_approvals|GET /api/v1/expense-approvals|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|17/6/11/6|
|expense_approval.approval_summary|GET /api/v1/expense-approvals/summary|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|6/1/5/1|
|expense_approval.get_threshold|GET /api/v1/expense-approvals/threshold|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|21/11/10/11|
|expense_approval.set_threshold|PUT /api/v1/expense-approvals/threshold|{"operate": ["warehouse_admin"]}|frontend/src/app/(dashboard)/config-center/page.tsx|25/3/22/3|
|expense_approval.update_approval|PUT /api/v1/expense-approvals/{approval_id}|{"operate": ["staff", "supervisor", "warehouse_admin"]}|frontend/src/app/(dashboard)/config-center/page.tsx<br>frontend/src/app/(dashboard)/expense-approvals/page.tsx|6/1/5/1|
|expense_approval.approve_approval|POST /api/v1/expense-approvals/{approval_id}/approve|{"approve": ["warehouse_admin"]}|frontend/src/app/(dashboard)/expense-approvals/page.tsx|18/15/3/15|
|expense_approval.reject_approval|POST /api/v1/expense-approvals/{approval_id}/reject|{"approve": ["warehouse_admin"]}|frontend/src/app/(dashboard)/expense-approvals/page.tsx|5/2/3/2|
|expense_approval.pay_approval|POST /api/v1/expense-approvals/{approval_id}/pay|{"operate": ["warehouse_admin", "staff"]}|frontend/src/app/(dashboard)/expense-approvals/page.tsx|67/42/25/42|
|cash_advance.document_options|GET /api/v1/cash-advances/document-options|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|32/27/5/27|
|cash_advance.list_payers|GET /api/v1/cash-advances/payers|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|11/3/8/3|
|cash_advance.summary|GET /api/v1/cash-advances/summary|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|20/12/8/8|
|cash_advance.list_advances|GET /api/v1/cash-advances|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|47/32/15/31|
|cash_advance.upload_voucher|POST /api/v1/cash-advances/voucher|{"operate": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|13/3/10/3|
|cash_advance.create_advance|POST /api/v1/cash-advances|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/cash-advances/page.tsx|172/133/39/125|
|cash_advance.edit_advance|PUT /api/v1/cash-advances/{advance_id}|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/cash-advances/page.tsx|16/2/14/2|
|cash_advance.linked_document_detail|GET /api/v1/cash-advances/{advance_id}/documents/{link_id}|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|7/3/4/3|
|cash_advance.confirm_advance|POST /api/v1/cash-advances/{advance_id}/confirm|{"approve": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|236/221/15/210|
|cash_advance.reject_advance|POST /api/v1/cash-advances/{advance_id}/reject|{"approve": ["warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|22/4/18/4|
|cash_advance.repayment_accounts|GET /api/v1/cash-advances/repayment-accounts|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|8/2/6/2|
|cash_advance.repayment_voucher|POST /api/v1/cash-advances/repayment-voucher|{"operate": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|44/38/6/35|
|cash_advance.list_repayments|GET /api/v1/cash-advances/{advance_id}/repayments|{"view": ["staff", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|31/20/11/16|
|cash_advance.repay_advance|POST /api/v1/cash-advances/{advance_id}/repayments|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/cash-advances/page.tsx|81/34/47/30|
|cash_advance.revoke_repayment|POST /api/v1/cash-advances/repayments/{repayment_id}/revoke|{"operate": []}|最小办理或原业务上下文；须参照页面实测清单|37/0/37/0|
|cash_advance.verify_advance|POST /api/v1/cash-advances/{advance_id}/verify|{"operate": ["staff", "warehouse_admin"]}|frontend/src/app/(dashboard)/cash-advances/page.tsx|227/222/5/211|
|secure_uploads.read_upload|GET /uploads/{file_path:path}|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|200/67/133/67|
|main.root|GET /|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|1/1/0/1|
|main.health|GET /health|{"view": ["staff", "supervisor", "warehouse_admin"]}|最小办理或原业务上下文；须参照页面实测清单|2/2/0/2|
|access.catalog|GET /api/v1/access/catalog|{"view": ["warehouse_admin", "super_admin", "supervisor", "staff", "warehouse_labor"]}|最小办理或原业务上下文；须参照页面实测清单|4/4/0/4|
|access.my_actions|GET /api/v1/access/me|{"view": ["warehouse_admin", "super_admin", "supervisor", "staff", "warehouse_labor"]}|最小办理或原业务上下文；须参照页面实测清单|1/1/0/1|
|access.choices|GET /api/v1/access/choices/{module}|{"view": ["warehouse_admin", "super_admin", "supervisor", "staff", "warehouse_labor"]}|最小办理或原业务上下文；须参照页面实测清单|119/57/62/57|
|access.migrate|POST /api/v1/access/migrate|{"operate": ["warehouse_admin", "super_admin"]}|最小办理或原业务上下文；须参照页面实测清单|12/5/7/5|
