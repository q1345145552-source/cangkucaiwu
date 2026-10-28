# 授权格式、转换与安全回退

本轮不增加 SQL 列、不改 ORM 模型。复用 `users.extra_permissions` JSON 列；新格式为 `['@wf-actions:1', 'employees:view', 'employees:operate', ...]`。动作目录中的稳定动作 ID 映射至模块三档，个人身份、对象字段、仓库、状态和本人禁批禁付继续独立校验。

|原值|运行行为/显式转换|证据|
|---|---|---|
|null、空列表|无附加管理授权；转换为仅版本标记，不补全权限|extended-02|
|已识别中文旧菜单|旧业务守卫继续执行，同时受本轮角色上限；显式转换取角色上限内三档|matrix-final、两组第五轮回归|
|未知中文、旧键值|不识别项不授予新权限，转换审计保留原值及 unknown_legacy_values|extended-02|
|非列表、非字符串、未知版本、混合新旧、重复/越上限新键|拒绝，不默认全权；整批转换前验证|extended-02|
|主管历史全勾|不恢复核薪、资金批准、账户管理、记账或财务规则|matrix-final、前轮回归|
|财务受限菜单|只转换实际旧菜单；本人/仓库和独立付款约束保留|extended-02、final-round3-versioned|
|已是 v1（包括撤权后仅标记）|重复迁移跳过，不重新授予|extended-02、migration-cli-apply.log|
|禁用账号|不改变停用状态，不能登录；转换仍受管理员目标范围|extended-02|
|跨仓或混合合法非法批次|整批拒绝、业务数据不变|extended-02|

不在启动时自动执行本轮转换。旧启动补权跳过版本标记、空值、非法值及未知旧值，避免重启重新补权。旧测试中“空主管自动获得修改日志”的预期因此变化，不能为了通过旧测试恢复补权。

管理员使用 `POST /api/v1/access/migrate`，提供明确 `user_ids` 与 `reason`。服务先对全部目标加锁、检查账号管理能力、本人及所有授权仓库，再转换；事务中的审计失败全量回滚。权限编辑必须给调整原因；旧请求不能把 v1 悄悄降回中文格式。授予、撤回、迁移记录操作者、目标、仓库、前后授权、原因和来源版本；不记录密码或令牌。

隔离本地命令（仅允许本轮 65509 合成数据库，不能指向生产）：

```
cd /private/tmp/permissions-round6-env
/tmp/supplier01-py312/bin/python /private/tmp/permissions-round6-20261028/backend/tests/permission_round6/migrate_local.py --database-url postgresql+asyncpg://round6@127.0.0.1:65509/round6browser --actor-id 1 --user-ids 3 --reason 'synthetic delivery idempotency'
```

默认为 dry-run；明确追加 `--apply` 才调用原迁移服务并提交。dry-run 和对已版本化用户 apply 的退出码均为 0；真实旧值转换、回滚与并发撤权以 API 验收为准。该工具不能作为生产执行指令。

回退不能把 v1 原始值直接交给旧菜单代码，也不能自动将历史全选恢复。无列可删除。安全处理为保留本轮中央角色上限、v1 解析、字段投影与审计的兼容版本；由管理员逐账号核对授予，仍使用 v1 写入。若仅回退 UI，后端保持本轮解析与权限守卫。不得删除审计记录、恢复已停用付款撤销，或通过旧补权脚本恢复权限。完整回退到第五轮二进制不属于安全兼容回退，未验证、不得直接执行。
