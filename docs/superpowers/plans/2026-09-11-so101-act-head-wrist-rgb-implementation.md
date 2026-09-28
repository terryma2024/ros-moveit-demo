# SO-101 Head/Wrist RGB ACT Implementation Plan

> **2026-09-24 refresh:** [Task 8 live and formal collection design](../specs/2026-09-24-so101-act-task8-live-formal-collection-design.md) is approved and incorporated below. MuJoCo is the only simulator; campaign resource binding is checked once at admission; W2 proceeds directly to one independent 40-scene exact-W8 qualification, without W4/W6. This plan supersedes the earlier Task 7A–11A wording.

> **2026-09-28 refresh:** [Task 8 artifact preparation design](../specs/2026-09-28-so101-act-task8-artifact-preparation-design.md) is approved and incorporated as Tasks 8P1–8P4 and 8L. Task 8 core and all later source-changing collection tasks are completed, committed and installed before the final runtime identity is frozen; Task 8 live cannot start until a self-contained bundle has an atomically published `preparation-receipt.json` and production admission accepts it.

> **For execution:** follow the repository model rule: run implementation with DeepSeek Harness TUI (`dst`) in a dedicated ai-station `tmux` session, one reviewed task boundary at a time. This document update does not start that execution. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 MuJoCo 中实现双 RGB、独立颈部搜索、MoveIt 示教和 ACT 无干预 pick-place，并在单次 120 s 内完成撤离与物理验收。

**Architecture:** ACT 输入仅为双 RGB 和 8 维状态，输出 6 维绝对位置目标。搜索、动作执行和物理监督各自拥有明确接口，ROS/控制器与 MuJoCo 真值留在 adapter 边界。Task 8 core 完成后，独立的 artifact preparation 层先生成 source provenance、collection config、测量合同、确定性校准报告和自包含 bundle；receipt 原子发布后，`UnifiedWorkloadService.start(spec)` 才做一次 production admission 并返回不可变 `AdmittedCampaignContext`。每个 Worker 只通过 typed `WorkerPort` 驱动唯一 ROS execution child。MoveIt 示教采集复用 `main` 的 fixed exact-N v3 shared queue、Worker 私有 Recorder 和确定性 Coordinator；正式采集固定 W8，不自适应降档。最后从 verifier 认可的不可变数据导出训练、接入执行与封存测试。

**Tech Stack:** Python、ROS 2 Jazzy、MuJoCo、MoveIt 2、ros2_control、C++ CameraPlugin、LeRobot/PyTorch、fixed exact-N v3 shared queue、fsync journal、有界 IPC、React/TypeScript/Bun。

**Specs:** [SO-101 双 RGB ACT 设计](../specs/2026-09-10-so101-act-head-wrist-rgb-design.md)；[Task 8 live 与正式采集设计](../specs/2026-09-24-so101-act-task8-live-formal-collection-design.md)；[Task 8 准入工件生成设计](../specs/2026-09-28-so101-act-task8-artifact-preparation-design.md)。执行者必须先读三份设计和本计划；校准项由测量工件提供，不把测试示例数值用于实际控制。

## Global Constraints

- 保留 V5-T001～V5-T005 的 Agent、感知与几何规划链路；本计划对应 V5-T006～V5-T010，不写学习者进度。
- 两相机首版统一为 `640×480`、RGB、10 Hz。head/wrist 不创建 Depth topic；task_camera 保留既有 RGB-D。
- `observation.state` 为 `[q1,q2,q3,q4,q5,q6,sin(neck_yaw),cos(neck_yaw)]`；`action` 为 `[q1_target,…,q6_target]`，单位 rad。
- ACT 不读取 `task_camera`、Depth、`/cup_pose`、TF、Planning Scene、物体真值、接触或教师内部阶段。
- neck 独立 controller，不加入手臂 MoveIt planning group；搜索完成后锁定，ACT 运行中不追踪转头。
- `act_timeout_s=120`（2 分钟），从首次推理前开始用单调墙钟计时，包含等待、抓放、撤离和最终检查；不得暂停或刷新计时。
- 非法动作拒绝并留证，不静默裁剪；监督器只批准、拒绝、停止与交接，不替 ACT 生成抓放动作。
- Train 50、Validation 10、Offline Test 10 个成功 episode；Rollout Validation 至少 10 个固定初始条件；Rollout Test 至少 10 个封存初始条件。
- 首版只并行 MoveIt 专家示教采集；ACT 闭环验证和封存测试仍按单场景独立执行。资格/扩容 episode 不进入正式训练数据。
- 仿真后端只允许 MuJoCo。配置、依赖或请求出现 Gazebo 时入口 fail closed；不实现 Gazebo adapter、topic/service、truth 或回退路径。
- Linux 新执行只使用 `ParallelRuntimeConfigV3`、`BatchRequestV3` 和 fixed exact-N shared queue。ACT 先通过 W1 smoke、同一八场景的完整 W1/W2 功能资格，再直接运行一份独立 40 场景 exact-W8 持续负载资格；不测试 W4/W6，也不把 W8 写成项目永久全局默认值。
- 每个采集 batch 固定 exact N。业务失败形成不可重试的 `FAILED` scenario 终态；基础设施失败只允许在相同 W8、manifest、runtime/collection config、contact policy 与 campaign 数据身份下显式恢复。恢复使用新的 resource binding/generation，不得改变业务输入或跨 N fallback。
- Web 和 headless CLI 共享 `UnifiedWorkloadService.start(spec)`。服务在创建任何 Worker、Recorder、Broker 或 ROS child 前一次性核验 `GlobalMutationArbiter`、物理 GPU lease、MuJoCo-only、manifest/config/policy hash、资格记录与 cleanup fence，并签发不可变 `AdmittedCampaignContext`。资源绑定不穿透到内部组件重复验证。
- campaign owner 负责 lease heartbeat、fencing、runtime telemetry 和 owned cleanup。Worker、Recorder、Broker、Task 8 phase runner 与 ROS child 只消费 context 中的业务身份和审计字段，不查询 arbiter，也不把运行期资源采样当作第二套 authority。
- 单 stack、并行采集、共享教师执行与训练必须共同使用按稳定 host identity + 物理 GPU UUID 持久化的 `ActGpuWorkloadArbiter`。authority 在 admission 时解析 selector 与可见性映射，歧义或漂移 fail closed；lease 原子领取并由 campaign owner 保持到 cleanup/release proof，只读 GPU 进程检查不是互斥。
- 接触 analyzer 只能产出 disabled proposal。`POLICY_FINGERPRINT` 必须是 canonical policy payload bytes 的 SHA256；proposal envelope hash 不是批准对象。只有用户批准精确 fingerprint 并生成独立 activation receipt 后，Task 8 live、W8 资格和正式采集才可启动。
- Task 8 live 只接受同一最终 bundle 目录下的八个启动工件：七个业务工件加 `preparation-receipt.json`。receipt 是 bundle 的唯一提交标记；缺失、hash 不闭合、存在未登记依赖或旧 evidence 不可用时无法独立验证，均在 production admission 创建进程前拒绝。
- Task 8L 是 B 批次全部 source-changing 代码（截至 Task 11A）提交并通过代码门后的最终 runtime gate。冻结 provenance 后若任何受控源码、submodule、installed role、runtime/collection config 或 policy identity 改变，当前 bundle、Task 8 live 结果和 `QUALIFIED` 全部失效，必须从 Task 8L Step 1 以新 run root 重做，不能补写或复用旧结果。
- Task 8 head-search runtime 与 `parallel_batch_v3.yaml` 都必须请求 CUDA 并设置 `allow_cpu_fallback=false`。资源不足时停止等待人工决策，不得切换 CPU。Recorder 每 Worker 使用 `capacity=16`、`high=12`、`recovery=8`，深度到 16 立即失败，连续 0.2 s 不低于 12 也停止新业务。
- W8 资格遇到 CPU/GPU/RAM、磁盘、MuJoCo RTF、Recorder queue、10 Hz frame gap、吞吐、物理成功率或 QC 门槛失败时立即停止，等待人工决策；不得自动降 Worker、换设备、降画质、降采样或用低档结果续算。
- 旧 `/data/work/so101-evidence/act-data/0917a` 已丢失。分支 commit 只能恢复源码，不能恢复 episode、QC 或训练资格；新采集使用新的 dataset/run ID 与 evidence root。
- 训练只消费 coordinator journal commit 引用且 verifier 通过的正式数据；资格、surplus、失败、迟到 seal、目录扫描结果与旧 0917a 均不得导入。训练与采集/Broker GPU 负载串行。
- V5-T009 首次无干预成功率至少 70%；V5-T010 至少 20 个共享测试场景。搜索失败进入端到端分母，恢复另计干预。
- 目标平台是 macOS 与 ai-station/Linux，分别验证；实体机械臂迁移属于 V6，本计划不授权实机动作。
- 不运行无关 `benchmark_test`；普通 Python 包测试只收集 `src/so101_demo_py/test/`。
- README 使用英文；中文指南使用 `humanizer-zh`；教学指南放 `docs/guides/`。本计划不改 README、课程或个人进度。
- 不使用 `gh`、force-push、`ament_uncrustify --reformat`；下列 commit 步骤只提交本任务明确列出的文件，不自动 push。

---

## 范围、基线与交付顺序

建议把后续执行拆为三个审阅批次：A 相机/搜索与接触策略（Task 1–6A）、B 执行安全、准入工件与数据（Task 7、7A、8、8P1–8P4、9–11、11A、8L）、C 训练/产品接入/验收（Task 12、12A、13–16）。本总计划保持一份，避免跨文件接口漂移。2026-09-28 把 Task 8 的代码交付与 live 验收拆开：软件交付顺序固定为 Task 6A→7→7A→8 core→8P1→8P2→8P3→8P4→9→10→11→11A；全部受控代码提交并通过 package/full gates 后冻结并安装唯一 HEAD，再执行 Task 8L；Task 8L 通过后才按 W1→W2→独立 40 场景 exact-W8 资格→正式 W8 采集推进，最后进入 Task 12。策略未激活、bundle 未提交或 production admission 未通过时，不得开始 Task 8 live；W8 未通过不得开始正式采集。A 的输出是可搜索、锁定并具有已批准接触策略的 MuJoCo 仿真；B 的输出是有安全门控、可重放且完成 exact-W8 资格的示教管线；C 的输出是经过封存测试的 ACT 系统。

原计划编写基线为 `0fbef11441e7eb541854b367a21b38dc354c43ac`。上一次 ACT 实现分支的可恢复末端为 `e2ec28c33ecaa455045477185b9c5dbc5e367538`；旧数据和运行 evidence 不可恢复。2026-09-24 文档更新对照的 ai-station `main` 为 `fd7348aa27361750f7e2e7954df53ef75e96545c`。执行者必须先把该分支 rebase 到现场最新 `main`，记录冲突与新 HEAD，再按更新后的任务边界审计已有实现。哈希只标识本轮现场基线，执行时仍需读取实际 HEAD、dirty files 和两远端状态。路径均相对仓库根。

已核实的集成点：

- `src/so101_demo_py/setup.py` 将 `src/` 映射为 `so101_demo`，自动安装 assets/config/launch；这是 ament_python 包，没有该包的 CMakeLists.txt。
- `src/so101_demo_py/src/runtime/launch_composition.py` 的 `_render_mujoco_robot_description` 和 `_mujoco_stack_actions` 当前读取固定 MuJoCo 资产与配置。增加显式 ACT profile，默认路径保持兼容，不复制整套大 launch 文件。
- `src/so101_demo_py/src/backends/mujoco/reset.py` 的 `MujocoResetClient` 当前要求六维状态；`client.py` 的 `latest_joint_positions`/`joints_converged` 也需要一起检查，不能只去掉长度断言。
- `src/so101_demo_py/config/mujoco/ros2_controllers.yaml` 使用独立的五维 arm 和一维 gripper JointTrajectoryController。
- CameraPlugin 位于子模块 `third_party/mujoco_ros2_control`；2026-09-24 对照的 `src/so101_demo_py/config/dependency-lock.yaml` 锁定 `5a590b22770b270b71ba6a1c3443d4e67edc7f4b`。执行时必须重新核对实际 gitlink 与锁；修改子模块后先提交子模块，再更新父仓 gitlink 和锁，不改写历史 provenance 报告。
- 仿真物理证据来源为 `src/so101_mujoco_support` 与 `src/so101_demo_py/src/backends/mujoco/observer.py`。持物监督复用既有杯子证据；Task 8 在 support 插件增设不经杯子过滤的全机器人接触流。所有真值仍只供监督/审计，不进入 ACT observation。
- `src/so101_demo_py/src/parallel_batch/contracts.py` 的 `ParallelRuntimeConfigV3` 与 `BatchRequestV3` 是 Linux 新执行契约；`coordinator.py` 的 ordered pending 集合、`worker.py`、Broker、start guard、owned-process manifest 与 fsync journal 提供无生命周期配额领取、lease、结果 commit 和精确清理。Task 11A 通过 ACT 专用 ports 接入，不复制调度或恢复权威；`queue.py` 是 macOS selection-binding 的 `DurablePointQueue`，不是 Linux fixed 调度依据。
- `BatchRequestV3` 不限制 `selected_point_ids` 为 20 项。Task 11A 在 ACT collection config 中另冻结 `max_wave_size=20`，以限制单批故障域并保留资格口径；冻结 scenario 清单确定性分 wave，每个 wave 创建 exact-N v3 request，单 wave 恢复继续使用 main 的 fixed resume 语义。
- `config/mujoco/parallel_batch_v3.yaml` 冻结 Linux CUDA、Domain 池与 start guard。ACT 的 `config/act/parallel_collection_v3.yaml` 只保存 collection workload、Recorder 与资格参数，并引用 v3 配置路径/hash；不得复制或改写公共运行字段。
- `src/so101_teleop/so101_teleop/unified/arbiter.py` 是 Teleop、Tasks 与 Validation 的唯一 mutation reservation authority；`unified/teleop_service.py` 是 Web/headless 共同 admission 入口。Task 7A 扩展既有 `OperationSpec`、`WorkerPort`、closed `IpcRequest`、`BridgeProcessOwner`、`ChildRuntime` 和 `ros_child.py`，不新建第二套 ACT command broker。
- `src/so101_teleop/so101_teleop/unified/ros_child.py` 是唯一 ROS import/driver 边界；现有 `RclpyActionDriver.submit` 的 `ROS_DRIVER_NOT_PROVISIONED` 是 Task 7A 必须闭合的真实实现缺口。

## 文件结构与职责

新建 `src/so101_demo_py/src/act/` 包，包含 `__init__.py`。它按 ACT 领域职责拆文件，不重新组织既有代码。纯领域逻辑不导入 ROS、torch、MuJoCo；所有 `adapters/act/` 新目录也增加 `__init__.py`。下面各任务 Files 清单给出完整路径及唯一责任，文件首次出现为创建，后续引用为修改。

| 单元 | 主要文件 | 责任 |
| --- | --- | --- |
| 契约与时间 | `act/contracts.py`, `act/deadline.py` | 输入白名单、时间网格、错误与 120 s 截止时间 |
| Admission 与 typed IPC | `so101_teleop/unified/contracts.py`, `parents.py`, `ipc.py`, `bridge.py`, `child_runtime.py`, `ros_child.py`, `teleop_service.py` | 单次资源 admission、不可变 campaign context、每 Worker 唯一 ROS child 与闭合 operation registry |
| 图像与搜索 | `act/synchronizer.py`, `act/search.py`, `act/bearing.py` | 因果取样、扫描/锁定、相机视线方向 |
| 校准 | `act/calibration.py`, `act/contact_calibration.py`, `act/contact_policy.py`, `act/task8_measurement_contract.py`, `act/task8_calibration_aggregator.py`, `act/task8_live_qualification.py`, `cli/act_preflight.py`, `cli/act_measure_task8_calibration.py`, `cli/act_build_task8_calibration_report.py`, `cli/act_build_task8_qualified_report.py` | 通用预检、冻结测量合同、原始 batch、确定性聚合、live 资格聚合、接触 proposal 与 activation receipt |
| Task 8 工件 | `act/source_provenance.py`, `act/collection_config.py`, `act/task8_artifact_bundle.py`, `cli/act_build_task8_source_provenance.py`, `cli/act_prepare_task8_live_artifacts.py`, `cli/act_validate_task8_artifacts.py`, `so101_teleop/unified/act_artifacts.py`, `unified/admission.py` | 运行角色 provenance、collection config、闭合依赖 bundle、receipt 原子提交、纯只读验证和启动入口验证 |
| 执行与监督 | `act/execution.py`, `act/task8.py`, `act/supervisor.py`, `adapters/act/ros_execution.py`, `adapters/act/physics.py` | 双控制器、九阶段 phase-prefix/full runner、路径检查、释放门控和状态机 |
| 数据 | `act/expert.py`, `act/recorder.py`, `act/sampling.py`, `act/collection.py` | 实际 reference、无损记录、划分与单场景采集 |
| 并行采集 | `act/parallel_collection.py`, `adapters/act/parallel_collection_runtime.py`, `adapters/act/parallel_collection_results.py`, `runtime/act_fixed_collection_composition.py`, `cli/act_collect_parallel.py` | scenario→exact-N v3 wave、Worker ports、同 N 恢复、原子封存与确定性总 manifest |
| 模型 | `act/bundle.py`, `act/policy.py`, `adapters/act/lerobot.py`, `cli/act_train.py` | 离线模型工件、单次推理、版本隔离 |
| 推理进程 | `adapters/act/inference_process.py`, `cli/act_inference_worker.py` | 指定解释器、模型加载、非阻塞 IPC |
| 离线评估 | `act/offline_evaluation.py`, `cli/act_offline_evaluate.py` | 冻结 Offline Test 与带 mask 的动作误差 |
| 组合与评测 | `act/session.py`, `act/evaluation.py`, `runtime/act_composition.py`, `cli/act_session.py`, `cli/act_evaluate.py` | 运行生命周期、命令入口、封存评测 |
| Teleop | `so101_teleop/act_gateway.py`, `web/src/components/teleop/act-panel.tsx` | 页面操作与后台命令，不承载 10 Hz 循环 |

## 统一接口约定

Python 接口中的 `dict` 均为下列闭合 JSON schema，校验拒绝多余字段；图像 bytes/array 仅存在内存，不把审计侧字典整体传入模型。坐标、时间、单位在字段名中明确。所有时间比较先校验 session/attempt，所有 float 拒绝 bool、NaN、Inf。

| schema | 精确字段 |
| --- | --- |
| `Observation` | `session_id:str, attempt_id:str, sim_time_s:float, head:RGB array, wrist:RGB array, state:tuple[float,...]`（8 维） |
| `ActionPrefix` | `session_id:str, attempt_id:str, sequence:int, observation_time_s:float, target_times_s:tuple[float,...], positions:tuple[tuple[float,...],...]`（每行 6 维） |
| `SearchResult` | `found:bool, status:str, bearing_rad:float|None, frame_id:str, ray_origin_frame_id:str, neck_yaw_rad:float|None, confidence:float|None, timestamp:float, attempt_id:str` |
| `Scenario` | `scene_id:str, split:str, xy:tuple[float,float], arm_q:tuple[float,...]`（6 维）, `search_start_rad:float, seed:int, config_sha256:str` |
| `AdmittedCampaignContext` | `operation_id:str, campaign_id:str, workload_kind:str, stable_host_id:str, physical_gpu_uuid:str, source_sha256:str, manifest_sha256:str, runtime_config_sha256:str, collection_config_sha256:str, contact_policy_fingerprint:str, worker_count:int, resource_binding_id:str, service_epoch:int, execution_generation:int, admitted_at_monotonic_s:float, deadline_monotonic_s:float, evidence_root:str` |
| `Task8Request` | `session_id:str, attempt_id:str, scenario_id:str, mode:"phase_prefix"|"full", stop_after:str|None, contact_policy_fingerprint:str, deadline_monotonic_s:float` |
| `CollectionScenarioResult` | `scene_id:str, split:str, status:str, business_failure:str|None, infra_attempts:int, episode_root:str, episode_sha256:str, worker_id:str, batch_id:str, worker_generation:int, worker_count:int, coordinator_commit_sequence:int` |
| `RunResult` | `scene_id:str, split:str, search_locked:bool, done:bool, interventions:int, failure:str|None, elapsed_wall_s:float, elapsed_sim_s:float, checkpoint_sha256:str, config_sha256:str` |

`ContractError(ValueError)` 用于输入/工件拒绝；执行状态使用稳定字符串，如 `ACT_TIMEOUT`、`TARGET_AMBIGUOUS`、`TARGET_NOT_FOUND`、`INPUT_STALE`、`COLLISION_REJECTED`、`RELEASE_UNSUPPORTED`、`CONTROLLER_PAIR_FAILED`。错误细节留审计侧，不悄悄转换为成功。

## 执行前准备与测试命令

- [ ] 读取当前根/父仓 AGENTS.md、`so101-dev` 及有关 reference；记录本地和 ai-station 的 pwd、branch、commit、submodule、dirty files。只在执行阶段访问远端。需要隔离 checkout 时使用 `superpowers:using-git-worktrees`，不把用户未跟踪设计丢在原 checkout。
- [ ] 检查已有进程、ROS graph 和 tmux 所有权；运行阶段不得启动重复 stack。本轮长程任务继续使用账本 `docs/experiments/so101-act-data-experiment-ledger.md` 与已登记的唯一 durable evidence root `/data/work/so101-evidence/act-data/20260924-fbc25063-resume/`。测试 scratch、measurement batch、bundle 和 live 证据都放在该 root 的独立子目录；不得另建第二个 task root。superseded batch 移入同一平台根的 `archived/act-data/<run-id>/` 前先核对清单、hash、大小与数量；未获用户授权不删除。
- [ ] 在执行主机配置一次下面的 shell 环境。Mac 使用当前已加载 ROS 的 zsh；Linux 直接在 ai-station 执行，禁止再次 SSH 自身。

```zsh
if [[ "$(uname -s)" == Darwin ]]; then
  : "${ACT_EVIDENCE:?先登记并导出本 Mac task 的唯一 evidence root}"
  test -d "$ACT_EVIDENCE" || exit 1
  ACT_PYTHON=/Users/matianyi/ros2_jazzy/.venv/bin/python3
  ACT_BUILD_BASE="$PWD/build"
  ACT_INSTALL_OVERLAY="$PWD/install"
  ACT_LOG_BASE="$PWD/log"
  eval "$(direnv export zsh)"
else
  source /opt/ros/jazzy/setup.zsh
  ACT_EVIDENCE=/data/work/so101-evidence/act-data/20260924-fbc25063-resume
  test -d "$ACT_EVIDENCE" || exit 1
  ACT_BUILD_BASE="$ACT_EVIDENCE/b"
  ACT_INSTALL_OVERLAY="$ACT_EVIDENCE/i"
  ACT_LOG_BASE="$ACT_EVIDENCE/l"
  test -d "$ACT_BUILD_BASE" || exit 1
  test -f "$ACT_INSTALL_OVERLAY/setup.zsh" || exit 1
  test -d "$ACT_LOG_BASE" || exit 1
  ACT_PYTHON=$(command -v python3)
fi
export ACT_EVIDENCE ACT_PYTHON ACT_BUILD_BASE ACT_INSTALL_OVERLAY ACT_LOG_BASE
export ROS_HOME="$ACT_EVIDENCE/ros-home" ROS_LOG_DIR="$ACT_EVIDENCE/ros-home/log"
mkdir -p "$ROS_LOG_DIR"
# 使用依赖锁规定的 fork overlay，然后 project overlay；具体绝对路径记入账本。
source "$ACT_INSTALL_OVERLAY/setup.zsh"
"$ACT_PYTHON" -c 'import sys, rclpy; print(sys.executable); print(rclpy.__file__)'
```

- [ ] 把以下函数留在同一执行 shell。Linux 每次测试创建全新 NVMe scratch，用实际 Python 验证；普通 gate 不收集 benchmark。运行耗时和 scratch 随日志登记，readback 后分类为删除候选，禁止自动删除。

```zsh
act_test() {
  if [[ "$(uname -s)" == Linux ]]; then
    mkdir -p "$ACT_EVIDENCE/scratch"
    ACT_SCRATCH=$(mktemp -d "$ACT_EVIDENCE/scratch/test-XXXXXXXX")
    mkdir "$ACT_SCRATCH/tmp"
    export TMPDIR="$ACT_SCRATCH/tmp" TMP="$ACT_SCRATCH/tmp" TEMP="$ACT_SCRATCH/tmp"
    "$ACT_PYTHON" -c 'import os,tempfile; from pathlib import Path; assert Path(tempfile.gettempdir()).resolve()==Path(os.environ["TMPDIR"]).resolve()' || return 1
  fi
  PYTHONNOUSERSITE=1 /usr/bin/time -p "$ACT_PYTHON" -m pytest -p no:cacheprovider "$@"
}
```

每个 Task 的 RED/GREEN 命令使用 `act_test`，只作为定向诊断。纯 Python 新包在 Linux 通过 `colcon --log-base "$ACT_LOG_BASE" build --build-base "$ACT_BUILD_BASE" --install-base "$ACT_INSTALL_OVERLAY" --packages-select so101_demo_py --symlink-install` 安装后再 source 该 overlay；macOS 才使用 checkout 默认的 `build/install/log`。测试必须出现预期断言失败或缺失的新符号，ROS/dylib bootstrap 失败不能当 RED。每个受影响 Python 模块的完整普通测试目录必须按 `test-and-acceptance.md` 使用 `pytest-xdist -n min(8, logical CPU)`，分别记录 CPU/worker 数、解释器与 xdist 来源、fresh scratch、JUnit、采集数、跳过数、elapsed 和退出码；资源冲突必须修复隔离后以相同 worker 数重跑，不能降并行度。ai-station 仍要运行必要的 `colcon test`/package gate 并核验实际 pytest argv，再以 `colcon test-result --verbose` 汇总；`tools/so101_pytest_gate.py` 的文件分片/串行安全 lane 只能作为补充 provenance/coverage 证据，不能替代完整 xdist 门。新增 C++/Teleop 任务各自运行自己的 package gate。

以下代码块给出必须落地的边界测试与关键实现，不是只有正常路径的完整实现。每个任务还列出失败矩阵，逐项补参数化测试；校准、录制和训练是长时间命令，启动、读取报告、判定作为独立步骤，不承诺一次完整训练只需 2–5 分钟。


### Task 1: 闭合 observation/action 契约与 120 s 截止时间

**Files:**

- Create: `src/so101_demo_py/src/act/__init__.py`
- Create: `src/so101_demo_py/src/act/contracts.py`
- Create: `src/so101_demo_py/src/act/deadline.py`
- Create: `src/so101_demo_py/test/test_act_contracts.py`

**Interfaces:** Consumes: 标准库及本计划 schema。Produces: `ContractError`；`validate_action(values: tuple[float, ...]) -> tuple[float, ...]`；`validate_observation(value: dict) -> dict`；`Deadline(started_wall_s: float).expired(now_wall_s: float) -> bool`。

- [ ] **Step 1: 写入边界失败测试。**

```python
import pytest
from so101_demo.act.contracts import ContractError, validate_action
from so101_demo.act.deadline import Deadline

def test_nonfinite_action_and_fixed_deadline():
    with pytest.raises(ContractError):
        validate_action((0., 0., 0., 0., 0., float("nan")))
    budget = Deadline(started_wall_s=10.)
    assert not budget.expired(129.999)
    assert budget.expired(130.)
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_contracts.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
from dataclasses import dataclass
import math

class ContractError(ValueError):
    pass

def validate_action(values: tuple[float, ...]) -> tuple[float, ...]:
    if len(values) != 6 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise ContractError("ACTION_INVALID")
    return tuple(float(v) for v in values)

@dataclass(frozen=True)
class Deadline:
    started_wall_s: float

    def expired(self, now_wall_s: float) -> bool:
        return now_wall_s - self.started_wall_s >= 120.0
```

