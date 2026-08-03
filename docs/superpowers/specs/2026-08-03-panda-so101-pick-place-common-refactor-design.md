# Panda / SO-101 Pick-Place 公共组件重构设计

**日期：** 2026-08-03

**状态：** 方案 A 已获用户批准；等待书面 spec 复核

**源码基线：** `moveit-demo/main@d2a2761617397d9b6fdd14346e1aabca854caa05`

## 1. 背景

`panda_gazebo_demo` 是现有 pick-place 状态机的第一套实现，`so101_gazebo_demo`
随后以“先复制隔离、跑通后再抽象”的方式迁移。两套实现现在都包含状态、错误模型、
runner、checkpoint/resume、执行 registry、Gazebo attachment 和 MoveIt Planning Scene
等相似结构，但它们已经分别演化：

- Panda 使用 7-DoF、双指夹爪、Pose/Cartesian 与 named-target 规划；
- SO-101 使用 5-DoF joint target/waypoint ladder、单关节夹爪、物理接触和 regrasp 门控；
- SO-101 还增加了 `WAIT_GRASP_STABLE`、`MICRO_LIFT`、`VALIDATION_FAILED`、
  `single_step`、`force_continue` 和 `state_trace` 等语义；
- 两边的 checkpoint JSON、world observation 和 scene geometry 也存在真实差异。

当前重复已经增加双向维护成本。例如两个 package 都定义本地 `pick_place_core`，都保留
相似的 `domain_types`、`state_action`、`transition_table`、`runner`、
`simulation_session_id`、`gazebo_attachment_executor` 和 C++ quality gate。继续复制会让
错误修复、安全门控和 Teleop workflow 语义产生漂移。

本设计启动此前预留的“两个实现跑通后进行对比重构”阶段，但不把机器人专属物理语义
伪装成通用逻辑。

## 2. 基线与事实边界

设计审批后重新执行了：

```bash
git -C moveit-demo fetch origin --prune
git -C moveit-demo pull --ff-only origin main
```

结果为 `Already up to date`，本设计基于 `main@d2a2761`。该提交仅收敛 SO-101
fingertip geometry 测试；此前的 workflow run/resume spec 和 plan 已在其父提交中。

源码静态盘点得到：

- `include/.../pick_place` 有 17 个同名头文件；
- `src/pick_place` 有 14 个同名 C++ 文件；
- `gazebo_attachment_executor.cpp` 的控制流程高度相似；
- `cmake/run_cpp_quality_gate.cmake` 当前两份内容完全相同；
- `domain_types.hpp`、`state_action.hpp`、`transition_table.hpp` 和
  `moveit_scene_executor.hpp` 具有明显共同结构。

这些是“候选公共边界”的源码证据，不等于所有同名文件都可以直接合并。尤其是
`file_checkpoint_store.cpp`、`gazebo_world_observer.cpp`、`pick_place_runtime.cpp` 和
运动/夹爪验证已经显著分化，不能按文件名机械抽取。

## 3. 目标

1. 新增一个由 Panda 和 SO-101 同时依赖的 ROS 2 package：`pick_place_common`。
2. 让纯状态机工作流、错误模型、registry、runner 和公共 side-effect executor 只有一个
   实现来源。
3. 保留两个机器人的运动学、夹爪、几何、配置、物理证据和安全策略边界。
4. 保持现有 ROS 外部契约、状态序列、失败代码、checkpoint/resume 和运行证据语义。
5. 支持逐消费者迁移、独立测试和单提交回退，避免大爆炸式重构。
6. 让后续第三种机械臂可以复用工作流内核，但仍必须实现自己的 robot profile 和物理策略。

## 4. 非目标

- 不改变 Panda 或 SO-101 的抓取动作、waypoint、夹爪目标或接触阈值。
- 不重新设计 SO-101 Teleop UI/API。
- 不把本次仿真结果扩展为实机安全结论。
- 不统一 URDF、SRDF、launch、world、controller 或 Planning Scene 几何配置。
- 不引入运行时插件加载、动态字符串 DSL 或跨进程状态机服务。
- 不以“消灭所有重复行”为目标；差异大且所有权明确的实现继续留在机器人 package。
- 不在本设计中承诺合并 `file_checkpoint_store` 或完整 `gazebo_world_observer`；只有后续
  characterization test 证明语义一致时才允许抽取其内部子组件。

## 5. 方案比较

### 方案 A：独立公共 package，分阶段迁移

