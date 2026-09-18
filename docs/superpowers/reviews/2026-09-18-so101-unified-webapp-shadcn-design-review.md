# SO-101 单 Web 服务设计独立审查

- 审查日期：2026-09-18。
- 审查角色：GPT-6 Astra / High，独立于设计作者。
- 结论：`CHANGES_REQUIRED`。
- 审查对象：`docs/superpowers/specs/2026-09-18-so101-unified-webapp-shadcn-design.md`，233 行。
- 对象 SHA256：`f986ff881ef6e34f0c8fcd44e1444bb91dc8ff0f957863f5334bc66118111548`。读取正文前及形成报告前均已核验。
- 源码基线：`84620fc0529779a27c6985f8717d78f0386e0135`；源码直读根为 `/private/tmp/so101-doc-publication.R3yXD0aj/repo`。下文源码行号均指此基线，不指原 `587b` 工作区的旧源码。
- 证据根：`/tmp/so101-debug-unified-webapp-design-20260918/`，由主协作者登记并维护账本；审查者未写账本。
- 本报告是静态设计审查记录；未执行测试、ROS、仿真、远端操作、安装、commit 或 push，不构成 runtime PASS。

## 审查方法与边界

完整读取冻结设计，核对仓库 `AGENTS.md`、项目 `so101-dev` 技能及系统地图、分层证据、验收和账本参考。源码核对覆盖 Teleop API、service、command coordinator、ROS action、Tasks service、Validation API/lease/production、浏览器客户端及租约恢复、投影和实际前端配置。本报告属于审计记录，不对正文作人类化编辑。

并行预算设计和计划的本地 SHA256 与设计第 200 行记录一致，分别为 `5e085f98e9926591fbefd3d6e16c16b33bfc9956df9221c46f383b310553657b`、`cd1b606fd8a40d7bb6e576f6f59a6ef5abcb45a8bee7e2a669c7b7a40bfc8789`。未修改这些文件，也未接管其独立执行任务。

## 必须修改的问题

### R1 — [P1] Execute All 需要一个跨子步骤的持久 reservation

设计位置：第 99–105、109–111、192 行。

设计按 operation/command ID 定义 reservation，并要求长 action 保留至终态及清理；第 192 行又承诺保留 `execute-all`。基线的 Execute All 不是一个服务端 action：`src/so101_teleop/web/src/api/client.ts:25–29` 先调用 `/plans/{plan_id}/execute`，成功后再调用 `/gripper/execute`，两次 `post` 分别生成新的 command ID（同文件第 10–15 行）。按当前文字为每个单独 command 获取和释放 reservation，arm action 终态之后、gripper 请求之前存在全局 `IDLE` 窗口。

具体交错为：arm 完成并释放 → Validation start 获得 reservation → Execute All 的第二步到达。此时夹爪步骤会被拒绝，保留了一个部分完成的 Execute All；若浏览器第二步迟到且另一域已经完成，其夹爪指令还可能作用于已经变化的现场。两个 HTTP 请求各自原子并不能满足这个组合操作的原子占用。

修改建议：明确 Execute All 是单个服务端复合操作，或采用等价的、服务端授权且持久化的 parent operation/reservation。arm 与 gripper 子步骤绑定同一个 parent、frozen payload、runtime identity 和执行 generation；其他入口不能借 parent ID 获取授权。子步骤继承 reservation，不重新竞争，也不在子步骤终态释放父 reservation。只有整个复合操作收敛才释放；在两步之间断网、取消、超时或崩溃时保留可查询的部分结果，禁止浏览器恢复后自动补发夹爪动作。旧的单步 API 可以继续存在。

所需验收：在 arm ACK、arm terminal 和 gripper dispatch 三个切点竞争 Validation start；整个复合操作期间均不得入场。覆盖 arm 失败、第二步失败、两步之间浏览器断线/Web 重启、重复 parent ID 与不同 payload。计划还应逐项辨明 `home`、workflow 内部连续动作和暂停 checkpoint 的父操作终态，避免以一次子命令完成代替整个逻辑操作收敛。

### R2 — [P1] 安全取消必须绕过现有命令锁和普通执行队列

设计位置：第 103、107、119–125、196、216–218 行。

“保留原安全路径”和不隐藏 cancel 还不足以保证取消能送达。基线 `src/so101_teleop/so101_teleop/server.py:728–730` 的 `cancel` 与执行命令共同进入第 858 行的 `CommandCoordinator.run`；`control.py:55–56` 在长 action 持锁时直接拒绝新命令，返回 `SERVER_BUSY`。此外，基线 `server.py:538` 的取消只检查 `_active_goal`，该字段在 arm 执行第 411 行设置，gripper 的 handle 在第 423–427 行仅是局部变量。照搬这条路径既不能及时取消持锁的 arm，也不能证明取消了对应的 gripper。

设计已为 owner-channel watchdog 要求独立性，但没有明确浏览器安全取消、lease-maintenance 取消和 watchdog 取消在服务端调度/IPC/child action 层的共同可达契约。有界的普通 IPC 队列仍可能被长动作占满或堵住，reservation 自身也不能成为 cancel 等待的锁。

