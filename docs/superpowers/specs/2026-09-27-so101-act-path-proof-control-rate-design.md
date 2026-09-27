# SO-101 ACT 路径证明、提交窗口与控制频率规格

状态：待用户书面复核。本文只冻结接口和验收条件，不授权实现、控制目标或真实机械臂试验。项目 ACT 数据与策略保持 10 Hz；正式 accepted Train/Validation/Offline Test 均为 0/0/0。实验事实见[账本](../../experiments/so101-act-data-experiment-ledger.md)。

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
| 身份 | scene/model、checker 版本、profile、激活 policy fingerprint、session、attempt、reset epoch、broker ticket 与 ownership generation |
| 检查规则 | 2 mm clearance、速度/加速度/terminal-stop、phase allowlist、full-robot 及 held-cup 接触判定 |

规范化编码须固定字段顺序、单位、浮点编码、joint order、数组长度、非有限值处理与版本；NaN/Inf 直接拒绝。`canonical_input_hash` 覆盖全部输入，另保存 `prefix_hash`、`snapshot_hash`、`model_hash`、`policy_hash`、`profile_hash`，以及 checker/规则版本。结果包含 generation/epoch、`SAFE` 或第一违规的样本索引和原因、实际处理样本数、monotonic 开始/结束时间和 `proof_compute_latency`。`SAFE` 必须有 701 个完整样本和全局规则通过；worker 崩溃、超时或样本缺失一律没有 proof。哈希用于定位差异，提交时仍逐字段验证现场来源与规范编码，不能靠脱离现场的哈希或 Boolean 放行。

证明对相对时间曲线工作。它只在机器人已停稳、没有控制目标的准备阶段运行；证明期间的 reset/cancel/ownership 变更使结果作废。证明所用 model、接触规则和外部场景必须对共同起始时间平移不变。若存在随绝对时间变化的障碍、控制参考或约束，这个证明形式不适用，应拒绝。

## 证明后的 commit window

完整证明返回后，broker 重新读取物理与控制状态，并取得新鲜 monotonic/simulation 双时钟。先校验 ticket、generation、session、attempt、epoch 和唯一 owner，再比较完整 `qpos/qvel`、robot/cup/scene、phase、holding、attachment、cup transform、controller reference/feedback、bridge 与 proof 输入。首版采用规范编码后的 exact equality；不设置经验容差。未来若允许变化，必须先给出覆盖全部路径样本、接触和动态界限的保守 envelope 证明，并另经规格复核。状态微小漂移导致拒绝，也不能在窗口内悄悄重算。

以下任一事件令 proof 失效：reset、cancel、goal replacement、unknown goal、hazard、source loss、停止证明失效、时钟不连续、epoch/generation 变化。prefix 任一 row、相对时间、joint order、contact scope、model/profile/policy 或 checker 规则变化，同样拒绝。broker 在单个原子状态转移中把 proof 从 `VALIDATED` 消费成 `CONSUMED`；重放、过期或并发消费都失败。失败后的 proof 进入 `CLOSED`，不能恢复。

绝对共同起始时间 `T0` 在上述新鲜状态和时钟读回后确定。第 `i` 个目标时间是 `T0 + τ_i`，其中 `τ_i` 是已证明的相对偏移。不得先证明带旧绝对时间的目标再平移它。生成 arm/gripper 两路目标后，exact-goals 边界比对实际准备发送的规范序列化内容：joint names/order、每一 row、相对偏移、生成的绝对 stamp、共同 `T0`、controller 身份与 reference 起点。只有传输层生成且与运动语义无关的 nonce 可以排除，排除字段必须枚举并测试；未枚举字段不排除。`T0` 时的 controller reference/bridge 必须与 proof 的起点一致，否则拒绝。这样时间平移不改变已证明的相对速度、加速度和 terminal stop；新目标绝对时间仍由提交时的时钟验证。

permit consume 和 exact-goals 阶段只做这些身份、状态、内容与时间校验，不再各跑一次 701 点 MuJoCo 检查。提交与 action acceptance 之间仍持续监测 generation、epoch、cancel、stop、unknown goal 与时钟；任一变化停止提交。两路目标须被各自真实 action server 在共同起始时间前接收。若只接收一路，取消已接收目标，验证物理停止并封闭 proof/attempt；不能自动重试另一目标或把部分接收记作成功。

## 两段时序的验收式

