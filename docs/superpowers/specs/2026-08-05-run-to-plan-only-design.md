# Run-to-Plan-Only 与 Pick/Place 启动参数手册设计

日期：2026-08-05
状态：书面 spec 已批准，进入实施计划阶段
适用范围：`pick_place_common`、`panda_gazebo_demo`、`so101_gazebo_demo`

## 1. 背景

当前 common runner 的非 resume `plan_only` 会默认选择第一个注册了 planner 的状态，并直接从当前观测进行该状态的前置验证与规划。SO-101 的第一个可规划状态是 `MOVE_ABOVE_OBJECT`，但其前置状态 `PREPARE_OPEN_GRIPPER` 尚未执行，因此 fresh simulation 的 q6 仍为 `0`，而运动策略要求 q6 为 preopen `0.465038`，最终在任何规划发生前返回 `Q6_TARGET_OUT_OF_TOLERANCE`。

该问题不应通过修改 Gazebo 初始 q6、绕过 q6 验证或伪造 world observation 解决。`plan_only` 应明确表达“执行到目标状态入口，然后只规划该目标状态，不执行该目标状态”。

## 2. 目标

1. `plan_only` 必须显式指定一个允许规划的目标状态。
2. runner 必须沿正常成功路径真实执行并验证所有前置状态。
3. 到达目标状态后，只执行 precondition、plan 和 plan validation，不执行目标状态。
4. Panda 与 SO-101 共用同一套 runner 语义，并分别通过 workflow 数据声明白名单。
5. checkpoint、resume、recovery 和 failure provenance 必须保持 fail-closed。
6. 新建统一的 Panda/SO-101 pick/place 启动参数手册，集中描述参数、组合规则、副作用和标准命令。

## 3. 非目标

- 不修改 Gazebo/ros2_control 的初始关节位置。
- 不删除或放宽 SO-101 q6、夹爪、Gazebo、MoveIt Scene 或 attachment 契约。
- 不把真实 q6 替换成策略中的虚拟 q6。
- 不允许 recovery 状态成为 plan-only 目标。
- 不改变 checkpoint schema v3 的磁盘字段。
- 不增加真实机械臂验收；运行时验收限定为 ai-station 仿真。
- 不重构与本问题无关的运动规划、抓取或恢复实现。

## 4. 精确定义

### 4.1 Plan-only 的含义

`plan_only` 仅保证目标状态本身不被 execute。目标之前的状态会真实执行，并可能产生以下副作用：

- 机械臂和夹爪运动；
- Gazebo attach/detach；
- MoveIt Planning Scene attach/detach/sync；
- checkpoint 写入；
- 失败后的 recovery。

因此该模式的完整语义是 run-to-plan-only，而不是全流程无动作。启动参数手册必须将这一点放在 plan-only 章节开头和命令示例之前。

### 4.2 成功流程

```text
initial or resumed state
  -> execute and validate every predecessor on the forward-success path
  -> arrive at plan_only_state entry
  -> observe
  -> validate target precondition
  -> plan target
  -> validate target plan
  -> do not execute target
  -> PLAN_ONLY_COMPLETE
```

例如：

```text
run_mode=plan_only, plan_only_state=MOVE_ABOVE_OBJECT

IDLE
  -> execute PREPARE_OPEN_GRIPPER
  -> validate q6=preopen
  -> plan MOVE_ABOVE_OBJECT
  -> validate the plan
  -> stop without executing MOVE_ABOVE_OBJECT
```

## 5. Plan-only 状态白名单

Panda 与 SO-101 第一版使用相同的显式白名单：

1. `MOVE_ABOVE_OBJECT`
2. `DESCEND`
3. `LIFT`
4. `MOVE_ABOVE_PLACE`
5. `DESCEND_TO_PLACE`
6. `RETREAT`

所有 `RECOVER_*` 状态、gripper 状态、attachment 状态、验证状态和终态均不允许作为 plan-only 目标。

