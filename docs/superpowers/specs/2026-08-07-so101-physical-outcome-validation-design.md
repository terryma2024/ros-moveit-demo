# SO-101 物理结果验收设计

日期：2026-08-07

状态：已批准设计的实现前规格

范围：SO-101 Gazebo pick-place；本文件不构成实现计划

## 1. 背景与问题陈述

当前 SO-101 正向流程在 `VERIFY_PHYSICAL_GRASP` 后执行 `ATTACH_GAZEBO`，放置时又在
`OPEN_GRIPPER` 后执行 `DETACH_GAZEBO`。这使 Gazebo detachable joint 而不是接触、摩擦、
重力和机器人运动决定杯子的搬运结果。流程可以在状态、action 和 Planning Scene 层报告
成功，却没有证明杯子被物理夹持、物理释放并最终稳定落在目标桌面区域。

当前实现还存在三个与此相关的证据缺口：

1. `GazeboWorldObserver` 已订阅 `task_object_contact_bottom`，但 `onContacts()` 仅保留
   fixed finger 和 moving jaw 的碰撞；杯底与桌面的接触在过滤阶段被丢弃。
2. `WorldSnapshot` 只有单点 pose、attachment、gripper contact 和基于 pose window 的
   `gazebo_task_object_stationary`，没有可隔离于释放前样本的 release epoch，也没有最终支撑
   接触、线速度和角速度证据。
3. 当前 detach/sync contract 围绕标称 `place_pose` 和 Gazebo joint detach 建模，恢复路径会
   自动走 `RECOVER_OPEN_GRIPPER`。对真正由物理接触夹持的杯子，这可能在杯子离开支撑面时
   自动松手，并在最终失败后改变待取证结果。

本设计把 Gazebo 重新确立为杯子物理真值源，把 MoveIt attachment 限定为碰撞规划 shadow，
并把成功定义改为“释放后稳定的物理结果 + 全程硬安全不变量”。五次连续运行不再要求中间
样本完全一致，而要求每次都满足同一个最终结果 contract。

## 2. 目标与明确非目标

### 2.1 目标

- SO-101 正常正向流程从 `CLOSE_GRIPPER` 到物理释放结束绝不创建 Gazebo attachment。
- 保留 MoveIt Planning Scene attachment，但它只作为 collision-planning shadow，并从最新、
  authoritative、fresh、finite 的 Gazebo 杯子 pose 创建。
- 搬运期间保存 contact、q6、杯子相对 TCP drift、Gazebo/MoveIt shadow drift 等分布型遥测；
  普通随机波动不再直接等同失败。
- 保留 controller/execution、freshness、finite、禁碰、现有 penetration ceiling、灾难性丢杯和
  planning-shadow divergence 等硬门控。
- 在打开夹爪前先 detach MoveIt；`OPEN_GRIPPER` 后完全依靠 Gazebo physics。
- 从 release epoch 之后的新样本判断最终位置、支撑、姿态、速度、接触和双重 detached 状态。
- 对最终失败给出互斥、可诊断的 failure code，并保留原始观察与中间分布指标。
- 失败时不在无支撑处自动松开物理夹持的杯子；reset 是独立、受控 transaction。
- 与共享 `pick_place_common` 和 Panda workflow 保持显式兼容。

### 2.2 非目标

- 不修改 Gazebo 物理引擎、杯子质量、摩擦、碰撞几何、控制器或运动目标来“制造”成功。
- 不复活已证伪的 0.75 mm seat、独立 `CLOSE_GRIPPER` seat motion、单纯延长 close duration、
  放宽安全门控或未注册 fixed-port retry fixture。
- 不把 MoveIt attached object pose、标称 `place_pose`、RViz 画面或状态机 `DONE` 当成物理结果。
- 不要求五次运行的 carry drift、q6 或 contact sample 完全相同。
- 不在本设计中确定新阈值数值；所有新阈值必须可配置，并由后续 live calibration 证据说明。
- 不改变 Panda 的物理 attachment 语义；Panda 是否迁移到相同模型属于独立设计。
- 不在本轮修改实验账本、运行仿真、生成实现计划或改变 runtime state。

## 3. 物理真值与 planning shadow 所有权

### 3.1 权威边界

| 事实 | 唯一权威源 | 禁止用途 |
|---|---|---|
| 杯子 world pose、姿态、运动和支撑接触 | Gazebo | 不得由 MoveIt attached pose 或标称目标替代 |
| 杯子是否被物理 joint 固定 | Gazebo attachment relay | 正常 SO-101 正向流程必须始终为 detached |
| 夹爪/杯子和杯底/桌面接触 | Gazebo contact sensors | 不得由几何距离推断来替代实际接触 |
| controller 与轨迹执行健康 | ROS 2 controller/action/joint feedback | 不得由 `plan()` 成功替代 |
| world/attached collision membership | MoveIt Planning Scene | 不得驱动或回写 Gazebo pose |
| 最终可计数成功 | release-epoch evaluator + final scene sync contract | 不得由单点 snapshot、日志或截图单独建立 |

### 3.2 MoveIt shadow 创建

`ATTACH_MOVEIT` 必须继续使用 `SO101MoveItScenePolicy` 的 upsert-before-attach 模式，但输入是
`VERIFY_PHYSICAL_GRASP` 之后、执行 `ATTACH_MOVEIT` 前立即获取的 fresh、finite Gazebo world
pose。不得使用 `SO101Profile::calibrated_grasp_relative_pose` 重新放置杯子，也不得调用
`GazeboAttachmentExecutor`。attach 后 MoveIt 自己维护 attached collision object 供后续规划；
这个对象是 shadow，不是物理状态。

