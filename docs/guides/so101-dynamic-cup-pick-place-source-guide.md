# SO-101 Dynamic Cup Pick Place 源码导读

**范围：** `so101_demo_py` 的生产源码与运行配置，不讲测试实现

**对象：** `fixed_cup_pick_place` 与 `dynamic_cup_pick_place`

**目标：** 理解感知到的杯子 Pose 如何变成 SO-101 可以规划、执行和验证的抓取动作

## 1. 先建立整体直觉

这次改动没有把原来的固定抓取直接改成“订阅一个 topic”。它保留 V1，并新增一条相互隔离的 V2 执行链：

```text
fixed_cup_pick_place
  -> 固定 V1 policy
  -> 固定 joint waypoint
  -> 原有状态机

dynamic_cup_pick_place
  -> /cup_pose
  -> 冻结一个合法 CupPoseSample
  -> DynamicPickTemplate
  -> 动态生成 TCP targets
  -> IK 求 joint targets
  -> MoveIt 规划与执行
  -> MuJoCo 物理门禁
  -> 同一套状态机
```

两条链共享 `StateMachineRunner + SO101_WORKFLOW`。区别只在于动作目标从哪里来，不复制状态顺序、失败转移和 recovery 规则。

最值得先记住的是：

> 更新杯子的 Planning Scene Pose，不会让固定 joint waypoint 自动跟随杯子。V2 必须把感知 Pose 显式转换成 TCP Pose，再经过 IK 和 MoveIt 变成关节轨迹。

## 2. 两个 executable 的边界

console script 注册在 [`setup.py`](../../src/so101_demo_py/setup.py)：

```text
fixed_cup_pick_place   -> so101_demo.cli.fixed_cup_pick_place:main
dynamic_cup_pick_place -> so101_demo.cli.dynamic_cup_pick_place:main
```

### 2.1 V1：固定位置策略

[`fixed_cup_pick_place.py`](../../src/so101_demo_py/src/cli/fixed_cup_pick_place.py) 只是给原有 `pick_place.py` 提供明确的 public 名称。它继续读取 V1 固定 waypoint，不依赖 `/cup_pose`。

原有 launch composition 也显式调用 `fixed_cup_pick_place`，所以现有 launch 不会因为 V2 出现而悄悄改变行为。

### 2.2 V2：感知位置策略

[`dynamic_cup_pick_place.py`](../../src/so101_demo_py/src/cli/dynamic_cup_pick_place.py) 是独立入口。当前模式矩阵是：

| Backend | `plan_only` | `execute` |
|---|---:|---:|
| Gazebo | 支持 | 拒绝 |
| MuJoCo | 当前实现拒绝 | 支持 |
| real / unknown | 拒绝 | 拒绝 |

MuJoCo execute 必须同时给出：

```text
--mode execute --execute
```

这是显式的双重执行授权。V2 的输入、策略、场景或物理门禁失败时会返回错误，不会转去执行 V1 固定抓取。

## 3. `/cup_pose` 输入如何进入状态机

topic 契约是：

```text
/cup_pose
geometry_msgs/msg/PoseStamped
```

这里有两个用途不同的订阅器。

### 3.1 持续诊断订阅器

[`cup_pose_subscriber.py`](../../src/so101_demo_py/src/cli/cup_pose_subscriber.py) 面向人类观察：

- 合法 Pose 输出一行 JSON；
- 非法 Pose 输出一行 `CUP_POSE_INVALID`，然后继续监听；
- inter-message timeout 或 SIGINT 后退出；
- 不生成任何 fallback Pose。

它用于回答“外部发布器有没有持续发布合格消息”，但不能证明状态机使用了该消息。

### 3.2 状态机的一次性输入

[`RosCupPoseSource`](../../src/so101_demo_py/src/ros/cup_pose_source.py) 面向一次 pick-place 任务。它调用 [`acquire_one()`](../../src/so101_demo_py/src/ports/cup_pose_source.py)：

```text
开始等待
  ├─ 没有消息：继续等待
  ├─ 非法消息：报告错误并继续等待
  └─ 第一条完全合法的消息：返回并销毁 subscription
```

等待使用 absolute monotonic deadline。非法消息不会重新开始倒计时，因此持续发送垃圾数据不能让程序永远等待。

输入必须满足：

