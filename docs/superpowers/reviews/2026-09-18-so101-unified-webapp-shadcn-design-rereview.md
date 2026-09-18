# SO-101 单 Web 服务设计独立复审

- 复审日期：2026-09-18。
- 复审角色：GPT-6 Astra / High，独立于设计作者。
- 结论：`PASS`，仅限本对象的静态设计审查。
- 审查对象：`docs/superpowers/specs/2026-09-18-so101-unified-webapp-shadcn-design.md`，275 行。
- 对象 SHA256：`4e11f3a385e8d078523ee3c3b3b11d2ec372215188cfbdabdea824c35dd54fa1`。
- 源码基线：`84620fc0529779a27c6985f8717d78f0386e0135`；基线读取根为 `/private/tmp/so101-doc-publication.R3yXD0aj/repo`。
- 首审报告：`2026-09-18-so101-unified-webapp-shadcn-design-review.md`，SHA256 `bbe2a1962a77c00f9105cbc413601afb2903c545899e4275e06b082559dab8a8`；保持原文和原 `CHANGES_REQUIRED` 结论，不覆盖。
- 唯一任务证据根：`/tmp/so101-debug-unified-webapp-design-20260918/`；账本仍由主协作者单写。

## 复审范围

重新完整读取修订后的 12 节设计，并检查新增契约与原单服务边界、路由、域租约、持久仲裁、IPC、组件迁移、既有业务、预算资格及验收之间的关系。本轮不是只按关键词核对 R1–R3。适用的仓库规则、`so101-dev` 技能和参考约束沿用首审已完整读取的版本。

复审未修改设计、源码、账本或预算文档，未运行产品测试、ROS、仿真、远端命令、安装、commit 或 push。结论只说明当前设计可进入书面设计审阅和后续实施计划阶段，不说明功能实现或运行资格成立。

## 首审问题关闭

| 问题 | 修订位置 | 复审结论 |
| --- | --- | --- |
| R1 / P1：Execute All 两个单步 reservation 之间的 admission 空隙 | 第 132–140、259 行 | 已关闭。新增服务端 `POST /plans/{plan_id}/execute-all`；parent 在 dispatch 前持久化，child 由服务端产生并继承同一 reservation，arm terminal 到 gripper dispatch 不经过 `IDLE`。冻结 payload/runtime/execution generation；partial、unknown、取消和重启禁止补发未执行 child。home 与 workflow 的连续动作、暂停及显式 resume 同样受父生命周期约束。 |
| R2 / P1：cancel 被普通锁/队列阻塞且无法准确取消 gripper | 第 160–170、260 行 | 已关闭。Web/child 两端的专用安全处理能力及独立 control IPC 不等待普通命令锁、执行线程池、backlog 或 action completion。arm/gripper/parent-child registry 绑定真实 goal identity；先封住后续 child dispatch，再取消精确活动目标。delivery、stop confirmation 与 cleanup 分层，accepted ACK 不释放 reservation；取消能力不能证明的 backend 不获对应运行许可。 |
| R3 / P2：相同 lease 值不能区分多个页面实例 | 第 98–110、261 行 | 已关闭。服务器随机 proof 仅留 document 内存，经 WebSocket 握手绑定实际通道和 revision；每域唯一 controller、逐请求 authority headers、显式 handoff，以及旧通道迟到拒绝构成服务端约束。execution generation 与 lease renewal generation 分开；新 document、刷新和重复标签不自动恢复执行权，SPA 切页复用原 provider。 |

三个问题均有对应的竞争、断线或故障切点验收，不以 UI disabled、HTTP 成功或缓存状态替代服务端结果。

## 完整设计与新增交互复查

