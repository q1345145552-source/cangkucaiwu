# 最终14项成本失败的实际断言复核

全量最终14项均在精确基线相同合法夹具中失败，不能称通过。COST-ASSERTION-COMPARISON.json保留全部原始断言，12项仅归一化Python内存地址后逐字一致。

另外两项逐项补证：

- 成本分页/共享投影：首次pytest截断且字典打印顺序不同，不能据此判同根因。使用相同PYTHONHASHSEED=0、清除额外quiet参数、-vv分别实际复跑当前和基线，两次exit1，完整断言18879字符。完整比较仅随机生成的收据PNG文件名不同；只归一化该32位十六进制文件名后全部一致，包括原6≠8、data及cost_basis的实际差异。证据cost-projection-{current,baseline}06b.log/xml、COST-PROJECTION-VERBOSE-COMPARISON.json。
- 垫款工资7000：只有合成执行disbursed_at时间不同；仅归一化该字段后全部断言一致，包括expense_record_id为None及原成本金额/条数失败。没有忽略金额、来源、状态或业务对象ID。

结论：本次到达的14组原成本断言在基线与当前具有相同实际业务差异；没有发现新增权限回归，但不等于全系统无缺陷。成本原期望未改，须按COST-DECISIONS.md另行独立核对口径。