为每个 schema 实现严格字段白名单、非空 ID、有限时间、向量形状检查。Observation 只允许两张 uint8 RGB 图片与 8 维 state；禁止额外 truth/depth/task_camera 字段。ActionPrefix 目标时间严格递增、步长 0.1 s、首目标为 observation_time_s+0.1；禁止 bool 假冒数值。Deadline 构造和调用拒绝非有限值或倒退的单调时间，计时对象不可重启。常量放 deadline.py，不在训练配置暴露可调 timeout。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_contracts.py -q
```

预期非零测试收集、全部通过。补测 5/7 维 action、8 维 state、错误图像、额外禁止字段、120 s 边界；纯契约导入不能触发 ROS、torch、MuJoCo 导入。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/__init__.py src/so101_demo_py/src/act/contracts.py src/so101_demo_py/src/act/deadline.py src/so101_demo_py/test/test_act_contracts.py
git diff --cached --check
git commit -m "feat: define ACT observation and deadline contracts"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 2: CameraPlugin 逐相机 RGB-only 扩展

**Files:**

- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control_plugins/src/camera_plugin.hpp`
- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control_plugins/src/camera_plugin.cpp`
- Modify: `third_party/mujoco_ros2_control/mujoco_ros2_control_plugins/test/test_camera_plugin.cpp`
- Modify: `src/so101_demo_py/config/dependency-lock.yaml`

**Interfaces:** Consumes: 既有 CameraData、CameraPlugin 参数与渲染线程。Produces: 相机级 `publish_depth: bool`（默认 true）；false 时不创建 depth publisher、不分配/读取 depth buffer；RGB 与 CameraInfo 保持原语义。

- [ ] **Step 1: 写入边界失败测试。**

```cpp
// 加入现有 test_camera_plugin.cpp，使用已有 camera_plugin.hpp。
TEST(CameraDataContract, DepthRemainsEnabledByDefault)
{
  mujoco_ros2_control_plugins::CameraData camera;
  EXPECT_TRUE(camera.publish_depth);
}
```

- [ ] **Step 2: 验证 RED。**

```zsh
colcon --log-base "$ACT_LOG_BASE" test --build-base "$ACT_BUILD_BASE" --install-base "$ACT_INSTALL_OVERLAY" --packages-select mujoco_ros2_control_plugins --event-handlers console_direct+
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```cpp
// CameraData 新字段；注册相机时从相机级参数读取，默认 true。
bool publish_depth{true};
// render 的像素读取分支：
mjr_readPixels(camera.image_buffer.data(),
  camera.publish_depth ? camera.depth_buffer.data() : nullptr,
  camera.viewport, &render_context);
```

读取 register_cameras 与 render 的实际变量名，将上面的分支放到现有 mjr_readPixels 调用处；深度图转换、buffer resize 和发布也受同一标志约束。不得更改 Linux EGL/macOS CGL 上下文所有权。用现有 CameraPluginTest fixture 建立 RGB-only 与默认 RGB-D 两台相机，实际启动 executor、渲染并验证 topic discovery、RGB 字节数、CameraInfo 与帧时间一致；不能只用结构体默认值测试宣布完成。默认 task_camera 和 macOS lifecycle 测试必须保持通过。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
colcon --log-base "$ACT_LOG_BASE" test --build-base "$ACT_BUILD_BASE" --install-base "$ACT_INSTALL_OVERLAY" --packages-select mujoco_ros2_control_plugins --event-handlers console_direct+
```

预期非零测试收集、全部通过。子模块构建 `colcon build --packages-select mujoco_ros2_control_plugins`，测试 `colcon test --packages-select mujoco_ros2_control_plugins --event-handlers console_direct+`，读取 CTest 结果。修改子模块的实际文件后在该仓 commit；以 `git -C third_party/mujoco_ros2_control rev-parse HEAD` 更新 dependency-lock.yaml 的 fork.commit，父仓显式提交 gitlink 和锁。不得捏造安装 provenance 或发布远端。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git -C third_party/mujoco_ros2_control add mujoco_ros2_control_plugins/src/camera_plugin.hpp mujoco_ros2_control_plugins/src/camera_plugin.cpp mujoco_ros2_control_plugins/test/test_camera_plugin.cpp
git -C third_party/mujoco_ros2_control commit -m "feat: support per-camera RGB-only rendering"
git -C third_party/mujoco_ros2_control rev-parse HEAD
```

先将上述实际 SHA 写入 dependency-lock.yaml，再提交父仓：

```zsh
git add third_party/mujoco_ros2_control src/so101_demo_py/config/dependency-lock.yaml
git diff --cached --check
git commit -m "build: pin RGB-only camera dependency"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 3: ACT 场景、neck controller 与按名称 reset

**Files:**

- Create: `src/so101_demo_py/assets/mujoco/act/scene.xml`
- Create: `src/so101_demo_py/assets/mujoco/act/so101.xml`
- Create: `src/so101_demo_py/assets/mujoco/act/so101.urdf`
- Create: `src/so101_demo_py/config/mujoco/act/ros2_controllers.yaml`
- Create: `src/so101_demo_py/config/mujoco/act/mujoco_plugins.yaml`
- Modify: `src/so101_demo_py/src/runtime/launch_composition.py`
- Modify: `src/so101_demo_py/src/backends/mujoco/reset.py`
- Modify: `src/so101_demo_py/src/backends/mujoco/client.py`
- Create: `src/so101_demo_py/src/act/joints.py`
- Create: `src/so101_demo_py/launch/so101_mujoco_act.launch.py`
- Create: `src/so101_demo_py/test/test_act_model_reset.py`

**Interfaces:** Consumes: Task 2 publish_depth；既有六关节 reset。Produces: `ordered_positions(values: dict[str,float], names: tuple[str,...]) -> tuple[float,...]`；launch 参数 `act_profile` 默认 false；ACT 入口设 true；neck_yaw_joint 独立于 joints 1–6。

- [ ] **Step 1: 写入边界失败测试。**

```python
import pytest
from so101_demo.act.joints import ordered_positions

def test_neck_does_not_shift_arm_order():
    values = {"neck_yaw_joint": 3., "6": .6, "1": .1}
    assert ordered_positions(values, ("1", "6")) == (.1, .6)
    with pytest.raises(ValueError):
        ordered_positions(values, ("missing",))
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_model_reset.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
def ordered_positions(values: dict[str, float], names: tuple[str, ...]) -> tuple[float, ...]:
    if len(set(names)) != len(names) or any(name not in values for name in names):
        raise ValueError("JOINT_MAPPING_INVALID")
    return tuple(values[name] for name in names)
```

从现有 XML/URDF 生成显式 ACT 变体，修正 mesh/include 的相对路径；wrist 安装到刚性腕部，head 支架固定于基座，yaw 连续、俯角固定。新增质量/惯量/碰撞体、两相机 640×480 和 neck position actuator；keyframe 用 mj_name2id/jnt_qposadr 按名字构造。安装参数首先为校准输入，Task 6 测量通过后冻结。URDF、MJCF、ros2_control 关节集合一致，SRDF arm group 不加 neck。新增 ACT launch profile 只选择资产/controller/plugin 配置，复用原 launch 组合，禁止另起重复 move_group。MujocoResetClient 新增可选 expected_joint_names，默认保留原六关节；client 的取值与收敛路径接受同一名字列表。ACT reset 要求 7 个关节及 neck controller 的新鲜反馈，不改变旧调用行为。



- [ ] **Step 3a: 把 Scenario 的初始关节状态写入 reset 请求。**

`client.py` 新增 `JointResetOverride(name:str, position:float, velocity:float=0.0)`。`MujocoRosClient.reset_world(keyframe, free_joint_overrides=(), *, joint_overrides:tuple[JointResetOverride,...]=()) -> bool` 和 `MujocoResetClient.reset` 增加同名 keyword-only 参数；旧调用缺省空 tuple。Scenario.arm_q 映射 joints 1–6，search_start_rad 映射 neck_yaw_joint，七个目标都通过同一 reset 事务写入。

```python
from sensor_msgs.msg import JointState

# request 为既有 ResetWorld.Request；joint_overrides 为已校验记录。
request.state_overrides.joint_states = JointState(
    name=[item.name for item in joint_overrides],
    position=[item.position for item in joint_overrides],
    velocity=[item.velocity for item in joint_overrides],
)
```

拒绝重复/未知/非单自由度关节、越界位置和非有限速度；保持旧 keyframe/free_joints 语义。暂停、控制器停用、reset override、atomic snapshot、新 epoch、控制器恢复和新鲜收敛构成一个事务。必须同步控制器保持参考，避免恢复时跳回旧目标。override 不等于 expected state：写入列表和期望读回来自同一 Scenario，但读回必须来自实际消息。

```python
from so101_demo.backends.mujoco.client import JointResetOverride, joint_override_message

def test_joint_override_serializes_both_position_and_velocity():
    msg = joint_override_message((JointResetOverride("1", .15, 0.),
                                  JointResetOverride("neck_yaw_joint", -1.2, 0.)))
    assert msg.name == ["1", "neck_yaw_joint"]
    assert list(msg.position) == [.15, -1.2]
    assert list(msg.velocity) == [0., 0.]
```

将构造提取为 `joint_override_message(items:tuple[JointResetOverride,...])->JointState`，以上测试直接验证真实序列化函数。再用 fake service 捕获完整请求，确认协调器没有丢失参数；live 用两个不同 arm_q/neck 起点重复 reset，断言七关节实测值/零速度/epoch 与清单一致。缺少 neck 或仍停留旧 keyframe 时明确失败。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_model_reset.py -q
```

预期非零测试收集、全部通过。加载 MJCF 与 URDF 检查 joint 集合；打乱 XML joint 顺序后 mapping 仍正确；对旧 6 关节和 ACT 7 关节分别 reset 两次，验证 epoch、位置/速度和相机新帧。`ros2 launch so101_demo_py so101_mujoco_act.launch.py --show-args`，两个平台验证 head/wrist TF 与碰撞几何一致。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/assets/mujoco/act/scene.xml src/so101_demo_py/assets/mujoco/act/so101.xml src/so101_demo_py/assets/mujoco/act/so101.urdf src/so101_demo_py/config/mujoco/act/ros2_controllers.yaml src/so101_demo_py/config/mujoco/act/mujoco_plugins.yaml src/so101_demo_py/src/runtime/launch_composition.py src/so101_demo_py/src/backends/mujoco/reset.py src/so101_demo_py/src/backends/mujoco/client.py src/so101_demo_py/src/act/joints.py src/so101_demo_py/launch/so101_mujoco_act.launch.py src/so101_demo_py/test/test_act_model_reset.py
git diff --cached --check
git commit -m "feat: add ACT scene and named neck reset"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 4: 因果 RGB 同步与 reset 缓存失效

**Files:**

- Create: `src/so101_demo_py/src/act/synchronizer.py`
- Create: `src/so101_demo_py/src/adapters/act/__init__.py`
- Create: `src/so101_demo_py/src/adapters/act/ros_observation.py`
- Create: `src/so101_demo_py/test/test_act_synchronizer.py`

**Interfaces:** Consumes: Task 1 Observation、Task 3 关节名字。Produces: `causal_sample(samples: list[tuple[float,object]], at_s:float, max_age_s:float) -> object`；`RgbObservationSynchronizer.push(stream:str, session_id:str, sim_time_s:float, value:object) -> None`；`.sample(session_id:str, attempt_id:str, at_s:float) -> dict`；`.reset(session_id:str) -> None`。构造参数为 max_age_s、max_skew_s，来自校准工件。

- [ ] **Step 1: 写入边界失败测试。**

```python
import pytest
from so101_demo.act.synchronizer import causal_sample

def test_future_state_is_never_used():
    assert causal_sample([(1., "past"), (1.1, "future")], 1.05, .1) == "past"
    with pytest.raises(ValueError):
        causal_sample([(1.1, "future")], 1.05, .1)
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_synchronizer.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
def causal_sample(samples, at_s, max_age_s):
    valid = [(t, v) for t, v in samples if 0 <= at_s - t <= max_age_s]
    if not valid:
        raise ValueError("INPUT_STALE")
    return max(valid, key=lambda item: item[0])[1]
```

四个 stream 固定为 head、wrist、arm、neck；用 stamp 和 session 校验新鲜度，双相机优先同一 physics snapshot，否则最大时间差不得超过 max_skew_s。arm 6 维后附 sin/cos yaw；记录原 yaw 只在 audit 输出。相同 stamp 重复拒绝，像素相同允许；有界 ring buffer 不无限增长。ROS adapter 只订阅双 RGB 与 joint feedback；样本时间来自消息 stamp。reset 清空全部 buffer、旧 session 和策略关联，不以墙钟拼接仿真序列。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_synchronizer.py -q
```

预期非零测试收集、全部通过。参数化检查不同相机快照、旧 session、空 buffer、时间倒退、neck 缺失、重复 stamp 与静止像素；模拟缺帧必须让 recorder 拒绝 episode，不能重排帧号伪装连续。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/synchronizer.py src/so101_demo_py/src/adapters/act/__init__.py src/so101_demo_py/src/adapters/act/ros_observation.py src/so101_demo_py/test/test_act_synchronizer.py
git diff --cached --check
git commit -m "feat: synchronize causal ACT observations"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 5: 固定扫描、轻量检测与相机视线方位

**Files:**

- Create: `src/so101_demo_py/src/act/search.py`
- Create: `src/so101_demo_py/src/act/bearing.py`
- Create: `src/so101_demo_py/src/adapters/act/detector.py`
- Create: `src/so101_demo_py/src/adapters/act/ros_search.py`
- Create: `src/so101_demo_py/test/test_act_search.py`

**Interfaces:** Consumes: 新鲜 head RGB、CameraInfo、neck 实测反馈、Task 4 同步策略。Produces: `bearing(ray_base: tuple[float,float,float]) -> float`；`HeadSearchController(config:dict).tick(frame:dict, feedback:dict, now_wall_s:float) -> dict`（输出 neck_target_rad 或 SearchResult）；`detect_head(rgb:object, bundle:dict) -> list[dict]`，检测框精确字段为 xyxy、confidence、class_id、track_id。

- [ ] **Step 1: 写入边界失败测试。**

```python
import math
import pytest
from so101_demo.act.bearing import bearing

def test_ray_uses_base_axes_and_rejects_vertical():
    assert bearing((0., 1., -1.)) == pytest.approx(math.pi/2)
    with pytest.raises(ValueError):
        bearing((0., 0., -1.))
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_search.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
import math

def bearing(ray_base):
    x, y, z = ray_base
    if not all(math.isfinite(v) for v in ray_base) or math.hypot(x, y) < 1e-9:
        raise ValueError("BEARING_INVALID")
    return (math.atan2(y, x) + math.pi) % (2 * math.pi) - math.pi
```

状态 SAFE_OBSERVE→SEARCH_CUP→CENTER_CUP→TARGET_LOCKED；先检测起点，粗扫用连续累计 yaw，最大一整圈；步长≤水平 FOV/2。每次移动停稳再用新帧，居中修正受次数/累计角/总时间限制。锁定需同一目标至少 3 帧、水平死区、有效垂直区、最小面积，不能仅按类别关联；歧义返回 TARGET_AMBIGUOUS。失帧停 neck，微调丢失恢复剩余预算扫描。相机视线用去畸变像素 K^-1 后乘实际安装旋转与帧时刻 neck 旋转；不引入距离/桌面交点。无效结果 bearing/confidence 清空。检测器 adapter 只收 head RGB；首个候选复用已安装轻量检测器但必须经 Task 6 head 视角资格验证，权重 hash 和运行依赖单独冻结，失败就不采集。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_search.py -q
```

预期非零测试收集、全部通过。搜索测试使用注入 frame/feedback 序列验证无目标、多目标、左右偏移、±π、垂直视线、锁定漂移、reset、微调预算和超时。加入畸变/俯角/水平偏置几何测试，证明 bearing 是相机光心射线而非基座到杯心角。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/search.py src/so101_demo_py/src/act/bearing.py src/so101_demo_py/src/adapters/act/detector.py src/so101_demo_py/src/adapters/act/ros_search.py src/so101_demo_py/test/test_act_search.py
git diff --cached --check
git commit -m "feat: add bounded head search and bearing"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 6: 相机、搜索与控制参数预检工件

**Files:**

- Create: `src/so101_demo_py/src/act/calibration.py`
- Create: `src/so101_demo_py/src/cli/act_preflight.py`
- Create: `src/so101_demo_py/config/act/calibration-schema.json`
- Modify: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/test/test_act_calibration.py`

**Interfaces:** Consumes: Task 3–5、既有 MoveIt 教师链路。Produces: `require_gate(report:dict, gate:str)->None`，其中 `gate=task8_live|formal_collection`；CLI `act_preflight --measured-report PATH --source-root PATH --output PATH` 只验证已有 report 并写 readback，不生成或升级状态；校准 JSON 含 status、source_commit、config_sha256、measurements、checks。`TASK8_READY` 只要求 Task 8 可启动的前置检查通过；`QUALIFIED` 还要求 Task 8 live 的 release/retreat 结果由 Task 8P4 producer 从完整 journals 计算通过，只允许正式采集使用。

- [ ] **Step 1: 写入边界失败测试。**

```python
import pytest
from so101_demo.act.calibration import require_gate

def test_unmeasured_report_cannot_start_collection():
    with pytest.raises(ValueError):
        require_gate({"status": "CALIBRATION_REQUIRED", "checks": {}}, "formal_collection")
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_calibration.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
def require_gate(report, gate):
    required_by_gate = {
        "task8_live": {"fov", "collision", "search", "synchronization", "execution"},
        "formal_collection": {"fov", "collision", "search", "synchronization", "execution", "release", "retreat"},
    }
    required = required_by_gate[gate]
    checks = report.get("checks", {})
    allowed_status = {"task8_live": "TASK8_READY", "formal_collection": "QUALIFIED"}
    if report.get("status") != allowed_status[gate] or not required.issubset(checks) or any(checks[k] != "PASS" for k in required):
        raise ValueError("CALIBRATION_REQUIRED")
```

注册 act_preflight entry point。测量并输出高度/偏置/俯角、相机内外参、yaw 零位方向、扫描/微调预算、检测阈值、head 锁定有效区、动作限速/限加速度、同步新鲜度、抓取窗口、controller 提交提前量、支撑/释放/撤离阈值；每个值含单位、样本路径与 hash。使用专家全阶段轨迹检查视野和新增几何，分别验证两个平台 RGB 与原 task_camera 回归。Task 7 完成 controller timing 后，前置检查齐全可输出 `TASK8_READY`；Task 8P4 在 live 后从原始 release/retreat 与 cleanup evidence 生成新版本 `QUALIFIED`。禁止用 `TASK8_READY` 启动采集，也禁止在 Task 8 live 前伪造 `QUALIFIED`。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_calibration.py -q
```

预期非零测试收集、全部通过。完成 A 阶段时报告相机/搜索实测值及未通过的执行/释放检查。小规模 mock 报告测试缺失项、非有限值、错误单位、篡改哈希；live 校准保留新鲜双视角图像、关节/TF、物理碰撞和检测失败记录。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/calibration.py src/so101_demo_py/src/cli/act_preflight.py src/so101_demo_py/config/act/calibration-schema.json src/so101_demo_py/setup.py src/so101_demo_py/test/test_act_calibration.py
git diff --cached --check
git commit -m "feat: gate ACT capture on measured calibration"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 6A: 接触校准、策略 fingerprint 与显式激活

**Files:**

- Create: `src/so101_demo_py/src/act/contact_calibration.py`
- Create: `src/so101_demo_py/src/act/contact_policy.py`
- Create: `src/so101_demo_py/src/cli/act_collect_contact_calibration.py`
- Create: `src/so101_demo_py/src/cli/act_analyze_contact_calibration.py`
- Create: `src/so101_demo_py/src/cli/act_activate_contact_policy.py`
- Create: `src/so101_demo_py/config/act/contact-calibration-schema.json`
- Modify: `src/so101_demo_py/src/core/contact_policy.py`
- Modify: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/test/test_act_contact_calibration.py`
- Create: `src/so101_demo_py/test/test_act_contact_policy_activation.py`

**Interfaces:** Consumes: Task 3 的确定性 MuJoCo reset、Task 6 的来源/配置 hash、原始接触与状态证据。Produces: `canonical_policy_payload(payload:dict)->bytes`；`policy_fingerprint(payload:dict)->str`；`verify_activation(payload:dict, receipt:dict)->None`；collector CLI 的 `--mode offline|live`；analyzer CLI 只写 `status=DISABLED` proposal envelope；activation CLI 要求 `--policy-fingerprint`、`--approved-by`、`--approval-reference` 和 `--evidence-root`，只在精确 fingerprint 与 proposal payload hash 一致时写 receipt。canonical payload 冻结运行阈值、适用 MuJoCo/模型版本与 `source_evidence_sha256`；activation receipt 单独记录已批准 fingerprint、批准身份、批准引用、时间和 evidence root，不改写 proposal 或 payload。

- [ ] **Step 1: 先写 fingerprint、样本矩阵和自举边界测试。**

```python
from so101_demo.act.contact_policy import policy_fingerprint, verify_activation

def test_activation_approves_payload_hash_not_envelope_hash():
    payload = {"schema_version": 1, "thresholds": {"touch_n": 1.0},
               "mujoco_version": "frozen", "model_sha256": "a" * 64,
               "source_evidence_sha256": "b" * 64}
    fingerprint = policy_fingerprint(payload)
    verify_activation(payload, {"policy_fingerprint": fingerprint,
                                "approved_by": "user", "approved_at": "2026-09-24T00:00:00Z",
                                "evidence_root": "/data/work/so101-evidence/act-head-wrist/run"})
    assert policy_fingerprint({**payload, "thresholds": {"touch_n": 1.1}}) != fingerprint
```

参数化测试要求五类状态 `no_contact`、`bilateral_touch`、`over_compression`、`micro_lift_slip`、`stable_hold` 各恰好 20 个 deterministic offline MuJoCo 样本和 5 个隔离 ROS/MuJoCo live 样本；另有 table-only、post-release residual、unilateral 三类 negative control。测试还要证明 collector 只读独立 diagnostic hard limits，不读取待批准 policy；proposal envelope hash、旧 fingerprint、缺失来源 hash、额外字段、非 canonical 数值和被改写 receipt 全部拒绝。

- [ ] **Step 2: 运行 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_contact_calibration.py src/so101_demo_py/test/test_act_contact_policy_activation.py -q
```

预期新模块缺失或边界断言失败；环境/bootstrap 失败不计 RED。

- [ ] **Step 3: 实现 collector、analyzer 与 activation verifier。**

`canonical_policy_payload` 使用 schema 的闭合字段、UTF-8、确定性 JSON（排序键、固定 separators、拒绝 NaN/Inf/bool-as-number），返回的 bytes 是唯一 fingerprint 输入。analyzer 从封存样本拟合候选阈值并输出 evidence index、混淆矩阵、negative-control 结果、适用版本、canonical payload、`POLICY_FINGERPRINT = SHA256(payload_bytes)` 和 disabled 状态；不得生成自批准 receipt。`src/core/contact_policy.py` 迁移到相同 canonical helper；删除 ACT 新策略中的 Gazebo-only key，旧 reader 若仍需兼容只能显式读取旧 schema，不能把该字段带入新 fingerprint。

collector 每条样本保存原始接触流、MuJoCo state、ROS time、单调墙钟、scenario 参数、source/config/model hash 与 diagnostic result。offline 生成器必须可用固定 seed 重放；live 模式每次启动单一隔离 ROS/MuJoCo session，禁止复用正式 collection root。两种模式都在写完文件、manifest 和父目录后 `fsync`，再由 analyzer 按 manifest 读取，禁止目录扫描补样本。

策略激活是执行阶段的人工门：独立审阅 proposal 后，用户授权精确 `POLICY_FINGERPRINT`，工具才写单独 receipt。计划中的测试只验证协议，不伪造真实批准。`verify_activation` 同时核对 payload fingerprint、receipt schema、source evidence 和当前 MuJoCo/model 适用性；失败返回 `POLICY_NOT_ACTIVATED`，零 Task 8/Worker 进程启动。

- [ ] **Step 4: 验证 GREEN、离线确定性与隔离 live 证据。**

```zsh
act_test src/so101_demo_py/test/test_act_contact_calibration.py src/so101_demo_py/test/test_act_contact_policy_activation.py -q
```

随后按冻结 schema 运行 offline 100 条和 live 25 条主样本，加三类 negative control；两次 analyzer 对同一 payload 产生相同 fingerprint。独立审阅确认 evidence→payload→fingerprint 一致后停止，等待用户授权；未收到授权不得勾选 Task 8 live 的启动门。

- [ ] **Step 5: 审查并提交。**

```zsh
git add src/so101_demo_py/src/act/contact_calibration.py src/so101_demo_py/src/act/contact_policy.py src/so101_demo_py/src/cli/act_collect_contact_calibration.py src/so101_demo_py/src/cli/act_analyze_contact_calibration.py src/so101_demo_py/src/cli/act_activate_contact_policy.py
git add src/so101_demo_py/config/act/contact-calibration-schema.json src/so101_demo_py/src/core/contact_policy.py src/so101_demo_py/setup.py src/so101_demo_py/test/test_act_contact_calibration.py src/so101_demo_py/test/test_act_contact_policy_activation.py
git diff --cached --check
git commit -m "feat: calibrate and activate ACT contact policy"
```

真实 activation receipt 是运行证据，不进入源码 commit。保留所有 proposal、批准或拒绝记录；未经用户授权不得替换 fingerprint。

### Task 7: 双控制器定时提交与停止确认

**Files:**

- Create: `src/so101_demo_py/src/act/execution.py`
- Create: `src/so101_demo_py/src/adapters/act/ros_execution.py`
- Create: `src/so101_demo_py/test/test_act_execution.py`

**Interfaces:** Consumes: ActionPrefix、校准执行参数。Produces: `split_positions(rows:tuple) -> tuple[tuple,tuple]`；`ActExecutionAdapter.submit(prefix:dict, permit:dict) -> str`；`.stop(reason:str) -> str`；controller port 为 `send(goal:dict)->str, accepted(goal_id:str)->bool, cancel(goal_id:str)->None, stopped()->bool`，ROS 实现封装 FollowJointTrajectory。

- [ ] **Step 1: 写入边界失败测试。**

```python
from so101_demo.act.execution import split_positions

def test_same_rows_reach_arm_and_gripper():
    arm, gripper = split_positions(((1.,2.,3.,4.,5.,6.), (2.,3.,4.,5.,6.,7.)))
    assert arm == ((1.,2.,3.,4.,5.), (2.,3.,4.,5.,6.))
    assert gripper == ((6.,), (7.,))
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_execution.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
def split_positions(rows):
    return tuple(tuple(row[:5]) for row in rows), tuple((row[5],) for row in rows)
```

