# SO-101 Teacher 执行简化修订：回到 MoveIt/JTC 原生执行

日期：2026-10-06
状态：用户已在讨论中确认本文的三项原则，并授权主任务据此修订执行计划并执行。本文经编写者 inline self review；未宣称任何代码、集成或运行验收通过。

## 1. 适用范围与优先级

本文修订 `2026-10-05-so101-teacher-act-decoupling-amendment.md`（下称“10-05 修订”）及其执行计划 `2026-10-05-so101-teacher-act-decoupling-implementation.md`。冲突时本文优先。10-05 修订中以下内容保持不变：

- Teacher 与 Recorder/QC 分离，数据侧没有控制权限（10-05 §2、§3、§5）；
- 端点判据 `teacher_endpoint_v2`：起终 Pose、五个容差、直立、`settle_s`（10-05 §4.2，计划 D2）；
- 过程质量项 audit-only 的归属表（计划 D3），但其中依附 broker 的条目按本文 §4 重新落位；
- 训练数据合同不降低（10-05 §5）；
- 结果三分报告 `teacher_execution_status` / `teacher_task_result` / `act_data_status`（计划 D1）；
- MuJoCo-only、无硬件、无训练、W2 后的配额规则。

## 2. 三项原则（用户确认）

1. **不要求“控制器执行的每条命令都出自 Teacher”。** ACT 需要的是成功抓放过程的数据，命令来源不重要。MoveIt 本身就是 expert，部分或全部轨迹来自 MoveIt 规划和 `ExecuteTrajectory` 是预期行为。因此删除“独占命令所有权证明”这一要求，以及为它建立的 reservation/admission/native reconstruction 链。
2. **动作标签必须绑定到实际命令。** 标签取自控制器实际接受并输出的 reference，不取自规划意图或 Teacher 自报的命令。
3. **当前版本不做并行隔离。** 单 stack 运行，用正确且唯一的 `ROS_DOMAIN_ID` 隔离；`SimulationEvidence.simulation_session_id` 校验作为兜底。Docker 隔离留待后续版本，本版不实现、不设计。

Teacher 仍必须能停止机器人（见 §4）。

## 3. 新的 Teacher 执行路径

Teacher 复用原始 MuJoCo pick-place 的执行方式：

```
MoveIt plan → move_group /execute_trajectory (ExecuteTrajectory action) → 标准 joint_trajectory_controller
```

- 控制器：`config/mujoco/act/ros2_controllers.yaml` 中 `arm_controller`、`gripper_controller`、`neck_controller` 改回标准 `joint_trajectory_controller/JointTrajectoryController`，与原 pick-place 配置一致（执行者核对原 pick-place 使用的 yaml 并对齐参数）。
- 执行客户端：`src/control/trajectory/executor.py` 的 `MoveItExecutionClient`，带 `monitor` 回调；不经 broker、不经 reservation socket、不经 native forward。
- 状态机：原 pick-place 状态机（含 `RECOVER_*` 状态）。端点判据、audit-only 过程诊断、Teacher event 发布按 10-05 修订挂在这条路径上。
- 规划场景：沿用原 pick-place 的 Planning Scene 同步与 attachment shadow，仍不得用物体瞬移或人工 physics attachment 制造成功。

## 4. 停止机器人（保留的执行保护）

停止全部走原 pick-place 已有的机制，不新建 broker：

| 保护 | 机制 |
|---|---|
| 危险接触力/压缩、明确危险碰撞、必要状态不可用、`paused`/`reset_epoch` 变化 | 各阶段 `monitor()` 抛 `RuntimeError` → `MoveItExecutionClient` 调 `cancel_goal_async()` → `_cancel_and_settle`（5 s 上限）→ JTC 取消后 hold 当前位置 |
| 计划起点漂移 | 执行前 `maximum_joint_error(handoff, trajectory_start) > 0.01 rad` 拒绝执行 |
| 单段执行超时 | `execute(timeout_s)` 超时 → cancel → `TIMED_OUT` |
| 整个 attempt 的独立 deadline（计划 D6，默认 180 s） | Teacher 外层 watchdog：超时则 cancel 当前 goal 并进入终止，不再发新 goal |
| 用户停止 | SIGINT/launch shutdown → watchdog cancel 当前 goal，进程有界退出 |
| 控制器失效 | `ExecuteTrajectory` 拒绝/失败结果码 → FAILED，进入原 `RECOVER_*` 或终止 |
| 释放前支撑（不对无支撑持杯自动开爪） | 保留原 release 阶段的支撑检查，新鲜度用计划 D5 的 `state_max_age_s` |

