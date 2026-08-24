# SO-101 固定与感知 Cup Pick 双策略设计

**日期：** 2026-08-23

**当前修订：** V2.2，MuJoCo 感知位置可执行版
**源码基线：** `moveit-demo/main@5407592100823bcfa43138611f8de6b0de0c93f8`

## 1. 目标与结论

同一个 `so101_demo_py` package 发布两个明确分工的 executable：

```text
fixed_cup_pick_place    # V1：固定 cup 位 + 固定 joint waypoint
dynamic_cup_pick_place  # V2：/cup_pose + 动态解析目标 + MuJoCo 物理执行
```

V1 保留原行为和 policy，不依赖视觉输入。V2 在状态机开始前冻结一条合法 `/cup_pose`，由模板解析整条状态机的 TCP 目标，并在 MuJoCo 中执行完整 pick-place。两者共享仓库唯一的 `StateMachineRunner + SO101_WORKFLOW`，不复制状态转移，也不允许 V2 在任何失败路径回退到 V1 固定 pick waypoint。

Gazebo 的 V2 仍只允许 `plan_only`；MuJoCo 是当前唯一允许动态 execute 的 backend。真实硬件不在本设计的执行范围。

## 2. 总体数据流

```text
/cup_pose (PoseStamped)
  -> 一次性输入与时间校验
  -> frozen CupPoseSample
  -> DynamicPickTemplate
  -> ResolvedMotionTargets
  -> DynamicStateAction
  -> StateMachineRunner + SO101_WORKFLOW
  -> MuJoCo controller / Planning Scene / physical gates
```

cup 的 Planning Scene object Pose 和机器人运动目标是两条不同数据流。更新 cup object 不会让固定 joint waypoint 自动跟随；V2 必须显式计算：

```text
T_world_tcp_grasp = T_world_cup * T_cup_tcp_grasp
```

四元数先归一化，再按刚体变换组合；禁止逐分量相加，也禁止把 cup quaternion 直接复制成 TCP quaternion。

## 3. 输入契约

`CupPoseSample` 保存 `frame_id`、`source_stamp_ns`、`received_monotonic_s` 和 `pose_world`。输入必须满足：

- topic 为 `/cup_pose`，类型为 `geometry_msgs/msg/PoseStamped`；
- `frame_id == "world"`，当前版本不做隐式 TF 转换；
- position 和 quaternion 的全部分量为有限数；
- quaternion norm 大于最小阈值，并在使用前归一化；
- source stamp 非零，未超过 maximum age，也不超出 future skew；
- 输入 cup origin 与 canonical `plastic_cup` geometry manifest 一致。

获取使用绝对 monotonic deadline。非法消息输出一行 `CUP_POSE_INVALID` 并继续监听，且不延长 deadline。deadline 前无消息为 `CUP_POSE_TIMEOUT`；仅收到非法消息为 `CUP_POSE_INVALID`。第一条完全合法的消息被冻结，后续状态机使用同一份样本。

持续诊断 executable `cup_pose_subscriber` 与一次性状态机输入 source 相互独立；前者持续监听至 SIGINT 或 inter-message timeout，后者只冻结一个合格样本。

## 4. DynamicPickTemplate 的职责

模板描述“如何抓、如何放、如何验证”，不保存运行时 cup world Pose。主要字段包括：

- identity：schema、policy、backend、execution allowance；
- planning：frame、group、joint names、TCP link、timeout、容差、速度/加速度 scaling；
- object：`plastic_cup` 和 `T_cup_tcp_grasp`；
- pick：pregrasp、micro-lift、lift 的 world-Z clearance；
- place：固定 place TCP、approach、retreat clearance；
- safety：workspace、source freshness、scene comparison tolerance。

模板不得包含固定 cup world Pose、固定 V1 pick joint waypoint 或隐藏 fallback。V1 的 `light_cup_wall_pick/v1` 文件和 hash 保持不变；V2 使用独立的 `dynamic_cup_pick/v1` schema v2。

## 5. 目标解析

`ResolvedMotionTargets` 覆盖全部 forward 和 recovery motion state：

| State | V2 target source |
|---|---|
| `MOVE_ABOVE_OBJECT` | perception grasp + pregrasp world-Z |
| `DESCEND` | perception grasp |
| `MICRO_LIFT` | perception grasp + micro-lift world-Z |
| `LIFT` | perception grasp + lift world-Z |
| `MOVE_ABOVE_PLACE` | template place + approach world-Z |
| `DESCEND_TO_PLACE` | template place |
| `RETREAT` | template place + retreat world-Z |
| recovery motion states | 显式映射到本次 resolved target |

所有目标必须在 workspace 内。两条相差 0.1 m 的合法输入应产生相差 0.1 m 的 pick-family target，证明位置来自感知而不是固定 waypoint。

## 6. 唯一状态机

```text
Fixed actions  --------------------+
                                   +-> StateMachineRunner -> SO101_WORKFLOW
DynamicStateAction + target source-+
```

`DynamicStateAction` 只负责把当前 `State` 映射为动态目标并调用 execution port。状态顺序、成功转移、失败转移和 recovery 都来自 `SO101_WORKFLOW`。V2 不建立并列 workflow。

完整成功轨迹为：

