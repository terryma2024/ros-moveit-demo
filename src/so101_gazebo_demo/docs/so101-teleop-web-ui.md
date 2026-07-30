# SO-101 Teleop Web UI 操作手册

本文介绍如何在 ai-station 的 SO-101 仿真环境中启动和使用 Teleop Web UI。它面向日常姿态调试、MoveIt 规划、Gazebo 证据采集和 pick-place 状态机排障。

> **适用范围：仅仿真。** 服务端会拒绝非 loopback、非 Tailscale 网段的监听地址，但这不是实机安全系统。不要把本工具连接到真实机械臂。

## 1. 系统组成

Web UI 不直接控制 ROS。完整链路是：

```text
Mac 浏览器
  -> Tailscale HTTP/WebSocket
  -> ai-station FastAPI Teleop server
  -> ROS 2 / MoveIt 2 / controllers
  -> Gazebo
```

事实来源分工：

- Gazebo：杯子实际位姿、接触和物理 Attach/Detach。
- MoveIt Planning Scene：碰撞物体及 MoveIt Attach/Detach。
- `/joint_states` 与 TF：机械臂关节和 TCP 实际状态。
- 浏览器中的 Target：操作员准备提交的目标，不是实际状态。

## 2. 启动前检查

先确认 ai-station 上没有第二套 Gazebo、MoveIt 或 Teleop：

```bash
ssh ai-station
tmux list-sessions
pgrep -af 'gz sim|move_group|so101_teleop_server.py'
ss -ltnp | rg ':8000'
```

不要用宽泛的 `pkill -f ros` 或 `killall gz`。发现重复进程时，先确认 PID、父进程、`ROS_DOMAIN_ID` 和 `GZ_PARTITION`，只关闭已经证明属于旧实验的进程。

## 3. 构建与 Bun

安装 package 时执行：

```bash
cd /data/work/ws_moveit
source /opt/ros/jazzy/setup.zsh
colcon build --packages-select so101_gazebo_demo --symlink-install
source install/setup.zsh
ros2 pkg prefix so101_gazebo_demo
```

本项目统一使用 Bun，以 `bun.lock` 为唯一 Web 依赖锁文件：

```bash
command -v bun
bun --version
```

`ros2 pkg prefix` 应指向 `/data/work/ws_moveit/install` 下的 overlay。
`so101_teleop.launch.py` 会在 FastAPI 启动前检查 production bundle：新鲜时直接
跳过；缺失或比 `src/**`、package/lockfile、Vite/Tailwind/PostCSS/TypeScript
配置旧时自动构建。lockfile 指纹未变化时不会重复 `bun install --frozen-lockfile`。构建失败会阻止
server 启动，不能留下仅 API 可用、页面资源损坏的半启动状态。FastAPI 直接
提供验证后的 bundle；现场不需要、也不应保留常驻 Vite/Node server。

## 4. 启动 Gazebo 与 MoveIt

GUI 长进程必须由 tmux 持有，并从当前 GNOME 会话加载图形环境。先在一个
session 中启动 Gazebo：

```bash
tmux new -s so101-gazebo

source ~/gui-env.zsh
source /opt/ros/jazzy/setup.zsh
cd /data/work/ws_moveit
source install/setup.zsh

export ROS_DOMAIN_ID=55
export GZ_PARTITION=so101_teleop_live

ros2 launch so101_gazebo_demo so101_gazebo.launch.py \
  object_config:=/data/work/ws_moveit/src/so101_gazebo_demo/config/task_objects/light_plastic_cup.yaml \
  headless:=false
```

再在另一个 tmux session 中启动 MoveIt。它必须使用完全相同的 domain、
partition 和 object config：

```bash
tmux new -s so101-moveit

source ~/gui-env.zsh
source /opt/ros/jazzy/setup.zsh
cd /data/work/ws_moveit
source install/setup.zsh

export ROS_DOMAIN_ID=55
export GZ_PARTITION=so101_teleop_live

ros2 launch so101_gazebo_demo so101_move_group_headless.launch.py \
  object_config:=/data/work/ws_moveit/src/so101_gazebo_demo/config/task_objects/light_plastic_cup.yaml
```

`ROS_DOMAIN_ID` 和 `GZ_PARTITION` 可以更换，但 Teleop server 必须使用与这套仿真完全相同的值。

看到 Gazebo 场景、机械臂、杯子和控制器均已出现后，再启动 Teleop server。

## 5. 启动 Teleop server

另开一个 tmux session：

