# 第四轮 fix01 已本地提交，待独立复验
marker permissions7-r04-fix01-20261028。独立验收发现合法+json媒体类型绕过本人报销附件归属，原第四轮未通过独立验收。
当前基线 ec2666f915db561554d666b32de445d59a4ec835；工作树/private/tmp/permissions-round4-20261028；分支codex/permissions-round4-20261028，开始时干净。
当前接续：上述修复及最终真实验证已完成。新增320请求、原275记录、前轮277/265 HTTP均通过；最终283/239回归仍8/5失败，3继承未验证保留；完整tsc/build0。原始日志、前后数据库证据及逐项失败对照见docs/permissions-r04-fix01-20261028。自有PG已停止，临时依赖链接移除。补修提交43eaec0fa0488341d16c4a89d33eb53cd1ddf464已完成；最终交接提交及完整HEAD见docs/permissions-r04-fix01-20261028/COMMIT-HANDOFF.md和最终回复。现在停止等待独立复验，不第五轮。
严格仅本地/合成数据库/本地commit；不push/fetch/部署/SSH/.deploy/生产/真实数据，不改模型/库存计价/财务口径，不派其他会话，不第五轮。每次压缩先重读最新fix01指令及r04-prompt.txt与本顶部。独立证据 reviews-r04-01 位于协调接续目录，保留原样。

--- 以下是修复前历史记录，不构成fix01通过 ---
# 第四轮进行中
唯一标记 permissions7-r04-20261028。
每次压缩先完整重读当前提示：/Users/xiongliu/.codex/visualizations/2026/10/19/01a15255-f18d-7002-b020-50e27f71b2f8/权限七轮接续-20261028/r04-prompt.txt，再读本顶部并核对实际Git。不得恢复第二轮、第三轮补修或旧供应商任务。
工作树 /private/tmp/permissions-round4-20261028；分支 codex/permissions-round4-20261028；基线HEAD 1602e8133ebea004eb2d17d20e41187bab46ccd0。从已核实干净的第三轮建立独立工作树，不混桌面改动。
边界：仅本地代码、独立合成验证和本地commit；不push/fetch/部署/SSH/.deploy/生产凭据/任何生产连接/真实数据。不改模型、库存计价、成本公式或期初库存，不创建自动任务、不联系其他会话；完成第四轮提交后停止，不第五轮。
已完成：完整读第四轮提示、第三轮fix01报告与兼容说明，核实第三轮提交链/干净状态，建立本轮分支。前轮277及265目标通过；283回归275通过8历史失败，3条缺费用对象断言未验证，保持透明不改金额口径。
待做：读取逐断言表和失败原证据；枚举A正式记账及旁路、B规则/员工敏感字段、C本人审批、D员工自助、E前端审计兼容真实路由/字段/服务；实现最小权限修复及真实正反例、身份切换页面验证；前轮目标与有效回归、完整tsc/build；更新F01-F19/T01-T13与限制报告；停服务，本地提交、核对本轮HEAD后交付停止。

## resume01 纠偏
上一轮压缩后错误回复了第二轮旧交付，并未完成第四轮。协调纠偏标记 permissions7-r04-resume01-20261028；已重新完整阅读本轮提示和本文件，核实本轮分支/HEAD仍为上述基线，仅本目录未跟踪。该旧回复不构成第四轮交付。本轮持续实施，最终必须核对新增第四轮提交，不再以第二轮报告结束。

