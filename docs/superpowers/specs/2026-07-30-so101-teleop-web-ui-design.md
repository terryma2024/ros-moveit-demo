# SO-101 Teleop Web UI 设计

## 1. 背景与目标

SO-101 Gazebo 抓取调试目前依赖命令行、临时 YAML、远程桌面和分散的状态查询。微调关节或 TCP 后，需要在多个工具之间切换才能规划、执行、观察碰撞并保存参数，容易混淆实际状态、编辑目标和历史 plan。

本功能提供一个仅面向 Gazebo 仿真的远程调试工作台：

- ai-station 运行 Python FastAPI + ROS 2 server；
- 用户在 Mac 浏览器中通过 ai-station 的 Tailscale IP 访问；
- Web UI 使用 React、TypeScript、Vite 和 shadcn/ui；
- 实时显示六关节、TCP Pose6D、碰撞、物体和 controller 状态；
- 支持关节/TCP 微调、Plan、Execute、Attach、Detach、Home、Reset；
- 支持正式 pick-place 状态机的单步执行、物理抓取验证和可审计的仿真强制继续；
- 支持只截取 Gazebo 窗口及保存本地 YAML 参数快照。

第一版明确不支持真实机械臂。强制继续仅用于 Gazebo 调试，并被限制在显式的 validation override；不能绕过控制权、数据新鲜度、ROS/Gazebo/MoveIt readiness、命令互斥、执行器错误或陈旧 checkpoint。

## 2. 已确认的产品决策

| 项目 | 决策 |
|---|---|
| 运行范围 | 仅 Gazebo 仿真 |
| 网络 | FastAPI 绑定 ai-station 明确配置的 Tailscale IP |
| 后端 | Python、FastAPI、rclpy |
| 前端 | React、TypeScript、Vite、shadcn/ui |
| shadcn preset | `bKsFBxgG` |
| 部署 | Vite SPA 构建产物，由 FastAPI 单进程托管 |
| 实时通道 | REST 命令 + WebSocket telemetry |
| TCP 步进 | World/Tool 两种坐标系 |
| 关节步长 | 每步 1 degree |
| TCP XYZ 步长 | 每步 1 mm |
| TCP RPY 步长 | 每步 1 degree |
| 参数保存 | 浏览器下载/加载 Mac 本地 YAML |
| arm/gripper | joints 1-5 与 q6 分开执行，Execute All 顺序执行 |
| pick-place | 复用现有 C++ 状态机及 checkpoint，支持 Next Step、Run、Pause/Stop、Reset Workflow |
| 抓取验证 | Close 后稳定，Micro Lift 1 mm，再验证杯子离桌、跟随率和滑移，通过后才 Attach |
| 强制继续 | 仅仿真、仅覆盖当前状态的 validation failure、要求二次确认并保留审计证据 |

## 3. 总体架构

```text
Mac Browser
  React + Vite static Web UI
       | REST + WebSocket over Tailscale
       v
ai-station so101_teleop_server
  FastAPI event loop
       | command queue / immutable snapshots
       v
  ROS worker thread (rclpy executor)
       |
       +-- MoveIt IK / planning / state validity / execution
       +-- arm and gripper controllers
       +-- TF and joint states
       +-- Planning Scene
       +-- Gazebo object pose / contacts / attachment
       +-- Gazebo X11 window screenshot
```

### 3.1 单进程服务

FastAPI 同时提供：

- Vite SPA 构建产物；
- REST API；
- WebSocket telemetry；
- OpenAPI schema；
- Gazebo PNG 截图响应。

前端构建为纯静态 SPA。FastAPI 对前端路由提供 `index.html` fallback，并从 fallback 中排除 REST 和 WebSocket 路径。ai-station 不运行常驻 Node server。

### 3.2 并发边界

服务端分成三个边界：

