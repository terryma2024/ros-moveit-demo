# SO-101 macOS service campaign 闭环实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 实际实现只能由 mac-mini 上 tmux session `dst-so101-macos-closure` 中的 DeepSeek Harness TUI（`dst`）inline 执行；每个 checkpoint 由 GPT-5.6 Sol / High 复核，设计、计划和最终 guide 由 GPT-6 Astra / High 独立审查。

**Goal:** 在 macOS MuJoCo 仿真上闭合统一 Web 服务的 W2 first-pass、W1 first-pass 与单点 `FULL_RESTART_RETRY`，只使用现有轻量 `StartGuard` 做启动保护，并完成可恢复 projection、真实 owner tree 和 fresh Chrome 验收。

**Architecture:** macOS 固定只支持 W1/W2。schema v4 保持 exact-W2；schema v5 表达 W1 retry；schema v6 表达 W1 ordinary first-pass。Web selection 进入 durable shared queue，每个 Worker lease 只执行一个点；既有 `CoordinatorJournal` 用 committed watermark 向唯一 reducer 提供权威事件。`StartGuard` 在 campaign 和每个 Worker spawn epoch fresh 执行，运行期安全由既有 hard timeout、lease、owner tree、fence 和 cleanup 收敛。

**Tech Stack:** Python 3.11、SQLite、ROS 2 Jazzy、MoveIt 2、ros2_control、MuJoCo、PyTorch MPS、AF_UNIX、FastAPI/Pydantic、React/TypeScript、Bun、Vitest、Playwright、pytest、colcon/CMake/gtest。

**Spec:** [SO-101 macOS service campaign 闭环设计](../specs/2026-09-21-so101-macos-service-campaign-closure-design.md)。执行恢复锚点为本地提交 `fea8f57c`、`e264d1eb`、`82b7a7d9`；执行器必须先回读其完整 SHA 与 ancestry。

## Global Constraints

- 本计划从 legacy `CP-MSC-A` 恢复，但该 checkpoint 的结论是 `UNCONFIRMED`，不是 PASS。task-owned station 曾 READY；5x `FULL_RESTART` 尚未执行。
- 已完成的 Task 0–2 不重跑、不改写。先回读三个恢复提交、ledger、证据和 dirty state；缺失或 ancestry 不符即停止。
- 唯一实现执行器是现有 `dst-so101-macos-closure`。旧 `dst-so101-macos-mps-w2` 保留且不接管；不启动第二个 writer、第二个实现 worktree 或第二套服务。
- 不授权真实机械臂、sudo、系统/全局环境修改、停止 foreign 进程、删除或归档证据、push、merge、force push 或发布。
- 继续使用已有单写 ledger `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md` 和其中登记的唯一 evidence root。不要创建第二个 root。每次实验先写 `PLANNED`。
- macOS 不套用 ai-station 的 `/data` NVMe pytest scratch 规则。每个测试调用使用 evidence root 下新子目录，并设置 task-local `ROS_HOME`、`ROS_LOG_DIR`、`TMPDIR`、`TMP`、`TEMP`。
- 所有产品修改严格 RED -> GREEN；依赖导入、DYLD bootstrap、零收集和未执行到目标边界不算 RED。
- schema v4 bytes/SHA 与 exact-W2 含义保持不变。v5 只允许 Darwin/MPS W1 `FULL_RESTART_RETRY`；v6 只允许 Darwin/MPS W1 `FIRST_PASS`。
- macOS `worker_count` 只允许 1/2。N>2 Web 不可选，API/preflight/adapter 拒绝。worker profile 不从 point count 推断。
- 只复用现有 `StartGuard`：RAM 和 MPS headroom FAIL 阻止 spawn，CPU busy 只 WARN，probe/identity/scope/cleanup error fail closed。不得新增 sampler、运行期 watchdog或容量公式。
- `so101_measure_parallel_resources` 保持 retired/fail closed；不创建替代入口，不修改旧预算设计/计划。
- `PointStatus` 仍只有 `UNRUN/PASSED/FAILED/INDETERMINATE`。`RUNNING` 属于 execution phase，`INVALID` 属于 attempt validity。
- 一个 service instance 同时只允许一个 active campaign 和一个有效 control lease。W1/W2 不并行。
- 每个 task 只 stage 自己列出的文件，运行 `git diff --check` 和 scoped diff readback 后提交；不用 `git add -A`。
- live 验收只声明功能、稳定性、物理结果、projection、ownership 和 cleanup，不声明 resource qualification 或 capacity certification。

## 已完成快照与恢复规则

| 已有事实 | 状态 |
| --- | --- |
| runtime closure、run binding、attestation 实现 | 已在恢复提交中，执行前回读测试与 diff |
| controller 直连诊断与 MoveIt readiness 分离 | 已在恢复提交中，执行前回读测试与 diff |
| task-owned full station READY | OBSERVED：3 controllers、3 services、3 actions |
| 旧卡死 | 只在 incomplete dylib closure 中复现，`@rpath/libmujoco.3.4.0.dylib` load failure |
| C++ controller 根因 | `UNCONFIRMED`；foreign modified overlay 未重跑，无 C++ 产品修改 |
| Gate A 5x FULL_RESTART | NOT RUN |

恢复后先在 ledger 追加 `CP-MSC-R0`，保留 legacy `CP-MSC-A` 原文，不回写成 PASS。

## 文件与接口总图

