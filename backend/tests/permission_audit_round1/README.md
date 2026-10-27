# 第一轮权限现状复现

这些测试保存 **当前行为**，包括缺陷。`expected-current.json` 的200不代表授权目标正确。未来修复后应另建目标验收测试，并更新现状基线，不能以保持这些越权200为业务要求。

只可用一次性本机数据库。先用本机 PostgreSQL 创建UTF8数据库 audit_round1，用户仅服务于本地合成测试。不要使用项目.env、.deploy、生产连接或真实身份。每组创建随机schema；实际应用的路由、JWT、数据库加载和业务服务保持不变；替换的只是本地数据库连接与文件保存目录。ASGITransport不运行启动迁移；Base.metadata.create_all只在本轮合成schema建表，未改项目结构和迁移。

在无.env的隔离目录运行（以下路径为本轮实际环境）：

```sh
cd /private/tmp/permissions-audit-round1-env
AUDIT_DATABASE_URL=postgresql+asyncpg://audit_local@127.0.0.1:65329/audit_round1 /tmp/supplier01-py312/bin/python /private/tmp/permissions-audit-round1-20261028/backend/tests/permission_audit_round1/run_audit.py
```

合成JWT签名密钥在测试内明确写为 synthetic；不会读取真实签名密钥。密码和身份均合成。正常运行退出0，含义仅为当前行为成功复现。任何断言不匹配退出1；拒绝或读取若写数据库也会失败。每次都会更新docs里的原始结果，运行前可复制已有报告供对比。

`inventory.py` 读取实际注册路由及依赖闭包生成登记清单；`expand_matrix.py` 加入独立动作分支、页面调用候选、实测证据；`write_findings.py` 生成已人工审阅的问题清单。源码自动提取不能替代完整语义审阅，未测项在coverage.json逐条列出。

页面：`browser_fixture.py` 只绑定127.0.0.1:65330，使用独立audit_browser schema且关闭应用lifespan；`browser_proxy.cjs` 监听65332，前端65331；`browser_audit.cjs` 仅允许127.0.0.1请求。使用前置供应商批次已构建的前端，135个源文件/配置逐字节比较相同，证据在frontend-build-source-match.json。页面脚本不是全页面验收，未点击全部操作，7场景及一次账号刷新结果分别标注。

前端构建目录、解释器、Chrome、端口是当前机器依赖，不保证在别的机器原样存在。可准备相同依赖后调整这几个测试路径；不得修改业务配置来跑测试。文件fixture和token只落在本机隔离临时目录，不提交token。

未来目标验收见docs中的TARGET-ACCEPTANCE.md；本轮不实施、不自动启动。