ROS adapter 构造 JointTrajectory，两者 header.stamp 相同，点的 time_from_start 根据绝对 target_times_s 转换；不能把当前墙钟作仿真 stamp。必须在共同起始时刻之前取得双方接受；失败取消双方并等待回执+实际速度低于停止阈值。send/cancel 不持有推理线程锁。维护单调动作序号、当前 goal ID 与 attempt；迟到 prefix/过期 permit 拒绝。permit 必须绑定该 prefix 内容 hash、状态 snapshot 和生效期限，不能把上一条的批准复用。替换前缀用 controller 实际插值规则验证，原 reference tap 与部署一致。无原子提交假设，单侧已开始时仍停止双方并记 CONTROLLER_PAIR_FAILED。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_execution.py -q
```

预期非零测试收集、全部通过。注入两个 fake controller：一个接受一个拒绝、一个超时、取消回执但速度未归零、停止后推理返回、旧 goal 回调、新旧前缀衔接。测试必须断言两侧被停止且无后续提交。live 重放同时读 desired/reference 与 joint feedback，证明共同时间、最大时差和停止延迟；不通过则不采集。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/execution.py src/so101_demo_py/src/adapters/act/ros_execution.py src/so101_demo_py/test/test_act_execution.py
git diff --cached --check
git commit -m "feat: coordinate ACT arm and gripper execution"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 7A: 统一 admission、typed WorkerPort 与每 Worker ROS child

**Files:**

- Modify: `src/so101_teleop/so101_teleop/unified/contracts.py`
- Modify: `src/so101_teleop/so101_teleop/unified/parents.py`
- Modify: `src/so101_teleop/so101_teleop/unified/ipc.py`
- Modify: `src/so101_teleop/so101_teleop/unified/bridge.py`
- Modify: `src/so101_teleop/so101_teleop/unified/child_runtime.py`
- Modify: `src/so101_teleop/so101_teleop/unified/ros_child.py`
- Modify: `src/so101_teleop/so101_teleop/unified/admission.py`
- Modify: `src/so101_teleop/so101_teleop/unified/teleop_service.py`
- Modify: `src/so101_teleop/so101_teleop/unified/compose.py`
- Modify: `src/so101_teleop/so101_teleop/unified/intent_store.py`
- Create: `src/so101_teleop/so101_teleop/unified/gpu_workload.py`
- Modify: `src/so101_demo_py/src/adapters/act/ros_execution.py`
- Create: `src/so101_teleop/test/teleop/test_act_campaign_admission.py`
- Create: `src/so101_teleop/test/teleop/test_act_worker_port.py`
- Create: `src/so101_teleop/test/teleop/test_act_ros_child.py`
- Create: `src/so101_teleop/test/teleop/test_gpu_workload_arbiter.py`

**Interfaces:** Consumes: 既有 `OperationSpec`、`WorkerPort`、`IpcRequest`、`BridgeProcessOwner`、`ChildRuntime`、`RclpyActionDriver` 和 unified arbiters。Produces: `UnifiedWorkloadService.start(spec:OperationSpec)->AdmittedCampaignContext`；`WorkerPort.task8(request:dict)->dict`、`.act_collection(request:dict)->dict`、`.cancel(request:dict)->dict`；closed IPC operations `task8_phase`、`task8_full`、`act_collection_start`、`act_collection_resume`、`cancel`。每个 request 必须携带 operation/campaign/worker/execution generation、session/attempt、deadline 和闭合 payload schema。

- [ ] **Step 1: 写 fail-closed admission 与 child 唯一性测试。**

```python
import pytest

def test_start_rejects_gazebo_and_creates_no_child(unified_service, gazebo_spec):
    with pytest.raises(ValueError, match="MUJOCO_ONLY"):
        unified_service.start(gazebo_spec)
    assert unified_service.child_registry.keys() == ()

def test_one_child_per_campaign_worker_generation(child_registry, launch):
    child_registry.register(launch(campaign_id="c", worker_id="w00", generation=3))
    with pytest.raises(ValueError, match="DUPLICATE_CHILD"):
        child_registry.register(launch(campaign_id="c", worker_id="w00", generation=3))
```

再参数化测试无 activation receipt、错误 policy fingerprint、过期 deadline、stale service epoch/generation、未知 operation、schema 多余字段、资源 authority 非当前 owner、cleanup fence 和 W8 正式模式缺资格记录；每一种都断言零 Worker/Recorder/ROS child 进程启动。Web 与 CLI 对同一 `OperationSpec` 必须产生逐字段相同的 context 或相同稳定错误；context 序列化回读要保留 `operation_id`、host/GPU 物理身份与 admission 时间，任一字段篡改都拒绝。

- [ ] **Step 2: 运行 RED。**

```zsh
act_test src/so101_teleop/test/teleop/test_act_campaign_admission.py src/so101_teleop/test/teleop/test_act_worker_port.py src/so101_teleop/test/teleop/test_act_ros_child.py src/so101_teleop/test/teleop/test_gpu_workload_arbiter.py -q
```

- [ ] **Step 3: 扩展现有 unified service，不建立第二套 broker。**

`AdmittedCampaignContext` 是 frozen dataclass/闭合 JSON，至少含全局接口表列出的字段，并额外保存 ROS Domain/MuJoCo session 分配表的 hash。`start` 按固定顺序：校验 MuJoCo-only 和 request schema→解析 manifest/config/policy hash→核验 activation receipt/正式 W8 资格→取得物理 GPU lease→取得 `validation` reservation→检查 cleanup fence→原子持久化 intent/context→才允许 compose children。任一步失败都逆序清理由本次调用取得的 owner 资源，不留下半启动进程。

Task 7A 同时交付通用 `ActGpuWorkloadArbiter`，不能等到并行采集阶段。它与 `GlobalMutationArbiter` 共用持久 `IntentStore`，在 admission 把 `INDEX`/`UUID` selector 和可见性映射解析为物理 GPU UUID，再按 `(stable_host_id, physical_gpu_uuid)` 互斥；歧义、映射漂移、PID 重用、未知 live owner 或 cleanup 未收敛均 fail closed。lease 绑定 service epoch、owner PID/start time、workload、physical GPU UUID、generation 与 deadline，只由 campaign owner 续租和释放。Task 8 live 因而不依赖 Task 11A 才具备 GPU admission。

资源 authority 校验到此为止。context 发出后，campaign owner 续租并处理 fencing/cleanup；`WorkerPort`、Recorder、Task 8、child 和 controller driver 不读取 operation-binding 文件、不调用 arbiter、不解析 GPU selector。内部请求只校验 context 业务身份、generation、deadline 和 payload schema；runtime telemetry 回传 campaign owner，但不能改变 admission 结论或自动降档。

扩展既有 `IpcRequest.operation` Literal 和 registry，禁止任意 import path/反射调用。`BridgeProcessOwner` 为每个 `(campaign_id, worker_id, generation)` 生成唯一 socket、ROS Domain、namespace、controller 名和 MuJoCo session；W8 正常创建八个 child。`ChildRuntime` 只路由注册方法；`ros_child.py` 保持唯一 ROS import 边界，并实现目前缺失的 `RclpyActionDriver.submit`：保留真实 action accepted/status/error、支持 cancel/stop confirmation，绝不把 IPC ACK 当执行成功。Task 7 的 paired-controller driver 通过该 typed path 调用，不另建 `act_command_broker`、`Ownership` 或兼容 ActionClient 假层。

- [ ] **Step 4: 验证 Web/CLI 等价、隔离和故障矩阵。**

```zsh
act_test src/so101_teleop/test/teleop/test_act_campaign_admission.py src/so101_teleop/test/teleop/test_act_worker_port.py src/so101_teleop/test/teleop/test_act_ros_child.py src/so101_teleop/test/teleop/test_gpu_workload_arbiter.py -q
```

fake W8 必须建立 8 个不同 Domain/session child，并证明每个 Worker 只收到自己的 request/result；注入 child crash、父进程断开、socket 路径过长、旧 generation response、deadline 到期、单 controller 接受/另一侧拒绝和 cancel 后未停稳，全部 fail closed 并进入 owner cleanup。运行期 arbiter 状态变化只由 campaign owner fencing 整个 campaign，内部组件不得自行重取 binding 或继续生成业务结果。

- [ ] **Step 5: 审查并提交。**

```zsh
git add src/so101_teleop/so101_teleop/unified/contracts.py src/so101_teleop/so101_teleop/unified/parents.py src/so101_teleop/so101_teleop/unified/ipc.py src/so101_teleop/so101_teleop/unified/bridge.py src/so101_teleop/so101_teleop/unified/child_runtime.py
git add src/so101_teleop/so101_teleop/unified/ros_child.py src/so101_teleop/so101_teleop/unified/admission.py src/so101_teleop/so101_teleop/unified/teleop_service.py src/so101_teleop/so101_teleop/unified/compose.py src/so101_teleop/so101_teleop/unified/intent_store.py src/so101_teleop/so101_teleop/unified/gpu_workload.py src/so101_demo_py/src/adapters/act/ros_execution.py
git add src/so101_teleop/test/teleop/test_act_campaign_admission.py src/so101_teleop/test/teleop/test_act_worker_port.py src/so101_teleop/test/teleop/test_act_ros_child.py src/so101_teleop/test/teleop/test_gpu_workload_arbiter.py
git diff --cached --check
git commit -m "feat: admit ACT campaigns through typed worker ports"
```

Task 7A 通过前，不进行 Task 8 live、Task 9 重放或 Task 11 采集。旧 V5 入口仍经现有 unified path 回归，不能为 ACT 新增旁路。

### Task 8: 碰撞、持物、释放与撤离监督

**Files:**

- Create: `src/so101_demo_py/src/act/task8.py`
- Create: `src/so101_demo_py/src/act/task8_manifest.py`
- Create: `src/so101_demo_py/src/act/supervisor.py`
- Create: `src/so101_demo_py/src/adapters/act/physics.py`
- Create: `src/so101_demo_py/src/cli/act_task8_live.py`
- Create: `src/so101_demo_py/config/act/task8-live-anchors.yaml`
- Create: `src/so101_demo_py/config/act/task8-live-schema.json`
- Modify: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/test/test_act_task8.py`
- Create: `src/so101_demo_py/test/test_act_task8_manifest.py`
- Create: `src/so101_demo_py/test/test_act_supervisor.py`

- Create: `src/so101_mujoco_support/msg/RobotContactEvidence.msg`
- Modify: `src/so101_mujoco_support/include/so101_mujoco_support/simulation_evidence_plugin.hpp`
- Modify: `src/so101_mujoco_support/src/simulation_evidence_plugin.cpp`
- Modify: `src/so101_mujoco_support/CMakeLists.txt`
- Modify: `src/so101_mujoco_support/test/test_simulation_evidence_plugin.cpp`
- Create: `src/so101_demo_py/src/adapters/act/contact_evidence.py`
- Create: `src/so101_demo_py/test/test_act_contact_evidence.py`

**Interfaces:** Consumes: Task 6A 已激活 policy、Task 7 执行接口、Task 7A typed `WorkerPort`、Task 1 Deadline、MuJoCo/MoveIt/controller/contact evidence。Produces: `Task8Runner.run(request:Task8Request)->Task8Result`；固定九相 `Task8Runner.PHASES`；`build_task8_live_manifest(anchors:dict, *, source_sha256:str, runtime_config_sha256:str, collection_config_sha256:str, contact_policy_fingerprint:str, calibration_report_path:str, calibration_report_sha256:str)->dict`；`release_allowed(...)`；`ActSupervisor.check(...)`；physics port `check_path(...)`、`snapshot()`。本 Task 只完成 runner、manifest primitive、监督器和运行适配，不生成可启动 bundle，也不运行 Task 8 live；Tasks 8P1–8P3 完成 preparation，Task 8P4 完成 qualification producer，Task 8L 才启动 live。

- [ ] **Step 1: 写入边界失败测试。**

```python
from so101_demo.act.supervisor import release_allowed

def test_cannot_open_unsupported_cup():
    assert not release_allowed(True, True, False, True)
    assert not release_allowed(True, True, True, False)
    assert release_allowed(True, True, True, True)

def test_phase_prefix_stops_only_after_requested_phase(fake_task8):
    result = fake_task8.run({"mode": "phase_prefix", "stop_after": "MICRO_LIFT"})
    assert result["completed_phases"] == ["SEARCH", "APPROACH", "CLOSE", "MICRO_LIFT"]
    assert result["formal_episode_eligible"] is False
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_task8.py src/so101_demo_py/test/test_act_task8_manifest.py src/so101_demo_py/test/test_act_supervisor.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
def release_allowed(holding, opening, supported, fresh):
    if holding and opening:
        return fresh and supported
    return True
```

`Task8Runner` 使用唯一固定相序 SEARCH→APPROACH→CLOSE→MICRO_LIFT→TRANSPORT→ALIGN→RELEASE→RADIAL_RETREAT→FINAL_CHECK。`phase_prefix` 在每个 `stop_after` 边界先验证规划、controller reference、joint feedback、接触、MuJoCo truth 与 Planning Scene 一致，再安全停止；prefix 永远不生成正式 episode。`full` 必须从 FULL_RESTART 开始并自主完成全部九相，禁止人工或 MoveIt recovery 接管后继续计成功。

`task8-live-anchors.yaml` 冻结 default/left/forward 三个 anchor 的场景参数；值来自 Task 6 测量，不在代码里另写默认值。`task8-live-schema.json` 要求 manifest 冻结 source/config/policy/anchors hash、三个 anchor、九条按相序排列且各含唯一 `stop_after` 的 prefix case，以及五条 full case。五条 full 的 anchor 顺序显式写入并覆盖三者，每条要求 FULL_RESTART；manifest 不接受额外 case、重复/遗漏 phase、未知 anchor 或 hash 漂移。producer 只创建新文件，已存在时拒绝覆盖。

把 holding 扩展为运行状态 EMPTY/HOLDING/UNKNOWN；上述 bool 函数只用于已明确状态，UNKNOWN 一律停止。snapshot 明确包含 session/reset_epoch/release_epoch/sim_time_s、arm 位置速度、neck 漂移、target_visible、双侧接触、杯子高度/支撑/放置稳定/撤离稳定及证据新鲜度。check_path 在独立 MuJoCo data 上重建 controller 插值与持物体积，沿前缀检查自碰撞、桌面、支架和相机；使用冻结步长与安全距离界定离散近似，实际执行中还有接触 hazard 停止。允许接触按阶段+明确几何对收窄，不把杯子整体从碰撞检查删除。开爪前必须等支撑成立，不得把尚未成立条件的开爪排入不可撤销长队列；首版在潜在释放边界截断前缀，下一 tick 用新证据重新审批。

RELEASE 先发送 `DETACH_MOVEIT` 并等待 Planning Scene 回读确认，再开放 gripper。合法释放建立新的 `release_epoch`；这不会使同一 episode 失效，但随后支撑、无持续指尖接触和放置稳定只能由新 epoch 的证据证明。RADIAL_RETREAT 先沿径向离开 10 mm，再垂直上抬 60 mm；两段都受相同 path/contact permit 约束。任何 reset、session 或 attempt 变化仍使旧证据与旧 permit 失效。



- [ ] **Step 3a: 增加不依赖杯子过滤的运行接触流。**

现有 `EvidenceBuilder::build()` 仅保留涉及杯子的接触；不能将它作为全机器人 hazard 的数据源。保留旧 SimulationEvidence/PhysicsStepEvidence 供原链路使用，另加 `/so101/simulation/robot_contacts`，消息 `RobotContactEvidence.msg`：

```text
string simulation_session_id
uint64 reset_epoch
uint64 physics_step
float64 simulation_time_s
string[] geom_a
string[] geom_b
float64[] signed_distance_m
float64[] normal_force_n
bool truncated
bool evidence_loss
```

在仿真 physics-step 回调遍历所有 `data->contact`，先按模型缓存的机器人/neck/相机/支架 geom 集合选择“任一端属于受保护集合”的接触；不经过 object_geom 过滤。杯子持物检查继续使用原流。记录所有候选接触而不是预先按允许列表丢弃；监督器根据阶段和冻结配置判定允许接触。数组长度必须一致，几何 ID 映射取实际模型，固定支架与基座等静态合法接触必须显式校准。

使用有界逐 physics-step buffer，发布所有未读记录；溢出/截断置 evidence_loss，并在仿真端保持 hazard latch 至显式 reset 新 epoch，避免短暂撞击在低频订阅中消失。Python `contact_hazard(frame:dict, allowed_pairs:set[tuple[str,str]])->bool` 拒绝失帧、truncated、旧 epoch、未知 geom 和过期样本，触发 Task 7 的双方停止。

```python
from so101_demo.adapters.act.contact_evidence import contact_hazard

def test_non_cup_contact_and_truncation_are_hazards():
    frame = {"geom_a":["arm_collision"], "geom_b":["table_collision"],
             "signed_distance_m":[-.001], "normal_force_n":[2.],
             "truncated":False, "evidence_loss":False}
    assert contact_hazard(frame, set())
    frame.update(geom_a=[], geom_b=[], signed_distance_m=[], normal_force_n=[], truncated=True)
    assert contact_hazard(frame, set())
```

`contact_hazard` 的纯函数检查数组、loss 和接触对；时间/session/epoch 校验在同文件的 `RobotContactObserver.accept(frame:dict)->None` 完成。Observer 使用 Task 4 新鲜度约定，未取得合格新帧之前不可批准路径。

```python
def contact_hazard(frame, allowed_pairs):
    if frame["truncated"] or frame["evidence_loss"]:
        return True
    pairs = list(zip(frame["geom_a"], frame["geom_b"]))
    return any(tuple(sorted(pair)) not in allowed_pairs for pair in pairs)
```

补齐长度/有限数校验后再使用此核心逻辑。C++ builder 的单测构造“不含杯子”的 arm/table、arm/arm、arm/mast 接触，断言新流保留而旧杯子流兼容；buffer overflow、reset epoch 和短暂接触也必须测。Python 接入测试注入这些消息，断言双方 controller 的 stop 被调用且旧 permit 失效。最终在仿真故障注入中确认真实非杯子接触能止动，不能只检验离线路径预测。

```zsh
colcon --log-base "$ACT_LOG_BASE" build --build-base "$ACT_BUILD_BASE" --install-base "$ACT_INSTALL_OVERLAY" --packages-select so101_mujoco_support so101_demo_py --symlink-install
source "$ACT_INSTALL_OVERLAY/setup.zsh"
act_test src/so101_demo_py/test/test_act_contact_evidence.py -q
colcon --log-base "$ACT_LOG_BASE" test --build-base "$ACT_BUILD_BASE" --install-base "$ACT_INSTALL_OVERLAY" --packages-select so101_mujoco_support --event-handlers console_direct+
colcon test-result --test-result-base "$ACT_BUILD_BASE" --verbose
```

Linux 仍先建立全局测试函数规定的 NVMe scratch 并用实际 Python 验证；C++ 消息增加后必须重新构建/source 两个包，记录类型与安装产物 provenance。默认非 ACT profile 可关闭新流，不改变原杯子证据接口。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_task8.py src/so101_demo_py/test/test_act_task8_manifest.py src/so101_demo_py/test/test_act_supervisor.py -q
```

预期非零测试收集、全部通过。补测抓取前丢失、接触阶段有界遮挡窗口、双侧接触+微抬升+离台确认、neck 漂移、悬空开爪、release epoch 只接受新证据、退臂碰杯、未知持物停住、120 s 推理阻塞与仿真暂停。监督器没有生成轨迹接口；MoveIt recovery 单独算干预。

这一阶段只跑离线/合成失败矩阵，不用 mock `TASK8_READY` 结果宣称 live 可运行。Tasks 8P1–8P4 会迁移 manifest schema、校准绑定、live qualification producer 和入口；在 receipt 原子提交之前，现有 `act_prepare_task8_live` 输出只算未提交候选，不能用于 production admission。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/task8.py src/so101_demo_py/src/act/task8_manifest.py src/so101_demo_py/src/act/supervisor.py src/so101_demo_py/src/adapters/act/physics.py
git add src/so101_demo_py/src/cli/act_task8_live.py src/so101_demo_py/config/act/task8-live-anchors.yaml src/so101_demo_py/config/act/task8-live-schema.json src/so101_demo_py/setup.py
git add src/so101_demo_py/test/test_act_task8.py src/so101_demo_py/test/test_act_task8_manifest.py src/so101_demo_py/test/test_act_supervisor.py
git add src/so101_mujoco_support/msg/RobotContactEvidence.msg src/so101_mujoco_support/include/so101_mujoco_support/simulation_evidence_plugin.hpp src/so101_mujoco_support/src/simulation_evidence_plugin.cpp src/so101_mujoco_support/CMakeLists.txt src/so101_mujoco_support/test/test_simulation_evidence_plugin.cpp src/so101_demo_py/src/adapters/act/contact_evidence.py src/so101_demo_py/test/test_act_contact_evidence.py
git diff --cached --check
git commit -m "feat: supervise ACT collision release and retreat"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 8P1: Source provenance 与 ACT collection config

**Files:**

- Create: `src/so101_demo_py/src/act/source_provenance.py`
- Create: `src/so101_demo_py/src/act/collection_config.py`
- Create: `src/so101_demo_py/src/cli/act_build_task8_source_provenance.py`
- Create: `src/so101_demo_py/config/act/task8-source-provenance-schema.json`
- Create: `src/so101_demo_py/config/act/parallel-collection-v3-schema.json`
- Create: `src/so101_demo_py/config/act/parallel_collection_v3.yaml`
- Modify: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/test/test_act_source_provenance.py`
- Create: `src/so101_demo_py/test/test_act_collection_config.py`

**Interfaces:** Consumes: Task 8 当前 source tree、已安装 overlay、`config/mujoco/parallel_batch_v3.yaml` 和已批准 policy identity。Produces: `build_source_provenance(source_root:Path, install_overlay:Path)->dict`；`write_source_provenance(document:dict, output:Path)->Path`；`verify_source_provenance(document:dict, *, source_root:Path, install_overlay:Path)->dict`；`load_collection_config(path:Path, *, package_share:Path)->dict`；CLI `act_build_task8_source_provenance --source-root PATH --install-overlay PATH --output PATH`。source provenance 的 canonical 文件 hash 是 admission 使用的 `source_sha256`；collection loader 返回闭合、已解析且绑定公共 runtime config 原始字节 hash 的配置。

- [ ] **Step 1: 写 provenance 与 collection config 的失败测试。**

```python
import pytest

from so101_demo.act.collection_config import load_collection_config
from so101_demo.act.source_provenance import verify_source_provenance

def test_collection_config_freezes_w8_and_recorder_backpressure(config_path, package_share):
    value = load_collection_config(config_path, package_share=package_share)
    assert value["qualification"] == {
        "functional_worker_counts": [1, 2], "load_worker_count": 8,
        "formal_worker_count": 8, "max_wave_size": 20,
        "no_auto_degrade": True,
    }
    assert value["recorder"] == {
        "sample_rate_hz": 10, "queue_capacity_samples": 16,
        "queue_high_watermark_samples": 12,
        "queue_recovery_watermark_samples": 8,
        "queue_high_watermark_hold_s": 0.2, "lossless": True,
    }
    assert value["recovery"] == {
        "business_retry_count": 0, "max_infra_attempts_per_scenario": 2,
        "resume_requires_identical_business_hashes": True,
    }
    assert value["telemetry"] == {"period_s": 1.0}

def test_provenance_rejects_changed_controlled_source(document, source_root, install_overlay):
    controlled = source_root / "src/so101_demo_py/src/adapters/act/command_broker.py"
    controlled.write_bytes(controlled.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="SOURCE_PROVENANCE_DIRTY"):
        verify_source_provenance(document, source_root=source_root,
                                 install_overlay=install_overlay)
```

参数化补测必需 logical role 缺失/重复、verbatim install 字节不等、compiled role 无 build receipt、receipt 输入或输出 hash 错误、external runtime 无实际路径/version、submodule 漂移、额外字段和非 canonical serialization。collection config 还要拒绝绝对路径、`..`、symlink、越出 package share、公共配置 hash 错误、非 CUDA、`allow_cpu_fallback=true`、任何 fallback 列表以及 Recorder 阈值次序错误。

- [ ] **Step 2: 运行 RED。**

```zsh
act_test \
  src/so101_demo_py/test/test_act_source_provenance.py \
  src/so101_demo_py/test/test_act_collection_config.py -q
```

预期新模块缺失或上述边界断言失败。测试 bootstrap、overlay 或 fixture 权限失败不算 RED。

- [ ] **Step 3: 实现闭合 role registry、canonical provenance 与 collection loader。**

`source_provenance.py` 固定保存 `repository_head`、全部 submodule commit、`calibration_identity.source_commit/config_sha256` 和不可由 CLI 删减的 runtime role registry。registry 至少覆盖 Task 8 Python 入口、`so101_teleop` child/owner、simulation-evidence plugin、broker-owned controller plugin、`mujoco_ros2_control`、机器人模型/控制器配置、ROS runtime 和模型权重。`verbatim_install` 同时保存 source/install 路径与 hash；`compiled` 绑定列出源码、头文件、CMake 参数、编译器、链接器、依赖库和输出 hash 的 build receipt；`external_runtime` 保存实际加载路径、文件 hash 与版本。受控 Git 路径必须相对 `repository_head` 无修改，无关用户改动不阻塞。CLI 只调用固定 registry，原子写新文件，目标已存在时拒绝覆盖。

所有 JSON 使用 UTF-8、排序键、紧凑 separators、`allow_nan=False` 和一个结尾换行。路径只接受规范化绝对路径或仓库相对 POSIX 路径。`parallel_collection_v3.yaml` 使用设计 §4.3 的完整冻结值；`parallel_runtime.path` 只能从已安装 package share 解析，hash 按原始 YAML 字节计算。head-search runtime 与公共 parallel runtime 都要求 CUDA 且禁止 CPU fallback，不提供环境变量覆盖。

- [ ] **Step 4: 运行 GREEN 与确定性复验。**

```zsh
act_test \
  src/so101_demo_py/test/test_act_source_provenance.py \
  src/so101_demo_py/test/test_act_collection_config.py -q
```

用同一 fixture 连续生成两次 provenance，要求逐字节相同。把一个受控 installed file、build receipt input 和 public runtime YAML 分别篡改 1 byte，三次都必须在创建 manifest 前拒绝。

- [ ] **Step 5: 审查并提交。**

```zsh
git add src/so101_demo_py/src/act/source_provenance.py src/so101_demo_py/src/act/collection_config.py src/so101_demo_py/src/cli/act_build_task8_source_provenance.py
git add src/so101_demo_py/config/act/task8-source-provenance-schema.json src/so101_demo_py/config/act/parallel-collection-v3-schema.json src/so101_demo_py/config/act/parallel_collection_v3.yaml
git add src/so101_demo_py/setup.py src/so101_demo_py/test/test_act_source_provenance.py src/so101_demo_py/test/test_act_collection_config.py
git diff --cached --check
git commit -m "feat: bind Task 8 source and collection provenance"
```

### Task 8P2: Task 8 测量合同、原始 batch 与确定性聚合

**Files:**

