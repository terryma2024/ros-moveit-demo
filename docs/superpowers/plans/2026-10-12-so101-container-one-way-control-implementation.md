# SO-101 容器单向控制实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 原由 Codex inline 执行；用户最新要求 Codex 停止、Claude 接续，继续使用同一 worktree、单写者和 inline 自审；不使用 dst、subagent 或独立 reviewer。

**Goal:** 实现 Coordinator 发起的四操作容器协议、固定输出回收和执行故障清理，并在交付前移除旧协议专属源码与测试。

**Architecture:** Host 适配器提供 `start`、`assign_task`、`get_status`、`terminate`，容器顺序执行完整场景任务。Host 持有调度和目录映射，查询成功后回收数据，只用 task_id 一致性校验任务归属。执行故障确认该实例全部运行资源退出，数据质量继续使用既有 QC。

**Tech Stack:** Python、ROS 2 Jazzy、MuJoCo、Docker、现有私有 Unix IPC、MCAP、pytest/xdist。

**Spec:** [2026-10-12-so101-container-one-way-control-design.md](../specs/2026-10-12-so101-container-one-way-control-design.md)。用户已确认书面设计、task_id 简化及旧协议清理，并于本计划提交 `a36c1f1e5` 后回复 `ok` 批准实施。执行方式沿用当前 Codex inline；无需再次审批。

## Global Constraints

- 只允许 Coordinator 发起控制调用，操作只有 `start`、`assign_task`、`get_status`、`terminate`；每实例同时一个任务。
- 容器输出根固定 `/act/output`，任务目录 `/act/output/tasks/<task_id>/`；任务参数不含输出路径。
- 任务归属只核对发出的 task_id、状态返回的 task_id 和结果中的 task_id；不增加执行身份、租约交互或提交证明协议。
- Teacher 失败、抓取失败和正常 QC `INVALID` 是业务结果；进程异常、超时等执行故障触发实例清理。
- `SUCCEEDED` 必须在原有停止确认、bag 关闭、结果完整落盘与 seal 完成后发布；Host 核对 task_id 后登记回收。既有 QC/导出规则决定数据是否合格。
- 未确认资源释放不得复用槽位或 GPU 占用；故障实例不终止其他实例仍在使用的共享 Head/Teacher 服务。
- 固定输入、源身份、原始时间戳/hash、Teacher 安全条件及 QC 门槛保持不变。无 CPU 推理降级。
- 复用当前 ai-station worktree/分支；只有一个 Codex writer。无 self SSH、dst、agent、resume、新 worktree、硬件、训练、push、证据删除或阈值降低。
- registered root 为 `/data/work/so101-evidence/act-data/20260924-fbc25063-resume`；本 dispatch 证据子目录为其下 `container-campaign-20261012T003700Z-2130aaf1`，下文记作 `R`。
- 每次 fsync-heavy pytest 使用 `R/scratch/` 下全新目录，设置 TMPDIR/TMP/TEMP，用实际 Python 确认 tempfile 路径；不删除 scratch。
- 每项任务做定向 RED/GREEN 和 inline self review；完整普通包门禁只在最终 source/image freeze 与必要的最终修复边界运行。普通范围不收集 benchmark。
- 旧协议清理必须在同一计划内完成；不留下兼容入口、双协议开关或无调用者的旧专属实现。非容器流程和历史证据保留。

## Review Focus

- 发任务响应丢失：只查询原任务，不能重复执行；Task 1、4 覆盖。
- terminate 与正在构造/执行的任务竞态：不遗漏迟到辅助进程，不重新进入 READY；Task 3 覆盖。
- 固定目录中的残留结果：缺失或错误 task_id 不得回收为本项任务，不能修改原始 seal；Task 2、4 覆盖。
- 当前执行与上一项任务的观测混用：保持既有 reset/freshness 安全检查，不为此增加 Coordinator 调用；Task 3 覆盖。
- 清理后通用 IPC 或正式导出受损：保留仍有非容器调用者的实现和有效断言，最终真实链与逐包门禁运行在清理后的版本；Task 5、6、7 覆盖。

## 文件职责与当前基线

