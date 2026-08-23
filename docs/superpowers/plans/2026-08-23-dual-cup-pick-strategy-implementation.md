# SO-101 固定与感知 Cup Pick 双策略实施计划

**设计：** `docs/superpowers/specs/2026-08-23-dual-cup-pick-strategy-design.md`
**目标：** 在不改变固定抓取基线的前提下，发布 `fixed_cup_pick_place` 与 `/cup_pose` 驱动的 `dynamic_cup_pick_place`。
**执行边界：** 动态路径从 pure tests 开始，仅在完成独立证明后逐级开放；本计划不授权真实硬件。

## 全局不变量

- V1 和 V2 是两个显式 strategy，任何错误、超时或缺失输入都不得自动跨策略回退。
- V1 固定 motion-policy v1 的行为、SHA、waypoint ladder 与既有资格结论保持不变。
- V2 topic 仅在状态机副作用前读取一次并冻结；执行期间不静默重规划。
- 默认 `world` frame 和 `observe_only` 场景权威；TF 与 topic-driven scene reset 是后续独立任务。
- V2 在计划、执行、证据和 qualification 上与 V1 独立统计。

## Task 1：冻结 V1 为 `fixed_cup_pick_place`

**文件：**

- 修改：`src/so101_demo_py/setup.py`
- 修改：`src/so101_demo_py/src/cli/pick_place.py` 或新建薄 wrapper
- 新建：`src/so101_demo_py/test/test_fixed_cup_pick_place.py`

**实现：**

1. 注册 `fixed_cup_pick_place = so101_demo.cli.fixed_cup_pick_place:main`。
2. wrapper 调用现有固定 path；不得 import `rclpy`、`CupPoseSource` 或 dynamic policy。
3. 统一 `argparse.prog` 与 manifest `strategy=fixed`。
4. 明确移除或弃用 generic `pick_place` entry point；不可同时保留未标记的第三条 public 策略入口。

**RED：** 测试新 entry point 存在、固定策略不订阅 topic、并且同一 fixed fixture 生成相同 waypoint/state result。
**GREEN：** V1 定向 tests、现有 fixed policy tests、`colcon build --packages-select so101_demo_py --symlink-install`。

## Task 2：实现纯 DynamicPickTemplate 与 DynamicPickPlan

**文件：**

- 新建：`src/so101_demo_py/src/core/dynamic_pick.py`
- 新建：`src/so101_demo_py/src/core/dynamic_pick_policy.py`
- 新建：`src/so101_demo_py/test/test_dynamic_pick.py`
- 新建：`src/so101_demo_py/test/test_dynamic_pick_policy.py`

**实现：**

1. 定义 `CupPoseSample`、`DynamicPickTemplate` 和 `DynamicPickPlan` 为 frozen dataclass。
2. 实现有限数、四元数正规化、刚体 Pose composition 与 world-z offset。
3. 实现 workspace、source age 和 template 标量约束校验。
4. loader 仅接受 schema v2，不能调用 `load_task_policy()` 偷读 V1 waypoint。

**RED：**

- 输入 cup x 增加 0.1 m，三个 TCP 目标 x 都必须增加 0.1 m；
- 位置/四元数非法、零四元数、越界、过期值均抛确定错误；
- 四元数与姿态 composition 的 fixture 覆盖非 identity rotation。

**GREEN：** pure Python tests 完全通过；无 `rclpy` import。

## Task 3：建立 dynamic policy registry

**文件：**

- 新建：`src/so101_demo_py/config/policies/dynamic_cup_pick/v1/manifest.yaml`
- 新建：`src/so101_demo_py/config/policies/dynamic_cup_pick/v1/gazebo.yaml`
- 新建：`src/so101_demo_py/config/policies/dynamic_cup_pick/v1/mujoco.yaml`
- 新建：`src/so101_demo_py/config/policies/dynamic_cup_pick/v1/real_stub.yaml`
- 修改：`src/so101_demo_py/src/core/policy_registry.py` 或新建独立 dynamic registry
- 新建：`src/so101_demo_py/test/test_dynamic_pick_registry.py`

**实现：**

1. 固定 policy 与 dynamic template 使用不同 schema/type，禁止一个 loader 猜测另一个类型。
2. manifest 为每个 backend 提供独立 hash 和 qualification status。
3. `real_stub` 明确 `execution_allowed: false`。
4. 静态夹爪、place、安全与接触参数必须显式声明来源，不复制未审阅常量。

**验收：** manifest identity、hash mismatch、未知字段、错 backend、缺少 variant 均 fail-closed；现有 v1 registry tests 不变。

## Task 4：实现一次性 `/cup_pose` preflight source

**文件：**

- 新建：`src/so101_demo_py/src/ports/cup_pose_source.py`
- 新建：`src/so101_demo_py/src/ros/cup_pose_source.py`
- 修改：`src/so101_demo_py/src/cli/cup_pose_subscriber.py`，复用纯校验而不改变其持续监听语义
- 新建：`src/so101_demo_py/test/test_cup_pose_source.py`

**实现：**