- `header.frame_id == "world"`；
- position 和 quaternion 全部是有限数；
- quaternion 不是零四元数；
- quaternion 使用前会归一化；
- source stamp 非零；
- 消息没有超过最大 age；
- 消息时间不能明显来自未来。

当前版本没有隐式 tf2 转换。如果真实相机发布 `camera_color_optical_frame`，会 fail closed：

```text
CUP_POSE_TF_UNAVAILABLE
```

后续真实视觉链应在进入动态抓取前完成：

```text
camera-frame Pose
  -> tf2 transform
  -> world-frame Pose
  -> RosCupPoseSource
```

## 4. 为什么只冻结一条感知结果

[`CupPoseSample`](../../src/so101_demo_py/src/core/dynamic_pick.py) 保存：

- `frame_id`；
- `source_stamp_ns`；
- 本机接收时刻；
- 归一化后的 `pose_world`。

第一条合格消息被冻结后，整次状态机都使用同一份输入。这样机械臂不会在执行时追逐每帧视觉噪声：

```text
frame 1: cup.x = 0.020
frame 2: cup.x = 0.018
frame 3: cup.x = 0.023
```

如果 `DESCEND`、`MICRO_LIFT`、`LIFT` 分别读取不同帧，三个目标会不连续，甚至可能把已经接触到的杯子推倒。

当前任务语义因此是：

```text
一次感知 -> 一次策略解析 -> 一次完整任务
```

如果杯子在状态机开始后被移动，应停止本次任务并重新感知，而不是继续追踪新 Pose。

## 5. DynamicPickTemplate 到底是什么

[`DynamicPickTemplate`](../../src/so101_demo_py/src/core/dynamic_pick.py) 描述：

> 已知杯子在哪里之后，应该如何接近、抓取、抬升、放置和验证。

它不保存本次 cup world Pose，也不包含 V1 固定 pick joint waypoint。主要字段分为：

| 类别 | 内容 |
|---|---|
| planning | frame、group、joint names、TCP link、timeout、容差、速度和加速度 scaling |
| object | `plastic_cup`、`T_cup_tcp_grasp` |
| pick | pregrasp、micro-lift、lift 的 world-Z clearance |
| place | 固定 place TCP、approach、retreat clearance |
| safety | workspace、消息新鲜度、场景位置和姿态容差 |

实际 MuJoCo 参数在 [`config/policies/dynamic_cup_pick/v1/mujoco.yaml`](../../src/so101_demo_py/config/policies/dynamic_cup_pick/v1/mujoco.yaml)。

[`dynamic_pick_policy.py`](../../src/so101_demo_py/src/core/dynamic_pick_policy.py) 使用严格 schema 加载配置：

- 未知字段和缺失字段都拒绝；
- backend 和 execute allowance 必须一致；
- variant 文件 SHA-256 必须与 manifest 一致；
- Gazebo variant 明确不可 execute；
- MuJoCo variant 才允许 execute。

这避免了“读错 backend 配置但仍然运动”的隐式行为。

## 6. 从杯子 Pose 推导抓取 Pose

核心刚体变换是：

```text
T_world_tcp_grasp
    =
T_world_cup
    *
T_cup_tcp_grasp
```

含义分别是：

- `T_world_cup`：感知告诉我们的杯子 world Pose；
- `T_cup_tcp_grasp`：模板中标定的“相对杯子，TCP 应该在哪里”；
- `T_world_tcp_grasp`：机械臂真正需要到达的 world Pose。

[`compose_pose()`](../../src/so101_demo_py/src/core/dynamic_pick.py) 会旋转 child translation、组合四元数并归一化。不能把两个 Pose 的位置和四元数逐分量相加。

[`resolve_motion_targets()`](../../src/so101_demo_py/src/core/dynamic_pick.py) 进一步生成所有运动状态的目标：

| State | 目标来源 |
|---|---|
| `MOVE_ABOVE_OBJECT` | perception grasp + pregrasp world-Z |
| `DESCEND` | perception grasp |
| `MICRO_LIFT` | perception grasp + micro-lift world-Z |
| `LIFT` | perception grasp + lift world-Z |
| `MOVE_ABOVE_PLACE` | template place + approach world-Z |
| `DESCEND_TO_PLACE` | template place |
| `RETREAT` | template place + retreat world-Z |
| recovery motion | 显式复用本次解析出的安全目标 |

所有 TCP 目标都必须落在模板 workspace 内。

