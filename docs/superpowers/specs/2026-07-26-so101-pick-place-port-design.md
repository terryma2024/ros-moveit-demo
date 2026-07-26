# SO-101 固定位置 Pick-Place 状态机迁移设计

## 1. 背景与范围

Phase 1 已将 SO-101 的 description、ros2_control、MoveIt、Gazebo world 和工具合并到 `/data/work/ws_moveit/src/so101_gazebo_demo`。本阶段在该 package 内复制 Panda pick-place 的组件化状态机，使 SO-101 在固定场景中完成完整抓取、放置、恢复和 headless 验收。

本阶段目标：

- 保留 Panda 的状态、执行模式、checkpoint/resume、恢复链与证据化门控结构；
- 用 SO-101 自己的关节、link、controller、目标策略和夹爪几何实现适配层；
- 在 Gazebo 与 MoveIt 双世界中完成固定位置 Coke pick-place；
- 完整验证正常流程、失败注入、resume 和三种 attachment 恢复场景；
- 不修改 `panda_gazebo_demo`，不抽取跨 package 公共库。

不在本阶段范围：相机感知、动态目标识别、实机控制、Panda/SO-101 公共组件重构。

## 2. 方案比较与选择

### 2.1 迁移组织

方案 A：整体复制后统一改名。优点是早期文件齐全；缺点是 Panda 双指、6D 姿态、attachment link 和 table geometry 会先形成错误实现，安全门控形同虚设。

方案 B：能力优先分层迁移。先补物理 attach 与观测能力，再复制纯状态机，最后实现 SO-101 adapter、目标策略和 E2E。每层都有独立测试和运行证据。

方案 C：先抽公共库，再接两个机器人。可减少重复，但会在 SO-101 语义尚未跑通前冻结错误抽象，并扩大 Panda 回归面。

选择方案 B。它最符合“先复制隔离、两边跑通后再重构”的既定边界。

### 2.2 5-DOF 运动策略

方案 A：直接沿用 Panda 完整 6D Pose target。拒绝。SO-101 手臂只有关节 `1..5`，不能把任意位置和任意完整四元数都作为独立约束。

方案 B：所有状态只校验关节角。可运行，但无法证明 TCP 到达 Coke 上方、局部运动接近垂直，也无法支撑后续感知坐标接入。

方案 C：校准后的 joint target/waypoint ladder 作为首版命令真值，TCP 位置和工具 approach-axis 作为计划与执行观测真值；释放绕工具轴的 twist。选择此方案。

具体策略：

- `MOVE_ABOVE_OBJECT`、`MOVE_ABOVE_PLACE`、`RETREAT` 和相应恢复运动：碰撞感知 joint-space goal；
- `DESCEND`、`LIFT`、`DESCEND_TO_PLACE` 和相应恢复短运动：校准的 joint waypoint ladder；
- 每个 waypoint 通过 FK 重建 `so101_tcp` 路径，验证端点、近垂直、单调性、关节跳变、碰撞和时间参数；
- Cartesian 规划不是首版依赖。只有离线实验同时满足 fraction、端点、工具轴和碰撞门控后，才允许替换某段 ladder；状态机契约不随之改变。

## 3. 不变量与机器人 Profile

新增集中式 `SO101Profile`（名称可按现有 C++ 风格调整），禁止 SO-101 常量散落在 adapter：

- world frame：`world`
- planning group：`arm`
- TCP：`so101_tcp`
- arm joints：`1`, `2`, `3`, `4`, `5`
- gripper joint：`6`
- gripper controller action：`/gripper_controller/follow_joint_trajectory`
- arm controller action：`/arm_controller/follow_joint_trajectory`
- MoveIt attach link：`gripper`
- MoveIt touch links：`gripper`, `jaw`
- Coke model/link：`coke` / `body`
- table geometry：size `0.50 × 0.60 × 0.04 m`，world pose `(0, -0.20, 0.10)`
- Coke geometry：radius `0.033 m`，height `0.122 m`，canonical world pose `(0.02, -0.28, 0.181)`
- gripper pre-open：`q6 = 0.707194871 rad`，目标宽度 `70 mm`
- gripper contact：`q6 = 0.662818811 rad`，目标宽度 `66 mm`
- grasp section depth：`20 mm`
- attachment topics：`/so101/attach_coke`, `/so101/detach_coke`, `/so101/coke_attached_event`, `/so101/coke_attached`

Gazebo DetachableJoint 的实际 parent link 必须从运行时 SDF entity tree 验证，不根据 URDF link 名猜测。MoveIt attach link 仍使用 SRDF/RobotModel 中的 `gripper`。

