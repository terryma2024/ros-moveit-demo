# SO-101 ACT 路径证明、提交窗口与控制频率规格

状态：用户已于 2026-09-27 书面复核，同意按本规格继续。实现和仿真验证须逐项通过下文门禁；真实机械臂写入仍受独立资格约束。项目 ACT 数据与策略保持 10 Hz；正式 accepted Train/Validation/Offline Test 均为 0/0/0。实验事实见[账本](../../experiments/so101-act-data-experiment-ledger.md)。

## 现场问题与设计边界

EXP-466 在用户设置的 `performance` 电源策略下，首次完整 701 点检查耗时 89.572717 ms。原链路分别在 approve、permit consume 和 exact goals 阶段做完整路径检查。原 25 ms 是这条三次检查链的局部预算，不是 MuJoCo 500 Hz 的物理常数。EXP-469 的 16-lane 探针此前已执行一次：四次干净路径检查分别耗时 12.849、12.217、12.291、12.567 ms，但其状态是 `TIMING_PASS_PARITY_INCOMPLETE`。这组数值不能证明违规路径等价，也不能给生产路径授予准入。该方向停止，证据保留。

以下设计保留 2 ms 路径网格、2 mm clearance、完整 701 样本及现有速度、加速度、terminal-stop 和接触规则。提交前只做一次完整路径证明。若现场不再匹配该证明，本次尝试拒绝；重新证明只能作为另一次明确的准备事务，不能藏在提交窗口里。MuJoCo-only，现有 campaign 资源绑定仍仅在启动入口检查。

## `PathProof` 的输入、所有者与结果

broker 是 `PathProof` 的唯一创建者、保管者和消费者。检查 worker 只返回带类型的结果，不持有 permit，不发送 goal。proof 不能作为可复制的 `safe=true` 缓存传给其他 attempt。

证明输入是不可变的规范记录，含以下字段：

| 范围 | 必须绑定的内容 |
| --- | --- |
| 路径 | arm/gripper 的 exact prefix rows、joint order、相对起点的时间偏移与 2 ms 插值网格；所有 701 个样本及预期第一目标相对偏移 |
| 物理状态 | 完整 measured model `qpos/qvel`、robot/cup/scene 状态、cup-in-gripper transform、attachment、phase、holding state 和接触 scope |
| 控制来源 | 已停稳的 controller reference/feedback、bridge 初始状态与采样时间、两路 controller 身份和停止证明 |
| 身份 | scene/model、checker 版本、profile、激活 contact-policy fingerprint、prefix source artifact SHA256、session、attempt、reset epoch、broker ticket 与 ownership generation |
| 检查规则 | 2 mm clearance、速度/加速度/terminal-stop、phase allowlist、full-robot 及 held-cup 接触判定 |

规范化编码须固定字段顺序、单位、浮点编码、joint order、数组长度、非有限值处理与版本；NaN/Inf 直接拒绝。路径时间在进入相对合同前按 ROS stamp 精度转为整数纳秒，所有偏移以整数纳秒比较；不能让浮点数的大时间戳舍入误差决定是否同一路径。`canonical_input_hash` 覆盖全部输入，另保存 `prefix_hash`、`snapshot_hash`、`model_hash`、`contact_policy_hash`、`source_artifact_hash`、`profile_hash`，以及 checker/规则版本。结果包含 generation/epoch、`SAFE` 或第一违规的样本索引和原因、实际处理样本数、monotonic 开始/结束时间和 `proof_compute_latency`。`SAFE` 必须有 701 个完整样本和全局规则通过；worker 崩溃、超时或样本缺失一律没有 proof。哈希用于定位差异，提交时仍逐字段验证现场来源与规范编码，不能靠脱离现场的哈希或 Boolean 放行。

证明对相对时间曲线工作。当前 `validate_action_prefix` 把 `target_times_s` 绑定到 `observation_time_s`；提交延后后，原合同不能直接用来验证新目标。准备阶段先保留原 prefix 和所选观察的哈希，再生成受 broker 管理的相对路径合同：以候选共同起点为零，记录实测 bridge 和每个目标的偏移。完整 checker 消费这些偏移及实测状态，保留 bridge→start→目标的全部时间间隔；`observation_time_s` 仍是原始仿真采样时间，不能随目标平移。实际提交使用单独验证的 materialized prefix/goal 合同，绑定原观察、positions、相对 grid 和新绝对时间，不能把移动后的绝对目标塞回旧 `validate_action_prefix` 伪装成原输入。它只在机器人已停稳、没有控制目标的准备阶段运行；证明期间的 reset/cancel/ownership 变更使结果作废。证明所用 model、接触规则和外部场景必须对共同起始时间平移不变。若存在随绝对时间变化的障碍、控制参考或约束，这个证明形式不适用，应拒绝。