当前 V2 是“pick 位置动态、place 位置固定”。如果 cup 的 X 增加 `0.10 m`，pick-family target 的 X 也应增加约 `0.10 m`；place-family target 不变。

## 7. 为什么要比较三份杯子 Pose

收到合法 topic 仍然不代表场景正确。执行前，[`validate_cup_scene()`](../../src/so101_demo_py/src/application/cup_pose_preflight.py) 比较三个事实源：

```text
Topic 感知 Pose
Simulator 物理 Pose
MoveIt Planning Scene Pose
```

它做三组比较：

```text
topic <-> simulator
topic <-> MoveIt
simulator <-> MoveIt
```

任一位置或姿态差异超过模板容差，就返回：

```text
CUP_POSE_SCENE_DIVERGENCE
```

任务开始前，`plastic_cup` 还必须是 MoveIt world object，不能已经 attached。

这项检查避免了危险的三方分裂：感知认为杯子在 A，MuJoCo 物理杯在 B，MoveIt 碰撞体却在 C。

## 8. V1 和 V2 为什么共用状态机

[`build_dynamic_actions()`](../../src/so101_demo_py/src/application/dynamic_execute.py) 为现有 `SO101_WORKFLOW` 的每个 action state 安装一个 `DynamicStateAction`。

职责被分成两部分：

```text
StateMachineRunner / SO101_WORKFLOW
  -> 当前是什么 state
  -> 成功后去哪里
  -> 失败后怎样 recovery

DynamicStateAction
  -> 当前 state 使用哪个动态 target
  -> 调用 execution port 执行
```

因此不会出现 V1 修复了 recovery，但 V2 还保留旧 recovery 的双状态机漂移。

成功链是：

```text
IDLE
-> PREPARE_OPEN_GRIPPER
-> MOVE_ABOVE_OBJECT
-> DESCEND
-> CLOSE_GRIPPER
-> WAIT_GRASP_STABLE
-> MICRO_LIFT
-> WAIT_MICRO_LIFT_STABLE
-> VERIFY_PHYSICAL_GRASP
-> ATTACH_MOVEIT
-> LIFT
-> MOVE_ABOVE_PLACE
-> DESCEND_TO_PLACE
-> DETACH_MOVEIT
-> OPEN_GRIPPER
-> WAIT_RELEASE_SETTLE
-> VALIDATE_FINAL_PLACEMENT
-> SYNC_WORLD_OBJECT
-> RETREAT
-> DONE
```

## 9. 5-DoF SO-101 如何执行 6D Pose

### 9.1 先理解“欠驱动”

一个 TCP Pose 通常包含 6 个自由度：

```text
position: x, y, z
rotation: roll, pitch, yaw
```

SO-101 arm 只有 5 个独立关节。令关节向量为：

```text
q = [q1, q2, q3, q4, q5]
```

FK（Forward Kinematics，正运动学）是从 5 个关节角计算 TCP Pose：

```text
TCP_pose = FK(q)
```

IK（Inverse Kinematics，逆运动学）则希望反过来求：

```text
找到 q，使 FK(q) 接近 target_pose
```

问题在于，目标有 6 个约束，变量只有 5 个。局部 Jacobian 的形状是：

```text
J: 6 x 5
```

它的列空间最多只有 5 维，通常不能同时消除任意 6 维误差。这就是 underactuated（欠驱动）在这里的含义：

> 机械臂能够到达很多位置和姿态组合，但不能保证精确实现任意给定的 6D Pose。

因此 [`UnderactuatedPoseIk`](../../src/so101_demo_py/src/control/moveit/underactuated_ik.py) 不是承诺“任何 Pose 都能解”，而是：

1. 在当前姿态附近寻找关节解；
2. 在 joint limit 内尽量同时减小位置和姿态误差；
3. 用明确的 residual 门槛决定解是否可接受；
4. 无法满足门槛时 fail closed，不把近似程度不明的结果交给机器人。

### 9.2 从 URDF 建立运动链

入口是 `UnderactuatedPoseIk.from_urdf()`。它从安装的 URDF 读取每个 joint 的：

- parent link 和 child link；
- joint type，例如 revolute 或 fixed；
- joint origin 的 `xyz/rpy`；
- 转轴 `axis`；
- `lower/upper` joint limit。

代码先建立 `child link -> joint` 索引，再从 `so101_tcp` 沿 parent 方向回溯到 `world`，最后把结果反转成正向链：

