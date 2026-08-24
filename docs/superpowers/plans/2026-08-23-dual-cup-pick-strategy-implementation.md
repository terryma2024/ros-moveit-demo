# SO-101 固定与感知 Cup Pick 双策略实施计划

**设计：** `docs/superpowers/specs/2026-08-23-dual-cup-pick-strategy-design.md`

**版本：** V2.2，V1 固定策略兼容 + V2 MuJoCo 动态执行
**源码基线：** `5407592100823bcfa43138611f8de6b0de0c93f8`

## 全局不变量

- V1/V2 共用 `StateMachineRunner + SO101_WORKFLOW`，不复制状态机。
- V1 policy 不修改；V2 任何失败都禁止 fallback。
- V2 在状态机前冻结一条合法 `/cup_pose`，整次运行使用同一输入。
- Gazebo V2 保持 plan-only；MuJoCo 是当前唯一 dynamic execute backend。
- 物理成功、Planning Scene 同步、controller active 和证据完整必须同时成立。

## Task 1：发布两个 executable

- [x] 新建 `cli/fixed_cup_pick_place.py` 和 `cli/dynamic_cup_pick_place.py`。
- [x] `setup.py` 发布两个入口并移除 generic `pick_place` entry point。
- [x] launch composition 的固定 workflow 改用 `fixed_cup_pick_place`。
- [x] tests 证明 fixed wrapper 不 import dynamic ROS 路径。

验收：installed overlay 同时列出两个入口；fixed policy SHA 不变。

## Task 2：动态领域模型和 policy

- [x] `CupPoseSample`、`DynamicPickTemplate`、`ResolvedMotionTargets`。
- [x] quaternion/Pose 刚体运算、workspace gate 和完整 state coverage。
- [x] strict schema v2 loader，独立 `gazebo.yaml` 与 `mujoco.yaml`。
- [x] A/B tests 证明 pick-family targets 随输入 Pose 变化。

## Task 3：`/cup_pose` source

- [x] pure validation port 与 ROS 2 subscriber adapter。
- [x] absolute deadline、invalid 不续期、world-only、freshness/future-skew gate。
- [x] 第一条合法样本冻结；持续诊断 subscriber 语义保持。

## Task 4：Gazebo plan-only 兼容

- [x] 只读 Gazebo/MoveIt observer 和 planning 前后 TOCTOU gate。
- [x] 单一显式 `--plan-only-state` Pose planning。
- [x] Gazebo execute 在 ROS 初始化前拒绝。

本轮不运行 Gazebo E2E。

## Task 5：接入唯一状态机的 MuJoCo execute

- [x] `application/dynamic_execute.py` 绑定全部 `SO101_WORKFLOW.action_states`。
- [x] runtime 组合 source、policy、runner 和 evidence。
- [x] MuJoCo execution port 实现所有 state action。
- [x] CLI 要求 `--backend mujoco --mode execute --execute` 双重显式授权。

## Task 6：5-DoF Pose 求解和分段运动

- [x] `UnderactuatedPoseIk`：FK、DLS full-pose solve、joint limit、residual gate。
- [x] descent、transport、place descent 使用 Pose interpolation 分段执行。
- [x] 每段从 live joint state 开始，禁止 V1 seed/fallback。

## Task 7：碰撞、抓取与释放门禁

- [x] descent 前临时放行 jaw/gripper 与 cup 的窄 ACM，attach 后恢复。
- [x] release 后仅在 `RETREAT/RECOVER_RETREAT` 期间放行同一窄 ACM pair，退离完成后立即恢复。
- [x] micro-lift 物理证明后才做 MoveIt shadow attach。
- [x] detach、open、settle、final validate、world sync、retreat 按 workflow 执行。
- [x] final upright tilt 忽略圆柱自身 yaw。
- [x] 所有物理失败使用稳定 code 并进入 recovery。

## Task 8：测试用 MuJoCo truth bridge

- [x] 从当前 session/reset epoch 的 lossless evidence 发布 `/cup_pose`。
- [x] 明确只用于 E2E，不作为生产视觉或感知精度证据。

## Task 9：验证阶梯

- [x] domain/source/policy/runner/IK/ACM/physical-gate tests。
- [x] 完整 package pytest：250 passed（最终回归）。
- [x] package colcon build、installed prefix/executable discovery、overlay precedence gate。
- [x] V1 MuJoCo GUI 端到端成功，保留三阶段截图和数值 readback。
- [x] V2 MuJoCo headless 端到端成功，完整 19-state transition 到 `DONE`。
- [x] V2 MuJoCo GUI 端到端成功，EXP-008 保留下降、搬运、最终三阶段截图。
- [x] 最终 rerun pytest/build/diff-check 并固化 140-file hash/size 清单。

## Task 10：macOS GUI 环境补齐

- [x] 固定 pinned fork overlay precedence。
- [x] 保护 GLFW primary monitor 空指针。
- [x] 保护无 primary monitor 时 CoreVideo VSync mutex 死锁。
- [x] 重新安装 `mujoco_vendor`、重建 fork，GUI 栈完成 model load，三个 controller active。
- [x] 在已解锁 desktop session 中完成 EXP-008 视觉证据采集。

## 完成条件

- fixed 和 dynamic 各有一次真实 MuJoCo 单杯 pick-place 成功；
- dynamic 输入、targets、state trace、physical samples、final scene/controller readback 完整；
- 无 V1 fallback、无第二状态机、无全局碰撞关闭；
- 可视化证据非全黑，且能辨认机器人、cup 和阶段；
- ledger 记录 retained、archived、deletion candidates；不自动删除证据。