```bash
tmux new -s so101-teleop

source ~/gui-env.zsh
source /opt/ros/jazzy/setup.zsh
cd /data/work/ws_moveit
source install/setup.zsh

export ROS_DOMAIN_ID=55
export GZ_PARTITION=so101_teleop_live

tailscale ip -4
```

记下 ai-station 的 Tailscale IPv4，然后启动：

```bash
ros2 launch so101_gazebo_demo so101_teleop.launch.py \
  bind_address:=<ai-station-tailscale-ip> \
  port:=8000 \
  simulation_session_id:=teleop-$(date +%Y%m%d-%H%M%S)
```

这是 Teleop 的一键启动命令。默认 `build_web_if_needed:=true`。源码无法自动
发现时显式传入：

```bash
ros2 launch so101_gazebo_demo so101_teleop.launch.py \
  web_source_dir:=/data/work/ws_moveit/src/so101_gazebo_demo/web
```

可用 `SO101_TELEOP_BUN=/absolute/path/to/bun` 指定 Bun。只有在已存在完整 bundle 且希望禁止构建时才使用
`build_web_if_needed:=false`；入口或引用资产缺失/空文件仍会直接失败。失败时
先核对 Bun 版本、`web_source_dir`、Bun stderr 和磁盘空间，再重启同一命令，
不要另起 Vite server。

如果只在 ai-station 本机访问，可使用 `bind_address:=127.0.0.1`。截图功能依赖 `~/gui-env.zsh` 提供的当前桌面环境。

## 6. 从 Mac 打开界面

确保 Mac 与 ai-station 均已连接 Tailscale，然后访问：

```text
http://<ai-station-tailscale-ip>:8000
```

不要把服务暴露到公网，也不要使用普通局域网的 `0.0.0.0` 监听。

Tailscale 的 plain HTTP origin 不提供 `crypto.randomUUID`。前端会使用
`crypto.getRandomValues` 生成兼容 UUID；因此普通 HTTP 下命令仍具有唯一
command ID，不需要为了该 API 改成不受控的公网 HTTPS。

页面顶部应显示：

- `READY`：ROS、TF、控制器和遥测满足控制门槛。
- `simulation-only`：当前服务仅允许仿真。
- `session`：本轮仿真的唯一 session ID。
- `rev`：最新 snapshot revision。
- `RTT`：浏览器到服务端的往返时间。
- `RTF`：Gazebo Real Time Factor（实时因子）。明显过低意味着仿真执行和遥测会变慢。

页眉顺序固定为 **SO-101 Teleop → READY/mode → Acquire lease/Lease active →
动态 metadata**。标题、状态 Badge 和租约按钮组成稳定的操作区；session、rev、
RTT（以及显示时的 TTL）在其后的独立区域截断或换行。因此遥测数字变长或租约
倒计时更新不会推移租约按钮，窄屏也不会产生整页横向滚动。

如果不是 `READY`，先排查服务端和 ROS 环境，不要尝试用 Force Continue 绕过。

全局状态、notice、**Current to Target**、诊断下载和 RTF 始终显示在功能 Tabs
外。八个顶层 Tabs 为 **Joints / TCP / Collision / Target / Gazebo / Workflow /
Events / Environment**，默认 Joints；每次只显示选中面板。切换 Tabs 不会清除
target、plan、workflow 或断开 telemetry。窄屏可在 Tab 栏内部横向滚动，不应
出现整页横向滚动条。

### Environment

Environment 是只读运行环境面板，用于确认浏览器正在观察哪一套 ROS/Gazebo
通信域。它只显示服务端明确允许的以下键，不会枚举完整进程环境，也不会显示
token、密码等其他变量：

- ROS：`ROS_DOMAIN_ID`、`ROS_DISTRO`、`ROS_VERSION`、
  `ROS_PYTHON_VERSION`、`ROS_AUTOMATIC_DISCOVERY_RANGE`、
  `AMENT_PREFIX_PATH`、`COLCON_PREFIX_PATH`；
- Gazebo 与运行时：`GZ_PARTITION`、`GZ_CONFIG_PATH`、
  `GZ_SIM_RESOURCE_PATH`、`GZ_SIM_SYSTEM_PLUGIN_PATH`、`PYTHONPATH`、
  `LD_LIBRARY_PATH`。

未设置的变量显示 `—`。长值在表格内部换行，**Copy** 复制未经截断的完整值。
`ROS_DOMAIN_ID` 和 `GZ_PARTITION` 仅在 Environment Tab 显示，避免页眉动态
metadata 过长；执行命令前可打开该 Tab 核对通信域。

## 7. 控制租约（Lease）

所有会改变仿真状态的操作都需要租约：