```text
world
  -> joint/link transforms
  -> joint 1
  -> joint 2
  -> joint 3
  -> joint 4
  -> joint 5
  -> fixed transforms
  -> so101_tcp
```

初始化时还会检查：URDF 链中的可动关节集合必须与模板声明的 5 个 arm joint 完全一致。缺关节、多关节或 link 链断裂都会返回 `DYNAMIC_IK_CHAIN_INVALID`。

这一步的意义是：IK 使用的几何、转轴和限位来自当前安装的机器人模型，而不是在 Python 中重新硬编码一套臂长。

### 9.3 FK 如何计算一个候选解的 TCP Pose

`_matrix()` 从单位矩阵开始，沿运动链依次相乘：

```text
T_world_tcp(q)
  = T_origin_1 * R_axis_1(q1)
  * T_origin_2 * R_axis_2(q2)
  * ...
  * T_fixed_tcp
```

其中：

- `T_origin_i` 是 URDF joint origin 的固定变换；
- `R_axis_i(qi)` 是关节绕 URDF axis 旋转 `qi` 后的变换；
- fixed joint 只乘固定 origin，不增加优化变量。

`forward()` 再从最终 4x4 齐次变换矩阵中取出：

```text
translation -> TCP position
rotation    -> normalized quaternion
```

IK 的每次迭代、最终验收以及 evidence 中的 `resolved_fk_pose`，都使用这套 FK 重新计算，不是假定“求解器返回的 q 一定等于目标 Pose”。

### 9.4 residual：求解器到底在缩小什么

给定当前候选关节角 `q`，代码构造一个 6 维 residual（残差，也就是尚未消除的误差）：

```text
position_error
  = target_position - actual_position

orientation_error
  = rotation_vector(R_target * transpose(R_actual))

residual
  = [position_error,
     0.08 * orientation_error]
```

前三维是米，后三维是旋转向量，方向表示应该绕哪个轴修正，模长表示应修正多少弧度。

`0.08` 是位置和姿态在数值优化目标中的相对权重。它不是把姿态门禁放宽 8%，也不是忽略姿态。优化结束后仍会分别检查真实的位置误差和姿态误差。

最终姿态误差通过四元数计算：

```text
orientation_error_rad
  = 2 * acos(abs(dot(q_actual, q_target)))
```

这里使用绝对值，是因为四元数 `q` 和 `-q` 表示同一个旋转。如果不处理这个等价关系，求解器可能把同一姿态错误地认为相差接近 360 度。

### 9.5 数值 Jacobian 如何得到

代码没有手写 SO-101 的解析 Jacobian，而是使用 finite difference（有限差分）计算数值 Jacobian。

对第 `i` 个关节，把它临时增加：

```text
epsilon = 1e-5 rad
```

然后重新计算 residual：

```text
J[:, i]
  = (residual(q + epsilon_i) - residual(q)) / epsilon
```

5 个关节分别扰动一次，就得到 `6 x 5` Jacobian。它近似描述：

> 当前姿态附近，每个关节发生一个很小变化，会怎样影响 TCP 的位置和姿态误差。

数值 Jacobian 的优点是实现直接，并且自动跟随 URDF 几何；代价是每轮需要多次 FK，而且精度依赖 `epsilon`。

### 9.6 阻尼最小二乘如何更新关节角

求解器使用 DLS（Damped Least Squares，阻尼最小二乘）计算本轮步长：

```text
delta_q
  = -(transpose(J) * J + lambda * I)^-1
     * transpose(J)
     * residual

lambda = 1e-5
```

直觉上，这是在问：

> 关节角朝哪个方向变化，能让加权 residual 的平方和下降最多？

加入 `lambda * I` 很重要。当机械臂接近 singularity（奇异位形）或者某些方向几乎无法运动时，`JᵀJ` 会病态甚至不可逆。阻尼项让求解更稳定，避免一次迭代产生极大的关节跳变。

代码还有两层限制：

```text
单轮 delta_q 的整体范数最大 0.20 rad
每次更新后把 q clip 到 URDF joint limits
```

所以单次迭代不会无限跳跃，也不会为了降低 TCP 误差而给出越过机械限位的关节角。

### 9.7 seed 为什么使用实际 joint state

`solve()` 的起点不是固定 home waypoint，而是当前 `/joint_states`：