1. 定义 `CupPoseSource.get_one(timeout_s) -> CupPoseSample`。
2. ROS adapter 订阅 `/cup_pose`，无效消息输出单行 `CUP_POSE_INVALID` 并继续等待。
3. V2.1 只接受 `frame_id=world`；错误 frame 返回 `CUP_POSE_TF_UNAVAILABLE`。
4. 当收到第一条有效、未过期、在 workspace 内的消息时停止订阅并返回冻结 sample。
5. 所有清理路径以 `rclpy.ok()` 防止重复 shutdown。

**RED/GREEN：** 使用 fake receive/spin/clock 测试无消息、连续无效、有效后停止、过期和 world-frame gate；已有 `cup_pose_subscriber` 测试必须保持通过。

## Task 5：实现 V2 motion executor 与 workflow

**文件：**

- 新建：`src/so101_demo_py/src/application/dynamic_pick_workflow.py`
- 新建：`src/so101_demo_py/src/backends/gazebo/dynamic_workflow.py`
- 新建或修改：MoveIt `RobotControlPort` adapter
- 新建：`src/so101_demo_py/test/test_dynamic_pick_workflow.py`
- 新建：`src/so101_demo_py/test/test_dynamic_gazebo_workflow.py`

**实现：**

1. 新 workflow 对 `MOVE_ABOVE_OBJECT`、`DESCEND`、`LIFT` 调用 `plan_tcp_motion`，不调用 V1 `state.waypoints`。
2. 每段只在 `PlanResult.accepted` 后允许 `execute`；失败保留 `CUP_POSE_PLAN_FAILED` 和 planner error code。
3. gripper、attachment、scene、recovery 与既有状态词汇可复用，但动态 path 必须显式传入 `DynamicPickPlan`。
4. V1 `execute_gazebo_workflow()` 不修改；动态 implementation 新建为并列文件。

**验收：** mock `RobotControlPort` 验证 pregrasp/grasp/lift 依次作为 TCP request 发送；任一规划失败时后续 gripper/attachment 未被调用。

## Task 6：加入场景一致性 preflight

**文件：**

- 新建：`src/so101_demo_py/src/application/cup_pose_preflight.py`
- 新建：`src/so101_demo_py/test/test_cup_pose_preflight.py`
- 只在后续显式授权时修改：Gazebo/MuJoCo scene reset adapter

**实现：**

1. 默认 `observe_only`，读取 simulator cup Pose 与 MoveIt world object Pose。
2. 在可配置 position/orientation tolerance 内同时匹配才允许进入 planning。
3. mismatch 返回 `CUP_POSE_SCENE_DIVERGENCE`，无任何 arm/gripper/attachment action。
4. `scene-source=topic` 不在本任务实现；如后续批准，必须按 simulator write/readback → MoveIt upsert/readback 的独立 reset transaction 实现。

**验收：** topic、simulator、MoveIt 任意一对不一致均拒绝；完全一致才调用 dynamic planner。

## Task 7：发布 `dynamic_cup_pick_place`

**文件：**

- 新建：`src/so101_demo_py/src/cli/dynamic_cup_pick_place.py`
- 修改：`src/so101_demo_py/setup.py`
- 新建：`src/so101_demo_py/test/test_dynamic_cup_pick_place.py`
- 修改：运行 manifest writer 与相关 application config

**CLI：**

```zsh
ros2 run so101_demo_py dynamic_cup_pick_place \
  --backend gazebo \
  --mode plan_only \
  --cup-pose-timeout-s 5 \
  --dynamic-policy <installed-policy-path> \
  --scene-source observe_only
```

**实现：**

1. 新 CLI 是唯一拥有 ROS node、CupPoseSource、preflight 和 dynamic workflow composition 的入口。
2. 只有 `--mode plan_only` 可在首次发布时运行；`--mode execute --execute` 在 dynamic qualification 完成前拒绝。
3. manifest 写入 `strategy=dynamic`、topic input、template hash、TCP targets、scene readback、backend/session/reset provenance。
4. `fixed_cup_pick_place` 和 `dynamic_cup_pick_place` 都必须出现在 package executable discovery；旧 generic entry point 的行为按 Task 1 决议验证。

## Task 8：分层验证与 qualification

### 自动化

1. 全部 V1 fixed regression。
2. Dynamic pure/registry/source/preflight/workflow/CLI tests。
3. 输入 A/B：发布或 fake 两个相差 0.1 m 的 world Pose，断言 TCP targets 和 planner request 同样变化 0.1 m。
4. V2 无 topic、坏 topic、TF/frame、scene mismatch、IK/plan failure：断言零 arm/gripper/attach 调用。
5. `git diff --check` 与 package build。

### Runtime 阶梯

1. Gazebo `plan_only`：保存 topic、MoveIt plan、joint/TF 起终点、scene readback。
2. Headless dynamic execute：只在 plan-only 通过且新实验账本为 `PLANNED` 后进行。
3. GUI dynamic execute：保存新鲜 Gazebo/RViz 截图、cup pose/contact、MoveIt attachment/world membership。
4. 完整重启下的动态 qualification 另开批次；V1 固定路径的成功次数不得计入。

## 完成条件

- 两个 executable 都可由安装 overlay 发现，且策略互不回退。
- V1 的 fixed regression 没有行为变化。
- V2 对有效 `/cup_pose` 生成不同的动态 TCP target，并完成 plan-only A/B 证据。
- V2 所有输入/场景/规划失败均在副作用前 fail-closed。
- execute、物理和真实硬件结论只在各自独立验收通过后声明。