EXP-485 的源码审计补出一处来源边界：SEARCH 读回已有七路原始 monotonic 接收时间，它们只证明被选中的物理帧和传感器样本何时到达。当前固定诊断路线由 reset 阶段的 manifest 构造，生产 pick-place 子进程没有 prefix 生成器，也没有把生成结果连同 owner ticket 登记到 broker 的私有收据。因此，不能把 SEARCH 完成时间、传感器接收时间或 Unix RPC 到达时间填成 `policy_received_wall_s`。接入 proof 前，实际 prefix 生产者须在同一 session/attempt/reset epoch 内消费那份已验证的 SEARCH 读回，生成并冻结 exact rows 与相对时间，再由 broker 绑定 owner ticket、prefix hash 和原始来源时间；延迟、重放、换路或换 ticket 均须拒绝。固定诊断路线仍只作无命令权限的候选；它若将来用作专家控制源，须另行定义并验证其“产生时刻”，不能借用尚不存在的 policy 推理收据。

### Prefix 来源收据

Task 8 的专家数据先于 Task 12 的 ACT 训练，准入不能要求一个尚不存在的 ACT 模型。来源分为 `EXPERT_ROUTE` 与 `ACT_POLICY`：前者在当前 SEARCH 读回通过后，用已冻结的专家路线模板生成当前 attempt 的 prefix；后者在模型输出到达时冻结 exact prefix。模板可以在 reset 时载入，但载入时间不算 prefix 签发时间。SEARCH→APPROACH 是首个实例；后续阶段须用该阶段的新鲜物理读回签发，不能复用 SEARCH 收据。现有 `eligible_for_collection=False` 的诊断路线仍无控制权限；将来要用于专家执行，须先有独立的路线资格和完整 proof，不能只改这个标志。

broker 私有的 `PrefixSourceReceipt` 记录 `source_kind`、session/attempt/reset epoch、来源 phase/physics step、当前 owner ticket/generation、七路原始 `source_received_wall_s`、所选图像与状态的规范哈希、source artifact SHA256、激活 contact-policy fingerprint、exact prefix hash、sequence 和 `prefix_issued_wall_s`。`source_artifact_sha256` 对专家路线是已核验的 route manifest，对 ACT 输出是实际模型/检查点；它与接触策略指纹是两个不同身份。收据不接受 Unix 请求提供的时间、ticket 或哈希，也不作为可复制的 RPC 结果返回。当前子进程里的 SEARCH 端口与 broker 同进程，可信内部生产者取得已验证读回后，须在 broker 的 ownership fence 内登记结果；提交请求只以当前 ticket 和 exact prefix 查找私有收据。

签发前须再次核对所选 world/scene/contact 为同一 session、epoch 和 physics step，四路 RGB/关节样本属于这次来源读回的因果窗口；七路接收时间逐一有限、未超龄且不晚于签发时钟。`EXPERT_ROUTE` 在路线选择、状态核对和 exact rows 冻结完成时取 `prefix_issued_wall_s`；`ACT_POLICY` 保留模型输出首次进入可信适配器的 monotonic 接收时间，不能在 broker 收到 RPC 后重打时间戳。prefix 的 `observation_time_s` 仍取被选中物理帧的 simulation time，不能改成签发时刻。登记前后都复核 ticket/generation/epoch；其间若发生 reset、cancel、unknown goal、hazard、source loss 或路线更换，丢弃结果。一个 ticket、来源 phase/step、sequence 组合只准签发一次；proof 开始时收据一次性消费，失败或撤销后关闭，重放和替换一律拒绝。

当前原型 `RelativePathRequest.policy_received_wall_s` 与 `max_policy_age_s` 只表达单一 policy 时钟，不能直接承担上述双来源合同。生产接线前须把它们迁移为来源中性的 `prefix_issued_wall_s` 与 `max_prefix_age_s`，并在 proof 输入中保留七路原始接收时间及来源身份。旧原型的测试通过不证明迁移完成；未迁移时生产 proof 入口继续关闭。

