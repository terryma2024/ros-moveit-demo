# SO-101 自适应分批 pick-place 实验规划器设计

- 日期：2026-08-09
- 状态：已批准设计固化；用户已授权编写 spec 与 implementation plan，但尚未授权执行实现。
- 所属 worktree：`/data/work/ws_moveit/.worktrees/so101-gazebo-demo-py`，分支 `codex/so101-gazebo-demo-py`
- 上游文档：
  - `docs/superpowers/specs/2026-08-07-so101-gazebo-demo-py-design.md`（现行 Python 设计及其增补授权）
  - `docs/superpowers/plans/2026-08-07-so101-gazebo-demo-py-implementation.md`（现行实现计划）
  - `docs/experiments/so101-gazebo-demo-py-experiment-ledger.md`（实验台账，全部 append-only）
  - `docs/experiments/2026-08-08-so101-grasp-gate-failure-knowhow.md`（失败 know-how 总结）

## 1. 目标

设计一个面向**完整 SO-101 物理 pick-place** 的自适应分批实验规划器（adaptive batched
experiment planner）。规划器以动作图（ActionGraph）为单位组织实验，按"完整路径上首个失败
节点"打开局部参数子树逐节点推进，直到整链路在冻结版本下通过最终验收。

`MICRO_LIFT` 只是当前首个失败 checkpoint 所在的区段，**不得**被硬编码为规划器的中心或
终点；规划器的最终目标始终是完整物理 pick-place：杯子被物理夹取、搬运、释放，并稳定、
直立地停在批准的放置容差区内。

## 2. 支配性边界（不可违反）

1. **Gazebo 接触物理拥有杯子真实运动**：从 `CLOSE_GRIPPER` 到 `OPEN_GRIPPER` 全程，杯子的
   运动必须持续由 Gazebo 物理/接触驱动；**禁止 forward Gazebo attach**（任何把 Gazebo 物体
   直接绑定到夹爪的指令）。
2. **MoveIt Planning Scene attach/detach 保留**，但只作为碰撞规划影子（planning shadow）；
   其生命周期固定（`ATTACH_MOVEIT` / `DETACH_MOVEIT` 两个节点），**不是搜索变量**。
3. **冻结层**：物理引擎、几何、质量/摩擦、controller/增益、碰撞规则全部冻结，规划器不得
   把它们纳入搜索空间。
4. **penetration_target（目标咬合深度）是候选搜索参数**，允许范围 `[0.0001, 0.001] m`；
   `0.001 m` 是不可突破的全局硬上限。
5. **历史 solver-limit fingerprint 的处置**：当前分支历史实验曾采用 `0.0013 m` 的
   solver-limit penetration ceiling（见 ledger `CP-AUTHORIZATION-SOLVER-LIMIT-GATE-001` 与
   fingerprint `CP-QUALIFICATION-FINGERPRINT-002`）。该 ceiling 语义与本合同的
   penetration 上限不一致，属于**历史证据**，只能保留在台账中供审计；其下取得的任何结果
   **不得计入**新规划器的搜索、qualification 或最终五连验收。本 spec 只记录这一差异，
   不修改任何运行时文件。
6. **motion settle wait（运动后稳定等待）可搜索**，但验证容差、稳定观测窗口、速度阈值等
   验收语义固定，规划器不可放宽。

## 3. 动作图（ActionGraph）

### 3.1 完整成功路径

```
READY
 -> PRE_GRASP / PREPARE_OPEN_GRIPPER
 -> MOVE_ABOVE_OBJECT / APPROACH
 -> DESCEND
 -> CLOSE_GRIPPER
 -> WAIT_GRASP_STABLE / SEAT_CONTACT
 -> MICRO_LIFT
 -> WAIT_MICRO_LIFT_STABLE
 -> VERIFY_PHYSICAL_GRASP
 -> ATTACH_MOVEIT
 -> LIFT
 -> MOVE_ABOVE_PLACE / CARRY
 -> DESCEND_TO_PLACE
 -> DETACH_MOVEIT
 -> OPEN_GRIPPER / RELEASE
 -> WAIT_RELEASE_SETTLE
 -> VALIDATE_FINAL_PLACEMENT
 -> SYNC_WORLD_OBJECT
 -> RETREAT
 -> FINAL_STABLE / DONE
```