1. ROS worker thread：唯一持有 `rclpy` executor、TF buffer、publishers、service/action clients；
2. FastAPI event loop：负责网络请求与 WebSocket，不直接调用 ROS；
3. command queue：串行执行所有会改变仿真状态的命令。

Plan、Execute、pick-place Step/Run、Attach、Detach、Home、Reset 和 Repair 不能并发。读取 telemetry 和截图不获取写锁，但截图必须在 Gazebo 窗口唯一且可见时执行。

## 4. 网络与控制权

- server 必须显式配置 bind address；拒绝以 `0.0.0.0` 启动；
- 预期 bind address 为 ai-station 的 Tailscale IP；
- 允许多个只读客户端查看状态；
- 同一时刻只有一个客户端持有 control lease；
- control lease 需要周期续租，过期后动作按钮失效；
- 每个改变状态的请求携带 `command_id`，重复请求不重复执行动作；
- WebSocket 断开后，浏览器立即禁用动作；若正在 Execute，server watchdog 请求 Cancel；
- Cancel 后保留当前仿真姿态，不自动 Reset。

## 5. 服务端状态机

```text
STARTING -> READ_ONLY -> READY -> BUSY
                         |        |
                         +------> DEGRADED
```

- `STARTING`：正在发现 ROS/Gazebo/MoveIt 能力；
- `READ_ONLY`：telemetry 可用，但仿真 controller、MoveIt 或 Gazebo 条件不完整；
- `READY`：允许 Plan 和改变仿真状态；
- `BUSY`：正在执行互斥命令；
- `DEGRADED`：Gazebo 与 Planning Scene 不一致、数据过期或 reset 不完整。

`DEGRADED` 状态只开放读取、Cancel、Reset Simulation 和 Repair Scene Sync。

server 只有在确认以下条件后才进入 `READY`：

- 当前是仿真环境；
- 只有目标 ROS/Gazebo stack；
- MoveIt services/actions 可用；
- arm 和 gripper controllers 均为 active；
- joint states 与 TF 新鲜；
- Gazebo world、对象和 Planning Scene 可查询。

## 6. 实时状态模型

### 6.1 Actual 与 Target 分离

- Actual 来自 ROS/Gazebo，只读并实时刷新；
- Target 是浏览器中的编辑状态；
- telemetry 更新不得覆盖 Target；
- `Current -> Target` 显式把 Actual 复制为 Target；
- 修改任一 Target 后立即使旧 plan 失效。

### 6.2 刷新频率

| 数据 | server 聚合推送频率 |
|---|---:|
| joints、TCP、controller | 10 Hz |
| Planning Scene、object pose、attachment | 5 Hz，操作后立即刷新 |
| MoveIt collision、Gazebo contact | 变化时立即推送，空闲时 5 Hz |
| real-time factor、网络延迟、数据年龄 | 2 Hz |

所有 telemetry 带 server 时间、simulation session ID、序列号和数据年龄。WebSocket 断开时 UI 冻结最后值并标记为 stale，不用旧值继续执行。

### 6.3 监视项

- joints 1-6：position、velocity、limit、controller；
- TCP：source frame、TCP frame、XYZ、quaternion、RPY；
- selected object：6D pose、stationary、Gazebo attached；
- Planning Scene：world/attached membership、attached link、touch links；
- MoveIt：current/target/trajectory collision；
- Gazebo：raw contact pairs、solver-reported depth、real-time factor；
- plan：ID、状态、耗时、预计轨迹时长、起点/场景是否过期；
- server：模式、control lease、网络 RTT、最近错误。

## 7. 关节与 TCP 控制

### 7.1 六关节

- joints 1-5 属于 arm controller；
- q6 属于 gripper controller；
- 每个关节显示 Actual 与 Target；
- UI 同时显示 degree 与 radian，编辑主单位为 degree；
- `-1 degree` / `+1 degree` 为固定步长；
- 超出 joint limit 时 Target 标记无效，Plan/Execute 禁用。

操作：

