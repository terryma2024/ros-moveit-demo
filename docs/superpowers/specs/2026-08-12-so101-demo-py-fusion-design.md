# SO-101 MuJoCo / Gazebo 统一模块设计

**日期：** 2026-08-12
**状态：** 用户已确认
**设计取证提交：** `3acb85c74c9f3180a4d8b25ee6c1fc09ede33879`
**实施基线：** 按第 3.1 节在实施开始时现场选择
**目标 ROS 2 package：** `so101_demo_py`
**目标 Python namespace：** `so101_demo`

## 1. 目标

把 `so101_mujoco_demo_py` 与 `so101_gazebo_demo_py` 的控制逻辑收敛为一个实现包
`so101_demo_py`，同时满足以下要求：

- MuJoCo 与 Gazebo 使用同一套状态机、阶段编排、MoveIt 请求、轨迹执行、夹爪控制、
  Planning Scene 同步、恢复和结果结构。
- MuJoCo 与 Gazebo 保留独立启动器，可以明确选择仿真环境。
- policy 允许按 backend 演进；v1 的 MuJoCo 和 Gazebo variant 都从 MuJoCo 五连胜 policy
  原样复制。
- MuJoCo 在新包、新安装产物和新 bundle 指纹上重新取得 FULL_RESTART 5/5 与
  RESET_WORLD 5/5，两种生命周期分开统计。
- Gazebo v1 正常执行相同控制链。执行失败时报告真实首个失败阶段和证据；结果不作为
  v1 RED -> GREEN 或发布门控。
- 视觉 mesh、任务物体 geometry 和稳定命名尽量复用；碰撞、接触和物理求解参数允许
  backend 专用。
- 为未来真实 SO-101 arm 预留控制、安全和能力接口。v1 只提供 fail-closed stub，不连接
  驱动、不发送动作。
- 旧两个包保留一个兼容窗口，只做命令和 launch 转发，不继续拥有控制逻辑或资产。

## 2. 非目标

本次融合不包括：

- 调整 MuJoCo 五连胜 motion/contact policy；
- 为 Gazebo 调参到完整成功或五连胜；
- 统一 MuJoCo 与 Gazebo 的接触力、penetration、friction 或 solver 数值语义；
- 新建真实机械臂启动器、连接真机驱动或执行真机动作；
- 在启动时自动转换 URDF、MJCF 或 SDF；
- 重写 MoveIt 2、ros2_control 或 controller manager；
- 删除旧包兼容入口。删除应在兼容窗口结束后作为独立变更完成。

## 3. 已审计基线

设计期间在 ai-station 的
`/data/work/ws_moveit/.worktrees/so101-mujoco-ros2` 只读确认：

- 分支在讨论期间前进到 `3acb85c`，现有 worker 仍有未提交实验代码和未跟踪实验文档；
  本设计不覆盖、清理或纳入这些 dirty files。
- 主工作区 `/data/work/ws_moveit` 的 `main` 为 `8d85205286d2635d4ddbc91431c933dafb4eb661`，
  工作树 clean；迁移 worktree 的已提交 HEAD 为
  `3acb85c74c9f3180a4d8b25ee6c1fc09ede33879`。
- `main` 是迁移 HEAD 的祖先，迁移 HEAD 不是 `main` 的祖先；`git cherry` 显示 128 个
  feature-only patch、0 个 patch-equivalent commit。
- 主工作区没有 `src/so101_mujoco_demo_py`，因此截至本次审计，MuJoCo 迁移尚未合回主工作区。
- MuJoCo motion policy
  `src/so101_mujoco_demo_py/config/motion_policies/light_cup_wall_pick.yaml` 的已观察
  SHA-256 为
  `aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356`。
- 历史资格证据中，`EXP-158` 至 `EXP-162` 是固定 bundle 的 FULL_RESTART 连续五次
  有效成功；`EXP-163` 至 `EXP-167` 是独立统计的 RESET_WORLD 连续五次有效成功。
- MuJoCo 实现已经形成九阶段物理执行链，并包含原子仿真证据、ResetWorld、接触策略、
  Planning Scene shadow、资格 runner 和逐物理步运输诊断。