| 边界 | 文件与职责 |
| --- | --- |
| Gate A / rpath | `third_party/mujoco_ros2_control/mujoco_ros2_control/CMakeLists.txt`；`src/so101_demo_py/test/test_macos_install_contract.py`；既有 runtime closure/diagnostic 测试 |
| selection / queue | 新 `parallel_batch/selection.py`、`queue.py`、`single_point_input.py`；修改 W2 campaign/worker/composition |
| journal / projection | 修改 `parallel_batch/journal.py`；新 `expert_validation/reducer.py`、`projection_source.py`；修改 events/models/store/production |
| owner tree | 新 `expert_validation/owner_tree.py`；修改 process owner/store/supervisor 和四个真实 spawn 边界 |
| W1/W2 profiles | 新 v5/v6 YAML、`w1_composition.py`、两个 W1 CLI；修改 contracts、adapter、setup |
| StartGuard spawn binding | 修改 `macos_service_campaign.py`、`campaign_supervisor.py`、`macos_w2_worker.py`、W1 composition；复用现有 guard/probe |
| execution authorization / retry | 新 `expert_validation/execution_context.py`；修改 API/models/store/supervisor/service/statistics |
| support matrix / Web | 修改 preflight/api/production、unified app、campaign setup/app、生成 OpenAPI/types 和 live-sim tests |
| 最终文档 | 修改 task ledger；新 `docs/guides/so101-macos-service-campaign-closure.md` |

---

### Task 1: 恢复 checkpoint，闭合 copied-install rpath，并完成 5x readiness

**Files:**
- Modify only when Step 3 confirms the rpath boundary: `third_party/mujoco_ros2_control/mujoco_ros2_control/CMakeLists.txt`
- Modify only when Step 3 confirms the rpath boundary: `src/so101_demo_py/config/mujoco/dependency-lock.yaml`
- Modify only when Step 3 confirms the rpath boundary: `src/so101_demo_py/config/dependency-lock.yaml`
- Modify only when Step 3 confirms the rpath boundary: `scripts/check_backend_integration.py`
- Modify: `src/so101_demo_py/test/test_macos_install_contract.py`
- Modify: `src/so101_demo_py/test/test_runtime_closure.py`
- Modify: `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md`

**Interfaces:**
- Consumes: committed `RuntimeClosureIdentity`, `RunBinding`, `RuntimeAttestation`, `so101_diagnose_macos_station`
- Produces: relocatable macOS install-rpath contract, confirmed first bad boundary, five consecutive valid readiness records, `CP-MSC-01`

- [ ] **Step 1: 回读恢复锚点与已有证据**

在 `dst-so101-macos-closure` 中回读 `hostname`、`pwd`、branch、HEAD、三个恢复提交的完整 SHA、
`git status --short`、submodule SHA/status、ledger latest checkpoint、tmux 和相关进程。把 ledger 中的
`RUN_ROOT`、`TEST_PYTHON`、ROS/TMP 路径加载并逐项验证。Expected: legacy checkpoint 明确为
`UNCONFIRMED`；不存在第二个 writer 或未归属的 task process。

- [ ] **Step 2: 写 copied-install rpath RED**

在 `test_macos_install_contract.py` 增加断言：copied install 的
`libmujoco_ros2_control.dylib` 必须包含可重定位的 MuJoCo vendor LC_RPATH；在移除 task-owned
`DYLD_LIBRARY_PATH` 的净化环境中，plugin 的 `libmujoco.3.4.0.dylib` 依赖必须可解析到同一
copied prefix。`test_runtime_closure.py` 增加 loaded image 超出 copied prefix/vendor closure 的拒绝。

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_macos_install_contract.py \
  src/so101_demo_py/test/test_runtime_closure.py \
  --junitxml="$RUN_ROOT/task1-rpath-red.xml"
```

Expected: 非零收集；RED 精确落在缺少 vendor LC_RPATH/净化环境无法解析，不是 import 或工具缺失。

- [ ] **Step 3: 运行有界 A/B**

预先登记两条实验，使用相同 copied bytes/config 和 domain policy。A 不注入
`DYLD_LIBRARY_PATH`；B 只注入当前 task-owned vendor lib 路径。保存 `otool -L`、`otool -l`、
plugin XML、loaded images、direct controller query 与 READY 结果。Expected: 只有当 A 在 dylib
解析处失败而 B READY，才确认 install-rpath 根因；否则保持 `UNCONFIRMED` 并停止，不改 C++。

- [ ] **Step 4: 实施最小 CMake 修复并 GREEN**

只修改 submodule CMake 的 Apple `INSTALL_RPATH`，保留 `@loader_path`，并加入指向同一 prefix
`opt/mujoco_vendor/lib` 的相对 loader path。不得改 node、dispatcher 或 hardware interface。
先形成 submodule commit，再把它的完整 SHA 同步到两份 dependency lock 和
`check_backend_integration.py` 的 candidate 常量；parent gitlink、两锁、candidate 断言和 submodule
HEAD 必须一致，并继续证明 lineage/policy ancestry，不得放宽 provenance 测试。冻结这组来源后再
重建 copied install，并在净化环境运行上一步测试和 diagnostic。

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_macos_install_contract.py \
  src/so101_demo_py/test/test_runtime_closure.py \
  src/so101_demo_py/test/test_diagnose_macos_station.py \
  src/so101_demo_py/test/test_motion_stack_ready.py \
  --junitxml="$RUN_ROOT/task1-rpath-green.xml"
```