- `Plan Joint Target`：只规划 joints 1-5；
- `Execute Latest Plan`：只执行已验证的 arm plan；
- `Execute Gripper`：单独执行 q6；
- `Execute All`：先执行 arm plan，确认到位后再执行 q6，不并发。

### 7.2 TCP Pose6D

- 显示 Actual 与 Target XYZ/RPY；
- XYZ 编辑主单位为 mm，每步 1 mm；
- RPY 编辑主单位为 degree，每步 1 degree；
- 目标明确显示 source frame 与 TCP frame；
- 支持 World/Tool 两种步进坐标系，默认 World；
- World 模式沿世界坐标轴增量；
- Tool 模式沿当前 TCP 局部坐标轴增量；
- RPY/quaternion 转换必须规范化，并处理角度 wrap。

`Plan TCP Target` 先调用 IK，再把 IK 解送入与 joint target 相同的规划、轨迹碰撞检查和执行路径。IK 不可达、超限、跳变或碰撞时不产生可执行 plan。

## 8. Plan 生命周期与执行门控

Plan 保存在 server 内存中，客户端不能上传轨迹。Plan 响应包含：

- `plan_id`；
- 起始 joint fingerprint；
- target fingerprint；
- Planning Scene revision；
- IK 结果（TCP 模式）；
- 轨迹点数、预计时长、最大关节变化；
- current/target/trajectory collision 结果；
- 创建和过期时间。

以下任一事件使 plan 过期：

- Target 改变；
- Reset、Attach、Detach 或 Repair；
- Planning Scene revision 改变；
- 实际关节偏离计划起点超过阈值；
- plan 超时；
- control lease 转移；
- telemetry 过期。

普通 Execute 只接受 server 中最新、未过期、无禁止碰撞的 plan。

`Force Continue` 不等同于无条件执行任意轨迹。它只适用于 pick-place 当前状态已经完成动作、但后置 validation 返回失败的情形。用户必须看到失败 code、证据值和预期阈值，输入确认并二次确认后，server 才能为该状态提交一次性 override。override 与 `command_id`、workflow run ID、状态、snapshot revision、失败证据和时间戳一起写入事件日志；进入下一状态后立即失效。以下条件永远不可 override：

- control lease 缺失或已经转移；
- telemetry、checkpoint 或 simulation session 陈旧；
- Gazebo、MoveIt、controller 或 ROS action/service 不可用；
- 当前有其他 mutation 命令；
- 动作本身失败、Cancel 或执行器报错；
- 请求跳过状态或复用其他状态的 override。

## 9. 碰撞与接触显示

界面必须分开显示三类 MoveIt 碰撞和 Gazebo contact：

1. Current collision：实际 joint state 的 state validity；
2. Target collision：编辑目标或 IK 解的 state validity；
3. Trajectory collision：规划轨迹的首次无效 waypoint、对象/link pair；
4. Gazebo contact：物理引擎实际报告的 collision pair 与 depth。

MoveIt collision 与 Gazebo contact 不合并为一个结论。Gazebo depth 标为 `solver-reported`，避免将 speculative manifold 自动解释为精确网格穿透。

碰撞表至少显示：

- source；
- object/link A；
- object/link B；
- allowed/forbidden；
- waypoint index（若适用）；
- depth（若数据源提供）；
- 首次/最近时间。

## 10. Attach、Detach 与场景修复

默认 selected object 为 `plastic_cup`。

### 10.0 物理抓取验证

正式抓取主路径在 Attach 前增加以下状态：

```text
CLOSE_GRIPPER
  -> WAIT_GRASP_STABLE
  -> MICRO_LIFT
  -> WAIT_MICRO_LIFT_STABLE
  -> VERIFY_PHYSICAL_GRASP
  -> ATTACH_GAZEBO
  -> ATTACH_MOVEIT
  -> LIFT
```

