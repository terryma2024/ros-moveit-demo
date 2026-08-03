# SO-101 放置释放与偏置 Retreat 设计

## 背景

旧策略在放置后把夹爪恢复到 `q6=1.70`，随后直接沿原竖直路径抬升。Trial 3 的运行证据表明，杯壁会在夹爪全开和上撤早期再次接触 jaw/gripper；第一版“先侧下移、再回原路径”的修复也因过早横向合流触发 `TEMPORAL_CONTACT_NEGATIVE_AXIAL_PROGRESS`。

## 已验证行为

`pick_place_state_machine` 固化以下顺序：

1. `DESCEND_TO_PLACE` 到补偿后的落点。
2. `OPEN_GRIPPER` 分阶段打开到 `q6=0.750`，不恢复到原始全开 `1.70`。
3. 依次执行 `DETACH_GAZEBO -> DETACH_MOVEIT -> SYNC_WORLD_OBJECT`。
4. `RETREAT` 先把 TCP 朝底座方向轻微移动并下放，再保持侧向净空上升，只有到高位才与原 `ABOVE_PLACE` 终点合流。

`q6=0.750` 明显小于全开位置；对这条“一指在杯外、一指在杯内”的夹持拓扑，不把 pad gap 误当作杯子直径。实际净空由时序接触采样和最终 Gazebo 画面验收。

## Retreat 几何

放置终点 TCP 为 `[-0.069889681, -0.232459408, 0.207733946] m`。首个清障 waypoint 相对它约为：

- `dx=+1.20 mm`
- `dy=+3.96 mm`（朝机械臂底座）
- `dz=-1.98 mm`

之后使用 6 个关节 waypoint：首个侧下移、三个保持偏置的上升点、一个偏置高位点、最后在安全高位合流到原 `ABOVE_PLACE`。Retreat 速度和加速度缩放均为 `0.03`。

## 时序接触与安全门

- request-scoped ACM 只在本次 Retreat 规划中临时处理 `plastic_cup:jaw` 和 `plastic_cup:gripper`，不写入持久 Planning Scene。
- 前缀接触沿首段清障方向验证，净空阈值为 `0.0044 m`；超过阈值必须出现无接触样本，之后不得复现。
- 通用验证器保留 `TEMPORAL_CONTACT_*` 细粒度原因；Retreat 对外收敛为 `RETREAT_CONTACT_NOT_CLEARED`。
- 放置后仍要求杯子 stationary、两套 attachment 均为 false、MoveIt 无碰撞，终点回到原 `ABOVE_PLACE`。

## 支撑稳定性参数

为避免与 Retreat 无关的边界抖动破坏端到端复跑，运行证据还固化了：

- 5 个臂关节通用 trajectory/goal tolerance 为 `0.002 rad`；接触关键状态仍由独立 `0.00025 rad` 末端门约束。
- Gazebo detachable-joint 携带沉降门为 `5 mm / 0.070 rad`，仍严于绝对 attachment 倾斜上限 `0.087 rad`。
- 唯一一次 regrasp 的额外收紧量为 `0.006 rad`，但它只用于把杯壁重新坐入双侧接触：首次连续 6 个双侧样本后必须回到标定的 `q6_contact`，再取得第二组连续 6 个双侧、深度受限样本，之后才允许附着。
- `ATTACH_GAZEBO` 后的夹爪保持目标同样固定为 `q6_contact`，不把瞬时深 regrasp 固化进 detachable-joint；原生指垫干涉上限仍 fail-closed。

## 实机前边界

本策略只在 ai-station 的 SO-101 Gazebo/MoveIt 仿真栈验证。迁移到实机前必须重新标定夹爪开度、杯壁摩擦、底座方向和 TCP 清障位移，并设置力/速度限制；仿真 3/3 不代表实机安全性或成功率。

## 验收结果

- 远端 symlink-install 构建通过；覆盖 runtime、task3、motion validation、fixed targets、policy、MoveIt scene 与 configuration contract 的 8 个定向 CTest 全部通过。
- 冻结后的三次完整运行均到达 `DONE`，状态序列包含完整 release/detach/sync/retreat。
- 三次最终位置误差为 `2.218 / 2.124 / 2.844 mm`；平均 `2.396 mm`，最大 `2.844 mm`。
- 三次 Z 误差最大 `0.000098 mm`，杯子最终倾斜最大约 `0.000029 rad`。
- 每次最终 `gazebo_attached=false`、`moveit_attached=false`、`moveit_collisions=[]`。