`ATTACH_MOVEIT` 的 postcondition 要验证：正确 object id、attached link、touch links、world
集合移除，以及由 attach 时 Gazebo pose 与 attach link pose 推导出的实际相对 pose。当前
`requireExactMoveItAttachment()` 将 attached relative pose 与 calibrated pose 比较的契约需要
改为与本次 attach snapshot 的派生 relative pose 比较。

### 3.3 单向数据流

数据只允许 `Gazebo observation -> MoveIt collision shadow`。`MoveIt -> Gazebo` 的 pose 或
attachment 写入在正常 workflow 中不存在。`WorldResetCoordinator` 仍可在独立 reset transaction
中 defensively detach stale Gazebo joint；这不是正向流程的一部分，也不能计入 run success。

## 4. 提议状态机

SO-101 正向路径为：

```text
IDLE
 -> PREPARE_OPEN_GRIPPER
 -> MOVE_ABOVE_OBJECT
 -> DESCEND
 -> CLOSE_GRIPPER
 -> WAIT_GRASP_STABLE
 -> MICRO_LIFT
 -> WAIT_MICRO_LIFT_STABLE
 -> VERIFY_PHYSICAL_GRASP
 -> ATTACH_MOVEIT
 -> LIFT
 -> MOVE_ABOVE_PLACE
 -> DESCEND_TO_PLACE
 -> DETACH_MOVEIT
 -> OPEN_GRIPPER
 -> WAIT_RELEASE_SETTLE
 -> VALIDATE_FINAL_PLACEMENT
 -> SYNC_WORLD_OBJECT
 -> RETREAT
 -> DONE
```

新共享状态建议命名为 `WAIT_RELEASE_SETTLE` 和 `VALIDATE_FINAL_PLACEMENT`。名称表达真实动作，
不保留误导性的 SO-101 `ATTACH_GAZEBO`/`DETACH_GAZEBO` no-op。`WAIT_RELEASE_SETTLE` 是有界
采样 action；`VALIDATE_FINAL_PLACEMENT` 是只读判定 action。二者都是 SO-101 forward action，
不是 motion-planning state，也不进入 `plan_only_states`。

`DETACH_MOVEIT` 必须位于 `OPEN_GRIPPER` 之前。它只删除 attached collision shadow 并恢复
临时 world object membership；随后物理释放期间该 world object 可能暂时落后于 Gazebo，故
不得用于控制物理。`SYNC_WORLD_OBJECT` 在最终物理 pose 已冻结后，用 evaluator 选定的最终
Gazebo pose 更新 world collision object。

`VALIDATE_FINAL_PLACEMENT` 先完成所有物理条件并产生 immutable final-result evidence；
`SYNC_WORLD_OBJECT` 再消费同一 final pose。最终 placement contract 直到 sync postcondition
证明 world object pose 一致才完整，只有此后才可 `RETREAT` 和 `DONE`。这样既保持批准的状态
顺序，也满足“最终 MoveIt world-object synchronization”属于最终成功条件。

共享 `State` 仍保留 `ATTACH_GAZEBO`、`DETACH_GAZEBO` 和 `RECOVER_DETACH_GAZEBO`，因为 Panda
workflow 和共享 `GazeboAttachmentExecutor` 仍使用它们。只从 `so101WorkflowDefinition()` 的
正向集合、转移和 SO-101 runtime registration 中移除正常 attach/detach；不得全局删除枚举。

## 5. Observation 与数据模型

### 5.1 `WorldSnapshot` 扩展

在 `pick_place_common/world_observer.hpp` 的共享 snapshot 中增加通用、可选字段，保持 Panda
observer 源码兼容：

- Gazebo pose sample 的 source timestamp/monotonic receipt sequence；
- 杯子 derived linear speed 和 angular speed，以及计算它们的 sample interval；
- 杯底与 intended table 的 fresh contact boolean；
- 支撑 contact 的 collision names、有效物理 contact points、depth 范围和 contact timestamp；
- 明确的 contact-evidence freshness，而不是以任意一个 sensor callback 刷新全体接触；
- 可选的 Gazebo-vs-MoveIt shadow position/orientation divergence metrics；
- release epoch id/sequence 只放在 evaluator-owned sample record 中，不把当前 snapshot 伪装成
  epoch accumulator。

共享字段保持 `std::optional`，Panda observer 未提供时仍可编译和运行；只有 SO-101 的新状态
contract 要求这些字段存在。

### 5.2 支撑接触证据

`GazeboWorldObserver::Impl::onContacts()` 必须按 sensor identity 和 collision pair 分类，而不是
先要求 `robot_gripper`。对 `task_object_contact_bottom`：

- 只接受一端属于当前 `task_object_id`、另一端精确匹配配置的 intended table collision；
- 继续丢弃缺失、non-finite 或负 depth 的 manifold point；
- 保留 world/object-frame contact point、normal、depth、双方 collision name 和独立 timestamp；
- 其他地面、机器人、pedestal 或未知 collision 不得满足支撑条件，但应作为诊断 metric 保存；
- bottom sensor 的新消息不得延长旧 finger contact 的 freshness，反之亦然。

当前 `mergeFreshContactEvidence()` 用一个 `contact_received_at_ = now` 汇总不同 sensor，会把旧证据
伪装成新证据。实现必须按 evidence 自身 timestamp 逐项输出 freshness，并区分
`gripper_contact_observed_at` 与 `support_contact_observed_at`。

### 5.3 速度与稳定窗口

