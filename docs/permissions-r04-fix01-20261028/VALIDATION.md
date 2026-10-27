# fix01 最终验证

|项目|结果|日志|退出码|
|---|---|---|---|
|第四轮原目标|275记录，0失败|round4-final.log；round4/status.json|0|
|新增附件/媒体/员工字段/Form|320请求，0失败|round4-final.log；media-status.json、media-requests.json|0|
|第三轮原目标|277 HTTP，0失败|round3-final.log|0|
|第二轮原目标|178 HTTP，0失败|round2-final.log|0|
|第二轮补充|87 HTTP，0失败|partial-final.log|0|
|前轮相关回归|283项：275通过，8失败，0跳过|regression-prior-01.log/xml|1|
|受影响相关回归|239项：234通过，5失败，0跳过|regression-related-01.log/xml|1|
|完整独立tsc|通过，未改配置|tsc.log|0|
|完整Next构建|通过，未改配置|build-02.log|0|
|Python编译与源码差异检查|通过|compile.log、diff-check.log|0|

8项与5项失败的用例集合与第四轮最终证据完全相同，完整失败文本逐项存于failure-comparison.json。比较错误行时仅标准化内存地址，不能据同名测试就认为所有表现完全一致；逐项布尔值与原文保留。原3项不可达断言仍未证明。没有新增skip、xfail、宽松配置或鉴权替身。

首轮新增320前身314有20项显式空Content-Type预期不符，按安全拒绝415修复而非改成放行；第二跑314通过，加入6个Form变体后最终320通过。旧失败尝试保留attempt-01、attempt-02及原始日志。Next首次构建缺本机临时worker依赖，退出1，SHA512校验本地缓存恢复后第二次退出0。

本补修未改前端代码，未重跑页面浏览器组合；原第四轮浏览器证据保留，不冒称本次重新验证。关键后端归属和事务行为直接以真实路由/JWT/PG验证。

差异复核：2项垫款归还错误的字典展示次序/截断不同；垫款工资仅测试实际时间戳不同而关键750/7750及缺费用对象一致；1项AST字典输出次序/截断不同，clock_in.py未被本补修修改。不把被截断内容冒称逐字段等价，详见comparison_note。