## 证明后的 commit window

完整证明返回后，broker 重新读取物理与控制状态，并取得新鲜 monotonic/simulation 双时钟。先校验 ticket、generation、session、attempt、epoch 和唯一 owner，再比较完整 `qpos/qvel`、robot/cup/scene、phase、holding、attachment、cup transform、controller reference/feedback、bridge 与 proof 输入。首版采用规范编码后的 exact equality；不设置经验容差。未来若允许变化，必须先给出覆盖全部路径样本、接触和动态界限的保守 envelope 证明，并另经规格复核。状态微小漂移导致拒绝，也不能在窗口内悄悄重算。

以下任一事件令 proof 失效：reset、cancel、goal replacement、unknown goal、hazard、source loss、停止证明失效、时钟不连续、epoch/generation 变化。prefix 任一 row、相对时间、joint order、contact scope、model/profile/policy 或 checker 规则变化，同样拒绝。broker 在单个原子状态转移中把 proof 从 `VALIDATED` 消费成 `CONSUMED`；重放、过期或并发消费都失败。失败后的 proof 进入 `CLOSED`，不能恢复。

绝对共同起始时间 `T0` 在上述新鲜状态和时钟读回后确定。若 proof 中 bridge 相对偏移为 `τ_bridge`，新实测 bridge 时间必须满足 `t_bridge'=T0+τ_bridge`；第 `i` 个目标时间是 `T0+τ_i`。proof 的 positions、bridge→start 间隔和目标间隔逐项相同，才是同一条经证明的曲线。原始 `observation_time_s` 不平移，观察与 prefix 到 acceptance 的年龄都须满足各自 freshness 上界；过期则拒绝。若新 bridge 无法同时满足状态、reference 与这个 `T0`，直接拒绝，不选择另一条曲线或在窗口里重算。不得先证明带旧绝对时间的目标再只平移 goal。生成 arm/gripper 两路目标后，exact-goals 边界比对实际准备发送的规范序列化内容：joint names/order、每一 row、相对偏移、生成的绝对 stamp、共同 `T0`、controller 身份与 reference 起点。只有传输层生成且与运动语义无关的 nonce 可以排除，排除字段必须枚举并测试；未枚举字段不排除。`T0` 时的 controller reference/bridge 必须与 proof 的起点一致，否则拒绝。整段 bridge 与目标同幅平移才保持已证明的相对速度、加速度和 terminal stop；新目标绝对时间仍由提交时的时钟验证。

permit consume 和 exact-goals 阶段只做这些身份、状态、内容与时间校验，不再各跑一次 701 点 MuJoCo 检查。提交与 action acceptance 之间仍持续监测 generation、epoch、cancel、stop、unknown goal 与时钟；任一变化停止提交。两路目标须被各自真实 action server 在共同起始时间前接收。若只接收一路，取消已接收目标，验证物理停止并封闭 proof/attempt；不能自动重试另一目标或把部分接收记作成功。

## 两段时序的验收式

所有 wall duration 由同一 monotonic clock 测量；MuJoCo `sim_time` 用于目标时间、physics step 和共同起始边界。一次原子双时钟读回记录映射及其误差上界 `ε_clock`；若映射不连续或误差界缺失，拒绝。设七路原始接收时间的最早值为 `m_oldest`、最晚值为 `m_ready`，prefix 首次签发于 `m_prefix`。证明后新鲜物理状态在 `m_s` / simulation `s_s` 读回，最后一路接受发生在 `m_a` / 对应 simulation `s_a`，共同起始时间为 `T0`，第一目标为 `T1=T0+τ_1`。已冻结的观察、prefix 与物理状态最大年龄分别为 `A_obs`、`A_prefix`、`A_state`，预留抖动余量 `J_obs`、`J_start`、`J_first`，则至少满足：

```text
proof_compute_latency = m_proof_end - m_proof_start
commit_latency = m_a - m_s
m_oldest <= m_ready <= m_prefix <= m_proof_start <= m_proof_end <= m_s <= m_a
commit_latency + J_obs + ε_clock < A_state
(m_a - m_oldest) + J_obs + ε_clock < A_obs
(m_a - m_prefix) + J_obs + ε_clock < A_prefix
s_a + J_start + ε_clock < T0
s_a + J_first + ε_clock < T1
T1 = T0 + τ_1;  τ_i 与 (τ_{i+1} - τ_i) 均与 PathProof 输入逐项相同
```