### 3.2 抽象节点到现有 Python `State` 的映射

现有 `so101_gazebo_demo_py.domain.State` 与 `live_execute.TRACE` 已覆盖成功路径的全部物理
节点。映射关系（抽象节点 -> 现有 State/TRACE 项）：

| 抽象节点 | 现有 State / TRACE |
|---|---|
| READY | `IDLE`（含环境初态断言） |
| PRE_GRASP / PREPARE_OPEN_GRIPPER | `PREPARE_OPEN_GRIPPER` |
| MOVE_ABOVE_OBJECT / APPROACH | `MOVE_ABOVE_OBJECT` |
| DESCEND | `DESCEND`（含 grasp 校正执行） |
| CLOSE_GRIPPER | `CLOSE_GRIPPER` |
| WAIT_GRASP_STABLE / SEAT_CONTACT | `WAIT_GRASP_STABLE`（含 seating preload） |
| MICRO_LIFT | `MICRO_LIFT`（+0.002 m world-Z 探针） |
| WAIT_MICRO_LIFT_STABLE | `WAIT_MICRO_LIFT_STABLE` |
| VERIFY_PHYSICAL_GRASP | `VERIFY_PHYSICAL_GRASP`（物理 gate） |
| ATTACH_MOVEIT | `ATTACH_MOVEIT`（仅影子） |
| LIFT | `LIFT` |
| MOVE_ABOVE_PLACE / CARRY | `MOVE_ABOVE_PLACE`（含 shadow gate） |
| DESCEND_TO_PLACE | `DESCEND_TO_PLACE` |
| DETACH_MOVEIT | `DETACH_MOVEIT` |
| OPEN_GRIPPER / RELEASE | `OPEN_GRIPPER` |
| WAIT_RELEASE_SETTLE | `WAIT_RELEASE_SETTLE` |
| VALIDATE_FINAL_PLACEMENT | `VALIDATE_FINAL_PLACEMENT` |
| SYNC_WORLD_OBJECT | `SYNC_WORLD_OBJECT` |
| RETREAT | `RETREAT` |
| FINAL_STABLE / DONE | `DONE` |

恢复节点（如 reclose/retry/重新 SEAT_CONTACT）属于**失败收敛**路径，用于把一次运行收敛为
可归类的证据，**不作为正常成功路径**的一部分；成功路径必须是无恢复干预的线性轨迹。

### 3.3 MICRO_LIFT 节点成功合同

`MICRO_LIFT`（及其稳定判定 `WAIT_MICRO_LIFT_STABLE`）节点的成功必须同时满足以下物理
合同，缺一不可：

1. **完整位姿达标**：杯子的完整位置与姿态（position + orientation）均进入预定的固定
   容差，不允许只用单一轴或单一自由度判成功。
2. **脱离支撑**：杯子已脱离桌面及一切非预期支撑（non-intended support）。
3. **窗口内持续稳定**：在固定的观测窗口内持续满足位姿、线速度和角速度阈值。
4. **物理来源**：杯子的运动必须由 Gazebo 接触物理产生。

明确禁止的替代判据：仅凭命令执行成功（action/controller 返回成功）、仅凭 TCP 运动达到
预期、或仅凭 world-Z delta 达标，均**不能**判定 MICRO_LIFT 成功。

### 3.4 节点通用声明

ActionGraph 中每个节点必须声明以下字段（缺任一字段即视为注册表缺陷，拒绝生成候选）：

