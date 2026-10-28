# 2026-10-28 物流入口、弹窗和收货交付记录

## 工作树与边界

- 独立工作树 `/tmp/hide-logistics-modal-style-20261028`，分支 `codex/hide-logistics-modal-style-20261028`，主支基线 `c5e10d9a8942826cb0c7a217dd22912ceff33187`。
- 原工作树 `/Users/xiongliu/Desktop/海外仓财务系统` 的分支是 `codex/supplier-optimization-20261026`，起始 HEAD `79fae5f59d710e1e4e8176b325f0bfe861b4269a`。其中员工和授权办理相关未提交改动未覆盖、未携入；未读 `.deploy`。
- 最新要求取代此前“点遮罩关闭”：所有弹窗改用显式退出按钮，未保存内容先确认。成功结果也使用已有关闭按钮。
- 只使用本地 PostgreSQL 随机隔离 schema、虚构供应商/SKU/采购/账户和合成图片。未连接生产、未改真实数据、未部署。
- 后端仅修改收货服务的照片校验和存储失败提示；审批、付款、金额算法、库存计价和数据库结构未改。

## 物流入口和供应商类型

关闭物流分类页签、物流报价、物流模板、多供应商物流导入、供应商行物流入口、详情物流报价、物流比价，以及通用办理事项中的 7 个物流动作。采购下单不出现物流报价。采用可恢复的 UI 开关；原函数/组件、接口、权限目录及表（包括 `supplier_route_prices`）全部保留。

新建供应商类型下拉实测只有 **耗材商**。

历史物流供应商**不改分类、不停用、不改记录，只隐藏该分类入口**，遵循同一要求的“不改数据”。没有执行迁移或停用。合成旧物流档案前后仍 category_id=2、is_active='true'，不出现在耗材商列表；历史结算供应商引用未受迁移影响。

管理账号实际的 6 组、23 个入口，顺序为：

1. 档案：供应商档案 → 耗材商 → 新建供应商。
2. 报价：产品报价 → 阶梯与有效期 → 耗材模板 → 多供应商耗材导入。
3. 采购：采购单列表 → 采购审批 → 收货验收 → 收货差异。
4. 结算：应付账单 → 付款计划 → 对账单。
5. 库存：标准SKU目录 → 耗材库存 → 盘点。
6. 分析：比价 → 供应商采购分析 → 采购汇总 → 价格监控 → 采购价差月报 → 采购风险看板。

桌面逐项打开/下载/取消共 23 个入口；手机 390×844 下全部可横向滚动到达。

## 弹窗样式与关闭

报价相关实际弹窗：报价供应商选择、产品定价（含产品新增）、数量阶梯报价（新建和编辑状态）、产品 SKU 人工映射、产品 Excel 预览、通用 Excel 预览、采购下单、非最低价原因、疑似重复应付/费用核对。有效期是数量阶梯弹窗内的日期字段；没有另造一个系统原本不存在的“独立有效期弹窗”或“产品编辑弹窗”，报价版本编辑在数量阶梯报价中。

全项目扫描 **142 处定义、55 个文件**，包括已隐藏物流定义。原扫描有 17 个“不直接写白底”的候选：**1 个真实透明表单**（供应商选择引用未定义的 `.modal-content`）、6 个已有 `.modal-sm` 白底、10 个正常的深底图片浏览器。已修复该真实缺陷，并给普通弹窗统一白底、深字、50% 黑遮罩及手机边界；图片浏览器保留深底。

移除 **115 处遮罩关闭事件、涉及 43 文件**；其余定义本来没有遮罩关闭。所有 142 处已检查，无剩余遮罩关闭事件。费用审批、加班、付款计划、工资签字图片这 4 个原本只靠遮罩退出的预览补了 X。