`A_obs`、`A_prefix`、`A_state` 与余量必须从已冻结的现场 freshness/调度合同和实测尾延迟得出；缺值不准提交。观察和 prefix 年龄都包含 proof 的计算时间，不能用新的物理读回重置；七路源时间还须逐路满足各自的接收年龄门槛。最后一路 acceptance 到达 `T0` 或之后，即使尚早于第一轨迹点，也失败。提交窗口还需在每个发出目标前重验剩余时间；已过界就走取消/停止路径。proof 的准备时间不偷占 commit window，但 proof 的 wall 有效期和代际 fence 仍独立检查。初版 worker wall timeout 提议为 250 ms，从调用开始计时，超时就关闭 proof/attempt 并确认停止；这只是待复核的 fail-closed 上限，必须再用准备阶段停止保持能力及首次/尾部测量验证，不能沿用 25 ms 当作物理常数。

测量报告分开列 `proof_compute_latency` 的首次、后续 p50/p95/p99/max，及输入规范化、grid、MuJoCo、聚合各段；`commit_latency` 要分出新鲜采样、身份/状态校验、permit consume、exact-goal 校验、两路 submit 和两路 acceptance 的首次与尾部。超时、拒绝和首次调用进入分母，不能只报平均值或只选 warm cache。对照实验固定同一 immutable fixture：旧三次完整检查链若超过其 25 ms 局部预算如实失败；新链仅允许一次 proof，随后对任意状态或 goal 改动都须拒绝。新架构是否满足上述不等式，留待规格通过后的独立验证，不由 EXP-469 的局部时间推断。

## 执行期安全与四层频率

`PathProof` 只覆盖提交前路径。执行中继续取 500 Hz MuJoCo physics evidence、controller reference/feedback、full-robot contact、force、displacement、support、slip 和 lossless evidence；stop/cancel/retire、ownership generation 与 unknown-goal fence 保持原有拒绝语义。proof `SAFE` 不等于 Task 8 readiness、live PASS 或正式数据资格。

| 层 | 当前规格 | 验证含义 |
| --- | --- | --- |
| ACT observation/action | 10 Hz | 保持训练/推理动作栅格，不重采样、不重训 |
| camera | 10 Hz | 图像新鲜度仍单独门控 |
| joint/evidence feedback | 100 Hz 候选 | 由实际带时间戳的反馈证明连续性与丢样，未证明前只是候选 |
| MuJoCo physics/controller | 2 ms / 500 Hz 候选 | 测真实 step 与 controller update 的连续性、wall/sim jitter、missed tick 和长时 RTF；读 YAML 不算验证 |