所有 wall duration 由同一 monotonic clock 测量；MuJoCo `sim_time` 用于目标时间、physics step 和共同起始边界。一次原子双时钟读回记录映射及其误差上界 `ε_clock`；若映射不连续或误差界缺失，拒绝。设新鲜状态在 monotonic `m_s` / simulation `s_s` 读回，最后一路接受发生在 `m_a` / 对应 simulation `s_a`，共同起始时间为 `T0`，第一目标为 `T1=T0+τ_1`。已冻结的 observation 最大年龄为 `A_max`，预留抖动余量 `J_obs`、`J_start`、`J_first`，则至少满足：

```text
proof_compute_latency = m_proof_end - m_proof_start
commit_latency = m_a - m_s
commit_latency + J_obs + ε_clock < A_max
s_a + J_start + ε_clock < T0
s_a + J_first + ε_clock < T1
T1 = T0 + τ_1;  τ_i 与 (τ_{i+1} - τ_i) 均与 PathProof 输入逐项相同
```

`A_max` 与余量必须从已冻结的现场 freshness/调度合同和实测尾延迟得出；缺值不准提交。最后一路 acceptance 到达 `T0` 或之后，即使尚早于第一轨迹点，也失败。提交窗口还需在每个发出目标前重验剩余时间；已过界就走取消/停止路径。proof 的准备时间不偷占 commit window，但 proof 的 wall 有效期和代际 fence 仍独立检查。初版 worker wall timeout 提议为 250 ms，从调用开始计时，超时就关闭 proof/attempt 并确认停止；这只是待复核的 fail-closed 上限，必须再用准备阶段停止保持能力及首次/尾部测量验证，不能沿用 25 ms 当作物理常数。

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

以下是 **proposed acceptance，等待书面复核**，不是厂商保证：对目标周期 `T=1/f`，测量段完整有效读数至少 `60f`，timeout/retry/CRC/通信错误均为 0；`p99(period) ≤ 1.25T`、`max(period) ≤ 2T`、miss（周期 `>1.25T`）比例 `<0.1%`，采样进程 CPU `p95 ≤ 50%` 单逻辑核。所有指标逐档单独判定，不能用 30 Hz 结果外推 60 Hz。60 Hz 只有全部通过后才可申请后续写入资格；30 Hz 不稳定时停下等待人工决定。被动读通过不证明 `sync_read + sync_write` 闭环通过。

真正的 goal write/read round trip 只能在以后独立的 torque-disabled 或 bench-fixture 阶段验证。那一阶段须先有急停、限速、限位、净空、明确写入范围和新的用户授权；本规格不启动它。最终真实频率由实测闭环选定并记录对 10 Hz action chunk 的插值/保持方式。硬件或 W8 有资源瓶颈时停止等待人工决定；不改测 W4/W6，也不降低路径采样密度。

## 规格通过后的验证矩阵

| 边界 | 必须区分的样本及通过条件 |
| --- | --- |
| 完整 proof | safe 全 701；首/中/末违规的第一索引；2 mm 边界两侧；robot-only、held-cup-only、allowed→forbidden；NaN/Inf 拒绝；与现有 oracle 的接触顺序和结论逐项一致 |
| 现场绑定 | snapshot、model、policy、profile、phase、holding、attachment、reference、prefix、generation 或 epoch 任一改变都拒绝；session/attempt/ticket、clock、source loss 同理 |
| 一次性提交 | permit replay、proof 过期、worker crash/timeout、目标 rows/stamp/reference 改动、controller partial acceptance、acceptance at/after common start 均拒绝并有停止/退役证据 |
| provenance | source tests、installed package tests 与实际生产入口链分别证实同一 proof/permit/goal 内容；生产入口不存在或未连通不得以单测代替 |
| 仿真动态 | 500 Hz physics step/controller update 连续性、wall/sim jitter、missed tick、长时 RTF 和执行期无损安全证据达标 |
| 真实硬件 | 只按上节做 passive read；结果只决定下一轮是否可申请写入资格，不产生运动授权 |

W2 的独立门禁通过后，直接执行独立 40 场景 W8；本规格不开放 W4/W6 折中。没有 threshold relaxation、sample-rate downgrade、隐藏 fallback，也不把任何 diagnostic PASS 当 production authority。上述验证尚未执行，本文的所有“通过条件”均是待复核的规格，不是当前通过声明。