计划基线为 `55db48a2a`。当前六个 source/test 草稿未提交：`campaign_shard.py`、`shard_owner.py`、`shard_launcher.py`、`worker_builder.py`、`test_campaign_shard.py`、`test_worker_builder.py`。先保存 diff/hash 和引用清单到 R；后续迁移其有效检查，禁止 reset/stash/clean。既有 Claude 和其他 Codex/app-server 会话保持不动。

新文件放在 `src/so101_demo_py/src/runtime/container_campaign/`：

| 文件 | 职责 |
| --- | --- |
| `task_contracts.py` | 封闭任务请求和状态值；拒绝额外字段和不合法 ID。 |
| `task_control.py` | Host 四操作适配器，对接原有 owner 和当前私有 control client。 |
| `task_executor.py` | 容器单任务执行、状态保存、期限和单次清理。 |
| `task_builder.py` | 从冻结任务输入构造真实 Teacher/Recorder/runtime；不连接 Host Coordinator。 |
| `task_journal.py` | Host 发放和回收的本地记录；核对 task_id，不提供容器 RPC或额外证明协议。 |

已有 `paths.py`、`case_artifacts.py`、`collection_runtime.py`、`coordinator.py`、`result_verifier.py`、`shard_owner.py`、`shard_launcher.py` 和 `owner.py` 分别承接映射、单任务 artifacts、本地运行、轮询调度、回收、资源归属与 campaign 生命周期。改动限于相关职责，不重新搭一套 registry。

`src/so101_teleop/so101_teleop/unified/` 下的 `ipc.py`、`child_runtime.py`、`ros_child.py`、`bridge.py`、`teleop_service.py` 和 `admission.py` 只修改容器任务的接线。通用 pick-place、macOS 和非容器 batch 不切换协议。

## 定向验证约定

执行前验证 `R/container-test-venv/bin/python` 可执行及测试 import 的真实源路径。已有 `R/run-targeted-container.zsh` 为每次调用建立 NVMe scratch 并保存 argv、tempfile proof、JUnit、退出码和耗时。调用形式如下，实际命令使用完整 R 路径，不能将缩写 R 直接当作现有目录：

```zsh
zsh "$ACT_RUN_ROOT/run-targeted-container.zsh" <本任务的测试路径> -q
```

每项任务的 RED 必须到达指定代码边界；缺依赖或不存在测试路径不是 RED。GREEN 需要 rc=0，明确 pass/fail/skipped 数量。每项结束保存 exact diff/source hash 与自审结果，再只提交本项路径。

### Task 1: 四操作合同和 Host 适配器

**Files:** 创建 `task_contracts.py`、`task_control.py`；修改 `control_client.py`、`src/so101_teleop/so101_teleop/unified/ipc.py`；新增 `test/runtime/container_campaign/test_task_control.py` 和 `src/so101_teleop/test/unified/test_container_task_contract.py`。

**Interfaces:** `TaskSpec(task_id: str, inputs_ref: dict, deadline_monotonic_s: float)`；`ContainerTaskControl.start() -> InstanceStatus`；`assign_task(task: TaskSpec) -> TaskStatus`；`get_status(task_id: str | None = None) -> InstanceStatus`；`terminate(reason: str) -> InstanceStatus`，四方法均 async。适配器构造时绑定唯一 shard owner，不在各调用中接收可变实例或目录。

`InstanceStatus` 固定包含 instance_id、state、task、fault_reason、resources_released。`TaskStatus` 固定包含 task_id、state、fault_reason。实例状态和任务状态取值采用设计原文；未知任务明确拒绝，不返回另一任务的成功。`inputs_ref` 使用既有冻结输入引用，不另包执行身份或提交证明。没有输出路径、回调 endpoint、coordinator token 或 ACK 序号字段。

- [x] 写测试 `test_only_four_operations`、`test_assignment_rejects_output_and_callback_fields`、`test_unknown_task_cannot_return_previous_success`、`test_lost_assignment_reply_queries_without_resend`；断言额外字段、bool deadline、非有限/过期期限、路径分隔符 ID 和输入变化被拒绝。
- [x] 对上述两个测试文件运行定向 RED，记录真正合同或适配器边界的失败。
- [x] 实现封闭合同和单次控制 exchange；start/terminate 委托原有 owner；不引入 HTTP、额外服务或第五操作。
- [x] 对上述两个文件及已有 `test_control_client.py`、`test_unified_ipc.py` 运行定向 GREEN；检查通用 IPC 的旧支持范围未被容器改造覆盖。
- [x] inline self review 并 scoped commit：`feat: add four-operation container task control`，`4e50afec0`；最终定向 gate 49 passed，见 CP-3601。