- Create: `src/so101_demo_py/src/act/task8_measurement_contract.py`
- Create: `src/so101_demo_py/src/act/task8_calibration_aggregator.py`
- Create: `src/so101_demo_py/src/cli/act_measure_task8_calibration.py`
- Create: `src/so101_demo_py/src/cli/act_build_task8_calibration_report.py`
- Create: `src/so101_demo_py/config/act/task8-calibration-measurement-contract-schema.json`
- Create: `src/so101_demo_py/config/act/task8-calibration-measurement-contract-v1.json`
- Modify: `src/so101_demo_py/config/act/calibration-schema.json`
- Modify: `src/so101_demo_py/src/act/calibration.py`
- Modify: `src/so101_demo_py/src/act/head_search_binding.py`
- Modify: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/test/test_act_task8_measurement_contract.py`
- Create: `src/so101_demo_py/test/test_act_task8_calibration_aggregator.py`
- Modify: `src/so101_demo_py/test/test_act_calibration.py`
- Modify: `src/so101_demo_py/test/test_act_head_search_binding.py`

**Interfaces:** Consumes: Task 8 core path/contact/execution evidence、Task 8P1 source provenance、runtime config、anchors、policy、ACT profile 和已关闭的 measurement batch。Produces: `bind_measurement_contract(template_path:Path, identities:dict, output:Path)->Path`；`load_measurement_contract(path:Path, *, expected_hashes:dict)->dict`；`close_measurement_batch(root:Path, identity:dict)->Path`；`aggregate_task8_calibration(batch_roots:tuple[Path,...], contract:dict, output_root:Path)->dict[str,Path]`，返回 `head_search_qualification`、`calibration_report` 和 `aggregation_receipt`。两个 report 都含必填 `source_provenance_sha256`。

- [ ] **Step 1: 写五项裁决和跨 identity 拒绝测试。**

```python
import json
import pytest

from so101_demo.act.task8_calibration_aggregator import aggregate_task8_calibration

def test_aggregator_never_trusts_raw_pass_labels(batch_factory, contract, tmp_path):
    batch = batch_factory(search_lock_frames={"default": 2, "left": 4, "forward": 4},
                          declared_status="PASS")
    outputs = aggregate_task8_calibration((batch,), contract, tmp_path / "out")
    report = json.loads(outputs["calibration_report"].read_text())
    assert report["status"] == "CALIBRATION_REQUIRED"
    assert report["checks"]["search"] == "FAIL"

def test_aggregator_rejects_mixed_source_provenance(batch_factory, contract, tmp_path):
    a = batch_factory(source_provenance_sha256="a" * 64)
    b = batch_factory(source_provenance_sha256="b" * 64)
    with pytest.raises(ValueError, match="CALIBRATION_IDENTITY_MISMATCH"):
        aggregate_task8_calibration((a, b), contract, tmp_path / "out")
```

fixture 覆盖三个 anchor 的完整专家 phase path。分别制造动态 FOV 中段出界、跨 anchor 拼接 lock frame、单点 age/skew 越界但 p95 合格、第四次完整 path-proof 调用超过 25 ms、非法接触、reference 与 permit 不一致、terminal stop 超时、cleanup receipt 缺失、batch 未关闭和时间倒退。任一输入缺失为 `UNMEASURED`；有效越界为 `FAIL`；污染 batch 为 `INVALID`，不能参与聚合。

- [ ] **Step 2: 运行 RED。**

```zsh
act_test \
  src/so101_demo_py/test/test_act_task8_measurement_contract.py \
  src/so101_demo_py/test/test_act_task8_calibration_aggregator.py \
  src/so101_demo_py/test/test_act_calibration.py \
  src/so101_demo_py/test/test_act_head_search_binding.py -q
```

预期新模块或 `source_provenance_sha256` schema 缺失。不能用手写 `TASK8_READY` fixture 让 RED 变 GREEN。

- [ ] **Step 3: 实现测量入口与纯离线聚合器。**

仓库中的 measurement contract 是闭合阈值模板。`bind_measurement_contract` 在测量前把 source provenance、runtime config、anchors、policy、ACT profile 和所有阈值来源文件原始 hash 写入 evidence root 的新合同，再计算合同 hash；不得直接把未绑定模板当作本轮合同。FOV 逐 2 ms path sample 检查 phase-camera 矩阵；search 要求每 anchor 同一目标至少 3 个连续合格 frame；synchronization 要求零缺样、零倒退且每个 age/skew 不越界；collision 覆盖三个 anchor、首个完整请求和随后三个请求，四次完整调用各自不超过 25 ms；execution 核对 reference/permit、速度、加速度、submit lead、首尾停止和 cleanup。

`act_measure_task8_calibration` 只运行测量并关闭 raw batch。它按 `PLANNED→RUNNING→VALID|INVALID` 更新现有实验账本，保存 session/reset epoch/attempt、双 RGB、joint/TF、reference/feedback、MuJoCo pose/contact、进程/socket/goal/owner cleanup。`act_build_task8_calibration_report` 不启动 ROS、MuJoCo 或模型；它重新计算所有输入 hash，按合同公式生成结果。`TASK8_READY` 仅在 fov/collision/search/synchronization/execution 全部 PASS 且 release/retreat 均 UNMEASURED 时产生；CLI 不提供状态覆盖参数。

head-search qualification sample 保存 `_MEASURED` 的 17 个值、4 个 camera measurement、三个 anchor 最小连续 lock frame 数和 `source_provenance_sha256`。校准报告内对应 17 项指向同一个 sample/hash。`calibration.py`、schema 和 `validate_head_search_binding()` 同步要求 provenance hash；旧 partial/旧 schema 继续 fail closed。

- [ ] **Step 4: 运行 GREEN、确定性和篡改矩阵。**

```zsh
act_test \
  src/so101_demo_py/test/test_act_task8_measurement_contract.py \
  src/so101_demo_py/test/test_act_task8_calibration_aggregator.py \
  src/so101_demo_py/test/test_act_calibration.py \
  src/so101_demo_py/test/test_act_head_search_binding.py -q
```

同一关闭 batch 聚合两次，三个输出逐字节一致。修改一个 raw frame、合同来源 hash、cleanup receipt 或 source provenance 后，聚合必须非零退出且不留下 `TASK8_READY`。这一步只验证 producer/aggregator，不把 fixture 结果用于 live。

- [ ] **Step 5: 审查并提交。**

```zsh
git add src/so101_demo_py/src/act/task8_measurement_contract.py src/so101_demo_py/src/act/task8_calibration_aggregator.py
git add src/so101_demo_py/src/cli/act_measure_task8_calibration.py src/so101_demo_py/src/cli/act_build_task8_calibration_report.py
git add src/so101_demo_py/config/act/task8-calibration-measurement-contract-schema.json src/so101_demo_py/config/act/task8-calibration-measurement-contract-v1.json src/so101_demo_py/config/act/calibration-schema.json
git add src/so101_demo_py/src/act/calibration.py src/so101_demo_py/src/act/head_search_binding.py src/so101_demo_py/setup.py
git add src/so101_demo_py/test/test_act_task8_measurement_contract.py src/so101_demo_py/test/test_act_task8_calibration_aggregator.py src/so101_demo_py/test/test_act_calibration.py src/so101_demo_py/test/test_act_head_search_binding.py
git diff --cached --check
git commit -m "feat: derive Task 8 calibration from measured evidence"
```

### Task 8P3: 自包含 Task 8 bundle、receipt 与 production admission

**Files:**

- Create: `src/so101_demo_py/src/act/task8_artifact_bundle.py`
- Create: `src/so101_demo_py/src/act/task8_live_evidence.py`
- Create: `src/so101_demo_py/src/cli/act_prepare_task8_live_artifacts.py`
- Create: `src/so101_demo_py/src/cli/act_validate_task8_artifacts.py`
- Create: `src/so101_demo_py/config/act/task8-preparation-receipt-schema.json`
- Create: `src/so101_demo_py/config/act/task8-live-evidence-schema.json`
- Modify: `src/so101_demo_py/src/act/pick_place_validation_manifest.py`
- Modify: `src/so101_demo_py/src/act/pick_place_runner.py`
- Modify: `src/so101_demo_py/src/adapters/act/pick_place_readback.py`
- Modify: `src/so101_demo_py/src/adapters/act/pick_place_search_port.py`
- Modify: `src/so101_demo_py/config/act/task8-live-schema.json`
- Modify: `src/so101_demo_py/src/cli/act_prepare_pick_place_validation.py`（canonical preparation implementation）
- Modify: `src/so101_demo_py/src/cli/act_run_pick_place_validation.py`（canonical live implementation）
- Modify: `src/so101_demo_py/src/cli/act_prepare_task8_live.py`（thin compatibility alias）
- Modify: `src/so101_demo_py/src/cli/act_task8_live.py`（thin compatibility alias）
- Modify: `src/so101_demo_py/src/act/pick_place_validation_campaign.py`
- Modify: `src/so101_teleop/so101_teleop/unified/pick_place_case_execution.py`
- Modify: `src/so101_teleop/so101_teleop/unified/pick_place_full_restart_campaign.py`
- Modify: `src/so101_demo_py/setup.py`
- Modify: `src/so101_teleop/so101_teleop/unified/contracts.py`
- Modify: `src/so101_teleop/so101_teleop/unified/act_artifacts.py`
- Modify: `src/so101_teleop/so101_teleop/unified/admission.py`
- Modify: `src/so101_teleop/so101_teleop/unified/bridge.py`
- Modify: `src/so101_teleop/so101_teleop/unified/ros_child.py`
- Create: `src/so101_demo_py/test/test_act_task8_artifact_bundle.py`
- Modify: `src/so101_demo_py/test/test_act_task8_manifest.py`
- Modify: `src/so101_demo_py/test/test_act_task8_live_cli.py`
- Create: `src/so101_demo_py/test/test_act_task8_live_evidence.py`
- Modify: `src/so101_demo_py/test/test_act_task8_live_campaign.py`
- Modify: `src/so101_teleop/test/teleop/test_task8_case_execution.py`
- Modify: `src/so101_teleop/test/teleop/test_task8_full_restart_campaign.py`
- Modify: `src/so101_teleop/test/teleop/test_act_campaign_admission.py`
- Modify: `src/so101_teleop/test/teleop/test_act_ros_child.py`

**Interfaces:** Consumes: Task 8P1 provenance/config、Task 8P2 calibration outputs、anchors、proposal/activation receipt 和最终 bundle path。Produces: `Task8ArtifactInputs(source_root, install_overlay, source_provenance, runtime_config, collection_config, calibration_report, head_search_qualification, measurement_contract, aggregation_receipt, anchors, proposal, activation_receipt)`；`prepare_task8_bundle(inputs:Task8ArtifactInputs, bundle_root:Path)->Path`，返回原子提交后的 `preparation-receipt.json`；`PreparedTask8Bundle(receipt, source_provenance, manifest, runtime_config, collection_config, calibration_report, proposal, activation_receipt)`；`verify_prepared_task8_bundle(receipt_path:Path)->PreparedTask8Bundle`；纯只读 `validate_task8_startup_artifacts(payload:Mapping[str,object])->PreparedTask8Bundle`；`build_task8_case_spec(bundle:PreparedTask8Bundle, case:Task8Case, journal_path:Path)->OperationSpec`；`Task8LiveEvidenceRecorder.append(sample:dict)->None`、`.seal(identity:dict)->dict`，返回闭合 `path/sha256/schema_version`。`PickPlaceExecutionPort.seal_live_evidence(request)->dict` 只在 full 的 `FINAL_CHECK` 通过后调用；`PickPlaceRunner.run()` 的闭合结果增加 `live_evidence_artifact:dict|None`，prefix 必须为 `None`，full 必须为已 seal artifact。manifest v2 同时保存 rebased `calibration_report_path`、`calibration_report_sha256` 和内部 `manifest_document_sha256`；production Task 8 payload 新增 `preparation_receipt_path` 与 `preparation_receipt_sha256`。receipt 只在 `UnifiedWorkloadService.start(spec)` 验证，不传入 Worker、Broker、Task 8 runner 或 ROS child。canonical live CLI 只接受 `--artifact-bundle` 与 `--journal`，在一次 production 调用中执行 trusted composition 固定的九个 prefix 加五个 full；两个 `act_*task8_live.py` 文件只保留兼容转发，不承载第二套逻辑。

- [ ] **Step 1: 写 bundle 提交、旧 evidence 隔离和零进程拒绝测试。**

```python
import pytest

import so101_demo.act.task8_artifact_bundle as bundle_module
from so101_demo.act.task8_artifact_bundle import prepare_task8_bundle, verify_prepared_task8_bundle

def test_committed_bundle_survives_source_evidence_becoming_unavailable(valid_inputs, tmp_path):
    receipt = prepare_task8_bundle(valid_inputs, tmp_path / "bundle-001")
    valid_inputs.calibration_report.parent.rename(tmp_path / "old-evidence-unavailable")
    verified = verify_prepared_task8_bundle(receipt)
    assert verified.calibration_report.parent == receipt.parent

def test_bundle_without_receipt_is_never_admitted(
        valid_inputs, tmp_path, workload_service, task8_spec_for_bundle, monkeypatch):
    def fail_publish(*_args, **_kwargs):
        raise OSError("injected receipt publish failure")
    monkeypatch.setattr(bundle_module, "_publish_receipt", fail_publish)
    root = tmp_path / "bundle-002"
    with pytest.raises(OSError):
        prepare_task8_bundle(valid_inputs, root)
    with pytest.raises(ValueError, match="TASK8_PREPARATION_REQUIRED"):
        workload_service.start(task8_spec_for_bundle(root))
    assert workload_service.child_registry.count == 0
```

`valid_inputs` fixture 创建闭合的七业务工件和全部传递依赖；`task8_spec_for_bundle` 只从给定 bundle 解析 production payload，不能替测试补造 receipt。

增加纯函数测试：`validate_task8_startup_artifacts()` 只解析 payload、schema、receipt、hash 和 identity，不调用 `UnifiedWorkloadService.start()`，也不取得 mutation/GPU lease。测试注入会在 resource acquire、Worker/Broker/ROS child 构造时抛错的 spy，验证纯校验成功与失败路径的 spy 调用数都为零。另测 canonical CLI 只提交一次 14-case trusted composition；九个 prefix 与五个 full 各自生成唯一 operation/session/child identity，顺序、anchor 和 `stop_after` 完全由 bundle manifest 决定。

故障矩阵逐点注入每个 file fsync、rebased report、manifest、receipt temp、receipt rename、bundle dir fsync 和 parent dir fsync。补测遗漏 qualification sample、任一唯一 `sample_path`、build receipt、原始→副本映射，错误 manifest digest 类型、receipt 之外的工件读取、不同 bundle 目录、symlink、已存在 destination、旧 schema 和 proposal/activation 内容变化。所有 admission 失败都断言零 Worker、零 Broker、零 ROS child、零动作。

- [ ] **Step 2: 运行 RED。**

```zsh
act_test \
  src/so101_demo_py/test/test_act_task8_artifact_bundle.py \
  src/so101_demo_py/test/test_act_task8_manifest.py \
  src/so101_demo_py/test/test_act_task8_live_cli.py \
  src/so101_demo_py/test/test_act_task8_live_evidence.py \
  src/so101_demo_py/test/test_act_task8_live_campaign.py \
  src/so101_teleop/test/teleop/test_act_campaign_admission.py \
  src/so101_teleop/test/teleop/test_act_ros_child.py \
  src/so101_teleop/test/teleop/test_task8_case_execution.py \
  src/so101_teleop/test/teleop/test_task8_full_restart_campaign.py -q
```

预期 preparation receipt、manifest v2 或 admission payload 字段缺失。旧 `act_prepare_task8_live` 单独生成 manifest 的成功不能算 GREEN。

- [ ] **Step 3: 实现闭包复制、rebased report、receipt 提交和启动校验。**

preparation 先重新验证输入 source provenance 与当前 source/install overlay 完全一致，再以独占 `mkdir` 创建最终 bundle path。复制七个业务工件、已绑定 measurement contract、aggregation receipt、head-search qualification sample、所有唯一 `sample_path` 和 provenance build receipt，并逐文件 fsync。原始 calibration report 不改；bundle 内生成 `admission-calibration-report.json`，只把 sample path 改为 bundle 最终绝对路径，数值、单位和 sample hash 必须逐项相同。build receipt 等审计依赖只能通过 receipt 的原始路径→副本路径映射读取，不能重新打开旧 evidence。

manifest builder/schema/validator/admission 同步迁移，manifest 内部摘要命名 `manifest_document_sha256`，receipt 另存包含换行的完整 `manifest_file_sha256`。提交前运行与 production admission 相同的 artifact validator，并只跟踪工件解析/验证读取；Python import、ROS package index、动态库和 installed runtime 由 role provenance 约束，不计入 bundle 文件闭包。receipt temp 写入并 fsync 后，以 destination-must-not-exist 原子 rename 发布，随后 fsync bundle 和父目录。receipt 出现是唯一提交点。

`UnifiedWorkloadService.start(spec)` 在取得 mutation/GPU resource 之前验证 receipt schema、完整文件集/hash、policy、source provenance、manifest 两类摘要和 bundle identity。现有共享 `_ACT_PAYLOAD_KEYS` 拆成闭合的 Task 8 与 collection 两组：`task8_phase|task8_full` 必须带 receipt path/hash，collection 继续使用自己的正式采集 schema，不能因可选字段同时接受两种形状。proposal 与 activation receipt 逐字节复制，不重新签发 policy；activation receipt 内的原 approval evidence root 保持不变，admission 通过 preparation receipt 的原始→副本映射核对它，不能要求该字段等于 bundle path。`ActArtifactBinding` 从已验证 bundle 构造七个业务工件绑定；bridge/child 不接收 receipt path，也不再次校验 campaign resource。ROS child 启动时可核对实际加载 runtime role 的路径/hash 与已准入 provenance，但不能重新读取旧 evidence、receipt 或查询 arbiter。

`act_prepare_pick_place_validation.py` 与 `act_run_pick_place_validation.py` 是实际生产实现；旧 `act_prepare_task8_live.py`、`act_task8_live.py` 只转发它们的 `main()`。live canonical CLI 从 committed bundle 构造每个 case 的唯一 `OperationSpec`，并复用 `pick_place_validation_campaign.py` 到 `pick_place_full_restart_campaign.py` 的 trusted composition；一次调用固定执行全部 `(*prefix_cases, *full_cases)`，不得分两次调用或重复 prefix。journal 只允许新建在严格的 `<run-root>/task8-live/cases/`，已存在的 case 或 summary 一律拒绝，首个失败即停止且不能用旧 case 拼接续跑。每个 case journal 必须保存 child retirement 和 stack retirement receipt 的路径/hash，以及 source/config/policy/manifest identity。

生产原始证据由 child 内真实 execution port 采集，不由父进程或测试 fixture 补造。`pick_place_readback.py` 从 CLOSE 进入时开始，覆盖 CLOSE、MICRO_LIFT、TRANSPORT、ALIGN、set-down、release、两个 retreat segment 和 FINAL_CHECK，按冻结 10 Hz 因果网格保存 same-step join，并在 phase/release epoch/contact 边沿额外保存事件样本；事件样本不能替代网格点。相邻网格间隔必须满足 measurement contract 的精确周期/容差，缺点、重复、倒退或任一源超过 frozen `max_age_s/max_skew_s` 都使 full INVALID，不能把缺样时长算作遮挡。

`pick_place_search_port.py` 持有 per-case `Task8LiveEvidenceRecorder`，逐样本写入 case 私有 staging 目录。每个 canonical sample 固定包含 `case_id/session_id/attempt_id/reset_epoch/release_epoch/physics_step/sim_time_s/phase`；`source_stamps_s` 与 `source_received_monotonic_s` 必须分别闭合保存 `world/scene/contact/head/wrist/arm/neck` 七个来源的原始数值，并保存各自可解引用 raw record 的相对路径/SHA256；还要保存 `holding_state`、`wrist_frame_valid`、`wrist_target_visible`、`contact_observation_valid`、`bilateral_contact/no_fingertip_contact/cup_supported/released/placement_stable`，以及单位明确的 `cup_support_distance_m/end_effector_position_m/cup_position_m/cup_orientation_xyzw`。raw record 必须在同一 live artifact 内，逐项绑定 session/reset/step/time，不允许只留无法解引用的 hash。identity/epoch 不匹配、非有限数、raw record 缺失/hash 错、任何 required source 无时间戳或 receipt、frame/contact observation 无效都立即使 case INVALID。

`wrist_frame_valid=true` 且完整 detector/audit 记录明确 `wrist_target_visible=false` 才是可计时的正常视觉遮挡；`wrist_frame_valid=false`、图像缺失/损坏、detector/audit 未运行、source stale/skew、`contact_observation_valid=false` 或 raw record 不闭合都是证据丢失，必须 INVALID，绝不能折算为有界遮挡。detector 权重、配置与阈值 hash 必须由 bundle manifest/source provenance 绑定，每个 audit record 回写相同 identity；该 detector 只为 Task 8 live 资格审计生成 `wrist_target_visible`，不进入 ACT observation，也不参与 ACT 动作生成。

full 的 FINAL_CHECK 通过后，runner 调用 `seal_live_evidence()`；recorder 写 canonical index 和逐样本 hash，fsync 每个 sample、index、目录与父目录，再以 destination-must-not-exist rename 发布。只有 seal 成功，runner 才能返回 artifact path/hash；prefix 明确返回 `None`。`pick_place_case_execution.py` 的闭合 `_RESULT_KEYS`、`_require_result()` 和 journal writer 同步迁移：重新读取并验证 artifact schema/hash/identity，要求路径在本 case evidence root 内且不是 symlink，再把 `live_evidence_path/live_evidence_sha256` 与 child/stack retirement receipt 的路径/hash写入 journal；父进程不得把 artifact 内容塞进 IPC，也不得信任 result 中预填的 PASS。artifact、case journal 或任一 retirement receipt 未 fsync/未封存时不发布 PASSED journal。

增加 production composition 集成测试：用真实 `PickPlaceRunner`、真实 execution-port adapter、`run_pick_place_case()` 和 trusted full-restart campaign 生成一个完整 full case journal，再由 Task 8P4 聚合器读取；测试不能手写 `live_evidence_artifact` 或完整 journal。另注入 CLOSE 后任一 phase 的 10 Hz 网格缺点/重复、各源 stamp/receipt 缺失或 stale/skew、有效帧目标不可见、无效/丢失帧、contact observation invalid、raw record 不可解引用、recorder 在 sample/index/rename/dir-fsync 处失败、result path 越界、epoch/时间倒退、artifact 篡改和 cleanup receipt 缺失；只有“有效帧且 target not visible”进入 occlusion 计时，其余证据缺口都断言没有可资格化 PASSED journal。

- [ ] **Step 4: 运行 GREEN、旧 evidence 隔离与完整 xdist gate。**

```zsh
act_test \
  src/so101_demo_py/test/test_act_task8_artifact_bundle.py \
  src/so101_demo_py/test/test_act_task8_manifest.py \
  src/so101_demo_py/test/test_act_task8_live_cli.py \
  src/so101_demo_py/test/test_act_task8_live_evidence.py \
  src/so101_demo_py/test/test_act_task8_live_campaign.py \
  src/so101_teleop/test/teleop/test_act_campaign_admission.py \
  src/so101_teleop/test/teleop/test_act_ros_child.py \
  src/so101_teleop/test/teleop/test_task8_case_execution.py \
  src/so101_teleop/test/teleop/test_task8_full_restart_campaign.py -q
```

定向测试通过后，按全局命令分别运行 `src/so101_demo_py/test/` 和 `src/so101_teleop/test/` 的完整 xdist gate，worker 数必须为 `min(8, os.cpu_count() or 1)`。每个模块使用新的 NVMe scratch 和自己的 JUnit。自包含性只用 fixture 副本或注入拒读的测试完成：准备独立临时 source-evidence fixture，提交 bundle 后让该 fixture parent 不可访问，再运行 production bundle validator 与纯只读 artifact probe。不得移动、改名或 chmod 已登记的真实 evidence root；真实 root 只做 readback 与保留。

- [ ] **Step 5: 审查并提交。**

```zsh
git add src/so101_demo_py/src/act/task8_artifact_bundle.py src/so101_demo_py/src/act/task8_live_evidence.py src/so101_demo_py/src/cli/act_prepare_task8_live_artifacts.py src/so101_demo_py/src/cli/act_validate_task8_artifacts.py
git add src/so101_demo_py/config/act/task8-preparation-receipt-schema.json src/so101_demo_py/config/act/task8-live-evidence-schema.json src/so101_demo_py/src/act/pick_place_validation_manifest.py src/so101_demo_py/src/act/pick_place_runner.py src/so101_demo_py/config/act/task8-live-schema.json
git add src/so101_demo_py/src/adapters/act/pick_place_readback.py src/so101_demo_py/src/adapters/act/pick_place_search_port.py
git add src/so101_demo_py/src/cli/act_prepare_pick_place_validation.py src/so101_demo_py/src/cli/act_run_pick_place_validation.py src/so101_demo_py/src/cli/act_prepare_task8_live.py src/so101_demo_py/src/cli/act_task8_live.py src/so101_demo_py/src/act/pick_place_validation_campaign.py src/so101_demo_py/setup.py
git add src/so101_teleop/so101_teleop/unified/pick_place_case_execution.py src/so101_teleop/so101_teleop/unified/pick_place_full_restart_campaign.py
git add src/so101_teleop/so101_teleop/unified/contracts.py src/so101_teleop/so101_teleop/unified/act_artifacts.py src/so101_teleop/so101_teleop/unified/admission.py src/so101_teleop/so101_teleop/unified/bridge.py src/so101_teleop/so101_teleop/unified/ros_child.py
git add src/so101_demo_py/test/test_act_task8_artifact_bundle.py src/so101_demo_py/test/test_act_task8_manifest.py src/so101_demo_py/test/test_act_task8_live_cli.py src/so101_demo_py/test/test_act_task8_live_evidence.py src/so101_demo_py/test/test_act_task8_live_campaign.py
git add src/so101_teleop/test/teleop/test_act_campaign_admission.py src/so101_teleop/test/teleop/test_act_ros_child.py src/so101_teleop/test/teleop/test_task8_case_execution.py src/so101_teleop/test/teleop/test_task8_full_restart_campaign.py
git diff --cached --check
git commit -m "feat: admit Task 8 from committed artifact bundles"
```

### Task 8P4: 从完整 live journal 确定性生成 `QUALIFIED`

**Files:**

- Create: `src/so101_demo_py/src/act/task8_live_qualification.py`
- Create: `src/so101_demo_py/src/cli/act_build_task8_qualified_report.py`
- Modify: `src/so101_demo_py/config/act/calibration-schema.json`
- Modify: `src/so101_demo_py/src/act/calibration.py`
- Modify: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/test/test_act_task8_live_qualification.py`
- Modify: `src/so101_demo_py/test/test_act_calibration.py`

**Interfaces:** Consumes: committed bundle 内的 `TASK8_READY` report 和 preparation receipt、canonical 14-case campaign result、每个 case journal、child/stack retirement receipts，以及 full case 的 release/retreat 原始观测。Produces: `build_task8_qualified_report(task8_ready_report:Path, preparation_receipt:Path, campaign_result:Path, case_root:Path, output:Path)->Path`；CLI `act_build_task8_qualified_report --task8-ready PATH --preparation-receipt PATH --campaign-result PATH --case-root PATH --output PATH`。输出是新的、不可变的 `QUALIFIED` calibration report；输入 `TASK8_READY` 文件保持逐字节不变。`act_preflight --measured-report PATH --source-root PATH --output PATH` 只验证已有 report，不生成或升级状态。

- [ ] **Step 1: 写完整 14-case、retirement 与 release/retreat 聚合测试。**

fixture 按 trusted composition 生成精确九个 phase-prefix 和五个连续 full。有效 case 都绑定同一 source/config/policy/manifest/preparation receipt identity，且各自有唯一 operation/session/child identity、闭合 journal hash、`full_restart_retired=true`、child retirement receipt 和 stack retirement receipt。五个 full 覆盖 manifest 冻结的 default/left/forward 序列；release sample 保存开爪前支撑、开爪后的接触消失与稳定窗口，retreat sample 保存末端撤离距离、目标稳定和 120 s deadline 内的完成时间，所有值都有单位、原始 sample path 与 SHA256。