| 边界 | 复查结果 |
| --- | --- |
| 单服务与域故障隔离 | 一个 HTTP/WS 进程、监听端口和 bundle 的边界未变。ROS 仅在非 Web child；无 ROS 时 factory 可加载，历史可读，未知运动 intent 仍全局阻塞。新增实例控制通道属于同一个 Web 服务，不构成第二个 Web listener。 |
| 全局仲裁与 TOCTOU | 双向 admission、所有 legacy/internal/background mutation、dispatch 前持久 intent 和短事务均保留。复合 parent 的继承授权仅由服务端发给确定 child；普通单步 API 不能借 parent ID 绕过。handoff 要求全局无未收敛 owner，不能在活动 parent 期间提升 generation 夺权。 |
| 取消与子步骤竞争 | parent cancel 先原子禁止后续 child dispatch；sequencer 在关键切点重新核验冻结 authority、runtime 和取消状态。安全 lane 只更新短临界状态，不在锁内等待长动作；停止未确认继续 blocked。因此独立取消能力没有变成释放 reservation 或任意 reset 的旁路。 |
| durable crash 恢复 | intent、accepted、terminal、cleanup 的证据层保持分离。Web restart 使 proof/controller epoch 失效，但不清除旧 reservation/owner；不接管存活执行器、不重发未知命令、不恢复旧 parent。新增内存 proof 不被当作持久 owner 记录的替代品。 |
| 租约、实例与刷新 | 两域 proof/lease 独立；legacy Tasks 复用 Teleop controller。renewal 不改变运行中 action 的 execution generation；channel revision 只约束连接。硬刷新丢失执行 proof 后保持只读是明确设计选择，不能以复制旧 lease 恢复。原 controller 丢失后的恢复仍受 lease 失效、owner 和 cleanup 证据约束。 |
| 兼容性边界 | 第 110 行明确旧路径和业务 DTO 保留，但 acquire/renew/mutation 新增 authority 要求，旧客户端返回 `CONTROLLER_INSTANCE_REQUIRED`。这是显式的控制客户端升级要求，不是未经说明的兼容保证；历史读取继续兼容。新增 endpoints 应纳入同一个 OpenAPI 和生成客户端，不产生第二套手写协议。 |
| 身份与通信 | 新 proof 用于实例绑定，不被宣称为用户认证或 TLS；现有受限网络边界和 same-origin/Origin 检查明确。IPC 仍是私有 Unix socket、服务 epoch token、peer UID、封闭 schema、固定 executable 和有界消息；没有引入任意命令或通用 RPC。 |
| 路由与 health | `/tasks` 真实能力、assets alias、artifact 权限、API namespace 排除 SPA fallback、聚合 readiness/liveness 和无重复 OpenAPI operation 的要求均保留。没有用 Validation ready 伪装 ROS ready。 |
| 设计系统可实施性 | 实际 Tailwind `3.4.17` 是迁移起点，CLI v4 检测不能覆盖源码事实；Radix 与 preset 元数据分开。若冻结 registry 需要 v4，要求整套 compiler/PostCSS/CSS/tokens/依赖迁移、锁文件冻结和构建验证；未写成已经安装或已兼容。 |
| 布局、几何与功能 | accepted manifest、真实几何/等比投影、同半径状态圈、左栏尺寸、结果列数、证据 Sheet、两个指定视口和无障碍要求一致。Teleop 保留真实 5+1、现有 backend capability 和规划/执行分离；不为截图增加虚构能力。 |
| workflow 限制 | pause/step/resume 保留 run parent；删除 checkpoint 不是释放证明。新增安全 lane 不补造 backend 不支持的 workflow stop，无法证明停止时保持 blocked；这些限制不能在实现中被解释成无条件运行资格。 |
| 并行预算 | exact N、无 K、unknown/rejected 禁用、不静默降档、新 R 重新资格与 operator promotion 保留。新增 controller channels、安全 lane、sequencer 及相关线程/进程同样属于实际 runtime footprint，受第 243 行统一身份与重新资格约束。独立预算任务未被改写或接管。 |
| 验收与权限 | 新增第 259–261 行明确断点测试，且原安装 provenance、普通包测试、NVMe scratch、Chrome/物理证据、授权运行窗口等要求仍在。静态 PASS 不授权部署、接管、恢复、profile promotion 或真实机械臂动作。 |

本次没有发现新增的阻断设计问题，未保留未关闭的 P1/P2 finding。

## 实施计划需要落实的已有契约

以下是设计已要求的实施细化，不构成本次追加的设计修改条件：为新增实例/parent 状态查询与错误响应建立单一 schema；把 parent cancellation 与 child dispatch 的线性化点、目标 accepted 前后的取消处理、持久事务边界落到代码和故障注入测试；冻结安全 lane 的正值 deadline/容量和前端 registry/依赖版本；在能力矩阵中记录各 backend 的可取消范围。不能用本次 PASS 跳过这些实现和验收工作。

## 对象与证据保留

并行预算设计 SHA256 `5e085f98e9926591fbefd3d6e16c16b33bfc9956df9221c46f383b310553657b`、实施计划 SHA256 `cd1b606fd8a40d7bb6e576f6f59a6ef5abcb45a8bee7e2a669c7b7a40bfc8789` 及首审报告哈希均再次核对，未改变。

已有 evidence root 与首审记录继续 retained；本轮仅新增此复审报告，没有新增运行批次、archived run 或 deletion candidate，没有删除证据。本结论只绑定页首对象 SHA；后续修改设计后不得把本 PASS 当作新对象已经审过。