`MICRO_LIFT` 默认命令 TCP 沿 world Z 上升 1 mm。两个稳定状态采用连续采样窗口，而不是固定 sleep；至少监视关节最大速度、杯子位置/姿态变化和样本年龄。`VERIFY_PHYSICAL_GRASP` 至少报告：

- 杯底相对桌面的净间隙；
- TCP 与杯子的 Z 位移及 cup-follow ratio；
- 杯子 XY 滑移；
- 杯子姿态变化；
- 夹爪与杯子的 Gazebo contact pair；
- 每项阈值、实测值和 PASS/FAIL。

只有普通验证 PASS，或用户对该状态提交一次性 Force Continue 后，才进入 Attach。Attach 的定位是把已经通过物理验证的抓取转成任务级约束，而不是代替抓取。

### 10.1 Attach Object

1. 验证 object 未 attached、telemetry 新鲜和当前状态允许 attach；
2. 保存操作前 Gazebo 与 MoveIt snapshot；
3. Gazebo attach；
4. 验证 Gazebo attachment；
5. MoveIt attach；
6. 验证 world/attached membership、attached link 和 touch links。

MoveIt attach 失败且 Gazebo attach 已成功时，有限回滚 Gazebo attachment，并报告各层最终状态。

### 10.2 Detach Object

1. Gazebo detach；
2. 验证 detached 并等待对象稳定；
3. 读取最终 Gazebo 6D pose；
4. MoveIt detach；
5. 使用最终 Gazebo pose 恢复 Planning Scene world object；
6. 验证两侧收敛。

### 10.3 Repair Scene Sync

以 Gazebo object pose/physical attachment 为物理事实源，以 MoveIt world/attached membership 为规划事实源。Repair 根据显式规则恢复一致，不隐藏部分失败。

主界面只提供高层 Attach/Detach。单独操作 Gazebo 或 MoveIt 的底层命令仅位于 Advanced Diagnostics，且要求二次确认。

### 10.4 Pick-place 单步控制

Web UI 直接驱动现有 C++ pick-place 状态机及其 checkpoint，不复制一套前端状态转换表。界面提供：

- `Start New Workflow`：创建绑定 simulation session 的 run ID；
- `Next Step`：只执行 checkpoint 指定的下一个合法状态；
- `Run`：连续执行，每个 validation gate 都评估并报告，失败时停止；
- `Pause/Stop`：请求取消当前 motion，并保留可验证 checkpoint；
- `Reset Workflow`：仅重置 workflow/checkpoint，不重置 world；
- `Force Continue`：仅在当前状态为 `VALIDATION_FAILED` 时出现。

状态面板显示当前状态、上一个完成状态、下一状态、完整 trace、checkpoint/session 匹配、动作结果、validation 证据和 override 审计记录。浏览器不能任意指定要执行的状态，也不能倒序或跳步。

## 11. Home 与 Reset

### 11.1 Home Robot

- 通过 MoveIt 规划到 canonical home；
- 保留 world objects 当前 pose；
- 如果碰撞或接触导致无法规划，明确失败；
- 不传送机器人，不降级为 Gazebo teleport。

### 11.2 Reset Simulation

Reset 是仿真专用的确定性重置事务：

1. 二次确认；
2. Cancel 当前动作并清除 plan；
3. 重置 Gazebo world；
4. 重置 joints 1-6 与 controllers；
5. 重置杯子及其他 task objects；
6. 清除 Gazebo attachment；
7. 重建 Planning Scene；
8. 清除 MoveIt attached objects，恢复 world objects；
9. 验证 joints、TCP、object poses、controller、Gazebo attachment 和 MoveIt membership。

任一层未收敛时返回 `RESET_INCOMPLETE`，server 进入 `DEGRADED`，不报告成功。

## 12. Gazebo 截图