速度必须由 release epoch 内按时间排序的 Gazebo pose 样本派生，不使用 controller target 或
MoveIt pose。线速度由相邻 position/time 计算；角速度由规范化 quaternion 的最短角距离/time
计算。拒绝 non-monotonic timestamp、过短/无效时间间隔和 non-finite pose。

现有 `PoseStabilityTracker` 可作为低层窗口工具扩展或被专用 evaluator 组合，但不能让
`OPEN_GRIPPER` 之前已积累的 stationary 样本进入 release window。中间样本必须保留为 bounded
ring buffer 或逐次聚合 metrics，避免只留下最后一个 boolean。

### 5.4 Checkpoint 与 resume

新状态改变 shared enum/string 映射与 SO-101 workflow，因此 `domain_types.cpp`、checkpoint JSON
解析、`checkpoint_validation`、`common_resume_validator`、SO-101 `file_checkpoint_store.cpp` 和
Teleop workflow trace 都是兼容边界。

release epoch 是进程内、run-scoped、不可跨 resume 伪造的证据。以下 checkpoint 不可直接恢复
为“继续使用旧窗口”：

- `OPEN_GRIPPER` 已完成但 release window 未完成；
- `WAIT_RELEASE_SETTLE` 或 `VALIDATE_FINAL_PLACEMENT` 中断；
- final physical result 已失败但尚未完成 evidence persistence。

实现计划必须在两种安全策略中选定一种：把这些 checkpoint 标为 non-resumable，或保存足够的
release marker 并在恢复后创建全新 epoch、重新收集全部 post-release 样本。无论选择哪种，均
不得复用 checkpoint 中单点 `gazebo_task_object_stationary` 作为最终稳定证据。checkpoint schema
需要显式升级并拒绝旧 schema 的歧义恢复；旧文件不得静默解释为新语义。

## 6. 中间 telemetry 与硬安全门控

### 6.1 仅作为 telemetry 的 carry 波动

从 physical grasp 验证通过到 `DETACH_MOVEIT` 前，以下 bounded stochastic quantities 记录完整
分布信息，但不以“每个样本等于 nominal”作为普通成功条件：

- fixed/moving contact presence、contact point、normal 和 solver depth；
- q6 position、velocity、controller error/abort disposition；
- 杯子相对 TCP 的 position/orientation drift；
- Gazebo pose 与 MoveIt collision shadow pose 的 divergence；
- 各状态窗口的 min/max/mean、sample count、超界 count 和发生状态。

这些 metric 必须进入 action/contract failure、运行摘要和后续实验 ledger evidence，而不能只留在
高频日志。允许中间接触切换或小幅 drift，不意味着忽略它们。

### 6.2 始终阻断的硬门控

以下仍是 hard failure：

- observation 不 fresh、字段缺失、timestamp 无效或任何参与判定的数值 non-finite；
- controller/action 执行失败、取消/超时未收敛、反馈缺失或机器人执行健康不成立；
- 现有 forbidden collision、gripper penetration ceiling 和规划路径碰撞限制被突破；
- catastrophic object loss：例如杯子越出可恢复 workspace、跌落桌面/穿透环境、与 TCP 分离到
  物理抓持已明显丧失，或其 pose/velocity 超出配置的灾难边界；
- 正常 SO-101 正向流程中 `gazebo_task_object_attached == true`；
- planning shadow divergence 超过配置上限，以致后续 collision planning 不可信。

“bounded telemetry”只改变普通 carry 波动的判定方式，不放宽现有安全 ceiling。现有数值继续由
当前已审计 policy/profile 管理；任何新边界都必须可配置并经 live calibration 证明。

## 7. 最终放置 contract 与 release epoch

### 7.1 Epoch 边界

`OPEN_GRIPPER` action 成功且 post-observation 首次确认夹爪进入 release/open 状态时，创建新的
`release_epoch_id` 和 monotonic `release_start_sequence`。先清空 evaluator 的 pose/contact/
attachment 窗口，再接受 sequence 严格晚于 marker 的样本。不得以进入 `DETACH_MOVEIT`、发出
open command 或 wall-clock 猜测作为 epoch 起点。

`WAIT_RELEASE_SETTLE` 持续采样，直到满足配置的 consecutive sample count 和 minimum duration，
或达到有界 timeout。每一个 counted sample 必须同时来自同一 simulation session、晚于 epoch、
fresh、finite，并覆盖所需 Gazebo/MoveIt/contact 字段。连续性被 stale、缺失或反向 timestamp
打断时计数归零，但样本和原因仍留作 metrics。

### 7.2 每个最终样本的条件

最终稳定窗口中的每个 counted sample 必须满足：

- 杯子中心 XY 落在配置的最终目标 region；region 是明确几何区域，不只是一点距离日志；
- 杯子 pose/杯底高度落在配置的 support-height range；
- 杯子 local +Z 相对 world +Z 的 tilt 不超过配置上限；
- derived linear speed 和 angular speed 不超过配置上限；
- `task_object_contact_bottom` 报告杯底与 intended table 的 fresh physical contact；
- 无 fresh fixed finger、moving jaw 或其他 gripper contact；
- `gazebo_task_object_attached == false`；
- `moveit_task_object_attached == false`；
- session id、object id 和 table collision identity 与本次 run/config 一致。

最终 pose 取合格稳定窗口中明确定义的代表样本。建议使用最后一个 counted Gazebo sample，确保
`SYNC_WORLD_OBJECT` 使用最新 authoritative pose；实现计划必须锁定这一选择并测试，不能使用
标称 `place_pose` 或窗口前样本。

### 7.3 Failure code

失败优先保留所有 violated predicates 为 metrics，同时返回一个稳定 primary code。至少定义：

