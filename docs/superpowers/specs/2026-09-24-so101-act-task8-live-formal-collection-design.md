# SO-101 ACT Task 8 live 与正式采集设计

日期：2026-09-24

状态：方案已在对话中确认，并通过独立 GPT-6 Astra / High 文档审查；等待用户书面审阅。本文只定义实现与验收合同，不表示接触校准、Task 8 live、W8 资格或正式数据已经完成。

关联文档：

- [双 RGB ACT 总体设计](2026-09-10-so101-act-head-wrist-rgb-design.md)
- [ACT 实施计划](../plans/2026-09-11-so101-act-head-wrist-rgb-implementation.md)

本文收紧总体设计中 Task 7A 至 Task 11A 的边界。发生冲突时，以本文为准。实施计划需在本文书面审阅通过后更新，不能继续执行其中已被本文替换的 Gazebo、W4/W6 逐档测试或内部资源复验要求。

## 1. 目标和范围

本轮补齐四个缺口：

1. 建立可生成、分析并审批新版接触策略的校准链。
2. 让 Web 与 headless CLI 通过同一执行入口驱动 Task 8 live。
3. 用 MuJoCo 完成 Task 8 分阶段验收、完整自主流程和 W8 并发资格。
4. 在相同数据合同下采集 50/10/10 条合格专家 episode。

仿真后端只支持 MuJoCo。系统保留 ROS 2、MoveIt 2、`ros2_control`、双 RGB 相机和 MuJoCo 接触/物理证据，不实现 Gazebo adapter、Gazebo topic/service、Gazebo truth 或失败后回退 Gazebo 的路径。启动配置、依赖或 operation 请求中出现 Gazebo 后端时，入口直接拒绝。

本轮不包含真实机械臂验收。未来硬件 adapter 可以复用业务接口，但不能继承本轮的接触阈值、物理 truth 或仿真通过结论。

Task 12 训练及后续 ACT 部署不在本轮实现范围内。正式数据完成后仍需单独冻结 dataset、campaign index 和策略指纹，才能开始训练。

## 2. 已确认决策

| 主题 | 决策 |
| --- | --- |
| 仿真后端 | 仅 MuJoCo；不再支持 Gazebo |
| 操作入口 | Web 与 headless CLI 共用一个 `UnifiedWorkloadService` 和 campaign owner；每个 Worker 只有一个隔离的 ROS execution child |
| 资源校验 | 只在 campaign 启动入口执行；内部组件不查询 lease 或重新验证资源 |
| 接触校准 | 离线确定性 MuJoCo 样本拟合，加隔离的 ROS/MuJoCo live 评估 |
| 策略批准 | analyzer 只产出 disabled proposal；用户批准精确 `POLICY_FINGERPRINT` 后才允许写 activation receipt |
| Task 8 live | 先逐 phase-prefix 验收，再做完整自主流程连续成功 |
| 正式数据资格 | 只有完整自主流程可进入训练候选；人工操作或 MoveIt recovery 使 episode 失去资格 |
| 并发资格 | W1 冒烟；W1/W2 八场景功能资格；W2 通过后直接以独立 40 场景测试 W8 |
| 跳过档位 | 不测试 W4、W6；W8 也不写成项目的永久全局默认值 |
| 资源瓶颈 | W8 遇到 CPU、GPU、RAM、磁盘、RTF 或 Recorder 瓶颈时停止，等待人工决策；不自动降档 |
| 失败重试 | 业务失败不重试；基础设施中断只允许相同 W8、manifest、config 和 policy 的显式恢复 |
| 正式配额 | Train 50、Validation 10、Offline Test 10；Rollout Validation/Test 不采专家 episode |

## 3. 总体架构

```text
Web / headless CLI
        |
        v
UnifiedWorkloadService.start(spec)
        |
        | startup admission only
        v
AdmittedCampaignContext  <---- immutable manifest/config/policy/resource identity
        |
        v
Campaign owner  <---- heartbeat, lease renewal, fencing, stop, cleanup proof
        |
        v
typed WorkerPort -> child IPC -> one ROS child per Worker -> explicit ROS operation
        |
        +--> Task 8 phase runner -> MuJoCo / MoveIt / controllers
        |
        +--> FixedActCollectionCampaign -> private Recorder -> atomic episode commit
```