`panda_gazebo_demo` 子树对象在整个阶段前后必须保持 `75fb2e1e66ad1440f47f52f708b91887384084fd`。

## 4. 组件边界

### 4.1 复制的纯状态机组件

以下结构复制进 `so101_gazebo_demo`，改为 SO-101 namespace/include path，但不改变行为语义：

- state/domain types 与 transition table；
- state action registry、plan/executor/validator interfaces；
- runner 与 `dry_run`, `plan_only`, `execute`；
- `fail_at`, `stop_after`, checkpoint v3, `resume`；
- simulation session id 与 common resume validator；
- recovery 以当前可观测事实为依据的执行框架。

不复制未被 Panda runtime 使用的旧 wrapper：`move_above_object_planner.*`、`descend_planner_executor.*`。

### 4.2 参数化复制的 ROS adapter

- MoveIt motion adapter：对象名、planning group、TCP 和目标类型来自 SO profile；
- Gazebo observer/attachment executor：world、model/link 和 topics 来自 SO profile；
- MoveIt scene adapter/executor：table/Coke geometry、attach link、touch links 可配置；
- attachment state relay：使用 SO topics，并保持 durable state 与 initial detach 语义；
- world reset：同步 Gazebo canonical pose、MoveIt world objects 和 attachment 状态。

### 4.3 SO-101 专项实现

- `FollowJointTrajectoryGripperAdapter`：只向 joint `6` 发送单关节轨迹，action 成功后仍必须用 `/joint_states` 验证；
- 单关节夹爪 validator：使用 q6 和 20 mm 截面宽度函数，不使用 Panda 双指对称性；
- 5-DOF motion target、plan evidence 和 transition validator；
- SO-101 fixed target/waypoint policy；
- SO-101 recovery policy 与 runtime node assembly；
- SO-101 launch、headless fixtures 和日志证据。

## 5. 可计算的验证语义

### 5.1 工具姿态

设目标工具 approach-axis 为单位向量 `a_t`，观测姿态旋转矩阵为 `R`，`so101_tcp` 在本地坐标中的 approach-axis 为单位向量 `a_local`。观测轴：

```text
a_o = R · a_local
axis_error = acos(clamp(a_o · a_t, -1, 1))
```

validator 检查 `axis_error <= axis_tolerance`，不比较绕 `a_o` 的 twist。因此不是“删除全部姿态检查”，而是将完整 quaternion 距离替换为机器人可实现的工具轴倾角。

### 5.2 近垂直短路径

对 FK TCP path `p_0 ... p_n` 和目标垂直方向 `v`：

- 轴向进度 `s_i = (p_i - p_0) · v` 必须按状态方向单调；
- 横向偏差 `l_i = ||(p_i - p_0) - s_i v||` 不得超过阈值；
- 终点位置误差不得超过阈值；
- 每一点工具轴误差不得超过阈值；
- 轨迹完整、有时间参数、关节跳变受限且通过碰撞检查。

### 5.3 静止判据

当前 SO-101 ros2_control 只暴露 position，不能把缺失/NaN velocity 当作零。推荐优先补 `velocity` state interface，并验证 `/joint_states` 为有限值；若 Gazebo 插件无法可靠提供，则使用独立位置窗口判据：

```text
max_j(max_i |q_j(t_i) - q_j(t_0)|) / (t_last - t_0) <= stationary_threshold
```

窗口至少包含 3 个新鲜样本，覆盖 arm joints `1..5` 和 joint `6`。缺样本、时间倒退或非有限值一律是 observation failure。

### 5.4 夹爪

- PREPARE_OPEN/CLOSE 的 API 成功只是执行证据，不是物理成功；
- pre-open 目标验证 `q6` 落在 pre-open 容差，并由同一几何函数得到约 `70 mm`；
- contact 目标验证 `q6` 落在 contact 容差，并由同一几何函数得到约 `66 mm`；
- Coke 在 close 前后不得被明显推偏或抬起；
- joint `6` 的运动不纳入 arm TCP 的“机械臂静止”判定，但必须有自己的停止门控。

### 5.5 双世界 attachment

成功顺序保持：

```text
CLOSE_GRIPPER → ATTACH_GAZEBO → ATTACH_MOVEIT → LIFT
```

门控：