除参数化 fixture 外，至少一条集成测试必须从 Task 8P3 的真实 `PickPlaceRunner`、execution-port adapter、`run_pick_place_case()` 和 trusted campaign 生产 full case 的 live artifact 与 journal，再直接喂给本聚合器；不得在测试中手写 runner result、live artifact index 或 case journal。该测试同时读回 seal/dir-fsync 证据，证明 producer→journal→aggregator 是同一生产路径。

失败矩阵至少包含：第 1/9/10/14 case 缺失或重复、顺序变化、prefix/full 数量不是 9/5、full 不连续、case 或 summary status 非 PASSED、跨 run 拼接、identity 混合、journal hash 篡改、旧 reset/service epoch、缺 child 或 stack retirement receipt、`full_restart_retired=false`、release/retreat sample 缺失或越界、sample path 逃逸、deadline 超时和输出已存在。任一失败均不得留下 `QUALIFIED`。

- [ ] **Step 2: 运行 RED。**

```zsh
act_test \
  src/so101_demo_py/test/test_act_task8_live_qualification.py \
  src/so101_demo_py/test/test_act_calibration.py -q
```

预期 qualification producer 或 schema 字段缺失；手写 `status=QUALIFIED`、调用 `act_preflight` 或只复制 campaign summary 不能算 GREEN。

- [ ] **Step 3: 实现离线、确定性的资格聚合器。**

聚合器先核对 preparation receipt、manifest file/document 两种摘要与 `TASK8_READY` report，再按 manifest case table 逐项重算 journal、live evidence artifact 和 retirement receipt hash。只从五个 full 的原始观测按 measurement contract 计算 `checks.release=PASS` 与 `checks.retreat=PASS`；不信任 case/result 中预填的 PASS 字符串，也不改变其余五项前置 check。合同为五项分别冻结 comparator、阈值、连续窗口算法、pose 稳定容差和跨 case reduction；不能由 CLI 覆盖：

- `grasp_occlusion_window_s`：从 CLOSE 到首次满足 release proof 的完整 10 Hz 时间线中，只累计 `wrist_frame_valid=true`、detector/audit 完整且 `wrist_target_visible=false` 的最长连续区间；五个 full 取最大值，要求不大于合同上限。无效帧、detector/audit 缺失、contact observation invalid 或任一 source stale/skew 直接 INVALID，不属于 occlusion。
- `support_distance_m`：在 set-down/release-preflight 窗口计算杯底到 manifest 绑定 support surface 的绝对有符号距离；每个 full 取窗口最大值，跨五次再取最大值，要求不大于合同上限，同时 `cup_supported=true`。
- `release_stable_s`：从 release epoch 增加后，连续满足 `released=true`、`holding_state=EMPTY`、`no_fingertip_contact=true`、`cup_supported=true` 且 source fresh 的时长；每个 full 取最长连续窗口，跨五次取最小值，要求不小于合同下限。
- `retreat_distance_m`：以 release proof 时的末端位置为基准，计算 retreat/final-check 已验证末端位置的欧氏位移；每个 full 取完成撤离时的最小合格位移，跨五次取最小值，要求不小于合同下限。命令的 nominal 0.01 m/0.06 m 不能替代 readback。
- `placement_stable_s`：retreat 后连续满足杯 pose 在合同平移/姿态容差内、`cup_supported=true`、`no_fingertip_contact=true` 且 source fresh 的时长；每个 full 取最长连续窗口，跨五次取最小值，要求不小于合同下限。

时间差只使用同一 session/reset/release epoch 内的仿真时间，并用七个 source 的原始 stamp/monotonic receipt 检查网格顺序、wall-age 与 skew；两者倒退、缺样、raw record 不可解引用或 hash 不符都使该 full INVALID。输出保存每项 conservative reduction 的值、单位、合同阈值/comparator、五个 per-case 值、原始 artifact path/SHA256 和来源 case ID，并绑定 campaign result、全部 case journals 与 retirement receipt 的 canonical digest。只有前置五项仍为 PASS、release/retreat 都通过、14 个 case 与 cleanup 全闭合时，状态才是 `QUALIFIED`。

同一组输入聚合两次必须逐字节一致。producer 不启动 ROS、MuJoCo、Worker、Broker 或模型，不取得资源 lease；output 以 temp+fsync+destination-must-not-exist rename+parent fsync 发布。

- [ ] **Step 4: 运行 GREEN、篡改与完整 gate。**

```zsh
act_test \
  src/so101_demo_py/test/test_act_task8_live_qualification.py \
  src/so101_demo_py/test/test_act_calibration.py -q
```

把一个 full sample、child retirement receipt、case journal 或 campaign summary 各篡改 1 byte，四次都应非零退出且无输出。定向通过后纳入 Task 8P3 同一轮 demo/teleop 完整 xdist 与 package gate，不额外频繁重跑 full suite。

- [ ] **Step 5: 审查并提交。**

```zsh
git add src/so101_demo_py/src/act/task8_live_qualification.py src/so101_demo_py/src/cli/act_build_task8_qualified_report.py
git add src/so101_demo_py/config/act/calibration-schema.json src/so101_demo_py/src/act/calibration.py src/so101_demo_py/setup.py
git add src/so101_demo_py/test/test_act_task8_live_qualification.py src/so101_demo_py/test/test_act_calibration.py
git diff --cached --check
git commit -m "feat: qualify Task 8 from complete live evidence"
```

### Task 8L: 生成当前 identity 工件并执行 Task 8 live

**Files:**

- Modify: `docs/experiments/so101-act-data-experiment-ledger.md`
- Create under registered evidence root: measurement batch、aggregation outputs、committed bundle、phase-prefix/full evidence 与 cleanup receipts

**执行时机：** 本节在文档中集中定义 Task 8 runtime gate，但不得在 Task 9–11A 的 source-changing 代码完成前执行。必须先完成并提交 Tasks 8、8P1–8P4、9、10、11、11A，跑完相应代码门，再冻结并安装唯一 HEAD。Task 11A 代码完成不等于可以直接跑 W1/W2；必须先返回本节完成 Task 8L。任何后续受控源变更都会撤销本节结果。

**Interfaces:** Consumes: Tasks 8、8P1–8P4、9–11A 已提交且 package/full gates 通过并安装到 `ACT_INSTALL_OVERLAY` 的同一 HEAD，已批准 contact policy，CUDA-only runtime。Produces: 当前 identity 的 committed Task 8 bundle、`TASK8_READY` admission report、九个有效 phase-prefix、五个连续有效 FULL_RESTART，以及 live 后由独立 producer 新生成的 `QUALIFIED` calibration report。该 Task 不产生训练 episode。

- [ ] **Step 1: 冻结 provenance、配置和实验条目。**

账本先追加新的 `PLANNED` measurement experiment，写明 HEAD、overlay、runtime executable、ROS Domain、MuJoCo session、evidence root、三个 anchor、合同 hash、policy fingerprint 和唯一变量。确认受控 source path 无修改，runtime/parallel config 都是 CUDA 且 `allow_cpu_fallback=false`；当前已允许 fallback 的候选文件作废，不覆盖旧证据。随后先生成本轮 source provenance：

```zsh
ACT_PACKAGE_SHARE="$(ros2 pkg prefix so101_demo_py)/share/so101_demo_py"
test -d "$ACT_PACKAGE_SHARE/config/act"
mkdir -p "$ACT_EVIDENCE/task8-preparation"
TASK8_PREP_RUN=$(mktemp -d "$ACT_EVIDENCE/task8-preparation/run-XXXXXXXX") || exit 1
export ACT_PACKAGE_SHARE TASK8_PREP_RUN
ros2 run so101_demo_py act_build_task8_source_provenance \
  --source-root "$PWD" \
  --install-overlay "$ACT_INSTALL_OVERLAY" \
  --output "$TASK8_PREP_RUN/source-provenance.json"
```

- [ ] **Step 2: 运行 MuJoCo 测量并离线聚合。**

```zsh
ros2 run so101_demo_py act_measure_task8_calibration \
  --source-root "$PWD" \
  --source-provenance "$TASK8_PREP_RUN/source-provenance.json" \
  --runtime-config "$ACT_EVIDENCE/config/head-search-runtime.json" \
  --collection-config "$ACT_PACKAGE_SHARE/config/act/parallel_collection_v3.yaml" \
  --contract-template "$ACT_PACKAGE_SHARE/config/act/task8-calibration-measurement-contract-v1.json" \
  --contract-output "$TASK8_PREP_RUN/measurement/measurement-contract.json" \
  --anchors "$ACT_PACKAGE_SHARE/config/act/task8-live-anchors.yaml" \
  --policy "$ACT_EVIDENCE/contact/proposal.json" \
  --activation-receipt "$ACT_EVIDENCE/contact/activation-receipt.json" \
  --output "$TASK8_PREP_RUN/measurement/raw"
ros2 run so101_demo_py act_build_task8_calibration_report \
  --batch "$TASK8_PREP_RUN/measurement/raw" \
  --contract "$TASK8_PREP_RUN/measurement/measurement-contract.json" \
  --output "$TASK8_PREP_RUN/measurement/aggregated"
```

读取三个输出的路径、大小和 SHA256。只有聚合报告为 `TASK8_READY`、五个前置 check 全 PASS、release/retreat 为 UNMEASURED 时继续。测量、路径检查或 controller 频率形成资源瓶颈时停止，保留 evidence 等人工决定，不修改合同或降档。

- [ ] **Step 3: 生成并验证 committed bundle。**

```zsh
ACT_TASK8_BUNDLE="$TASK8_PREP_RUN/bundle"
test ! -e "$ACT_TASK8_BUNDLE"
export ACT_TASK8_BUNDLE
ros2 run so101_demo_py act_prepare_task8_live_artifacts \
  --source-root "$PWD" \
  --install-overlay "$ACT_INSTALL_OVERLAY" \
  --source-provenance "$TASK8_PREP_RUN/source-provenance.json" \
  --runtime-config "$ACT_EVIDENCE/config/head-search-runtime.json" \
  --collection-config "$ACT_PACKAGE_SHARE/config/act/parallel_collection_v3.yaml" \
  --calibration-report "$TASK8_PREP_RUN/measurement/aggregated/task8-ready-calibration.json" \
  --head-search-qualification "$TASK8_PREP_RUN/measurement/aggregated/head-search-qualification.json" \
  --measurement-contract "$TASK8_PREP_RUN/measurement/measurement-contract.json" \
  --aggregation-receipt "$TASK8_PREP_RUN/measurement/aggregated/aggregation-receipt.json" \
  --anchors "$ACT_PACKAGE_SHARE/config/act/task8-live-anchors.yaml" \
  --policy "$ACT_EVIDENCE/contact/proposal.json" \
  --activation-receipt "$ACT_EVIDENCE/contact/activation-receipt.json" \
  --output "$ACT_TASK8_BUNDLE"
test -f "$ACT_TASK8_BUNDLE/preparation-receipt.json"
```

随后只调用纯只读 validator，不调用 `UnifiedWorkloadService.start()`：

```zsh
ros2 run so101_demo_py act_validate_task8_artifacts \
  --artifact-bundle "$ACT_TASK8_BUNDLE"
```

它调用 `validate_task8_startup_artifacts()` 核对 receipt、manifest 两种摘要、source provenance 和 rebased calibration；实现与测试必须证明它没有 resource acquire、Worker/Broker/ROS child 或控制副作用。真实运行不得移动、改名或撤销已登记 evidence root 的权限；旧 evidence 隔离只在 Task 8P3 的独立 fixture/read-denial 测试完成。

- [ ] **Step 4: 一次调用运行 trusted composition 的九个 prefix 与五个 full。**

```zsh
TASK8_CAMPAIGN_RESULT="$TASK8_PREP_RUN/task8-live/cases/campaign-result.json"
test ! -e "$TASK8_PREP_RUN/task8-live"
mkdir -p "$TASK8_PREP_RUN/task8-live/cases"
export TASK8_CAMPAIGN_RESULT
ros2 run so101_demo_py act_task8_live \
  --artifact-bundle "$ACT_TASK8_BUNDLE" \
  --journal "$TASK8_CAMPAIGN_RESULT"
```

canonical CLI 只提交这一次 production campaign；它从 manifest 读取九个唯一 `stop_after`，再按 trusted composition 继续五个 full。每个 case 使用独立 FULL_RESTART owner，并保存 child retirement 和 stack retirement 两份 receipt。任一 prefix/full 出现人工/MoveIt recovery、旧 epoch、contact evidence loss、身份/hash 漂移或 cleanup 不完整，当前 batch 立即停止并作废；不得以第二次调用补齐、跳过或拼接旧 case。

- [ ] **Step 5: 读取完整 campaign，生成并验证 `QUALIFIED`。**

```zsh
ACT_QUALIFIED_CALIBRATION="$TASK8_PREP_RUN/calibration-qualified.json"
export ACT_QUALIFIED_CALIBRATION
ros2 run so101_demo_py act_build_task8_qualified_report \
  --task8-ready "$ACT_TASK8_BUNDLE/admission-calibration-report.json" \
  --preparation-receipt "$ACT_TASK8_BUNDLE/preparation-receipt.json" \
  --campaign-result "$TASK8_CAMPAIGN_RESULT" \
  --case-root "$TASK8_PREP_RUN/task8-live/cases" \
  --output "$ACT_QUALIFIED_CALIBRATION"
ros2 run so101_demo_py act_preflight \
  --measured-report "$ACT_QUALIFIED_CALIBRATION" \
  --source-root "$PWD" \
  --output "$TASK8_PREP_RUN/qualified-readback.json"
```

campaign summary 必须精确记录 9 个 prefix、5 个连续 full、相同 source/config/policy/manifest/preparation identity，以及每个 case 的 journal 与两类 retirement receipt hash。五次 full 覆盖 default/left/forward，且每次都是独立 FULL_RESTART；逐次核对 MuJoCo、Planning Scene、controller、全机器人 contact stream、双 RGB 时间线、120 s deadline、release/retreat 原始测量和 cleanup。只有 Task 8P4 producer 从完整证据重新计算 release/retreat 且全部通过时才生成 `QUALIFIED`；`act_preflight` 只做 readback 验证，不能升级状态。失败或 INVALID 都终止当前连续批次，不能拼接旧运行。

### Task 9: 实际 reference 动作标签与无损 episode

**Files:**

- Create: `src/so101_demo_py/src/act/expert.py`
- Create: `src/so101_demo_py/src/act/recorder.py`
- Create: `src/so101_demo_py/src/adapters/act/ros_expert.py`
- Create: `src/so101_demo_py/test/test_act_recorder.py`

**Interfaces:** Consumes: Task 4 Observation、两个 controller desired/reference、goal 接受/替换事件。Produces: `require_grid(times:list[float], dt:float=0.1)->None`；`MoveItExpertActionTap.label(at_s:float)->tuple[float,...]`（取 at_s+0.1 reference）；`EpisodeRecorder(root:Path).append(observation:dict, action:tuple, audit:dict)->None`、`.finish(outcome:dict)->Path`。

- [ ] **Step 1: 写入边界失败测试。**

```python
import pytest
from so101_demo.act.recorder import require_grid

def test_missing_tick_invalidates_episode():
    require_grid([1., 1.1, 1.2])
    with pytest.raises(ValueError):
        require_grid([1., 1.2])
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_recorder.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
def require_grid(times, dt=0.1):
    if any(abs((b-a)-dt) > 1e-6 for a,b in zip(times, times[1:])):
        raise ValueError("EPISODE_TIME_GAP")
```

每个 10 Hz observation 在时刻 `t` 同步保存 head/wrist RGB 与 8D state；action 是 controller 在 `t+0.1 s` 的实际 desired/reference。goal 接受/起始/取消/替换构成有效 reference 区间。若缺目标时刻 reference，只能用经过验证的 controller 同款插值重建；不能从未来实测关节生成 action。独立 gripper goal 同步转换，没有新 goal 保持最后有效 reference；跨取消空洞无有效 hold 时拒绝 episode。原始 RGB 用无损 PNG 或等价无损格式保存，JSONL 保存原 stamp、q、reference、goal、阶段事件、代码/场景/配置/策略 hash、seed。MuJoCo truth、接触原始流、Planning Scene 和 controller 状态只进入 audit，不进入 observation。

episode 从锁定稳定开始，直到专家撤离+最终检查完成，尾部无足够未来标签的观测留审计侧，不导出伪标签。相机过期、时间倒退、reference 缺失、采样间隔超限、跨 reset/session/attempt 或无损写入失败都会使 QC 失败。合法 RELEASE 在同一 episode 内生成显式 release-epoch event，不使 episode 失效；新 epoch 之后只能使用新支撑/接触证据。Task 8 业务成功和业务失败都停止 Recorder，写不可变终态 manifest/hash，对文件和父目录 `fsync` 后运行 verifier；成功封存为 `PASSED`，业务失败封存为 `FAILED`。seal/hash/fsync/verifier 失败是基础设施故障，不能伪造 `FAILED`。只有 `PASSED`、QC 合格且随后由 Coordinator commit 的结果可进入训练配额；目录存在或 Recorder finish 不等于已提交。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_recorder.py -q
```

预期非零测试收集、全部通过。测试夹爪与手臂不同 goal、reference 替换、时间空洞、保持 state==action、重复 stamp、时间尾段、合法 release epoch、reset/session/attempt 变化、`PASSED`/`FAILED` 两种 seal、磁盘写入失败、父目录 fsync 与文件 hash。先回放一条完整示教，经 Task 7–8 验证实际物理抓放+撤离；只通过 action 数值误差不能批采。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/expert.py src/so101_demo_py/src/act/recorder.py src/so101_demo_py/src/adapters/act/ros_expert.py src/so101_demo_py/test/test_act_recorder.py
git diff --cached --check
git commit -m "feat: record controller-reference demonstrations"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 10: 可达区域与五集合空间划分

**Files:**

- Create: `src/so101_demo_py/src/act/sampling.py`
- Create: `src/so101_demo_py/src/cli/act_sample.py`
- Modify: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/test/test_act_sampling.py`

**Interfaces:** Consumes: Task 6 校准和 MoveIt 完整预检。Produces: `assert_separated(a:list[tuple],b:list[tuple],gap_m:float)->None`；`make_manifest(config:dict, seed:int)->dict`（五集合 Scenario 列表、示教候选预算与稳定 `scene_id`）；`project_collection_manifest(split_manifest:dict)->dict`（只含 Train/Validation/Offline Test，并保存总清单 SHA256）；CLI `act_sample --calibration PATH --output PATH --collection-output PATH --seed INT [--qualification-output PATH] [--qualification-load-output PATH]`。两个可选输出分别生成 8 个功能资格场景和 40 个持续负载场景，均与正式五集合互斥且不得进入训练。

- [ ] **Step 1: 写入边界失败测试。**

```python
import pytest
from so101_demo.act.sampling import assert_separated

def test_labels_do_not_hide_near_duplicate_positions():
    with pytest.raises(ValueError):
        assert_separated([(0.,0.)],[(.001,0.)],.01)
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_sampling.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
import math

def assert_separated(a, b, gap_m):
    if any(math.dist(x,y) < gap_m for x in a for y in b):
        raise ValueError("SPLIT_DISTANCE_VIOLATION")
```

Scenario 恢复必须调用 Task 3 的 joint_overrides 写入接口，不能只修改期望读回；记录 reset 后实测七关节作为清单实现证据。候选网格逐点检查桌边、碰撞、pre-grasp/grasp/lift/place/retreat IK 与完整规划、搜索可见性和双视角覆盖，输出有效单元而非包围矩形。单元内部采样的实际点重新完整检查；杯子 XY 与小幅初始关节扰动使用显式种子，初始 arm_q 不能在恢复观察姿态时无声覆盖。按距离/左右/边缘/head 锁定角分层配额，记录拒绝原因。五集合空间隔离、种子、初始状态与轨迹去重；固定外观/光照/尺寸/放置区。闭环验证场景保存 Scenario 全字段，测试场景物理失败不能抽掉后补成容易成功的集合。正式采集前按小批实测有效率为 Train/Validation/Offline Test 冻结大于成功配额的候选预算，每项生成与清单顺序无关的稳定 `scene_id`；运行期间不得临时追加随机候选。`collection.json` 必须由已经原子写入的五集合 `splits.json` 确定性投影，记录后者的内容 hash，并把 Rollout Validation/Test 标记为来源清单中的 `NOT_COLLECTION_ELIGIBLE`，不能自行重新采样。候选耗尽仍不足时输出 QUOTA_UNSATISFIED，并在新数据版本中重新采样，不能缩小隔离距离或反复执行业务失败场景暗中凑数。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_sampling.py -q
```

预期非零测试收集、全部通过。参数化检查相邻格边界泄漏、重复 seed/episode、无法达到配额、中心通过但实际点拒绝、manifest 重放、候选顺序变化时 `scene_id` 稳定、collection 投影只含三个示教 split 且总清单 hash 可读回；生成足以覆盖至少 50/10/10 成功示教目标的冻结候选预算与 10/10 闭环场景，另保留 20 个共享路线比较场景。测试清单生成前不得跑 ACT 筛成功位置。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/sampling.py src/so101_demo_py/src/cli/act_sample.py src/so101_demo_py/setup.py src/so101_demo_py/test/test_act_sampling.py
git diff --cached --check
git commit -m "feat: isolate ACT spatial splits"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 11: 小批 QC 与正式示教采集

**Files:**

- Create: `src/so101_demo_py/src/act/collection.py`
- Create: `src/so101_demo_py/src/cli/act_collect.py`
- Modify: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/test/test_act_collection.py`

**Interfaces:** Consumes: Task 9 recorder、一个 Task 10 `Scenario`、QUALIFIED 校准、已激活 policy，以及 Task 7A 的 `AdmittedCampaignContext`/typed `WorkerPort`。Produces: `training_eligible(record:dict)->bool`；`prepare_scenario(...)`（只做一次 reset、七关节读回与安全就绪证明）；`collect_authorized_scenario(...)`（从搜索到 QC，不再 reset）；W1 调试 CLI `act_collect --manifest PATH --calibration PATH --policy PATH --activation-receipt PATH --root PATH --limit INT [--qualification]`。CLI 只构造 `OperationSpec` 并调用统一服务；ports 固定 reset/search/expert/recorder/supervisor。全局候选循环、配额和并发调度属于 Task 11A。

- [ ] **Step 1: 写入边界失败测试。**

```python
from so101_demo.act.collection import training_eligible

def test_failure_is_retained_but_not_exported():
    assert not training_eligible({"qc": "PASS", "done": False, "interventions": 0})
    assert not training_eligible({"qc": "FAIL", "done": True, "interventions": 0})
    assert not training_eligible({"qc": "PASS", "done": True, "interventions": 0,
                                  "status": "PASSED", "coordinator_committed": False})
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_collection.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
def training_eligible(record):
    return (record["status"] == "PASSED" and record["qc"] == "PASS" and
            record["done"] and record["interventions"] == 0 and
            record["coordinator_committed"])
```

W1 CLI 在任何 reset 或子进程启动前把闭合 spec 交给 `UnifiedWorkloadService.start`；缺失/错误 policy、authority 非当前 owner、cleanup fence、过期 deadline 或非 MuJoCo backend 时由 admission 拒绝，并断言零动作、零 Recorder/ROS child。成功后只把不可变 context 和业务 payload 交给内部组件；内部不再读取 binding 文件或查询 arbiter。campaign owner 保持资源到最后一个 scenario 终态与 cleanup proof，CLI 提前退出不能释放。

每条 scenario 调用一次 `prepare_scenario`，把 reset epoch、实测七关节与场景哈希传给 `collect_authorized_scenario`，完成 search→lock→stable→record→teacher inference→expert→release→retreat→final-check→QC；后半段拒绝再次 reset。单 stack 入口只有 Task 11A 完成统一 admission 接线后才允许进行 5 条 smoke 与完整 W1 基线。正式模式仅采 Train/Validation/Offline Test 示教；`--qualification` 只接受 qualification 场景并阻止结果进入训练 manifest；两个 Rollout 集合不得运行专家采标签。每条成功示教受 120 s 墙钟预算；搜索、规划、执行或 QC 失败封存为不可改写业务 `FAILED`，不在此函数内重试。放置失败先保留证据再独立恢复，持物/未知时不能直接 reset。每条记录生命周期、运行产物 provenance、policy fingerprint 与模型来源。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_collection.py -q
```

预期非零测试收集、全部通过。单测注入 admission 拒绝、失败 reset、搜索歧义、MoveIt 失败、旧 reset epoch/教师 pose、QC 时间洞、Recorder 队列背压、磁盘写入失败和配置中途变化；admission 失败时断言零 reset、零动作、零子进程。搜索/内容 QC 失败成为业务 `FAILED`；Recorder 或持久化故障必须返回 infra，不得 seal 成业务失败。每个 attempt 只 reset 一次，同一 `scene_id` 的重入不能覆盖既有终态。B 阶段通过条件还包括 Task 11A W8 资格，不包括 ACT 成功率。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/collection.py src/so101_demo_py/src/cli/act_collect.py src/so101_demo_py/setup.py src/so101_demo_py/test/test_act_collection.py
git diff --cached --check
git commit -m "feat: collect quality-gated ACT demonstrations"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 11A: fixed exact-N v3 多 stack 示教采集与并发资格验证

本 Task 先完成并提交 fixed exact-N 采集实现、测试和 package/full gate；Steps 6–7 是后续现场资格门，执行时必须先回到 Task 8L，在同一最终 HEAD 上取得新的 `QUALIFIED`。因此代码完成顺序是 11A Step 5→8L，运行资格顺序是 8L→11A Step 6→11A Step 7。若 Step 6/7 前又修改任何受控代码，先重做 Task 8L。

**Files:**

- Create: `src/so101_demo_py/src/act/parallel_collection.py`
- Create: `src/so101_demo_py/src/act/parallel_collection_recovery.py`
- Create: `src/so101_demo_py/src/adapters/act/gpu_workload_client.py`
- Create: `src/so101_demo_py/src/adapters/act/parallel_collection_runtime.py`
- Create: `src/so101_demo_py/src/adapters/act/parallel_collection_results.py`
- Create: `src/so101_demo_py/src/runtime/act_fixed_collection_composition.py`
- Create: `src/so101_demo_py/src/cli/act_collect_parallel.py`
- Modify: `src/so101_demo_py/src/cli/act_collect.py`
- Modify: `src/so101_demo_py/src/cli/mujoco_parallel_batch.py`
- Modify: `src/so101_demo_py/config/act/parallel_collection_v3.yaml`（由 Task 8P1 创建；本 Task 只增加并行采集消费与回归）
- Modify: `src/so101_demo_py/src/parallel_batch/worker.py`
- Modify: `src/so101_teleop/so101_teleop/unified/bridge.py`
- Modify: `src/so101_teleop/so101_teleop/unified/teleop_service.py`
- Modify: `src/so101_teleop/so101_teleop/unified/contracts.py`
- Modify: `src/so101_teleop/so101_teleop/unified/admission.py`
- Modify: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/test/test_act_parallel_collection.py`
- Create: `src/so101_demo_py/test/test_act_parallel_collection_runtime.py`
- Create: `src/so101_demo_py/test/test_act_parallel_collection_recovery.py`
- Create: `src/so101_demo_py/test/test_act_parallel_collection_integration.py`
- Create: `src/so101_demo_py/test/test_act_parallel_collection_subprocess.py`
- Create: `src/so101_demo_py/test/test_act_gpu_workload_client.py`
- Modify: `src/so101_demo_py/test/test_parallel_batch_worker.py`
- Create: `src/so101_teleop/test/teleop/test_unified_act_collection.py`