- Gazebo 实现仍保留较早的紧凑 workflow，且大部分 live execute 行为集中在单文件；已知
  MuJoCo v1 policy 无法在 Gazebo 完成同一闭环。
- 两边名称相似的 `domain`、`workflow`、`runner`、`motion` 和 `moveit` 文件已经分叉，不能
  通过同名文件平均合并。

### 3.1 实施基线选择硬门

本设计分支只承载 spec。正式实施前必须重新读取主工作区和迁移 worktree 的 commit、dirty
状态、实验账本和资格 bundle，并按以下顺序选择基线：

1. 解析主工作区 `main` HEAD 和迁移 worktree 最新已提交 HEAD。
2. 使用 ancestry、patch-equivalence 和目标 package/资产存在性共同判断迁移是否已合回；
   不能只看分支名、提交标题或单个 merge commit。
3. 若迁移 HEAD 已被主工作区包含，且主工作区实际包含完整 `so101_mujoco_demo_py`、
   `so101_gazebo_demo_py` 和对应资格 bundle，则以当时主工作区的 clean HEAD 为实施基线。
4. 若尚未合回，则以迁移 worktree 的最新 clean commit 为实施基线。
5. 任一候选 worktree dirty 时，未提交内容都不能进入基线。等待当前 worker 提交并形成新的
   clean commit，或者明确冻结已有 clean HEAD；不得 stash、reset、clean 或复制 dirty 内容。

截至本次审计，第 3 条不成立，因此当前候选基线是迁移 worktree 的已提交 HEAD `3acb85c`；
它只是当前判断，正式实施时仍必须重新执行本节硬门。

## 4. 选定路线

采用以 MuJoCo 五连胜实现为行为基线的绞杀式迁移：

1. 先把已验证 MuJoCo 实现机械迁入 `so101_demo_py`。
2. 只做 package、import 和 resource 路径改名，先证明行为保持。
3. 逐个把 MuJoCo 直接依赖收口为稳定 ports。
4. 在相同 ports 上接入 Gazebo adapter。
5. 最后加入旧包转发和 real-arm fail-closed stub。

不采用以下路线：

- 同时从两个包抽取“折中核心”：两边行为成熟度和结构差异过大，会让回归根因不可定位。
- 拆成 core、MuJoCo backend、Gazebo backend 三个 ROS package：依赖隔离更强，但增加
  ament resource、版本和发布复杂度，也不符合一个合并模块的目标。

## 5. 包与源码布局

代码必须使用映射式 `src` 布局，不创建 `so101_demo_py/so101_demo_py` 或
`src/so101_demo_py` 嵌套目录：

```text
so101_demo_py/
├── src/
│   ├── __init__.py
│   ├── core/
│   │   ├── domain.py
│   │   ├── workflow.py
│   │   ├── runner.py
│   │   ├── policy.py
│   │   ├── outcome.py
│   │   └── recovery.py
│   ├── application/
│   │   ├── phases/
│   │   ├── pick_place.py
│   │   └── qualification.py
│   ├── control/
│   │   ├── moveit/
│   │   ├── trajectory/
│   │   ├── gripper/
│   │   └── planning_scene/
│   ├── ports/
│   │   ├── robot_control.py
│   │   ├── world.py
│   │   ├── lifecycle.py
│   │   ├── phase_evidence.py
│   │   ├── capabilities.py
│   │   └── evidence.py
│   ├── backends/
│   │   ├── mujoco/
│   │   ├── gazebo/
│   │   └── real_stub/
│   ├── runtime/
│   │   ├── composition.py
│   │   ├── launch_composition.py
│   │   └── provenance.py
│   └── cli/
├── launch/
├── config/
├── assets/
├── test/
├── package.xml
├── setup.py
└── setup.cfg
```

`setup.py` 使用：

```python
package_name = "so101_demo_py"
python_package = "so101_demo"
package_dir = {python_package: "src"}
```

内部导入统一为 `from so101_demo...`。安装测试必须验证 import namespace、ament package
name 和 package share directory 三者没有混淆。

