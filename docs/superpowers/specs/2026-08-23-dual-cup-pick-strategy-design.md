# SO-101 固定与感知 Cup Pick 双策略设计

**日期：** 2026-08-23
**状态：** 已批准实施边界；动态路径仅允许 `plan_only`，尚未获得 execute qualification
**源码基线：** `moveit-demo/main@e34bf2b8eea55c44b24b32ff6521887cad0abca4`

## 1. 背景

当前 Python package 同时具备两种尚未连通的能力：

- `cup_pose_subscriber` 可以持续订阅 `/cup_pose`，校验非空 `frame_id`、有限位置/四元数和非零四元数；
- `pick_place` 的 live 路径从完整 motion-policy YAML 读取固定 joint waypoints，后端按这些 waypoint 发送轨迹。

两者不能通过“替换 YAML 中的一个数”连通。`TaskPolicy.states[*].waypoints` 的值是预先为一个固定杯位求出的关节轨迹；外部 cup Pose 改变后，机器人必须重新求 IK 和轨迹。仅移动 Gazebo 或 Planning Scene 中的杯子也不会让固定关节轨迹跟随它。

本设计引入两个明确、可并存的 public executable：

```text
fixed_cup_pick_place   # V1：固定 cup 位、固定 joint waypoint
dynamic_cup_pick_place # V2：/cup_pose 驱动的运行时 TCP 目标与规划
```

它们共享状态机的夹爪、物理 attachment、Planning Scene、恢复和证据规则，但不共享运动目标来源。V2 无有效感知输入时必须失败，禁止回退到 V1。

## 2. 目标、非目标与安全边界

### 2.1 目标

1. V1 在新名称 `fixed_cup_pick_place` 下保持现有固定 motion-policy 语义和结果。
2. V2 在 `dynamic_cup_pick_place` 启动状态机前读取一条合格 `/cup_pose`，冻结为本次运行输入。
3. V2 根据 cup Pose 和固定抓取几何生成 pregrasp、grasp、lift TCP 目标，由 MoveIt 在运行时规划。
4. V2 对无消息、坏输入、过期输入、TF 不可用、工作区越界、场景分叉和规划失败全部 fail-closed。
5. 每次运行记录 `strategy=fixed|dynamic`、静态模板 hash、输入 Pose、场景读回和规划证据，禁止混算两条路径的结果。

### 2.2 非目标

- 不改变 V1 的 YAML waypoint、夹爪值、接触阈值或已有 qualification 结论。
- 不在 V2 里实现“执行中目标持续移动”的视觉伺服；本设计只在状态机开始前获取并冻结 Pose。
- 不把动态路径的 `plan_only` 成功宣称为 Gazebo 或真实硬件 execute 成功。
- 不授权真实硬件；`real_stub` 继续 fail-closed。
- 不隐式移动 Gazebo/MuJoCo cup；场景写入必须是显式模式并且有读回。

## 3. 当前代码边界

| 位置 | 当前职责 | 设计处理 |
|---|---|---|
| `src/so101_demo_py/src/cli/cup_pose_subscriber.py` | ROS 2 持续监听与输入校验 | 保留为诊断 CLI；抽取无 ROS 的校验逻辑供 V2 复用 |
| `src/so101_demo_py/src/cli/pick_place.py` | ROS-free 固定策略入口 | 不直接引入 `rclpy`；迁移为 V1 内部实现 |
| `src/so101_demo_py/src/core/policy.py` | 严格加载固定 `states[*].waypoints` | 保留 schema v1；新增独立 dynamic template schema |
| `src/so101_demo_py/src/backends/gazebo/workflow.py` | 用 policy state 执行固定 waypoint | 保留为 V1；新增 V2 dynamic workflow |
| `src/so101_demo_py/src/ports/robot_control.py` | 定义 `TcpMotionRequest` 与规划/执行端口 | V2 的唯一运动规划接口 |

V2 不得修改 V1 的 `execute_gazebo_workflow()` 行为来实现“兼容”。两条路径的入口、motion provider 和 manifest 必须可区分。

## 4. 总体架构

```text
                                  ┌───────────────────────┐
fixed motion-policy YAML ───────►│ FixedMotionProvider     │
                                  │ joint waypoints         │
                                  └───────────┬───────────┘
                                              │
fixed_cup_pick_place ────────────────────────┼──► fixed workflow
                                              │
/cup_pose ─► ROS CupPoseSource ─► preflight ─┴──► DynamicMotionProvider
                 │                  │                TCP pose targets
                 │                  └─ scene/TF gate          │
dynamic_cup_pick_place ──────────────────────────────────────┴──► dynamic workflow
                                                                    │
                                     shared gripper / attach / scene / recovery / evidence
```

`fixed_cup_pick_place` 只创建固定 provider；`dynamic_cup_pick_place` 只创建动态 provider。它们不能因缺少参数、topic 或 policy 而互相切换。