**Interfaces:** Consumes: Task 10 冻结候选清单、Task 11 单场景接口、Task 7A `AdmittedCampaignContext`/typed `WorkerPort`、`ParallelRuntimeConfigV3`、`BatchRequestV3`、fixed shared queue、Coordinator/Worker/start guard/cleanup。Produces: `partition_waves(...)`；`FixedActCollectionCampaign(manifest:dict, config:dict, context:AdmittedCampaignContext, root:Path).run()->dict`；`ActFixedWaveRecovery.resume(wave_record:dict, context:AdmittedCampaignContext)->dict`；`ActCollectionResultStore`/`ActCollectionResultVerifier`；原子 `qualification-contract.json` 和 `campaign-index.json`。CLI `act_collect_parallel --manifest PATH [--split-manifest PATH] --calibration PATH --policy PATH --activation-receipt PATH --collection-config PATH --runtime-config PATH [--qualification-contract PATH] --root PATH [--qualification] --worker-count INT [--resume]` 只创建 `OperationSpec` 并调用统一服务。W8 资格必须显式传入尚不存在的 contract 路径，由入口在 spawn 前原子创建；已存在或不可持久化则拒绝。资格模式只允许 W1、W2 或独立 W8 清单；正式模式必须是 exact W8 且引用未撤销的 40 场景 W8 资格。

- [ ] **Step 1: 写外层 wave、终态与恢复的失败测试。**

```python
from so101_demo.act.parallel_collection import partition_waves

def test_manifest_order_is_partitioned_without_duplication():
    scene_ids = tuple(f"scene-{index:03d}" for index in range(45))
    waves = partition_waves(scene_ids, max_wave_size=20)
    assert tuple(map(len, waves)) == (20, 20, 5)
    assert tuple(item for wave in waves for item in wave) == scene_ids
```

增加 fake exact-W2/W8 集成测试：每个 `scene_id` 只有一个业务终态；`PASSED` 与 `FAILED` 都必须先 seal、verifier 通过并由 Coordinator commit；业务 `FAILED` 不重试。未提交项只能在相同 W8、manifest、runtime/collection config、policy 和 campaign 数据身份下 `--resume`，允许新 resource binding/generation；同一 scenario 的冲突终态拒绝。journal 截断恢复到最后一个 fsync 事件。另模拟父进程在 seal/commit 后、外层导入前退出，要求从 commit 重放导入，不扫描任意目录，也不创建 W1 continuation。

- [ ] **Step 2: 验证 RED。**

```zsh
act_test \
  src/so101_demo_py/test/test_act_parallel_collection.py \
  src/so101_demo_py/test/test_act_parallel_collection_runtime.py \
  src/so101_demo_py/test/test_act_parallel_collection_recovery.py \
  src/so101_demo_py/test/test_act_parallel_collection_integration.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。不得把既有 adaptive tests 的通过当成本任务 RED。

- [ ] **Step 3: 实现确定性 exact-N wave、统一 authority 与外层配额。**

`FixedActCollectionCampaign` 只创建 `RunMode.EXECUTE` 的 `BatchRequestV3`，先校验 manifest hash、成功配额、唯一 `scene_id`、split 白名单和 context identity。正式模式固定 `worker_count=8`，要求未撤销的 ACT W8 资格记录，并核对五集合总清单、collection 投影、三个示教 split 的逐项身份/顺序；Rollout 场景拒绝。`--qualification` 只接受 `qualification`，禁止 `--split-manifest`，使用隔离 root，不能生成 Task 12 可消费的训练 manifest。`BatchRequestV3` 本身不限 20 项；ACT config 冻结 `max_wave_size=20`。campaign 按清单顺序分 wave，每个 wave 创建短 ASCII batch ID、相同 exact N 和独立 v3 request。外层 fsync journal 记录 `COLLECTION_MANIFEST`、`CAMPAIGN_ADMITTED`、`WAVE_STARTED`、`SCENARIO_TERMINAL`、`WAVE_TERMINAL`、split 配额和 summary。

所有启动资源检查都由 `UnifiedWorkloadService.start` 在第一条 wave 前完成并返回 `AdmittedCampaignContext`。Web/CLI 不自行核验或重签 binding；Worker、Recorder、Broker、Task 8 与 ROS child 不查询两个 arbiter。campaign owner 保持 GPU lease 与 `validation` reservation 到所有 wave 终态和 owned cleanup 收敛，负责 heartbeat、fencing、runtime telemetry 与 release；HTTP/CLI 提前退出不能释放。训练持有同 GPU lease 时采集 admission 失败，采集持有时训练 admission 同样失败。

Task 11A 复用 Task 7A 已交付的 `ActGpuWorkloadArbiter`，不再实现第二份 authority。状态仍与 `GlobalMutationArbiter` 共用持久 `IntentStore`；admission 解析稳定 host 与物理 GPU UUID，campaign owner 续租，内部组件只保留 context 审计摘要。服务重启先恢复并 fencing，未知 live owner 时保持阻塞。

外层发现未终态 wave 时，`ActFixedWaveRecovery` 先取得 collection root 的独占恢复锁，读取 batch ID、resource/owned-process manifest 和 coordinator journal；调用 main 的 fixed resume fence，确认旧 Worker/Broker 进程、controller goal、socket 与 Domain 已停止或仍由同一恢复流程精确拥有。任一对象身份不明或无法清理时停止。fencing 后按 coordinator journal 顺序重建 lease 裁决。已有 result commit 的位置调用 `ActCollectionResultVerifier.verify`；缺 commit 时只允许 main 固定恢复协议在该 lease 的登记 workspace 调用 `discover`。`LEASE_EXPIRED`、revocation、replacement 与 `LATE_RESULT_REJECTED` 优先于磁盘 seal；迟到封存只保留审计。每个验证通过的结果以 `SCENARIO_RECONCILED` fsync 到外层 journal，保留 batch、worker generation、attempt 和 commit sequence。

剩余 scenario 保持原 wave 顺序，只能由同一 batch ID、exact W8、manifest/runtime config/collection config/policy hash 和 campaign 数据身份的 `--resume` 继续；恢复必须重新 admission，因此 resource binding 和 generation 可以更新。若 main 的 fixed resume fence 不成立，wave 标记 `INFRA_INVALID`，campaign 停止并保留未完成列表；新运行必须用新 batch ID/证据目录，不能伪装 continuation。业务失败不进入 resume。外层记录每个 scenario 的 infra attempt，超过冻结上限形成 `INFRA_EXHAUSTED`。

每个 wave 通过 `ActFixedBatchComposition` 复用 v3 shared queue、lease、heartbeat、Domain claim、start guard、owned-process manifest 和 cleanup。公共 `parallel_batch_v3.yaml` 保持原样；`parallel_collection_v3.yaml` 只保存 workload、Recorder、资格和配额字段，并绑定公共配置 hash。`scenario_id` 映射为 `point_id` 只属于调度适配，终态工件仍使用 collection schema。`PointStatus.PASSED` 表示训练合格 episode，`PointStatus.FAILED` 表示已封存业务失败；二者均不可改写。

正式采集按 split 和冻结顺序分别分 wave，一个 wave 完整终态后才判断配额。每个 split 选择 manifest 顺序中前 N 个训练合格结果；包含第 N 个成功的 wave 中，排在其后的成功 episode 保留为 `SURPLUS_SUCCESS` 但不进入 Task 12，之后的 wave 标记 `UNSCHEDULED_QUOTA_MET`。因此 Worker 完成顺序不会改变数据集成员。资格模式没有成功配额，必须消费完整资格清单。增加乱序完成测试，要求 W1/W2 的选中 `scene_id` 集合一致。

Task 11A 只消费并回归 Task 8P1 已生成的 `parallel_collection_v3.yaml`，不在这里创建第二份 schema 或改写冻结值。配置分开声明 `functional_worker_counts: [1,2]`、`load_worker_count: 8`、`formal_worker_count: 8`、`max_wave_size: 20`、Recorder 队列上限、infra attempt 上限和 telemetry 周期，并引用 `parallel_batch_v3.yaml` 的路径/SHA256。它没有 fallback 序列，也不把 W8 导出为项目全局默认值。运行目录固定为 `<registered-root>/<run-code>/r/<one-char-wave-id>/wNN`；`run-code` 只允许 `s`、`u`、`q1`、`q2`、`q8`、`d`。

`act_fixed_socket_paths(batch_root, worker_count)` 是唯一 endpoint manifest，合并 fixed Coordinator/Broker/Worker 端点和每个 Worker 的 typed ROS child IPC 端点。启动预检、owned-process manifest、cleanup 和恢复读取同一清单；不存在 Task 7A 私有 command broker。CLI 在创建进程前用真实 evidence root 枚举全部端点，最长编码路径超过 107 bytes 立即拒绝。测试断言启动、清理与恢复使用同一集合，并以实际最长端点验证 107 bytes 通过、根路径增加 1 byte 后 108 bytes 且零进程启动。

- [ ] **Step 3a: 适配现有 Worker ports、start guard 与统一 reservation，不复制调度状态机。**

在 `parallel_batch/worker.py` 增加可选、闭合的 workload port。未指定时构造 `PointValidationWorkload`，逐行封装当前 `_run_authorized` 的既有 inference→admit→execute/plan 逻辑，确保原 CLI、v3 shared queue 和证据字节契约保持不变；`act_collection` 才构造 `ActCollectionWorkload`。Worker 继续维护 shared-queue terminal lease 的 heartbeat/`_boundary`、异常捕获与 `_safe_stop`；这不是 campaign resource binding 的再次校验。workload 只能通过 context 绑定的 typed callback 调用 runtime/Broker，不能绕过 Coordinator 或 WorkerPort。两类 workload 返回 `AuthorizedWorkloadResult`，再由 Worker 执行既有 seal/commit/recovery。ACT 搜索/规划/QC 业务失败作为正常 decision 返回，不能抛异常进入基础设施恢复。

`ActCollectionWorkerRuntime.reset_point` 调用 Task 11 `prepare_scenario`，只做一次 reset、实测七关节读回和 reset epoch 建立；`point_initial_gate` 只验证 controller 无活跃 goal、相机/Recorder/Broker/ROS 就绪和 preparation 身份，不执行 head 搜索，不把业务失败塞进初始门。`ActCollectionWorkload.run_authorized` 在获准阶段一次完成 head 搜索、相机稳定、教师 snapshot/Broker inference、pose 陈旧检查、录制、专家执行和 QC，并调用 `collect_authorized_scenario`，禁止第二次 reset。搜索歧义/未找到、规划/执行失败和 QC 失败返回正常业务 `FAILED`；端口、进程、通信或封存故障返回 `INVALID/INDETERMINATE`，停止当前 campaign 或按原 exact N 显式恢复。每个动作边界同时要求有效 terminal lease 和 context 绑定的 WorkerPort；内部不重新向资源 authority 申请许可。

Broker 请求/响应必须关联 batch、worker、worker generation、`scenario_id`/point、attempt、lease generation、reset epoch、request sequence 和输入帧时间。现有 LeaseIdentity 已包含的字段直接复用；reset epoch 和 frame stamp 由 ACT runtime 作为请求负载校验。head 搜索检测留在 Worker 进程，head/wrist 训练帧由 Worker 私有 Recorder 直接写盘，不进入共享 Broker。

`ActFixedBatchComposition` 构造闭合 worker spec，写入 `workload_kind`、scenario manifest/config 绝对路径/hash、policy fingerprint、campaign 数据身份、context 审计摘要及 v3 runtime hash。明确修改真实入口 `cli/mujoco_parallel_batch.py::_build_worker_from_spec`：schema 接受闭合 `workload_kind=point_validation|act_collection`，默认仍选 `_ArtifactResults`/`RosWorkerRuntimePorts`；ACT 值从本地 registry 选择 `ActCollectionWorkerRuntime`、`ActCollectionWorkload`、`ActCollectionResultStore` 和 verifier adapter，禁止任意 import path。`_start_workers` 继续使用现有 `python -m so101_demo.cli.mujoco_parallel_batch --internal-worker <spec>` argv，因此 cleanup/owned-process 逻辑不分叉。resume 拒绝 workload、业务 hash、exact N 或 campaign 数据身份变化，但接受统一服务签发的新 resource binding/generation。

`test_act_parallel_collection_subprocess.py` 必须启动真实 `--internal-worker` 子进程，而不是只调用 fake composition：用 in-package closed test ports 提供无 ROS 副作用的一个 ACT scenario，等待 child READY，完成一次 `FAILED` 业务结果的 seal/verifier/commit，再读回 child 报告的四个 factory identity；同时运行默认 point-validation spec，证明原 builder 字节契约不变。未知 workload/额外字段在真实子进程中非零退出且不创建结果目录。

start guard 使用 v3 `EpochStartGuard`，作为统一 service admission 的内部步骤：preflight 一次，真正 spawn 前按同一 batch/epoch/owner scope 再运行一次。CPU、RAM、GPU、cleanup、owner 或 probe failure 按冻结 policy fail closed。start guard 通过不写 ACT 并发资格，也不能替代 W2 或 W8 负载实测。admission 完成后，Worker/child 不再重复执行资源 authority 校验。

统一 bridge 增加闭合 `act_collection_start|act_collection_resume|cancel` operation，与 Task 7A 的 Literal/registry 一致。服务在 dispatch 前持久写入 intent/context，child ACK 后记录真实 campaign/batch/owner identity。cancel 只作用于已登记 campaign，先冻结新 terminal lease，再取消 owned controller goal/process；accepted 不等于 cleanup confirmed。Web 重启只能恢复 projection 和 blocked 原因，不自动重发采集命令。

`ActCollectionResultStore` 在 Worker 私有临时目录写原始 RGB、状态/action、事件、QC 和 provenance；成功或业务失败都先写闭合 manifest、逐文件 hash，以及由 Worker/Coordinator 共用注入时钟产生的 `completed_monotonic_s`，再原子 rename 并 fsync 文件与父目录。它完整实现 Worker 需要的 `seal_attempt`、`write_recovery_receipt`、`verify_recovery_receipt`。`ActCollectionResultVerifier` 实现 `verify(lease, location, run_mode)` 与 `discover(lease, workspace)`，只在登记 workspace 内确认身份、状态、hash、完成时间和终态都匹配的结果，并拒绝 `completed_monotonic_s > lease_deadline_monotonic_s`。每个 wave 终态后，外层聚合器原子更新 `campaign-index.json`，逐项绑定 batch ID、实际 coordinator journal root/hash、commit sequence、verifier receipt root/hash 和 episode hash；它不复制或合并 coordinator journal。Task 12 只从这个索引逐 wave 回放有效 result commit。即使 `discover` 找到封存目录，也必须先形成合法 commit 才能导入。

失败分类必须分开：相机来源时间洞、reference 缺失等内容问题可形成业务 QC `FAILED`；Recorder queue overflow、持续写入达不到无损要求、文件/rename/fsync/verifier 失败属于基础设施 `INVALID/INDETERMINATE`，不能伪造 `FAILED`。每个 Worker 使用独立队列，每次 enqueue 同步检查深度；达到 16 立即失败，连续 0.2 s 不低于 12 时停止发放新 terminal lease，恢复前必须回落到 8 或以下。1 s telemetry 只记录 campaign 资源，不承担溢出保护。瞬时 Recorder/进程故障 fence 当前 wave 后只允许相同 W8 数据身份恢复。若 queue 高水位不回落、磁盘吞吐/延迟持续越过 `qualification-contract.json` 或资源采样缺失，则是 campaign 资源瓶颈：立即停止整个 W8，保留未完成候选，等待人工决策，不自动 resume 或继续消费清单。

- [ ] **Step 4: 验证 GREEN、隔离和故障矩阵。**

```zsh
act_test \
  src/so101_demo_py/test/test_act_parallel_collection.py \
  src/so101_demo_py/test/test_act_parallel_collection_runtime.py \
  src/so101_demo_py/test/test_act_parallel_collection_recovery.py \
  src/so101_demo_py/test/test_act_parallel_collection_integration.py \
  src/so101_demo_py/test/test_act_parallel_collection_subprocess.py \
  src/so101_demo_py/test/test_act_gpu_workload_client.py \
  src/so101_demo_py/test/test_parallel_batch_worker.py \
  src/so101_demo_py/test/test_parallel_batch_crash_recovery.py -q
act_test \
  src/so101_teleop/test/teleop/test_unified_act_collection.py \
  src/so101_teleop/test/teleop/test_gpu_workload_arbiter.py -q
```

预期非零测试收集、全部通过。故障矩阵至少覆盖：旧 point-validation spec 保持原契约；ACT spec 构造 typed workload；每 scenario 只 reset 一次；搜索失败封存/commit 为 `FAILED` 且不重试；旧 teacher pose/reset/release epoch 拒绝；W8 八个 Worker 的 ROS Domain/namespace/session/root 互异；错误 Worker 或旧 generation 响应拒绝；相机内容时间洞成为业务 QC；Recorder overflow、写入/fsync/verifier 故障成为 infra，停止新 lease 且不消费后续候选；持续 queue/disk/telemetry 阈值越界停止 campaign 等待人工；admission 第二次 start guard 拒绝后零 spawn；缺失 activation、foreign resource owner、cleanup fence 零 spawn；Web/CLI 同 spec 同结果；GPU selector 别名仍互斥；映射漂移/歧义 fail closed；训练与采集互斥；owner PID 重用、heartbeat 过期和未知 cleanup fail closed；W8 qualification 无需旧资格但正式模式必须有；seal 后 ACK 前崩溃按相同 W8 数据身份恢复；迟到 seal 拒绝；commit 后外层导入前崩溃可重放；未完成 fencing 禁止 resume；不同 N、manifest、config、policy 或 campaign 数据身份的 resume 拒绝，新 resource binding/generation 接受；目录无 commit 不进入数据集；campaign index 缺 wave、错 journal hash、重复 commit sequence 或 receipt 冲突拒绝；两个 20 项 W8 wave 中每个 Worker 至少两个实际 terminal；不同完成顺序选择相同 manifest 前 N 个合格 `scene_id`；完整 endpoint manifest 107 bytes 通过、108 bytes 时零进程启动；SIGTERM 后 owned process、Domain、socket、ROS child、controller goal、GPU lease 和 reservation 精确收敛。

- [ ] **Step 5: 审查并提交实现；在 Task 8L 前完成。**

```zsh
git add \
  src/so101_demo_py/src/act/parallel_collection.py \
  src/so101_demo_py/src/act/parallel_collection_recovery.py \
  src/so101_demo_py/src/adapters/act/gpu_workload_client.py \
  src/so101_demo_py/src/adapters/act/parallel_collection_runtime.py \
  src/so101_demo_py/src/adapters/act/parallel_collection_results.py \
  src/so101_demo_py/src/runtime/act_fixed_collection_composition.py \
  src/so101_demo_py/src/cli/act_collect_parallel.py \
  src/so101_demo_py/src/cli/act_collect.py \
  src/so101_demo_py/src/cli/mujoco_parallel_batch.py \
  src/so101_demo_py/config/act/parallel_collection_v3.yaml \
  src/so101_demo_py/src/parallel_batch/worker.py \
  src/so101_teleop/so101_teleop/unified/bridge.py \
  src/so101_teleop/so101_teleop/unified/teleop_service.py \
  src/so101_teleop/so101_teleop/unified/contracts.py \
  src/so101_teleop/so101_teleop/unified/admission.py \
  src/so101_demo_py/setup.py \
  src/so101_demo_py/test/test_act_parallel_collection.py \
  src/so101_demo_py/test/test_act_parallel_collection_runtime.py \
  src/so101_demo_py/test/test_act_parallel_collection_recovery.py \
  src/so101_demo_py/test/test_act_parallel_collection_integration.py \
  src/so101_demo_py/test/test_act_parallel_collection_subprocess.py \
  src/so101_demo_py/test/test_act_gpu_workload_client.py \
  src/so101_demo_py/test/test_parallel_batch_worker.py \
  src/so101_teleop/test/teleop/test_unified_act_collection.py
git diff --cached --check
git commit -m "feat: collect ACT demonstrations across isolated stacks"
```

提交前确认暂存区没有用户已有改动。这个 commit 与代码门是冻结 runtime identity 的前置条件，但不代表任何现场资格已经通过；提交后返回 Task 8L，在同一 HEAD 安装、生成 provenance 并取得 `QUALIFIED`。

- [ ] **Step 6: Task 8L 通过后，运行 W1/W2 资格批次。**

先生成单独的功能资格 manifest，使用 8 个覆盖不同区域和搜索角的 scenario；这些 episode 永久标记 `qualification`，不进入 Train/Validation/Offline Test。对同一清单分别运行 W1 单条入口、W1 并行入口和 W2。语义等价比较 schema、scene/reset 身份、10 Hz 时间网格、reference 定义、QC/失败分类、封存结构和物理结果，不要求不同运行的像素或 MoveIt 浮点轨迹逐字节相同。

W2 通过条件：8 个 scenario 各有唯一终态；无跨 Worker topic、帧、controller goal 或目录写入；无静默丢帧；所有进程、Domain、socket、goal 与 reservation 完成精确清理；`worker_count == 2`，零 infra interruption/retry、零 crash resume；有效 episode/分钟高于完整八场景 W1 基线，且物理成功率和 QC 合格率没有超出运行前冻结的退化容差。每次运行记录 source/runtime config/collection config/manifest/policy/context hash、worker count、每 scenario infra attempts、CPU、RSS、GPU、磁盘写入、RTF、帧间隔、吞吐与失败分布。恢复批次只证明恢复，不计 W2 资格或吞吐。W2 未通过时不启动 W8。

- [ ] **Step 7: W2 通过后，运行一次独立 40 场景 exact-W8 资格，再进行正式 W8 采集。**

W2 通过后，冻结一份与八场景清单、正式五集合都不重叠的 40 场景 load manifest，并按顺序分成两个完整 20 项 wave。启动前写不可变 `qualification-contract.json`，绑定 source、submodule、install/runtime executable、manifest、runtime config、collection config、policy fingerprint 和 context schema hash；同时冻结指标单位、采样窗口及 CPU/GPU/RAM 上限、磁盘 latency/持续吞吐、MuJoCo RTF 下限、Recorder queue 高水位/回落时间、10 Hz frame-gap 分位数、有效 episode/分钟、物理成功率和 QC 合格率阈值。运行中不得改阈值。

两个 wave 都必须 `worker_count == 8`。每个 wave 的每个 Worker 都要通过实际 terminal lease 连续完成至少 2 项，静态 preferred assignment 不算；40 场景全部产生唯一终态，零 infra interruption/retry、零 crash resume。任何指标越界、后半程吞吐持续下降、队列不能回落、资源采样缺失或 Worker terminal 覆盖不足，W8 资格失败并停止等待人工决策。不得自动降 Worker、换设备、降画质/采样，或用 W1/W2 continuation 冒充 W8。恢复运行只证明恢复协议，不授予资格。

本轮只要求一次完整 40 场景 W8。若人工决定失败后重测，使用新的 qualification ID 和 evidence 子树，从头运行全部 40 场景；不能拼接不完整结果。通过后签发仅适用于本 ai-station ACT campaign 的资格记录，不修改其他 workload 默认值。

正式采集固定 exact W8、`max_wave_size=20`，按 Train 50、Validation 10、Offline Test 10 的冻结候选顺序运行。基础设施中断只能在相同 W8、manifest/config/policy/campaign 数据身份下显式恢复；业务 `FAILED` 不重试。每个 split 完成包含第 N 个成功的整个 wave 后，按 manifest 顺序选择前 N 个已 commit 的 `PASSED`+QC episode；同 wave 后续成功保留为 `SURPLUS_SUCCESS`，不进入 Task 12。聚合器同时原子写 `d/campaign-index.json`（wave/commit/receipt 索引）和 `d/manifest.json`（最终选中 dataset manifest），两者互相保存内容 hash。候选耗尽不足返回 `QUOTA_UNSATISFIED`，保留全部失败、surplus 与未调度原因。

代码提交不代表运行门完成；只有 Task 8L、W1/W2、完整 40 场景 W8 资格和正式 W8 采集各自的现场证据满足对应门槛后，才能分别勾选。W8 失败时停在人工决策点，不创建低档正式 continuation。

### Task 12: LeRobot 导出、训练与模型工件

**Files:**

- Create: `src/so101_demo_py/src/act/bundle.py`
- Create: `src/so101_demo_py/src/act/training_owner.py`
- Create: `src/so101_demo_py/src/adapters/act/lerobot.py`
- Create: `src/so101_demo_py/src/cli/act_train.py`
- Create: `src/so101_demo_py/config/act/training.yaml`
- Create: `src/so101_demo_py/config/act/requirements.lock`
- Modify: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/test/test_act_bundle.py`
- Create: `src/so101_demo_py/test/test_act_training_owner.py`

**Interfaces:** Consumes: Task 11A 的 `campaign-index.json`、各 wave coordinator journal/verifier receipt、确定性正式 manifest、统一服务只读状态和 `ActGpuWorkloadArbiter` 签发的 training GPU binding。Produces: `resolve_committed_episodes(manifest:dict, campaign_index:Path)->tuple[dict,...]`；`export_dataset(committed:tuple[dict,...], output:Path)->Path`；`TrainingRunOwner.acquire(run_root:Path, dataset_sha256:str, config_sha256:str, gpu_lease:dict)->dict`；`train_act(config:dict, dataset:Path, owner:dict, output:Path)->Path`；`load_bundle(path:Path)->dict`；`load_policy(bundle_path:Path)->object`（返回具有 `infer(observation:dict)->tuple[tuple[float,...],...]` 与 `reset()->None` 的模型对象）；CLI `act_train --manifest PATH --campaign-index PATH --gpu-binding PATH --config PATH --output PATH --device DEVICE`。

- [ ] **Step 1: 写入边界失败测试。**

```python
from so101_demo.act.bundle import resolve_committed_episodes, training_rows

def test_normalization_uses_only_train():
    rows = [{"split":"train","state":[1.]}, {"split":"validation","state":[100.]}]
    assert training_rows(rows) == [rows[0]]

def test_directory_seal_without_coordinator_commit_is_rejected(tmp_path):
    (tmp_path / "episode-001").mkdir()
    assert resolve_committed_episodes(
        manifest={"episodes": [{"scene_id": "001", "status": "PASSED"}]},
        campaign_index=tmp_path / "campaign-index.json",
    ) == ()
```

还要覆盖：旧 `0917a` dataset/run ID、qualification、`SURPLUS_SUCCESS`、业务失败、迟到 seal、索引缺 wave、journal root/hash 或 verifier receipt 缺失、receipt/hash 冲突、collection 投影外的 split、batch 内重复 commit sequence、可变 manifest 和目录扫描输入均被拒绝。训练 owner 测试覆盖 arbiter 非 `IDLE`、同 GPU 已有采集/Broker/另一训练 lease、两个不同 run root 并发领取、训练持有 lease 后采集 admission、PID 重用、heartbeat 过期、owner/config/dataset/device 不匹配和失败后证据保留。

- [ ] **Step 2: 验证 RED。**