```text
q0 = current_joint_state
```

这有三个作用：

1. 更容易收敛到离当前姿态较近的局部解；
2. 减少相邻动态目标之间的关节跳变；
3. 不需要读取 V1 固定 waypoint 作为 fallback。

在分段运动中，每一小段执行完成后都会重新读取真实 joint state，并把它作为下一小段的 seed：

```text
target_pose_1 -> IK(q_current) -> plan -> execute
                                      ↓
                              read new joint state
                                      ↓
target_pose_2 -> IK(q_new)     -> plan -> execute
```

需要注意，这个求解器没有 random restart。给定同一 URDF、target 和 seed，行为是确定性的；但数值 IK 仍可能停在局部最优。某个 seed 求解失败，并不构成数学证明“全关节空间绝对不存在其他解”。对机器人执行而言，当前实现选择 fail closed，而不是在运行中无界搜索其他姿态。

### 9.8 什么时候认为 IK 成功

每轮迭代后，代码都用 FK 得到 `actual_pose`，并分别检查：

```text
position_error_m
  = distance(actual_position, target_position)

orientation_error_rad
  = quaternion angular distance
```

当前动态模板的典型门槛是：

```text
position_error <= 0.002 m
orientation_error <= 0.10 rad
```

也就是位置约 2 mm、姿态约 5.7 度。两项必须同时满足才能返回 joint target。

最多执行 200 次迭代。如果仍未满足门槛，就返回：

```text
DYNAMIC_IK_RESIDUAL_EXCEEDED:
position_m=<最终位置误差>
orientation_rad=<最终姿态误差>
```

这比单纯返回“没有 IK”更有教学和诊断价值：

- 位置误差大、姿态误差小：目标位置可能超出 workspace 或臂长；
- 位置误差小、姿态误差大：5-DoF 可能无法同时满足该姿态；
- 两项都大：seed、目标、URDF 链或整体可达性都需要检查。

### 9.9 IK 成功后为什么还要 MoveIt

`UnderactuatedPoseIk` 只回答：

```text
有没有一个关节终点 q_target，
使 TCP Pose 在允许 residual 内？
```

它不回答：

- 从当前关节角到 `q_target` 的路径是否碰撞；
- 中间姿态会不会扫过桌子或杯子；
- 轨迹时间、速度和加速度如何安排；
- controller 能否执行；
- cup 是否被真实夹住。

所以职责关系是：

```text
IK
  -> TCP Pose 转成候选 joint target

MoveIt
  -> 从当前 joint state 到 joint target 做碰撞感知路径规划

Controller
  -> 执行 MoveIt 产生的 trajectory

MuJoCo evidence
  -> 证明 robot 和 cup 物理上实际发生了什么
```

因此：

```text
IK success != collision-free path
MoveIt success != controller executed
controller success != cup physically grasped
```

### 9.10 为什么还要把长动作分段

为降低长距离关节插值扫过杯子或桌面的风险，`DESCEND`、`MOVE_ABOVE_PLACE` 和 `DESCEND_TO_PLACE` 会先做 Pose interpolation，再对每个中间 Pose 分别求 IK 和规划。

当前实现把这些动作的起点和目标之间分成 6 段。每一段都执行完整闭环：

```text
intermediate TCP Pose
  -> UnderactuatedPoseIk.solve()
  -> FK residual readback
  -> MoveIt joint path planning
  -> trajectory execution
  -> MuJoCo contact/force monitor
  -> refresh actual joint state
```

这样做不能数学上保证全局最优路径，但它比只求最终 Pose、再让关节空间一次跨越更贴合“TCP 沿着接近方向移动”的任务意图。

### 9.11 沿源码跟一次 `solve()`

可以把一次调用压缩成下面的伪代码：

```text
input:
  target TCP Pose
  current joint state as seed
  position/orientation tolerances

q = clip(seed, lower_limits, upper_limits)

repeat at most 200 times:
  actual_pose = FK(q)

  if position_error and orientation_error are both acceptable:
    return q

  residual = weighted_pose_error(actual_pose, target_pose)
  J = finite_difference_jacobian(q, residual)
  delta_q = damped_least_squares(J, residual)
  delta_q = limit_step_norm(delta_q, 0.20 rad)
  q = clip(q + delta_q, lower_limits, upper_limits)

raise DYNAMIC_IK_RESIDUAL_EXCEEDED
```

