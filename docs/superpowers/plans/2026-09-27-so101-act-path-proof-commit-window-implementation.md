# SO-101 ACT PathProof 与提交窗口实施计划

> **执行方式：** 当前 Codex 单写者使用 GPT-6 Sol inline；每项先 RED 再 GREEN。不得启动 `dst` 或第二执行者。

**目标：** 将 broker 的三次完整路径检查改为一次 `PathProof` 和严格的一次性提交窗口，并在正式控制前证明时间轴、状态和实际双目标与 proof 一致。

**架构：** 保留现有 MuJoCo checker 的 2 ms / 2 mm / 701 样本语义。broker 把旧绝对 prefix 转成相对路径合同，完整 checker 只执行一次；proof 留在 broker 内，permit 和 exact goals 只做可审计的身份、状态、时间和内容复核。真实硬件频率资格与 MuJoCo 500 Hz 动态资格各自独立，不由此代码路径直接授权。

**技术栈：** Python 3、ROS 2 Jazzy、MuJoCo 3.12、pytest-xdist、colcon。规格：[路径证明与控制频率规格](../specs/2026-09-27-so101-act-path-proof-control-rate-design.md)。

## 全局约束

- 当前 worktree、branch、唯一 evidence root `/data/work/so101-evidence/act-data/20260924-fbc25063-resume` 不变。保留所有现有 dirty 文件和证据。
- `PathProof` 保留 2 ms grid、2 mm clearance、完整 701 样本、速度/加速度/terminal-stop 和 phase allowlist。不得重启 EXP-469 的 16-lane 性能程序。
- policy/action 与 camera 为 10 Hz；100 Hz joint/evidence 和 500 Hz MuJoCo physics/controller 都需要动态门禁。真实六舵机串口先按待实测 30 Hz 基线、60 Hz 候选处理。
- 任何 proof、状态、permit、goal 或双 action acceptance 不一致即 fail closed。没有正向授权的 APPROACH source 时不能接线到生产目标。
- 本计划不执行真实机械臂写入或运动。被动串口读测试也须先完成设备/API 只读审计；涉及 goal/torque 的测试仍需独立明确授权。
- 正式 accepted Train/Validation/Offline Test 继续为 0/0/0；W2 后直接独立 40 场景 W8，资源瓶颈停下，不改 W4/W6。

## 审阅重点

- Policy observation 已老化而物理 snapshot 刚刷新：仍因 `A_policy` 超限拒绝；不能重置 policy 时钟。
- MuJoCo step 使 cup/qvel 或 reference 发生微小变化：首版 exact equality 拒绝，不能加经验容差。
- bridge→start 间隔在提交时改变：即使目标 rows 相同也拒绝，防止时间平移遗漏 bridge。
- arm 已接受但 gripper 未接受：取消已接受目标并验证停止，proof 与 attempt 一并关闭。
- ROS goal 序列化与内存中的位置数组不同：以准备送往 action client 的规范 goal 内容为准，拒绝未枚举差异。

## 文件职责

| 文件 | 职责 |
| --- | --- |
| `src/so101_demo_py/src/act/path_proof.py` | 相对路径、规范编码、proof 结果与一次性生命周期；不导入 ROS/MuJoCo |
| `src/so101_demo_py/src/adapters/act/physics.py` | 只在证明阶段调用原 checker，返回首违规与 701 点证据；不管理 permit |
| `src/so101_demo_py/src/act/permits.py` | broker 内绑定 proof、代际和新鲜状态；consume 不重跑完整 checker |
| `src/so101_demo_py/src/act/execution.py` | 从 proof 相对 grid 生成新绝对双目标，提交前逐字段比对并等待双接受 |
| `src/so101_demo_py/src/adapters/act/calibration_motion.py` | 采集完整 qpos/qvel、bridge/reference/phase/contact scope，复核现场；保留运行时安全门 |
| `src/so101_demo_py/src/adapters/act/broker_execution.py` 与 `src/so101_demo_py/src/cli/act_command_broker.py` | 唯一 broker owner 的 proof 路由与实际生产入口绑定 |

### 1. 相对路径与时间来源

**测试：** `src/so101_demo_py/test/test_act_path_proof.py`。写一个旧绝对 prefix 的例子，证明 materialized 目标只改变共同起始时间，`positions`、各 `τ_i` 和 bridge→start 间隔完全相同；原 policy observation 时间保持不变。另测 NaN/Inf、错误 joint order、被篡改 offset 和 `A_policy` 过期均拒绝。

- [ ] 写 RED 测试，指定 `RelativePathRequest.from_prefix(prefix, bridge_time_s, start_time_s, ...)` 与 `materialize(start_time_s)`；使用真实 `validate_action_prefix` 进入证明前边界。
- [ ] 用已核验的 task Python、此前不存在的 `/data` NVMe scratch 运行定向 pytest，保存命令、退出码和预期失败。
- [ ] 实现 `act/path_proof.py` 的规范输入与相对时间合同；原 prefix 哈希和 policy observation receipt 是不可变来源，materialized prefix 是另一种受验证的类型。
- [ ] 运行相同定向测试至 GREEN，再跑 `test_act_contracts.py` 与 `test_act_execution.py` 的相关测试；保留结果。