```zsh
act_test \
  src/so101_demo_py/test/test_act_bundle.py \
  src/so101_demo_py/test/test_act_training_owner.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

训练导出不遍历 episode 目录，也不假设顶层存在合并 journal。`resolve_committed_episodes` 从 `campaign-index.json` 逐 wave 定位实际 batch ID 与 coordinator journal root，先核对 journal/receipt hash，再按 batch 内 commit sequence 回放 result commit，校验 lease identity、split、dataset/run ID 和 verifier receipt，最后按冻结 manifest 顺序生成不可变导出清单。只接收状态为 `PASSED` 且被正式配额选中的 Train、Validation、Offline Test episode；旧 `0917a`、qualification、surplus、失败、未提交 seal、迟到结果和路径推断一律拒绝。导出清单保存来源 manifest、campaign index、各 journal/receipt、逐 episode 内容和输出数据的 SHA256；源文件变化后不能继续训练，也不能在原导出目录增量补写。

正式训练前读取统一服务状态，要求 `GlobalMutationArbiter` 为 `IDLE`，且最新 cleanup proof 已收敛；然后由与采集 admission 相同的 `ActGpuWorkloadArbiter` 解析请求 selector，并对稳定 host identity + 物理 GPU UUID 原子领取训练 lease。只读现场进程/GPU inventory 用于解析设备和发现 authority 外未知 owner，不能代替 lease。`TrainingRunOwner` 对独立 run root 建立单写者身份，并绑定 GPU lease ID/generation、PID、process start time、host、物理 GPU UUID、dataset/config hash、解释器和依赖锁。另一个 run root、采集或 Broker 争用同 GPU 时由同一持久 authority 拒绝；heartbeat 失联先 fencing 并确认原进程不存活，不能按超时直接偷锁。训练结束后只有 owner 终态和 GPU cleanup/release proof 均落盘才释放 lease。训练不申请机器人 mutation reservation；进程退出后保留 owner、stderr、checkpoint 与 `FAILED|COMPLETED` 终态，不自动清理或覆盖。dataset export 只读，checkpoint 写入本 run 私有目录。

在独立训练 venv 安装 LeRobot/PyTorch，执行时读取所选版本 ACT 配置、数据 API 源码和官方文档，版本解析后生成精确 requirements.lock 与来源 SHA；不在 ROS 环境 pip upgrade，不假设当前 API 名。adapter 负责上述稳定接口与被锁版本映射。load_policy 校验 bundle/依赖/权重哈希，在训练或推理解释器内加载模型并置 eval 模式；infer 在 inference_mode 下完成相同预处理、推理及反归一化，返回物理 rad，不调用任何 ROS API。保存加载 smoke 必须调用真实 load_policy(...).infer(...) 并验证双相机/8维输入到6维动作块，不能只断言权重文件存在。LeRobot 视图仅导出两 RGB、8 维 state、6 维 action 与 episode/frame/task；图像 HWC→CHW、RGB 顺序/resize/归一化一致，统计只拟合 Train。task 文本不是语言输入。冻结 action chunk、执行前缀、是否 temporal ensembling、checkpoint seed 与预处理 hash；首个 smoke config 使用 chunk_size=10、执行前缀=1、temporal ensembling=false，仅作候选配置，变更须经闭环验证及重放门。尾部 chunk 用明确 padding mask，禁止跨 episode 补帧。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test \
  src/so101_demo_py/test/test_act_bundle.py \
  src/so101_demo_py/test/test_act_training_owner.py -q
```

预期非零测试收集、全部通过。先从 campaign index 指向的 commit+receipt 闭环中导出 2 个合格 Train episode，反读 LeRobot schema、像素、timestamp 和 action，完成短训练+保存加载 smoke；再使用全新 run root 正式训练，并用 Validation 选 checkpoint。bundle 保存权重/hash、训练源码/依赖、相机键、q 顺序、统计、split manifest、campaign index 与各 journal/receipt hash、不可变导出、owner/GPU lease 终态、设备和校准配置 hash。测试 tamper hash、错相机/8→7 state、padding、非 Train 统计污染、未收敛 arbiter、并发 GPU owner 和旧 dataset ID 均拒绝。Offline Test 仅配置冻结后运行，不用其 loss 调参。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/bundle.py src/so101_demo_py/src/act/training_owner.py src/so101_demo_py/src/adapters/act/lerobot.py src/so101_demo_py/src/cli/act_train.py src/so101_demo_py/config/act/training.yaml src/so101_demo_py/config/act/requirements.lock src/so101_demo_py/setup.py src/so101_demo_py/test/test_act_bundle.py src/so101_demo_py/test/test_act_training_owner.py
git diff --cached --check
git commit -m "feat: export and train versioned ACT bundles"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 12A: 封存 Offline Test 的只读动作评估入口

**Files:**

- Create: `src/so101_demo_py/src/act/offline_evaluation.py`
- Create: `src/so101_demo_py/src/cli/act_offline_evaluate.py`
- Modify: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/test/test_act_offline_evaluation.py`

**Interfaces:** Consumes: Task 12 `load_policy`、dataset manifest、campaign index、bundle 和冻结清单。Produces: `masked_joint_mae(predicted:list, target:list, valid:list[bool])->list[float]`；`evaluate_offline(manifest_path:Path, bundle_path:Path, freeze_path:Path, output:Path)->dict`；`python -m so101_demo.cli.act_offline_evaluate --manifest PATH --bundle PATH --freeze PATH --output PATH`。此入口仅在训练环境执行，不依赖 ROS，也不驱动控制器。

- [ ] **Step 1: 写入 padding 不计入误差的失败测试。**

```python
from so101_demo.act.offline_evaluation import masked_joint_mae

def test_padding_is_excluded_from_joint_metrics():
    predicted = [[1.,2.,3.,4.,5.,6.], [100.,100.,100.,100.,100.,100.]]
    target = [[0.,0.,0.,0.,0.,0.], [0.,0.,0.,0.,0.,0.]]
    assert masked_joint_mae(predicted, target, [True, False]) == [1.,2.,3.,4.,5.,6.]
```

- [ ] **Step 2: 运行 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_offline_evaluation.py -q
```

预期新增符号缺失或 padded 数据污染误差导致断言失败。

- [ ] **Step 3: 实现只读推理、冻结核验和指标。**

```python
def masked_joint_mae(predicted, target, valid):
    if len(predicted) != len(target) or len(valid) != len(target):
        raise ValueError("MASK_SHAPE_INVALID")
    indices = [i for i, keep in enumerate(valid) if keep]
    if not indices:
        raise ValueError("NO_VALID_TARGETS")
    return [sum(abs(predicted[i][j] - target[i][j]) for i in indices)/len(indices)
            for j in range(6)]
```

逐行补齐六维/finite/bool mask 校验，不能因损坏数据静默减少分母。freeze JSON 固定六个字段：bundle_sha256、dataset_manifest_sha256、campaign_index_sha256、split_manifest_sha256、calibration_sha256、runtime_config_sha256。Task 16 从实际文件计算，配套同目录 freeze-paths.json 给出逐项绝对路径；字段缺失/多余、任一文件丢失或 hash 不符都拒绝评估。评估前逐项读回，并检查 dataset manifest 与 campaign index 互引 hash、至少 10 个成功 Offline Test episode、没有跨 split/episode chunk 或 Train 拟合统计被更新。

调用 load_policy(...).infer(...)，使用训练时同一预处理、action 时间约定和 tail padding mask；每个 episode 开始 reset 模型状态。全部指标用反归一化后的 rad，保存每关节 MAE/RMSE、按预测 horizon 的误差、每 episode 指标、有效目标数和 episode 等权总体均值，避免长 episode 独占总分。输出模型/清单/hash、配置、依赖版本、运行时间和错误；不反向传播、不更新统计、不选 checkpoint。

输出目录必须新建，报告原子写入；失败保存原因，不能把不完整评估标成功。技术故障重跑使用同一冻结 hash、新运行 ID 并保留失败记录；看过结果后改模型不再沿用这批数据的封存资格。

- [ ] **Step 4: 验证 GREEN 和真实模型离线评估。**

```zsh
act_test src/so101_demo_py/test/test_act_offline_evaluation.py -q
"$ACT_TRAIN_PYTHON" -m so101_demo.cli.act_offline_evaluate --help
```

先在专用 synthetic fixture 上测试错误 split、dataset manifest 篡改、campaign index 篡改、两者互引 hash 冲突、全 padding、跨 episode、归一化不变和 metric 数值；模型 smoke 用 Validation 数据的独立测试 fixture，不提前打开 Offline Test。真实 10 个封存 episode 的命令留到 Task 16 冻结之后；本任务以接口和 fixture 验证完成，不声称最终离线指标通过。

- [ ] **Step 5: 显式提交。**

```zsh
git add src/so101_demo_py/src/act/offline_evaluation.py src/so101_demo_py/src/cli/act_offline_evaluate.py src/so101_demo_py/setup.py src/so101_demo_py/test/test_act_offline_evaluation.py
git diff --cached --check
git commit -m "feat: evaluate frozen offline ACT actions"
```

### Task 13: ACT Runner、时间对齐与异步推理隔离

**Files:**

- Create: `src/so101_demo_py/src/act/policy.py`
- Create: `src/so101_demo_py/test/test_act_policy.py`

- Create: `src/so101_demo_py/src/adapters/act/inference_process.py`
- Create: `src/so101_demo_py/src/cli/act_inference_worker.py`
- Create: `src/so101_demo_py/config/act/runtime.yaml`
- Create: `src/so101_demo_py/test/test_act_inference_process.py`

**Interfaces:** Consumes: Task 12 load_policy/bundle 与 `infer(observation:dict)->tuple[tuple[float,...],...]` 模型 port。Produces: `target_times(observed_s:float,count:int)->tuple[float,...]`；`ActPolicyRunner(bundle:dict, infer:object).predict(observation:dict, sequence:int)->dict`（ActionPrefix）；`.reset(session_id:str,attempt_id:str)->None`。

- [ ] **Step 1: 写入边界失败测试。**

```python
import pytest
from so101_demo.act.policy import target_times

def test_chunk_keeps_observation_time_origin():
    assert target_times(5., 3) == pytest.approx((5.1,5.2,5.3))
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_policy.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
def target_times(observed_s, count):
    return tuple(observed_s + .1*(index+1) for index in range(count))
```

Runner 仅接收白名单 Observation，调用 LeRobot adapter 推理，反归一化后校验形状/finite；prefix 保留原 observation 时间，不在推理返回时重锚。temporal ensembling 只合成同一个绝对 target_time；其算法与权重来自已冻结 bundle，不用数组索引猜时间。运行入口从 --runtime-config 读取 inference_python 与 broker socket；eval 组合使用同一配置，拒绝未配置解释器。ROS executor 和 supervisor 看门狗独立于推理 worker；使用有界 IPC 队列，取消/超时使 generation token 失效，迟回预测丢弃。停止立即禁止提交并取消双方；无需等待 torch 调用返回才止动。reset 清理 chunk、ensemble 与模型缓存，不跨 attempt 复用。



- [ ] **Step 3a: 启动独立解释器的真实推理 worker。**

ROS 侧 `InferenceProcess(python_executable:Path, bundle_path:Path, socket_path:Path)` 用 `subprocess.Popen` 的 argv 列表启动：`[str(python_executable), "-m", "so101_demo.cli.act_inference_worker", "--bundle", str(bundle_path), "--socket", str(socket_path)]`。不使用 shell、不用默认 multiprocessing 继承 ROS Python。runtime.yaml 的 `inference_python` 是经过资格验证的绝对路径；不存在或与 bundle 依赖不兼容则拒绝运行。worker 使用 Task 12 的 load_policy，不导入 ROS；ROS 进程不导入 torch/LeRobot。

IPC 使用本机 Unix socket，长度前缀 JSON，单消息上限 4 MiB，两张 640×480 RGB uint8 图按 base64 原始字节传输；审计真值无对应字段。单个 in-flight 请求、最多一个待发送请求，满时返回 INFERENCE_BUSY，不无限排队。精确消息 schema：

| 消息 | 字段 |
| --- | --- |
| READY | kind、protocol_version=1、bundle_sha256、python_executable、requirements_sha256 |
| PREDICT | kind、request_id、generation:int、session_id、attempt_id、sim_time_s、head_rgb_b64、wrist_rgb_b64、state（8维） |
| RESULT | kind、request_id、generation、session_id、attempt_id、sim_time_s、positions（H×6 rad） |
| RESET | kind、generation、session_id、attempt_id |
| ERROR | kind、request_id、generation、code |

客户端接口 `start()->None`、`submit(observation:dict, generation:int)->str`、`poll()->dict|None`、`invalidate(generation:int)->None`、`close()->None`。start 有冻结的启动超时，只在 READY 的协议/hash/解释器匹配后合格；poll 非阻塞。Runner 的同步 predict 仅用于纯逻辑测试，live 组合使用 submit/poll，禁止在 supervisor 线程调用阻塞 infer。停止先本地 invalidate，使所有旧响应失效，再取消控制器；RESET 不要求卡住的 worker 先响应。进程重启与模型重载发生在新 attempt 前，不能重置当前 Deadline。

```python
from so101_demo.adapters.act.inference_process import response_matches

def test_late_worker_response_is_discarded():
    response = {"request_id":"r1", "generation":3, "session_id":"s", "attempt_id":"a"}
    assert not response_matches(response, "r1", 4, "s", "a")

```

核心匹配函数写入 inference_process.py：

```python
def response_matches(response, request_id, generation, session_id, attempt_id):
    return (response["request_id"], response["generation"], response["session_id"], response["attempt_id"]) == (request_id, generation, session_id, attempt_id)
```

测试文件只导入生产函数，不在测试里重新定义。解码另测畸形 JSON、超长包、错误 RGB 字节数、旧 session、worker 退出、队列满。真实进程 smoke 使用 Task 12 的 checkpoint，ROS 环境中 `find_spec("lerobot")` 为 None，worker 环境可加载模型，实际获得 H×6 响应；分别记录两边 sys.executable。再让测试 worker 阻塞结果发送，注入单调时钟推进到 120 s，断言 session 报 ACT_TIMEOUT、双方 controller 停止，不等待 worker 返回；另做真实墙钟 watchdog 验证。

```zsh
act_test src/so101_demo_py/test/test_act_inference_process.py -q
"$ACT_TRAIN_PYTHON" -m so101_demo.cli.act_inference_worker --help
```

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_policy.py -q
```

预期非零测试收集、全部通过。fake infer 故意阻塞、返回 NaN、错误 q 顺序、在 reset 后返回，测试无动作提交且 Deadline 仍推进；队列满不能无限积压。模型 smoke 与实时推理读回分别记录 p50/p95/p99 和 missed deadline，超过动作时间预算视为当前部署配置不合格。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/policy.py src/so101_demo_py/test/test_act_policy.py
git add src/so101_demo_py/src/adapters/act/inference_process.py src/so101_demo_py/src/cli/act_inference_worker.py src/so101_demo_py/config/act/runtime.yaml src/so101_demo_py/test/test_act_inference_process.py
git diff --cached --check
git commit -m "feat: run timestamped ACT inference"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 14: 搜索到 ACT 的运行组合与命令所有权

**Files:**

- Create: `src/so101_demo_py/src/act/session.py`
- Create: `src/so101_demo_py/src/runtime/act_composition.py`
- Create: `src/so101_demo_py/src/cli/act_session.py`
- Modify: `src/so101_demo_py/launch/so101_mujoco_act.launch.py`
- Modify: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/test/test_act_session.py`

**Interfaces:** Consumes: Task 3–13，尤其 Task 7A 的统一 admission/typed `WorkerPort` 和 Task 13 的非阻塞推理客户端。Produces: `retry_allowed(...)`；`ActSession(context:AdmittedCampaignContext, worker_port:WorkerPort).command(...)`；`.tick()`；CLI `act_session --mode dry_run|plan_only|execute --bundle PATH --calibration PATH --policy PATH --activation-receipt PATH --runtime-config PATH --evidence-root PATH`。CLI 仍只向 `UnifiedWorkloadService` 提交 spec。

- [ ] **Step 1: 写入边界失败测试。**

```python
from so101_demo.act.session import retry_allowed

def test_no_retry_with_unknown_or_held_cup():
    assert not retry_allowed(0, "UNKNOWN", True)
    assert not retry_allowed(0, "HOLDING", True)
    assert retry_allowed(0, "EMPTY", True)
    assert not retry_allowed(1, "EMPTY", True)
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_session.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
def retry_allowed(attempt_index, holding, feedback_ok):
    return attempt_index == 0 and holding == "EMPTY" and feedback_ok
```

组合所有 port，在进入 ACT 首次推理前建立 Deadline。搜索只拥有 neck，Runner 没有 neck port；arm/gripper 命令全部经 context 绑定的 typed `WorkerPort` 发送，Task 14 不取得第二份 lease、不读取 resource binding，也不建立进程内仲裁。admission 时若已有互斥 workload 或未知活跃 goal，统一服务拒绝交接。dry_run 无控制副作用，plan_only 只检查候选；execute 需要有效校准、已激活 policy、bundle 和 MuJoCo profile。命令白名单 Reset/Search/StartRecording/RunExpert/Keep/Discard/RunACT/Stop；RunExpert 与 RunACT 互斥。Stop 能由独立 callback 抢占。恢复只在 EMPTY+正常反馈+验证路径时交给 MoveIt，单独计干预；自动重搜最多 1 次。ACTIVE→timeout/error 后保留首次 RunResult，不用重试覆盖。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_session.py -q
```

预期非零测试收集、全部通过。全状态 fake ports 测试无控制权、neck 漂移、全部失败终态、120 s、重搜预算、Stop 优先和 reset 旧 token；live 首先 dry_run，再 plan_only，再小前缀仿真 execute。检查原 V5 launch 与 task_camera 行为无回归。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/session.py src/so101_demo_py/src/runtime/act_composition.py src/so101_demo_py/src/cli/act_session.py src/so101_demo_py/launch/so101_mujoco_act.launch.py src/so101_demo_py/setup.py src/so101_demo_py/test/test_act_session.py
git diff --cached --check
git commit -m "feat: compose ACT session ownership and recovery"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 15: Teleop ACT 操作面板与后台网关

**Files:**

- Create: `src/so101_teleop/so101_teleop/act_gateway.py`
- Modify: `src/so101_teleop/so101_teleop/api.py`
- Modify: `src/so101_teleop/so101_teleop/server.py`
- Modify: `src/so101_teleop/so101_teleop/openapi.json`
- Modify: `src/so101_teleop/web/src/api/schema.d.ts`
- Create: `src/so101_teleop/web/src/components/teleop/act-panel.tsx`
- Modify: `src/so101_teleop/web/src/task-app.tsx`
- Create: `src/so101_teleop/test/teleop/test_act_gateway.py`
- Create: `src/so101_teleop/web/src/components/teleop/act-panel.test.tsx`

**Interfaces:** Consumes: Task 7A `UnifiedWorkloadService`、Task 14 session spec。Produces: `ActGateway(service:object).command(name:str,payload:dict)->dict`；HTTP ACT command/status 接口；React ActPanel 展示状态、双相机、剩余时间与操作结果。Web 和 headless CLI 构造同一 `OperationSpec`，都由统一服务创建/恢复 `ActSession`。

- [ ] **Step 1: 写入边界失败测试。**

```python
import pytest
from so101_teleop.act_gateway import ActGateway

def test_gateway_rejects_arbitrary_command():
    with pytest.raises(ValueError):
        ActGateway(service=None).command("shell", {"command":"echo bad"})
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_teleop/test/teleop/test_act_gateway.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
class ActGateway:
    def __init__(self, service):
        self.service = service

    def command(self, name, payload):
        allowed = {"Reset","Search","StartRecording","RunExpert","Keep","Discard","RunACT","Stop"}
        if name not in allowed:
            raise ValueError("COMMAND_INVALID")
        return self.service.dispatch_act_command(name, payload)
```

沿现有 backend/profile 与 API 错误风格增加 ACT 能力，仅 ACT profile 显示面板。`dispatch_act_command` 对 Start/Resume 走与 CLI 相同的 `start(spec)`，其余命令路由到已登记 context/WorkerPort；服务端校验状态，不能仅禁用前端按钮。界面提供 Reset、Search、Start Recording、Run Expert、Keep/Discard、Run ACT、Stop；Keep 必须 QC PASS，Discard 不删除原始证据。浏览器刷新不会启动第二个 session，重复 command_id 幂等；关闭页面不杀监督看门狗。倒计时读取服务端剩余秒数，不用浏览器计时作为超时事实源；不显示训练内部字段充当普通用户操作。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_teleop/test/teleop/test_act_gateway.py -q
```

预期非零测试收集、全部通过。后端定向命令 `act_test src/so101_teleop/test/teleop/test_act_gateway.py -q`；其后整包 gate。前端先 `command -v bun`、`bun --version`，在 web 下 `bun run test -- src/components/teleop/act-panel.test.tsx`、`bun run generate:api`、`bun run build`。UI 测试验证操作→请求、运行中互斥、Stop 可用、QC 不通过不能 Keep；使用 gui-capture 的 snapshot→action→fresh snapshot 完成实际录制按钮验收。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_teleop/so101_teleop/act_gateway.py src/so101_teleop/so101_teleop/api.py src/so101_teleop/so101_teleop/server.py src/so101_teleop/so101_teleop/openapi.json src/so101_teleop/web/src/api/schema.d.ts src/so101_teleop/web/src/components/teleop/act-panel.tsx src/so101_teleop/web/src/task-app.tsx src/so101_teleop/test/teleop/test_act_gateway.py src/so101_teleop/web/src/components/teleop/act-panel.test.tsx
git diff --cached --check
git commit -m "feat: expose ACT controls in teleop"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

### Task 16: 封存测试、路线比较与操作指南

**Files:**

- Create: `src/so101_demo_py/src/act/evaluation.py`
- Create: `src/so101_demo_py/src/cli/act_evaluate.py`
- Modify: `src/so101_demo_py/setup.py`
- Create: `src/so101_demo_py/test/test_act_evaluation.py`
- Create: `docs/guides/so101-act-head-wrist-rgb.md`

**Interfaces:** Consumes: 冻结 checkpoint/config/manifest、Task 12A 离线评估入口与 RunResult。Produces: `summarize(results:list[dict])->dict`；CLI `act_evaluate --manifest PATH --split rollout_validation|rollout_test|comparison --bundle PATH --calibration PATH --runtime-config PATH --root PATH --route act|moveit`，输出 JSON/Markdown 报告及逐场景证据索引。

- [ ] **Step 1: 写入边界失败测试。**

```python
from so101_demo.act.evaluation import summarize

def test_search_failure_remains_in_denominator():
    runs = [{"search_locked":False,"done":False,"interventions":0,"elapsed_wall_s":1.},
            {"search_locked":True,"done":True,"interventions":0,"elapsed_wall_s":119.}]
    report = summarize(runs)
    assert report["end_to_end"] == .5
    assert report["locked_denominator"] == 1
    assert report["locked_success"] == 1.
```

- [ ] **Step 2: 验证 RED。**

```zsh
act_test src/so101_demo_py/test/test_act_evaluation.py -q
```

预期新符号缺失或新增边界断言失败；保存退出码和日志。环境初始化失败先修复，不计 RED。

- [ ] **Step 3: 实现核心逻辑与适配。**

```python
def summarize(results):
    locked = [r for r in results if r["search_locked"]]
    def success(r):
        return r["done"] and r["interventions"] == 0 and r["elapsed_wall_s"] < 120.
    return {"end_to_end": sum(success(r) for r in results)/len(results) if results else None,
            "locked_denominator":len(locked),
            "locked_success":sum(success(r) for r in locked)/len(locked) if locked else None}
```

先在 Rollout Validation 反复选择 checkpoint/前缀/监督阈值，每次记录结果而非挑最好一轮；参数改变重跑对应控制/校准门。最终冻结全部 hash，按 Task 12A 入口完成 Offline Test 动作误差评估并读取有效 episode/目标数及各关节指标；Rollout Test 至少 10 个初始条件、首次无干预≥70%，包含 ACT 撤离。路线比较至少 20 个共享场景，每次恢复同一初始物理状态，分布内与空间留出分别报；MoveIt 轨迹封存，不回流训练。报告搜索耗时/成功率/居中误差/方位误差、ACT 条件与端到端分母、timeout/失败分布、干预重搜、推理延迟与物理结果。结果无效与有效失败分开，不能把策略碰撞或超时排为环境问题。

- [ ] **Step 4: 验证 GREEN 与失败矩阵。**

```zsh
act_test src/so101_demo_py/test/test_act_evaluation.py -q
```

预期非零测试收集、全部通过。两个平台分别运行新增 RGB、neck/reset、录制重放及闭环；保留独立物理 pose/contact、controller、Planning Scene shadow（若维护）与新截图。按 so101-dev 附加要求另做固定 checkpoint/config/lifecycle 的连续 5 次有效仿真运行，不能替代封存测试或混算生命周期。指南覆盖安装/校准→录制→训练→验证→测试命令及证据解读，使用 humanizer-zh，不写已掌握。完成报告列 retained/archived/deletion candidates，未授权不删除。

- [ ] **Step 5: 审查本任务 diff 并提交。**

```zsh
git add src/so101_demo_py/src/act/evaluation.py src/so101_demo_py/src/cli/act_evaluate.py src/so101_demo_py/setup.py src/so101_demo_py/test/test_act_evaluation.py docs/guides/so101-act-head-wrist-rgb.md
git diff --cached --check
git commit -m "feat: evaluate frozen ACT runs and document workflow"
```

提交前确认暂存区没有用户已有改动；只在相关自动检查和本任务必需运行门通过后勾选，校准/训练长任务的结果另写账本。

## 运行命令与证据交付

下面命令在相应 Task 实现后才可运行，不是当前已经存在的功能。CLI 输出必须是原子写入的报告文件，异常返回非零退出码；所有入口提供 `--help`。单个长命令启动后由已登记的终端/tmux 持有，读取进度与结果作为下一步，不重复启动第二份。

- [ ] 完成 Task 11A 或 Task 12 的代码后，先运行定向测试，再分别运行受影响模块的完整普通 pytest-xdist 门。ai-station 上每次运行都在登记 evidence root 下创建此前不存在的 NVMe scratch，并在启动 pytest 前核验 `TMPDIR`、`TMP`、`TEMP` 与精确 Python/pytest/xdist 来源。保留 JUnit、stdout/stderr、采集/跳过数、scratch 路径、elapsed 和真实退出码；scratch 反读后只列为 deletion candidate，不自行删除。benchmark 不进入普通门。

```zsh
test -x "$ACT_PYTHON"
logical_cpus=$("$ACT_PYTHON" -c 'import os; print(os.cpu_count() or 1)') || exit 1
test "$logical_cpus" -ge 1 || exit 1
pytest_workers=$(( logical_cpus > 8 ? 8 : logical_cpus ))
print -r -- "logical_cpus=$logical_cpus pytest_workers=$pytest_workers"
mkdir -p "$ACT_EVIDENCE/scratch"

demo_gate=$(mktemp -d "$ACT_EVIDENCE/scratch/pytest-demo.XXXXXXXX") || exit 1
mkdir "$demo_gate/tmp" || exit 1
export TMPDIR="$demo_gate/tmp" TMP="$demo_gate/tmp" TEMP="$demo_gate/tmp"
"$ACT_PYTHON" -c 'import os,pathlib,sys,tempfile,pytest,xdist; actual=pathlib.Path(tempfile.gettempdir()).resolve(); expected=pathlib.Path(os.environ["TMPDIR"]).resolve(); print(sys.executable,pytest.__version__,pytest.__file__,xdist.__version__,xdist.__file__,actual); assert actual == expected' > "$demo_gate/tempfile-proof.log" 2>&1 || exit 1
{ /usr/bin/time -p "$ACT_PYTHON" -m pytest src/so101_demo_py/test -n "$pytest_workers" --junitxml="$demo_gate/junit.xml"; } > "$demo_gate/pytest.log" 2>&1
demo_test_rc=$?
print -r -- "$demo_test_rc" > "$demo_gate/exit-code.txt"

teleop_gate=$(mktemp -d "$ACT_EVIDENCE/scratch/pytest-teleop.XXXXXXXX") || exit 1
mkdir "$teleop_gate/tmp" || exit 1
export TMPDIR="$teleop_gate/tmp" TMP="$teleop_gate/tmp" TEMP="$teleop_gate/tmp"
"$ACT_PYTHON" -c 'import os,pathlib,sys,tempfile,pytest,xdist; actual=pathlib.Path(tempfile.gettempdir()).resolve(); expected=pathlib.Path(os.environ["TMPDIR"]).resolve(); print(sys.executable,pytest.__version__,pytest.__file__,xdist.__version__,xdist.__file__,actual); assert actual == expected' > "$teleop_gate/tempfile-proof.log" 2>&1 || exit 1
{ /usr/bin/time -p "$ACT_PYTHON" -m pytest src/so101_teleop/test -n "$pytest_workers" --junitxml="$teleop_gate/junit.xml"; } > "$teleop_gate/pytest.log" 2>&1
teleop_test_rc=$?
print -r -- "$teleop_test_rc" > "$teleop_gate/exit-code.txt"
if (( demo_test_rc != 0 || teleop_test_rc != 0 )); then
  print -u2 -r -- "xdist gate failed: demo=$demo_test_rc teleop=$teleop_test_rc"
  exit 1
fi
```