## 实施进度（resume01）
已实际修改后端：round4_access动作上限/严格选仓/审计摘要，employee_access正式有效唯一绑定与自助；正式记账、薪资/扣款规则、员工敏感字段；请假/代录/补卡/加班独立审批；个人报销备用金view=self；新增本人补卡申请（既有history表保存pending，独立审批才调用现有补卡，未改模型）。前端写按钮/敏感字段限制、财务自助导航、我的申请与补卡组件。
隔离PG /private/tmp/permissions-round4-env/pgdata，127.0.0.1:65389（round4/round3/round2/regression），运行中；全部合成。Python /tmp/supplier01-py312/bin/python。前端node_modules链接既有 /private/tmp/permissions-round3-env/frontend/node_modules，无fetch。
新增脚本 backend/tests/permission_round4/{fixtures,inventory,acceptance,extra_scenarios,prior_targets,regression}.py。真实注册路由234条已枚举（新增补卡后须更新）。首批target03全通过；扩展target04中生成费用拒绝先被原guard400拦截（已移除冗余新guard，改测试有效payload及原400），设置测试原用错PUT已改POST。待重跑target05。
第三轮原277请求复跑通过，证据 docs本轮/round3；第二轮原脚本完成，待读最终状态并跑partial；prior回归283仍在session68314，日志本轮env/logs；待related回归及基线逐项比较。tsc03退出0，build01退出0（后续改动后须最终再跑）。原始日志均在本轮env/logs，最终复制到本轮docs/raw-logs，不覆盖旧证据。
待做：扩展本轮目标至正常记账/并发/回滚/补卡/附件等全部通过、frontend真实浏览器角色与切换、相关回归调整合法前置保留断言、历史8失败/3未验证证据。补完整A-E动作表与F/T关闭表、兼容回退、原始证据清单。检查资金申请自助还需避免新政策（预支仍须原资金来源，由合法登记入口选，不静默默认）。最终停止本轮服务并本地提交，核实第四轮新HEAD后才交付。不可再回复第二轮旧完成。
2026-10-28 后续：前轮原脚本第三轮277、第二轮178+87=265均0失败。prior回归初次283有9失败，8原历史 +1旧自助伪造查询原期望忽略200；已加明确403及不伪造的本人GET，保留金额/范围断言。related初次233附近47失败，含历史源码恒等/旧菜单、授权改变及新scope对超管缺属性500（已修为实际403）、请假已批准→驳回旧合法流程误拦（已恢复独立者可驳回），不能简单声称历史失败。正在独立baseline worktree /private/tmp/permissions-round4-baseline @1602e81 跑related基线，session12952；同regression数据库，因此不要并发新回归。更新旧相关测试只替换合法前置/新拒绝，原数值断言保留；源码恒等不删改。
本地页面第一跑39组合中37通过：主管operating录入支出按钮漏禁用（已修），另主管员工“编辑”是合法现场事实入口、测试误判（已收窄测试，入弹框检查银行禁用）。18项主管/财务/无菜单自助与旧管理员缓存均200。API服务session93804:65390，前端62191:65391，代理17823:65392（都回环）；API/前端需在最终变更后重启/重建再验。
证据采集纠正：regression.py初版用固定related文件名，第二次相关回归启动覆盖了初次.log（原始XML已在结束前备份为regression-related-initial.xml；首轮失败详情仍在工具输出）。已修采集器自动递增文件名，后续不覆盖。交付须明确该一次初始原始log缺口，不能声称全部尝试原始log完整。当前related第二跑session93354；target06 session13402。此前baseline相关回归已完成exit1，原始baseline日志/XML保留。

## 第四轮完成待独立验收
实际275本轮目标记录通过；前轮第三轮277、第二轮178+87=265 HTTP最终复跑通过。prior283项275通过8原金额/显示失败；related239项234通过5源码/旧菜单失败，基线233项216通过17失败。失败逐项全文与3未验证沿用说明见REPORT/failure-comparison，不能声称全绿。浏览器39组合通过，追加5项正向检查通过；完整tsc-final-02/build-final-04退出0。最终补充管理员本人审批及代录/补卡403，独立主管可批准管理员员工请假200。
本机临时共享依赖缺失已从本地缓存恢复至r04-env独立目录，无网络；工作树node_modules临时链接已移除。所有本轮服务已停止（API77820、Next77826、proxy76395、PG65389），数据保留为合成环境。原始日志复制raw-logs；初次related日志覆盖缺口如实记录，未伪造。
业务/测试/审计交付即将本地提交，完整实际提交号见COMMIT-HANDOFF.md（提交后生成）。停止等待独立验收，不第五轮，不恢复第二轮旧任务。报告、逐动作237注册行、189未直接请求列表、兼容及F/T对照齐备。未push/fetch/部署/生产，未改模型和库存计价/成本公式。

fix01进度：已把附件检查移动至报销create/edit的已校验模型输入、写入前；新personal_receipts服务支持真实备用金文件的本人归属，不继承管理读取权限。员工JSON字段按路由模型检查，Form白名单按路由Form声明检查，不看header拼写。合法缺失header仍由FastAPI解析并完整校验，显式空header安全415。
首轮新增314请求除显式空header预期外都正确；FastAPI把显式空header当缺失而接受，因此现在明确拒绝415而非放行，失败原日志/JSON在fix01/attempt-01保留。新增员工Form头大小写/空格变体未知字段拒绝测试。原275及二三轮目标正在重复，tsc/build已成功（首次build缺临时依赖，缓存hash核对恢复107包后成功）；prior回归仍8失败，related运行中。后续须最终新增测试全通过、相关回归最终代码再跑、文档及本地commit并停服务。当前PG仅本地65389运行，其他UI服务未开。