- `FINAL_PLACEMENT_OUT_OF_REGION`
- `FINAL_PLACEMENT_UNSUPPORTED`
- `FINAL_PLACEMENT_TIPPED`
- `FINAL_PLACEMENT_STILL_MOVING`
- `FINAL_PLACEMENT_GRIPPER_CONTACT`
- `FINAL_PLACEMENT_EVIDENCE_STALE`
- `PLANNING_SHADOW_DIVERGENCE`
- `FINAL_PLACEMENT_SAFETY_FAILURE`

Gazebo attached、MoveIt attached、controller failure、forbidden collision、penetration 或
catastrophic loss 等具体事实应在 metrics/subcode 中保留；实现计划需给 primary-code precedence
一个确定、可测试的顺序。timeout 不能笼统返回 `NOT_STATIONARY`：必须根据窗口内最新可信证据
区分 out-of-region、unsupported、tipped、still-moving、gripper-contact 或 stale。

### 7.4 Final sync

`VALIDATE_FINAL_PLACEMENT` 成功后冻结 `FinalPlacementEvidence`，其中包含 epoch id、最终 Gazebo
pose、窗口时段、sample count、速度/倾角/支撑/contact metrics 和双重 detached 事实。
`SYNC_WORLD_OBJECT` 只能消费该证据中的 pose；完成后 postcondition 必须验证：

- MoveIt 中杯子不 attached，且 world object 唯一存在；
- MoveIt world pose 与冻结的 final Gazebo pose 在 scene convergence tolerance 内一致；
- 同期 Gazebo pose 仍 fresh，且没有出现需要使结果失效的安全变化。

sync 失败不抹掉已经观察到的物理结果，但整次 run 不能成功。

## 8. MoveIt shadow drift policy

carry 期间以同一时刻的 Gazebo cup world pose 和 `moveit_gripper_pose_world *
moveit_task_object_attached_relative_pose` 计算 position/orientation divergence。比较必须使用
fresh、finite 且时间上可配对的 observation；不能把不同状态的旧样本拼在一起。

policy 分两层：

1. 低于 hard divergence limit：记录 distribution telemetry，继续正常流程；不要求五次运行的
   drift 完全相同。
2. 达到或超过 hard limit，或无法取得可信 paired evidence：在下一个需要 collision planning 的
   状态前以 `PLANNING_SHADOW_DIVERGENCE` 阻断。不得自动把 MoveIt shadow 重新定位来掩盖物理
   drift，也不得让 MoveIt pose 回写 Gazebo。

检查点至少位于 `ATTACH_MOVEIT` postcondition、`LIFT`、`MOVE_ABOVE_PLACE` 和
`DESCEND_TO_PLACE` 的 planning precondition。`DETACH_MOVEIT` 前还要保留最终 carry divergence
metric。新 limit 和时间配对容差必须可配置，并由 live calibration 说明依据。

## 9. 失败与 recovery 语义

### 9.1 Hold-first 原则

一旦 physical grasp 已建立，任何失败都先 cancel active goal、停止/hold robot 和 gripper、冻结
evidence。只有观察证明杯子受到 intended table 支撑且松开不会造成掉落时，recovery 才可执行
`OPEN_GRIPPER`。不满足该证明时返回错误并保持夹持；不得自动沿当前通用链进入
`RECOVER_OPEN_GRIPPER`。

这要求 `SO101RecoveryPolicy::select()` 和 `canSkipRecoveryAction()` 按“是否物理持杯、是否受到
支撑、是否已 release、是否 final evidence frozen”选择路线，而不是仅按 failed state 和
MoveIt/Gazebo attachment。`RECOVER_DETACH_GAZEBO` 可保留用于清理历史 stale joint 或 reset，
但正常 forward failure 不应因其存在而假定杯子可安全打开。

### 9.2 最终失败保护

在 `OPEN_GRIPPER` 之后，最终 outcome 失败必须先保存完整 `FinalPlacementEvidence` 和失败
metrics。recovery 不得移动机器人、杯子、Planning Scene world pose 或调用 reset 来美化结果。
允许的自动动作仅限停止/hold 与无副作用的追加观察。用户随后显式启动的 reset 是新的 controlled
transaction，拥有独立 run/session/evidence 边界。

### 9.3 Reset

`WorldResetCoordinator` 继续按既有顺序 defensively detach stale Gazebo joint、清理 MoveIt
attachment、park/reset cup、reset robot 并验证收敛。reset 成功不能追认前一 pick-place 成功，
也不能覆盖前一 run 的 final failure evidence。

## 10. 配置 schema

新字段归入 `validation_policies/light_cup_wall_pick.yaml`，而不是硬编码进 `SO101Profile`。建议在
validation policy schema 的新版本加入以下严格 map；`policy_config.cpp` 继续 reject unknown field、
missing field、non-finite/非正值及不一致上下界：

```yaml
physical_outcome:
  intended_support_collision: <string>
  final_target_region:
    kind: circle | axis_aligned_box
    # circle: center_xy_m + radius_m
    # axis_aligned_box: min_xy_m + max_xy_m
  support_height_range_m: [<min>, <max>]
  max_upright_tilt_rad: <positive finite>
  max_linear_speed_m_s: <positive finite>
  max_angular_speed_rad_s: <positive finite>
  consecutive_samples: <positive integer>
  minimum_stable_duration_s: <positive finite>
  sample_interval_s: <positive finite>
  settle_timeout_s: <positive finite>
  max_observation_age_s: <positive finite>
  catastrophic_loss:
    workspace_bounds_m: <finite bounds>
    max_relative_position_drift_m: <positive finite>
    max_relative_orientation_drift_rad: <positive finite>
  planning_shadow:
    max_position_divergence_m: <positive finite>
    max_orientation_divergence_rad: <positive finite>
    max_pair_age_s: <positive finite>
```