### 2. 一次完整 MuJoCo proof

**测试：** 扩充 `test_act_physics.py` 与 `test_act_path_proof.py`。原 checker 与相对时间路径在相同 immutable fixture 上逐样本对照；safe、首/中/末违规、2 mm 两侧、robot-only、held-cup-only、allowed→forbidden 和 NaN/Inf 必须同判。每次正向 proof 的完整样本数恰为 701；worker crash/timeout 不生成 proof。

- [ ] 写 RED 测试，冻结 checker 输入中的完整 measured model `qpos/qvel`、phase、holding、attachment、controller bridge/reference、model/profile/policy 与 owner generation/epoch。
- [ ] 在独立 NVMe scratch 中运行定向测试，确认失败发生在缺少 proof/相对时间功能的目标边界。
- [ ] 让 `MujocoPathProcess` 对同一相对曲线只检查一次；保留原路径 oracle，返回带第一违规和 monotonic 耗时的 typed `PathProof`。
- [ ] 重跑定向测试；对不全的 parity 标记未通过，不能仅凭 safe fixture 晋级。

### 3. broker 一次性所有权与现场复核

**测试：** 扩充 `test_act_permits.py` 和 `test_act_command_broker.py`。同一 proof 的 checker 调用数为 1；approve 后改变 snapshot/model/policy/profile/phase/holding/attachment/reference/prefix、ticket/generation/epoch 的每一种情况都拒绝。重放、过期、worker loss、reset/cancel/unknown goal 也拒绝。

- [ ] 写 RED 测试：proof 留在 broker 私有 registry，不在公开 permit 中暴露可伪造的 `safe`；consume 原子化并销毁单次权利。
- [ ] 用新 scratch 跑目标测试，确认当前重复 `check_port` 调用和不完整状态绑定造成预期失败。
- [ ] 改 `PermitAuthority` 和 `BrokerPairedExecution`，加入证明后新鲜现场读回、规范等价比较和严格失效；不把昂贵 MuJoCo 检查放进锁里。
- [ ] 重跑目标测试；同步验证 revoke 能抢先于阻塞中的 checker 返回。

### 4. 双目标实际发送与提交时序

**测试：** 扩充 `test_act_execution.py`、`test_act_controller_reference.py` 和 ROS wire 测试。materialized 目标的 joint order、rows、offsets、绝对 stamp 与 proof 逐项一致；reference 不匹配、单侧提交/接受、接受到达 `T0` 或之后、时钟跳变、freshness/抖动余量不足均失败，发送过的目标需取消并确认停稳。

- [ ] 写 RED 测试覆盖两段时间不等式、首请求与尾部耗时记录，证明 `A_policy` 包含 proof 计算时间。
- [ ] 在新 scratch 中确认 RED 是提交边界拒绝缺失，而非 ROS 收集或依赖问题。
- [ ] 改 `ActExecutionAdapter`、`RosCalibrationMotionGuard.check_exact_goals` 和 broker 接线：先新鲜读回，后生成 `T0` 与两个 exact goals；只做 proof/goal/状态复核，不重复 701 点检查。保留停止、取消和 unknown-goal fence。
- [ ] GREEN 后运行相关执行/物理/permit 测试与实际序列化断言；失效时不自动重试。

### 5. 生产入口与独立频率资格

**测试：** 实际 `act_command_broker` 入口的 source/installed 对照。没有 source authority 的 APPROACH 仍无 command authority；正式绑定存在时才可从该入口拿到 proof-bound permit。另用无运动 MuJoCo stack 验证真实 physics step 与 controller update 的 2 ms 连续性、wall/sim jitter、missed tick 和长时 RTF，不能由 YAML 宣称通过。

- [ ] 给生产入口写 RED 集成测试，确认 `approve → consume → exact goals → 双接受` 只用一次完整 checker，且任意状态漂移失败；旧诊断入口不能绕过。
- [ ] 完成 source gate 后跑各模块完整普通 pytest `-n min(8, CPU)`，并在正确 overlay 上 build、installed package test、运行产物来源读回；每次 pytest/colcon 使用全新 `/data` scratch 和 `TMPDIR/TMP/TEMP` 证明。
- [ ] 只有上述门禁通过、原 policy 来源确实可绑定、物理停止及 owner/epoch 证据齐备，才另立隔离无运动动态验证；否则记录 blocker，不发送 goal。
- [ ] 真实串口先做只读 API/设备审计。审计证明连接和 `sync_read` 不会隐式写入后，另立每档预热 10 s、测量至少 60 s 的 30/60 Hz passive-read 试验；仅按规格提出的 provisional acceptance 判定，不从被动读推断闭环写入资格。

每项的命令、退出码、provenance、证据 SHA 和状态记入当前实验账本。生产入口和仿真动态门禁都未完成前，不做 Task 8 readiness、W2/W8 或正式数据收集的成功声明。
