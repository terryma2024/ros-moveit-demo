# Refactor Optimization R1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 清除 Panda 与 SO-101 pick-place 重构后的死亡代码和影子实现，把仍然行为等价的几何、状态机、校验装配与 resume 比较逻辑迁入 `pick_place_common`，同时修复 Panda 边界 metrics 在公共 runner 中未实际生效的问题。

**Architecture:** `pick_place_common::core` 继续只拥有机器人无关的值类型、几何纯函数、workflow/contract/runner 与 checkpoint 比较原语；`pick_place_common::ros_adapters` 只承载经过证明完全等价的 ROS/Gazebo 消息转换。Panda 与 SO-101 保留各自的 workflow 图、motion/gripper/contact/recovery/scene 策略和错误码映射，通过显式 policy/decorator seam 组合公共能力，不依赖同名非虚函数隐藏。

**Tech Stack:** C++17, ROS 2 Jazzy, MoveIt 2, Gazebo Sim, ament/colcon, GTest, pytest/ament lint, Git worktree, zsh。

## Global Constraints

- [ ] 只在新 worktree `/data/work/ws_moveit/.worktrees/refactor-optimization-r1`、分支 `codex/refactor-optimization-r1` 中修改；基线必须是主工作区当前干净 `main` 的 `fe446e0005c6432ab57aa73b2c4ea41f5863040e`。若基线、主工作区 dirty state 或同名 worktree/branch 不符合，停止并报告，不 reset/stash/clean。
- [ ] 使用 `tmux codex`，不发送任何输入到 `codex-cua`，不修改其他 worktree，不宽泛终止 ROS/Gazebo 进程。
- [ ] 开始前完整阅读根 `AGENTS.md`、`moveit-demo/AGENTS.md` 和项目 `$so101-dev` skill；执行计划用 `superpowers:executing-plans`，建 worktree 用 `superpowers:using-git-worktrees`，每个行为改动遵循 RED -> GREEN。
- [ ] 创建证据目录 `/tmp/so101-debug-refactor-optimization-r1-<timestamp>/`，保存 baseline、每任务定向测试、最终 build/test/runtime、进程所有权和截图清单。
- [ ] 不改变 Panda `pandaWorkflowDefinition()` 或 SO-101 `so101WorkflowDefinition()` 的状态集合、成功/失败边；特别保留 SO-101 的 `WAIT_GRASP_STABLE`、`MICRO_LIFT`、`WAIT_MICRO_LIFT_STABLE`、`VERIFY_PHYSICAL_GRASP`、`VALIDATION_FAILED`。
- [ ] 不改变 checkpoint schema v3 的磁盘字段、默认值或错误码：Panda 继续序列化 `configuration_hash`，SO-101 继续序列化 `policy_bundle_sha256`；公共内存字段仍为 `configuration_fingerprint`。
- [ ] 不机械替换 `SO101ResumeValidationPolicy::orientationError`：它使用四元数 chord distance，不等于 `orientationDistance()` 的角距离。
- [ ] `pick_place_common::core` 不新增 `rclcpp`、`geometry_msgs`、Gazebo 或 MoveIt 依赖；只有确认为纯消息转换的代码才可进入现有 `pick_place_common::ros_adapters` target。
- [ ] 删除公开头文件/脚本前必须用 `rg`、CMake install/export、launch、README/docs 和测试证明仓库内无生产消费者；Git 可恢复不等于可跳过证据。
- [ ] 每个任务独立 commit，commit 前运行对应定向测试和 `git diff --check`；不 push、不 merge 回 `main`，完成后等待用户审阅。
- [ ] 不运行 `ament_uncrustify --reformat`；只允许只读 lint 和定向 patch。

## Acceptance Matrix

以下规则全部满足才允许宣告 R1 完成；测试数量本身不是通过依据。