新增 `pick_place_common`，导出纯 C++ core 与 ROS adapter target。先建立行为基线和公共
测试，再分别切换 Panda、SO-101，最后删除重复实现。

优点：依赖显式、可独立测试、可逐包回退、真正停止代码漂移。缺点：需要一次受控的类型
和 namespace 迁移。

### 方案 B：header-only 模板状态机

让 runner 模板化到机器人自己的 State/WorldSnapshot 类型。

优点：两个机器人可以保留独立枚举。缺点：模板错误和编译边界复杂，难以共享 checkpoint、
ROS executor、CMake 和运行时观测基础设施，也会把大量实现暴露到头文件。

### 方案 C：继续复制，通过脚本同步

保留两个 package 的完整实现，用脚本检查或生成重复文件。

优点：短期改动小。缺点：两个 package 并未共同依赖同一组件，差异冲突仍需人工解决，
安全修复仍可能只落一边。

**选择：方案 A。**

## 6. 总体架构

```text
pick_place_common
├── pick_place_common::core
│   ├── domain/error/result types
│   ├── workflow definition + state machine
│   ├── action/plan/contract registries
│   ├── runner + checkpoint/resume orchestration
│   └── common world/task-object evidence
├── pick_place_common::ros_adapters
│   ├── Gazebo attachment executor
│   └── MoveIt scene executor
└── exported CMake quality-gate module

panda_gazebo_demo
├── Panda workflow definition and composition root
├── Panda motion/gripper/target/recovery policy
├── Panda observer and scene geometry
└── existing ROS executables and launch API

so101_gazebo_demo
├── SO-101 workflow definition and composition root
├── SO-101 motion/contact/gripper/recovery policy
├── SO-101 observer, scene geometry and reset
├── Teleop/web/camera/debug tooling
└── existing ROS executables and launch API
```

依赖只能从机器人 package 指向 `pick_place_common`。公共 package 不得 include 或 link
任何 Panda/SO-101 头文件和 target。

## 7. 公共 Core 设计

### 7.1 状态词汇与 WorkflowDefinition

`pick_place_common::State` 使用当前 Panda/SO-101 状态集合的并集。它表达 pick-place
领域词汇，而不是规定每个机器人必须运行全部状态。

机器人 package 分别构造 `WorkflowDefinition`：

```cpp
struct WorkflowDefinition
{
  State initial_state{State::IDLE};
  std::map<State, StateTransitions> transitions;
  std::set<State> action_states;
  std::set<State> forward_states;
  std::set<State> terminal_states;
  std::set<State> force_continue_states;
};
```

公共构造校验必须拒绝：

- 非终态没有 transition；
- transition 指向未声明状态；
- terminal state 同时被声明为 action；
- `force_continue_states` 不在当前 workflow；
- `IDLE`、`DONE`、`ERROR` 等基础边界缺失。

Panda definition 跳过 SO-101 专属的稳定、micro-lift 和物理抓取验证状态；SO-101
definition 保留当前完整图。公共 runner 不通过硬编码状态序列判断机器人类型。

### 7.2 请求、结果与错误模型

公共 `RunRequest` 使用两边能力的安全并集：

```cpp
struct RunRequest
{
  RunMode mode{RunMode::DRY_RUN};
  std::optional<State> stop_after;
  bool resume{false};
  std::optional<State> fail_at;
  std::uint64_t max_state_transitions{100};
  bool single_step{false};
  bool force_continue{false};
};
```

默认值保持 Panda 现有行为。`force_continue` 只有当前 workflow 明确声明允许的状态才能生效；
Panda 的集合为空。`RunResult` 始终包含 `state_trace`，Panda 的 ROS 日志和退出码不因此变化。

`FailureCategory`、`Failure`、`ActionResult`、`RunStatus` 和 `RunMode` 迁入公共 namespace。
现有失败 code、message 和 metrics 名称是兼容性契约，重构不能借机重命名。

### 7.3 Registry、契约和 Runner

迁入公共 core：

- `PlanArtifact`、`PlanResult`、`ExecutionContext`；
- `IStatePlanner`、`IStateExecutor`、`StateActionRegistry`；
- `IPlanValidator`、`PlanValidatorRegistry`；
- `ITransitionContract`、`TransitionContractRegistry`；
- `IRecoveryPolicy` 接口；
- `StateMachineRunner` 的 dry-run、plan-only、execute、failure、recovery、stop、step 和
  resume orchestration。

Runner 继续执行以下顺序：

```text
observe before
→ validate precondition
→ plan
→ validate plan
→ execute
→ observe after
→ validate transition
→ checkpoint
→ next state
```

