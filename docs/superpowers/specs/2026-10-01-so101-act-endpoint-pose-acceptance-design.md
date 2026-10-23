# SO-101 ACT 共用端点 Pose 验收修订

2026-10-05 优先修订：[Teacher 执行与 ACT 数据验证分离](2026-10-05-so101-teacher-act-decoupling-amendment.md)。Teacher 按起终点杯子 Pose 和最终直立结果判定任务；过程质量项以审计为主，保留真正的执行保护。ACT 采集/QC 故障不得阻断或撤销 Teacher 运动，数据标准和用途隔离不放宽。下文冲突条款以该修订为准；用户已授权现有 ai-station Claude 更新计划、清理旧逻辑/测试并执行，尚未形成新运行验收。

日期：2026-10-01
状态：端点方案及2026-10-01运行配置经验初值补充已获用户授权，独立GPT-6 Astra/High静态复审通过，交由原dst实施；不表示运行代码或资格已经更新。

## 1. 适用范围与优先级

杯子任务结果统一改为起点和终点 Pose 验收，采用运行前冻结、可配置的经验阈值。适用于非 Head 首条闭环、正式 MoveIt 示教采集、W1/W2/W8 资格、容器 shard，以及后续 ACT rollout 和路线比较。各场景仍执行各自获准的动作流程，不新增并行实现或真实机械臂授权。

本修订替代旧方案中的物体过程质量成功条件：双侧抓稳、实际抬升高度、全程持物、释放后接触、释放/放置稳定时长、撤离距离和速度质量评分。原来的记录仍保留审计，不能作为额外的任务结果 PASS 条件，也不能经 `DONE`、readback、verifier 或 aggregator 间接重新加回来。

以下文档中与物体任务结果相关的条款，以本文为准；其他条款不变：

| 文档 | 替代范围 |
| --- | --- |
| `2026-09-10-so101-act-head-wrist-rgb-design.md` | 示教/rollout 物体结果、最终检查和成功率的物理判定口径 |
| `2026-09-24-so101-act-task8-live-formal-collection-design.md` | Task 8 完整运行的物体质量条件、Task 9/正式配额中的物体结果 |
| `2026-09-30-so101-act-containerized-campaign-design.md` | shard 的物体结果、资格/正式采集的成功率口径 |
| `2026-09-30-so101-act-nonhead-first-episode-design.md` | 原始物理 QC 与非 Head 输入的质量测量前置条件 |
| Task 8 artifact preparation / measurement protocol | 五个质量测量字段不再是采集/成功资格前置条件；安全/Head/同步项保留 |
| 对应实施计划的 Tasks 6/8/9/11/11A/16、非 Head Tasks 1/3/4/6/7 | 质量策略输入、阶段质量断言、独立 QC、提交和成功率聚合 |

旧条款如同时包含安全和质量要求，只替代质量部分。Head 校准设计、数据集划分、YOLO 三版比较、Head 搜索成功条件、并行资格顺序和次数不由本修订改变。

## 2. 三个独立结果

`endpoint_pose` 只回答两个杯子 Pose 是否满足目标。它不证明杯子实际被抓起，也不证明已释放或持续稳定。推移、拖动等过程可能满足同样的端点，因此报告只能声明“端点 Pose 通过”，不能把它写成“抓稳/释放质量验证通过”。用户本次选择此口径，先打通采集流程。

执行结果另行要求正常完成、没有安全故障、超时、abort 或未授权干预。安全规则决定能否发动作和如何停止，不能被一个匹配的终点覆盖。数据结果另行要求连续采样、无损落盘、新进程 QC、实际 Coordinator commit 和用途身份正确。

正式 episode 可进入训练候选的条件为：正常的获准专家执行 + 端点 Pose PASS + 数据 QC PASS + durable commit + 正式 scope/split/配额资格。采用端点规则本身不使正式数据失去训练资格。非 Head 诊断仍禁止训练，原因是绕过了正式 Head 流程；资格批次、失败、surplus、人工恢复和迟到结果也仍按原规则排除。

## 3. 共用配置和默认值

新增持久配置 `src/so101_demo_py/config/act/endpoint_pose_acceptance_v1.yaml`。不为诊断和正式模式创建不同计算器。策略 envelope 的 closed keys 为 `kind,schema_version,rule_version,thresholds`，固定 `kind=ACT_ENDPOINT_POSE_POLICY`、`schema_version=1`、`rule_version=endpoint_pose_v1`；`thresholds` 只有下列五个字段：