Expected: copied install 不依赖 task-owned `DYLD_LIBRARY_PATH`；loaded images 都属于 attested
closure；原 A/B 首坏边界翻转。

- [ ] **Step 5: 执行五次 FULL_RESTART**

为五轮分别创建新实验 ID。每轮要求 closure hash 相同、run/attestation 唯一、三个 controller
active、三个 MoveIt service/action ready、fresh domain/session、自然退出且 task-owned residue 为零。
VALID failure 中断序列；INVALID 终止批次并使用新 ID 重开。既有 READY 不计数。

- [ ] **Step 6: 提交与 checkpoint**

先在 submodule 提交 CMake 与其 scoped diff，再提交 parent gitlink、两个测试和 ledger。

```bash
git -C third_party/mujoco_ros2_control add -- mujoco_ros2_control/CMakeLists.txt
git -C third_party/mujoco_ros2_control diff --cached --check
git -C third_party/mujoco_ros2_control commit -m "fix(mujoco): close macOS vendor install rpath"
git add -- third_party/mujoco_ros2_control \
  src/so101_demo_py/config/mujoco/dependency-lock.yaml \
  src/so101_demo_py/config/dependency-lock.yaml \
  scripts/check_backend_integration.py \
  src/so101_demo_py/test/test_macos_install_contract.py \
  src/so101_demo_py/test/test_runtime_closure.py \
  docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md
git diff --cached --check
git commit -m "fix(so101): attest relocatable macOS station closure"
```

STOP at `CP-MSC-01` for Sol/high review。5/5 缺失时不进入 campaign live。

### Task 2: 实现不可变 selection 和 durable shared queue

**Files:**
- Create: `src/so101_demo_py/src/parallel_batch/selection.py`
- Create: `src/so101_demo_py/src/parallel_batch/queue.py`
- Create: `src/so101_demo_py/test/test_parallel_selection.py`
- Create: `src/so101_demo_py/test/test_parallel_point_queue.py`
- Modify: `src/so101_demo_py/src/parallel_batch/w2_composition.py`
- Modify: `src/so101_demo_py/test/test_macos_w2_campaign.py`

**Interfaces:**
- Consumes: Web catalog and runtime closure hash
- Produces: `FirstPassSelectionBinding`, `RetrySelectionBinding`, `DurablePointQueue`

```python
class DurablePointQueue:
    def lease_next(self, worker: WorkerIdentity) -> PointLease | None: ...
    def commit_result(self, lease: PointLease, result: CommittedResult) -> None: ...
```

- [ ] **Step 1: RED** — 覆盖 first-pass 4–20 点/四 anchors、retry 单个业务失败点、hash drift、
  两个 slot 排空 20 点、重复 lease、stale generation、crash recovery、unselected injection。

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_parallel_selection.py \
  src/so101_demo_py/test/test_parallel_point_queue.py \
  src/so101_demo_py/test/test_macos_w2_campaign.py \
  --junitxml="$RUN_ROOT/task2-red.xml"
```

Expected: 当前 first-two static assignment 使测试失败。

- [ ] **Step 2: GREEN** — `exact_w2_slots()` 只返回容量 slot；全部 selected ids 进入 fsync-backed
  queue。lease identity 固定为 campaign/batch/point/attempt/generation/worker。

- [ ] **Step 3: 提交**

```bash
git add -- src/so101_demo_py/src/parallel_batch/selection.py \
  src/so101_demo_py/src/parallel_batch/queue.py \
  src/so101_demo_py/src/parallel_batch/w2_composition.py \
  src/so101_demo_py/test/test_parallel_selection.py \
  src/so101_demo_py/test/test_parallel_point_queue.py \
  src/so101_demo_py/test/test_macos_w2_campaign.py
git diff --cached --check
git commit -m "feat(so101): bind selected points to a shared queue"
```

### Task 3: 每个 Worker lease 只执行一个点

**Files:**
- Create: `src/so101_demo_py/src/parallel_batch/single_point_input.py`
- Create: `src/so101_demo_py/test/test_single_point_input.py`
- Modify: `src/so101_demo_py/src/cli/macos_w2_campaign.py`
- Modify: `src/so101_demo_py/src/cli/macos_w2_worker.py`
- Modify: `src/so101_demo_py/src/parallel_batch/macos_w2_campaign.py`
- Modify: `src/so101_demo_py/test/test_macos_w2_campaign.py`

**Interfaces:**
- Consumes: `PointLease`, selection binding
- Produces: hash-bound `PointExecutionInput`, `PointExecutionResult`

- [ ] **Step 1: RED** — selection 包含 anchors 与 P09/P14/P20；断言所有 selected 各一次，
  unselected 为零，完整 `rgbd_task_points.yaml` 从不传给 Worker，retry 输入只含失败点。

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_single_point_input.py \
  src/so101_demo_py/test/test_macos_w2_campaign.py \
  src/so101_demo_py/test/test_parallel_batch_broker.py \
  src/so101_demo_py/test/test_mujoco_rgbd_batch_cli.py \
  --junitxml="$RUN_ROOT/task3-red.xml"
```

- [ ] **Step 2: GREEN** — 原子写单点文件并 fsync；Worker readback point/hash 后执行；broker
  request 使用同一 attempt id；station、MoveIt、物理、manifest、cleanup ownership 全部 durable
  后才提交业务 result。

- [ ] **Step 3: 提交** — scoped add 上述六个文件，`git diff --cached --check`，提交
  `feat(so101): execute one point per worker lease`。