- `ATTACH_GAZEBO`：Gazebo durable state 由 false 变 true，Coke 未突跳；
- `ATTACH_MOVEIT`：Coke 从 MoveIt world 消失并出现在 `gripper` attached object，touch links 精确匹配；
- 进入 carrying motion 前，Gazebo/MoveIt 必须都 attached；
- 恢复不信任 checkpoint 的历史 attachment 标志，只以当前可观测事实决定需要执行哪些 detach；
- 最终目标是两边 detached、Coke 6D pose 同步、夹爪安全打开、arm 安全撤离。

## 6. 目标校准与安全门

固定目标不是从 Panda 数值平移得出。先提供 calibration/plan-only 工具，产生并记录：

- above-pick joint target；
- pick/contact joint target；
- above-place joint target；
- place joint target；
- retreat/home joint target；
- 三段短路径的 joint waypoint ladders。

每组目标必须同时通过：joint limits、MoveIt self/world collision、TCP FK 位置、工具轴、与 table/Coke 的几何余量。目标值进入版本控制前由测试锁定。没有通过校准门不得进入真实 execute E2E。

首次依赖夹爪—Coke 接触前，必须解决或隔离 Gazebo/DART mesh collision construction warning，并证明夹爪接触 collision geometry 实际存在；仅有 visual mesh 不算通过。

## 7. 状态与恢复语义

正常状态序列保持：

```text
IDLE → PREPARE_OPEN_GRIPPER → MOVE_ABOVE_OBJECT → DESCEND
→ CLOSE_GRIPPER → ATTACH_GAZEBO → ATTACH_MOVEIT → LIFT
→ MOVE_ABOVE_PLACE → DESCEND_TO_PLACE → OPEN_GRIPPER
→ DETACH_GAZEBO → DETACH_MOVEIT → SYNC_WORLD_OBJECT
→ RETREAT → DONE
```

恢复保持事实驱动，至少覆盖 `gazebo_only`、`moveit_only`、`both_attached`。恢复动作的顺序按当前边界选择最小安全集合，但必须满足：在 detach 后先确认 arm/夹爪真实状态，再执行 open/retreat；运行环境观测故障发生在 plan 前时直接停止，不盲目执行恢复动作。

每个动作状态继续遵守：

```text
observe before → validate precondition → plan → validate plan
→ execute → observe after → validate transition → next state
```

`dry_run` 不 plan/execute/validate；`plan_only` 在 stop boundary 只 plan+plan validation；`execute` 完整执行。checkpoint 只在成功边界持久化，resume 必须先以当前观测重新验证边界。

## 8. 实施顺序

1. 建立 SO profile、观测和仿真 attachment 基础能力；运行时确认 DetachableJoint parent link，并解决接触 collision 门控。
2. 复制纯状态机 core、checkpoint/runner 和对应单测，先跑通 dry-run/失败迁移。
3. 实现 SO gripper、MoveIt scene/attachment 和 5-DOF motion evidence/validator。
4. 增加固定目标校准工具，固化 joint targets/waypoint ladders，并通过 plan-only 矩阵。
5. 组装 runtime node、reset/relay/launch，先跑 pick half，再跑完整 place。
6. 迁移 recovery/resume/headless E2E，执行真实 GUI 与 headless 验收。

每项实现由 fresh subagent 完成并提交，随后由独立 reviewer 做规格和质量审查；发现 Critical/Important 必须修复并复审后才能进入下一项。

## 9. 验收标准

- Panda 子树对象不变，Panda build/test 不回归；
- SO package 在 ROS-only 环境 clean build/test 通过；
- dry-run 正常与 fail_at 状态序列准确；
- q6 FollowJointTrajectory 的 pre-open/contact 有 action、joint state、几何宽度三类证据；
- plan-only 对全部运动状态给出完整、碰撞感知、端点和工具轴证据；
- 真实执行最终为 DONE，Coke 到固定放置目标，夹爪打开，两边 detached，MoveIt/Gazebo Coke 6D pose 一致；
- `gazebo_only`、`moveit_only`、`both_attached` recovery 场景全部通过；
- stop/checkpoint/resume 不允许跳跃，resume validator 失败时不执行后续动作；
- headless CI 可启动、运行、失败时输出分类证据并清理进程；
- 连续三次完整固定位置 pick-place 成功；
- Gazebo GUI 截图和独立 topic/TF/Planning Scene 证据共同证明物理状态，不能只用日志宣称成功。

## 10. 后续重构门

只有上述验收全部通过，才启动 Panda/SO-101 对比重构。候选公共部分限于已经由两个机器人共同证明的纯状态机、checkpoint、runner、错误模型和抽象接口；gripper geometry、target policy、links/joints、world geometry 与 attachment profile 保持机器人专属。