- **前置条件**（preconditions）：进入该节点前必须为真的物理/场景断言。
- **目标状态**（goal）：该节点结束时应达成的可观测状态。
- **可搜索参数**（searchable parameters）：指向 ParameterRegistry 的 key 列表。
- **固定约束**（fixed constraints）：该节点不可违反的硬门（来自冻结层或验收语义）。
- **观测量**（observables）：该节点必须落盘的证据（contact、pose、q6、轨迹、shadow 等）。
- **成功判据**（success criteria）：判定节点通过的显式条件。
- **失败分类器**（failure classifier）：把失败映射到标准失败类别（见 6.4）的规则。
- **最小 stop_after**：能以最小物理执行复现该节点证据的 `--stop-after` 边界。
- **reset 规则**：该节点失败后回到可重试初态所需的 RESET_WORLD 子集。
- **可回溯祖先**（reopenable ancestors）：下游证据若指向上游余量不足时，允许带理由重开
  的祖先节点列表。

**冻结前缀语义**：冻结前缀只冻结参数值，不跳过物理执行；每个实验仍从初态（READY）完整
执行物理前缀到达被测节点。下游证据若指向上游余量不足（例如 CARRY 失稳归因于 grasp 咬合
过浅），规划器可携带该理由重开祖先节点的子树，而不是在下游补偿。

## 4. 参数树（Parameter Tree）

不限于历史已试的 Z/q6/orientation；完整参数树按 owning action node 分组。除 penetration
有明确批准范围外，其余每个参数的范围必须来自**现有已批准安全配置的审计登记**
（audit-registered bounds），规划器不得自行扩边。

### 4.1 PRE_GRASP / APPROACH（对应 MOVE_ABOVE_OBJECT）

- TCP x/y/z 偏移；roll/pitch/yaw 姿态偏移
- standoff（接近悬停距离）
- approach vector dx/dy/dz（接近方向）
- duration（段时长）；velocity/acceleration scaling（速度/加速度缩放）

### 4.2 GRASP_ACQUISITION（对应 DESCEND/CLOSE_GRIPPER/WAIT_GRASP_STABLE）

- grasp TCP x/y/z 偏移；roll/pitch/yaw 姿态偏移
- penetration_target（目标咬合深度，范围 `[0.0001, 0.001] m`，硬上限 `0.001 m`）
- q6 pre-open（预张开角）
- close/contact target（闭合/接触目标 q6）
- seating preload（落座预压量，沿用已批准 `[0.0, 0.006] rad` 登记范围）
- close duration / dwell（闭合时长/接触保持时间）

### 4.3 MICRO_LIFT

- lift vector dx/dy/dz（抬升方向向量）
- distance/height（抬升距离/高度）
- orientation delta（姿态增量）
- duration；velocity/acceleration scaling
- 执行后的 settle wait（稳定等待，可搜索；验收容差/窗口/速度阈值固定）

### 4.4 CARRY（对应 LIFT/MOVE_ABOVE_PLACE）

- waypoint count（仅允许安全枚举内的离散值）
- 各 waypoint 的 position/orientation
- segment duration；velocity/acceleration scaling

### 4.5 PLACE / RELEASE（对应 DESCEND_TO_PLACE/OPEN_GRIPPER）

- place approach pose（放置接近位姿）
- descend vector/distance（下放方向/距离）
- release pose（释放位姿）
- q6 release/open target（释放/张开目标）
- open duration / release dwell（张开时长/释放保持）

### 4.6 RETREAT

- vector/distance（撤离方向/距离）
- orientation delta
- duration；velocity/acceleration scaling

### 4.7 注册表中的 frozen/validation 字段（非搜索变量）

- 环境初态（杯/机器人 spawn 位姿、场景组成）
- 验收容差/稳定观测窗口/速度阈值
- Planning Scene attach lifecycle（ATTACH_MOVEIT/DETACH_MOVEIT 的位置与语义）

## 5. ParameterRegistry

每个参数一项登记，字段：