`UnifiedWorkloadService.start(spec)` 是唯一启动入口。它在创建任何 Worker、Broker、Recorder 或 ROS child 前完成 admission，并返回不可变的 `AdmittedCampaignContext`。Web 和 CLI 只改变交互方式，不形成两套执行路径。W8 会创建 8 个相互隔离的 ROS execution child，每个 child 绑定自己的 Worker、ROS Domain、namespace、controller 和 MuJoCo session。

Campaign owner 是资源生命周期的唯一持有者。它续租、维护 heartbeat、生成 fencing generation、停止全部 Worker，并在所有 goal、进程、socket、ROS Domain、campaign index 和 cleanup proof 收敛后释放 binding。

内部 Worker、Recorder、Broker、Task 8 phase 和 ROS driver 不读取 GPU lease，不查询资源仲裁器，也不重新验证 campaign 资源。它们只接收业务 payload，以及 `operation_id`、generation、campaign/scenario/episode ID 和审计 hash。GPU UUID 映射在 spawn 前冻结到进程环境；后续不允许组件自行重选设备。

## 4. 启动 admission 与 `AdmittedCampaignContext`

启动入口一次性核对：

- 稳定主机身份、GPU selector 到物理 UUID 的映射及 GPU lease；
- 全局 mutation reservation、owner、service epoch 和 fencing generation；
- MuJoCo-only backend；
- worker count、ROS Domain 池、端口和 socket 路径；
- manifest、runtime config、collection config、contact policy 的 SHA256；
- evidence root、旧 campaign cleanup 和启动资源余量；
- 正式模式下的 W8 资格记录。

任一检查失败时，结果是零动作、零 Worker、零 Broker、零 Recorder 和零 ROS child。已经领取但尚未 dispatch 的 lease 由入口释放。

`AdmittedCampaignContext` 至少冻结以下字段：

```text
campaign_id
operation_id
service_epoch
execution_generation
stable_host_id
physical_gpu_uuid
worker_count
manifest_sha256
runtime_config_sha256
collection_config_sha256
contact_policy_fingerprint
evidence_root
admitted_at_monotonic_s
```

这份 context 是 campaign owner 的资源授权记录，不是要求内部组件逐层传递和复验的 capability token。内部消息只带执行和审计所需的最小字段。资源 lease 在运行中丢失时，campaign owner fence 旧 generation 并停止全部 Worker；恢复必须重新 admission，取得新 binding 和新 generation。

## 5. 接触校准和策略批准

当前接触策略不能靠修改常量直接更新。校准链分为离线生成和 live 评估两段，两段都通过后才形成候选策略。

### 5.1 样本设计

五种状态各采 25 个样本，其中 20 个来自确定性离线 MuJoCo 生成，5 个来自隔离的 ROS/MuJoCo live 运行：

| 状态 | 要证明的边界 |
| --- | --- |
| `no_contact` | 无接触时不误报持物或压缩 |
| `bilateral_touch` | 双指有效接触可以被识别 |
| `over_compression` | 过度夹压会触发硬停止 |
| `micro_lift_slip` | 微抬升过程中的滑移不会误判为稳定持物 |
| `stable_hold` | 离台后稳定双侧持物可以持续成立 |

另外保留桌面单独接触、释放后残余接触和单侧指尖接触作为 negative control。这些样本不能混入五类正样本补数量。

collector 使用独立、保守的 diagnostic hard limits。它不能读取待批准策略来判断该策略自身是否正确，避免循环证明。每个样本保存原始接触流、MuJoCo 状态、ROS 时间、单调墙钟、scenario 参数和来源 hash。

### 5.2 分析和批准

analyzer 从不可变原始证据计算候选阈值、混淆矩阵、false positive/negative、单侧接触行为、时间新鲜度和 stop 行为。输出包括：

- `source_evidence_sha256`；
- collector/analyzer 代码与配置 hash；
- 各状态样本数和排除原因；
- 候选阈值及适用 MuJoCo/模型版本；
- 不可变的 canonical policy payload；
- `POLICY_FINGERPRINT = SHA256(canonical_policy_payload_bytes)`；
- 引用 fingerprint、证据和配置 hash 的 disabled proposal envelope；
- proposal envelope 的精确 SHA256，供审查材料寻址。