具体 region kind 只实现当前 campaign 需要的一种也可以，避免无用抽象；但 schema 必须表达区域而
不是复用 motion endpoint tolerance。`settle_timeout_s` 必须不小于 minimum duration，height
range 与 workspace bounds 必须有严格次序。所有新数值在提交默认值前都要由 live calibration
记录来源、采样分布、保守余量和未放宽的安全 ceiling。本设计不授权任何新数值。

policy schema version、`LoadedPolicyBundle::bundle_sha256` 和 checkpoint fingerprint 会因此变化。
launch 参数仍只传 policy 路径，不新增一组松散 CLI threshold，确保 CLI、Teleop 和 standalone
node 使用同一 bundle。

## 11. 测试策略

实现必须遵循 RED -> GREEN，先覆盖 contract，再做 package 和 live 验收。

### 11.1 Shared/common 单测

- `domain_types`：新状态 string round-trip、`isAction`/`isForwardAction` 的 workflow-specific
  边界不被全局误判。
- `workflow_definition`/runner：新状态可执行、stop-after/single-step/plan-only 行为正确；Panda
  workflow 仍含 Gazebo attach/detach 并完整注册。
- checkpoint：schema 升级、旧 schema 明确拒绝、release-window checkpoint 不复用旧样本。
- snapshot/pose utility：quaternion shortest-angle、derived speed、non-monotonic/non-finite rejection。

### 11.2 SO-101 单元与 contract 测试

- `test_transition_table.cpp`、`test_workflow_characterization.cpp`、`test_dry_run.cpp`：精确新正向
  trace 中没有 `ATTACH_GAZEBO`/`DETACH_GAZEBO`，且 detach MoveIt 先于 open。
- `test_so101_task3_runtime.cpp`/`test_so101_pick_place_runtime.cpp`：只注册 recovery/reset 所需的
  Gazebo detach，不注册 forward attach/detach；新 evaluator/action/contract 覆盖完整。
- observer 测试：bottom-table contact 被保留；非 table contact 不算 support；finger/bottom 的
  freshness 独立；negative/non-finite depth 被拒绝。
- release evaluator 测试：release 前样本绝不计数；consecutive count、minimum duration、epoch/
  session 隔离；位置、高度、倾角、速度、支撑、gripper contact 和双重 detached 的正反例。
- failure precedence 测试：八类 primary failure code 稳定，所有同时违反项仍进入 metrics。
- MoveIt scene 测试：attach 从最新 Gazebo pose upsert；relative pose 是本次派生值；shadow drift
  在 limit 内只记录、越界阻断；final sync 使用 frozen final pose。
- recovery 测试：off-support physically-held cup 只 hold、不 open；final failure 不移动杯子；
  独立 reset 仍可清理 stale Gazebo joint。
- policy parser 测试：schema、unknown/missing/non-finite、range ordering 和 timing consistency。

### 11.3 Compatibility、launch 与 Teleop 测试

- Panda registration/workflow characterization 全部保持原语义。
- SO-101 launch/config contract 确认 validation bundle 被所有入口一致加载。
- `file_checkpoint_store` JSON round-trip 和旧版本拒绝。
- Teleop `workflow_gateway.py` 不复制 transition table，能展示新 state、failure code 和 metrics；
  force-continue 仍只适用于批准的 physical-grasp validation boundary，不能跳过 final placement 或
  safety failure。
- `/snapshot`/workflow response 能暴露 final outcome 摘要、epoch/sample count、支撑和 detached
  事实；OpenAPI/model 测试同步更新。

### 11.4 验证阶梯

定向单测通过后运行 `pick_place_common` 与 `so101_gazebo_demo` package tests、只读 formatting
checks 和 launch contract。随后才在实现阶段 build/source 正确 overlay，做 dry-run、plan-only、
headless execute、GUI execute。不得用 dry-run 或 plan-only 计入物理成功。

## 12. 五次 live acceptance 与 ledger evidence

继续使用 `docs/experiments/so101-reset-world-five-success-experiment-ledger.md`，但在后续实现/验证
turn 新增清晰分隔的 **physical-outcome campaign**；不得改写旧 experiment 或把旧成功计入新批次。

新 campaign 固定同一 source commit、installed overlay、policy bundle fingerprint、run mode、
lifecycle 和成功 contract。五次均为 `VALID` 且连续成功；任何 `VALID` failure 终止序列，任何
`INVALID` 污染终止当前批次但不计产品失败。每次 run 前后使用独立 experiment id，并记录：

- source/install/runtime executable、`ROS_DOMAIN_ID`、`GZ_PARTITION`、session id；
- release epoch marker、采样时段、count、最终 Gazebo pose；
- target-region、height、tilt、linear/angular speed、support contact、gripper contact；
- Gazebo detached、MoveIt detached、final MoveIt world sync；
- carry telemetry distributions、最大 shadow divergence、硬安全 gate 结果；
- controller/action exit、state trace、failure code/metrics；
- 本轮新 Gazebo/RViz/Teleop snapshot 和最终截图路径。

单次 success 是最终稳定物理 outcome 全部成立、final sync 成功、全程 hard safety invariant 未违反，
且 `RETREAT -> DONE` 正常完成。中间 sample 不同不影响计数，只要 telemetry 留存且未越硬门控。

## 13. Migration、兼容性与 rollout

### 13.1 精确受影响组件