### Task 2: 固定输出和原始结果引用

**Files:** 修改 `paths.py`、`launch.py`、`case_artifacts.py`、`src/so101_demo_py/src/act/result_store.py` 中需要注入任务 workspace 的容器边界；新增 `test/runtime/container_campaign/test_task_output.py`，更新 `test_paths.py`、`test_case_artifacts.py`。现有非容器 `_workspace` 默认布局保持原契约。

**Interfaces:** `task_output_path(output_root: Path, task_id: str) -> Path` 只定位 `<root>/tasks/<id>`；`host_task_output(owner_root: Path, task_id: str) -> Path` 为 Host 对应目录。`CollectionCaseArtifacts` 的容器任务绑定接受显式 task workspace，不用改名 scene/attempt 身份来绕过原有检查。

容器在任务目录写 `task-result.json`，其中 task_id 原样来自 assign 请求，业务结果和已有数据文件引用由真实 producer 产生。完成记录与结果文件完整落盘后才发布 SUCCEEDED；不添加执行身份签名、提交证明或回调 token。

- [x] 写 `test_fixed_output_mount_and_distinct_instances`、`test_task_workspace_not_overwritten`、`test_foreign_or_symlink_output_refused`、`test_sealed_paths_readable_on_host_without_rewrite`。不同实例 Host 根对应固定容器目标；跨根原始字节保持测试控制外部 mount，未声称真实 Docker/QC。
- [x] 对 `test_task_output.py` 运行 RED。
- [x] shard launch 为 act_collection 强制将实例 output 专属目录映射到 `/act/output`；native 控制/停止证据仍用原有私有目录。不同实例不能共用输出根。回收不修改已有结果内容；真实 producer 引用在 Tasks3–5 接入后验证。
- [x] 容器注入边界使用 `tasks/<task_id>/attempts/<scene>/<attempt>`，保持原有 result store 的内部布局与内容检查，无需修改全局 ActCollectionResultStore 或新增租约证明。
- [x] 运行新增测试及现有路径/artifacts/result schema/QC/commit 定向 GREEN，最终 165 passed，见 CP-3602。
- [x] inline self review 并 scoped commit：`feat: bind task results to fixed container output`，`110f1f88e`；最终定向 gate 165 passed，见 CP-3602。

### Task 3: 容器本地完整任务执行与故障清理

**Files:** 创建 `task_executor.py`、`task_builder.py`；修改 `collection_runtime.py`、`case_artifacts.py`、`src/so101_demo_py/src/runtime/act_teacher_client.py` 的容器 context provider、`src/so101_demo_py/src/cli/campaign_shard.py`；新增 `test_task_executor.py`、`test_task_builder.py`。迁移草稿中的冻结输入和真实 stack 校验，不复制旧 proxy。

**Interfaces:** `build_collection_task(task: TaskSpec, *, stack, shard_spec, output_root: Path) -> CollectionTaskExecution`；`CollectionTaskExecution.run() -> dict` 返回已封存结果摘要，`request_stop() -> None` 和 `shutdown_owned() -> bool` 管理任务资源。`ContainerTaskExecutor.assign_task(task) -> TaskStatus`、`get_status(task_id=None) -> InstanceStatus`、`terminate(reason) -> InstanceStatus` 对接 Task 1 私有通道。

容器保存 assign 请求的 task_id，后续状态和 task-result.json 原样使用该 ID。禁止远程 lease grant/renew/ACK/recovery；不构造新的 Teacher 执行身份。现有运行组件继续检查 reset 后的观测、期限和安全条件，阶段预算使用原配置，不靠 Host 心跳 projection。原始数据若包含历史身份字段，它们属于内部证据格式，不是本协议的任务校验条件。