canonical policy payload 使用冻结的字段集合和确定性 JSON 编码，包含所有运行阈值、适用的 MuJoCo/模型版本及 `source_evidence_sha256`。用户批准的唯一授权对象是精确 `POLICY_FINGERPRINT`，不是 proposal envelope hash。独立审阅只能确认 envelope、payload 与证据一致，不能代替用户授权。激活通过单独的 approval/activation receipt 记录 fingerprint、批准身份、时间和证据根；它不改写 canonical payload 或 disabled proposal。payload 任一字段变化都会生成新 fingerprint，并重新走批准流程。

策略激活前不得开始 Task 8 live、W8 资格或正式采集。旧数据和旧指纹保留审计，但不能与新 campaign 混用。

## 6. Task 7A：统一执行入口和 typed IPC

Task 7A 扩展现有统一 Worker/child IPC，不增加 ACT 专用旁路。建议接口为：

```python
UnifiedWorkloadService.start(spec) -> AdmittedCampaignContext
WorkerPort.command(operation, payload, audit_context) -> OperationHandle
OperationHandle.cancel(reason) -> None
OperationHandle.result() -> OperationResult
```

`operation` 使用封闭的版本化联合类型，覆盖 Teleop、Tasks、Task 8 live 和正式采集。child IPC 携带：

- `operation_id`、`campaign_id`、`worker_id`；
- generation/fencing token；
- scenario、phase、deadline；
- manifest/config/policy hash；
- 显式 operation 和版本化 payload。

每个 `(campaign_id, worker_id, generation)` 只能有一个 ROS execution child。child 根据注册表路由到明确的方法，不接受任意 import path 或字符串拼接调用。未知 operation、schema 不匹配、旧 generation、过期 deadline、同一键下出现重复 child 或 driver 不可用都 fail closed。不同 Worker 的 child 必须处于不同 ROS Domain 和 MuJoCo session；W8 正常状态是 8 个隔离 child，而不是全服务只有一个 child。

Task 7A 只负责命令所有权和传输。碰撞、接触、释放、时间新鲜度等机器人安全条件仍由 Task 8 业务监督器判定。资源所有权只由 campaign owner 维护，不下沉到 command broker 或 phase runner。

## 7. Task 8 live 验收

Task 8 按以下阶段执行：

```text
SEARCH
  -> APPROACH
  -> CLOSE
  -> MICRO_LIFT
  -> TRANSPORT
  -> ALIGN
  -> RELEASE
  -> RADIAL_RETREAT
  -> FINAL_CHECK
```

### 7.1 Phase-prefix

每个阶段提供 `stop_after`，先独立证明规划、控制器 reference、关节反馈、接触、MuJoCo 物理和 MoveIt Planning Scene 的一致性。phase-prefix 是边界验收，不计完整 Task 8 成功，也不能产生正式 episode。

holding 为 unknown、接触流过期、控制器状态不明或 release 前失败时，系统停止并保存证据。reset/recovery 是独立事务，不能把恢复后的结果拼成原 attempt 成功。

### 7.2 完整自主流程

phase-prefix 全部通过后，在冻结的 default、left、forward anchor scene 上做完整自主运行。五次运行使用预先冻结、覆盖三个 anchor 的顺序；接受门是同一 commit、配置、policy 和 `FULL_RESTART` 生命周期下至少连续 5 次有效成功。

每次运行必须证明：

1. 搜索完成，head/wrist RGB 新鲜且身份正确。
2. 接近路径安全，控制器实际执行 reference 与 permit 一致。
3. 双侧接触、微抬升、离台和稳定持物证据成立。
4. 搬运与对齐期间没有非法机器人接触或持物丢失。
5. 开夹爪前完成 `DETACH_MOVEIT`。
6. 新 release epoch 证明桌面支撑成立，且没有持续指尖接触。
7. 径向撤离 10 mm，再垂直撤离 60 mm。
8. 杯子最终位于目标区，保持稳定且姿态合格。
9. MuJoCo、Planning Scene、controller、contact stream 和双 RGB 时间线一致。
10. 全程无人工介入、无 MoveIt recovery、无证据丢失。