恢复状态虽然可能注册 planner，但它们不能通过正常 forward-success path 到达，且依赖失败上下文，因此不能仅根据“是否注册 planner”推导白名单。

## 6. Common 类型与 workflow 声明

### 6.1 `RunRequest`

新增：

```cpp
std::optional<State> plan_only_state;
```

`stop_after` 保持原有 dry-run/execute 停止边界含义，不再承担 plan-only 目标含义。

### 6.2 `WorkflowDefinition`

新增：

```cpp
std::set<State> plan_only_states;
```

Panda 与 SO-101 workflow 必须显式填充第 5 节白名单。`validateWorkflowDefinition()` 必须验证：

- 每个白名单状态同时属于 `forward_states` 和 `action_states`；
- 每个白名单状态可从 initial state 沿成功边到达；
- 白名单状态不是 terminal；
- workflow 中不存在导致目标前向路径不唯一的结构。

运行时 registry 校验还必须确认目标状态具有 planner、plan validator 和成功 transition contract，目标之前的所有 action state 具有 executor 和 transition contract。

## 7. Runner 架构

采用已批准的方案 A：在 common runner 的单一执行循环中加入目标边界切换，不通过两个 runner 调用拼接流程，也不在 Panda/SO-101 wrapper 中复制逻辑。

### 7.1 Fresh run

1. `run()` 在任何 observe、plan、execute 或 checkpoint 写入前验证请求。
2. plan-only 复用 execute 所需的 observer、checkpoint store、resume validator、recovery policy、executor、contract、planner 和 plan validator 完整性检查。
3. runner 从 workflow 初始成功后继状态开始正常执行。
4. 每次循环开始时，如果 `state == plan_only_state`，调用目标规划分支，而不是 `runExecuteStep()`。
5. 目标规划分支执行严格 precondition、plan 和 plan validation。
6. 成功时返回 `PLAN_ONLY_COMPLETE`，不调用目标 executor，不执行 transition postcondition，不写目标完成 checkpoint。

### 7.2 RunResult

成功结果约定：

- `status = PLAN_ONLY_COMPLETE`；
- `current_state = plan_only_state`；
- `next_state = resolve(plan_only_state, SUCCEEDED)`，仅表示该 plan 对应的预期成功后继，不表示 transition 已发生；
- `state_trace` 包含已真实到达的目标入口，但不包含目标成功后继；
- `transition_count` 只统计真实发生的 state transition，目标规划不增加 transition count。

文档与测试不得将 `next_state` 或 trace 中出现目标状态解释为目标已执行。

## 8. 参数契约

标准 launch 调用：

```bash
run_mode:=plan_only plan_only_state:=MOVE_ABOVE_OBJECT
```

SO-101 直接 CLI 同时提供：

```bash
--mode plan_only --plan-only-state MOVE_ABOVE_OBJECT
```

参数组合规则：

| 条件 | 结果 |
| --- | --- |
| `run_mode=plan_only` 且未提供 `plan_only_state` | 启动前失败 |
| `plan_only_state` 不在白名单 | 启动前失败 |
| 非 plan-only 模式提供 `plan_only_state` | 启动前失败 |
| plan-only 同时提供 `stop_after` | 启动前失败 |
| plan-only 同时提供 `single_step` / `--step` | 启动前失败 |
| `force_continue` 不是 execute resume | 保持现有失败语义 |
| plan-only fresh run | 允许 |
| plan-only forward resume | 按第 10 节处理 |

所有请求错误必须在产生任何副作用前返回。

## 9. Checkpoint 语义

plan-only 的前置状态是真实 execute，因此继续在每个成功边界写 checkpoint：

```text
source_mode=execute
last_completed_state=<真实完成的前置状态>
next_state=<下一状态>
```

目标状态仅规划，不写“目标已完成”checkpoint。成功返回时，磁盘上最新 checkpoint 应仍准确描述目标入口，例如：

```text
last_completed_state=PREPARE_OPEN_GRIPPER
next_state=MOVE_ABOVE_OBJECT
```