| 边界 | 当前组件 | 设计影响 |
|---|---|---|
| shared State/string | `pick_place_common/domain_types.hpp`, `domain_types.cpp` | 新增两状态；保留 Panda 所需 Gazebo states |
| workflow | `so101_workflow.cpp`, `transition_table.cpp`; `panda_workflow.cpp` | 只替换 SO-101 正向图；Panda 不变 |
| runtime registration | `so101_task3_runtime.*`, `pick_place_runtime.cpp`, state machine node wiring | 移除 SO-101 forward Gazebo attach/detach；注册 settle/evaluator |
| attachment contracts | `so101_attachment_contracts.cpp`, `SO101MoveItScenePolicy`, common `moveit_scene_executor` | 改为 physical carry + derived shadow pose；final sync contract |
| observer/snapshot | common `world_observer.hpp`, SO-101 `gazebo_world_observer.cpp` | 独立 bottom support、timestamps、速度输入、drift evidence |
| checkpoint/resume | common checkpoint/runner/validators；SO-101 `file_checkpoint_store.cpp`, resume policy | schema 升级；release epoch 不跨界复用 |
| policy parsing | `policy_config.*`, validation YAML, configuration tests | 新 strict `physical_outcome` schema；bundle hash 更新 |
| recovery/reset | `so101_recovery_policy.cpp`, runner recovery, `world_reset_coordinator.*` | hold-first；final evidence preservation；reset 仍防御 detach |
| tests | common、SO-101 pick_place、launch/config、Panda characterization | 新 trace/contract；共享兼容回归 |
| Teleop/evidence | `so101_teleop/{models,server,workflow_gateway,telemetry}.py`, OpenAPI/web consumers | 展示新 state/failure/metrics，不复制判定逻辑 |

此外，`docs/pick-place-architecture.md`、`docs/pick-place-launch-parameters.md`、package README 和
SO-101 skill 的按状态验收表在实现时需要同步，避免继续宣称 normal workflow 使用 Gazebo joint。

### 13.2 Rollout 顺序

1. 先引入兼容的数据类型、policy schema 和纯 evaluator，保持 production workflow 未切换。
2. 建立 observer、MoveIt shadow 和 recovery contract 的自动回归证据。
3. 原子切换 SO-101 workflow/runtime registration，确保不存在半迁移的 attach/no-op 路径。
4. 更新 checkpoint schema、Teleop/snapshot 和文档消费者。
5. 完成 package/dry-run/plan-only/headless/GUI 阶梯后，启动独立 physical-outcome five-run campaign。

rollout 不提供 legacy SO-101 forward-attach 开关。保留开关会形成两套相反物理语义并使验收不可
比较。回滚应回滚整个 workflow commit，而不是运行时选择旧 joint attach。

## 14. 被拒绝的替代方案

1. **保留 `ATTACH_GAZEBO`/`DETACH_GAZEBO` 为 no-op。** 状态名会继续虚假表达物理所有权，
   checkpoint、Teleop 和 ledger 也会产生误导证据，因此拒绝。
2. **继续用 Gazebo detachable joint 搬运，只在末尾增加稳定检查。** 最终落杯仍不能证明真实
   grasp/carry，违背本设计的物理真值边界。
3. **完全移除 MoveIt attachment。** carry planning 会失去杯子碰撞体，无法保证机器人、杯子与
   环境的规划安全；保留 collision shadow 更合适。
4. **用标称 `place_pose` 同步 MoveIt。** 会覆盖失败的真实落点并污染证据；必须使用冻结的最终
   Gazebo pose。
5. **把 carry 中每个 contact/q6/drift 样本设为成功门槛。** 物理接触具有随机性，会把可接受的
   分布波动误判为失败；只保留明确 safety ceiling 和 shadow-validity gate。
6. **放宽 penetration/collision/safety gate 来提高成功率。** 会把安全退化包装成稳定性提升，
   明确禁止。
7. **失败后自动 open、retreat 或 reset。** 可能在空中掉杯或改变最终失败结果，破坏取证。
8. **复活 0.75 mm seat、独立 close seat motion、延长 close duration 或 fixed-port retry。** R3
   审计已否定或排除这些路线；当前 main 已包含有效 R3 refactor 与 reset-2s/
   `MOVE_ABOVE_OBJECT-0.03` fixes，本设计不倒退。
9. **要求五次中间轨迹/接触完全一致。** 不符合随机物理系统，且不能比最终 outcome + hard
   invariants 提供更正确的产品结论。

## 15. 后续 implementation plan 必须解决的开放细节

以下是实现选择，不得改变已批准语义：

- `WAIT_RELEASE_SETTLE` 与 `VALIDATE_FINAL_PLACEMENT` 的 executor/evaluator 文件拆分、接口签名和
  evidence store 生命周期。
- release marker 取自 gripper post-observation 的精确 sequence，及 observer 如何提供跨 topic
  可比较的 receipt sequence/timestamp。
- velocity derivation 使用相邻样本还是窗口回归；选择必须抵抗不等间隔采样并有确定测试 oracle。
- final target region 首版采用 circle 还是 axis-aligned box，以及如何由 campaign 目标表达；不能
  退化成标称 pose 的隐式 tolerance。
- 多条件同时失败时 primary failure precedence 的固定顺序和 subcode/metrics 命名。
- `FinalPlacementEvidence` 如何传给 `SYNC_WORLD_OBJECT` 并持久化，同时避免把进程内 epoch window
  错误恢复。
- interrupted post-release checkpoint 采用 non-resumable 还是 fresh-epoch resume；两者都必须
  禁止复用旧样本并保护已观察结果。