### Task 4: 扩展 CoordinatorJournal committed watermark

**Files:**
- Modify: `src/so101_demo_py/src/parallel_batch/journal.py`
- Modify: `src/so101_demo_py/src/cli/macos_w2_campaign.py`
- Modify: `src/so101_demo_py/test/test_parallel_batch_journal.py`
- Modify: `src/so101_demo_py/test/test_macos_w2_campaign.py`

**Interfaces:**
- Produces: `CommittedWatermark`, `append_committed()`, `read_committed_prefix()`

- [ ] **Step 1: RED** — 覆盖 single writer、epoch takeover、idempotency、result fsync before
  proposal、journal fsync、watermark fsync/rename、ACK ordering、flush-before-fsync invisibility、
  watermark lag、partial tail、tamper、sequence gap、terminal append。

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_parallel_batch_journal.py \
  src/so101_demo_py/test/test_parallel_batch_crash_recovery.py \
  src/so101_demo_py/test/test_macos_w2_campaign.py \
  --junitxml="$RUN_ROOT/task4-red.xml"
```

- [ ] **Step 2: GREEN** — 保留 `read_only_replay()` strict 语义；live reader 只返回 watermark
  覆盖的 prefix。writer 退出后的多余 bytes 标记 `UNCONFIRMED_DURABILITY`，不自动 truncate/append。

- [ ] **Step 3: 提交** — scoped add 四个文件并提交
  `feat(so101): publish durable campaign watermarks`。

### Task 5: 建立唯一 reducer 和事务化 projection

**Files:**
- Create: `src/so101_teleop/so101_teleop/expert_validation/projection_source.py`
- Create: `src/so101_teleop/so101_teleop/expert_validation/reducer.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_reducer.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/coordinator_events.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/models.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/store.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/production.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_coordinator_events.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_store.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_production_projection.py`
- Modify: `src/so101_teleop/CMakeLists.txt`

**Interfaces:**
- Produces: `ProjectionSource.read_after()`, `CanonicalCampaignReducer.apply()`,
  `SupervisorStore.accept_projection_batch()`

- [ ] **Step 1: RED** — source 不能 merge `payload.delta`；验证四条正交状态轴、result-derived
  terminal、INVALID 不映射 FAILED、illegal append、identity drift。注入 reducer 后/cursor 前失败，
  要求全事务回滚；重启不重复统计 attempt。

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_teleop/test/teleop/test_expert_validation_coordinator_events.py \
  src/so101_teleop/test/teleop/test_expert_validation_reducer.py \
  src/so101_teleop/test/teleop/test_expert_validation_store.py \
  src/so101_teleop/test/teleop/test_expert_validation_production_projection.py \
  --junitxml="$RUN_ROOT/task5-red.xml"
```

- [ ] **Step 2: GREEN** — idempotency、reducer state、attempt、accepted cursor 在一个 SQLite
  transaction 更新。React/OpenAPI 仍只消费服务状态。

- [ ] **Step 3: 提交** — scoped add 上述文件并提交
  `feat(teleop): reduce committed campaign events transactionally`。

### Task 6: 持久化真实 owner tree 和 crash cleanup

**Files:**
- Create: `src/so101_teleop/so101_teleop/expert_validation/owner_tree.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_owner_tree.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/models.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/store.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/process_owner.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/supervisor.py`
- Modify: `src/so101_demo_py/src/cli/macos_service_campaign.py`
- Modify: `src/so101_demo_py/src/cli/macos_w2_worker.py`
- Modify: `src/so101_demo_py/src/parallel_batch/campaign_supervisor.py`
- Modify: `src/so101_demo_py/src/runtime/task_stack.py`
- Modify: `src/so101_demo_py/test/test_campaign_supervisor.py`
- Modify: `src/so101_demo_py/test/test_task_stack.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_process_owner.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_process_owner_integration.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_operator_recovery.py`
- Modify: `src/so101_teleop/CMakeLists.txt`

**Interfaces:**
- Produces: `OwnerIntent`, `ConfirmedOwnerProcess`, `OwnerTreeRecovery.recover_leaf_first()`

- [ ] **Step 1: RED** — adapter/campaign/worker/station `SIGKILL`、独立 session、PID reuse、
  unresolved intent、duplicate reaper、wrong generation receipt、station outside Worker PGID、
  crashes before/after `Popen` 与 confirmation。

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_campaign_supervisor.py \
  src/so101_demo_py/test/test_task_stack.py \
  src/so101_teleop/test/teleop/test_expert_validation_owner_tree.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner_integration.py \
  src/so101_teleop/test/teleop/test_expert_validation_operator_recovery.py \
  --junitxml="$RUN_ROOT/task6-red.xml"
