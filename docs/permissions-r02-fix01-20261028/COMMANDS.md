# 本地复核命令与环境

只可用于新建的本机合成数据库。`partial_acceptance.py`和旧目标脚本会重建指定round2库的public schema；不得指定真实数据库。脚本限定127.0.0.1和round2库名，运行目录不得有.env。固定示例密钥仅用于合成测试。

环境：Python `/tmp/supplier01-py312/bin/python`；PostgreSQL `/tmp/supplier01-pgserver/pgserver/pginstall/bin/`；Node `/Users/xiongliu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node`。项目工作树 `/private/tmp/permissions-round2-20261028`。以下命令在 `/private/tmp/permissions-r02-fix01-env` 运行。

```sh
LC_ALL=C /tmp/supplier01-pgserver/pgserver/pginstall/bin/initdb -D /private/tmp/permissions-r02-fix01-env/pgdata -A trust -U round2
/tmp/supplier01-pgserver/pgserver/pginstall/bin/pg_ctl -D /private/tmp/permissions-r02-fix01-env/pgdata -l logs/postgres.log -o '-h 127.0.0.1 -p 65349 -k /private/tmp/permissions-r02-fix01-env' start
/tmp/supplier01-pgserver/pgserver/pginstall/bin/createdb -h 127.0.0.1 -p 65349 -U round2 round2
ROUND2_DATABASE_URL=postgresql+asyncpg://round2@127.0.0.1:65349/round2 /tmp/supplier01-py312/bin/python /private/tmp/permissions-round2-20261028/backend/tests/permission_round2/partial_acceptance.py
```

首次initdb未设置LC_ALL，locale错误；后用LC_ALL=C成功，均保留日志。环境当前已停止，不需要为阅读证据启动。

旧目标脚本复跑：将`backend/tests/permission_round2`加入Python sys.path，import run_acceptance as suite；将suite.OUT指向`docs/permissions-r02-fix01-20261028/original-target`后`asyncio.run(suite.main())`。不能直接覆盖旧目标证据目录。

回归环境变量：`PYTHONPATH=/private/tmp/permissions-round2-20261028/backend`、`DATABASE_URL`和`INCOMING_TEST_DATABASE_URL`均为上述65349本地URL、`SECRET_KEY=synthetic-fix01-only`、`UPLOAD_DIR=/private/tmp/permissions-r02-fix01-env/uploads`。运行`python -m pytest`下列绝对文件并`--junitxml=logs/regression-final.xml`：

- backend/tests/test_fund_disbursement.py
- backend/tests/test_fund_item_controls.py
- backend/tests/test_fund_receipts.py
- backend/tests/test_reimbursement_payments.py
- backend/tests/test_disabled_financial_reversals.py

候选对照：工作树内`git archive 11d032a41d0d39d770285ce5367ea4d15a2e8e51`解包到`/private/tmp/permissions-r02-fix01-env/baseline`，相同环境变量（PYTHONPATH和测试路径改指baseline/backend）、相同5文件测试，输出baseline.log/XML。不checkout覆盖当前分支、不fetch。测试各自使用隔离schema或临时SQLite；均为合成数据。

前端源未变更：在`/private/tmp/permissions-round2-env/frontend`复用原本地依赖（已检查源码和工作树逐文件一致），使用上述Node执行`node_modules/typescript/bin/tsc --noEmit`及`NEXT_TELEMETRY_DISABLED=1 node node_modules/next/dist/bin/next build`。Python执行`-m compileall -q /private/tmp/permissions-round2-20261028/backend/app`。每条命令stdout/stderr写入本次logs并单独记录实际退出码，无忽略错误。

结束仅停止本次集群：`pg_ctl -D /private/tmp/permissions-r02-fix01-env/pgdata stop -m fast`。没有启动HTTP监听服务，HTTP测试为真实ASGI路由和鉴权。

收集证据：工作树中`python3 backend/tests/permission_round2/collect_partial_evidence.py`；校验回归失败集合、源码摘要、前端一致性、受保护路径与本地停止状态，不连接网络。