公共 runner 只依赖接口与 `WorkflowDefinition`。运动、夹爪、attachment、scene 和 recovery
的实际 policy 由机器人 composition root 注册。

### 7.4 WorldSnapshot

公共 `WorldSnapshot` 使用通用 `task_object` 命名，包含：

- observation 时间与 freshness；
- arm/gripper stationary 状态；
- TCP pose、joint positions/velocities；
- MoveIt world object、task-object attachment/link/touch-links；
- Gazebo task-object pose、attachment、stationary；
- simulation session ID；
- 可选的 task-object/finger contact evidence。

SO-101 当前需要的 collision name、contact point、normal、depth 和 contact-height 证据使用
类型化的可选结构保留。Panda observer 可以不填这些字段。不得使用 `std::any`、裸 JSON
或无约束 metrics map 代替已有物理证据类型。

### 7.5 Checkpoint 与兼容性

公共 core 持有：

- `CheckpointPhase`；
- `ExpectedWorldState`；
- `Checkpoint` 的工作流字段；
- `ICheckpointStore`；
- common resume validation 和 runner 内的 checkpoint/resume orchestration。

Panda 的 `configuration_hash` 与 SO-101 的 `policy_bundle_sha256` 在公共内存模型中统一为
`configuration_fingerprint`，但磁盘 codec 必须保持各自 schema v3 字段和兼容读取：

- 现有 Panda v3 fixture 可以加载并 resume；
- 现有 SO-101 v3 fixture 可以加载并 resume；
- 新写出的文件仍可被重构前同版本 parser 读取，除非另行批准 schema v4；
- 不兼容、session mismatch、fingerprint mismatch 和 world mismatch 继续 fail closed。

两边 `file_checkpoint_store.cpp` 当前差异很大。本轮默认只共享接口、内存模型和 orchestration，
保留各自 codec/store；若 characterization tests 证明某个原子文件 I/O 子组件完全等价，才在
同一范围内抽取该子组件。

## 8. 公共 ROS Adapter 设计

### 8.1 GazeboAttachmentExecutor

抽取通用 attach/detach 命令、timeout、poll、cancel、idempotency 和 durable-state convergence。
构造配置包含 allowed state、目标 attachment 状态、topics 和时间参数。

机器人专属前置条件通过 `IAttachmentGuard` 注入：

- Panda 可以保留夹爪开度/状态门控；
- SO-101 的双侧接触、沉降和 penetration 门控仍由 SO-101 contract/guard 拥有；
- 公共 executor 不解释具体夹爪几何。

### 8.2 MoveItSceneExecutor

公共接口使用 `task_object`，提供：

- attach with `MoveItAttachmentSpec`；
- detach；
- sync/upsert task-object world pose；
- observe attachment/world convergence。

公共 executor 拥有状态检查、调用顺序、timeout、poll、cancel 和 idempotency。具体
CollisionObject geometry、table/pedestal 初始化和 robot-specific scene reset 仍在消费者。

### 8.3 暂不整体抽取的 ROS 组件

- `GazeboWorldObserver`：SO-101 的接触和 fingertip evidence 显著多于 Panda；先共同实现
  `IWorldObserver` 和 snapshot 类型，不合并两个完整 observer。
- attachment relay node：只有在 topic/event/durable-state characterization 一致后再抽取
  relay class；两个 package 的 executable 名保持不变。
- MoveIt motion/gripper adapter：机器人自由度、controller action 和验证模型不同，不抽取。

## 9. 构建与 Package 边界

新增：

```text
src/pick_place_common/
├── CMakeLists.txt
├── package.xml
├── cmake/
├── include/pick_place_common/
├── src/core/
├── src/ros_adapters/
└── test/
```

导出唯一 target 名：

```text
pick_place_common::core
pick_place_common::ros_adapters
```

Panda 和 SO-101 的 `package.xml` 增加 `<depend>pick_place_common</depend>`。现有本地库 target
分别重命名为带机器人前缀的内部 target，避免两个 package 都生成语义不清的
`libpick_place_core.so`：

```text
panda_pick_place_runtime
panda_pick_place_ros_adapters
so101_pick_place_runtime
```

现有 ROS executable 名、package 名和 launch 名不变。

两份 C++ quality gate CMake 实现迁入 `pick_place_common` 导出的 CMake extras，统一函数名：

```cmake
pick_place_common_add_cpp_quality_gate(...)
```

