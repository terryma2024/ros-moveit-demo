# 分层证据与根因定位

## 快速分流

先按症状取第一检查点，不要凭印象直接改代码。

| 症状 | 第一检查点 |
|---|---|
| 修改 C++ 后行为不变 | `ros2 run` 使用的 install 前缀、构建时间、重新 source 的 overlay |
| `No kinematics plugins defined` | 警告所属进程，以及 `/move_group` 的 dotted leaf parameter |
| 状态机到 `DONE` 但物体未搬运 | 物体 world pose、support contact 和 gripper contact；不要先改 transition table |
| MoveIt 规划成功但机械臂未动 | 是否调用 execute、action 结果、`/joint_states` 与 TF 前后差值 |
| normal forward path 出现 unexpected Gazebo attachment | `/so101/object_attached` 与 `/so101/object_attached_event`，以及是谁下发 attach |
| MoveIt 仍是 world object 而画面里物件跟着夹爪 | MoveIt attached membership 与 attached link；物理是否真的持有靠 pose 和 contact 判断 |
| 日志互相矛盾 | 是否同时存在重复 `/move_group`、RViz、Gazebo 或旧 tmux 进程 |
| GUI 与日志不一致 | 新截图、正确窗口或会话、画面时间与本轮日志时间是否一致 |

## 先写竞争假设

不要从症状直接跳到修改。每轮写 2–3 个可区分的假设，再选成本最低、信息增益最大的命令。示例：状态机输出 `DONE` 但物体没动时，用运行参数和 runtime registration、物体 world pose 加 `/task_object/contacts`、本轮时间戳的新截图，分别区分“dry-run executor”“物理根本没夹住”“截图过期或看错会话”。先跑能分开它们的检查，不要先改 transition table。

## 六层证据

| 层 | 要回答的问题 | 典型证据 |
|---|---|---|
| Provenance | 哪份源码、配置和 binary 在运行？ | commit/status、package prefix、installed 文件、PID/cmdline |
| ROS/MoveIt | node、参数、service/action、plan 是否正确？ | node list、dotted params、MoveIt error code、trajectory points |
| Controller/feedback | goal 被谁接收，执行结果和真实关节是否变化？ | controller state、action info/result、`/joint_states` 前后、TF 前后 |
| Gazebo physics | 机器人/物体在物理世界中实际发生了什么？ | 物体 world pose、support/gripper contact、`/task_object/contacts`、reset state，以及是否出现 unexpected Gazebo attachment |
| Planning Scene | 碰撞世界与 attached object 是否同步？ | world/attached membership、attached link/touch links、pose |
| Visual | 人看到的场景是否符合目标？ | 本轮之后的新 Gazebo/RViz screenshot 或 CUA snapshot |

只检查与当前假设有关的层，但完成声明必须覆盖所有受影响层。

## 建立干净复现

1. 记录当前相关 PID、tmux session、ROS nodes、`GZ_PARTITION` 和 `ROS_DOMAIN_ID`。
2. 优先复用用户指定 stack；若需全新 stack，先确认不会影响既有进程。
3. 日志写进本 task 已登记的唯一 evidence root（路径规则见 `SKILL.md` 的“证据根”一节），例如：

```bash
: "${SO101_EVIDENCE_ROOT:?先 export 本 task 已登记的唯一 evidence root}"
debug_dir="$SO101_EVIDENCE_ROOT/ros-logs"
mkdir -p "$debug_dir" || exit 1
export ROS_LOG_DIR="$debug_dir"
```

4. 记录完整 launch 命令与 stdout/stderr；退出码通过 shell/tmux 明确保留。使用唯一 `simulation_session_id` 和独立 checkpoint 路径；只有启动完全独立的一套 Gazebo 客户端/服务端时才设置新的 `GZ_PARTITION`，连接既有 stack 时必须沿用其 partition。

## 高价值只读检查

先确认没有重复 stack，再看控制器和 action：

```bash
ros2 node list | sort
pgrep -af 'move_group|rviz2|gz sim|pick_place_state_machine'
ros2 control list_controllers
ros2 action list -t
ros2 action info /arm_controller/follow_joint_trajectory
```

关节、TF、物理接触、unexpected attachment 和 Planning Scene 都用边界清晰的一次性样本：

```bash
ros2 topic echo /joint_states --once
timeout 3 ros2 run tf2_ros tf2_echo '<base-link>' '<tcp-link>'
ros2 topic echo /task_object/contacts --once
gz topic -e -t /so101/object_attached -n 1
gz topic -i -t /so101/object_attached_event
ros2 run so101_gazebo_demo_cpp so101_moveit_scene observe
```

normal forward path 不该出现 Gazebo attachment，所以 `/so101/object_attached` 只用来发现 unexpected attach，不用来判断夹取是否成功；物理是否夹住要靠物体 world pose 和 contact。`so101_moveit_scene observe` 的合法子命令是 `observe|upsert|attach|detach`。link 名称必须从当前 URDF/SRDF 或 TF tree 获取，不从历史答案猜。命令或 topic 不存在时，先从 installed launch/config 和 `ros2 topic list -t`、`gz topic -l` 重新发现，不把缺少命令当成业务根因。

## 日志归属

同名 logger 可能来自不同进程。对关键 warning/error 记录日志文件绝对路径、PID、命令行、启动 tmux pane、同时间附近的前后日志，以及对应 ROS node 名称和是否有重名节点。例如 `No kinematics plugins defined` 必须先回答“哪个进程里的哪个 RobotModelLoader 发出”，再判断影响；不要把 `planning_scene_interface_*` logger 自动归为 `/move_group`。

## 根因门槛

可以写“根因已确认”的最低条件：

1. 竞争假设至少有一个被独立证据排除；
2. 变量 A 存在时稳定失败，移除或修正 A 后同一复现通过；
3. 变化首先出现在预期系统边界，而不是只在更下游的日志或画面；
4. 没有重复 stack、旧 binary、过期 screenshot 等替代解释。

否则分别写 `OBSERVED`（命令或画面直接看到的事实）、`INFERRED`（由多项事实支持、尚未 A/B 的推断）或 `HYPOTHESIS`（下一轮准备验证的解释）。

## 收敛规则

连续两轮没有新增区分性证据时，停止扩大搜索范围。输出当前证据矩阵、最大的未知项和下一条能解除阻塞的命令；不要继续无界浏览源码或重复相同日志。