| 字段 | 含义 |
|---|---|
| key/path | 配置内的唯一路径（如 `motion.grasp_tcp_translation_offset_m[2]`） |
| type | scalar/vector/discrete |
| unit | 物理单位（m/rad/s/无量纲） |
| frame | 参考系（world/TCP-local/joint 等） |
| default/anchor | 默认值/当前锚点值 |
| allowed interval/discrete values | 允许区间或离散集合（来自审计登记，不得自扩） |
| step generator | 确定性步进生成器（如二分/等差/中点规则） |
| owning action node | 所属 ActionGraph 节点 |
| dependencies/mutual exclusions | 依赖与互斥（如单轴平移互斥） |
| hard constraints | 硬约束（如 penetration 全局上限） |
| requires plan-only | 是否要求 plan-only 预检通过才可 execute |
| eligible interactions | 允许参与的有限交互项 |
| searchable/frozen | 可搜索或冻结 |
| provenance | 该登记的来源（批准文档/commit/实验证据） |

## 6. 自适应分批搜索（adaptive batched search）

### 6.1 开子树规则

按**完整路径上首个失败节点**打开该节点的局部参数子树；不做全量笛卡尔积。首个失败节点
未推进前，不为下游节点生成候选（允许 plan-only 预演，但不消耗物理执行额度）。

### 6.2 wave 组成

每个 wave（批次）的候选按默认策略混合：

- 约 50%：当前最优邻域开发（exploitation）
- 约 30%：未覆盖安全空间探索（exploration）
- 约 20%：有因果依据的有限交互（interaction）

该比例为**可配置默认策略**，不改变任何硬门。

### 6.3 交互示例（eligible interactions）

- grasp Z × penetration
- yaw × q6 preload
- approach vector × pre-open
- lift direction × speed
- release height × open duration

### 6.4 失败映射（failure classifier -> 参数子树）

| 失败类别 | 打开的参数子树 |
|---|---|
| PLAN / IK / COLLISION | approach/pose/waypoint |
| miss contact（未接触） | grasp pose/preopen/penetration |
| contact no lift（接触但带不起） | penetration/close/preload/dwell |
| slip（滑脱） | orientation/preload/lift vector/speed |
| target miss（落点偏离） | lift/carry/place vector/pose |
| unstable（不稳定） | execution speed/duration/settle wait |

### 6.5 候选准入管线

每个候选必须依次通过以下闸门才可 execute：

1. **范围/依赖检查**（ConstraintEngine）：区间、互斥、硬约束。
2. **plan-only 预检**：IK/路径/碰撞全部通过（对 `requires plan-only` 的参数强制）。
3. **历史去重**：与台账中已有候选指纹比对，重复候选直接拒绝（禁止结果购物）。
4. **不可变固化**：候选配置写为不可变 YAML 并记录 SHA；执行必须使用与该 SHA 一致的
   installed 产物。

## 7. 候选状态与评分

### 7.1 候选生命周期状态

- `INVALID_CANDIDATE`：候选自身违规（范围/依赖/plan-only/去重未过）。
- `INVALID_ENVIRONMENT`：环境不满足 RESET_WORLD 合同或资源守卫，证据不可用于学习。
- `VALID_FAILURE`：干净环境下的真实物理失败，计入失败映射。
- `PROVISIONAL_FEASIBLE`：单次通过全部硬门。
- `PROMOTED_ANCHOR`：跨 lane 复验后晋升的锚点（仍不是最终验收）。

硬门失败的候选**不可参与最佳排序**。

### 7.2 可行候选排序指标

- 位置/姿态容差余量
- 离开非预期支撑（non-intended support clearance）
- 稳定窗口最差余量
- 线/角速度峰值
- 安全边界余量（各参数到区间边界的距离）
- RESET_WORLD 鲁棒性（复验一致性）

### 7.3 晋升规则

单次成功仅为 `PROVISIONAL_FEASIBLE`；至少**两次跨 lane 的 RESET_WORLD 复验**通过后才晋升
`PROMOTED_ANCHOR`。晋升锚点仍不等于最终验收（最终验收见第 10 节）。

## 8. 并发模型（Planner/Supervisor lanes）

- 最多 **3 条 lane**；资源探测按 1 -> 2 -> 3 递增，资源占用或实时率（real-time factor）
  恶化时自动降级回更少 lane。