## 6. 分层与依赖方向

### 6.1 Core

`core` 保存纯业务值和规则：状态、转移、运行结果、policy model、outcome、checkpoint 与恢复
决策。它不得导入 ROS、MoveIt、MuJoCo、Gazebo 或 backend 实现。

### 6.2 Application

`application` 编排经过验证的九阶段行为：

```text
APPROACH
-> GRASP
-> MICRO_LIFT
-> LIFT
-> TRANSPORT
-> DESCEND
-> ALIGN
-> RELEASE
-> RETREAT / FINAL_VALIDATE
```

Application 只依赖 core、ports 和共享 control service，不直接创建具体 observer、ROS action
client 或 simulator client。

### 6.3 Control

`control` 保存 MuJoCo 与 Gazebo 共用的 ROS 2 / MoveIt 控制实现，包括：

- joint waypoint 与 TCP motion request；
- MoveIt plan/execute；
- FollowJointTrajectory 和 gripper action；
- joint state、TF 与执行结果证据；
- Planning Scene world/attached shadow；
- 可逆 Allowed Collision Matrix lease；
- controller readiness 与有界 stop/cancel。

仿真环境通过 ros2_control hardware plugin 不同，但上层 action/topic 契约一致，因此不为两个
backend 复制 control 代码。

### 6.4 Ports

Ports 是 application 与外部系统之间的稳定边界。Backend 实现 ports，application 不反向依赖
backend。

### 6.5 Backends

- `backends/mujoco`：原子 world evidence、reset epoch、pause、viewer 和逐物理步诊断。
- `backends/gazebo`：Gazebo pose/contact/world stats、reset 和 bridge 生命周期。
- `backends/real_stub`：能力声明和安全拒绝；不含真实驱动。

### 6.6 Runtime

`runtime` 是唯一选择 backend、policy variant 和具体 adapter 的位置。业务代码中禁止出现
`if backend == "mujoco"` 或 `if backend == "gazebo"`。

依赖方向只有：

```text
launch / CLI -> runtime composition -> application -> core + ports
                         |                    |
                         |                    -> shared control
                         -> backend adapters -> ports
```

## 7. Ports 与中立证据

### 7.1 RobotControlPort

```python
class RobotControlPort(Protocol):
    def current_joint_state(...) -> JointStateEvidence: ...
    def plan_joint_waypoints(...) -> PlanResult: ...
    def plan_tcp_motion(...) -> PlanResult: ...
    def execute(...) -> ExecutionResult: ...
    def command_gripper(...) -> GripperResult: ...
    def stop(...) -> StopResult: ...
```

它面向机器人动作，不面向仿真器。未来真机可以实现同一接口，但必须先增加独立安全设计和
用户授权。

### 7.2 WorldPort

```python
class WorldPort(Protocol):
    def snapshot(...) -> WorldEvidence: ...
    def snapshot_with_receipt(...) -> ReceivedWorldEvidence: ...
    def reset(...) -> ResetReceipt: ...
```

`WorldEvidence` 至少保留：backend、session ID、reset epoch、simulation step、simulation
time、物体 pose/twist、接触身份、原始碰撞体名称、truncation/evidence-loss 状态和
backend metadata。

统一结构不等于统一物理语义。MuJoCo signed distance / force 与 Gazebo contact depth / force
不能使用同一阈值解释。

### 7.3 PlanningScenePort

```python
class PlanningScenePort(Protocol):
    def add_world_object(...) -> SceneResult: ...
    def attach_shadow(...) -> SceneResult: ...
    def detach_shadow(...) -> SceneResult: ...
    def synchronize_object_pose(...) -> SceneResult: ...
    def temporary_allow_collision(...) -> SceneLease: ...
```

物理世界和 Planning Scene 分别取证。Planning Scene attachment 只是规划 shadow，不能证明
仿真物体被物理夹持。

### 7.4 LifecyclePort

```python
class LifecyclePort(Protocol):
    def readiness(...) -> ReadinessResult: ...
    def pause(...) -> PauseReceipt: ...
    def shutdown(...) -> ShutdownResult: ...
```