| 配置键 | 默认值 | 判定 |
| --- | --- | --- |
| `initial_position_tolerance_m` | `0.010` | 起点 body 原点的三维欧氏误差 ≤10 mm |
| `initial_axis_tolerance_rad` | `0.15` | 起点杯子轴与目标轴夹角 ≤0.15 rad |
| `final_xy_tolerance_m` | `0.020` | 终点 body 原点的 XY 欧氏误差 ≤20 mm |
| `final_z_tolerance_m` | `0.010` | 终点 body 原点的 Z 绝对误差 ≤10 mm |
| `final_axis_tolerance_rad` | `0.15` | 终点杯子轴与目标轴夹角 ≤0.15 rad |

这些是经验默认值，不称为已校准阈值。位置、角度单位分别是 m、rad。所有值必须是有限正数，角度还须 ≤π；拒绝 bool、NaN/Inf、未知字段和未知版本。支持启动时和两次 episode 之间通过配置覆盖，不要求在开发前定死数值或取得质量校准报告。每次 episode 开始时记录完整生效配置及 hash，独立 QC 使用这份快照；正在采集的 episode 不热改判据，也不按结果事后放宽。一次正式资格批次仍使用同一配置身份，改变配置须建立新批次，不修改旧结果。

杯子绕自身轴的旋转不评价。倾斜角评价 body 局部 `+Z` 经四元数旋转后的单位向量：`acos(clamp(dot(actual_axis,target_axis),-1,1))`。四元数按 `xyzw` 表示，输入 norm 与 1 的误差须 ≤`1e-3`，随后归一化；零向量、非有限值、超差 norm 拒绝。`q` 与 `-q` 给出相同结果。

## 4. 目标、身份与采样边界

每个 scene/scenario 在执行前冻结唯一 `object_id/body_name`、`frame_id=world`、完整起点目标 Pose、完整终点目标 Pose、reset/放置 recipe 和对应变换 hash。位置统一使用同一个 MuJoCo 杯子 body 的原点，不混用杯底、TCP 或不同 frame。放置 recipe 若给出 TCP Pose，先通过冻结的 cup-to-TCP 变换换算杯子目标 Pose；禁止用实际终点反推目标。

初始端点是本次 reset 确认后、采集窗口内第一条新鲜杯子 Pose，必须早于本次抓放的首条 arm/gripper dispatch，不包含之前的 neck 搜索 dispatch。正式模式在 Head 锁定、相机稳定后开启 episode；诊断在预选目标确认后开启，二者均先采起点再允许 arm/gripper 动作。终止端点是正常结束触发、controller 停止确认之后第一条新鲜杯子 Pose；保留该样本后关闭采集。不增加稳定等待、速度条件或释放后接触条件，也不从历史挑选最接近目标的帧。不要求额外最小位移。

两个采样边界都必须记录实际源事件、stamp、sequence、session/reset/attempt/full lease identity。比较使用同一 session/reset 的 MuJoCo sim-time；publisher 与 broker 的 ROS sim clock 须有已验证映射，monotonic 时间只做 deadline/接收审计，不能与 sim-time 相减。

定义 `t_reset`、`t_capture_start`、`t_first_arm_dispatch`、`t_stop_confirmed` 为对应真实事件的 sim-time；Pose 在 physics step 生成时标记 `t_pose/physics_sequence`，source 采集边界消费该 Pose 的事件记 `t_capture`。初始满足 `t_pose >= max(t_reset,t_capture_start)` 且 `t_pose < t_first_arm_dispatch`。终止满足 `t_pose >= t_stop_confirmed`；若stamp相等，Pose的physics step sequence必须严格晚于停止确认时绑定的最后physics sequence。两端均满足 `0 <= t_capture-t_pose <= 0.1s`，以source sequence选第一个符合条件的样本。停止前采样、停止后收到的缓存Pose即使age≤0.1s也拒绝，不让receipt time掩盖source time。

缺样本、非有限 Pose、对象/frame 不符或跨 session/reset 数据属于证据无效。reset 或证据窗口变化不能拼成同一次成功。样本来自执行动作的同一个 MuJoCo 世界，不启动第二模拟器，也不通过瞬移或 physics attachment 制造终点。

终态不能仍依赖被取消的质量窗口。例如 `placement_stable_s`、释放后指尖接触和实际撤离距离不得藏在诊断或正式 `DONE` 前置条件里。既有开爪前的真实支撑确认、collision/contact force interlock、controller admission、detach-before-open、stop/hold 则继续作为动作安全门。实现必须逐项列出旧条件保留在哪个安全边界、哪些改为 audit-only，避免把质量校准报告当作这些安全门的唯一输入。

### 4.1 正常结束触发

MoveIt专家：本次获准抓放/撤离命令序列已完成，各controller结果合法；提交 `expert_sequence_complete` 事件，禁止新动作，再确认controller停止。取消的是旧质量验收分支，不取消实际动作完成或停止确认。