```

- [ ] **Step 2: GREEN** — 每个真实 spawn 先 intent，后 readback confirmation；reaper 按
  station -> worker -> broker/campaign -> adapter 回收。未知 identity 不 signal，fence 保留。

- [ ] **Step 3: 提交与 checkpoint** — scoped add，提交
  `feat(teleop): recover macOS ownership leaf first`。Sol/high 在 `CP-MSC-02` 复核 Tasks 2–6。

### Task 7: 新增 v5/v6、W1 composition 和 per-spawn StartGuard

**Files:**
- Create: `src/so101_demo_py/config/mujoco/parallel_batch_v5_macos_mps_w1_retry.yaml`
- Create: `src/so101_demo_py/config/mujoco/parallel_batch_v6_macos_mps_w1_first_pass.yaml`
- Create: `src/so101_demo_py/src/parallel_batch/w1_composition.py`
- Create: `src/so101_demo_py/src/cli/macos_n1_first_pass.py`
- Create: `src/so101_demo_py/src/cli/macos_n1_retry.py`
- Create: `src/so101_demo_py/test/test_macos_w1_composition.py`
- Create: `src/so101_demo_py/test/test_macos_n1_cli.py`
- Modify: `src/so101_demo_py/src/parallel_batch/contracts.py`
- Modify: `src/so101_demo_py/src/parallel_batch/start_guard.py`
- Modify: `src/so101_demo_py/src/parallel_batch/start_guard_probe.py`
- Modify: `src/so101_demo_py/src/parallel_batch/w2_composition.py`
- Modify: `src/so101_demo_py/src/cli/macos_service_campaign.py`
- Modify: `src/so101_demo_py/src/cli/macos_w2_campaign.py`
- Modify: `src/so101_demo_py/src/cli/macos_w2_worker.py`
- Modify: `src/so101_demo_py/src/parallel_batch/campaign_supervisor.py`
- Modify: `src/so101_demo_py/setup.py`
- Modify: `src/so101_demo_py/test/test_parallel_batch_contracts.py`
- Modify: `src/so101_demo_py/test/test_parallel_start_guard_composition.py`
- Modify: `src/so101_demo_py/test/test_parallel_start_guard_probe.py`
- Modify: `src/so101_demo_py/test/test_macos_w2_campaign.py`
- Modify: `src/so101_demo_py/test/test_macos_install_contract.py`

**Interfaces:**
- Produces: `ParallelRuntimeConfigV5`, `ParallelRuntimeConfigV6`, `compose_w1_first_pass()`,
  `compose_w1_retry()`, exhaustive typed dispatch, fresh `GuardScope` per spawn epoch

- [ ] **Step 1: RED profile matrix** — freeze v4 bytes/SHA；v5 只接受 W1 retry，v6 只接受 W1
  first-pass；所有 cross-profile、N>2、adaptive、CPU fallback 和 point-count inference 拒绝。

- [ ] **Step 2: RED StartGuard spawn semantics** — campaign 与每个 Worker 使用不同 fresh epoch；
  旧 preflight result 不可重用。RAM/MPS FAIL 和 probe/identity error 不调用 `Popen`；CPU WARN 仍
  调用一次；同一 service 不可同时启动 W1/W2。public W2 CLI 即使已存在 PASS/FAIL
  `start-guard.json` 也必须 fresh probe；旧 epoch、不同 owner 或篡改文件都不能准入。guard 阶段
  到 broker 阶段的 `exec` 只接受本次进程创建的 inherited pipe 中一次性 result，消费后关闭；
  磁盘 JSON 只供审计。测试同时证明 broker 阶段开始前已通过 `exec` 清除 guard 阶段的 torch 导入。

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_parallel_batch_contracts.py \
  src/so101_demo_py/test/test_macos_w1_composition.py \
  src/so101_demo_py/test/test_macos_n1_cli.py \
  src/so101_demo_py/test/test_parallel_start_guard_composition.py \
  src/so101_demo_py/test/test_parallel_start_guard_probe.py \
  src/so101_demo_py/test/test_macos_w2_campaign.py \
  src/so101_demo_py/test/test_macos_install_contract.py \
  --junitxml="$RUN_ROOT/task7-red.xml"
```

- [ ] **Step 3: GREEN** — 共用 W1 primitive 只创建一套 slot/Worker/domain。把 StartGuard 源码中
  “仅 schema v4” 的限制收窄为“所有已批准的 Darwin/MPS v4/v5/v6 profile”，但保持 Linux v3
  不能携带 MPS headroom；不改变现有 probe、阈值和判定算法。扩展真实
  `load_execution_config_for_schema()` 和 host validation，使安装版 v5/v6 YAML 能沿 MPS 路径加载，
  且 W1 composition 复用这条入口。adapter 的 dispatch
  key 是 schema/profile/batch_kind/worker_count，不提供 generic `--batch-kind` fallback。guard
  绑定真实 owner birth 与 epoch。

- [ ] **Step 4: 提交** — scoped add 上述文件并提交
  `feat(so101): add closed macOS W1 profiles and spawn guards`。

### Task 8: 固定 macOS W1/W2 support matrix

**Files:**
- Modify: `src/so101_teleop/so101_teleop/expert_validation/preflight.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/api.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/production.py`
- Modify: `src/so101_teleop/so101_teleop/unified/app.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_api.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_preflight.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_start_guard.py`
- Modify: `src/so101_teleop/test/teleop/test_unified_guard_document.py`

**Interfaces:**
- Produces: platform-bound capabilities with W1/W2 only; stable `UNSUPPORTED_ON_MACOS` reasons

- [ ] **Step 1: RED** — macOS capabilities 只允许 `SEQUENTIAL/W1` 和 `PARALLEL/W2`；N3–N8
  不可选且没有 profile/qualification hash；API/preflight 对 N>2 与 ADAPTIVE 拒绝；点数变化不改
  worker profile。分别从安装版 v4/v5/v6 YAML 发起 service preflight，要求三者都使用实际
  profile/config hash、W1/W2 scope 和 MPS probe，且不进入 CUDA/NVML；Linux v3/v4 fixture 保持
  原语义。`_LazyStartGuard` 可按 `(profile, config_sha256, accelerator, selector)` 缓存 composition，
  但每个 request/spawn epoch 都必须 fresh probe，不能缓存 verdict。

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_teleop/test/teleop/test_expert_validation_api.py \
  src/so101_teleop/test/teleop/test_expert_validation_preflight.py \
  src/so101_teleop/test/teleop/test_expert_validation_start_guard.py \
  src/so101_teleop/test/teleop/test_unified_guard_document.py \
  --junitxml="$RUN_ROOT/task8-red.xml"