- `Screenshot Gazebo` 由 server 在当前 GNOME/X11 session 查找 Gazebo 窗口；
- 只截取 Gazebo 窗口区域，不截桌面、RViz 或终端；
- 找不到窗口或发现多个无法区分的 Gazebo 窗口时失败，不猜测；
- 响应为 PNG，并携带 server 时间、窗口几何和 simulation session ID；
- UI 显示最新缩略图并允许下载原始 PNG；
- 可选自动刷新只按低频定时请求截图，不作为 telemetry 视频流。

## 13. 参数与诊断记录

### 13.1 Target YAML

浏览器下载/加载 Mac 本地 YAML，不由 server 持久保存。内容包括：

- schema version；
- joints 1-6 target；
- TCP Pose6D target；
- source/TCP frames；
- World/Tool 模式；
- 步长；
- server endpoint；
- robot/model/config fingerprint；
- 备注与保存时间。

实时 telemetry、碰撞状态和 plan 结果不混进可重新执行的 Target YAML。

### 13.2 Diagnostic Snapshot

可选下载独立诊断 JSON/YAML，包含：

- 当前 telemetry snapshot；
- collision/contact；
- plan 摘要；
- controller 与 scene 状态；
- 最近结构化错误；
- Gazebo screenshot 引用。

## 14. Web UI

### 14.1 技术与样式

- React SPA；
- TypeScript；
- Vite；
- shadcn/ui；
- preset `bKsFBxgG`；
- 静态构建并由 FastAPI 托管；
- 使用 preset semantic tokens，不硬编码状态颜色和字体。

初始化和组件安装必须使用 shadcn CLI。preset code 直接交给 CLI 解析，不手工解码或构造 URL。

新建前端时使用 Vite template 和已确认 preset：

```bash
npx shadcn@latest init --name web --preset bKsFBxgG --template vite
```

### 14.2 页面布局

- Header：连接、server 状态、control lease、session、RTF、staleness、Stop；
- 左侧 Tabs：Joints、TCP、Objects；
- 中间：Gazebo screenshot、Plan 摘要、Plan/Execute 操作、pick-place 状态机单步控制；
- 右侧：MoveIt collisions、Gazebo contacts、controller、scene 和 attachment；
- 底部：Home、Reset、Save/Load、Diagnostic Snapshot、结构化事件日志。

### 14.3 shadcn 组件映射

- `Card`：监视和控制分区；
- `FieldGroup` / `Field`：目标参数表单；
- `ToggleGroup`：World/Tool 与有限选项；
- `Tabs`：Joints/TCP/Objects；
- `Table`：collision/contact；
- `Badge`：状态；
- `Alert`：scene mismatch、stale data、expired plan；
- `AlertDialog`：Execute、Attach/Detach、Reset 确认；Force Continue 显示 validation 失败证据并要求输入确认；
- `Sonner`：命令结果；
- `Skeleton`：初始 telemetry 和截图加载；
- `Collapsible` / `ScrollArea`：Advanced Diagnostics 和事件日志。

Actual 与 Target 必须视觉分离；动作按钮的 disabled 原因必须可见，不能只显示灰色按钮。

## 15. REST 与 WebSocket 接口

```text
GET  /health
GET  /capabilities
GET  /snapshot
WS   /telemetry

POST /control/lease
POST /control/lease/renew
POST /plan/joints
POST /plan/tcp
POST /plans/{plan_id}/execute
POST /gripper/execute
POST /execution/cancel

POST /workflow/start
POST /workflow/step
POST /workflow/run
POST /workflow/stop
POST /workflow/reset
POST /workflow/force-continue

POST /attachment/attach
POST /attachment/detach
POST /scene/repair

POST /robot/home
POST /simulation/reset
POST /gazebo/screenshot
```

错误响应使用稳定的 machine-readable code、human-readable message、受影响层和当前 snapshot revision。HTTP success 不代表机器人动作成功；动作结果必须包含 ROS action/service 最终状态和验证结果。

## 16. 测试策略

### 16.1 纯逻辑单元测试