## 5. 领域模型

### 5.1 感知输入

新增纯领域对象 `CupPoseSample`：

```python
@dataclass(frozen=True, slots=True)
class CupPoseSample:
    frame_id: str
    source_stamp_ns: int
    received_monotonic_s: float
    pose_world: Pose7
```

`Pose7` 是 `(x, y, z, qx, qy, qz, qw)`。输入必须已在规划 frame 中；V2 第一版的 planning frame 固定为 `world`。

接收器对每条消息执行现有有限数/非零四元数检查；无效消息记录后继续等候有效消息。第一条通过全部 preflight 的消息被冻结，后续 topic 消息不改变本次运行目标。

### 5.2 DynamicPickTemplate

`DynamicPickTemplate` 表示稳定、经版本控制的“如何抓”，不表示“杯子在哪里”：

```python
@dataclass(frozen=True, slots=True)
class DynamicPickTemplate:
    planning_frame: str
    cup_to_tcp_grasp: Pose7
    pregrasp_world_z_clearance_m: float
    lift_world_z_clearance_m: float
    workspace_bounds_m: tuple[float, float, float, float, float, float]
    maximum_source_age_s: float
    planning_timeout_s: float
    velocity_scaling: float
    acceleration_scaling: float
```

它保留 cup-to-gripper 相对抓取姿态、预抓取/抬升高度和安全约束。它不得包含 cup 的固定 world Pose、固定抓取 joint waypoint 或运行期消息。

### 5.3 DynamicPickPlan

```python
@dataclass(frozen=True, slots=True)
class DynamicPickPlan:
    input_pose: CupPoseSample
    pregrasp_tcp_world: Pose7
    grasp_tcp_world: Pose7
    lift_tcp_world: Pose7
```

计算规则：

```text
T_world_tcp_grasp    = T_world_cup × T_cup_tcp_grasp
T_world_tcp_pregrasp = Translate(world_z, pregrasp_clearance) × T_world_tcp_grasp
T_world_tcp_lift     = Translate(world_z, lift_clearance) × T_world_tcp_grasp
```

四元数必须按刚体变换合成并正规化；不得把 cup 四元数直接复制为 TCP 四元数，也不得对四元数分量做加法。

## 6. 配置与版本策略

保持现有 `light_cup_wall_pick/v1` 不变。新增独立 policy ID，例如：

```text
config/policies/dynamic_cup_pick/v1/
├── manifest.yaml
├── gazebo.yaml
├── mujoco.yaml
└── real_stub.yaml
```

动态 YAML 使用 `schema_version: 2`，示例：

```yaml
schema_version: 2
policy_id: dynamic_cup_pick
planning_frame: world
object_id: plastic_cup
cup_to_tcp_grasp:
  xyz_m: [0.0, 0.0, 0.035]
  xyzw: [0.0, 0.0, 0.0, 1.0]
pick:
  pregrasp_world_z_clearance_m: 0.08
  lift_world_z_clearance_m: 0.10
  maximum_source_age_s: 0.20
  workspace_bounds_m: [-0.21, -0.46, 0.12, 0.21, 0.06, 0.30]
motion:
  planning_timeout_s: 5.0
  velocity_scaling: 0.03
  acceleration_scaling: 0.03
```

固定 placement region、夹爪目标和接触/物理 outcome policy 可作为动态模板的静态部分复用，但须由动态 schema 显式加载，不能从 v1 固定 joint-policy 隐式取值。

## 7. 运行契约

### 7.1 V1：`fixed_cup_pick_place`

- 使用现有完整 motion-policy v1 和固定 `MotionStatePolicy.waypoints`。
- 不创建 `/cup_pose` subscription，也不等待 topic。
- 当前 `pick_place` 的行为成为 V1 回归基线；公共 entry point 改名后必须通过同样的 fixed policy 测试。
- manifest 写入 `strategy=fixed` 和 fixed policy SHA-256。

### 7.2 V2：`dynamic_cup_pick_place`

新增 ROS-aware composition root，顺序严格为：

```text
parse CLI
→ acquire one valid /cup_pose
→ transform/require world frame
→ freshness + workspace validation
→ scene authority check and readback
→ DynamicPickPlan resolution
→ plan each dynamic pick motion
→ start state-machine side effects
```

读取 Pose、TF、场景检查、动态 plan 任一失败，状态机不得进入 `PREPARE_OPEN_GRIPPER`，不得发送 arm/gripper/attachment 命令。

V2 使用 `RobotControlPort.plan_tcp_motion(TcpMotionRequest(...))` 和 `execute()`；`MOVE_ABOVE_OBJECT`、`DESCEND`、`LIFT` 分别消费 dynamic plan 的三个 TCP Pose。其余状态必须在实施时显式决定使用动态 TCP goal 或固定安全 template，不得偷偷访问 V1 的 pick waypoint。