Reset、pause、shutdown 都返回可关联 session/epoch 的 receipt，不能仅根据 service 返回值
推断世界已经稳定。

### 7.5 PhaseEvidencePort

当前 MuJoCo 分支已经加入逐物理步运输证据，因此保留可选 instrumentation port：

```python
class PhaseEvidencePort(Protocol):
    def begin_trace(...) -> TraceReceipt: ...
    def mark_boundary(...) -> BoundaryReceipt: ...
    def finish_trace(...) -> PhaseTrace: ...
```

规则：

- 该 port 只负责诊断和资格证据，不直接修改 trajectory 或 policy。
- MuJoCo qualification profile 可以要求 lossless physics-step trace。
- Gazebo v1 缺少等价能力时仍正常 execute，只在结果中声明该诊断 unavailable。
- 只有 policy/qualification profile 显式要求某 capability 时，缺失才 fail closed；不得把
  MuJoCo 专用 instrumentation 隐式升级为所有 backend 的执行前置条件。

### 7.6 Capabilities

Backend 在 composition 时返回显式 capabilities，例如：

- `atomic_snapshot`
- `snapshot_with_receipt`
- `reset_epoch`
- `pause`
- `viewer_camera`
- `physical_contact_force`
- `lossless_physics_step_trace`

Application 通过 capability requirement 选择合法流程，不使用 duck-typing fallback。

## 8. Workflow 与运行结果

MuJoCo 的九阶段语义是唯一 v1 行为基线。Gazebo 旧 workflow 中仍有价值的 reset、observer、
contact 和 failure evidence 被迁入 adapter，但不作为第二套状态机保留。

运行状态与资格状态必须分离：

```text
RunStatus:
  SUCCEEDED  完整执行成功
  FAILED     有效运行中的策略或物理失败
  INVALID    provenance、初态、证据或基础设施污染
  REJECTED   能力或安全门拒绝执行

QualificationStatus:
  QUALIFIED
  NOT_QUALIFIED
```

Gazebo v1 正常执行。若在第一段 MOVE_ABOVE_OBJECT 失败，应返回：

```yaml
run_status: FAILED
qualification_status: NOT_QUALIFIED
backend: gazebo
first_failed_phase: MOVE_ABOVE_OBJECT
failure_code: PATH_TOLERANCE_VIOLATED
evidence:
  - <运行证据引用>
```

不得返回 `SKIPPED`，也不得把有效策略失败伪装成基础设施无效。反之，启动或证据污染必须
返回 `INVALID`，不能冒充 Gazebo policy 已知失败。

## 9. Policy 与资格 bundle

### 9.1 完整 variant

不使用多层 YAML overlay。每个 backend 拥有一份完整、严格、可独立哈希的 variant：

```text
config/policies/light_cup_wall_pick/v1/
├── mujoco.yaml
├── gazebo.yaml
├── real_stub.yaml
└── manifest.yaml
```

v1 规则：

- `mujoco.yaml` 按字节复制资格使用的冻结 policy，不重新格式化、不调参。
- `gazebo.yaml` 第一版按字节复制同一 policy，明确记录 `NOT_QUALIFIED`。
- Gazebo 后续调整必须新增 version，例如 `v2/gazebo.yaml`，不得回写 v1。
- `real_stub.yaml` 只保存安全范围和禁止执行声明，不复制仿真接触阈值。

### 9.2 两种 fingerprint

`policy fingerprint` 证明 waypoint、阶段参数、gripper target、outcome 和恢复规则一致。

`qualification bundle fingerprint` 覆盖：

- policy；
- source commit；
- package install prefix；
- MJCF/SDF/URDF 与 collision 资产；
- contact、Noslip/solver 和 task scene 配置；
- ros2_control/controller 与 MoveIt 配置；
- evidence schema/plugin；
- lifecycle 与 qualification runner 版本。

包重命名和接口重构会产生新的 bundle hash，因此不能沿用历史 QUALIFIED 标签。历史 5/5
是行为基线，最终必须在新 bundle 上重新资格测试。

### 9.3 Loader 规则

Loader 必须：