函数继续接受每个 package 自己的 source root、target 和 exclusion list；SO-101 生成式 calibration
headers 的 exclusions 必须保留。禁止运行 `ament_uncrustify --reformat`。

## 10. 外部兼容性契约

以下行为不得变化：

- package：`panda_gazebo_demo`、`so101_gazebo_demo`；
- executable 和 launch 文件名；
- ROS topic、service、action、parameter 名和默认值；
- dry-run、plan-only、execute、stop、step、resume 和 force-continue 语义；
- 正常、失败和 recovery 状态序列；
- process exit code、failure category/code 和关键 metrics；
- Gazebo attachment 与 MoveIt attachment 的独立事实边界；
- checkpoint v3 兼容性；
- Teleop Start/Run/Resume 对 C++ owner 的参数映射。

允许变化的是内部 include namespace、CMake target、库文件组织和机器人 composition root 的
组装方式。若发现外部消费者直接 include 现有 package 内部 pick-place headers，实施者必须先
报告依赖，再决定提供过渡 alias 还是将其列为显式 breaking change；不得静默破坏。

## 11. 迁移顺序

### Phase 0：ai-station 当前基线

1. 读取根仓和 `moveit-demo/AGENTS.md`、执行 `$so101-dev`。
2. 记录本地与 ai-station 的 pwd、branch、commit、submodule 和 dirty files。
3. 检查 `codex-cua`、现有 Gazebo/MoveIt/controller/Teleop 进程，不启动第二套 stack。
4. 在独立 `codex/pick-place-common-refactor` branch/worktree 工作。
5. 使用当前安装产物记录 Panda/SO-101 dry-run、plan-only、checkpoint/resume、recovery 和
   execute 基线；现状不通过时先报告，不把重构当成掩盖基线失败的手段。

### Phase 1：Characterization tests

在移动源码前锁定：

- 两个 workflow 的完整 normal/fail-at state trace；
- action/plan/contract registration coverage；
- plan-only 不执行且返回 `PLAN_ONLY_COMPLETE`；
- stop/single-step/checkpoint/resume 边界；
- stale/incompatible checkpoint 拒绝；
- cancel/timeout/idempotency；
- Gazebo attachment 与 MoveIt scene convergence；
- 现有 checkpoint v3 fixture。

### Phase 2：建立 `pick_place_common`

先添加 package、导出 target、公共 quality gate 和公共单测，不切换两个 runtime。公共实现和
现有实现可以短期并存，但不能在此阶段删除消费者源码。

### Phase 3：迁移纯 Core

1. 先将 Panda 切换到公共 domain、workflow、registry 和 runner；完成 focused/package test
   以及 dry-run/plan-only runtime gate。
2. 再将 SO-101 切换到同一公共 core；保留扩展状态、step、force-continue、contact evidence
   和 state trace。
3. 每个消费者切换是独立提交和独立 reviewer gate；一个消费者失败不影响另一个回退。

### Phase 4：迁移公共 Side-Effect Executor

先迁移 Gazebo attachment executor，再迁移 MoveIt scene executor。每次只改变一个边界，并
分别验证 success、failure、timeout、cancel、idempotency 和真实状态收敛。

### Phase 5：删除重复与文档收口

只有两个 package 都不再编译旧实现后，才删除重复文件。更新 CMake、package.xml、README、
架构文档和测试路径；用静态扫描证明公共实现只剩一份，并证明 robot-specific 文件仍留在
各自 package。

### Phase 6：最终运行验收

重新 build/source 安装产物，执行完整测试矩阵和 fresh GUI 验收。最终结果必须来自本轮构建，
不能复用旧日志、旧截图或旧 `element_index`。

## 12. 测试与验收矩阵

| 层 | Panda | SO-101 | 公共门 |
|---|---|---|---|
| 编译/质量 | package clean build、clang-tidy/format check | package clean build、生成头 exclusions 保留 | common package build/test/export |
| 状态机 | normal/fail-at/recovery traces | 扩展状态、validation failed、force continue | WorkflowDefinition coverage |
| 模式 | dry-run、plan-only、execute、resume | 加 single-step/Teleop owner mapping | 公共 runner semantics |
| checkpoint | Panda v3 fixture/round-trip | SO-101 v3 fixture/round-trip | mismatch fail closed |
| Gazebo | attach/detach/pose | attach/detach/contact/settling | executor timeout/cancel/idempotency |
| MoveIt | world/attached Coke | world/attached task object、touch links | scene convergence |
| 运动 | Panda plan/execute/joint/TF | SO-101 joint ladder/contact/retreat | 不由公共层解释机器人运动学 |
| E2E | 完整 pick-place 与 recovery | 连续三次完整 pick-place 与 recovery | 无重复 stack、退出码正确 |
| 视觉 | fresh Panda Gazebo/RViz | `LAYOUT_OK` 后 fresh SO-101 Gazebo/RViz | 截图与数值状态一致 |

