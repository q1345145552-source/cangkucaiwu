# 第二轮本地验收

仅从没有 `.env` 的独立目录运行。目标脚本只接受 `127.0.0.1` 的 `/round2` 数据库，**会重建该专用数据库的 public schema**；不得传入共享或生产连接。服务由本轮新建的 `/private/tmp/permissions-round2-env/pgdata` 提供。

`fixtures.py` 是从第一轮复制到本轮的合成夹具，使用真实应用、JWT 和数据库；不改第一轮脚本或证据。

- `run_acceptance.py`：角色上限、所属仓库、代录/关联员工、状态、批量原子性、重复并发、失败回滚。输出本轮 `target-requests.json` 和 `target-status.json`。176条记录中并发条目含两次实际请求，共177次。
- `browser_fixture.py`：通过真实申请、核验、批准接口准备待处理页面样例；合成令牌只写隔离环境，不进仓库。
- `browser_proxy.cjs` / `browser_acceptance.cjs`：仅本地服务，角色入口、手机视口和旧缓存换号；另外确认CSS已加载。
- `build_report.py`：实际注册路由和目标证据覆盖、动作表及旧预期对照；不连数据库。
- `collect_validation.py` / `collect_manifest.py`：从原始日志/XML及源码校验生成基线对照和环境边界说明。

完整命令、退出码、环境、角色、未测范围及结果见 `docs/permissions-round2-20261028/validation-manifest.json`、`REPORT.md` 和 `raw-logs/`。

旧相关测试中“菜单授权即允许管理”“审批即付款”的期望已改为本轮目标；合法金额、历史和回滚断言保留。未修改业务去满足已知基线失败，没有添加 skip/xfail 或放宽类型配置。本轮目标验收使用实际停用守卫；历史撤销内部回归夹具不是接口开放证明。