`monitor()` 的状态来源不变：Teacher 节点自己订阅 `/joint_states` 和 `/so101/simulation/evidence`（`MujocoWorldObserver`），由执行等待循环里的 `progress()`（`rclpy.spin_once`）驱动回调。新鲜度阈值改为计划 D5 的 `state_max_age_s`（0.5 s），与原 qualified phases 的 0.5 s 一致。

计划 D3 中“Keep”的执行保护按上表重新落位到 monitor/cancel；D3 中引用 broker 的条目（`teacher_cup_safety.py`、`teacher_table_support.py`、`teacher_phase_lifecycle.py` 的 ownership/predecessor/pending goal）里，力/压缩与释放前支撑迁入 monitor，ownership/generation/peer 类条目随 broker 一起删除。

## 5. 动作标签绑定到实际命令

- 来源：Recorder 独立订阅各控制器的 `controller_state`（`control_msgs/msg/JointTrajectoryControllerState`，例如 `/arm_controller/controller_state`、`/gripper_controller/controller_state`）。该消息由 JTC 在每个控制周期发布，`reference` 是控制器正在跟踪的插值点，`output`（或该版本对应字段）是实际写给硬件接口的命令。
- 6D accepted controller reference 取 `reference` 中 5 个 arm 关节 + 1 个 gripper 关节的位置；字段与 JTC 版本的确切对应由执行者在当前安装的 `control_msgs` 上核对并写入计划。
- 标签 = 10 Hz sim-time 网格上 `t+0.1 s` 时刻的 reference，沿用现有数据合同；时间基准用消息 header 的 sim-time stamp，同一 reset epoch 内对齐；超出容差、缺口、跨 reset 均使数据 INVALID，不插值伪造。
- 控制器空闲（无活动轨迹）时 JTC 仍发布 hold reference，可作为“保持”标签；如该版本空闲时不发布，则由计划明确定义空闲段处理方式，不得复制旧帧冒充。
- 现有 `act/episode_reference_readback.py` 已能解码 `JointTrajectoryControllerState`，优先复用。
- 不再需要 Teacher event 中的 “native dispatch receipts with accepted controller reference”；Teacher event 保留 reset 完成、起终 Pose、phase begin/finish、正常停止和 terminal。

这样标签来自控制器实际执行的命令，不论命令由谁发出。数据侧依然只读，不连接任何控制入口。

## 6. 删除范围

以下组件只服务于独占命令所有权证明，按 10-05 修订 §7 的清理规则删除（先列清单：旧条件 → 新归属 → 消费者 → 测试 → 理由）：

- C++（`so101_mujoco_support`）：`BrokerOwnedTrajectoryController`、`controller_reservation_socket`、`controller_reservation_protocol`、`controller_reservation_provision`、`controller_goal_admission.hpp`、`bound_reservation.hpp`、`controller_goal_types.hpp`、`so101_trajectory_controllers.xml` 插件注册及其 CMake 目标。若同一包内其他插件（例如 simulation evidence 插件）共用文件，只删 reservation/broker 部分。
- Python ACT adapters（`src/so101_demo_py/src/adapters/act/`）：broker、command broker、reservation client/provision、native forward/runtime/reconstruction、bound authority、owner peer、physics source（broker 用途）、dispatch transaction、broker authority composition/wiring、`teacher_point_of_use`、visible approach commit ingress 等。逐个文件核对消费者：仍被非 ACT 功能使用的保留。
- `so101_teleop/unified` 中的 controller reservation 路径（`controller_reservation_paths.py` 以及 arbiter/admission/bridge/ros_child 中的 reservation 分支）：teleop 若依赖 reservation 获取控制权，执行者先确认 teleop 在不使用 reservation 时的原有控制方式；不能为删除 ACT 链而破坏 teleop。若必须保留 teleop 的某部分，列明理由，不保留给 ACT 用。
- 运行时：`runtime/parallel_ipc.py`、`launch_composition.py`、`act_first_episode_composition.py`、`parallel_worker_runtime.py` 中的 reservation/broker 组装；`source_provenance.py` 中 broker controller 条目。
- 计划 D8（broker 时序模型）整体作废：D8a–D8g 只针对 broker/native 链，随链删除；其中 D8e 的“高频数据回调不得饿死控制回调”原则保留到 Recorder 与 Teacher 分进程的设计里自然满足。
- 相关测试：验证旧所有权合同的测试随实现删除，并在清单中说明被哪条新合同替代；不得 skip/xfail 留尸。