1. 点击 **Acquire lease**。
2. 成功后按钮显示 **Lease active**。
3. 浏览器每 10 秒自动续租；服务端租约有效期为 30 秒。合法续租独立于耗时的
   workflow/MoveIt 命令序列化，因此运行中的长命令不会把续租误拒绝为
   `SERVER_BUSY`。
4. 同一时间只有一个操作员能持有租约。

页面刷新、连接中断、Reset 或 session 变化后，旧租约可能失效。重新点击 **Acquire lease** 即可。

## 8. 推荐的安全操作顺序

每次手动调试建议使用：

```text
确认 READY
  -> Acquire lease
  -> Current to Target
  -> 修改一个最小目标
  -> Plan
  -> 检查碰撞、接触和事件日志
  -> Execute
  -> 等待实际状态稳定
  -> Capture Gazebo window
```

**Current to Target** 会把最新实际关节和 TCP 复制到 Target，并清除旧 plan。开始新动作前先点一次，可以避免基于过期目标继续累积偏移。

## 9. Joint actual / target

该面板用于关节空间调试：

- Joint 1–5：MoveIt 手臂关节。
- Joint 6：夹爪开合，由 gripper controller 单独执行。
- `Actual °`：ROS 反馈的实际角度。
- `Velocity °/s`：实际关节速度。
- `Target °`：准备规划或执行的目标。
- `−1° / +1°`：每次修改 1°，只改变 Target。

按钮含义：

- **Plan Arm**：只为 Joint 1–5 生成候选轨迹；机械臂不会运动。
- **Execute Arm**：执行最近一次仍然有效的手臂轨迹。
- **Execute gripper**：只把 Joint 6 的 Target 发送给夹爪控制器。
- **Execute All**：先执行已有手臂轨迹；只有手臂执行成功才继续执行 Joint 6。
- **Cancel**：请求取消当前 MoveIt 执行动作。

修改任何 Target 后，旧 plan 会显示 `PLAN_STALE_TARGET` 并禁用执行。重新 Plan 后才能 Execute。
每个关节的 Safe range 来自服务端权威 hard limit，两端统一内缩 2°。直接输入、±1° 和 YAML 导入都会截断到该范围并显示反馈；遥测没有有效 limit 时对应编辑器禁用。

## 10. TCP Pose6D actual / target

TCP = Tool Center Point（工具中心点）。该面板使用 6D Pose：

- `x_m / y_m / z_m`：位置，数值框单位是米。
- `roll_rad / pitch_rad / yaw_rad`：姿态；界面数值按度显示和编辑，内部转换为弧度。
- XYZ 步进按钮：每次 1 mm。
- RPY 步进按钮：每次 1°。

步进参考系：

- **World frame**：旋转采用前乘，XYZ 增量直接沿世界坐标轴组合。
- **Tool frame**：旋转采用后乘，XYZ 增量先由当前 Target TCP 姿态旋转到
  世界坐标再组合。例如 Tool Z +1 mm 会沿工具当前朝向移动，不一定等于
  世界 Z +1 mm。

两种模式都会归一化最终四元数；每次步进只组合到 Target，不会直接改写
Actual，也不会把连续 Euler 角加法误当成空间旋转。
两个 frame 按钮是连成一体的 segmented control；高亮项和 `aria-pressed=true`
共同表示当前模式，可用 Tab 聚焦后按 Enter/Space 操作。

按钮含义：

- **Plan TCP**：通过 MoveIt IK（Inverse Kinematics，逆运动学）和运动规划生成轨迹，不执行。IK 时限为 60 秒，等待期间按钮显示 **Planning TCP…** 并禁止重复提交。
- **Execute planned TCP**：执行仍然有效的 TCP plan。
- **Cancel TCP**：请求取消当前 MoveIt 执行。

TCP 调试建议每次只移动 1–3 mm 或旋转 1°，观察碰撞与实际位姿后再继续，不要一次输入大跨度目标。
本机械臂只有五个手臂自由度，不能满足所有六维 Pose6D 约束。`MOVEIT_IK_FAILED_-31` 表示该目标无 IK 解，属于 HTTP 409 目标冲突，不是服务停机。所有失败 API 响应都会在右上 toast 显示 machine code 和 message。

## 11. Collision、contact 与物理抓取证据

该面板同时显示两类不能互相替代的证据：

- **MoveIt collisions**：规划场景中的碰撞检测结果。
- **Gazebo contacts**：物理仿真中的真实接触对象、碰撞名称和深度。

顶部结构化摘要还包括：

- Cup X/Y/Z：Gazebo 中杯子的实际世界坐标，固定三位小数（m）。
- Arm/Gripper：controller 状态 Badge。
- Ages：固定顺序与三位小数（s）；超过范围显示 `>99.999 s`。

