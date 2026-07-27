# SO-101 reset robot home 设计

## 目标

扩展 `reset_so101_world`：除了恢复 Gazebo 与 MoveIt 中的环境物体和 attachment
事实，还必须让 SO-101 的 arm 与 gripper 到达 SRDF 命名状态 `home`，并由独立
`/joint_states` 证据确认六个关节到位且静止。

Canonical home 定义为：

- arm：关节 `1..5 = [0, 0, 0, 0, 0]`
- gripper：关节 `6 = 0`

`fullopen`（`q6 = 1.7`）仅是 reset 过程中的安全中间状态，不是最终状态。

## 设计边界

`WorldResetCoordinator` 继续负责流程编排，不直接依赖 ROS 2 或 MoveIt 类型。新增：

- `IArmHomeAdapter`：以碰撞感知方式执行 arm home，内部必须显式 `plan → execute`。
- 复用 `ISO101GripperCommand`：发送 `fullopen` 和最终 `home` q6。
- 复用 `IJointPlanningBoundary::currentState()`：提供六关节位置、速度和观测时间。

生产 wiring 在 `reset_so101_world` 中创建这些 adapter。测试使用可控 fake，验证调用
顺序、失败短路和最终门控，不把 ROS 通信细节放进 coordinator。

## Reset 顺序

1. 获取 Gazebo、MoveIt 与完整六关节初始事实；任何证据缺失时无副作用失败。
2. 仅依据当前事实，分别解除 Gazebo 和 MoveIt attachment，并观察到 detached。
3. 命令 gripper 到 `fullopen=1.7`，等待 q6 到位且速度归零。
4. 使用 MoveIt Planning Scene 规划 arm 到 `home`；只有完整有效轨迹才能执行。
5. 执行 arm home，等待关节 `1..5` 到位且速度归零。
6. 恢复 table、pedestal、Coke 的 canonical pose，并确认 Gazebo/MoveIt 一致。
7. 命令 gripper 到最终 `home=0`，等待 q6 到位且速度归零。
8. 最终联合验证机器人与世界事实后返回成功。

该顺序保证夹爪不会在机械臂仍靠近 Coke 时先闭合，同时 arm 的回撤不会绕过碰撞
检查。Coke 在 arm 回 home 后才被传送至 canonical pose，避免物体重置穿过机械臂。

## 成功门控

- Gazebo Coke detached，且 Coke pose 为 canonical pose。
- MoveIt Coke detached、存在于 world；table、pedestal、Coke 位姿均为 canonical pose。
- Gazebo 与 MoveIt 的 Coke 6D pose 一致。
- arm 关节 `1..5` 分别在 home 容差内，速度均低于停止阈值。
- gripper 关节 `6` 在 `0` 的容差内，速度低于停止阈值。
- 关节证据完整、有限且新鲜。

Action 或 MoveIt API 返回成功本身不构成成功门控。

## 失败语义

- 初始观测失败：直接停止，不产生新副作用。
- attachment、gripper 或 arm 命令失败：立即停止，不执行后续步骤。
- arm plan 失败或轨迹不完整：不 execute。
- 动作成功但物理状态未在超时内收敛：返回对应 timeout/postcondition failure。
- Failure metrics 必须包含相关的 `expected_*`、`actual_*` 与速度值，便于现场诊断。

Reset 不进入 pick-place recovery 状态机；它自身采用逐步门控和 fail-closed 语义。

## 测试

单元测试至少覆盖：

- detached 初始状态下的完整安全顺序。
- 两种 attachment 当前事实及其按需 detach。
- gripper 先 fullopen、arm 再 home、世界复位、gripper 最终 home 的严格顺序。
- 初始 joint evidence 缺失时零命令。
- arm plan 失败时不 execute，且不继续世界/gripper final reset。
- 每个命令失败和每个收敛超时均会短路。
- 最终位置或速度不合格时失败信息带 expected/actual metrics。

集成验收从非 home arm、非 home gripper 和被扰动的 Coke 开始；运行
`reset_so101_world` 后，用 Gazebo、Planning Scene 与 `/joint_states` 三路独立证据验证
上述成功门控。
