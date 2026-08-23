# SO-101 MuJoCo ROS 2 重复性资格验证

## 结论

冻结实现 `279e5b381406e09cae34ccbcef39ef7d63f00c0b` 已分别通过：

- 5 次连续 `FULL_RESTART`：每次使用独立 ROS domain、session 和新建的 MuJoCo/MoveIt/controller/Teleop stack。
- 5 次连续 `RESET_WORLD`：五次使用同一个 stack/session，reset epoch 严格递增为 1、2、3、4、5。

两组结果不能互相混算。每个计数运行都完成同一九阶段 production workflow，物理释放结果、MoveIt attached/world 状态、Planning Scene 同步、artifact SHA-256 和干净退出均通过。

## 冻结指纹

```yaml
source_commit: 279e5b381406e09cae34ccbcef39ef7d63f00c0b
dependency_sha256: 1df4cf0677b1d92ae1c64d2e2064fd4dd88d7e92111c74320e7170dd431fde6d
task_scene_sha256: a2a49391e52d1f885e8ebb4c85fd282d1e83f0ce82eb63e83bac645343b1f9a0
scene_sha256: b98eca6f2ae8547b8b7213625512ef360c5496c7ea2d124535698ea58b24e7c0
robot_mjcf_sha256: f87a033fab8cf7291e737519290a639e0310e703f8169288f075f3fe0c8b5aca
urdf_sha256: 0646707fbfb8fdfea5076afbf89f297027c0324465ab7ebe8129fc36c0445f4a
motion_policy_sha256: d39bbbed69c2376ddfb816a51bd8fd720dd82c55b17b1340f13e0d5d02b93808
contact_policy_sha256: 3b857d9663953a8f41382061b1c068798e3c54bc6d478eceebab0989ae331db1
```

## 无效批次

`TASK15-FULL-A`（EXP153–157）不计数。它以 `headless=true` 启动，必需的 Viewer camera preset 在没有 Viewer 时返回 HTTP 503；旧 runner 还把 reset 前的基础设施故障误标为有效失败并继续后四次。修复后：

- reset/workflow 前的 backend、camera、lease 或 provenance 故障归类为 `INVALID` 并立即终止批次；
- runner 等待 camera service、arm/gripper controllers 和 `SCENE_SETUP_OK`；
- clean shutdown 拒绝任何 child `process has died` 或致命信号。

无效 manifest SHA-256：`2cbef9d4cfe41ea748605e41afadb0195a83323ef1e2b454aeb12cc466536301`。

## FULL_RESTART：TASK15-FULL-B

```yaml
experiments: [EXP-158, EXP-159, EXP-160, EXP-161, EXP-162]
domains: [175, 176, 177, 178, 179]
attempt_count: 5
consecutive_successes: 5
qualified: true
reset_epoch_each: 1
manifest_sha256: 98c29b847cd40c5ca2061596739f8d66eaf96d3b4b1c707048371fb9773b6f11
runner_log_sha256: ac07e1163af6959620fb660c11334d0d62799638a15d6e5cf56e185f4c3176ac
```

五次最终杯子位置范围：x `[-0.079482, -0.078709] m`、y `[-0.248169, -0.247929] m`、z `[0.165105, 0.165503] m`；最大最终倾斜 `0.017537 rad`。每次 release 后 gripper contact=false、MoveIt attached=false、world object synchronized=true，且独立 stack 都有 ordered shutdown marker、return code 0、无 child death、无残留 owned process。

## RESET_WORLD：TASK15-RESET-A

```yaml
experiments: [EXP-163, EXP-164, EXP-165, EXP-166, EXP-167]
domain: 180
simulation_session_id: TASK15-RESET-A-reset
stack_restarts_between_runs: 0
reset_epochs: [1, 2, 3, 4, 5]
simulation_steps_after_reset: [0, 0, 0, 0, 0]
attempt_count: 5
consecutive_successes: 5
qualified: true
manifest_sha256: e49a6d2a4256c10d5a4d901620fc24429ea58a511f320f3178d857860e7e59dc
runner_log_sha256: bc7eecbf54d0e1a08989a82e03fc8dd072d220a709524f7184f251303cde8246
```

五次最终杯子位置范围：x `[-0.080387, -0.078681] m`、y `[-0.248402, -0.247193] m`、z `[0.164980, 0.165506] m`；最大最终倾斜 `0.017662 rad`。所有运行最大线速度为 0，最大最终角速度约 `1.12e-5 rad/s`。共享 stack 仅在第五次完成后退出，ordered shutdown、return code 0、无 child death/致命信号和 owned process 残留。

## 证据边界

- MoveIt 规划/执行成功不能替代 MuJoCo 物理结果。
- MuJoCo 杯子位姿不能替代 Planning Scene world/attached readback。
- GUI 只能作为可视佐证，不能替代 typed physical outcome、reset receipt、artifact hash 或退出状态。
- 未使用 weld/equality/adhesion/mocap、物体 teleport、直接 object qpos/qvel 写入或隐藏重试。

## 剩余范围

RGB-D 感知、VLM/目标检测和 Teleop Web UI 的进一步重构不属于本资格验证。

## 最终门与视觉复核

最终 clean gate：MuJoCo pytest `365 passed, 4 skipped`；Ruff 109 files；Teleop Vitest 45/45；colcon `857 tests, 0 errors, 0 failures, 6 skipped`。fork runtime、reset runtime、双 isolation gate、protected Gazebo 零差异和 `git diff --check` 全部通过。

不计数的 EXP168 使用独立 domain 181/session 完成同一 production workflow，并保留终态供 `codex-cua` 的 fresh snapshot 检查。原始 5120×2880 画面确认 RViz 左、MuJoCo 右、Viewer Running、机器人/基座/桌面/杯子/红圈均可见、杯子位于红圈内、夹爪打开且机械臂退开；RViz 同时显示 robot 与 Planning Scene table/cup/pedestal。截图 SHA-256：`c5ffd4865cd33966f3f888513ad362572af76c5d3bb9e2f13fab0b11d7b936a0`。

EXP168 随后按精确进程组 SIGINT 关闭，launch return code 0、ordered shutdown marker 存在，无 child death、致命信号或 owned process 残留。