```

- [ ] **Step 2: GREEN** — `_HostResourceProbe` 继续只调用 StartGuard；删除 macOS capabilities
  对 budget/qualification source 的依赖，不改变 Linux adapter。StartGuard policy/status 仍可展示，
  文案明确它不是资格证明。

- [ ] **Step 3: 提交** — scoped add 八个文件并提交
  `feat(teleop): limit macOS validation to W1 and W2`。

### Task 9: 候选/生产执行 context 与原子 retry admission

**Files:**
- Create: `src/so101_teleop/so101_teleop/expert_validation/execution_context.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_execution_context.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/api.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/models.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/store.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/statistics.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/supervisor.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/production.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/service.py`
- Modify (generated): `src/so101_teleop/so101_teleop/expert_validation_openapi.json`
- Modify (generated): `src/so101_teleop/web/src/api/expert-validation-schema.d.ts`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_store.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_statistics.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_supervisor.py`
- Modify: `src/so101_teleop/CMakeLists.txt`

**Interfaces:**
- Produces: `CandidateExecutionContext`, `ProductionExecutionContext`, `RetryStartRequest`,
  `SupervisorStore.admit_retry()`

```python
class SupervisorStore:
    def admit_retry(
        self,
        *,
        request: RetryStartRequest,
        context: CandidateExecutionContext | ProductionExecutionContext,
        spawn_intent: OwnerIntent,
    ) -> RetrySelectionBinding: ...
```

- [ ] **Step 1: RED** — context 类型混用、过期、replay、profile/config/closure/N/batch/root/
  lease drift；非业务失败；原 batch 非 terminal-clean；active/unknown owner；fence；重复 command；
  transaction 后 spawn fail。

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_teleop/test/teleop/test_expert_validation_execution_context.py \
  src/so101_teleop/test/teleop/test_expert_validation_store.py \
  src/so101_teleop/test/teleop/test_expert_validation_statistics.py \
  src/so101_teleop/test/teleop/test_expert_validation_supervisor.py \
  --junitxml="$RUN_ROOT/task9-red.xml"
```

- [ ] **Step 2: GREEN** — context 不含预算/资格/promotion 字段。一个 transaction 内消费
  command、验证 result/lease/cleanup/fence、创建 retry binding、写 spawn intent。retry 只追加历史。

- [ ] **Step 3: OpenAPI 生成与提交**

```bash
$TEST_PYTHON -m so101_teleop.openapi_export --validation \
  src/so101_teleop/so101_teleop/expert_validation_openapi.json
cd src/so101_teleop/web
bun run generate:api:validation
cd ../../../
```

stage 本 task 列出的产品、测试、生成 OpenAPI/types，`git diff --cached --check`，提交
`feat(teleop): authorize one-time macOS retries`。

STOP at `CP-MSC-03`；Sol/high 复核 v4/v5/v6、W1/W2 matrix、fresh guard 和 retry atomicity。

### Task 10: 更新 Web 为 W1/W2，并补浏览器合同

**Files:**
- Modify: `src/so101_teleop/web/src/components/expert-validation/campaign-setup.tsx`
- Modify: `src/so101_teleop/web/src/components/expert-validation/components.test.tsx`
- Modify: `src/so101_teleop/web/src/expert-validation-app.tsx`
- Modify: `src/so101_teleop/web/src/expert-validation-app.test.tsx`
- Modify: `src/so101_teleop/web/src/api/live-evidence.test.ts`
- Create: `src/so101_teleop/web/src/api/campaign-live-evidence.test.ts`
- Modify: `src/so101_teleop/web/e2e/expert-validation/assertions/live-evidence.ts`
- Modify: `src/so101_teleop/web/e2e/expert-validation/live-sim/02-parallel.spec.ts`
- Modify: `src/so101_teleop/web/e2e/expert-validation/live-sim/04-start-guard.spec.ts`
- Modify: `src/so101_teleop/web/e2e/expert-validation/live-sim/06-fixed-n-execution.spec.ts`
- Modify: `src/so101_teleop/web/e2e/expert-validation/live-sim/07-retry-full-restart.spec.ts`

**Interfaces:**
- Consumes: platform capabilities、StartGuard status、canonical campaign projection
- Produces: W1/W2-only selector、N>2 disabled reasons、W2/W1/retry evidence assertions

- [ ] **Step 1: RED** — macOS UI 只可选 W1/W2；N3–N8 显示
  `UNSUPPORTED_ON_MACOS`；不读取 qualification view 决定可选性；点数不改变 profile；StartGuard
  RAM/MPS FAIL 与 CPU WARN 文案正确。

```bash
cd src/so101_teleop/web
bun run test -- src/components/expert-validation/components.test.tsx
bun run test -- src/expert-validation-app.test.tsx
bun run test -- src/api/live-evidence.test.ts
bun run test -- src/api/campaign-live-evidence.test.ts
```

- [ ] **Step 2: GREEN** — UI 只依据 capabilities support matrix 和 preflight guard；不实现平台
  reducer。W2、W1、retry assertions 校验 selected-only、sequence/watermark、物理证据和 cleanup。

- [ ] **Step 3: Web gate 与提交**

```bash
bunx tsc -b --pretty false
bun run test
bun run build
cd ../../../
```

stage 上述十一个文件，`git diff --cached --check`，提交
`feat(web): expose macOS W1 and W2 execution only`。

### Task 11: Offline package gate 与候选 live gate

**Files:**
- Modify: `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md`
- Evidence only: registered evidence root

**Interfaces:**
- Consumes: frozen copied install and one-time `CandidateExecutionContext`
- Produces: offline gate evidence、bounded W2/W1/retry candidate evidence、`CP-MSC-04`

- [ ] **Step 1: 冻结候选 bytes** — 记录 HEAD/submodule、copied install inventory、v4/v5/v6
  hash、catalog/model/parser/reducer/StartGuard bytes 和 executable origins。之后 product edit 使本批
  live evidence 失效。

- [ ] **Step 2: 运行 package gate** — 定向测试之后运行以下精确命令。普通 Python gate 只收集
  `test/`，不会进入 `benchmark_test/`。保存非零 collection、JUnit/CTest、exit code、elapsed 和
  import origin。

```bash
$TEST_PYTHON -m pytest -p no:cacheprovider src/so101_demo_py/test -q \
  --junitxml="$RUN_ROOT/task11-so101-demo-py.xml"
