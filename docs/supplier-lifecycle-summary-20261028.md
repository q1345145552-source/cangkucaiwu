# 供应商删除与停用验收（2026-10-28）

## 范围与基线

工作树 `/private/tmp/supplier-import-main-20261027`，分支 `main`，基线 `ad9311e083db245ded0054c1351978aa25c327f9`。只修改供应商删除、启停及相关入口与测试；无数据库迁移，不修改报价、成本、库存计价或其他供应商字段定义。仅本地合成数据，未接触生产、未部署、未推送。

## 修改

- `supplier_lifecycle.py` 检查所有直接供应商外键及报价阶梯、收货、库存、风险快照关联；有记录返回中文 400 和分类数量。空供应商可删除。
- 删除角色上限为仓库管理员；主管、财务即使历史授权仍返回指定中文 403。保留超级管理员既有特殊限制。
- 删除和启停使用仓库锁、行锁；提交异常也在捕获范围，失败回滚。启停记录操作者、所属仓库、时间及前后状态。
- 页面增加启停按钮和状态标记；停用供应商不进入采购选择，不能新增采购；历史查看不受影响。

## 实际返回（供应商 20 为隔离数据库合成样本）

1. 删除：HTTP 400，`该供应商已有业务记录，请改用停用；该供应商有 1 条产品报价；1 条物流报价；1 条跨境物流报价；3 张采购单；1 张应付账单；1 条产品报价版本；1 条阶梯报价；1 条收货记录；1 条库存记录；1 条风险看板记录`。
2. 异常：删除/停用/启用 × 审计写入/flush/commit 九种注入故障均返回中文 400；另有真实 PostgreSQL 即时及延迟外键失败两例，均 400，业务数据及审计回滚。正常操作 200。权限失败按要求 403，不是 500。未宣称覆盖所有可能的运行环境故障。
3. 创建空供应商返回 `{"id":21,"message":"创建成功"}`，删除 HTTP 200 `{"message":"删除成功"}`。
4. 停用 HTTP 200 `{"message":"已停用","id":20,"is_active":"false"}`；采购选择无 20，历史采购、应付、产品查询均 200，供应商名称保留。启用 HTTP 200 `{"message":"已启用","id":20,"is_active":"true"}`，采购选择恢复。

主管与财务删除均 HTTP 403 `{"detail":"供应商删除只能由仓库管理员操作"}`。

## 验证及证据

真实应用路由、JWT 鉴权和独立 PostgreSQL，未使用永远放行的鉴权。测试共 **93 通过、0 失败、0 跳过**，其中新增生命周期测试 19 项。覆盖真实外键、事务回滚、独立关联类别、跨仓、非法状态、重复并发删除、启停历史保留，以及供应商、SKU、报价、收货、采购和应付相关回归。旧删除测试由 409 改为要求的 400，历史保留断言保留。

运行文件：`test_supplier_lifecycle.py`、`test_supplier_workflow_round1.py`、`test_supplier_sku_round5.py`、`test_supplier_quotes_round6.py`、`test_supplier_receipts_round3.py`、`test_supplier_acceptance_854e389.py`、`test_management_inventory.py`。

完整前端 TypeScript 检查与生产构建退出码均 0。手机尺寸 390×844 的真实浏览器点击删除显示中文提示，无白屏；启停成功；财务和主管没有删除按钮。浏览器验收退出码 0。没有逐页手工验收整个系统，不宣称全系统后端测试已执行。

原始文件保留在 `/Users/xiongliu/Desktop/供应商删除停用验收-20261028`；临时隔离环境 `/private/tmp/supplier-lifecycle-20261028`。`logs/verified.xml` 为最终 93 项结果，`verified.log/exit`、`tsc.log/exit`、`build.log/exit`、`browser-verified.log/exit` 为原始日志及退出码；`supplier-lifecycle-20261028/actual.json` 为接口实际返回，`browser-results-verified.json` 及截图为页面证据。早期夹具调试失败日志保留，最终结果未覆盖旧日志。合成身份令牌、数据库文件和依赖未归档进仓库。

执行环境：Python `/tmp/supplier01-py312/bin/python`；数据库仅 `127.0.0.1:65519/lifecycle`；测试设置 `INCOMING_TEST_DATABASE_URL` 指向该库并由夹具创建独立 UUID schema；启用了仅允许本地端口且禁止生产凭据读取的既有测试 guard。具体运行命令及输出见原始日志。本轮提交仅包含代码、测试与本摘要，不提交大日志、JSON 或截图。
