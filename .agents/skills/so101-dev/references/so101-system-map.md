# SO-101 系统地图

## Source of truth 顺序

发生冲突时按以下顺序判断：

1. 本轮运行进程、ROS graph、Gazebo/MoveIt 状态和对应日志；
2. ai-station 实际 checkout 与已安装产物；
3. 当前源码、launch、CMake 和测试；
4. README、设计文档和历史记录。

README 可能落后于正在修改的实现。开始调试时重新检查 live checkout，不把本文的路径快照当成版本证明。

## 仓库与子模块边界

本 skill 本身就装在 SO-101 实现仓库里，所以全文只用两个位置记号，不要混用：

- `<current-repo>`：SO-101 实现仓库根，也就是 `.agents/skills/so101-dev/` 所在的 checkout，用 `git rev-parse --show-toplevel` 得到。
- `<parent-repo>`：把 `<current-repo>` 登记为子模块的上层仓库，用 `git -C "$(git rev-parse --show-toplevel)/.." rev-parse --show-toplevel` 得到，当前为 `robot_demo_001`。

| 层 | 常用位置 | 注意 |
|---|---|---|
| 当前实现仓 | `<current-repo>` | 源码、launch、测试和子模块都在这里；remote `origin` 是 `ros-moveit-demo`，另有 `github` |
| 上层总仓 | `<parent-repo>` | remote `origin` 是 `robot_demo_001`；它的 `.gitmodules` 把 `moveit-demo` 登记为子模块，URL 是 `git@gitee.com:zjumty/ros-moveit-demo.git` |
| 当前仓的子模块 | `<current-repo>/third_party/mujoco_ros2_control` | `<current-repo>` 目前的唯一子模块，以现场 `git submodule status` 为准 |
| ROS 包 | `<current-repo>/src/so101_gazebo_demo_cpp`、`<current-repo>/src/pick_place_common` 等 | 上层仓 `git status` 不展开子模块内部差异 |
| ai-station 工作区 | `/data/work/ws_moveit` | 远端主机路径，本机无法核对；与本地 checkout 不一定同 commit、同 dirty state |
| ai-station package source | `/data/work/ws_moveit/src/so101_gazebo_demo_cpp` | 远端；以远端 live `git status`、`rev-parse` 为准 |
| ai-station install | `/data/work/ws_moveit/install/so101_gazebo_demo_cpp` | 远端；`ros2 run/launch` 通常从这里取产物 |

本地仓和子模块都可能有用户未提交的工作，要查当前仓必须用 `git -C <current-repo> status --short` 单独看。不要自动同步、reset、checkout、stash、clean 或覆盖 remote 文件。

## 运行入口

常见 public launch：

```bash
ros2 launch so101_gazebo_demo_cpp so101_display.launch.py
ros2 launch so101_gazebo_demo_cpp so101_controller.launch.py
ros2 launch so101_gazebo_demo_cpp so101_gazebo.launch.py
ros2 launch so101_gazebo_demo_cpp so101_moveit.launch.py
ros2 launch so101_gazebo_demo_cpp so101_pick_place.launch.py
```

`so101_pick_place.launch.py` 当前默认 `run_mode:=dry_run`、`start_simulation:=false`。执行前总是先跑 `--show-args` 或打开 installed launch 文件确认当前参数；运行模式、`stop_after`、`simulation_session_id` 和 `headless` 的用法与测试阶梯见 [`test-and-acceptance.md`](test-and-acceptance.md)。

## 状态、转移与代码归属

状态枚举和状态机骨架由 `pick_place_common` 拥有，SO-101 只在自己的 workflow 文件里给出具体状态图。下面路径都相对 `<current-repo>`：

- `src/pick_place_common/include/pick_place_common/domain_types.hpp`：`State`、`RunStatus` 等公共领域类型（`ATTACH_GAZEBO`/`DETACH_GAZEBO` 仍在枚举里，但 SO-101 normal forward path 不使用）
- `src/pick_place_common/src/workflow_definition.cpp`：`WorkflowDefinition` 与合法性校验
- `src/pick_place_common/src/runner.cpp`：跨项目共享的运行循环、recovery 和退出码
- `src/so101_gazebo_demo_cpp/src/pick_place/so101_workflow.cpp`：SO-101 的 transitions、`forward_states`、`plan_only_states` 等。判断“某个状态在正常路径上是否真的会被走到”以它为准
- `src/so101_gazebo_demo_cpp/src/pick_place/transition_table.cpp`：把上面这份 workflow 接到 `TransitionTable`/`StateMachine`
- `src/so101_gazebo_demo_cpp/src/pick_place/so101_non_motion_runtime.cpp` 与 `pick_place_state_machine.cpp`：不产生运动的动作实现、节点入口和 checkpoint 接线
- `src/so101_gazebo_demo_cpp/launch/so101_pick_place.launch.py`：参数默认值