- shadow pose 时间配对、divergence 计算所在层，以及进入每个 carrying planner 前的 gate 注入点。
- hold-first recovery 的 controller/gripper hold primitive、超时和 operator-facing 指示；不得因此
  自动 open off-support cup。
- bottom sensor 中 intended table collision 的精确 scoped-name 解析和对 world/model 前缀的稳健
  规范化。
- metrics 的 bounded storage、聚合字段和 Teleop/OpenAPI 表达，保证足够 ledger evidence 而不让
  checkpoint 或响应无限增长。
- policy schema 的版本号、旧 checkpoint 的迁移错误文案，以及 Panda 对新增 optional snapshot
  字段的 compile/runtime compatibility tests。
- live calibration protocol：如何在不放宽现有硬安全限制的前提下，为所有新阈值记录分布、
  余量、provenance 和批准依据。

这些细节将在用户审阅本 spec 后由单独的 implementation plan 分解为 TDD tasks。本文件不授权
生产代码、测试、配置、账本或 runtime state 的修改。

## 16. 2026-08-08 经用户批准的 support-evidence 窄化修订

`DBG-PHYSICAL-001` 的 live A/B 证明：production `gz-physics-bullet-featherstone-plugin` 把同一
link 的真实杯底/桌面接触归到 compound owner collision，并在稳定静止时报告量级很小的负
`depth` 数值噪声。DART 无法创建现有机器人 mesh/VHACD collision，classic Bullet 则不提供所需
contact stream；因此不能靠更换 physics engine 解决，同时仍保持既有碰撞安全层。

用户明确批准以下窄化语义，替代第 5.2 节中“只能来自专用 bottom collision identity”与“任何负
depth 一律拒绝”的过强实现假设，但不改变物理结果所有权：

- `GazeboWorldObserver` 可以把 Bullet Featherstone compound owner 上真实的
  `task object ↔ intended table` contact 作为 intended support evidence；counterparty 仍必须精确
  匹配配置的 table collision，不能以 pose 距离、标称高度或 MoveIt 几何替代真实 contact。
- 增加严格配置化的 `minimum_support_contact_depth_m`。它是经 live calibration 证明的负向数值
  噪声下限；仅接受 finite 且 `depth >= minimum_support_contact_depth_m` 的 sample。缺失、non-finite
  或更负的 depth 继续拒绝。该阈值不是 penetration ceiling，不得用于放宽任何既有碰撞/穿透门控。
- compound-owner identity、原始 collision names、原始 depth min/max、被 noise bound 接受/拒绝的
  sample count 必须保留为 bounded metrics，确保 ledger 可审计。
- 最终成功仍同时要求 target XY region、support-height range、upright tilt、derived linear/angular
  speed、无 gripper contact、Gazebo detached、MoveIt detached 和最终 world-object sync。
- physics engine、collision geometry、cup mass/friction、controller、motion target，以及现有
  forbidden-collision/penetration safety ceilings 均不得改变。
- 正常 SO-101 forward path 仍不得 Gazebo attach/detach；MoveIt attachment 仍只作为从最新 Gazebo
  pose 创建的 collision-planning shadow，并在物理 `OPEN_GRIPPER` 前 detach。

该修订必须先经 stable Featherstone compound-owner + bounded-negative-noise 的自动回归
RED→GREEN，再重新执行现场校准。此前 `CAL-PHYSICAL-001` 继续保持 `INVALID`，不得反向用于选值。

## 17. 2026-08-08 经用户批准的 grasp/motion target 校准 addendum

### 17.1 授权边界

HEAD `2eda34cebc26f359b6687e1f03808fe700c49d01` 的 fresh-lifecycle 证据把首个有效失败收敛到
真实杯子/指垫接触深度与 object-relative drift。用户仅批准有界调整：杯子相对 TCP 的抓取位置/
姿态、`q6` 闭合目标、micro-lift 向量/高度/姿态、carry/place/retreat waypoint 与目标姿态，以及
轨迹目标时长/速度/加速度；缺少配置边界时可按 TDD 增加最小 plumbing。

controller 算法/增益/plugin、physics engine、杯子/夹爪 geometry、mass、friction、Gazebo forward
attach、MoveIt planning-shadow 语义、final-outcome 容忍范围，以及所有 penetration、planning-shadow、
collision、recovery hard ceiling 继续冻结。候选必须通过原 hard gates，不得为接受候选而改 gate。

### 17.2 baseline、单位与几何约束

长度单位为 metre，角度/joint 为 rad，scaling 为无量纲比例。权威 baseline 如下：

| 层 | 来源 | baseline |
|---|---|---|
| 抓取 TCP endpoint | motion policy `DESCEND` terminal joints 的 real-model FK；validation policy 锁定 | xyz `[0.020676684, -0.262821021, 0.200630611]`；approach axis `-Z` |
| cup spawn/geometry | task-object policy | xyz `[0.020, -0.280, 0.165]`；height `0.090`；radius `0.040`；wall/bottom `0.002` |
| 抓取轴向约束 | task-object + validation policy | below-rim nominal `0.025`、range `[0.008, 0.035]`；bottom clearance `0.020` |
| 指垫/q6 | task-object + URDF collision + motion policy | pad thickness `0.005`；gap `0.00196`；safe lower `-0.059600220867817`；close `-0.047608632840292` |
| micro-lift | runtime/retry + planning boundary | world-Z `+0.002`；hard upper bound `0.002` |
| carry/place/retreat | motion policy fixed joint ladders | 当前 `LIFT`、`MOVE_ABOVE_PLACE`、`DESCEND_TO_PLACE`、`RETREAT` ladders |
| velocity/acceleration | motion policy | above `0.03/0.03`；descend/lift `0.10/0.10`；carry `0.02/0.02`；place/retreat `0.03/0.03` |