| Gate | 必须通过的证据 |
|---|---|
| Provenance | worktree/branch/HEAD 与本计划一致；根 checkout 和其他 worktree 前后 status 对比无变化 |
| Dead code | 计划列出的 stale `.cpp`、旧 Panda planners、legacy Cartesian API、`AttachmentExpectation` 和孤立 cleanup script 已移除；`rg` 无消费者/残留；package-layout 测试能阻止未编译 source 回归 |
| Common ownership | 两个 robot package 不再各自实现行为等价的 pose finite/relative/compose/stability、transition resolve、functional contract 和 named-joint 比较；机器人策略仍留在 robot package |
| Semantic compatibility | Pose 非有限值、零/非单位 quaternion、`q/-q`、时间戳逆序；workflow 全边；metrics/failure 顺序；resume joint 缺失/多余/NaN/Inf/容差边界均有 RED/GREEN 测试 |
| Panda runner bug | 通过真实 `pick_place_common::StateMachineRunner` 调用证明 Panda boundary failure metrics 出现在 pre/post/resume 失败结果；禁止仅直接调用 Panda registry wrapper 的测试 |
| Checkpoint compatibility | 两包现有 schema-v3 fixture/read-write/negative resume 测试全部通过，JSON key 和错误码 snapshot 不变 |
| Build/test | 三包 clean-cache build 成功；`colcon test-result --verbose` 为 0 errors / 0 failures；格式、clang-tidy/ament lint 与 package-layout gate 通过 |
| Runtime | Panda execute/recovery/plan-only-resume 现有脚本通过；SO-101 dry-run、headless plan-only、一次 fresh simulator execute 通过，且使用本 worktree install overlay |
| Robot state | SO-101 execute 的 Gazebo attachment、MoveIt scene、controller/joints/TF 和最终 object pose 相互一致；失败/恢复只撤销已产生副作用 |
| Visual | 本轮 execute 后的新截图被实际查看，能描述 RViz/Gazebo 中机械臂、夹爪和物体终态；截图与同轮数值/日志证据对应 |
| Hygiene | worktree clean、提交按任务分组、无 build/install/log/capture 产物入库、未 push/merge、只停止本轮精确 PID/session/window |

---

## Task 1: Freeze the Baseline and Add Source-Manifest Guards

**Files:**