## 系统边界

| 边界 | 权威状态 | 常见代码 |
|---|---|---|
| 任务状态机 | 当前 state、Outcome、recovery、exit code | `pick_place_state_machine.cpp`、`transition_table.cpp`、`src/pick_place_common/src/runner.cpp` |
| MoveIt 规划 | planning group、目标、trajectory、error code | `so101_motion_planner.cpp`、`moveit_joint_planning_boundary.cpp` |
| 执行反馈 | FollowJointTrajectory goal/result、controller、joint feedback | `so101_joint_motion_adapter.cpp`、`follow_joint_trajectory_gripper_adapter.cpp` |
| Gazebo attachment | 物理 attach/detach、物体 pose、contact | `src/pick_place_common/src/gazebo_attachment_executor.cpp`、`gazebo_world_observer.cpp` |
| Planning Scene | world/attached collision membership | `moveit_scene_adapter.cpp`、`src/pick_place_common/src/moveit_scene_executor.cpp` |
| reset/recovery | 已产生副作用的逆序收敛 | `world_reset_coordinator.cpp`、`so101_recovery_policy.cpp` |

带 `src/` 前缀的文件按 `<current-repo>` 解析，其余都在 `src/so101_gazebo_demo_cpp/src/pick_place/` 下。

### Physical outcome 归属

- Gazebo pose、contact、friction 和 gravity 从 close 到 release 拥有杯子的 physical truth；MoveIt attachment 只是从最新 Gazebo pose 派生的 collision-planning shadow。Carry plan 要检查两者的 divergence，不要用一个去推断另一个。
- Normal forward execution 从不 attach Gazebo，也不调用 `ATTACH_GAZEBO`/`DETACH_GAZEBO`；reset 为建立 canonical state 做的防御性 detach 是独立事务。
- 当前释放顺序是 `DESCEND_TO_PLACE -> OPEN_GRIPPER -> RETREAT -> DETACH_MOVEIT -> WAIT_RELEASE_SETTLE -> VALIDATE_FINAL_PLACEMENT -> SYNC_WORLD_OBJECT -> DONE`，`WAIT_RELEASE_SETTLE` 和 `VALIDATE_FINAL_PLACEMENT` 只消费当前 non-resumable release epoch。
- 目标安全要求：物理 `OPEN_GRIPPER` 之前必须 `DETACH_MOVEIT`。当前实现不满足它，shadow detach 排在 `OPEN_GRIPPER` 和 `RETREAT` 之后；在独立验证通过或契约被明确修改之前，不得宣称该安全属性通过。

## 安装产物陷阱

`ros2 run` 不执行 source tree 中的 `.cpp`，而是执行当前 overlay 的 installed executable。出现“改了代码行为不变”时依次检查：

```bash
ros2 pkg prefix so101_gazebo_demo_cpp
ros2 pkg executables so101_gazebo_demo_cpp
type -a ros2
printenv AMENT_PREFIX_PATH | tr ':' '\n'
stat /data/work/ws_moveit/install/so101_gazebo_demo_cpp/lib/so101_gazebo_demo_cpp/pick_place_state_machine
```

然后重新 build、source，并在 installed share 目录检查 launch/config 是否已更新。IDE 的 compile_commands 或无报错索引只证明编辑环境，不证明安装与运行。

## kinematics 参数陷阱

ROS 2 会把嵌套 YAML 展平。不要只查：

```bash
ros2 param get /move_group robot_description_kinematics
```

应先枚举并查 dotted leaf：

```bash
ros2 param list /move_group | rg robot_description_kinematics
ros2 param get /move_group robot_description_kinematics.arm.kinematics_solver
```

`No kinematics plugins defined` 还必须定位到具体进程。客户端本地 `RobotModelLoader` 的 warning 不等于 `/move_group` 缺少 solver；当前路径只用 joint-space target 时，它也可能不阻塞执行。加入客户端本地 IK 后要重新评估影响。