理解这段伪代码后再读 `underactuated_ik.py`，每个矩阵函数就有了明确位置：URDF 提供几何，FK 产生实际 Pose，residual 表示差多少，Jacobian 描述关节如何影响误差，DLS 选择下一步，最终门禁决定能否执行。

## 10. 物理抓取和 MoveIt attachment 是两回事

动态 MuJoCo 执行器是 [`RosDynamicMujocoExecution`](../../src/so101_demo_py/src/ros/dynamic_mujoco_execution.py)。

正确的抓取顺序是：

```text
真实闭爪
-> MuJoCo 触点稳定
-> micro-lift
-> MuJoCo 证明 cup 真实上升并离桌
-> ATTACH_MOVEIT
-> 搬运
```

MoveIt attachment 只是 planning shadow：它告诉规划器“碰撞检查时把杯子当作机器人携带的物体”。它不会在 MuJoCo 里创建一根隐形约束把杯子粘到夹爪上。

正常 forward execution 不调用 MuJoCo attach service。杯子必须依靠夹爪接触和摩擦被真实搬运。

执行过程中读取的 MuJoCo 原子证据包括：

- cup position 和 orientation；
- cup linear/angular velocity；
- 左右 fingertip contact；
- maximum normal force；
- table contact；
- simulation session id；
- reset epoch 和 publisher sequence。

关键门禁包括：

- 闭爪前 cup 不能被提前推走；
- 搬运期间必须保持双侧接触；
- 接触力不能超过限制；
- micro-lift 必须证明 cup 实际上升并离桌；
- release 后 cup 必须落桌并稳定；
- 最终必须没有 fingertip contact；
- 最终位置、高度和 upright tilt 必须合格。

因此以下结果不能互相替代：

```text
MoveIt plan success
controller action success
Planning Scene attached
MuJoCo 中 cup 真正被抬起
GUI 中最终画面正确
```

## 11. Planning Scene 的 attach、detach 和同步

抓取被物理证明后，Planning Scene 才把 `plastic_cup` 从 world object 变成 attached object。

释放顺序是：

```text
DETACH_MOVEIT
-> 打开夹爪
-> WAIT_RELEASE_SETTLE
-> VALIDATE_FINAL_PLACEMENT
-> SYNC_WORLD_OBJECT
-> RETREAT
```

[`make_cup_collision_object()`](../../src/so101_demo_py/src/control/planning_scene/cup.py) 使用 12 个杯壁 BOX 和一个杯底 CYLINDER，重建 canonical `plastic_cup` 碰撞体。最终 readback 必须满足：

- attached object 中没有 `plastic_cup`；
- world object 中存在完整的 `plastic_cup`；
- Pose 来自释放后的最新 MuJoCo 物理状态。

## 12. 为什么需要局部 ACM 例外

ACM = Allowed Collision Matrix，允许碰撞矩阵。

夹爪抓取时必须接近甚至接触杯子；释放后退时，夹爪也可能暂时处在保守 cup collision proxy 内部。因此代码只在两个窄边界临时允许：

```text
jaw/gripper <-> plastic_cup
```

- 抓取 `DESCEND`；
- 释放后的 `RETREAT/RECOVER_RETREAT`。

阶段结束后立即恢复禁止碰撞。没有全局关闭碰撞，也没有允许其他 robot link 穿过桌子或杯子。

## 13. `plan_only` 路径解决什么问题

[`dynamic_plan_only.py`](../../src/so101_demo_py/src/application/dynamic_plan_only.py) 和 [`dynamic_planner.py`](../../src/so101_demo_py/src/ros/dynamic_planner.py) 可以对单个动态 state 做 Pose 规划，但不执行轨迹。

它用于回答：

```text
这条感知 Pose 能否生成目标？
目标是否在 workspace 内？
IK/MoveIt 能否找到候选轨迹？
规划前后场景有没有发生意外变化？
```

`TcpMotionRequest` 因此扩展了 planning frame、group、TCP link、容差、scaling 和显式 start state；`PlanResult` 增加 terminal joint state，便于证明规划结果完整。

`plan_only` 只证明候选路径存在，不证明 controller 执行、cup 被抓住或最终放置成功。

## 14. Evidence 文件如何连接输入、决策和结果

动态 execute 会持续写入：

```text
dynamic-execute-manifest.json
```

内容包括：