- 1 degree / 1 mm 步进；
- World/Tool transform；
- RPY/quaternion 转换、规范化和 wrap；
- joint limit；
- telemetry freshness；
- plan fingerprint 与失效；
- command idempotency；
- Pydantic/TypeScript schema compatibility。

### 16.2 server contract 测试

使用 fake ROS ports 验证：

- readiness gate；
- command serialization；
- control lease；
- disconnect cancel；
- attach/detach 顺序和回滚；
- reset 收敛与 `RESET_INCOMPLETE`；
- screenshot 窗口唯一性；
- collision source 不混淆。
- workflow 合法状态转换、单步 checkpoint 和禁止跳步；
- 稳定窗口、1 mm micro-lift 和 physical-grasp 指标；
- validation override 的允许边界、一次性消费和审计记录；

### 16.3 headless 集成测试

- joint target plan/execute；
- TCP IK/plan/execute；
- gripper execute；
- stale plan rejection；
- current/target/trajectory collision names；
- cancel；
- attach/detach；
- simulation reset。
- pick-place Next Step/Run/Stop/Resume；
- physical grasp PASS 后 Attach；
- validation FAIL 时普通路径停止，确认后的 override 仅继续一次；

### 16.4 Web UI 测试

- Actual/Target 分离；
- WebSocket 断线与 stale 状态；
- Target 修改使 plan 失效；
- disabled reason；
- YAML download/upload round-trip；
- confirmation dialogs；
- collision/contact 分栏；
- screenshot 展示和下载。
- 状态 trace、Next Step、Run/Stop 和 workflow reset；
- Force Continue 只在 validation failure 时可见，显示证据并二次确认。

### 16.5 ai-station 视觉验收

- 浏览器与 Gazebo 同时观察；
- 六关节和 TCP 数值随 Gazebo 同步；
- joints 每步 1 degree；
- TCP XYZ 每步 1 mm、RPY 每步 1 degree；
- World/Tool 方向与预期一致；
- Plan 与 Execute 结果和画面一致；
- screenshot 只含 Gazebo；
- collision 显示具体双方名称；
- Attach/Detach、Home、Reset 的数值状态和画面一致。
- Close 后稳定、Micro Lift 1 mm、物理抓取指标和 Attach 顺序一致；
- 单步与连续运行使用同一状态机 trace；强制继续被醒目标记且日志可追溯。

## 17. 完成标准

只有满足以下条件才可宣布第一版完成：

- Mac 浏览器可通过 Tailscale IP 打开 UI，不安装 ROS；
- server 不在非指定接口监听；
- 仿真缺失时 Execute 不可用；
- 六关节和 TCP Actual 实时刷新且不覆盖 Target；
- joint/TCP Plan、arm Execute 和 q6 Execute 可用；
- latest-plan 与 scene/joint staleness 门控生效；
- collision/contact 能显示对象/link 名称和数据源；
- Attach/Detach、Repair、Home、Reset 通过对应分层验证；
- pick-place 可单步执行，checkpoint/session 防止跳步和误续跑；
- 物理抓取验证位于 Attach 之前，报告桌面间隙、跟随率和滑移；
- validation override 只在仿真和明确边界内生效，并留下完整审计记录；
- Gazebo screenshot 只截取目标窗口；
- Target YAML 能在浏览器下载并重新加载；
- 自动测试通过，并有本轮 ai-station 运行日志和新鲜视觉证据；
- 没有遗留第二套 Gazebo/MoveIt/server 进程。

## 18. 非目标

第一版不包含：

- 真实机械臂控制；
- 多机器人/多 world；
- 浏览器内 3D 渲染或 RViz 替代品；
- 实时视频流；
- 轨迹编辑器；
- 自定义碰撞放行；
- 任意轨迹的 force execute，或绕过 readiness/lease/action failure；
- 云端账户、权限或数据库；
- server 端持久保存用户 Target YAML。