ACT rollout：在运行前的执行合同冻结 `stop_rule=first_final_pose_match_v1`，仅在抓放attempt开始后评价source新鲜杯子Pose。遇到第一条满足共用终点位置/轴阈值的样本，记录 `endpoint_stop_requested`，停止新的推理/动作提交，按实际broker停止/撤销协议撤销未完成goal并确认controller停止。该预期停止带明确原因，不与故障abort混为一谈；随后从停止确认之后取第一个新physics Pose作为最终端点，重新计算QC。请求停止时的Pose不能直接当终点；停下后偏离目标仍FAIL。不事后扫描历史选最好帧，也不把每个chunk结束当整个attempt完成。

ACT终止评估中的MuJoCo Pose只进入监督/验收和audit，不进入ACT observation、模型输入、目标动作或替模型生成开爪/撤离。该结束规则明确替代旧 `RELEASE_CONFIRMED → ACT_RETREAT → 稳定检查 → DONE` 的质量依赖；策略不保证先释放，报告不得声称它验证释放或完整抓取。120s内没有触发、停止失败、触发后出现安全故障或终点采样失败，仍按原超时/安全/基础设施分类失败。标准停止协议使用相同lease与revoke历史，尾部标签只保留已生效reference，不能制造未来action。

## 5. 输入和审计

不再以 `grasp_occlusion_window_s`、`support_distance_m`、`release_stable_s`、`retreat_distance_m`、`placement_stable_s` 的正式质量测量报告作为任何采集模式的前置条件，不伪造其 PASS。若现有安全开爪策略使用支撑距离或稳定窗口，保留该安全配置和有效批准绑定；取消的是质量报告要求，而不是执行器需要的安全数值。

`path_step_s/path_clearance_m`、velocity/acceleration、接触策略 activation、RGB age/skew、RTF/disk/queue hard-stop 属于安全或数据边界，依旧验证。新增端点策略不能解决或掩盖缺失的安全参数、资源限制或同步配置。Head 的检测/居中/锁定参数和批准条件不变。

### 5.1 用户授权的开发初值与配置方式

用户授权剩余数值先用经验初值推进开发，不再等待这些数值的前期测量报告。适用于已有 MuJoCo 仿真执行范围，不授权真实硬件或新的接触策略 activation。参数仍须传到实际生产消费者，并记录实际运行证据；初值不代表已校准或 live 合格。

| 配置键 | 开发初值 | 用途与依据 |
| --- | --- | --- |
| `path_step_s` | `0.002` s | 路径检查时间采样间隔；沿用当前 visible approach candidate 的 2 ms 初值，不是 Recorder 采样率 |
| `path_clearance_m` | `0.002` m | 路径碰撞净空初值；沿用同一 candidate 的 2 mm；保留完整碰撞检查和已有合法接触对 |
| `max_age_s` | `0.1` s | RGB 新鲜度上限初值；仍验证真实 source stamp，不改变 10 Hz 连续性或未来标签语义 |
| `max_skew_s` | `0.1` s | RGB 同步容差初值；不是同一物理步或因果一致性的替代证明 |
| 安全开爪所需 `support_distance_max_m` | `0.002` m | 仅当实际安全消费者需要该量时使用；真实世界支撑/contact 判断保留，双侧夹持不能冒充桌面支撑 |
| `hard_stops.rtf_min` | `0.90` | MuJoCo RTF 保护初值；实际不足时记资源 blocker，不由 agent 自动降低 |
| `hard_stops.disk_free_min_bytes` | `53687091200` | 50 GiB 可用磁盘保护初值，仍保留无损写入与磁盘错误拒绝 |

资源配置不在两个历史候选间盲选：以当前受控 `config/mujoco/parallel_batch_v3.yaml` 与 `config/act/parallel_collection_v3.yaml` 为基础，显式补上两个 hard-stop，再生成新生效配置/hash 和资源身份。保留现有 start guard（`timeout_s=2.0`、`cpu_busy_warn_fraction=0.90`、`ram_minimum_bytes=1073741824`、`ram_minimum_fraction=0.05`、`gpu_minimum_bytes=1073741824`）及 Recorder 水位（capacity 16、high 12、recovery 8、hold 0.2 s）、10 Hz、`lossless=true`、CUDA/no CPU fallback；同步 collection 中绑定的 runtime hash。不用 GPU INDEX 在多个下游重复重新选择资源，campaign 资源绑定仍只在启动入口。

新增配置 `config/act/endpoint_pose_development_runtime_v1.yaml`（package-relative）。配置覆盖优先级为 CLI 指定的运行配置 > 安装包开发初值；未知字段、错误单位/类型、非有限或非正数、无效水位和 clock-domain 混算拒绝。不引入模糊环境变量覆盖。运行开始解析一次，生成不可变的 effective-config artifact 并传给现有输入冻结器；`approval=user_empirical_default` 与用户本轮授权绑定，不能写成 `nonhead_calibration` 或伪造 measurement/sample PASS。正式模式仍独立要求 Head、既有安全 activation 和正式资格。若现有安全门确实还消费其他已取消质量字段，先列出消费者；仅保留真实安全用途，不凭空为旧终态质量 gate 补默认值。