```text
IDLE -> PREPARE_OPEN_GRIPPER -> MOVE_ABOVE_OBJECT -> DESCEND
-> CLOSE_GRIPPER -> WAIT_GRASP_STABLE -> MICRO_LIFT
-> WAIT_MICRO_LIFT_STABLE -> VERIFY_PHYSICAL_GRASP -> ATTACH_MOVEIT
-> LIFT -> MOVE_ABOVE_PLACE -> DESCEND_TO_PLACE -> DETACH_MOVEIT
-> OPEN_GRIPPER -> WAIT_RELEASE_SETTLE -> VALIDATE_FINAL_PLACEMENT
-> SYNC_WORLD_OBJECT -> RETREAT -> DONE
```

## 7. MuJoCo 动态运动实现

SO-101 arm 只有 5 个独立关节，不能把通用 6-DoF IK 的任意结果当作可执行解。V2 使用 `UnderactuatedPoseIk`：

- 从安装的 URDF 构建 FK chain；
- 以实际 joint state 为 seed；
- 使用 damped least-squares 同时收敛位置与姿态；
- 解后重新计算 FK，超过 position/orientation residual 门槛则 fail-closed；
- 不读取 V1 waypoint 作为 seed 或替代解。

为避免长距离关节插值扫到 cup 或桌面，`DESCEND`、`MOVE_ABOVE_PLACE` 和 `DESCEND_TO_PLACE` 采用 perception-derived Pose interpolation，并对每个中间 Pose 独立求解。每段执行后读取 MuJoCo lossless evidence，校验 cup 位姿、速度、触点和力。

## 8. 碰撞与 Planning Scene

默认 Planning Scene 保持严格碰撞。仅在两个物理边界临时允许 `jaw/gripper <-> plastic_cup` 的窄 ACM pair：抓取 `DESCEND` 前应用并在 attach 完成后恢复；释放并把 cup 恢复成 world object 后，在 `RETREAT/RECOVER_RETREAT` 规划与执行期间应用，并在退离完成后立即恢复。这样既允许 gripper 从保守 cup 碰撞体中物理分离，又不扩大到其他 link、object 或状态；不允许全局关闭碰撞。

物理顺序必须是：

```text
真实闭爪和 micro-lift 成功
-> MuJoCo 证据证明 cup 随夹爪离桌
-> MoveIt shadow attach
-> 搬运
-> MoveIt detach/world sync
-> 开爪 -> release settle -> 最终放置验证
```

正常 forward 不创建 MuJoCo 虚拟 attachment。MoveIt attach 只是规划场景 shadow，不能替代物理抓取证明。

## 9. 物理证据门禁

每个关键 state 都保存 before/after evidence sample。至少检查：

- descent 前 cup 未被推走，且没有过早接触/超力；
- close 后触点和力在允许范围；
- micro-lift 后 cup 随 gripper 上升并满足离桌语义；
- transport 中 cup 持续随夹爪运动；
- release 后 cup 稳定落桌，指尖触点为零；
- final cup XY 在 place tolerance 内，线速度/角速度低于稳定阈值；
- upright tilt 只计算 cup 轴线相对 world-Z 的倾角，不把圆柱自身 yaw 当作倾倒；
- 最终 Planning Scene 无 attached cup，world 中 canonical cup 唯一且 geometry 完整；
- 三个 controller 在结束后仍为 active。

任何门禁失败进入状态机 recovery，并生成稳定 `DYNAMIC_*` failure code，不得改走 fixed 策略。

## 10. Backend 与模式矩阵

| backend | plan_only | execute |
|---|---:|---:|
| Gazebo | 支持，observe-only | 拒绝 `DYNAMIC_EXECUTION_NOT_QUALIFIED` |
| MuJoCo | 不作为当前验收入口 | 支持，必须同时给 `--mode execute --execute` |
| real / unknown | 拒绝 | 拒绝 |

MuJoCo execute 还要求 `scene_source=observe_only`、session id/reset epoch 一致、policy manifest 对 MuJoCo 显式 `execution_allowed: true`。

## 11. 测试用感知桥

本地 E2E 使用 `mujoco_cup_pose_bridge` 把 MuJoCo lossless ground truth 转成 `/cup_pose`，仅用于验证消费链路，不属于生产视觉节点。它证明 dynamic executable 的输入确实走 ROS topic、校验、冻结和动态解析；不能被表述为视觉算法准确率验证。

## 12. Evidence 与成功定义

动态执行写入 `so101-dynamic-mujoco-execute-v1` manifest，包含 source/session/reset/policy path 与 SHA、frozen `/cup_pose`、全部 targets、精确 state trace、state before/after physical sample、release marker、final samples、Planning Scene readback 和 failure/DONE。

一次成功必须同时满足：进程 exit 0、state trace 到 `DONE`、物理门禁通过、最终 cup 稳定落在目标区、Planning Scene 同步正确、controller readback active。只看到 topic、只完成规划、只保存截图或只打印 `DONE` 都不够。

## 13. 可执行与兼容性

- public executable 为 `fixed_cup_pick_place`、`dynamic_cup_pick_place`；
- generic `pick_place` console entry point 移除；
- launch composition 的固定路径调用 `fixed_cup_pick_place`；
- fixed executable 不 import dynamic ROS composition；
- dynamic executable 不读取 fixed pick/recovery waypoint；
- 两者都从 build 后 source 的 installed overlay 发现和运行。

## 14. 当前验收范围

V1 和 V2 都必须在本机 MuJoCo 环境各完成一次单杯 pick-place。V1 保留三阶段视觉证据；V2 至少保留 headless 数值成功证据，并在可见、已解锁的 macOS desktop session 中保留下降、搬运、最终状态截图。Gazebo 不在本轮验收范围。
