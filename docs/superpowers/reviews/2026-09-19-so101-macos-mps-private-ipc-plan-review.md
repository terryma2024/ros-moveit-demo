# SO-101 macOS MPS 与私有 IPC 实施计划独立审查

Verdict: PASS

## 审查对象与边界

- 审查模型：GPT-6 Astra / High。
- 审查方式：独立静态审查；完整阅读设计、设计审查、实施计划、适用 `AGENTS.md` 和项目 `so101-dev` 的相关证据、测试、账本及交接约束。
- 计划：`docs/superpowers/plans/2026-09-19-so101-macos-mps-private-ipc-implementation.md`。
- 最终计划 SHA-256：`cd098f4025eb00cb1beae0b0072dcaca35010c9ab1c1ac2334b4bda37df3ead2`。
- 设计 SHA-256：`480da6dcdfea1da988f9f4e706c8340dbb6d7283200c27bb723859119145db1b`。
- 设计审查 SHA-256：`05a483e59dff596c37cbad737d85fa0a096242a7f6c9a1324a22c1c8329b71c8`。

本报告只批准上述哈希对应的实施计划进入执行。审查者未修改计划、产品源码或账本，未启动 DST、测试、模型、仿真、GUI 或 Linux 命令，未提交或发布代码。执行 worktree 的 HEAD、依赖、模型兼容性及 DST goal 状态仍须按计划现场回读；静态 PASS 不代表这些运行门已通过。

## 阻塞项

无未解决的阻塞项。

## 审查中发现且已修正的事项

以下问题由计划作者修订，审查者已回读最终文件。行号均指上述最终计划。

1. **v4 平台契约不能因 Linux 验收延期而删除。** 原 Task 1 只允许 MPS，与设计 §4.1 的两个闭合组合冲突；原 Task 10 又把不调用 NVML/proc-fd 扩大到全部 v4。Task 1 第 147 行现已保留 Linux `cuda + proc_fd_unix` 和 Darwin `mps + darwin_private_path_unix`；Task 10 第 259 行将平台排除规则限定于 Darwin v4。Linux 现场回归仍由 Task 15 延期。
2. **真实故障验收不能在 timeout 与 Broker crash 中任选一个。** Task 13 第 290 行现分别要求 inference timeout、活动 Worker cancel 和 Broker crash 的原始证据，符合设计 §9.1。普通 Worker cancel 保留既有安全取消契约；timeout/Broker crash 才要求全 W2 pool 重建，没有借验收新增普通 cancel 的产品行为。
3. **连续 5/5 不能跨越环境污染或有效失败累计。** Task 14 第 297–301 行现明确冻结 commit、配置与生命周期，并规定 VALID 失败、INVALID、提前终止或证据缺失立即中断序列；即使只修复环境，下次有效批次也从 1/5 开始。
4. **新 DST 会话必须证明实际接收和真实预算。** 第 36–45 行新增投递门，核验 launcher/help、唯一 tmux、task-local 配置、实际 goal ID、`roundsStarted`、`maxGoalRounds=100`、handoff receipt 和首个真实工具动作。Task 0 第 127 行回读同一 checkpoint；pane 故障只可恢复同一 session/goal，不得重置或创建第二 goal。

## 可执行性与范围核对

| 审查项 | 最终计划位置 | 判定依据 |
| --- | --- | --- |
| 现有分支和 worktree | 第 15–18、31、104–105、126–129 行 | 执行路径与分支均为精确值，禁止新 checkout、第二执行器和第二证据根；旧进程所有权及 dirty state 必须回读。 |
| 模型与执行器 | 第 3、16、36–45、324 行 | Sol 编写及结果审查、Astra 独审、tmux 内 DST 实现的职责明确；100 轮来自真实 goal 状态，不能仅写入提示词。 |
| v3 冻结与 v4 exact W2 | Tasks 0–2、10 | 先运行基线，再做闭合 schema 的 RED→GREEN；Darwin 仅 W2，v3 解析与 CUDA/NVML 语义不混改；Linux v4 契约保留。 |
| MPS 准入与 ready | Tasks 2、3、8 | 固定 headroom、共享 deadline、helper reap、claim、SPAWNING/ACK/ACTIVE、spawn bootstrap、fallback=0、真实模型 warm-up/synchronize 和单执行 lane 均有对应测试或现场门。 |
| 私有 IPC | Tasks 4、5 | 固定 canonical 短路径、0700/0600、字节长度、新路径重启与精确 cleanup；Client/Server 不恢复 token、generation、lease、receipt 或 peer 认证。 |
| 输入与结果生命周期 | Tasks 6、7、9 | snapshot 的路径/类型/大小/SHA/shape/dtype 校验和保留边界明确；一次性 consume 与 cancel 互斥，旧 Broker 绑定失效；恢复由实际 parent/spawner/reaper 执行。 |
| TDD 与安装证据 | 第 24–27 行、Tasks 0–12、16 | 环境失败不算 RED，测试非零收集；普通测试排除 benchmark；source、package/CTest、copied install、OpenAPI 与 served bytes 分别取证，代码改变后重跑受影响门。 |
| 真实 W2 与连续稳定性 | Tasks 13、14 | 两个 slot、共享 Broker、三类失败路径、安全取消、物理/controller/MoveIt/GUI、新 epoch 与五次 FULL_RESTART 都是必需证据。 |
| Linux 延期 | 第 20 行、Task 15 | 使用 `DEFERRED_ENVIRONMENT`，保留明确原因、恢复条件与 gate 列表；禁止用 macOS 结果声明 Linux、跨平台或发布资格。 |
| 授权边界与收尾 | 第 17、26–27 行、Task 16 | 仅 task-owned 仿真和 scoped 本地提交；禁止硬件、sudo、全局配置、foreign process stop、证据删除、main 合并与远端发布；保留 retained/archived/deletion-candidate 分类。 |

任务顺序可执行：先冻结契约与环境，再实现 probe、Supervisor、地址与协议、snapshot、请求 registry 和 MPS Broker，随后组合恢复/安装/API，最后做现场 W2 与连续稳定性验收。新增模块、受影响测试、关键断言、提交边界和完成门均已列出，执行器无需重新选择架构或扩大授权。具体 executable、测试 nodeid、dependency closure 和服务参数由 Task 0/12 的现场发现与 provenance 门确认。

100 轮是执行上限，不是完成保证。若依赖、真实 MPS 模型兼容性、GUI 或 package runner 无法满足门槛，必须保留失败证据和 checkpoint，按 Task 16 报告 PARTIAL/FAIL；不得为了达到轮数内完成而缩减验收或将延期项写成 PASS。后续若改变计划中的接口、信任边界、恢复语义或验收要求，应重新审查相应修订，不能沿用本报告的哈希批准。