推荐最终命令骨架；精确 target/test 名以实施后 CMake 为准：

```bash
cd /data/work/ws_moveit-pick-place-common
source /opt/ros/jazzy/setup.zsh
colcon build --packages-up-to panda_gazebo_demo so101_gazebo_demo --symlink-install
source install/setup.zsh
PYTHONNOUSERSITE=1 colcon test \
  --packages-select pick_place_common panda_gazebo_demo so101_gazebo_demo \
  --event-handlers console_direct+
colcon test-result --verbose
ros2 pkg prefix pick_place_common
ros2 pkg prefix panda_gazebo_demo
ros2 pkg prefix so101_gazebo_demo
```

## 13. 运行时证据要求

最终报告分别列出：

- 当前 source、install prefix、binary `stat` 和运行命令；
- 状态 trace、process exit code 和 checkpoint；
- MoveIt plan/error code 和 Planning Scene world/attached membership；
- controller action result、joint/TF/TCP 前后差值；
- Gazebo task-object attachment 与 6D pose；
- SO-101 contact/penetration/settling 的受影响证据；
- fresh screenshot 路径和画面中确认的机器人、夹爪、物体状态；
- preserved dirty files、未通过项和下一条精确命令。

日志中的 `DONE`、plan success、action success、Gazebo attachment、MoveIt attachment 和 GUI
画面是不同证据，不能互相替代。

## 14. 错误处理与回滚

- 每个迁移 phase 在删除旧实现前必须有 GREEN gate。
- Panda 和 SO-101 的切换提交相互独立；回滚只撤销失败消费者，不 reset 整个 worktree。
- 不自动 stash、checkout、clean、reset 或覆盖用户 dirty files。
- baseline 已失败时暂停迁移，保存证据并区分“既有失败”与“重构回归”。
- 公共类型无法表达机器人安全事实时，优先把事实留在机器人 extension/policy，不扩大无类型
  escape hatch。
- 运行时发现 source/install 不一致时重新 build/source 并证明产物 provenance，不继续在旧
  binary 上调试源码。
- live 验收时不得并行启动第二套 `/move_group`、Gazebo、controller 或 Teleop stack。

## 15. 提交边界

实施计划应至少形成以下可独立审查的提交：

1. characterization tests；
2. `pick_place_common` package、exported targets 和 quality gate；
3. 公共 workflow/domain/registry；
4. Panda core migration；
5. 公共 runner/checkpoint orchestration；
6. SO-101 core migration；
7. Gazebo attachment executor migration；
8. MoveIt scene executor migration；
9. 重复源码删除、文档和最终验证记录。

提交时只 stage 当前任务列出的路径。没有用户明确要求时，不 push、不合并 main，也不更新
根仓 `moveit-demo` 子模块指针。

## 16. 完成标准

只有以下全部满足才可宣布重构完成：

- 两个 demo 在依赖图中都显式依赖 `pick_place_common`；
- 公共 workflow/runner/registry 和已选 side-effect executor 只有一个实现来源；
- robot-specific motion、gripper、geometry、profile、contact 和 reset 仍由各自 package 拥有；
- 三个 package 的 focused、package 和质量测试无新增失败；
- ROS 外部契约与 checkpoint v3 兼容测试通过；
- Panda 和 SO-101 的 before/after state trace、退出码和关键物理结果一致；
- SO-101 使用本轮构建连续三次到 `DONE`，两边 attachment 最终为 false；
- Gazebo、MoveIt、controller/joint/TF 和 fresh visual evidence 彼此一致；
- 没有覆盖用户改动，没有遗留重复 runtime stack；
- remaining risks 和未抽取重复项有明确所有权与理由。

## 17. 审批后的执行交接

本 spec 书面复核通过后，使用 `superpowers:writing-plans` 生成逐任务实施计划。计划必须给出
精确文件、接口、RED/GREEN 命令、预期结果、提交边界和 ai-station runtime/visual gates。

随后向 ai-station 的 Codex 发送一份完整 handoff，让其在独立 branch/worktree 中执行；主会话
只在每个 phase 的测试/reviewer gate、发现基线偏差或需要新增权限时介入，不通过零散命令
改变已批准设计。