$TEST_PYTHON -m pytest -p no:cacheprovider src/so101_teleop/test/teleop -q \
  --junitxml="$RUN_ROOT/task11-so101-teleop.xml"
colcon test --packages-select so101_teleop --event-handlers console_direct+
colcon test-result --verbose
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_copied_installed_entrypoint.py \
  src/so101_demo_py/test/test_macos_install_contract.py \
  --junitxml="$RUN_ROOT/task11-copied-install.xml"
cd src/so101_teleop/web
bunx tsc -b --pretty false
bun run test
bun run build
cd ../../../
```

- [ ] **Step 3: 候选 W2** — 一次性 candidate context，v4，包含非前两点的 4–20 点 selection。
  要求两个 Worker/station，全部 selected 各一次，unselected 零，StartGuard campaign+两 Worker
  fresh，journal/projection/物理/cleanup 一致。

- [ ] **Step 4: 候选 W1 first-pass** — v6、一个 Worker、同一完整 selection 顺序执行；fresh
  campaign/Worker guard；无 retry 语义。

- [ ] **Step 5: 候选 retry** — 先以 fault injection 验证拒绝分类，且不计业务成功。正式候选
  retry 必须使用一个 terminal-clean 的真实业务 `FAILED` point、v5、fresh FULL_RESTART，只执行
  指定点一次。

- [ ] **Step 6: checkpoint** — 任何 guard FAIL、unknown owner、projection mismatch、物理证据
  不完整或 cleanup residue 都停止，不自动循环。Sol/high 审查 `CP-MSC-04`。

### Task 12: 安装版 production + fresh Chrome 验收

**Files:**
- Modify: `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md`
- Evidence only: registered evidence root

**Interfaces:**
- Consumes: copied install、`ProductionExecutionContext`、exclusive control lease
- Produces: fresh Chrome W2/W1/retry acceptance、`CP-MSC-05`

- [ ] **Step 1: 独占窗口 preflight** — 回读 service/port/lease/owner/process；foreign service
  存在则停止，不 kill。production context 必须绑定当前 copied install、profile/config、batch、
  service session、lease generation、owner generation、command 和 expiry。

- [ ] **Step 2: W2 first-pass** — fresh Chrome profile 发起 v4 W2，校验 API/WebSocket、两 Worker、
  selected-only attempts、controller/joint/TF、MuJoCo pose/contact/release、MoveIt shadow/world、
  journal/watermark、evidence manifest 和 exact cleanup。

- [ ] **Step 3: W1 first-pass** — fresh Chrome 发起 v6 W1，校验一个 Worker 顺序执行，点数不
  改 profile，业务/物理/projection/cleanup 一致。

- [ ] **Step 4: W1 retry** — 从当前 production first-pass 中选择 terminal-clean 真实业务
  `FAILED`，使用新 command/lease-bound context 发起 v5 retry；只有该点执行一次，first-pass
  result/statistics 不变。

- [ ] **Step 5: Playwright projects**

```bash
cd src/so101_teleop/web
test "$SO101_ENABLE_LIVE_SIM_E2E" = "1"
test -n "$SO101_LIVE_SIM_HOST"
test -n "$SO101_E2E_EVIDENCE_ROOT"
test -n "$SO101_E2E_INSTALL_PREFIX"
test -n "$SO101_LIVE_SERVICE_BASE_URL"
test -n "$SO101_LIVE_SERVICE_STATE_ROOT"
test -f "$SO101_UNIFIED_LIVE_AUTHORIZATION"
test -x "$SO101_E2E_PYTHON"
test -f "$SO101_FUNCTIONAL_MANIFEST"
test -x "$SO101_PLAYWRIGHT_CHROME"
bun run test:e2e:live-sim --project parallel-resource
bun run test:e2e:live-sim --project fixed-n-execution
bun run test:e2e:live-sim --project retry-full-restart
cd ../../../
```

环境文件必须绑定当前服务 PID/birth、lease、context、deadline 与 evidence root；变量存在本身
不授予权限。Expected: 三个 project PASS，fresh browser 与 raw evidence 同 run identity。

- [ ] **Step 6: checkpoint** — 记录 `CP-MSC-05`，再次读回 task-owned process、ROS nodes、
  broker、IPC、ports 和 cleanup receipt；foreign process 保留并列出。

### Task 13: 最终 package gate、guide、独立审查和本地交接

**Files:**
- Modify: `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md`
- Create: `docs/guides/so101-macos-service-campaign-closure.md`

**Interfaces:**
- Consumes: all RED/GREEN/package/live evidence
- Produces: `CP-MSC-FINAL`、operator guide、scoped local commit；无发布

- [ ] **Step 1: 最终 gate** — 使用新的 JUnit 文件名重跑完整静态 gate，并读取 HEAD/submodule、
  closure、v4/v5/v6、owner tree、guard、journal、IPC 和 residue。

```bash
$TEST_PYTHON -m pytest -p no:cacheprovider src/so101_demo_py/test -q \
  --junitxml="$RUN_ROOT/task13-so101-demo-py.xml"