- frozen `/cup_pose`；
- policy path 与 SHA-256；
- 全部 resolved TCP targets；
- simulation session 和 reset epoch；
- state trace；
- 每个 state 的 before/after 物理样本；
- IK/FK residual 和 joint targets；
- release marker 与 final samples；
- Planning Scene 最终 readback；
- `DONE` 或稳定 failure code。

文件通过临时文件加 `os.replace()` 原子更新。即使中途失败，也尽量留下最后一个完整 JSON，而不是半写入文件。

这份 evidence 可以回答：

```text
输入是什么？
程序根据输入计算了什么？
MoveIt/controller 执行了什么？
杯子在物理世界里实际发生了什么？
```

## 15. MuJoCo cup pose bridge 的边界

[`mujoco_cup_pose_bridge.py`](../../src/so101_demo_py/src/ros/mujoco_cup_pose_bridge.py) 把 MuJoCo lossless truth 转换成 `/cup_pose`，用于本地端到端验证。

它证明：

```text
ROS topic
-> 输入校验与冻结
-> 动态目标解析
-> 状态机
-> MuJoCo 物理执行
```

它不证明：

```text
相机图像
-> 目标检测或分割
-> 深度恢复
-> 真实 3D cup Pose
```

因此人工 MuJoCo 验证通过，表示动态抓取消费链路和仿真物理执行通过，不表示视觉算法精度已验证。

## 16. 建议的源码阅读顺序

不要一开始从 600 多行执行器顺序向下读。按数据流阅读更容易形成机器人直觉：

1. [`dynamic_cup_pick_place.py`](../../src/so101_demo_py/src/cli/dynamic_cup_pick_place.py)：模式和执行门禁；
2. [`cup_pose_source.py`](../../src/so101_demo_py/src/ros/cup_pose_source.py)：ROS 消息如何变成 `CupPoseSample`；
3. [`dynamic_pick.py`](../../src/so101_demo_py/src/core/dynamic_pick.py)：刚体变换和目标解析；
4. [`mujoco.yaml`](../../src/so101_demo_py/config/policies/dynamic_cup_pick/v1/mujoco.yaml)：抓取模板中的标定参数；
5. [`cup_pose_preflight.py`](../../src/so101_demo_py/src/application/cup_pose_preflight.py)：三份 Pose 为什么必须一致；
6. [`dynamic_execute.py`](../../src/so101_demo_py/src/application/dynamic_execute.py)：动态 action 如何复用唯一状态机；
7. [`underactuated_ik.py`](../../src/so101_demo_py/src/control/moveit/underactuated_ik.py)：5-DoF IK、FK 和 residual；
8. [`dynamic_mujoco_execution.py`](../../src/so101_demo_py/src/ros/dynamic_mujoco_execution.py)：规划、controller、物理和 Planning Scene 如何闭环；
9. [`dynamic_runtime.py`](../../src/so101_demo_py/src/ros/dynamic_runtime.py)：以上组件如何组装成一次任务。

## 17. 当前实现的明确限制

- `/cup_pose` 当前只接受 `world` frame，没有接入 tf2；
- pick 目标来自感知，但 place 目标仍是模板中的固定位置；
- 一次任务只冻结一条 Pose，不做在线 visual servoing；
- Gazebo dynamic execute 仍被禁止；
- MuJoCo bridge 是验证适配器，不是生产视觉节点；
- 5-DoF 手臂只能接受满足位置和姿态 residual 门槛的目标；
- 当前验证覆盖仿真，不代表已经满足真实机械臂的限速、急停和净空安全要求。

## 18. 自检问题

读完源码后，应能够不看文档解释下面问题：

1. 为什么把 MoveIt Planning Scene 中的 cup 移动到新位置，固定 joint waypoint 不会自动跟随？
2. `T_world_cup * T_cup_tcp_grasp` 的两个输入分别来自哪里？
3. 为什么状态机只冻结一次 `/cup_pose`，而不是每个 state 都读取最新消息？
4. 为什么必须先用 MuJoCo 证明 micro-lift 成功，之后才能 `ATTACH_MOVEIT`？
5. IK 找到 joint target 后，为什么还必须交给 MoveIt 规划？
6. 人工 MuJoCo E2E 通过，为什么仍不能说真实视觉定位已经验证？

如果能把这六个问题讲清楚，就已经抓住了这次源码改动中最重要的机器人数据流和系统边界。