- 每 lane 独占：`ROS_DOMAIN_ID`（必须合法，<= 232）、`GZ_PARTITION`、tmux session、
  `ROS_LOG_DIR`、证据目录、`simulation_session_id`、checkpoint 存储、进程所有权
  manifest（owned-PID 清单）、候选配置副本。
- 每 wave 启动干净 stack；同 lane 内候选之间执行 RESET_WORLD。
- **禁止**并发写入源码/install/shared policy；候选配置以不可变 YAML 下发，运行时使用
  lane 私有副本。
- **ledger 单写者**：只有 Supervisor 写人类可读台账；worker 只输出结构化结果（JSONL）。

## 9. RESET_WORLD 合同

两次候选执行之间（同 lane）或任何失败后重试前，必须满足：

1. 取消进行中的 action；
2. 确认 Gazebo 无任何非预期 attachment；
3. 解除 MoveIt shadow 并恢复 world object；
4. 机器人回 home；
5. 杯子回 spawn 位姿；
6. controller 全部 active；
7. joint/杯位姿/接触读数稳定；
8. 分配新的 simulation_session_id / checkpoint / 证据目录；
9. 无残留接触状态或 attached 状态。

任一条不满足 => `INVALID_ENVIRONMENT`，该次运行不用于学习，并触发环境守卫处置。

## 10. 晋级与最终验收

1. 用自适应搜索推进当前首个失败节点，逐节点推进完整 pick-place。
2. 全链路打通后，**冻结完整 commit + policy fingerprint**。
3. 干净环境下串行 **FULL_RESTART × 5**（每次全新 stack）。
4. 同一冻结版本串行 **RESET_WORLD × 5**（同 stack 复位复跑）。
5. 最终成功判据：杯子在指定范围内、姿态正确（直立）、稳定；夹爪已释放并撤离；
   Gazebo 物理状态与 MoveIt scene membership 各自独立一致。
6. **post-retreat 最终判定**：最终杯子位姿与稳定性必须在 `RETREAT` 完成后**重新采样**
   并判定（FINAL_STABLE），以捕获撤离阶段对杯子/场景的扰动；
   `WAIT_RELEASE_SETTLE` / `VALIDATE_FINAL_PLACEMENT` 在撤离前取得的成功**不能替代**
   post-retreat final outcome。
7. 生命周期规则：`INVALID_*` 不计数但结束当批；`VALID_FAILURE` 终止当前 streak；
   不同生命周期状态的运行不可混算。

## 11. 架构组件

纯 Python CLI，YAGNI：不引入数据库/Web/外部服务。

| 组件 | 职责 |
|---|---|
| ActionGraph | 节点声明、依赖、可回溯祖先、最小 stop_after |
| ParameterRegistry | 参数登记、范围 provenance、step generator |
| CandidateGenerator | 按 wave 策略生成候选（exploit/explore/interaction） |
| ConstraintEngine | 范围/依赖/硬约束/plan-only 准入/去重 |
| ExperimentSupervisor | lane 管理、资源探测降级、进程所有权 manifest、ledger 单写者 |
| StageEvaluator | 节点成功判据、失败分类器、评分排序 |
| ExperimentLedger | 候选 YAML / 结果 JSONL / 人类可读台账（append-only） |

确定性要求：相同 seed + 相同历史 + 相同 registry 必须生成相同批次。

## 12. 数据流、恢复与幂等

- **数据流**：registry/历史 -> CandidateGenerator -> ConstraintEngine -> 候选 YAML(+SHA)
  -> lane 执行 -> 结果 JSONL -> StageEvaluator -> ledger（Supervisor 单写）。
- **恢复/幂等**：每个候选执行由 `simulation_session_id` + 候选 SHA 唯一标识；重复提交同一
  标识直接返回既有结果，不重复执行。中断后从 checkpoint 恢复 lane 状态；已完成候选不
  重跑。