$TEST_PYTHON -m pytest -p no:cacheprovider src/so101_teleop/test/teleop -q \
  --junitxml="$RUN_ROOT/task13-so101-teleop.xml"
colcon test --packages-select so101_teleop --event-handlers console_direct+
colcon test-result --verbose
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_copied_installed_entrypoint.py \
  src/so101_demo_py/test/test_macos_install_contract.py \
  --junitxml="$RUN_ROOT/task13-copied-install.xml"
cd src/so101_teleop/web
bunx tsc -b --pretty false
bun run test
bun run build
cd ../../../
```

- [ ] **Step 2: Sol/high 结果审查** — 对照设计完成定义；finding 返回 owning task，受影响 live
  证据失效。审查报告必须写明没有 resource qualification/capacity certification。

- [ ] **Step 3: ledger accounting** — 分别列 retained、archived 和 deletion candidates；不移动、
  不删除。任何未通过层写出下一条精确命令。

- [ ] **Step 4: Sol/high 编写 guide** — 使用 `$humanizer-zh`，记录 v4-W2、v6-W1、v5-retry
  选择，StartGuard 语义，N>2 拒绝，lease/context 前置，证据路径和恢复 checkpoint。明确
  `so101_measure_parallel_resources` 仍 retired，且系统没有 macOS 容量资格流程。

- [ ] **Step 5: Astra/high 独立终审** — 审查 scoped code、设计、计划、guide、ledger 和 production
  evidence。P0/P1/P2 finding 返回 owning task；未通过前不得标记 FINAL PASS。

- [ ] **Step 6: 本地提交**

```bash
git add -- docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md \
  docs/guides/so101-macos-service-campaign-closure.md
git diff --cached --check
git commit -m "docs: record macOS W1 W2 service closure"
```

不 push、不 merge。最终交接报告 branch、local HEAD、证据分类和未发布状态。

## Checkpoints

| Checkpoint | 必须满足 | 不满足时 |
| --- | --- | --- |
| legacy `CP-MSC-A` | 只作恢复锚点；结论 `UNCONFIRMED` | 不得解释为 PASS |
| `CP-MSC-R0` | 三个恢复提交、ledger、evidence root、writer ownership 已回读 | 停止，不重建第二套环境 |
| `CP-MSC-01` | rpath 根因 RED->GREEN；无临时 DYLD 依赖；station 5/5 | 不进入 campaign live |
| `CP-MSC-02` | selection/queue/single-point/watermark/reducer/owner tree 离线通过 | 返回 Tasks 2–6 |
| `CP-MSC-03` | v4 frozen；v5/v6 closed；W1/W2 only；fresh guard；retry atomic | 返回 Tasks 7–9 |
| `CP-MSC-04` | package gate 和 bounded candidate W2/W1/retry 有效且无残留 | 不进 production Chrome |
| `CP-MSC-05` | fresh Chrome W2/W1/retry 与 raw/physical/cleanup 一致 | 返回 owning task |
| `CP-MSC-FINAL` | Sol/high 与 Astra/high 审查通过，guide/ledger 完整 | 只报告 PARTIAL |

## 计划自查

- 设计 §5 对应 Task 1，保留现有 READY 事实但不假定 Gate A 已通过；rpath 文件和 RED/GREEN
  判据明确，不再强制 controller C++ 修改。
- 设计 §6–8 对应 Tasks 2、3、7、8；v4/v5/v6、W1/W2、point/profile 分离完整。
- 设计 §7 对应 Tasks 7–8；只复用现有 StartGuard，没有新 sampler/watchdog/容量证明。
- 设计 §9 对应 Tasks 4–5；committed watermark、唯一 reducer 和 cursor transaction 有明确测试。
- 设计 §10 对应 Task 9；candidate/production execution context 不含预算授权，retry 保留一次性
  command/lease 与真实 FAILED/terminal-clean 门禁。
- 设计 §11 对应 Task 6；真实 spawn intent、PID/birth、leaf-first cleanup 和 fence 均覆盖。
- fresh Chrome W2/W1/retry 对应 Tasks 10–12；最终声明边界由 Task 13 固定。
- 计划没有已删除资源子系统的 task、文件、命令、测试或 checkpoint，也不修改旧预算文档。
- 文件路径、接口、测试命令、预期结果和 scoped commits 均已给出；没有占位步骤或不确定路径，
  也不会自动 push/merge。