- 严格验证 schema 和字段全集；
- 拒绝未知字段、缺失 variant 和隐式 fallback；
- 只接受有限数值，布尔值不能冒充数值；
- 验证 backend 与 variant 匹配；
- 把 policy hash 和 bundle hash 写入每次运行结果。

## 10. 启动器与 composition

用户入口保持 backend 明确且相互独立：

```bash
ros2 launch so101_demo_py so101_mujoco.launch.py
ros2 launch so101_demo_py so101_mujoco_pick_place.launch.py
ros2 launch so101_demo_py so101_gazebo.launch.py
ros2 launch so101_demo_py so101_gazebo_pick_place.launch.py
```

不提供默认 backend，也不新增真实机械臂 launcher。

四个 launch 文件只解析参数和选择 backend，公共 composition 位于
`so101_demo.runtime.launch_composition`。公共参数为：

- `run_mode`
- `execute`
- `headless`
- `policy_id`
- `policy_version`
- `session_id`
- `evidence_file`
- `readiness_timeout_s`

Backend 专用参数显式命名，例如 `mujoco_scene`、`gazebo_world`，只能由对应 adapter 读取。

启动日志和运行 manifest 必须打印/记录 backend、source commit、package prefix、policy hash、
bundle hash、execute 状态、ROS domain 和 Gazebo partition（适用时）。

## 11. 几何资产

```text
assets/
├── common/
│   ├── visual/
│   ├── task_objects/
│   └── geometry-manifest.yaml
├── mujoco/
│   ├── collision/
│   └── scene.xml
└── gazebo/
    ├── collision/
    └── world.sdf
```

复用边界：

- SO-101 visual mesh、任务物体 visual、link/joint 名称、TCP 名称和共同尺寸由 `common`
  manifest 管理。
- 两个 backend 直接引用同一份 common visual mesh，不再各自复制原始 STL。
- MuJoCo 已验证的凸分解和 fingertip pad collision 保留在 `assets/mujoco/collision`。
- Gazebo primitive/SDF collision 保留在 `assets/gazebo/collision`。
- 惯量、friction、contact、Noslip/solver 和 world 文件允许 backend 专用。
- URDF/MJCF/SDF 转换只允许作为离线、版本固定、可审计的开发工具。运行时不得自动转换或
  下载资产。
- manifest 记录来源路径、格式、尺寸和 SHA-256；asset closure test 禁止运行时读取旧包。

Parity 测试比较共同 link、joint、mesh 尺寸、TCP 和 task-object 初始 pose，不要求两个物理
引擎产生相同接触数值。

## 12. 旧包兼容窗口

`so101_mujoco_demo_py` 和 `so101_gazebo_demo_py` 保留一版薄包装：

- package.xml 依赖 `so101_demo_py`；
- console script 转发到新 CLI 并输出一次弃用警告；
- launch include 对应的新 launcher；
- 显式映射旧参数名；
- 无法等价映射的参数直接报错，不能静默丢弃；
- 不保存 Python 控制逻辑、policy、模型、mesh 或重复测试 fixture。

兼容测试必须证明旧入口最终解析到 `so101_demo_py` 的安装前缀和同一 bundle。兼容窗口结束
后的删除作为独立 spec/变更处理。

## 13. 真实机械臂扩展边界

v1 只有 `backends/real_stub`：

- 可以解析安全配置和返回 capabilities；
- readiness 明确返回 `REAL_HARDWARE_NOT_CONFIGURED`；
- plan、execute、gripper、reset、recovery 全部 fail closed；
- 不打开串口、不发现设备、不加载硬件 plugin、不发布控制命令；
- 不提供 `so101_real.launch.py`。

未来真实接入必须有独立设计，至少覆盖：急停、使能、限速、关节软硬限位、通信 watchdog、
反馈新鲜度、净空、人工确认、plan-only/execute 权限分离和安全恢复。Simulation reset 不能映射
为真机 recovery。

## 14. 错误处理

每个失败结果必须包含：