- **证据 provenance**：每批保留 source commit、精确 dirty status、installed prefix/hash、
  实验 ID/生命周期、domain/partition/tmux/PID、命令与 exit code、plan/执行/接触/位姿/
  attachment/scene membership 证据、清理读回。
- **资源守卫**：CPU/内存/实时率超阈值时 lane 自动降级；`ROS_DOMAIN_ID` 必须 <= 232
  （历史 INVALID：EXP-QUAL2-PLAN-234、EXP-QUAL2-GRASP-1-233）。
- **磁盘水位**：证据目录设水位线；超线时停止开新 wave 并告警，不删除在役证据。
- **lane/wave 全局 invalid 条件**：shared 状态被并发写入、进程所有权 manifest 失配、
  preserved 进程被误伤、domain/partition 冲突——任一发生则整个 wave 记 `INVALID_ENVIRONMENT`
  并停止该批。
- **可观察性**：每 lane 的结构化心跳、候选状态迁移、gate 结果与评分全部入 JSONL；台账
  提供人类可读摘要。

## 13. 异常分类与测试设计

### 13.1 三类异常

1. **候选异常**（`INVALID_CANDIDATE`）：配置违规、plan-only 失败、重复指纹。
2. **环境异常**（`INVALID_ENVIRONMENT`）：RESET_WORLD 合同不满足、资源/所有权守卫触发。
3. **物理失败**（`VALID_FAILURE`）：干净环境下的真实物理失败，进入失败映射。

### 13.2 测试设计（实现阶段的必备测试层）

- unit/contract：registry 校验、候选生成确定性、约束判定、状态机迁移。
- 防作弊测试：硬门失败候选不得进入排序；`INVALID_*` 不得计入 streak；plan-only 未过
  不得 execute。
- RESET_WORLD 合同测试：逐条断言九项条件。
- 并发隔离测试：lane 资源独占、无共享写入、ledger 单写者。
- Planning Scene shadow 测试：attach/detach 只做影子、生命周期固定、不驱动物理。
- 真实失败回放 -> 候选生成测试：用台账中的历史 VALID_FAILURE 验证失败映射产出预期
  子树候选。
- 最终 acceptance 测试：FULL_RESTART×5 与 RESET_WORLD×5 的计数/生命周期语义。

### 13.3 第一版非目标

- 自动修改源码/自动编译
- 搜索冻结的物理/控制/碰撞参数
- 无界 Bayesian 优化或任何无界全局搜索
- 多机分布式、UI/Web
- 用随机单次成功代替验收（任何 streak 语义不可由单次运行替代）

## 14. 完成条件与开放风险

### 14.1 本规划器的完成条件

完整 pick-place 在冻结 commit+policy 下通过第 10 节的最终验收（FULL_RESTART×5 与
RESET_WORLD×5 均成功、最终状态判据全部满足、台账证据完整）。

### 14.2 开放风险（均已识别，无未决占位）

- **接触几何方差**：当前锚点的咬合骑在接触/不接触边界（标称干涉 0.00004 m，
  见 `CP-QUALIFICATION-ENDED-002`）；penetration_target 等新搜索维度能否覆盖该方差需由
  搜索实证回答。
- **范围登记缺口**：除已批准范围（penetration `[0.0001, 0.001] m`、preload
  `[0.0, 0.006] rad`、orientation 轴容差 `0.08726646259971647 rad`、既有平移 clearance
  `0.001 m`）外，其余参数的允许范围需在实现阶段从现有已批准安全配置做审计登记；
  登记完成前对应参数按 frozen 处理。
- **solver 上报上限**：接触深度超过 0.0013 m 后不可上报，penetration 观测量在该区间外
  失真；验收语义不得依赖超出可上报区间的深度读数。
- **历史结果隔离**：0.0013 m solver-limit fingerprint 下的全部历史结果仅作证据，不参与
  新搜索的排序、晋升或验收计数。
- **资源竞争**：ai-station 上存在与本任务无关的长驻进程（见台账 preserved 清单）；
  lane 资源探测必须把它们视为不可回收背景负载。