checkpoint schema version 和 Panda/SO-101 既有配置指纹磁盘键保持不变。

由于 fresh plan-only 会真实执行并写 checkpoint，其 simulation session ID 生命周期与 execute 相同：新运行省略 ID 时沿用现有自动生成规则；resume 必须提供并匹配 checkpoint/session 证据。

## 10. Resume 语义

`plan_only + resume` 必须同时指定 `plan_only_state`，并且：

- 只接受 `source_mode=execute`、`phase=FORWARD` 的兼容 checkpoint；
- checkpoint `next_state` 可以等于目标状态，也可以位于目标上游；
- resume validation 必须先证明当前 Gazebo、MoveIt、joint、attachment 和 session 状态与 checkpoint 一致；
- 验证成功后继续执行剩余前置状态，再规划目标；
- checkpoint 已经越过目标时，在动作前失败；
- recovery checkpoint 在动作前失败；
- 不允许通过 `force_continue` 绕过这些规则。

## 11. Failure 与 Recovery

### 11.1 前置状态失败

完全复用现有 execute failure handling、cancel、停止观测、recovery route、checkpoint 和 original failure 关联逻辑。

### 11.2 目标状态失败

目标 precondition、planning 或 plan validation 失败时：

1. 不执行目标状态；
2. 调用与 execute 模式同等的安全停止/恢复入口；
3. 从目标状态选择现有 recovery route；
4. 保留原始失败分类和 code；
5. 返回 recovery 结果，并在 recovery 失败时附加原始失败 provenance。

这条规则特别覆盖 `LIFT` 等目标：其前置链可能已夹持并 attach 物体，规划失败后不能直接遗留未收敛副作用。

### 11.3 目标规划成功

成功时不自动 recovery。系统停留在目标状态入口，以便检查、后续 execute resume 或显式 reset。启动参数手册必须提示深层目标可能留下已夹持或已 attach 的现场。

## 12. 新错误码

至少新增并稳定测试以下错误码：

- `PLAN_ONLY_STATE_REQUIRED`
- `PLAN_ONLY_STATE_NOT_ALLOWED`
- `PLAN_ONLY_STATE_UNREACHABLE`
- `PLAN_ONLY_ARGUMENT_CONFLICT`
- `PLAN_ONLY_TARGET_ALREADY_PASSED`
- `PLAN_ONLY_RECOVERY_RESUME_UNSUPPORTED`

对于请求/白名单/路径错误，必须断言：

```text
observer_calls=0
planner_calls=0
executor_calls=0
checkpoint_writes=0
```

## 13. Launch 与入口适配

SO-101：

- `so101_pick_place.launch.py` 新增 `plan_only_state`，默认空字符串；
- 参数传给 `pick_place_state_machine --plan-only-state`；
- `--show-args` description 明确白名单和“前置状态会执行”。

Panda：

- pick/place launch 新增 `plan_only_state` ROS 参数；
- node 使用仅允许白名单的 state parser；
- 参数冲突在 runner 调用前拒绝。

两个入口必须把相同的 common 语义暴露给用户，不允许一个仍把 `stop_after` 当 plan-only 目标。

## 14. 统一启动参数手册

新建：

```text
docs/pick-place-launch-parameters.md
```

该文档是 Panda 与 SO-101 pick/place 启动参数的统一用户手册，至少包含：

1. `dry_run`、run-to-`plan_only`、`execute` 的副作用对照表；
2. common 参数名、类型、默认值、允许模式和冲突关系；
3. Panda 专用参数表；
4. SO-101 专用参数表；
5. plan-only 六状态白名单和各目标会执行的前置阶段；
6. `stop_after`、`plan_only_state`、`resume`、checkpoint 和 session ID 的关系；
7. fresh simulation、连接已有 stack、forward resume 的可复制命令；
8. 深层 plan-only 成功后如何继续 execute resume 或 reset；
9. 常见错误码、首个检查点和处理建议；
10. 真实运动、Gazebo 物理副作用和 Planning Scene 副作用的醒目警告。