仿真目标的 500 Hz 不移植为真实 SO-101 串口目标。LeRobot `lerobot-rollout` 把默认 `--fps=30` 定义为 policy inference 与 dataset recording 频率；`--interpolation_multiplier=N` 对应每个 policy action 的 N 个 robot commands，默认 N=1。[官方 rollout 文档](https://github.com/huggingface/lerobot/blob/main/docs/source/inference.mdx)给出的是通用软件节拍，不能证明本机串口吞吐。SO-101 官方示例使用 30 fps 相机。[官方示例](https://huggingface.co/docs/lerobot/en/cheat-sheet)中这个值也是相机配置，不是伺服闭环实测。

SO follower 源码每次 observation 读一次 `sync_read("Present_Position")`，每次 action 写一次 `sync_write("Goal_Position", ...)`；设置 `max_relative_target` 会为 action 再读一次位置，并提示 fps 可能降低。[驱动源码](https://github.com/huggingface/lerobot/blob/main/src/lerobot/robots/so_follower/so_follower.py)。Feetech bus 源码默认 1,000,000 bps；[STS3215 厂商规格](https://www.feetechrc.com/Data/feetechrc/upload/file/20200611/6372749961523760249976542.pdf)写明半双工异步串口、38,400 bps–1 Mbps、出厂默认 1 Mbps。[总线源码](https://github.com/huggingface/lerobot/blob/main/src/lerobot/motors/feetech/feetech.py)。波特率不是六舵机读写闭环频率。

由此冻结待实测假设：真实 policy/采集参考 30 Hz；本项目 ACT 仍为 10 Hz。真实低层命令及位置反馈先以 30 Hz 为目标，即每个 100 ms ACT action interval 对应 3 个 setpoint。60 Hz 是候选，对应 6 个 setpoint；必须分别通过被动读和以后另获授权的写入资格测试。插值/保持不能改变动作端点、速度/加速度、terminal-stop 或 proof 的相对路径合同；若插值生成了不同的实际目标 rows，须另行证明，不能用本 proof 直接放行。真实机械臂 500 Hz 不作为准入假设。

### 无运动串口测量规格，待另轮授权执行

先只读回设备路径与身份、六个 servo ID、实际 baud rate、driver/SDK 版本、read/write API 和 `max_relative_target` 状态。与冻结配置任一不符，停止。不得通过连接流程隐式写 torque、goal、校准或 EEPROM；若驱动只读连接无法保证这一点，就不连接。使用 `sync_read("Present_Position")`，先测 30 Hz，再测 60 Hz。每档预热 10 s 后至少记录 60 s；预热时也只允许读。monotonic 原始开始/结束戳、实际周期 p50/p95/p99/max、deadline miss、timeout/retry、CRC/通信错误和 CPU 占用全量留证。一个档位未过即停止，不自动降频。

以下是**拟定验收阈值，尚待实测**，不是厂商保证：对目标周期 `T=1/f`，测量段完整有效读数至少 `60f`，timeout/retry/CRC/通信错误均为 0；`p99(period) ≤ 1.25T`、`max(period) ≤ 2T`、miss（周期 `>1.25T`）比例 `<0.1%`，采样进程 CPU `p95 ≤ 50%` 单逻辑核。所有指标逐档单独判定，不能用 30 Hz 结果外推 60 Hz。60 Hz 只有全部通过后才可申请后续写入资格；30 Hz 不稳定时停下等待人工决定。被动读通过不证明 `sync_read + sync_write` 闭环通过。

真正的 goal write/read round trip 只能在以后独立的 torque-disabled 或 bench-fixture 阶段验证。那一阶段须先有急停、限速、限位、净空、明确写入范围和新的用户授权；本规格不启动它。最终真实频率由实测闭环选定并记录对 10 Hz action chunk 的插值/保持方式。硬件或 W8 有资源瓶颈时停止等待人工决定；不改测 W4/W6，也不降低路径采样密度。

## 规格通过后的验证矩阵

| 边界 | 必须区分的样本及通过条件 |
| --- | --- |
| 完整 proof | safe 全 701；首/中/末违规的第一索引；2 mm 边界两侧；robot-only、held-cup-only、allowed→forbidden；NaN/Inf 拒绝；与现有 oracle 的接触顺序和结论逐项一致 |
| 现场绑定 | snapshot、model、policy、profile、phase、holding、attachment、reference、prefix、generation 或 epoch 任一改变都拒绝；session/attempt/ticket、clock、source loss 同理 |
| Prefix 来源 | `EXPERT_ROUTE` 与 `ACT_POLICY` 各自的首次签发；旧 SEARCH、旧路线模板、换 ticket、换 prefix、同一步重签、乱序或未来 monotonic 时间均拒绝；七路观察年龄与 prefix 签发年龄分别判定 |
| 一次性提交 | permit replay、proof 过期、worker crash/timeout、目标 rows/stamp/reference 改动、controller partial acceptance、acceptance at/after common start 均拒绝并有停止/退役证据 |
| provenance | source tests、installed package tests 与实际生产入口链分别证实同一 proof/permit/goal 内容；生产入口不存在或未连通不得以单测代替 |
| 仿真动态 | 500 Hz physics step/controller update 连续性、wall/sim jitter、missed tick、长时 RTF 和执行期无损安全证据达标 |
| 真实硬件 | 只按上节做 passive read；结果只决定下一轮是否可申请写入资格，不产生运动授权 |

W2 的独立门禁通过后，直接执行独立 40 场景 W8；本规格不开放 W4/W6 折中。没有 threshold relaxation、sample-rate downgrade、隐藏 fallback，也不把任何 diagnostic PASS 当 production authority。上述验证尚未执行，本文的所有“通过条件”均尚待实证，不是当前通过声明。