- [ ] 写 `test_business_failure_is_success_and_next_task_runs`、`test_qc_process_crash_is_execution_fault`、`test_success_waits_for_closed_bag_and_seal`、`test_terminate_during_builder_stops_late_helpers`、`test_expired_or_changed_local_context_refuses_teacher`、`test_stale_status_poll_triggers_owned_stop`；同时覆盖业务失败与 QC INVALID、超时与故障后禁止新任务。
- [ ] 对新增 executor/builder 文件运行 RED。
- [ ] 由真实 ActStack、ActRosRuntimePorts、共享 Teacher client、record-only Recorder 和现有离线/QC/seal producer 构造本地执行器；不使用 ParallelWorker 的 Coordinator 回调循环。共享 Head client 与现有 track/search/freshness 规则保持真实调用。
- [ ] 私有 assign 请求创建后台任务后立即返回 ACCEPTED，status 可在任务执行期间响应。任务与有效 status 请求分别驱动任务期限和 owner 存活期限；移除专属 heartbeat channel 的接线。终止 single-flight，处理构造中和执行中的辅助进程，迟到结果不解封已关闭实例。
- [ ] 运行新增测试及当前 runtime、Teacher client、Recorder close/stop、topic-map 与 QoS 定向 GREEN；分别说明真实组件和受控外部观察，不能以 fixture 声称物理验收。
- [ ] inline self review 并 scoped commit：`feat: execute collection tasks locally in shards`。

### Task 4: Host 轮询、结果校验与登记

**Files:** 创建 `task_journal.py`；修改 `coordinator.py`、`result_verifier.py`、`owner.py`、`src/so101_demo_py/src/act/result_store.py`、`parallel_collection.py`、`parallel_qualification_verifier.py` 的容器结果校验/提交读取；新增 `test_task_journal.py`、`test_task_coordinator.py`、`test_task_commit_readback.py`，迁移 `test/parallel_batch/test_container_wave_assignment.py` 的有效分配断言。

**Interfaces:** `ContainerTaskJournal.assign(*, instance_id, task, host_output) -> dict`；`collect(*, task_id, result) -> dict`；`fail(*, task_id, reason) -> dict`；`read_container_task_result(owner_root: Path, *, task_id: str) -> dict`。`ConcurrentCollectionCoordinator.run_wave` 保留 owner 使用的签名及 wave 输出键，内部使用 Task 1 适配器轮询，不调用旧 run_worker。

Host 本地记录任务 ID、所属容器、固定目录映射和回收结果，沿用现有持久写入原语，不新增 hash-chain 提交证明。查询 SUCCEEDED 后，读取该目录 task-result.json，只核对其中 task_id 与发出和状态返回的 ID 一致；缺失或不一致即拒绝。登记结果供 wave report 和 frozen index 使用，后续 QC/导出继续执行既有质量规则。旧 phase-lease commit checker只用于非容器流程，容器不生成旧 lease commit 事件，不要求额外开始证明或执行身份链。

- [ ] 写 `test_collect_only_after_matching_success`、`test_collection_requires_only_matching_task_id`、`test_missing_or_mismatched_result_id_refused`、`test_qc_invalid_is_collected_but_cannot_export`、`test_reservations_require_two_real_terminal_tasks`。相同 ID 的业务失败结果可回收；结果不含旧身份链或提交证明也可回收；缺失或错误 ID 必须拒绝。
- [ ] 对上述三个新文件运行 RED。
- [ ] 改成 all-ready barrier 后由 Host 逐任务发放、查询；两项 reserved 任务完成后才使用 surplus。取得 matching SUCCEEDED 后，按固定映射读结果、核对 ID并登记，再发下项任务。执行故障停止 dispatch 并触发 owner 清理；业务失败留在原分母。
- [ ] 实现按 task_id 的结果读取，接入 frozen campaign index/formal reader，不把旧提交证明改名继续使用。数据 QC/export rules保持不变；训练仍只消费 frozen index 中已回收登记且合格的数据。
- [ ] 对新增文件及旧 qualification reservations、result QC/export、owner/wave verifier 的有效测试运行 GREEN；20+20 原始分母、每实例至少两项终结任务和资格模式互斥断言保持。
- [ ] inline self review 并 scoped commit：`feat: poll and verify container task results on host`。

