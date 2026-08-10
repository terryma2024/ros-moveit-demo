# 分层证据与根因定位

## 导航

- [先写竞争假设](#先写竞争假设)
- [六层证据](#六层证据)
- [建立干净复现](#建立干净复现)
- [高价值只读检查](#高价值只读检查)
- [日志归属](#日志归属)
- [根因门槛](#根因门槛)
- [收敛规则](#收敛规则)

## 先写竞争假设

不要从症状直接跳到修改。每轮写 2–3 个可区分的假设，并选择成本最低、信息增益最大的命令。

示例：状态机输出 `DONE`，但 Coke 画面未移动。

| 假设 | 能证伪它的证据 |
|---|---|
| 状态机使用 dry-run executor | 运行参数、启动命令和 runtime registration |
| Gazebo attach 未发生 | `/so101/coke_attached` 前后样本和 Coke 6D pose |
| 物理发生但截图过期/看错会话 | 本轮时间戳的新截图与进程/session 对齐 |

先运行能把三者分开的检查，不要先改 transition table。

## 六层证据

| 层 | 要回答的问题 | 典型证据 |
|---|---|---|
| Provenance | 哪份源码、配置和 binary 在运行？ | commit/status、package prefix、installed 文件、PID/cmdline |
| ROS/MoveIt | node、参数、service/action、plan 是否正确？ | node list、dotted params、MoveIt error code、trajectory points |
| Controller/feedback | goal 被谁接收，执行结果和真实关节是否变化？ | controller state、action info/result、`/joint_states` 前后、TF 前后 |
| Gazebo physics | 机器人/物体在物理世界中实际发生了什么？ | attachment state、contact、Coke world pose、reset state |
| Planning Scene | 碰撞世界与 attached object 是否同步？ | world/attached membership、attached link/touch links、pose |
| Visual | 人看到的场景是否符合目标？ | 本轮之后的新 Gazebo/RViz screenshot 或 CUA snapshot |

只检查与当前假设有关的层，但完成声明必须覆盖所有受影响层。

## 建立干净复现

1. 记录当前相关 PID、tmux session、ROS nodes、`GZ_PARTITION` 和 `ROS_DOMAIN_ID`。
2. 优先复用用户指定 stack；若需全新 stack，先确认不会影响既有进程。
3. 为本轮设置唯一日志目录，例如：

```bash
debug_dir=/tmp/so101-debug-$(date +%Y%m%d-%H%M%S)
mkdir -p "$debug_dir"
export ROS_LOG_DIR="$debug_dir/ros"
```

4. 记录完整 launch 命令与 stdout/stderr；退出码通过 shell/tmux 明确保留。
5. 使用唯一 `simulation_session_id` 和独立 checkpoint 路径。只有启动完全独立的一套 Gazebo 客户端/服务端时才设置新的 `GZ_PARTITION`；连接既有 stack 时必须沿用其 partition。

## 高价值只读检查

先确认没有重复 stack：

```bash
ros2 node list | sort
pgrep -af 'move_group|rviz2|gz sim|pick_place_state_machine'
```

控制器和 action：

```bash
ros2 control list_controllers
ros2 action list -t
ros2 action info /arm_controller/follow_joint_trajectory
```

关节和 TF 用边界清晰的一次性样本：

```bash
ros2 topic echo /joint_states --once
timeout 3 ros2 run tf2_ros tf2_echo <base-link> <tcp-link>
```

link 名称必须从当前 URDF/SRDF 或 TF tree 获取，不从历史答案猜。

Gazebo attachment 的当前 package 约定可先检查：

```bash
gz topic -e -t /so101/coke_attached -n 1
gz topic -i -t /so101/coke_attached_event
ros2 topic echo /coke/contacts --once
```

Planning Scene 可使用已安装的观察 CLI：

```bash
ros2 run so101_gazebo_demo_cpp so101_moveit_scene observe
```

命令或 topic 不存在时，先从 installed launch/config 和 `ros2 topic list -t` / `gz topic -l` 重新发现，不把缺少命令当成业务根因。

## 日志归属

同名 logger 可能来自不同进程。对关键 warning/error 记录：

- 日志文件绝对路径；
- PID、命令行和启动 tmux pane；
- 同一时间附近的前后日志；
- 对应 ROS node 名称与是否有重名节点。

例如 `No kinematics plugins defined` 必须先回答“哪个进程里的哪个 RobotModelLoader 发出”，再判断影响。不要把 `planning_scene_interface_*` logger 自动归为 `/move_group`。

## 根因门槛

可以写“根因已确认”的最低条件：

1. 竞争假设至少有一个被独立证据排除；
2. 变量 A 存在时稳定失败，移除或修正 A 后同一复现通过；
3. 变化首先出现在预期系统边界，而不是只在更下游的日志或画面；
4. 没有重复 stack、旧 binary、过期 screenshot 等替代解释。

否则分别写：

- `OBSERVED`：命令或画面直接看到的事实；
- `INFERRED`：由多项事实支持、尚未 A/B 的推断；
- `HYPOTHESIS`：下一轮准备验证的解释。

## 收敛规则

连续两轮没有新增区分性证据时，停止扩大搜索范围。输出当前证据矩阵、最大的未知项和下一条能解除阻塞的命令；不要继续无界浏览源码或重复相同日志。