以下位置必须链接到统一手册：

- 仓库根 README；
- Panda package README；
- SO-101 package README；
- 两个 pick/place launch 参数 description。

README 只保留简短入口和常用命令，不复制完整参数表，避免文档漂移。

## 15. 自动化验收

### 15.1 Common runner

- 六个白名单目标分别证明正确执行所有前置状态。
- 目标 planner 和 plan validator 各调用一次，目标 executor 调用零次。
- trace 和 transition count 只反映真实到达边界。
- 目标成功后 checkpoint 仍指向目标入口。
- 缺目标、非法目标、参数冲突和不可达目标均为零副作用失败。
- 目标 precondition、plan、plan validation 三类失败均触发 recovery。
- recovery failure 保留 original failure。
- fresh plan-only 要求 execute 级基础设施完整。

### 15.2 Resume

- checkpoint `next_state == target` 时直接验证并规划。
- checkpoint 在目标上游时执行剩余前置状态后规划。
- checkpoint 已越过目标时零副作用失败。
- recovery checkpoint 零副作用失败。
- session/config/world mismatch 保持现有 fail-closed 行为。

### 15.3 Panda 与 SO-101

- 两个 workflow 的白名单完全等于第 5 节。
- 两个 CLI/launch 入口执行同一参数组合规则。
- 现有 dry-run、execute、stop-after、execute resume 和 recovery 测试无回归。
- 全部 package tests、lint 和 `git diff --check` 通过。

## 16. ai-station 运行时验收

1. 保存当前失败基线：旧实现 fresh SO-101 plan-only 在首状态前报 `Q6_TARGET_OUT_OF_TOLERANCE`。
2. 重新 build、source，并确认三个 package prefix 和 executable 都来自目标 worktree install。
3. Fresh SO-101 `plan_only_state=MOVE_ABOVE_OBJECT`：
   - `PREPARE_OPEN_GRIPPER` 确实执行；
   - q6 收敛到 preopen；
   - `MOVE_ABOVE_OBJECT` plan 和 validation 成功；
   - arm/TCP 不执行该目标轨迹。
4. SO-101 深层目标至少验证 `LIFT`：夹爪、physical grasp、Gazebo attachment 和 MoveIt attachment 前置链真实成立，LIFT 只规划不执行。
5. Panda 至少验证 `MOVE_ABOVE_OBJECT` 和一个深层目标。
6. 为目标 planning failure 做一次定向故障注入，证明 recovery 收敛且目标没有执行。
7. 检查 Gazebo 与 Planning Scene attachment/object pose 一致。
8. 获取本轮新的 GUI 截图，确认目标入口姿态、夹爪和物体状态。
9. 清理本轮隔离 stack，并证明没有遗留重复 Gazebo、MoveIt 或 state-machine 进程。

## 17. 兼容性与迁移

这是有意的命令行兼容性变化：

- 旧的 `run_mode=plan_only` 无目标调用改为失败；
- 旧的 `run_mode=plan_only stop_after=<STATE>` 改为参数冲突；
- 调用者必须迁移为 `run_mode=plan_only plan_only_state=<WHITELIST_STATE>`；
- execute/dry-run 的 `stop_after` 行为保持不变；
- checkpoint v3 schema 不变；
- Panda 与 SO-101 必须在同一提交系列内完成迁移，不能暂时保留两套语义。

## 18. 完成条件

只有同时满足以下条件才可宣布完成：

- 书面 spec 和实施计划已审批；
- RED -> GREEN 自动化证据完整；
- Panda、SO-101 和 common package tests 无新增失败；
- fresh 与 resume 的 run-to-plan-only 运行时矩阵通过；
- 目标状态从未执行；
- 目标失败 recovery 通过；
- 统一启动参数手册完整且所有入口链接有效；
- ai-station provenance、Gazebo、MoveIt、controller/joint/TF、checkpoint 和新截图证据齐全；
- 没有覆盖用户既有改动，没有遗留后台进程，也没有推送或合并未经授权的分支。