人工操作或 MoveIt recovery 可以用于诊断，但该次运行不得计入连续成功，也不得进入正式数据候选。

## 8. Task 9：10 Hz 因果 episode

每条 episode 使用固定 10 Hz 时间网格：

- observation：同一决策时刻的 head RGB、wrist RGB 和 8 维机器人状态；
- action：控制器在 `t + 0.1 s` 实际采用的 desired/reference；
- audit：MuJoCo truth、接触原始流、Planning Scene、controller 状态和阶段事件。

audit 数据不进入 ACT observation。规划目标、发送给 action server 的原始 goal、未来实测 joint state 或事后估计值不能替代 controller reference。

相机过期、时间倒退、reference 缺失、采样间隔超限、跨 reset/session/attempt 身份或无损写入失败都会使 episode QC 失败。正常释放会在同一 episode 内建立新的 release epoch，并以显式事件分隔释放前后样本；这不是 QC 失败。监督器只能使用当前 release epoch 的新接触、支撑和释放确认样本，不能用上一 epoch 的样本证明本次释放。Recorder 不允许静默丢帧、改变采样率或更换压缩语义来维持吞吐。

每个 Worker 有私有 Recorder 和临时 episode 目录。Task 8 成功和业务失败都要停止 Recorder，封存现有原始证据，写入不可改写的终态 manifest/hash，并对文件和父目录完成 `fsync`；verifier 通过后，由 Coordinator 提交 result commit。业务失败提交为 `FAILED`，不要求完整成功 episode 或 QC 通过，也不得因恢复而重试。只有 Task 8 完整自主成功、QC 合格且已提交为 `PASSED` 的结果可以进入训练配额。封存、hash、`fsync` 或 verifier 失败属于基础设施故障，不能伪造 `FAILED` 业务终态。目录存在不等于 episode 已提交。

## 9. Task 10：冻结清单与配额

五路清单继续分为 Train、Validation、Offline Test、Rollout Validation 和 Rollout Test。只有前三路生成专家 episode，配额为 50/10/10。后两路用于模型闭环评估，不进入正式采集调度。

正式候选使用冻结顺序。业务失败写入不可改写终态并推进到下一个候选，不重试同一场景。每个 split 选择 manifest 顺序中最靠前的 N 个合格 episode；Worker 完成顺序不改变数据集成员。

候选耗尽仍未满足配额时输出 `QUOTA_UNSATISFIED`。系统不复制 episode、不放宽 QC，也不自动生成新候选。是否创建新数据版本或新 manifest 由人工决定。

## 10. Task 11/11A：W8 资格与正式采集

资格顺序固定为：

```text
W1 smoke
  -> W1/W2 eight-scene functional qualification
  -> exact-W8 independent 40-scene sustained-load qualification
  -> formal W8 collection
```

八场景功能资格比较 W1 与 W2 的入口语义、exact-once、数据 schema、跨 Worker 隔离、Recorder 行为、物理结果和清理。W1 smoke 只检查最小链路，不是性能基线；随后 W1 和 W2 各自完整消费同一份八场景清单。每次资格运行必须零基础设施中断、零 retry、零 crash resume，八个场景各有唯一终态，所有 owned 资源完成清理。W2 的有效 episode/分钟必须高于 W1；物理成功率和 QC 合格率不得越过运行前冻结的退化容差。W2 未通过时不启动 W8。

W8 使用与八场景清单、正式五路清单都不重叠的 40 个场景，按冻结顺序分成两个 20 项 wave。每个 batch 的 `worker_count` 必须等于 8，不能用 W1/W2 结果或低并发 continuation 冒充 W8。每个 wave 中，每个 Worker 必须通过实际 terminal lease 连续完成至少 2 项；静态 preferred assignment 不算证据。两个 wave 必须完整消费 40 场景，产生 40 个唯一终态，并满足零基础设施中断、零 retry、零 crash resume。恢复批次只证明恢复协议，不授予 W8 持续负载资格。W4、W6 不再执行；W8 是本次 ai-station campaign 的执行要求，不是项目其他工作负载的永久默认值。