- backend、session ID 和 reset epoch；
- policy/bundle fingerprint；
- first failed phase；
- failure category 与稳定 error code；
- ROS action/service result；
- 相关 joint/TF、World 和 Planning Scene 证据引用；
- 结果属于 `FAILED`、`INVALID` 还是 `REJECTED`。

恢复只撤销已产生的副作用。Scene lease、attachment shadow、gripper command 和 trajectory goal
均必须具有可审计的 acquire/release 或 cancel 结果。未知状态不得继续执行下一阶段。

## 15. 迁移顺序

正式实施必须使用独立实现 worktree，并先按第 3.1 节确定主工作区或迁移 worktree 的 clean
基线 commit。

### 阶段 0：冻结实现与账本

- 重新审计主工作区与迁移 worktree 的 ancestry、patch-equivalence、目标 package 和 bundle；
  若迁移已合回，使用主工作区 clean HEAD，否则使用迁移 worktree 最新 clean commit。
- 保存最新 source、install、policy 和 bundle provenance。
- 读取现有迁移/资格账本，记录最后可信 checkpoint。
- 建立新的融合实验账本，不改写 EXP-158 至 EXP-167。
- 记录并保护现有 dirty files、tmux、ROS graph 和进程。

### 阶段 1：机械迁入

- 新建 `so101_demo_py` 和 `src -> so101_demo` 映射。
- 复制 MuJoCo 运行代码、测试和必要资产。
- 只改 package/import/resource 名称。
- 禁止抽象、调参、重排 phase 或更改 evidence schema。
- 用 characterization test 比较旧/新 CLI、workflow transitions、policy hash 和 result schema。

### 阶段 2：逐边界抽取

按 WorldPort、LifecyclePort、PlanningScenePort、RobotControlPort、PhaseEvidencePort 的顺序，
每次只替换一个直接依赖：

1. 先写会失败的 contract test；
2. 替换一个边界；
3. 跑定向与 package test；
4. 跑一次 MuJoCo 完整闭环；
5. 确认 package prefix 和 bundle provenance。

### 阶段 3：新启动器与兼容入口

- 新入口先通过安装空间验证。
- 旧入口映射到新 composition。
- 增加 forbidden-import/resource 测试，保证新包不读取旧包。

### 阶段 4：Gazebo adapter

- 迁入 Gazebo observer、reset、bridge 和 launch ownership。
- 将 Gazebo evidence 转换为中立类型，同时保留 backend metadata。
- 正常执行 v1 policy，记录真实首个失败阶段。
- 不根据已知失败预先拒绝 execute，也不要求 Gazebo 闭环成功作为 v1 merge gate。

### 阶段 5：Real stub

- 实现 capability/readiness 与所有动作的结构化安全拒绝。
- 用测试证明零设备访问和零 ROS 控制副作用。

### 阶段 6：最终资格

- 冻结新 source、policy、bundle 和生命周期。
- 分别执行 FULL_RESTART 与 RESET_WORLD 五连胜。
- 做一次不计数的新鲜 GUI/数值证据复核。
- 更新融合账本 checkpoint 后才能宣布完成。

## 16. 测试与验收矩阵

| 层级 | MuJoCo | Gazebo | Real stub |
|---|---|---|---|
| Policy/schema | 必须通过 | 必须通过 | 安全配置通过 |
| Unit/contract | 必须通过 | 必须通过 | 必须通过 |
| Package/build/install | 必须通过 | 必须通过 | 必须通过 |
| Asset closure | 必须通过 | 必须通过 | 不适用 |
| Dry-run | 必须通过 | 必须通过 | 拒绝执行 |
| Plan-only | 必须通过 | 正常运行并报告结果 | 拒绝执行 |
| Execute | 必须成功 | 正常运行，策略结果不门控 | 必须拒绝 |
| FULL_RESTART | 固定 bundle 连续 5/5 | 不门控 | 不适用 |
| RESET_WORLD | 固定 bundle 连续 5/5 | 不门控 | 不适用 |
| GUI/数值证据 | 至少一次新复核 | 失败边界需要数值证据 | 不适用 |

Gazebo v1 的 adapter/build/launch/evidence contract 是门控项。至少一次 execute 必须形成有效
运行并报告真实策略结果；`FAILED` 或 `SUCCEEDED` 均不阻止 v1，`INVALID` 不能替代这项验收。

