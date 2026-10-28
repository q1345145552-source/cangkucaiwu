# 最终运行命令与隔离位置

Python `/tmp/supplier01-py312/bin/python`；Node `/Users/xiongliu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node`；PostgreSQL数据 `/private/tmp/permissions-round7-env/pgdata`，仅127.0.0.1:65519。凭据只使用合成round7角色与测试签名串，sitecustomize加载local_guard，禁止非本地网络及.deploy/.ssh读取，不替换业务鉴权。

- 全量：在本工作树运行 `python backend/tests/permission_round7/full_sharded.py full-current-final06b`。确切四组用例/参数见raw-logs/full-current-final06b.command.json及每个shard.command.json/environment.json。收集使用 `pytest --collect-only -q -o addopts=`，只是避免pytest.ini额外-q变为按文件汇总；执行仍完整原配置。四个全新库round7regression1..4，各自uploads，UUID schema/临时SQLite/PGlite夹具再隔离。脚本为一次性证据运行，重复运行不得覆盖日志或原库；独立验收应使用新隔离环境。
- 资金链：cwd `/private/tmp/permissions-round7-env`；`ROUND7_DATABASE_URL=postgresql+asyncpg://round7@127.0.0.1:65519/round7 ROUND7_RUN=chain-final06c python /private/tmp/permissions-round7-20261028/backend/tests/permission_round7/prior_targets.py round3 versioned authorized-cash`。PYTHONPATH包含隔离guard与本轮backend；fixture限定cwd、端口和库名。
- 成本基线：cwd `/private/tmp/permissions-round7-cost-baseline-20261028/backend`；PYTHONPATH仅guard与该overlay/backend；DATABASE_URL/INCOMING_TEST_DATABASE_URL指向round7baseline；GIT_DIR指向精确基线worktree的Git元数据。`pytest tests/test_cost_funds_debt.py tests/test_cost_funds_debt_postgres.py tests/test_fund_disbursement.py tests/test_cash_advance_repayments.py tests/test_employee_advance_expense.py tests/test_employee_advance_funding.py tests/test_payroll_cash_advance.py tests/test_reimbursement_payments.py --tb=short -rA --junitxml=.../cost-baseline-final06.xml`。Node/PGlite路径同full_sharded.py，外部服务密钥为空。
- 投影补证：当前与上述基线各运行 `PYTHONHASHSEED=0 pytest tests/test_cost_funds_debt.py::test_pagination_category_exact_payer_and_shared_list_projection -o addopts= -vv --tb=long --junitxml=.../cost-projection-{current,baseline}06b.xml`；分别用round7regression/round7baseline。两次exit1，完整失败断言比较见报告。第一次06仍截断的日志保留，不作为完整比较。
- 类型与构建：独立前端拷贝 `/private/tmp/permissions-round7-env/frontend`，`tsc --noEmit` 与Next生产构建。raw-logs/tsc-final05、build-final05均exit0；拷贝hash与提交源码一致见RUNTIME-EVIDENCE-MATCH。
- 停服务：仅对已核对命令的本轮API/Next/proxy PID发SIGTERM；`pg_ctl -D /private/tmp/permissions-round7-env/pgdata stop -m fast -w -t 30`退出0。停止后lsof无监听，lsof退出1在此表示无匹配，不是停止失败。

原始退出码全部保留于EXIT-CODES.json。全量exit1和成本exit1不会被报告成通过；collect/中间夹具/主动停止等失败分别保留。没有skip/xfail掉有效失败断言。