资格运行前写入不可变的 `qualification-contract.json`，冻结 source/config/manifest/policy hash、指标单位、采样窗口和通过阈值。指标至少包括 CPU、GPU、RAM 上限，磁盘延迟与持续吞吐，MuJoCo RTF 下限，Recorder 队列高水位及回落时间，10 Hz 帧间隔分位数，有效 episode/分钟、物理成功率和 QC 合格率。运行中不允许改阈值。任一阈值越界、后半程吞吐持续下降、队列不能回落或资源采样缺失，都使该资格失败并停止 campaign，等待人工决定。系统不自动减少 Worker、换设备、降低图像质量、降采样或继续以较低档位计数。

本轮只要求一次完整的 40 场景 W8 资格，不隐式继承旧计划的第二轮独立复测。失败后若人工决定重测，必须使用新的资格 ID 和 evidence 子树，重新完整运行 40 场景；两次不完整结果不能拼接成一次资格。

正式采集同样运行 exact W8，`max_wave_size` 固定为 20。基础设施中断只允许在相同 worker count、manifest、runtime config、collection config、contact policy 和 campaign 数据身份下显式恢复。恢复会取得新 resource binding 和 generation，但不得改变业务输入。业务失败不进入恢复队列。

## 11. 失败语义

| 失败 | 处理 |
| --- | --- |
| admission、hash、binding、owner 不一致 | 拒绝启动，不创建子进程 |
| 非 MuJoCo 后端或 Gazebo 依赖 | fail closed |
| 接触、控制器、双 RGB、MoveIt 或时间线不安全 | 安全停止，封存证据，episode 不合格 |
| Task 8 业务失败 | 不重试同一候选，继续冻结候选序列 |
| Recorder、进程或通信基础设施中断 | 封存临时数据；仅允许同 W8 配置恢复 |
| W8 资源瓶颈 | 停止，等待人工决策 |
| 候选耗尽 | `QUOTA_UNSATISFIED` |
| campaign owner 或 lease 丢失 | fence 旧 generation，停止全部 Worker |
| cleanup 不完整 | campaign 不得标记完成或释放 binding |

取消请求先冻结新工作，再取消本 campaign 拥有的 controller goal 和进程。收到 cancel ACK 不等于 cleanup 已完成；只有 cleanup proof 收敛后才能释放资源或启动下一个 campaign。

## 12. 测试和验收顺序

实现按下列门推进：

1. 接触 collector/analyzer 的单元、篡改和混淆矩阵测试。
2. 离线校准及隔离 ROS/MuJoCo live 评估。
3. 独立审阅 proposal，用户批准精确 `POLICY_FINGERPRINT`。
4. typed IPC、generation、deadline、取消和唯一 ROS child 契约测试。
5. Web/CLI 等价、Teleop/Tasks 冲突、owner 丢失和旧 generation 拒绝测试。
6. Task 8 phase-prefix。
7. Task 8 完整自主流程连续 5 次 `FULL_RESTART` 成功。
8. 10 Hz Recorder replay、seal、commit 和故障恢复测试。
9. W1 冒烟及 W1/W2 八场景功能资格。
10. 独立 40 场景 exact W8 持续负载资格。
11. 正式 W8 采集 50/10/10，生成不可变 `campaign-index.json`、QC 汇总和 cleanup proof。

任一门未通过，后续阶段不能开始。package tests、HTTP ready、MuJoCo 窗口存在或单次成功都不能替代上述运行门。

## 13. 证据和完成边界

Task 8 live、W8 资格和正式采集分别使用独立 manifest 和 evidence 子树，但属于同一个已登记的 durable task evidence root。每个结果绑定 source commit、submodule、install overlay、runtime executable、ROS Domain、MuJoCo session、config/policy hash 和 campaign generation。

完成报告必须分别列出 retained、archived 和 deletion candidates。未经用户授权不删除证据。旧的 `/data/work/so101-evidence/act-data/0917a` 已丢失，只能作为 `evidence_unavailable` 的历史事实，不能恢复为本轮通过结论。

本设计的完成条件是文档经书面审阅并据此更新实施计划。运行完成仍需后续实现逐门提供证据；不能因设计或计划通过审查而声称 Task 8、W8、50/10/10 或训练完成。