### Task 5: 真实 CLI、实例 owner 和四操作集成

**Files:** 修改 `shard_owner.py`、`shard_launcher.py`、`src/so101_demo_py/src/runtime/act_fixed_collection_composition.py`、`src/so101_demo_py/src/cli/act_collect_parallel.py`、`campaign_shard.py`，以及统一 service/admission/child_runtime/ros_child/bridge 接线；更新 `test_campaign_shard.py`、`src/so101_teleop/test/unified/test_container_collection_operation.py`；新增 `test/cli/test_container_task_campaign_integration.py`。

**Interfaces:** 真实 CLI 通过现有 OperationSpec/admission 构造实际 `ContainerCampaignOwner`，每个 shard 使用 `ContainerTaskControl`，真实任务构造使用 Task 3，提交使用 Task 4。宿主机适配器从当前 registry 和 Docker inspect返回真实退出与资源释放状态。

- [ ] 写 `test_real_cli_builds_four_operation_owner`、`test_exited_instance_status_keeps_fault_and_stop_proof`、`test_unproven_stop_keeps_slot_fenced`、`test_shard_fault_preserves_shared_service`。CLI 测试经过实际 prepare/admission/owner/finish，不只验证 factory dict。
- [ ] 对实际 CLI/control 接线运行 RED；核对 launcher 草稿真实 `slot.namespace` 与 `worker_recovery_timeout_s` 字段，禁止用猜测属性修复 fixture。
- [ ] 连接当前 builder/launcher、精确 private IPC、Docker registry/native ready/retirement与四操作；去除 worker-spec/coordinator socket/token 接线。通用服务仍保留自己的功能；容器路径只开放已定义操作。
- [ ] 定向 GREEN 后运行真实不可运动的实例启动/查询/终止，保留当前源码、安装、镜像、CID、namespace 和退出证据。只声明无运动基础设施结论。
- [ ] 验证真实控制 socket、实际本地执行器、结果落盘和 Host 回收登记的集成接线，外部 ROS/Teacher 若受控必须明确标注。真实物理完整场景在 Task 7 最终冻结和 fresh 安全准入后执行，不用旧 calibration 或 fixture 声称通过物理验收。
- [ ] inline self review 并 scoped commit：`feat: connect one-way task control to campaign entry`。

### Task 6: 移除旧协议专属实现和测试

**Files:** 删除 `worker_transport.py`、`worker_runner.py`、`collection_worker.py`、旧 `collection_driver.py`、旧 `worker_builder.py`；删除对应专属 `test_container_coordinator_transport.py`、`test_container_worker_runner.py`、`test_container_collection_worker.py`、`test_collection_driver.py`、`test_worker_builder.py`。若某文件还有有效职责，先迁移至上述新文件再删除；其他混合文件仅移除容器旧接线。

- [ ] 保存清理前引用清单和新协议集成结果；用 `rg` 枚举旧 proxy/transport/runner/Worker、coordinator socket/token、heartbeat channel 和 worker-spec 在 active source/config/test 中的引用，逐项标明容器专属或通用使用者。
- [ ] 将尚未迁移的停止、数据、身份和分配断言补到新测试并运行 RED/GREEN；不保留只验证已废弃调用序列的测试。
- [ ] 用 targeted patches 删除专属实现、测试、安装/export、旧配置和失效入口。容器专属 `heartbeat.py`、`test_owner_heartbeat.py` 的功能迁入状态查询存活检查后移除；如果非容器 runtime 仍依赖其监视器，先迁移共享监视逻辑到明确的通用模块，禁止保留第二条容器 heartbeat 通道。
- [ ] 扫描 active 容器路径确认无旧 protocol symbols/imports/配置，无双协议开关；检查通用 `parallel_ipc/authority.py`、`cli/mujoco_batch/composition.py` 和 `worker_process.py` 的非容器使用者仍可导入与运行。Git 历史和历史 ledger/spec/snapshot 引用不计为残留代码。
- [ ] 对 Task 1–5 的新测试、受影响通用 IPC/CLI、数据提交与正式导出回归运行定向 GREEN。无旧专属测试被误收集，无有效业务断言丢失。
- [ ] inline self review 并 scoped commit：`refactor: remove superseded container callback protocol`。