TCP 相对 cup spawn 平移约为 `[+0.000676684, +0.017178979, +0.035630611]`，仅为当前 FK 差值，
不是 pass threshold。URDF 中 `so101_tcp` 固连于 `gripper`；fixed/moving pad collision profile 与
task-object native axial bounds 是不可修改的几何约束。

### 17.3 固定分层矩阵与有界范围

变量顺序固定 A→F；每次只改变一个 scalar，上一层消除当前首个 hard-gate failure 后才进入下一层：

1. **A / TCP translation**：x、y、z 依次。每轴相对 baseline 限于现有
   `approach_outside_clearance_m` 的 `±0.001 m`；z 还必须满足既有 below-rim/bottom-clearance 交集。
   FK 必须证明未选两轴与 orientation 不变。
2. **B / orientation**：roll、pitch、yaw 依次；单分量变化不超过现有 `axis_tolerance_rad`，且未选
   分量、TCP position、IK、collision/path contract 通过。
3. **C / q6**：`safe_lower_q6 <= candidate <= baseline grasp_close_q6`；仍满足 pad gap/fingerprint、
   feedback stability 与原 `max_penetration_m`。
4. **D / micro-lift**：位移范数 `(0, 0.002] m`；一次只改一个 vector/height/orientation 分量。
5. **E / carry/place/retreat**：一次只改一个 waypoint position 或 orientation 分量；范围为现有
   endpoint/axis tolerance、workspace、joint limit 与 trajectory collision contract 的交集。
6. **F / timing/scaling**：一次只改 duration、velocity 或 acceleration；finite positive，先限于
   controller 接受范围和当前值定义的保守不加速区间，除非 plan-only/controller contract 为更快值
   给出独立依据。

每个候选先 exact config/range contract RED，再最小 GREEN、clean build/source/prefix、完整
`plan_only`，最后才用 `stop_after`/最早可观测边界做隔离 headless 短路径。保留 solver depth、
cup/TCP pose、tilt/orientation drift、q6 feedback/velocity 与 shadow divergence。

探索候选一次 `VALID_FAILURE` 即淘汰；`INVALID` 终止批次；同方向连续三个有界候选失败则停止，
不扩大到禁止层。入选候选至少三次独立 `FULL_RESTART` qualification，任一 valid failure 退回本层。
只有冻结 commit/policy 的 full suite、dry-run、plan-only、headless、GUI 与连续五次最终物理结果
`VALID_SUCCESS` 全部成立后，才允许 push/merge。

## 18. 2026-08-10 经用户批准的释放阶段角度遥测 addendum

### 18.1 问题边界

`HEADLESS-PHYSICAL-018` 在进入 `DESCEND_TO_PLACE`、下降轨迹执行前触发
`PLANNING_SHADOW_DIVERGENCE`。位置 divergence 为 `0.000323127093308 m`，低于保留的
`0.005 m` 上限；杯体轴向角度 divergence 为 `0.103202253316 rad`，超过旧的 `0.070 rad`
中间门限。该门限阻止了物理释放，因此不能观察释放后由桌面支撑、重力、摩擦和夹爪撤离共同决定
的最终杯体结果。

### 18.2 批准语义

- `LIFT` 与 `MOVE_ABOVE_PLACE` 继续把 planning-shadow position 和 orientation divergence 作为
  hard gate，防止搬运阶段明显失稳。
- `DESCEND_TO_PLACE` 与 `RETREAT` 保留 finite、freshness、MoveIt attached membership、Gazebo
  forward-attachment forbidden、position divergence、碰撞、penetration、controller 和 arm stability
  hard gates；orientation divergence 继续记录 metric，但不阻止下降、开爪或撤离。
- `RETREAT` 是“物理已释放、planning shadow 尚 attached”的独立语义：Gazebo 杯体不再被要求跟随
  TCP，MoveIt attached object 仍参与 retreat collision planning；`RETREAT` 成功后才执行
  `DETACH_MOVEIT`。
- 当前正向顺序固定为
  `DESCEND_TO_PLACE -> OPEN_GRIPPER -> RETREAT -> DETACH_MOVEIT -> WAIT_RELEASE_SETTLE ->
  VALIDATE_FINAL_PLACEMENT -> SYNC_WORLD_OBJECT -> DONE`。本节替代此前“OPEN_GRIPPER 前 detach
  MoveIt”的旧表述。
- 释放阶段的 angle telemetry 不等于忽略最终姿态。post-release evaluator 继续要求 target region、
  intended support contact、support height、`max_upright_tilt_rad`、linear/angular stability、无 gripper
  contact、Gazebo detached 和 MoveIt detached；当前 production upright limit 保持
  `0.08726646259971647 rad`。
- physics engine、geometry、mass、friction、controller/gains、motion target、position divergence、
  penetration 和 collision ceiling 均不因本修订改变。

### 18.3 验证

自动回归必须证明：同一超角度样本在 `LIFT` 仍失败，在 `DESCEND_TO_PLACE`/`RETREAT` 仅产生
telemetry；同一超位置样本在释放阶段仍失败；retreat 使用 attached MoveIt shadow 规划但不要求
Gazebo 杯体随 TCP 移动；最终 tipped cup 仍由 `FINAL_PLACEMENT_TIPPED` 拒绝。完成 focused 与包级
GREEN 后，以唯一 GUI `FULL_RESTART` 栈执行一次，冻结日志、Gazebo pose、MoveIt membership、
controller/joint evidence 和本轮新截图。