文件的完整初值如下。每层只接受所列键，`kind/schema_version` 固定；CLI指定文件使用相同完整schema，不做隐式部分合并。effective artifact另存基底runtime/collection的字节与hash、用户覆盖来源、全部生效值及episode身份。支撑距离只是已有安全门的输入，不能以“距离小”取代真实桌面支撑证据。

```yaml
kind: ACT_ENDPOINT_DEVELOPMENT_RUNTIME
schema_version: 1
path_policy:
  path_step_s: 0.002
  path_clearance_m: 0.002
rgb_sync:
  max_age_s: 0.1
  max_skew_s: 0.1
safety_release:
  support_distance_max_m: 0.002
hard_stops:
  rtf_min: 0.90
  disk_free_min_bytes: 53687091200
```

本节取代 path/RGB/端点数值必须有预先测量报告的要求；不取代 runtime 的安全和数据检查。缺失配置时可用已安装的上述显式初值，不把它当作缺失证据的万能默认。运行中发现问题保存日志、源时间和实际 rc；调整由用户/显式配置操作完成，下一次运行建立新身份，旧 QUALIFIED 不沿用。

所有模式共用 inputs 冻结器、Recorder、封印、回读和 result verifier。端点策略完整内容、两个目标 Pose 和 recipe/变换 hash 都进入 inputs hash 链。acquisition、reference、执行事件、physics/contact/Planning Scene 原始记录仍按原 schema 留存；不因取消过程评分而删掉原始证据或因果标签证据。质量测量可以作为可选审计分析，但不产生伪造校准 PASS，不参与任务结果聚合。

## 6. 独立 QC、提交与统计

共享纯计算器读取真实两端 Pose、冻结目标和端点策略，输出五个误差及通过情况。新进程从已封印的边界事件和 physics history 确定样本后复算；不能相信 Worker 自报端点 PASS。共同 verifier/Coordinator/aggregator 使用相同规则，训练导出验证完整 hash 和用途身份。

QC 报告保持顶层共同 schema，通过已版本化 `rule_version=endpoint_pose_v1` 和 `checks.endpoint_pose` 记录结果。`checks.endpoint_pose` closed keys 为 `status,policy_sha256,initial_sequence,final_sequence,initial_pose,final_pose,initial_target,final_target,errors,passed`；Pose 为 `xyz_xyzw` 七个有限实数；`errors/passed` 的键与五个阈值一一对应。报告身份和 inputs hash 提供 object/frame/lease 绑定。共同 schema 验证器须显式接受此版本，未知或缺失规则不得回退。

W1/W2/W8、正式采集和 ACT rollout 的原“物理成功率”改按端点规则计算，并同时报告整体成功率、数据 QC 合格率、安全停止和失败分类。原统计次数、Head 搜索分母、干预、120 s deadline、业务失败不重试和 W2→独立 exact-W8/40 场景顺序不变。旧的过程质量成功率与新端点成功率不能直接混算或用于宣称无退化。

## 7. 失效和执行顺序

本次是受控 source/config/policy/验收合同变更。旧 bundle/live/QUALIFIED、旧资格基线和已封存数据不能用来授权新规则运行，需新 inputs/run/dataset 身份和对应门禁。旧证据只读保留原结论，不重贴新标签，也不重新计入训练配额。

先实现共享规则及单条生产闭环，在代码冻结后完成相关普通 package gate，再按原批准顺序重建正式资格及数据。不要为了本次修订抢先启动 W8、容器、训练或第二套 stack。现有 dst 是唯一代码写入者；本修订和实施计划审查通过、完成用户审阅及安全输入检查后，才由协调者下发给同一 dst。

## 8. 验收边界

必须覆盖阈值内外/等于边界、倾倒、yaw 不敏感、四元数符号、坏配置、错误对象/frame、过期/跨 reset、缺端点和历史择优拒绝。共享计算器正向控制须证明：两个端点合法且执行安全/数据证据完整时，缺少旧五项质量测量不会阻塞 prepare、终态、独立 QC 或 commit；安全故障即使终点匹配仍拒绝整体成功。

UT GREEN 不算闭环通过。代码冻结后运行实际默认 production composition：真实 MuJoCo 执行→连续 Recorder→sealed audit→独立进程 QC→实际 Coordinator→journal/index 回放；保留 installed executable、输入 hash、日志和真实退出码。负向检查只修改隔离副本，不删除原始证据。正式、诊断和用途隔离的回归必须同时通过。