输入、日期、选择、复选框、文件、数量加减、勾选采购商品和增删阶梯均纳入未保存保护。文案统一为：**已填内容将丢失，确定关闭吗？** 取消确认保留弹窗和内容；未填写直接关。业务保存按钮不被拦为关闭；原有提交中限制、原请求、切仓切账号清理不变，Escape 不绕过关闭。

桌面/手机共 13 个弹窗状态实测：白底 `rgb(255,255,255)`、深字 `rgb(17,24,39)`、不透明度 1、遮罩 `rgba(0,0,0,0.5)`，卡片均在视口内。产品表单、阶梯新建/编辑与日期、导入确认、采购勾选及收货的未保存关闭有实际浏览器验证。仅预览/取消的检查前后，合成产品、报价、采购、应付、流水、库存数量与供应商状态完全一致。

## 收货：先复现再修

修前正常图片路径**未复现**“成功但状态不变”：POST 200，`not_received → received`，新增 1 批、数量 3、图片路径非空，列表显示“已收货”。完整修前返回、明细和截图见 `receipt-baseline.json` / `.png`。这次基线走原有低于门槛直接生效路径；最终回归另外走了待审批→审批通过→收货。

四种可能的排查结果：

1. 照片随 `/suppliers/purchase-orders/{id}/receive` 的 multipart 请求和数量一起上传，不是先调用独立图片接口。失败必须明确提示。
2. 页面正常发送 POST，参数中有 file/items/request_key，未复现未调用或漏图。
3. 正常后端已经更新 receipt_status、flow_status、收货批次、图片路径。因此保留原累计、差异、库存登记和事务算法。
4. 原页面依赖刷新整个列表，读取失败被吞掉后显示空列表；非 JSON 响应只产生解析异常。注入刷新 503、损坏图片和响应丢失，可明确验证这些失败分支，已补修。

修复行为：

- **照片仍必传**。前后端拒绝空/无效照片和超过 **10MB** 的到货照片，明确提示“图片上传失败，请重试…”，保留数量、备注和原请求。没有改成无图收货。
- 图片存储异常回滚整个事务，不保存半条事件，给出中文存储失败提示。
- 即使 HTTP 200，也必须有 receipt_event_id 和有效 receipt_status 才显示成功；非 JSON、对象、数组错误均给可理解提示。
- 保存后重新 GET 当前采购详情，同步收货列表、采购列表和已开详情。刷新失败按已确认成功的返回更新状态，同时提示“收货已保存，详情刷新失败，请重新打开核对；不要另建收货批次”。
- 响应丢失时沿用原请求、原数量、原照片重试，仍只保存一批。

最终实际流程：采购 3 件→待审批→审批通过→登记收货→填 3→传 PNG→确认。HTTP 200，receipt_status=received、flow_status=completed、has_diff=false，收货表新增 1 条 active 记录，received_quantity=3、photo_path 非空。**完整响应和前后明细见 `receipt-browser-actual.json`，后台逐项结果见 `receipt-regression-actual.json`**；交付消息给出最终事件号、图片路径和完整记录链接。

错误验证：txt、10MB+1 图片被页面明确拒绝且未 POST；伪 PNG 损坏内容被后端 400 拒绝，状态仍 not_received、0 批；存储失败 500 回滚，原请求恢复后仅 1 批。模拟服务端成功但响应丢失后，页面保留待核对状态；原请求重试仍为 1 批、3 件。随后注入详情刷新 503，列表立即显示已收货，页面明确提示已保存、刷新失败。手机验证收货卡片不越界、遮罩不关、填写退出先确认。

## 验证、原始证据及限制

原始日志位于本工作树的 `docs/hide-logistics-modal-style-20261028/`，并归档到桌面独立验证记录目录。按仓库规则，日志/JSON/XML/截图不提交 Git；提交本报告和可重跑测试。