MuJoCo 两个五连胜批次必须分别固定 commit、policy、bundle 和 lifecycle：

- `VALID` success 进入分母并延长序列；
- `VALID` failure 进入分母并中断序列；
- `INVALID` 不进入分母，但作废当前批次；
- FULL_RESTART 与 RESET_WORLD 不得混算。

关键自动化门包括：

- `src` 映射和 import namespace 测试；
- workflow transition 与 RunResult characterization；
- policy exact hash 与 strict schema；
- qualification bundle manifest；
- backend contract fake；
- World/Scene/controller 分层证据；
- launch composition 与 argument mapping；
- old-package forbidden runtime ownership；
- asset closure、共同 geometry 和 backend-specific collision；
- real stub zero-side-effect；
- package prefix、runtime executable 和 installed resource provenance。

## 17. 完成条件

只有同时满足以下条件，才可宣布融合完成：

- `so101_demo_py/src` 是唯一控制逻辑来源；
- Python namespace 为 `so101_demo`，不存在嵌套源码目录；
- 两个旧包只剩可审计转发代码；
- MuJoCo 在新包和新安装产物上重新取得 FULL_RESTART 5/5；
- MuJoCo 在独立批次重新取得 RESET_WORLD 5/5；
- Gazebo execute 确实运行并产生可分类的首个失败阶段或成功结果；
- Gazebo 结果不进入 MuJoCo 资格结论，也不作为 v1 RED -> GREEN 门；
- real stub 的所有动作路径 fail closed，且没有硬件副作用；
- 几何 manifest、资产闭包和 package provenance 通过；
- 每次计数运行都记录 source、install、policy/bundle、controller、world、Planning Scene 和
  joint/TF 证据；
- 使用本轮新视觉证据复核可见结果；
- 现有 worker 的 dirty files、实验文档、tmux 和 ROS/Gazebo/MuJoCo 进程均未被覆盖或误停。

## 18. 主要风险与控制

### 风险：大规模改名掩盖行为变化

控制：先机械迁入和 characterization，再逐 port 抽取；每次只有一个主动边界变化。

### 风险：把统一 evidence 类型误当作统一物理量

控制：保留 backend metadata 和独立 threshold；禁止跨引擎复用接触数值资格结论。

### 风险：Gazebo 已知失败拖动 MuJoCo policy

控制：v1 两份 policy 初始相同且不可改；Gazebo 后续调整只能新增 version。

### 风险：可选 MuJoCo 诊断阻止 Gazebo 正常执行

控制：PhaseEvidencePort 由 capabilities/qualification profile 管理，不是 base execute 的隐式
前置条件。

### 风险：旧包继续成为第二实现源

控制：forbidden-import/resource、安装前缀和 asset closure 测试；兼容包仅转发。

### 风险：为未来真机预留接口演变成未授权动作

控制：v1 无真实 launcher，real stub 零设备访问并对所有动作 fail closed。

### 风险：并发 worker 状态被设计或实施覆盖

控制：设计与实施使用独立 worktree；实施前重新审计 clean commit、dirty state、账本、tmux 和
进程所有权。

## 19. 已确认决策

- 采用 MuJoCo 五连胜基线的绞杀式迁移。
- 实施基线不是固定设计提交：迁移已合回时使用主工作区，否则使用迁移 worktree 最新 clean
  commit；未提交内容永不进入基线。
- 合并包名为 `so101_demo_py`，Python namespace 为 `so101_demo`。
- 源码目录固定为 `so101_demo_py/src`。
- MuJoCo 与 Gazebo 启动器分开。
- 旧包保留一版薄兼容入口。
- v1 两个仿真 backend 的 policy 从 MuJoCo 五连胜 policy 对齐。
- MuJoCo 两类五连胜是硬门。
- Gazebo execute 正常运行并报告首个失败，不作为 v1 RED -> GREEN 门。
- 真机 v1 只提供 fail-closed 扩展点。
- visual geometry 尽量复用，collision/physics 允许 backend 专用。