- Create: `src/panda_gazebo_demo/test/test_source_manifest.py`
- Create: `src/so101_gazebo_demo/test/test_source_manifest.py`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`
- Modify: `src/so101_gazebo_demo/CMakeLists.txt`

- [x] 创建 worktree，记录 `git rev-parse HEAD`、`git status --short --branch`、`git worktree list --porcelain`、相关 tmux/PID/ROS node；确认三个 package 当前来自预期源码。
- [x] 运行并保存 baseline：

```zsh
cd /data/work/ws_moveit/.worktrees/refactor-optimization-r1
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --symlink-install
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --event-handlers console_direct+
colcon test-result --verbose
```

- [x] 先写失败的 manifest tests：枚举各包 `src/pick_place/*.cpp`，要求每个 tracked implementation 要么出现在 `CMakeLists.txt` source manifest，要么出现在带原因的显式 allowlist；R1 完成后 allowlist 必须为空。
- [x] RED 必须捕获当前 6 个未编译 shadow sources：
  - Panda: `plan_validation.cpp`, `simulation_session_id.cpp`, `world_observer.cpp`
  - SO-101: `plan_validation.cpp`, `simulation_session_id.cpp`, `transition_contract.cpp`
- [x] 把测试注册进两个 package，确认 RED 原因准确，不允许通过忽略整个目录或模糊 basename 实现 GREEN。

**Acceptance:** 两个 manifest tests 在删除前因上述文件失败；错误消息逐个列出 source；无其他合法 source 被误报。

**Commit:** `test: guard Panda and SO-101 source manifests`

## Task 2: Remove Tracked Shadows and Panda Orphans

**Files:**

- Delete: `src/panda_gazebo_demo/src/pick_place/plan_validation.cpp`
- Delete: `src/panda_gazebo_demo/src/pick_place/simulation_session_id.cpp`
- Delete: `src/panda_gazebo_demo/src/pick_place/world_observer.cpp`
- Delete: `src/so101_gazebo_demo/src/pick_place/plan_validation.cpp`
- Delete: `src/so101_gazebo_demo/src/pick_place/simulation_session_id.cpp`
- Delete: `src/so101_gazebo_demo/src/pick_place/transition_contract.cpp`
- Delete: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/move_above_object_planner.hpp`
- Delete: `src/panda_gazebo_demo/src/pick_place/move_above_object_planner.cpp`
- Delete: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/descend_planner_executor.hpp`
- Delete: `src/panda_gazebo_demo/src/pick_place/descend_planner_executor.cpp`
- Delete: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/cartesian_plan_validation.hpp`
- Delete: `src/panda_gazebo_demo/src/pick_place/cartesian_plan_validation.cpp`
- Delete: `src/panda_gazebo_demo/scripts/cleanup_panda_demo.sh`
- Modify: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/state_validation.hpp`
- Modify: `src/panda_gazebo_demo/CMakeLists.txt`
- Modify/Delete: Panda tests that only assert these orphan types/APIs

- [x] 用 `rg -n` 和 CMake/install/docs 记录证明：生产 runtime 使用 `MotionStateAction`；`MoveAboveObjectPlanner` 没有构造者；`DescendPlannerExecutor` 只有类型继承测试；旧 `validateCartesianPlan()` 只有测试消费者；`cleanup_panda_demo.sh` 未安装、未 launch、未文档引用。
- [x] 删除 6 个 shadow sources，运行 manifest tests 到 GREEN。
- [x] 删除两个 old planner 类及其 type-only test/CMake source entry；不得删除当前 `MotionStateAction` 或现代 motion plan tests。
- [x] 将旧 Cartesian API 中仍有价值的边界用例迁到 `MotionPlanEvidence`/`validateMotionPlan()`，用 characterization/mutation coverage 证明现代 API 后再删旧 API 和 CMake entry。当前源码已在现代 validator 中实现这些行为，因此测试在删除前即通过；未伪造生产 RED。
- [x] 删除未使用的 `AttachmentExpectation`。
- [x] 删除孤立且以宽泛进程清理为目的的 `cleanup_panda_demo.sh`；最终说明它为何不再是受支持 operator surface。
- [x] 运行两个 package manifest tests、Panda motion validation tests、Panda package build/test、`git diff --check`。

**Acceptance:** `rg` 对所有删除符号/文件名无生产残留；Panda runtime 构造路径不变；现代 motion validation 覆盖旧 API 的 finite/fraction/trajectory/limits 边界；两个 manifest allowlist 为空。

**Commit:** `refactor: remove stale Panda and SO-101 implementations`

## Task 3: Introduce Common Pose Geometry and Stability Primitives

**Files:**

- Create: `src/pick_place_common/include/pick_place_common/pose_geometry.hpp`
- Create: `src/pick_place_common/src/pose_geometry.cpp`
- Create: `src/pick_place_common/include/pick_place_common/pose_stability_tracker.hpp`
- Create: `src/pick_place_common/src/pose_stability_tracker.cpp`
- Create: `src/pick_place_common/test/test_pose_geometry.cpp`
- Create: `src/pick_place_common/test/test_pose_stability_tracker.cpp`
- Modify: `src/pick_place_common/include/pick_place_common/world_observer.hpp`
- Modify: `src/pick_place_common/src/world_observer.cpp`
- Modify: `src/pick_place_common/CMakeLists.txt`

- [x] 写 RED tests 并定义以下公共 API：

```cpp
[[nodiscard]] bool isFinitePose(const Pose3d &) noexcept;
[[nodiscard]] bool hasUsableQuaternion(const Pose3d &, double minimum_squared_norm = 1e-24) noexcept;
[[nodiscard]] double positionDistance(const Pose3d &, const Pose3d &) noexcept;
[[nodiscard]] double orientationDistance(const Pose3d &, const Pose3d &) noexcept;
[[nodiscard]] std::optional<Pose3d> relativePose(const Pose3d & frame,
                                                 const Pose3d & object) noexcept;
[[nodiscard]] std::optional<Pose3d> composePose(const Pose3d & frame,
                                                const Pose3d & relative) noexcept;

class PoseStabilityTracker {
 public:
  PoseStabilityTracker(std::size_t required_samples, double position_tolerance,
                       double orientation_tolerance_rad);
  void addSample(const Pose3d &, std::chrono::steady_clock::time_point);
  [[nodiscard]] std::optional<bool> stationary() const noexcept;
};
```

- [x] Tests 必须覆盖：任一 position/quaternion 分量 NaN/Inf；零/近零 quaternion；非单位 quaternion 归一化；`q` 与 `-q` 的同姿态；relative/compose round-trip；无效 quaternion 返回 `nullopt`；样本不足；时间戳相等/逆序；位置/角度恰好等于和刚超过 tolerance。
- [x] 把现有 `positionDistance`/`orientationDistance` 实现迁到新 component，并让 `world_observer.hpp` 通过 include 保持已有 source compatibility，不复制第二份实现。
- [x] 公共实现只能用标准库数学，不引入 ROS/MoveIt/Gazebo/Eigen 依赖。

**Acceptance:** `pick_place_common` 定向 tests 全绿；`nm`/source inspection 只存在一份公共几何实现；invalid quaternion 行为显式且不产生 NaN 泄漏。

**Commit:** `refactor: add common pose geometry and stability primitives`

## Task 4: Migrate Panda and SO-101 Pose Logic Without Flattening Policies

**Files:**

- Modify: `src/panda_gazebo_demo/src/pick_place/state_validation.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/pick_place_contracts.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/recovery_contracts.cpp`
- Modify: `src/panda_gazebo_demo/src/nodes/pick_place_state_machine_node.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/gazebo_world_observer.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/pick_place_runtime.cpp`
- Modify: SO-101 files containing behavior-equivalent `finitePose`/distance helpers
- Create/Modify: SO-101 local support-pose utility and its tests

- [x] 在迁移前，为 Panda `CokePoseStabilityTracker` 和 SO-101 `TaskObjectPoseStabilityTracker` 现有行为补 characterization tests，证明两者与公共 tracker 在有效、抖动和逆序时间戳输入上相同。
- [x] Panda 用公共 `PoseStabilityTracker`、`relativePose()`；删除三个本地 relative-pose 实现。
- [x] SO-101 将行为等价的 `finitePose`/position/orientation/relative/compose 实现迁到公共 API，至少覆盖当前 active callers：attachment contracts、gripper state、recovery policy、joint motion adapter、runtime、Gazebo observer、world reset、scene initializer、physical grasp validator 和 scene node。
- [x] 对每个未迁移的 SO-101 本地 helper 写一行 code comment 说明语义差异和 owner；`SO101ResumeValidationPolicy::orientationError` 必须保留并有 chord-distance regression test。
- [x] 将 `supportedAtPick`/`supportedAtPlace` 收敛为一个 SO-101-owned utility，供 `so101_joint_motion_adapter.cpp`、`pick_place_runtime.cpp` 和 `so101_gripper_state.cpp` 共用；不得放进 common。
- [x] 只有在类型、frame 与异常语义完全相同时，才把重复 ROS/Gazebo message conversion 放进 `pick_place_common::ros_adapters`；否则保留 robot-local 并在本计划结果中说明差异。禁止给 common core 加消息依赖。（ROS/Gazebo conversions 保留 robot-local：消息类型与 frame/error 语义不同。）
- [x] 运行 common geometry/stability、Panda state/contract、SO-101 motion/runtime/attachment/recovery/observer tests。

**Acceptance:** `rg` 不再发现行为等价的本地 `finitePose`, `relativePose`, `TaskObjectPoseStabilityTracker`, `CokePoseStabilityTracker` 实现；保留的特殊距离/tilt/support 逻辑均有机器人语义测试；两个 workflow 行为结果不变。

**Commit:** `refactor: migrate robot pose helpers to common primitives`

## Task 5: Consolidate Transition Resolution and Compatibility Views

**Files:**

- Modify: `src/pick_place_common/include/pick_place_common/workflow_definition.hpp`
- Modify: `src/pick_place_common/src/workflow_definition.cpp`
- Modify: `src/pick_place_common/test/test_workflow_definition.cpp`
- Modify: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/transition_table.hpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/transition_table.cpp`
- Modify: Panda transition-table tests/callers
- Modify: `src/so101_gazebo_demo/include/so101_gazebo_demo/pick_place/transition_table.hpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/transition_table.cpp`
- Modify: SO-101 transition-table tests/callers

- [x] 为公共 API 写 RED tests：

```cpp
[[nodiscard]] State resolveTransition(const WorkflowDefinition &, State,
                                      ActionStatus) noexcept;
```

- [x] 覆盖 Panda 与 SO-101 每个 workflow state 的 `SUCCEEDED`/`FAILED` 结果、terminal 自环、未知 state 的当前兼容行为。
- [x] 两包 `TransitionTable::resolve()` 若仍是公开兼容入口，只能委托 `resolveTransition(<robotWorkflowDefinition>(), ...)`；`entries()` 只能返回 workflow definition 的 transitions view。
- [x] 删除两包重复 `StateMachine` 实现；现有消费者改用 `pick_place_common::StateMachine`。若公开 alias 必须保留，使用 `using StateMachine = pick_place_common::StateMachine` 或薄构造 wrapper，不保留 advance logic。

**Acceptance:** 全边 truth-table tests 逐项相等；`rg` 只找到 common 的 `StateMachine::advance` 实现；SO-101 特有状态未丢失。

**Commit:** `refactor: centralize transition resolution in common workflow`

## Task 6: Make Panda Boundary Metrics Effective Through the Common Runner

**Files:**

- Modify: `src/pick_place_common/include/pick_place_common/transition_contract.hpp`
- Modify: `src/pick_place_common/src/transition_contract.cpp`
- Modify: `src/pick_place_common/test/test_common_runner.cpp`
- Modify: `src/panda_gazebo_demo/include/panda_gazebo_demo/pick_place/transition_contract.hpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/transition_contract.cpp`
- Modify: Panda registry/runtime/tests

- [ ] 先写一个通过真实 `pick_place_common::StateMachineRunner` 的 RED test：Panda contract precondition/postcondition/resume 失败时，当前 `withBoundaryFailureMetrics()` 指标缺失，证明同名非虚方法隐藏是 effective-dead seam。
- [ ] 在 common 增加显式 decorator：

```cpp
class ITransitionValidationDecorator {
 public:
  virtual ~ITransitionValidationDecorator() = default;
  virtual ValidationResult decoratePrecondition(TransitionKey, const WorldSnapshot &,
                                                ValidationResult) const = 0;
  virtual ValidationResult decoratePostcondition(TransitionKey, const WorldSnapshot &,
                                                 const WorldSnapshot &, const ActionResult &,
                                                 ValidationResult) const = 0;
  virtual ValidationResult decorateResume(TransitionKey, const WorldSnapshot &,
                                          const WorldSnapshot &, ValidationResult) const = 0;
};
```

- [ ] `pick_place_common::TransitionContractRegistry` 持有可空 `shared_ptr<const ITransitionValidationDecorator>`，并在自己的三个 validation 方法内调用；没有 decorator 时结果逐字节语义等价。
- [ ] 把 Panda `withBoundaryFailureMetrics()` 变成 `PandaBoundaryMetricsDecorator`，Panda registry 只负责构造 common registry 与 `validateExecuteCoverage(pandaWorkflowDefinition())`，删除同名 `validate*` 隐藏方法。
- [ ] SO-101 使用 null/default decorator，现有错误码和 metrics 不变。
- [ ] tests 覆盖 decorator 调用恰好一次、成功不凭空失败、失败 metrics 同时出现在 result 和每个 Failure、pre/post/resume 三条路径。

**Acceptance:** runner-level RED 转 GREEN；Panda direct-wrapper-only tests 被 runner composition tests 替代；common/SO-101 无 decorator regression 全绿。

**Commit:** `fix: apply Panda boundary metrics inside common runner validation`

## Task 7: Extract Generic Functional Contracts and Validation Result Assembly

**Files:**

- Create: `src/pick_place_common/include/pick_place_common/functional_transition_contract.hpp`
- Create: `src/pick_place_common/src/functional_transition_contract.cpp`
- Create: `src/pick_place_common/include/pick_place_common/validation_result_utils.hpp`
- Create: `src/pick_place_common/src/validation_result_utils.cpp`
- Create: `src/pick_place_common/test/test_functional_transition_contract.cpp`
- Create: `src/pick_place_common/test/test_validation_result_utils.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/pick_place_contracts.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/recovery_contracts.cpp`
- Modify: `src/pick_place_common/CMakeLists.txt`

- [ ] 为 `FunctionalTransitionContract`、`appendFailure`、`mergeValidationResult`、`finalizeValidationResult` 写 RED tests。
- [ ] 明确并锁定现有语义：additional metrics 使用 `std::map::insert`，已有 key 优先；failure 保持追加顺序；finalize 以 failures 是否为空设置 `ok`；每个 failure 合并 result metrics 且 failure 自有同名 metric 优先。
- [ ] 用公共实现替换 Panda forward/recovery contracts 中两份相同的 `FunctionalContract`, `addFailure`, `merge`, `finish`。
- [ ] 机器人专属 failure category/code/message、required touch links 和 target/support policy 继续留在 Panda。

**Acceptance:** Panda contract tests 的 failure code、顺序和 metrics key/value 完全不变；两个 Panda `.cpp` 不再声明上述四套本地 helper。

**Commit:** `refactor: share functional contract validation assembly`

## Task 8: Share Resume Joint Comparison and Safe Checkpoint Structure Primitives

**Files:**

- Create: `src/pick_place_common/include/pick_place_common/checkpoint_validation.hpp`
- Create: `src/pick_place_common/src/checkpoint_validation.cpp`
- Create: `src/pick_place_common/test/test_checkpoint_validation.cpp`
- Modify: `src/panda_gazebo_demo/src/pick_place/panda_resume_validation_policy.cpp`
- Modify: `src/so101_gazebo_demo/src/pick_place/so101_resume_validation_policy.cpp`
- Modify: Panda/SO-101 file checkpoint stores only where a pure predicate is exactly shared
- Modify: `src/pick_place_common/CMakeLists.txt`

- [ ] 写 RED tests 并实现：

```cpp
struct NamedJointComparison {
  bool complete;
  bool within_tolerance;
  double maximum_error;
};

[[nodiscard]] NamedJointComparison compareNamedJointPositions(
  const std::map<std::string, double> & expected,
  const std::map<std::string, double> & actual,
  double tolerance) noexcept;

[[nodiscard]] bool hasFiniteJointPositions(
  const std::map<std::string, double> &) noexcept;
[[nodiscard]] bool hasFinitePoseMap(
  const std::map<std::string, Pose3d> &) noexcept;
```

- [ ] Tests 覆盖 empty、missing、extra、不同顺序、NaN/Inf、负/NaN tolerance、恰好等于与刚超过 tolerance；`maximum_error` 的 invalid-input 约定必须明确且可断言。
- [ ] Panda/SO-101 policies 使用公共 comparison，但 phase 判断、failure category/code/message 和各自 completeness 规则继续留在 policy。
- [ ] file store 仅迁移完全相同的 finite map/pose predicate；不要统一 JSON parser/writer，不改变原子写、备份、磁盘 key 或 schema rejection 文案。
- [ ] 用既有 schema-v3 fixtures 做 read -> write -> read 兼容测试；负向 resume exact code tests 必须通过。

**Acceptance:** 两个 resume policy 不再各自手写 named-joint 循环；Panda/SO-101 schema-v3 JSON key snapshot 与 R1 前一致；stale session 和 fingerprint mismatch 仍返回各自 exact code 且 trace 为空。

**Commit:** `refactor: share checkpoint comparison primitives`

## Task 9: Full Verification, Runtime Evidence, and Handoff

**Files:**

- Modify: `docs/superpowers/plans/2026-08-04-refactor-optimization-r1.md`（勾选已完成项并追加最终证据索引，不改验收标准）
- Create: no runtime/build artifacts in Git

- [ ] 从 clean cache build 并验证 overlay：

```zsh
cd /data/work/ws_moveit/.worktrees/refactor-optimization-r1
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --symlink-install --cmake-clean-cache
source install/setup.zsh
ros2 pkg prefix pick_place_common
ros2 pkg prefix panda_gazebo_demo
ros2 pkg prefix so101_gazebo_demo
PYTHONNOUSERSITE=1 colcon test --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo --event-handlers console_direct+
colcon test-result --verbose
```

- [ ] 运行只读 formatting/lint gates、两个 source-manifest tests、`git diff --check`；检查没有 `.obsidian`, build/install/log/capture 产物被 tracked。
- [ ] Panda runtime：

```zsh
src/panda_gazebo_demo/test/headless/run_pick_place_e2e.sh --runs 1 --label refactor-optimization-r1
src/panda_gazebo_demo/test/headless/run_recovery_scenarios.sh
src/panda_gazebo_demo/test/headless/run_plan_only_resume_matrix.sh
```

- [ ] SO-101 先 `--show-args`，再在不碰现有 stack 的独立 ROS domain/Gazebo partition 或明确空闲环境中运行：

```zsh
ros2 launch so101_gazebo_demo so101_pick_place.launch.py --show-args
ros2 launch so101_gazebo_demo so101_pick_place.launch.py run_mode:=dry_run start_simulation:=false simulation_session_id:=refactor-optimization-r1-dry
ros2 launch so101_gazebo_demo so101_pick_place.launch.py run_mode:=plan_only start_simulation:=true headless:=true simulation_session_id:=refactor-optimization-r1-plan
ros2 launch so101_gazebo_demo so101_pick_place.launch.py run_mode:=execute start_simulation:=true headless:=false simulation_session_id:=refactor-optimization-r1-execute
```

- [ ] GUI 必须由 `tmux codex` 的明确 window 持有，并先 `source ~/gui-env.zsh`；运行 tile 工具得到 `LAYOUT_OK`，获取本轮前后新截图并实际查看。若 existing live stack 有冲突，停止并报告，不抢占 `codex-cua` 或其他 session。
- [ ] 对 execute 保存同轮：完整命令/exit code、state trace、attachment topic、Planning Scene observe、controllers、joint/TF 前后、object 6D pose/contact、截图路径与 SHA-256。
- [ ] 只关闭本轮明确创建的精确 PID/tmux windows，随后重查既有进程仍在；保存 before/after process ownership。
- [ ] 最终 `git status --short` 必须为空；列出 commits、相对 base diffstat、测试结果、runtime/visual evidence、保留的特殊 robot-local helper 和明确延期项。

**Acceptance:** Acceptance Matrix 每一行都有可打开的 evidence path；任何一项缺失都标记 `NOT ACCEPTED`，不得用“编译通过”替代 runtime/visual 证据。

**Commit:** `docs: record refactor optimization R1 acceptance evidence`

## Explicitly Deferred Beyond R1

- 不统一 Panda 与 SO-101 的 JSON checkpoint store/parser/writer；R1 只抽纯比较/finite predicates，并保持 schema v3 磁盘兼容。
- 不把 SO-101 motion planning、gripper/contact、support surface、profile/target/link/joint、world reset/recovery、URDF/SRDF/launch/config、Teleop 迁入 common。
- 不把 Panda workflow、target/gripper/recovery/MoveIt policy 迁入 common。
- 不为“代码行数更少”改变 retry、timeout、failure category/code、metrics key、orientation metric 或仿真行为。
- 不做真实机械臂执行；runtime acceptance 限于 ai-station 仿真。

## Final Report Template

```text
Status: ACCEPTED | NOT ACCEPTED
Base / branch / worktree:
Commits:
Root and unrelated worktrees preserved:
Dead code removed and manifest guard:
Common components added:
Robot-local semantics intentionally retained:
Panda runner metrics bug RED/GREEN evidence:
Checkpoint schema/key compatibility:
Build and package tests:
Panda runtime evidence:
SO-101 runtime command and exit code:
Gazebo proof:
MoveIt proof:
Controller/joint/TF proof:
Visual proof and screenshot paths:
Exact PIDs/windows cleaned:
Remaining risks / deferred items:
Next review command:
```