舍入值可通过 Tooltip/原生 title 查看精确原值。MoveIt/Gazebo 窗格固定高度、
同时可见且各自内部滚动；长对象名会截断而不会撑宽页面，Depth 统一显示 mm。

典型判断：

- MoveIt 无碰撞不等于 Gazebo 没有物理接触。
- Gazebo 有接触不等于抓取稳定，也不等于 MoveIt 已 Attach。
- 抓取验证应观察双侧指尖接触、杯子漂移、micro-lift 后杯子是否离开桌面，以及 TCP/杯子跟随关系。

## 12. Target YAML 与诊断快照

### Browser-only Target YAML

- **Download Target YAML**：把当前 Joint Target、TCP Target 和 World/Tool step frame 下载到 Mac。
- **Load Target YAML**：从 Mac 载入上述目标。

YAML 只包含可重放目标，不包含实际遥测，也不会在服务端写文件。载入 YAML 后仍必须重新 Acquire lease、Plan 和 Execute。

文件 schema 固定如下；关节与 TCP 数值使用内部单位 rad/m：

```yaml
version: 1
target:
  step_frame: WORLD  # WORLD 或 TOOL
  joints_rad:
    "1": 0.0
    "2": 0.0
    "3": 0.0
    "4": 0.0
    "5": 0.0
    "6": -0.04
  tcp:
    frame_id: world
    tcp_frame: so101_tcp
    x_m: 0.02
    y_m: -0.28
    z_m: 0.20
    roll_rad: 0.0
    pitch_rad: 0.0
    yaw_rad: 0.0
```

Actual telemetry、contacts、collisions、plan、workflow result 与 source ages
都不写入 Target YAML；这些观测由 diagnostic snapshot 单独导出。

### Download diagnostic snapshot

下载的 JSON 包含：

- 当前实际 snapshot；
- Target；
- plan 状态；
- workflow 状态；
- 浏览器事件日志。

它适合问题复现和报告，不应直接作为下一次执行目标导入。

## 13. Gazebo evidence and convergence

### Capture Gazebo window

截取 ai-station 当前唯一 Gazebo 窗口。成功后出现下载链接。若返回窗口不存在或窗口歧义：

- 确认 Gazebo GUI 已启动；
- 确认 Teleop server 的 tmux shell 加载了 `~/gui-env.zsh`；
- 确认没有多个 Gazebo GUI。

### Attach / Detach

这两个操作都有确认弹窗，并以 Gazebo 与 MoveIt 两层独立收敛作为事务提交
条件：

- Attach：Gazebo 建立物理约束，MoveIt 将杯子加入 attached collision object。
- Detach：Gazebo 解除物理约束，MoveIt 移除 attached object 并恢复场景状态。

任一层失败或超时，事务会执行与已产生副作用对应的 rollback，并再次读取
两层事实；只有最终状态一致才返回成功。`GAZEBO_ATTACHMENT_UNVERIFIED` 表示
未能证明收敛，此时不得把单层状态或 UI 文案当作成功。现场 Attach 还可能
造成杯子位置不连续；除非 disposable run 已获得明确授权，应使用事务测试
验收，不要为了截图现场 Attach。

只有在接触和物理抓取验证已经通过时才使用 Attach。不要用 Attach 掩盖“夹爪没有真正抓住杯子”。

### Repair scene

重新同步 MoveIt Planning Scene。它可能改变 scene revision，因此所有旧 plan 都应视为无效并重新规划。

### Home

将手臂和夹爪送回仿真 Home。Home 改变真实 start state，因此会使旧 plan 失效。

### Reset world / robot

调用 C++ reset owner 重置 world、机械臂和夹爪，并创建新的 simulation session。Reset 后：

- 旧 lease 失效；
- 旧 plan 失效；
- 旧 workflow/checkpoint 失效；
- 浏览器应提示 session changed。

Reset 完成后等待状态恢复为 `READY`，再依次执行 Acquire lease、Current to Target 和重新 Plan。

`Convergence: Gazebo ... · MoveIt ...` 用于观察两层 attachment 是否一致。两者不一致时不要继续搬运。

## 14. Checkpointed pick-place workflow

状态机拥有状态转移权，浏览器不能任意选择跳转到某个状态。

- **Start**：创建新的 workflow run/checkpoint，并执行第一个单步请求。
- **Next Step**：从当前 checkpoint 执行下一状态，适合逐状态调试。
- **Run**：从当前 checkpoint 连续执行。
- **Stop**：停止请求后续状态；它不是急停，也不等同于取消正在执行的 MoveIt action。
- **Resume**：从当前 checkpoint 继续。
- **Reset workflow**：使当前 workflow checkpoint 失效，不重置整个 Gazebo world。

