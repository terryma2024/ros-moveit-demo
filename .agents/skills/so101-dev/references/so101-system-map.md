# SO-101 系统地图

## Source of truth 顺序

发生冲突时按以下顺序判断：

1. 本轮运行进程、ROS graph、Gazebo/MoveIt 状态和对应日志；
2. ai-station 实际 checkout 与已安装产物；
3. 当前源码、launch、CMake 和测试；
4. README、设计文档和历史记录。

README 可能落后于正在修改的实现。开始调试时重新检查 live checkout，不把本文日期为 2026-07-28 的路径快照当作版本证明。

## 仓库边界

| 层 | 常用位置 | 注意 |
|---|---|---|
| 本地总仓 | `<repo-root>` | `moveit-demo` 是独立子模块，根仓 status 不展示其内部全部差异 |
| 本地实现 | `<repo-root>/moveit-demo/src/so101_gazebo_demo_cpp` | 修改前运行 `git -C moveit-demo status --short` |
| ai-station 工作区 | `/data/work/ws_moveit` | 与本地 checkout 不一定同 commit、同 dirty state |
| ai-station package source | `/data/work/ws_moveit/src/so101_gazebo_demo_cpp` | 以 live `git status`、`rev-parse` 为准 |
| ai-station install | `/data/work/ws_moveit/install/so101_gazebo_demo_cpp` | `ros2 run/launch` 通常从这里取产物 |

根仓和子模块都可能有用户未提交工作。不要自动同步、reset、checkout、stash、clean 或覆盖 remote 文件。

## 运行入口

常见 public launch：

```bash
ros2 launch so101_gazebo_demo_cpp so101_display.launch.py
ros2 launch so101_gazebo_demo_cpp so101_controller.launch.py
ros2 launch so101_gazebo_demo_cpp so101_gazebo.launch.py
ros2 launch so101_gazebo_demo_cpp so101_moveit.launch.py
ros2 launch so101_gazebo_demo_cpp so101_pick_place.launch.py
```

`so101_pick_place.launch.py` 的当前源码默认 `run_mode:=dry_run`、`start_simulation:=false`。执行前总是运行 `ros2 launch so101_gazebo_demo_cpp so101_pick_place.launch.py --show-args` 或打开 installed launch 文件确认当前参数。

调试时优先使用：

- `run_mode:=dry_run`：检查状态机和失败路径，不证明规划或物理动作；
- `run_mode:=plan_only`：检查候选轨迹，不证明关节、TCP 或物体运动；
- `run_mode:=execute`：只有仿真 stack 与安全门控明确后使用；
- `stop_after:=<STATE>`：把复现缩到首个分叉边界；
- `simulation_session_id:=<unique-id>`：避免错误复用 checkpoint/session 证据；
- `headless:=true`：自动测试；最终视觉验收需 GUI 运行。

状态名、转移和运行模式以这些文件为准：

- `src/so101_gazebo_demo_cpp/src/pick_place/domain_types.cpp`
- `src/so101_gazebo_demo_cpp/src/pick_place/transition_table.cpp`
- `src/so101_gazebo_demo_cpp/src/pick_place/so101_task3_runtime.cpp`
- `src/so101_gazebo_demo_cpp/src/pick_place/pick_place_state_machine.cpp`
- `src/so101_gazebo_demo_cpp/launch/so101_pick_place.launch.py`

## 系统边界

| 边界 | 权威状态 | 常见代码 |
|---|---|---|
| 任务状态机 | 当前 state、Outcome、recovery、exit code | `pick_place_state_machine.cpp`, `runner.cpp`, `transition_table.cpp` |
| MoveIt 规划 | planning group、目标、trajectory、error code | `so101_motion_planner.cpp`, `moveit_joint_planning_boundary.cpp` |
| 执行反馈 | FollowJointTrajectory goal/result、controller、joint feedback | `so101_joint_motion_adapter.cpp`, `follow_joint_trajectory_gripper_adapter.cpp` |
| Gazebo attachment | 物理 attach/detach、Coke pose/contact | `gazebo_attachment_executor.cpp`, `gazebo_world_observer.cpp` |
| Planning Scene | world/attached collision membership | `moveit_scene_adapter.cpp`, `moveit_scene_executor.cpp` |
| reset/recovery | 已产生副作用的逆序收敛 | `world_reset_coordinator.cpp`, `so101_recovery_policy.cpp` |

正常链中 Gazebo Attach 与 MoveIt Attach 是两个独立副作用。Place 也要分别完成物理 detach、Planning Scene detach、最终物体 pose 同步和 retreat。

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

`No kinematics plugins defined` 还必须定位到具体进程。客户端本地 `RobotModelLoader` 的 warning 不等于 `/move_group` 缺少 solver；如果当前路径只使用 joint-space target，它也可能不阻塞执行。若加入客户端本地 IK，再重新评估影响。

## Physical outcome ownership addendum

- Gazebo pose/contact/friction/gravity 从 close 到 release 拥有杯子的 physical truth。
- MoveIt attachment 是从最新 Gazebo pose 派生的 collision-planning shadow。
- Carry plan 必须检查 Gazebo-vs-shadow divergence；开夹爪前先 detach shadow。
- `WAIT_RELEASE_SETTLE` 和 `VALIDATE_FINAL_PLACEMENT` 只消费当前 release epoch。
- Reset 可防御性 detach stale Gazebo joint；normal forward execution 永不 attach Gazebo。