定向测试通过只能支持对应边界，不能替代完整 xdist 门。共享 socket、ROS Domain、全局文件或 GPU 造成并发失败时修复 worker/run 隔离，再以相同 worker 数重跑完整模块；不能删除测试、缩小范围或降 worker 数。随后按包运行必要的 colcon/CTest gate 并核验实际 pytest argv。`tools/so101_pytest_gate.py --workers 8` 可另跑以保存确定性分片、串行安全 lane、exact coverage 与 provenance，但它不是 xdist，不替代上述门。

- [ ] 构建与确认新入口；source 顺序按 dependency-lock，读取 package prefix 与可执行文件路径写入账本。

```zsh
test -d "$ACT_BUILD_BASE" && test -d "$ACT_LOG_BASE" && test -f "$ACT_INSTALL_OVERLAY/setup.zsh"
colcon --log-base "$ACT_LOG_BASE" build \
  --build-base "$ACT_BUILD_BASE" \
  --install-base "$ACT_INSTALL_OVERLAY" \
  --packages-select so101_demo_py --symlink-install
source "$ACT_INSTALL_OVERLAY/setup.zsh"
ros2 pkg prefix so101_demo_py
ACT_PACKAGE_SHARE="$(ros2 pkg prefix so101_demo_py)/share/so101_demo_py"
test -d "$ACT_PACKAGE_SHARE/config/act"
ACT_COLLECTION_CONFIG="$ACT_PACKAGE_SHARE/config/act/parallel_collection_v3.yaml"
ACT_PARALLEL_RUNTIME="$ACT_PACKAGE_SHARE/config/mujoco/parallel_batch_v3.yaml"
test -f "$ACT_COLLECTION_CONFIG" && test -f "$ACT_PARALLEL_RUNTIME"
export ACT_PACKAGE_SHARE ACT_COLLECTION_CONFIG ACT_PARALLEL_RUNTIME
ros2 pkg executables so101_demo_py
ros2 launch so101_demo_py so101_mujoco_act.launch.py --show-args
ros2 run so101_demo_py act_build_task8_source_provenance --help
ros2 run so101_demo_py act_measure_task8_calibration --help
ros2 run so101_demo_py act_build_task8_calibration_report --help
ros2 run so101_demo_py act_prepare_task8_live_artifacts --help
ros2 run so101_demo_py act_validate_task8_artifacts --help
ros2 run so101_demo_py act_task8_live --help
ros2 run so101_demo_py act_build_task8_qualified_report --help
ros2 run so101_demo_py act_session --help
```

- [ ] 按 Task 8L Steps 1–5 运行接触策略核对、当前 identity 测量、确定性聚合、bundle preparation 和 Task 8 live。`act_preflight` 不再凭空生成 `TASK8_READY`；状态只能由 `act_build_task8_calibration_report` 根据关闭的 measurement batch 计算。若仍为 `CALIBRATION_REQUIRED`、policy fingerprint 未激活或 bundle 没有有效 receipt，只保留 evidence 并停止。

```zsh
ros2 run so101_demo_py act_collect_contact_calibration --mode offline --output "$ACT_EVIDENCE/contact/offline"
ros2 run so101_demo_py act_collect_contact_calibration --mode live --output "$ACT_EVIDENCE/contact/live"
ros2 run so101_demo_py act_analyze_contact_calibration --offline "$ACT_EVIDENCE/contact/offline/manifest.json" --live "$ACT_EVIDENCE/contact/live/manifest.json" --proposal "$ACT_EVIDENCE/contact/proposal.json"
# 独立审阅 proposal 后，由用户提供并批准精确 POLICY_FINGERPRINT；不得使用 proposal envelope hash。
ros2 run so101_demo_py act_activate_contact_policy --proposal "$ACT_EVIDENCE/contact/proposal.json" --policy-fingerprint "$POLICY_FINGERPRINT" --approved-by "$ACT_POLICY_APPROVER" --approval-reference "$ACT_POLICY_APPROVAL_REFERENCE" --evidence-root "$ACT_EVIDENCE/contact" --receipt "$ACT_EVIDENCE/contact/activation-receipt.json"
# 之后完整执行 Task 8L 的 act_measure_task8_calibration、
# act_build_task8_calibration_report、act_prepare_task8_live_artifacts 与 act_task8_live 命令。
ros2 run so101_demo_py act_sample --calibration "$ACT_QUALIFIED_CALIBRATION" --output "$ACT_EVIDENCE/splits.json" --collection-output "$ACT_EVIDENCE/collection.json" --qualification-output "$ACT_EVIDENCE/parallel-qualification.json" --qualification-load-output "$ACT_EVIDENCE/parallel-load.json" --seed 20260911
```

`act_prepare_task8_live` 的旧单 manifest 入口只保留显式兼容拒绝或迁移提示，不能生成 production 可启动状态。`act_task8_live` 一次调用按 committed bundle 内 manifest 冻结的九个 `stop_after` 与随后五个 default/left/forward FULL_RESTART 执行全部 14 个 case；CLI 自己不直连 ROS，所有 case 都通过 unified service。prefix 结果不生成正式 episode；第二次调用不能补齐或拼接本轮资格。

- [ ] 先用 W1 单条入口运行 5 条小批，读取 QC 和重放证据。`act_collect` 的 limit 是总尝试上限，不是成功数量；这个 smoke 使用独立 root，不并入正式数据集。

```zsh
ros2 run so101_demo_py act_collect --manifest "$ACT_EVIDENCE/parallel-qualification.json" --calibration "$ACT_QUALIFIED_CALIBRATION" --policy "$ACT_EVIDENCE/contact/proposal.json" --activation-receipt "$ACT_EVIDENCE/contact/activation-receipt.json" --root "$ACT_EVIDENCE/s" --limit 5 --qualification
```

- [ ] 在独立资格清单上运行完整八场景的单 stack 基线、W1 并行入口和 W2；结果分别写入不同 root。三次均必须使用相同 manifest/calibration/config hash，且这些 episode 不并入正式数据集。

```zsh
ros2 run so101_demo_py act_collect --manifest "$ACT_EVIDENCE/parallel-qualification.json" --calibration "$ACT_QUALIFIED_CALIBRATION" --policy "$ACT_EVIDENCE/contact/proposal.json" --activation-receipt "$ACT_EVIDENCE/contact/activation-receipt.json" --root "$ACT_EVIDENCE/u" --limit 8 --qualification
ros2 run so101_demo_py act_collect_parallel --manifest "$ACT_EVIDENCE/parallel-qualification.json" --calibration "$ACT_QUALIFIED_CALIBRATION" --policy "$ACT_EVIDENCE/contact/proposal.json" --activation-receipt "$ACT_EVIDENCE/contact/activation-receipt.json" --collection-config "$ACT_COLLECTION_CONFIG" --runtime-config "$ACT_PARALLEL_RUNTIME" --root "$ACT_EVIDENCE/q1" --qualification --worker-count 1
ros2 run so101_demo_py act_collect_parallel --manifest "$ACT_EVIDENCE/parallel-qualification.json" --calibration "$ACT_QUALIFIED_CALIBRATION" --policy "$ACT_EVIDENCE/contact/proposal.json" --activation-receipt "$ACT_EVIDENCE/contact/activation-receipt.json" --collection-config "$ACT_COLLECTION_CONFIG" --runtime-config "$ACT_PARALLEL_RUNTIME" --root "$ACT_EVIDENCE/q2" --qualification --worker-count 2
```

`u` 是完整八场景单 stack 基线；`s` 只尽早检查 5 条记录内容和重放。W1 并行与 W2 都和 `u` 比较，不能用 smoke 作性能分母。每条命令由统一服务在 admission 时取得新的 GPU lease 与 `validation` reservation，并返回不可变 context；CLI 不手写 binding，内部组件不重复查询 authority。

W2 通过后直接在独立 40 场景清单上运行一次 exact-W8 资格；不运行中间档位，也不做隐式第二轮。所有入口先打印最长 socket 路径与字节数，超过 107 bytes 时不启动子进程。`q8/qualification-contract.json` 在启动前写入并冻结；W8 失败时停止等待人工决策。通过后用短目录 `d` 执行正式 exact-W8 采集：

```zsh
ros2 run so101_demo_py act_collect_parallel --manifest "$ACT_EVIDENCE/parallel-load.json" --calibration "$ACT_QUALIFIED_CALIBRATION" --policy "$ACT_EVIDENCE/contact/proposal.json" --activation-receipt "$ACT_EVIDENCE/contact/activation-receipt.json" --collection-config "$ACT_COLLECTION_CONFIG" --runtime-config "$ACT_PARALLEL_RUNTIME" --qualification-contract "$ACT_EVIDENCE/q8/qualification-contract.json" --root "$ACT_EVIDENCE/q8" --qualification --worker-count 8
ros2 run so101_demo_py act_collect_parallel --manifest "$ACT_EVIDENCE/collection.json" --split-manifest "$ACT_EVIDENCE/splits.json" --calibration "$ACT_QUALIFIED_CALIBRATION" --policy "$ACT_EVIDENCE/contact/proposal.json" --activation-receipt "$ACT_EVIDENCE/contact/activation-receipt.json" --collection-config "$ACT_COLLECTION_CONFIG" --runtime-config "$ACT_PARALLEL_RUNTIME" --root "$ACT_EVIDENCE/d" --worker-count 8
```

正式采集预算从分层有效率估算后写入冻结清单；不捏造可达区域或假定候选一次成功。配额不满返回 `QUOTA_UNSATISFIED`，不能复制 episode 或重跑业务失败补齐。`d/campaign-index.json` 按冻结顺序记录 QC、split、batch/Worker generation、Coordinator commit、infra attempts、surplus 与未调度原因；`d/manifest.json` 只列最终选中的正式 episode，并绑定前者 hash。不导出 Rollout Validation/Test 示教。命令行固定 8，不能临时降档。

- [ ] 使用独立训练 venv 执行离线入口，记录 `sys.executable` 与完整依赖锁。`ACT_TRAIN_PYTHON` 必须解析为该 venv 的实际 Python，先验证 LeRobot/torch 来源；不能沿用 ROS Python 安装训练依赖。

Task 12 先读取 `so101-dev/references/python-dependency-install.md`，按其中的索引规则创建 Python 3.12 训练环境；LeRobot 若声明不支持该版本，应先更新本计划的环境约定，不向 ROS 环境安装。执行阶段的环境创建与锁定命令为：

```zsh
uv venv --python 3.12 "$ACT_EVIDENCE/train-venv"
export ACT_TRAIN_PYTHON="$ACT_EVIDENCE/train-venv/bin/python"
uv pip install --python "$ACT_TRAIN_PYTHON" lerobot
uv pip freeze --python "$ACT_TRAIN_PYTHON" > "$ACT_EVIDENCE/training-resolved.txt"
uv pip install --python "$ACT_TRAIN_PYTHON" --no-deps -e src/so101_demo_py
```

首次安装用于资格检查，Task 12 在训练前把验证通过的精确依赖写入 `config/act/requirements.lock`；随后用该锁重建第二个干净训练环境并重复 smoke，证明可复现。未通过安装/版本资格不得启动正式训练。训练代码不得 import ROS。
```zsh
"$ACT_TRAIN_PYTHON" -c 'import sys,torch,lerobot; print(sys.executable); print(torch.__file__); print(lerobot.__file__)'
"$ACT_TRAIN_PYTHON" -m so101_demo.cli.act_train --manifest "$ACT_EVIDENCE/d/manifest.json" --campaign-index "$ACT_EVIDENCE/d/campaign-index.json" --gpu-binding "$ACT_EVIDENCE/train-gpu-binding.json" --config src/so101_demo_py/config/act/training.yaml --output "$ACT_EVIDENCE/training/run-001" --device cuda:0
export ACT_BUNDLE="$ACT_EVIDENCE/training/run-001/models/bundle.json"
test -f "$ACT_BUNDLE"
```

运行训练命令前必须保存统一 arbiter `IDLE` readback、最新 cleanup proof，以及所选 GPU 的 authority/进程清单，并请求统一服务原子领取训练 lease、写出本次 `train-gpu-binding.json`。CLI 必须在线核验并续租；无法取得或 binding 与 `--device` 不一致时不创建训练进程。Task 12 的 CLI 支持 `python -m`，在本次独立 run root 输出 `models/bundle.json`，引用真实 checkpoint 及其 SHA，不用可变的 latest 链接代替封存工件；失败 run 保持原样，下一次使用新的 run ID。`ACT_BUNDLE` 只从这个完成 run 的 receipt/确定路径冻结，后续所有评估使用同一绝对文件，不扫描或猜测 `latest`。

- [ ] 冻结模型前运行闭环验证。`act_evaluate` 使用必需参数 `--split rollout_validation|rollout_test|comparison`，缺省拒绝运行，避免误触封存测试。

```zsh
ros2 run so101_demo_py act_evaluate --manifest "$ACT_EVIDENCE/splits.json" --split rollout_validation --bundle "$ACT_BUNDLE" --calibration "$ACT_QUALIFIED_CALIBRATION" --runtime-config src/so101_demo_py/config/act/runtime.yaml --root "$ACT_EVIDENCE/validation" --route act
```

- [ ] 保存封存清单，并实际调用 Task 12A 的离线评估入口。Task 16 的启动核验需确认这些文件是同一已冻结配置，不重新训练或更新归一化统计。

```zsh
"$ACT_PYTHON" - <<'PY_FREEZE'
import hashlib, json, os
from pathlib import Path
root = Path(os.environ["ACT_EVIDENCE"])
artifacts = {
    "bundle_sha256": Path(os.environ["ACT_BUNDLE"]),
    "dataset_manifest_sha256": root / "d/manifest.json",
    "campaign_index_sha256": root / "d/campaign-index.json",
    "split_manifest_sha256": root / "splits.json",
    "calibration_sha256": root / "calibration-qualified.json",
    "runtime_config_sha256": Path("src/so101_demo_py/config/act/runtime.yaml"),
}
freeze = {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in artifacts.items()}
with (root / "freeze-paths.json").open("x") as stream:
    json.dump({key: str(path.resolve()) for key, path in artifacts.items()}, stream, indent=2)
with (root / "freeze.json").open("x") as stream:
    json.dump(freeze, stream, indent=2)
PY_FREEZE
"$ACT_TRAIN_PYTHON" -m so101_demo.cli.act_offline_evaluate --manifest "$ACT_EVIDENCE/d/manifest.json" --bundle "$ACT_BUNDLE" --freeze "$ACT_EVIDENCE/freeze.json" --output "$ACT_EVIDENCE/offline-test"
```

freeze 文件采用上述六个 hash 字段，另由同目录的 freeze-paths.json 记录六项实际文件路径；生成 freeze 时一并保存，evaluate_offline 据此逐项读取并校验。dataset manifest 与 campaign index 任一篡改或互引 hash 不一致都拒绝。不得为记录训练后的 runtime 配置回写原始 dataset manifest。模型内部的 checkpoint 与预处理 hash 由 load_bundle 继续递归核验。输出报告必须显示至少 10 个 Offline Test episode 和有效 mask 计数，缺失报告则 Task 16 不完成。

- [ ] 冻结 checkpoint、执行参数、场景清单与校准报告后运行封存测试及两路线比较。每次 invocation 创建独立子目录；报告保留每场景的首次结果。测试失败后调参必须更换新的封存批次。

```zsh
ros2 run so101_demo_py act_evaluate --manifest "$ACT_EVIDENCE/splits.json" --split rollout_test --bundle "$ACT_BUNDLE" --calibration "$ACT_QUALIFIED_CALIBRATION" --runtime-config src/so101_demo_py/config/act/runtime.yaml --root "$ACT_EVIDENCE/test" --route act
ros2 run so101_demo_py act_evaluate --manifest "$ACT_EVIDENCE/splits.json" --split comparison --bundle "$ACT_BUNDLE" --calibration "$ACT_QUALIFIED_CALIBRATION" --runtime-config src/so101_demo_py/config/act/runtime.yaml --root "$ACT_EVIDENCE/comparison-act" --route act
ros2 run so101_demo_py act_evaluate --manifest "$ACT_EVIDENCE/splits.json" --split comparison --bundle "$ACT_BUNDLE" --calibration "$ACT_QUALIFIED_CALIBRATION" --runtime-config src/so101_demo_py/config/act/runtime.yaml --root "$ACT_EVIDENCE/comparison-moveit" --route moveit
```

## 执行中必须解决的测量门槛

这些是实验输出，不是可用任意默认值替代的实现空缺。每项均有负责 Task、测量办法与拒绝条件。

| 工件 | 负责 Task | 测量/冻结办法 | 不通过时 |
| --- | --- | --- | --- |
| 相机安装与视野 | 3、6 | 全阶段专家轨迹、新双视角图像、标定投影误差、碰撞几何 | 调整安装后重做预检，不采数据 |
| 轻量检测器与阈值 | 5、6 | head 视角含无杯/多杯/遮挡的独立校准图；冻结模型来源、hash 与误差报告 | 无合格候选则停在搜索资格，不绕到真值检测 |
| controller 定时能力 | 7 | 10 Hz 重放的 reference/joint 对齐、部分接受取消与停止速度测量 | 不放宽标签时间语义、不平移迟到目标 |
| 接触策略 fingerprint | 6A | 五类各 20 offline+5 live、三类 negative control；独立审阅 disabled proposal；用户批准 canonical payload SHA256 | 未激活精确 fingerprint，不启动 Task 8 live |
| Task 8 准入与资格工件 | 8P1–8P4 | role-based source provenance；CUDA-only runtime/collection config；关闭的 MuJoCo measurement batch；确定性 aggregator；自包含 bundle 与原子 receipt；fixture read-denial 自包含测试；完整 live journals 生成 `QUALIFIED` | 任一 identity/hash/依赖/fsync/journal/retirement 边界不闭合时零进程启动或零资格输出，不手写 `TASK8_READY`/`QUALIFIED` |
| 持物/释放/路径检查 | 8、8L | 单次 canonical campaign 的九个 phase-prefix 与 default/left/forward 上五次连续 FULL_RESTART；新鲜双侧接触/离台/支撑证据、非法路径及悬空开爪注入 | 无有效 permit、14-case 闭包或五连 full，不进入采集 |
| LeRobot 版本、训练所有权和 GPU/CPU 能力 | 11A、12、13 | 执行时锁版本；campaign index 逐 wave 回放 commit+receipt；arbiter `IDLE`、cleanup 与 GPU inventory；采集/Broker/训练共用持久 GPU lease；单写者训练 run；导出/训练/推理 smoke 与真实延迟分位数 | 输入 provenance、环境复现、持久所有权或资源串行任一不合格就不训练；推理未合格则不报部署通过 |
| 数据空间隔离与规模 | 10、11、11A | 实际 XY 距离、冻结候选预算、分层配额、全轨迹预检和物理结果 | 报 QUOTA_UNSATISFIED，不复用封存位置或重跑业务失败 |
| ACT W8 采集资格 | 11A | 8 场景完整 W1/W2；随后一份独立 40 场景、两个 20 项 wave 的 exact W8；冻结 `qualification-contract.json`，每 wave 每 Worker 至少 2 个 terminal，记录 CPU/RSS/GPU/磁盘、RTF、Recorder queue、帧间隔、吞吐、QC 与物理成功率 | W2 未过不启动 W8；W8 任一门失败立即停下等待人工决策，不自动降档 |

## 自审：设计覆盖与一致性

| 设计章节 | 负责 Task | 检查结论 |
| --- | --- | --- |
| 1–3 目标、分工、输入边界 | 1、12–14 | 双 RGB/8→6、独立搜索与混合监督，原主线保留 |
| 4 模型与视野 | 2、3、6、8P2 | RGB-only、neck、名称映射、两平台、完整 phase 路径 FOV 和原 RGB-D 回归 |
| 5 搜索和方位 | 5、6、14 | 360°预算、身份一致、几何方位、过期失效与控制权 |
| 6 观测/action | 1、4、7、13 | 因果采样、前缀时间、双控制器、异步取消 |
| 7 示教 | 9、11、11A | t 时刻双 RGB+8D，t+0.1 实际 reference、合法 release epoch、PASSED/FAILED 封存、commit 后确定性汇总 |
| 8 随机区域 | 3、6、10 | 每实际点预检、分层拒绝统计与初始关节扰动 |
| 9 数据/泛化 | 10–12、12A、16 | 五集合隔离、冻结候选、资格数据排除、闭环调参、70%与20场景比较 |
| 10 安全/恢复 | 3、7、7A、8、8P3、13、14 | 120 s 墙钟、typed child、路径碰撞、支撑开爪、新 release epoch、原子 bundle、最多1次重搜 |
| 11 组件/Teleop | 2、3、7A、11A、12、14、15 | 子模块锁、unified admission、每 Worker ROS child、v3 fixed queue、训练单写者与界面同路径 |
| 12 校准顺序 | 6–8P4、9–11A、8L、12–13 | 全部 source-changing 代码提交/安装→contact fingerprint 激活→当前 identity 测量/聚合→committed bundle→单次 14-case Task 8 live→`QUALIFIED`→W1/W2→独立 W8→正式采集→commit+receipt 导出→训练 |
| 13 验收证据 | 11A、16及全局 gate | 并发正确性与吞吐分开、各层结果独立、两平台、原始证据与删除约束 |
| 14 本地依据 | 基线、Files 与 v3 runtime/统一仲裁实现 | 已查合入实现和限制，新路径均标 Create |

执行前还需将所选工作树与本计划基线比对；文件有改名时先更新计划路径再实现。每个任务的代码片段只规定核心边界，完整交付必须通过该任务失败矩阵与运行门，不能把 smoke test 通过当作整任务完成。

本次交付仅为实施计划，所有 checkbox 保持未勾选；没有运行相机、示教、训练或机器人验收，也没有提交或推送代码。

## Astra high 审查修订记录（2026-09-11）

| 审查问题 | 修订位置 | 新验收证据 |
| --- | --- | --- |
| P1 全机器人接触缺失 | Task 8 Step 3a：新消息、support plugin、observer | 不含杯子的实际碰撞、截断/丢帧均触发双方停止 |
| P1 公共仲裁缺失 | Task 7A，Task 14/15 复用 | ACT 持有 lease 时教师/Teleop 跨入口提交拒绝 |
| P2 reset 只读不写 | Task 3 Step 3a，Task 10 | 七关节 override 序列化、两个实际初态读回、旧六关节兼容 |
| P2 推理环境断点 | Task 12 load_policy、Task 13 Step 3a | 无 LeRobot 的 ROS 环境与独立 worker 的真实进程 smoke |
| P2 Offline Test 无入口 | Task 12A、Task 16、运行命令 | 冻结 hash、10 episode、padding mask 与动作误差报告 |

## Astra high 并行采集审查修订记录（2026-09-16）

本节是历史审查轨迹。涉及 adaptive continuation、分档扩容或 Task 7A command broker 的条目已由 2026-09-24 设计和本版 Task 7A/11A 取代，不再是可执行合同。

| 审查问题 | 修订位置 | 新验收证据 |
| --- | --- | --- |
| P1 搜索放入 initial gate 会被误判为 infra，且后续重复 reset | Task 11 分阶段接口；Task 11A Step 3a | 每 attempt 一次 reset；搜索失败封存为业务 `FAILED` 且不 fallback；旧 reset epoch/pose 拒绝 |
| P1 production 子进程缺少 ACT ports 与恢复 verifier 注入口 | Task 11A Files、workload factory、result store/verifier | 旧 spec 默认行为回归；真实 ACT 子进程构造；seal 后 ACK 前崩溃由 `discover` 恢复 |
| P2 资格目录超过 Unix socket 长度 | Task 11A 短目录合同、运行命令 | 真实绝对根枚举全部 socket，编码长度不超过 107 bytes，超限零进程启动 |
| P2 配额选择受 Worker 完成顺序影响 | Task 11A 完整 wave 屏障与 manifest 前 N 规则 | 乱序完成仍选择相同 `scene_id`；surplus/unscheduled 有明确状态 |
| P2 qualification schema 与正式 split 冲突 | Task 10、11、11A qualification mode | 两种模式互斥白名单；资格结果不能生成 Task 12 输入 |
| P2 8 场景不足以证明 W8 持续负载 | Task 11A Step 6–7、测量门槛 | 8 场景只验 W2 功能；40 场景形成两个完整 wave、每 wave 每 Worker 至少 2 项、候选默认全新 root 复测 |
| 第二轮 P1：已启动未终态的 AdaptiveBatchRunner 只能报告，外层无续跑协议 | Task 11A `ActWaveReconciler` | 旧资源先 fencing；verify/discover 后导入；累计 infra budget 分组 continuation；外层导入前崩溃测试 |
| 第二轮 P2：五集合总清单与三 split 采集白名单冲突 | Task 10 collection 投影、运行命令 | `splits.json` → `collection.json` hash 贯通；Rollout 集合不调度；正式入口只读投影 |
| 第二轮 P3：preferred 项可被 stealing，不能写成静态保证 | 设计第 7 节、Task 11A Step 7 | 初始优先分配；按每个 Worker 实际 terminal lease 验收 |
| 第三轮 P2：崩溃对账可能导入 durable expiry 后的迟到 seal | Task 11A 对账优先级 | expiry/revocation/replacement/late rejection 优先；seal 完成时间不超过 lease deadline；专门故障测试 |
| 第三轮 P2：降级完成可能误算被测档位资格 | Task 11A Step 6–7 | 每个资格 wave 固定 `levels_used == [n]`，零 infra retry/fallback/continuation；降级只作恢复证据 |
| 第三轮 P2：旧方案 socket 预检遗漏独立动作端点 | 历史 Task 11A `act_parallel_socket_paths` | 当时补入全清单 107/108-byte 边界；现由 typed ROS child endpoint manifest 取代 |
| 第三轮 P3：缺完整八场景单 stack 命令 | 运行命令 `u` root | 5 条 smoke 与 8 条性能基线分开，W1/W2 都与完整基线比较 |
| 第三轮 P3：Task 14 重复标 Create | Task 14 Files | `so101_mujoco_act.launch.py` 改为 Modify，保留 Task 3 Create |
| 第四轮 P3：无法构造“只有新增短端点超长”的测试 | Task 11A socket 故障矩阵 | 改为端点包含性、三类消费者同集合，以及全清单最长路径 107/108-byte 边界 |

本次修订仅更新设计与实施计划，以上均为待执行要求，不表示相应测试、采集或运行验收已通过。历史审查记录对应各轮修订前的文件 hash，保留原记录，不覆盖历史结论。