A40 续租审计与 5.1 bound-mode 工作停止，不再修复“每个 service 只接受一个 native goal”的问题；已有证据保留、不移动、不删除，账本记录为 superseded by 本修订。

## 7. 隔离

- 本版只跑一套 headless MuJoCo stack，启动前设置并记录唯一 `ROS_DOMAIN_ID`，prestart 检查该 domain 无其他参与者。
- 不新增 Docker、IPC socket 目录或并行 worker 隔离逻辑；现有并行 IPC 中只服务 reservation 的部分删除，其余并行调度代码保持不动，不在本版扩展。
- Docker 化在后续版本另行设计。

## 8. 实施顺序与验收

1. 主任务按本文修订执行计划：更新 §0 起始状态、D3/D4/D6/D7 中依附 broker 的条目、作废 D8、重写 §2 清理清单和 §3–§5 阶段与门禁；在计划中写清实际命令、输入、预期产物、rc 和日志位置。
2. 定向 RED/GREEN：
   - Teacher 走 `ExecuteTrajectory` 完成无采集抓放（可先 fixture，再 live）；
   - monitor 触发 → cancel → JTC hold 的停止路径；deadline watchdog 与 SIGINT 停止；
   - Recorder 从 `controller_state` 生成 `t+0.1 s` 标签，缺口/跨 reset → INVALID；
   - 端点判据正反例沿用 10-05 修订。
3. 删除旧链并清理测试；冻结后跑普通 xdist/package gate（不收集 benchmark suite），重建/source，核验安装产物与进程 provenance，确认安装树中不再存在 broker controller 插件。
4. Live 串行运行（单 stack、固定场景）：采集关闭的真实抓放；正常采集的真实抓放 → Recorder → seal → 独立回读 QC → Coordinator commit/index；10-05 修订 §8 第 4 项列出的采集故障注入（证明故障不引起任何 Teacher cancel）。
5. 里程碑不变：一条真实抓放、端点通过、完整无损采集、新进程 QC PASS、实际提交、诊断用途拒绝导出。

## 9. 执行位置与证据

沿用 10-05 修订 §9：ai-station、worktree `/home/matianyi/Projects/ros-moveit-demo/.worktrees/so101-act-data-0917a`、branch `codex/so101-act-data-0917a`、evidence root `/data/work/so101-evidence/act-data/20260924-fbc25063-resume`、账本 `docs/experiments/so101-act-data-experiment-ledger.md`，主任务为唯一写入者。源码/config 变化使旧冻结和旧 live 证据对新身份失效，新冻结与新 run 用新子目录。`/data/work` 下的 rm 已获用户预授权，但 live 证据、冻结身份和账本引用的保留项仍保留，每次删除写入账本。不 push、不 merge、不碰硬件、不运行 `ament_uncrustify --reformat`、不用 gh CLI。

## 10. Inline self review

- 三项原则与讨论一致：命令来源不限、标签绑定实际命令、本版不做隔离；停止能力保留并有明确机制。
- 没有降低数据合同；只是把 reference 的来源从 broker dispatch receipt 换成 JTC `controller_state`，后者同样是控制器实际接受的命令。
- 风险：JTC `controller_state` 字段名随版本不同（`reference`/`desired`、`output`/`command`）；空闲时是否发布；该话题的发布频率与 10 Hz 网格对齐所需容差。这些由执行者在计划阶段用实际安装版本核实，不在本文猜定。
- 风险：teleop 对 reservation 的依赖需先查清，避免误删。
- 无未决的用户决策。