| 检查 | 数量 | 最终日志 | 退出码 |
|---|---:|---|---:|
| 供应商、报价、门槛、采购、收货、应付付款、库存和本轮新增回归 | 115 项，0 skip | backend-verified.log / .xml | 0 |
| 物流开关和原处理函数保持 | 7 动作、7 按钮、62 原处理函数 | feature-release.log | 0 |
| 全项目弹窗 | 142 处 / 55 文件 | modal-audit-release.log / modal-inventory.json | 0 |
| 原有 Excel UI | 12 项 | excel-final.log | 0 |
| 收货文件和响应 | 13 项 | receipt-response.log | 0 |
| 桌面/手机 UI | 13 弹窗状态、23 入口、未保存确认 | browser-final-ui.log / browser-actual.json | 0 |
| 收货浏览器全链路 | 审批/照片/失败/重试/刷新/手机 | receipt-browser-final-ui.log / receipt-browser-actual.json | 0 |
| 完整类型检查 | 全部前端 | types-delivery.log | 0 |
| 本地生产构建 | 全部前端 | build-delivery.log | 0 |

保留了未通过尝试：最初脚本把带行号的产品文案按产品名精确查找，以及测试快照端点未登记导致 403，均修正验证脚本后重跑。后端一次失败来自历史“收货接口函数保持原样”断言；没有改/删/skip 该断言，把大小检查放回收货服务并恢复接口原样后 115 项通过。已有弃用警告保留。

未测/限制：未连接线上调查真实失败请求；正常成功路径状态不变在基线未复现，不能声称已证明线上根因。手机为 Chrome 390×844，未逐一测实体 iOS/Android。142 处做完整静态覆盖，未逐个办理所有业务；实际浏览器集中在相关入口和表单，另有后端回归。不以“全部正常”代替这些限制。

本轮从干净主支基线起步，没有提交原工作树未完成补修。已有独立物流模板、导入预览、人工映射、防重复提交继续保留。本轮新增 UI 开关、弹窗守卫/样式、显式关闭标记、4 个图片 X、收货失败/刷新处理和对应测试。按会话已有授权本地提交并推主支，不部署；最终 SHA 和远端核对见交付消息及本地 Git 记录。

## 全项目弹窗逐文件清单

下面按源码定义计数；同一个定义的新建/编辑状态只计一处。完整逐处行号和标题在本地 `modal-inventory.json`。