逐步调试推荐流程：

1. Start。
2. 查看 `current_state -> next_state` 和 trace。
3. 查看 Gazebo、碰撞、接触、杯子位姿和 Event log。
4. 确认证据一致后点击 Next Step。
5. 在 Close 后的物理验证阶段，重点观察稳定等待、micro-lift、杯子离桌和跟随比例。

### Force Continue

Force Continue 只在 `VALIDATION_FAILED` 时出现，并要求输入：

```text
FORCE CONTINUE
```

它是单次、可审计的操作，仅允许越过新鲜的 physical-grasp post-validation failure。它不能绕过：

- 租约失效；
- 服务未 READY；
- session 不一致；
- checkpoint/plan 过期；
- action 或 controller 失败。

Force Continue 不代表抓取成功。使用前应下载 diagnostic snapshot、截取 Gazebo，并记录失败证据。

Workflow 命令发出后，当前按钮会显示 `Starting…`、`Stepping…`、`Running…`
等执行中状态，整个 workflow 操作组暂时禁用。只有服务端响应返回后按钮才恢复，
避免耗时状态边界被重复提交；失败 code 仍由全局 toast 和 Event log 显示。

## 15. Event log

Event log 最多保留浏览器本次会话最近 100 条命令，包含时间、操作、code 和 message。排障时先找首个非 `OK` 记录，而不是只看最后一个失败。

常见 code：

| Code | 含义与处理 |
|---|---|
| `READINESS_NOT_SATISFIED` | ROS、TF、controller 或遥测不新鲜；先修复运行环境。 |
| `LEASE_REQUIRED` | 没有有效租约；重新 Acquire lease。 |
| `LEASE_BUSY` | 另一个浏览器持有租约；不要并发操作。 |
| `SESSION_MISMATCH` | 仿真已经 Reset/重启；重新获取状态、租约和 plan。 |
| `PLAN_STALE_TARGET` | Target 在 Plan 后被修改；重新 Plan。 |
| `PLAN_STALE_START` | 实际关节 start state 已变化；Current to Target 后重新 Plan。 |
| `PLAN_STALE_SCENE` | Planning Scene 已变化；检查场景后重新 Plan。 |
| `PLAN_EXPIRED` / `PLAN_NOT_FOUND` | plan 已过期、执行或清除；重新 Plan。 |
| `MOVEIT_IK_FAILED_*` | TCP 目标不可达或姿态不合理；缩小步长或调整姿态。 |
| `PLAN_COLLISION` | 候选路径存在碰撞；检查碰撞对象和目标。 |
| `GAZEBO_ATTACHMENT_UNVERIFIED` | Gazebo attachment 没有在时限内收敛；不要继续 Lift。 |
| `WORKFLOW_RUN_MISMATCH` / `CHECKPOINT_STALE` | workflow 已重置或 session 改变；重新 Start。 |
| `SERVER_BUSY` | 另一条变更命令仍在执行；等待其结束。 |
| `CONFIRMATION_REQUIRED` | 服务端未收到正确的二次确认；从界面确认弹窗执行。 |

## 16. 典型调试任务

### 调 TCP 的 MOVE_ABOVE / DESCEND

1. READY、Acquire lease、Current to Target。
2. 选择 World frame 或 Tool frame。
3. 单次调整 XYZ 1 mm，Plan TCP。
4. 检查 MoveIt collisions。
5. Execute planned TCP。
6. 等待速度接近 0，检查 TCP、杯子位姿和 Gazebo contacts。
7. Capture Gazebo window。

### 验证物理抓取而不是 Attach 假成功

1. Close gripper 后等待接触稳定。
2. 检查两个指尖是否分别接触同一杯壁区域，且接触深度在策略允许范围内。
3. TCP micro-lift 1 mm。
4. 等待稳定，检查杯底是否离开桌面、杯子是否随 TCP 上升、XY 漂移是否可接受。
5. 物理验证通过后再 Attach，供后续任务级规划使用。

## 17. 结束与清理

结束本轮实验时：

1. 下载必要的 Target YAML、diagnostic snapshot 和 Gazebo PNG。
2. 记录当前 session ID 和 Event log 中首个失败 code。
3. 只停止本轮明确使用的 Teleop、Chrome 和仿真 tmux session。
4. 再次检查相关 PID 和 8000 listener，确认没有遗留第二套 stack。

不要删除源码目录中的用户改动，也不要使用 `git clean` 清理工作区。