修改建议：规定独立且有界的安全控制通道/优先处理路径，取消不获取新的运动 reservation，不等待普通 mutation lock、普通 IPC backlog 或 action completion。目标必须是持久记录对应的精确 operation/action identity；arm、gripper 和复合操作子 action 均须可识别，不能用一个泛化的 latest goal 指针代替。明确浏览器取消与维护/watchdog 内部取消各自 authority；租约失效或维护故障时，由内部安全 authority 处理其拥有的 action。取消 accepted ACK 之后仍保留 reservation，直到 action terminal 与所需停止/cleanup 证据成立。无可靠取消能力的 backend 应拒绝相关运行能力或保持明确 blocked，不能报告取消成功。

所需验收：长 arm/gripper action 尚未完成且普通执行队列饱和时，授权 cancel 必须在既定安全 deadline 内送达正确 owner；同时验证 lease-maintenance 故障、浏览器租约过期、Web owner heartbeat 丢失、重复 cancel、旧 action ID 及 foreign identity。不能只验证按钮可点击、HTTP 可返回或 watchdog timer 被触发。

### R3 — [P2] 多标签排他需要定义可由服务器验证的页面实例绑定

设计位置：第 85–89、119–121、219 行。

第 89 行要求“不能因多个标签保存同一 ID 就同时控制”，但仅要求新标签通过服务器验证，并未定义服务器用于区别两个页面实例的身份或交接规则。基线 Teleop `server.py:594` 只核对 lease ID 和到期时间；Validation `expert_validation/lease.py:122–136` 核对 lease ID、generation、service session 和到期时间。两个页面若持有同一组值，在下一次 renewal 改变 generation 前都能通过这些检查；普通全局 reservation 只防止动作重叠，不阻止两个标签轮流提交命令。基线 Validation 还从 session storage 恢复 service session 和 lease（`web/src/expert-validation-app.tsx:68–89`），恢复提示不能充当独立的页面实例证明。

修改建议：在设计中选定服务器能执行的单 controller-instance 绑定及显式交接规则。例如每个 document 建立新的 instance identity，经服务器确认后取得该域的控制绑定；恢复只读投影与恢复执行权分开，已存在 controller-instance 时新标签保持只读，显式交接原子递增 execution authority generation 并使旧实例失效。需要同时说明刷新、back/forward、断线重连和同一页面切路由的身份生命周期，且 lease renewal generation 不应被误当成运行中 action 的 generation。若使用兼容 header 或新增握手端点，应明确旧客户端的兼容行为；单靠 localStorage、BroadcastChannel 或浏览器自报同一个 ID 不能满足服务端保证。

所需验收：两个页面携带相同有效 lease/session/generation，同时或交替尝试 mutation；只能已绑定实例成功。覆盖重复标签、刷新恢复、旧连接迟到、显式交接期间竞争及 renewal；换页不应产生第二个 controller-instance 或夺取原控制权。

## 其余覆盖情况

| 审查边界 | 当前结论 |
| --- | --- |
| 单 Web 服务、非 Web ROS child、无 ROS factory 导入 | 设计边界清楚，不允许用双服务 launcher 冒充合并。 |
| 双向仲裁与入口闭合 | 默认全局互斥、legacy/internal/后台 dispatch、非运动 POST 和 cleanup fence 已纳入；需补 R1 的复合操作生命周期。 |
| durable intent/ACK 与 crash 恢复 | dispatch 前持久 intent、accepted/terminal/cleanup 分层、未知结果 blocked、重启不自动接管/重放已明确。 |
| ownership 与 IPC | 固定 executable、封闭 schema、权限/token/peer UID、deadline、PID reuse 和 foreign-process 禁止边界已明确；需补 R2 的安全通道调度和精确 action 目标。 |
| 路由、health、schema | router 抽取、保留 `/tasks`、排除 API/artifact fallback、聚合 readiness 与 liveness 分离、单 OpenAPI 投影已有明确要求。 |
| 切页、重连、lease | 根级 subscriptions/heartbeat 和快照补序正确；需补 R3 的实例级控制权契约。 |
| preset/Tailwind | 明确认定实际 Tailwind `3.4.17`，没有把 CLI 的 v4 检测当事实；Radix 非 preset 字段、smart merge 和必要时显式 v4 升级门槛清楚。精确 registry/版本冻结属于实施计划前置。 |
| 地图与旧功能 | accepted manifest、单一 `pixels_per_m`、完整左栏、同半径状态圈、真实几何与状态分离、5+1 关节和 Tasks 兼容均已明确。 |
| 预算边界 | exact N、未知档禁用、不静默降档、新 R 重新资格与独立 promotion、不改并行预算任务均已明确。 |
| 分层验收 | 明确自动回归、包级门控、授权 live 及独立物理/视觉证据；设计通过不替代运行资格。需加入上述三个问题对应的具体竞争和故障切点。 |

## 复审条件与证据保留

修订设计并冻结新的 SHA256 后，独立复审 R1–R3 的正文契约和验收项；本首次报告保留，不覆盖。此次没有修改 spec、产品源码、预算文件或账本，没有创建运行批次，没有删除证据。已有任务 evidence root 继续 retained；本审查未新增 archived run 或 deletion candidate。

即使修订后结论为设计 `PASS`，也仅表示静态设计可进入后续审批与实施计划阶段，不表示单端口服务已上线、ROS 安全取消已验证或任何 N 的资源资格通过。