## 8. Frame、时间与场景权威

### 8.1 V2.1 frame 策略

V2.1 仅接受 `header.frame_id == "world"`。其它合法但非 world 的消息返回 `CUP_POSE_TF_UNAVAILABLE`，而不是假设其坐标正确。

V2.2 才接入 `tf2_ros.Buffer`：按 `PoseStamped.header.stamp` 转换到 world，并把 source frame、target frame、stamp 和变换结果写入 manifest。

### 8.2 时间策略

使用 receipt monotonic time 判断等待超时；使用 ROS message stamp 判断 source age。若仿真时钟尚不可用或 stamp 为零，默认拒绝动态 execute，并在 plan-only 中明确报告 `CUP_POSE_STALE` 或 `CUP_POSE_CLOCK_UNAVAILABLE`。

### 8.3 场景权威模式

默认 `--scene-source=observe_only`：

```text
/cup_pose world pose ≈ simulator cup pose ≈ MoveIt world object pose
```

任何一对超过 position/orientation tolerance 即 `CUP_POSE_SCENE_DIVERGENCE`。

可选的 `--scene-source=topic` 只允许在显式 reset/preflight 事务中使用：先写 simulator cup Pose，再读回；随后 upsert MoveIt Scene，再读回；三方相同后才允许规划。禁止在正常执行中隐式 teleport cup。

## 9. 失败模型

| 失败码 | 触发条件 | side effect |
|---|---|---|
| `CUP_POSE_TIMEOUT` | 等待窗口内没有任何消息 | 无状态机动作 |
| `CUP_POSE_INVALID` | 收到消息但均不满足输入契约 | 无状态机动作 |
| `CUP_POSE_STALE` | 有效消息超过允许 age | 无状态机动作 |
| `CUP_POSE_TF_UNAVAILABLE` | frame 不等于 world 或 TF 无法转换 | 无状态机动作 |
| `CUP_POSE_OUT_OF_WORKSPACE` | cup/pregrasp/grasp/lift 超出模板边界 | 无状态机动作 |
| `CUP_POSE_SCENE_DIVERGENCE` | topic、simulator、MoveIt Scene 不一致 | 无状态机动作 |
| `CUP_POSE_PLAN_FAILED` | IK、碰撞检查或 trajectory planning 失败 | 不 execute 该段 |

V2 失败不得调用 `fixed_cup_pick_place`，不得载入 V1 抓取 waypoint 作为默认值。

## 10. 证据与 qualification

V1 与 V2 使用独立 `strategy` 字段、独立 policy/template hash 和独立 run ID。V1 历史 fixed-trajectory success 不构成 V2 qualification。

每个 V2 run manifest 至少包含：

- strategy、backend、source commit、installed prefix、ROS domain、Gazebo partition；
- 输入 Pose 原始 frame/stamp、receipt time、转换后的 world Pose；
- dynamic template path/SHA-256；
- pregrasp/grasp/lift TCP target；
- MoveIt plan result、trajectory summary 和 execute result；
- simulator pose、MoveIt Scene pose 及其差值；
- 状态 trace、失败码和创建证据的绝对路径。

V2 实施顺序为 pure unit → ROS input contract → Gazebo+MoveIt plan-only → headless execute → GUI execute。动态 execute 在完成独立 physical qualification 前保持禁止。

## 11. 兼容性与迁移

- 新 public executable 是 `fixed_cup_pick_place` 和 `dynamic_cup_pick_place`。
- `fixed_cup_pick_place` 替换 generic `pick_place` 的 public 用法；实施时须明确是否保留 legacy alias。默认建议删除 alias，避免用户误以为它会读取感知 topic。
- `cup_pose_subscriber` 保留为观测/调试工具，不能作为 V2 到 V1 的跨进程数据桥。
- V1 与 V2 的 policy registry 条目、test fixture、manifest schema 和 qualification ledger 分开维护。

## 12. 验收标准

### V1 回归

同一 fixed policy 输入产生与迁移前相同的 waypoint、state trace、failure contract 和 manifest strategy；V1 完全不订阅 `/cup_pose`。

### V2 输入和规划

1. 两条 `/cup_pose` 相差 0.1 m 的消息分别产生相差 0.1 m 的 pregrasp/grasp/lift target。
2. 无消息、非法消息、错误 frame、过期消息和 scene divergence 都不发送 arm/gripper/attach 命令。
3. `plan_only` 的 MoveIt trajectory 起点与当前 joint state 一致，目标为对应 dynamic TCP Pose，并通过碰撞检查。
4. V2 manifest 记录输入、转换、模板 hash、目标和规划读回。

### Execute 前门槛

V2 只有在独立 Gazebo 物理、MoveIt Scene、controller/joint/TF、cup pose/contact 和新鲜 GUI 证据均通过后才允许 `--mode execute --execute`。真实硬件不在本设计授权范围内。