### Task 7: 清理后冻结、完整门禁与原 campaign 接续

**Files:** 两个既有 `docker/campaign-{inference,shard}/Dockerfile`（必要安装修正）、相关 setup/install 规则、实验账本，以及 `docs/guides/` 下当前采集说明。persistent prose 使用项目 humanizer；不得把未测功能写为可用。

- [ ] 对最终 active source/CLI/schema 做自审，确认四操作、固定 mount、Teacher/Head 实际 provider、状态存活、完整数据链、task_id 回收读取与旧代码清理全部已连接。导出回归必须从 frozen index 读取已登记数据，拒绝目录扫描/资格模式/业务失败或数据 INVALID。
- [ ] 接续 dispatch approved-docs 中原计划剩余生产 measurement/Head/live 边界；任何尚未实现的 provider 必须在最终 source/image freeze 前接入并定向验证，不留“冻结后接入”项。
- [ ] 在完整 ROS underlay 上以唯一 R 内 build/install/log base 执行 `colcon build --packages-up-to so101_demo_py so101_teleop`；确认依赖闭包、实际 interpreter、各 package prefix 和 source/install/module origin。缺 setup/underlay/override 分类为环境问题，不算 source RED。
- [ ] 按冻结后的实际 package test 声明逐包运行完整普通 xdist，worker=`min(8, os.cpu_count() or 1)`，独立新 scratch、确切 Python tempfile proof、CPU/worker/argv/rc/JUnit/skips/耗时。`so101_demo_py` 范围为 `test/`，`so101_teleop` 范围为自己的 `test/`，不跑 benchmark。colcon 示例沿用原批准计划：`colcon test --packages-select so101_demo_py --pytest-args test -n "$ACT_XDIST" --event-handlers console_direct+`，随后读取 `colcon test-result --verbose`；不能用汇总替代实际 pytest 退出证据。
- [ ] 从同一个最终 source/install freeze 重建两类镜像，核对 source SHA、submodule、image digest、non-root权限、CUDA/EGL和共享模型实例，验证清理后的真实四操作。若最终修复产生新增代码，重新冻结后才运行相应 fresh验收。
- [ ] 按原批准规则执行 fresh calibration/Head promotion/live，然后实际完整单任务 Teacher、Recorder、bag close、offline10Hz、QC、seal、Host 查询/回收/commit 和退出链；继续 same-eight W1/W2、独立40/two20 exact-W8、formal approved split/quota及 training-ready committed manifest。不复用旧 topology PASS。HFA-010 UNKNOWN 和 stop-window 未确认观察如构成前置条件，按原始证据解决；资源或明确人类安全选择缺失时保存证据并只询问该缺项。无 W4/W6、自动补采或降门槛。
- [ ] 交付记录 retained/archived/deletion candidates 和实际拥有/保留进程；不删除证据，不训练、不 push。只在全部原 campaign 目标满足后标记 goal complete；本协议集成通过不是整个 goal 完成。

## 自审与执行交接

覆盖映射：四操作和消息边界→Task 1；固定目录、任务结果文件→Task 2；完整执行、业务/故障区分、清理/存活→Task 3；调度、分母、task_id 回收登记及原有导出规则→Task 4；真实入口与资源归属→Task 5；强制旧协议清理→Task 6；最终门禁和原 campaign 目标→Task 7。Review Focus 的五类失败均有对应定向测试。

自审确认新接口签名一致；任务归属只核对 task_id，没有改名保留执行身份或提交证明协议；原有本地执行安全条件与数据 QC保持。路径变化限制在实例 output 与其固定 mount；旧代码清理发生在完整门禁之前。所有步骤未执行，checkpoint 不宣称 GREEN。

本计划已批准。CP-3601 在 source 实现前确认原生 goal active；用户随后要求 Codex 停止、交由 Claude 接续，CP-3603 记录真实 native goal paused。Claude 从 Task3 接续，不重新审批 Task1/2 或恢复旧 Codex 会话争写；原有业务授权、禁止事项、批准快照及未完成的 campaign gates继续适用。完整交接在 dispatch R/claude-handoff-20261012.md。