| 文件 | 定义数 | 弹窗标题（动态标题保留源码形式） |
|---|---:|---|
| `frontend/src/app/(dashboard)/accounts/page.tsx` | 2 | {editingId ? "编辑收款账户" : "新建收款账户"} / 内部转账 |
| `frontend/src/app/(dashboard)/attendance/page.tsx` | 5 | {t("att_leave_form_title")} / {t("att_proxy_leave_form_title")} / {t("att_rest_day_form_title")} / {t("att_absence_form_title")} |
| `frontend/src/app/(dashboard)/cash-advances/page.tsx` | 3 | {editing ? "编辑垫款单" : "新建垫款单"} / 驳回垫款单 / 垫款单 #{documentsAdvance.id}· 关联单据 / {documentDetail.snapshot.document_number} |
| `frontend/src/app/(dashboard)/clock-in/page.tsx` | 1 | {t("clock_photo_confirm")} |
| `frontend/src/app/(dashboard)/clock-records/page.tsx` | 2 | Image / detail / shared dialog |
| `frontend/src/app/(dashboard)/credit/page.tsx` | 3 | {detail.customer_name}{detail.rating && ( &lt;span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs border font-medium ${RATING_COLORS[detail.rating]}`}> {(() => { const I = RATING_ICONS |
| `frontend/src/app/(dashboard)/customers/page.tsx` | 2 | {reconciling.company_name}· 客户对账 / {editingId ? "编辑客户" : "新建客户"} |
| `frontend/src/app/(dashboard)/deduction-templates/page.tsx` | 1 | Image / detail / shared dialog |
| `frontend/src/app/(dashboard)/employee-advances/page.tsx` | 3 | 确认作废预支 / 驳回预支 |
| `frontend/src/app/(dashboard)/employee-deductions/page.tsx` | 1 | Image / detail / shared dialog |
| `frontend/src/app/(dashboard)/employees/page.tsx` | 10 | 泰国证件 / 银行资料 / 护照 & 工作证 / {canReadPay ? "薪资 & 转正" : "转正"} / {detailEmp.name}{detailEmp.is_deleted && &lt;span className="ml-2 text-xs font-normal bg-red-500 text-white px-2 py-0.5 rounded-full align-middle">已删除&lt;/sp |
| `frontend/src/app/(dashboard)/expense-approvals/page.tsx` | 4 | Image / detail / shared dialog |
| `frontend/src/app/(dashboard)/expense-fund/page.tsx` | 5 | 新建备用金账户 / {editingItem ? "编辑开销" : "添加开销"}- {expenseAccount?.employee_name} / 充值备用金 / &lt;Image size={18} />凭证查看 / 确认作废这条开销？ |
| `frontend/src/app/(dashboard)/fund-review/page.tsx` | 1 | &lt;ImageIcon size={18} />凭证查看 |
| `frontend/src/app/(dashboard)/group-order/page.tsx` | 5 | 发起拼单 / 参与拼单 / 拼单详情 / &lt;Users size={14} />参与仓库 / 完成采购 / 取消拼单 |
| `frontend/src/app/(dashboard)/income-expense/page.tsx` | 1 | {tab === "income" ? "新建收款" : "新建付款"} |
| `frontend/src/app/(dashboard)/incoming/page.tsx` | 1 | Image / detail / shared dialog |
| `frontend/src/app/(dashboard)/labor-efficiency/page.tsx` | 2 | 录入订单数 / 补录工时 |
| `frontend/src/app/(dashboard)/market/page.tsx` | 1 | 上架商品 |
| `frontend/src/app/(dashboard)/modification-logs/page.tsx` | 1 | 修改详情 |
| `frontend/src/app/(dashboard)/my-payslip/page.tsx` | 1 | {selected.employee_name} |
| `frontend/src/app/(dashboard)/operating/page.tsx` | 6 | 录入运营支出 / 编辑运营支出 / 删除凭证 / 删除支出 / 变更历史 |
| `frontend/src/app/(dashboard)/other-income-expense/page.tsx` | 1 | {editing ? "编辑收入" : "新建其他收入"} |
| `frontend/src/app/(dashboard)/overtime/page.tsx` | 4 | Image / detail / shared dialog |
| `frontend/src/app/(dashboard)/payable/page.tsx` | 7 | 本次采购、收货与应付复核 / 新建应付账单 / 编辑账单 / 作废账单 / 付款 / 订单量 vs 耗材支出 趋势对比 |
| `frontend/src/app/(dashboard)/payment-plans/page.tsx` | 4 | 新建付款计划 / {showDetail.plan.plan_name} / 执行付款计划 |
| `frontend/src/app/(dashboard)/payroll/page.tsx` | 9 | {showPayslip.employee_name}{showPayslip.is_supervisor && &lt;span className="ml-2 inline-flex rounded bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">主管&lt;/span>} |
| `frontend/src/app/(dashboard)/recharge/page.tsx` | 3 | 编辑充值申报 / 删除申报 / 变更历史 |
| `frontend/src/app/(dashboard)/reconciliation/page.tsx` | 2 | 确认匹配 |
| `frontend/src/app/(dashboard)/reimbursement/page.tsx` | 4 | 报销详情 {detail.is_fund_linked === "1" && ( &lt;span className="px-2 py-0.5 rounded-full text-xs bg-purple-50 text-purple-700 font-normal flex items-center gap-1">&lt;Lock size={11} />关联备用金&lt;/span> )}&lt;span className={`px |
| `frontend/src/app/(dashboard)/salary-templates/page.tsx` | 1 | Image / detail / shared dialog |
| `frontend/src/app/(dashboard)/settings/page.tsx` | 1 | 编辑用户 |
| `frontend/src/app/(dashboard)/supplier-skus/page.tsx` | 1 | {editing ? '编辑 / 停用标准SKU' : '新建标准SKU'} |
| `frontend/src/app/(dashboard)/suppliers/page.tsx` | 18 | {quoteEntry==='logistics'?'物流报价':quoteEntry==='tiers'?'阶梯与有效期':'产品报价'}· 选择供应商 / 产品定价 - {data.find((s:any)=>s.id===productSupplierId)?.name // ""}{(()=>{const s=data.find((x:any)=>x.id===productSupplierId); retu |
| `frontend/src/app/(dashboard)/warehouses/page.tsx` | 1 | {editId ? "编辑仓库" : "新建仓库"} |
| `frontend/src/components/BatchMakeupModal.tsx` | 1 | 批量补卡 |
| `frontend/src/components/CashAdvanceRepaymentHistory.tsx` | 2 | 垫款 #{advance.id}归还与使用记录 / 已用于工资 {money(payrollUsage.payroll_used_amount)}{loan.currency} / 已用于报销 {money(reimbursementUsage.reimbursement_used_amount)}{loan.currency} / 已用于员工预支 {money(employeeAdvanceUsage.employ |
| `frontend/src/components/CashAdvanceRepaymentModal.tsx` | 1 | 归还垫款 #{advance.id} |
| `frontend/src/components/ClockRecordsGrid.tsx` | 3 | Image / detail / shared dialog |
| `frontend/src/components/CostIdentity.tsx` | 1 | {challenge.permission_required?"需有原单权限的人员核查":challenge.hard_duplicate?"同一发票不能重复登记":"跨渠道疑似费用，请核对"} |
| `frontend/src/components/CreditShipments.tsx` | 3 | {editing ? "编辑发货" : "登记发货"} / 发货记录 #{selected.id} / 作废发货 #{voidFor.id} |
| `frontend/src/components/ExcelImportDialog.tsx` | 1 | {title} |
| `frontend/src/components/InventoryBoard.tsx` | 1 | {kinds[form.kind]} |
| `frontend/src/components/InventoryControls.tsx` | 1 | {form.locked?'核对原盘点/配置请求':form.kind==='count'?'登记本次实盘':form.kind==='controls'?'安全库存与用量阈值':form.decision==='approve'?'审核盘点并生成调整':'驳回盘点'} |
| `frontend/src/components/MakeupBatchHistory.tsx` | 1 | 确认撤销这一批吗？ |
| `frontend/src/components/PayableDetail.tsx` | 1 | 应付详情 {bill?.bill_number // `#${billId}`} / 本次疑似重复核对留痕 / 逐笔实际付款（不补造历史） |
| `frontend/src/components/PayableDuplicateDialog.tsx` | 1 | {challenge.hard_duplicate ? "同一发票不能重复登记" : "疑似重复，请核对本次业务"} |
| `frontend/src/components/ProductImportDialog.tsx` | 1 | 产品Excel预览与确认 |
| `frontend/src/components/PurchaseReceiptInfo.tsx` | 1 | Image / detail / shared dialog |
| `frontend/src/components/ReimbursementPaymentHistory.tsx` | 1 | 确认撤销这笔报销付款吗？ |
| `frontend/src/components/ReimbursementPaymentModal.tsx` | 1 | 报销付款 #{reimbursement.id} |
| `frontend/src/components/SkuProductMapping.tsx` | 1 | 产品SKU人工映射 |
| `frontend/src/components/SupplierQuoteEditor.tsx` | 1 | 数量阶梯报价 · {product?.product_name} |
| `frontend/src/components/common/FormModal.tsx` | 1 | {title} |
| `frontend/src/components/ui/ConfirmDialog.tsx` | 1 | {title} |
