# SO-101 macOS service campaign 闭环实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 根据仓库执行器规则，实际实现只能由 mac-mini 上 tmux 持有的 DeepSeek Harness TUI（`dst`）inline 执行；每个 checkpoint 由 GPT-5.6 Sol / High 复核，设计、计划和 guide 的独立审查使用 GPT-6 Astra / High。

**Goal:** 在 macOS MuJoCo 仿真上闭合统一 Web 服务的 W2 first-pass、W1 first-pass 与单点 `FULL_RESTART_RETRY`，建立可恢复投影、完整进程所有权和 Darwin N1/N2 版本化资源资格，并在获批生产上下文后完成 fresh Chrome 验收。

**Architecture:** 保留 schema v4 exact-W2 和现有轻量 MPS start guard；新增不可变 selection/catalog 绑定、共享点位队列、schema v5/v6 typed W1 入口，以及基于现有 `CoordinatorJournal` committed watermark 的唯一 reducer。运行闭包拆成稳定 `RuntimeClosureIdentity`、单次 `RunBinding` 和启动后 `RuntimeAttestation`；资源链通过新的 macOS measurement CLI 重建 B/Q/P/M/D，旧 `so101_measure_parallel_resources` 继续只返回 `MEASUREMENT_ENTRY_RETIRED`。

**Tech Stack:** Python 3.11、SQLite、ROS 2 Jazzy、MoveIt 2、ros2_control、MuJoCo、PyTorch MPS、AF_UNIX、Swift `DispatchSourceMemoryPressure` helper、FastAPI/Pydantic、React/TypeScript、Bun、Vitest、Playwright、pytest、colcon/CMake/gtest。

**Spec:** [SO-101 macOS service campaign 闭环设计](../specs/2026-09-21-so101-macos-service-campaign-closure-design.md)，实现基线提交 `6d5069026fbd322076f58d0d4b9504891abeb861`，设计文件 SHA-256 `0a5f5e0d8006016fb778d186f7029247b7fe828f0e1efaea34e4e96b00480015`。实施前完整阅读设计与本计划；设计批准不等于代码、仿真、资格或生产验收通过。

## Global Constraints

- 本计划编写只产生这一份文档。编写阶段不启动服务、ROS graph、仿真、浏览器、measurement、MPS 模型或真实硬件，不运行测试，也不修改代码、设计、账本或历史证据。
- 实施从 mac-mini 现有分支 `codex/so101-unified-webapp` 的最新已核验 HEAD 开始。执行器先回读 worktree、branch、HEAD、upstream、submodule 和 dirty files；不覆盖、stash、reset、clean 或夹带用户改动。
- 唯一实现执行器是新建 tmux session 中的 `dst`。执行器直接运行在 mac-mini，不得把 mac-mini 任务误投到 ai-station，也不得启动第二个 coding agent、第二个 worktree writer 或第二套服务。
- 本计划不授权真实机械臂、sudo、系统/全局 Python 或 shell 配置修改、停止 foreign 进程、删除证据、归档证据、promotion、operator approval、push、merge、force push 或发布。到达相应边界时停止并请求单独授权。
- 实现期间建立一个单写账本 `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md`。每次实验先写 `PLANNED`，再运行；每个 checkpoint 先更新账本，再汇报 tmux 状态。
- macOS 普通日志、截图、构建和测试证据放在 `mktemp -d /tmp/so101-debug-macos-service-campaign-closure.XXXXXXXX` 创建的本任务唯一目录。Stage C 的 50/25 ms 原始采样和必须长期保留的资格证据只能放在实施当日创建并登记的 `/data/work/so101-evidence/macos-service-campaign-closure/` 下；末级目录名必须是现场生成并立即冻结的 UTC 基本时间戳、短横线和 UUID。若 mac-mini 没有可写 `/data/work/so101-evidence`，在首次高频采样前停止并请求存储决策，不得改用第二个 `/tmp` 根或源码目录。macOS 不套用 ai-station 的 NVMe pytest scratch 规则。
- 全任务只登记一个证据根；从普通调试切换到 durable Stage C 前，按 `experiment-ledger.md` 的迁移规则保存 source-to-target 清单、相对路径、SHA256、大小与数量并更新 tracked root。旧根只列 archived/deletion candidate，未授权不移动或删除。
- 每个测试调用使用证据根下此前不存在的子目录，设置 task-local `ROS_HOME`、`ROS_LOG_DIR`、`TMPDIR`、`TMP`、`TEMP`，保存 argv、stdout/stderr、退出码、elapsed、JUnit/CTest 和 module origin。依赖导入失败、DYLD bootstrap 失败或零收集不算 RED。
- 所有产品修改严格 RED -> GREEN。定向测试先行；随后运行受影响 package gate、copied-install/provenance gate。普通 `so101_demo_py` gate 不收集 `benchmark_test/`；Web 只用 Bun 与 `bun.lock`。
- schema v4 的 bytes 与 Linux/CUDA/EGL、Darwin/MPS/CGL 两个闭合组合保持不变。v5 只服务 Darwin/MPS W1 `FULL_RESTART_RETRY`；v6 只服务 Darwin/MPS W1 ordinary first pass。
- `PointStatus` 仍只有 `UNRUN/PASSED/FAILED/INDETERMINATE`。`RUNNING` 属于 execution phase，`INVALID` 属于 attempt validity；不得扩充 point enum 来绕过 reducer 设计。
- 旧 console script `so101_measure_parallel_resources` 和 `measure_parallel_resources.py` 保持退役，退出码 `2`、错误 `MEASUREMENT_ENTRY_RETIRED` 不变。新入口固定为 `so101_measure_macos_resources`，不复用旧命令名。
- Candidate measurement 和 production 是互斥上下文。candidate 不读取尚未生成的 P/Q/M/D；production 没有 matching P/Q/R/M/D 与 `RetryQualification` 时拒绝。fault 只进入安全包络，不计 normal/product 成功分母。
- 任何执行代码、config、selection/queue/reducer 语义、模型、closure inventory 或 parser 变化都生成新 execution identity R，并使此前相关 B/Q/P/M/D 与 retry qualification 失效。
- 每个 task 只 stage 自己列出的文件，运行 `git diff --check` 和 scoped diff readback 后提交。不得用 `git add -A`；不得将证据、构建产物、截图、数据库或临时授权文件提交到仓库。

## 文件与接口总图

| 边界 | 文件与职责 |
| --- | --- |
| station 诊断/闭包 | 新 `src/so101_demo_py/src/runtime/runtime_closure.py`、新 `src/so101_demo_py/src/cli/diagnose_macos_station.py`；修改 `cli/motion_stack_ready.py`、`runtime/task_stack.py`、`setup.py` |
| hardware phase | A/B 后只允许修改 `mujoco_ros2_control_node.cpp`、`macos_ui_dispatcher.cpp`、`macos_ui_dispatcher.hpp`、`mujoco_system_interface.cpp`、`mujoco_system_interface.hpp` 的证据确认子集；固定新增 `tests/test_macos_controller_startup.cpp` 并修改 submodule `CMakeLists.txt` |
| selection/queue | 新 `parallel_batch/selection.py`、`parallel_batch/queue.py`；修改 `w2_composition.py`、`cli/macos_w2_campaign.py`、`cli/macos_w2_worker.py` |
| journal/projection | 修改 `parallel_batch/journal.py`；新 `expert_validation/reducer.py`、`projection_source.py`；修改 `coordinator_events.py`、`models.py`、`store.py`、`production.py` |
| ownership | 新 `expert_validation/owner_tree.py`；修改 `process_owner.py`、`store.py`、`supervisor.py`、`cli/macos_service_campaign.py` |
| W1/retry | 新 `parallel_batch/w1_composition.py`、`cli/macos_n1_first_pass.py`、`cli/macos_n1_retry.py`、`expert_validation/retry_context.py`；修改 contracts/config/setup/supervisor/API |
| Darwin measurement | 新 `parallel_batch/measurement_authority.py`、`darwin_resource_sampler.py`、`resource_measurement.py`、`resource_budget.py`、`cli/measure_macos_resources.py`、`assets/macos/memory_pressure.swift` |
| OpenAPI/Web | 修改 expert-validation API/export/generated types，现有 campaign setup/progress/evidence 与 live-sim Playwright files；不加入平台专用 reducer |
| 持久文档 | 修改 2026-09-18 budget design/plan 的 Darwin/v5/v6 边界，新建 task ledger；不改写 2026-09-19 历史结论 |

---

### Task 0: 接管执行环境、登记证据和冻结基线

**Files:**
- Create: `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md`
- Evidence only: task-owned evidence root; no product source edits

**Interfaces:**
- Consumes: immutable design commit `6d5069026fbd322076f58d0d4b9504891abeb861`
- Produces: one ledger writer, frozen baseline manifest, registered evidence root, checkpoint `CP-MSC-000`

- [ ] **Step 1: Read the required instructions and freeze the actual checkout**

Read `AGENTS.md`, `.agents/skills/so101-dev/SKILL.md` and its relevant references, the design, this plan, the 2026-09-18 budget design/plan and 2026-09-19 MPS design/plan. Record SHA256, `hostname`, `pwd`, branch, HEAD, upstream, `git status --short`, `git diff --submodule=log`, `git submodule status`, tmux sessions, relevant processes and listening ports. Expected: mac-mini target is explicit; any unexpected writer or dirty overlap is a STOP, not an invitation to clean it.

- [ ] **Step 2: Create the single ledger and evidence registration**

Create the header with fixed `task_id: so101-macos-service-campaign-closure`, goal “close service-driven macOS W2, W1 and single-point retry with qualified N1/N2 budgets”, and success contract “design section 14, with candidate and production evidence kept separate”. Copy the absolute worktree, current commit and newly created evidence root verbatim from Step 1; set branch to the read-back branch, base commit to `6d5069026fbd322076f58d0d4b9504891abeb861`, empty confirmed/disproven lists, open hypothesis “controller-manager first bad boundary is not yet confirmed”, checkpoint `CP-MSC-000`, and next experiment `EXP-MSC-001`. Do not leave angle-bracket template text in the ledger.

Create the ordinary macOS evidence root exactly once and freeze the interpreter before any test command. Run these commands from the repository root; do not reuse either path from another task:

```bash
RUN_ROOT="$(mktemp -d /tmp/so101-debug-macos-service-campaign-closure.XXXXXXXX)"
TEST_PYTHON="$(command -v python3)"
test -n "$TEST_PYTHON"
test -x "$TEST_PYTHON"
mkdir -p "$RUN_ROOT/ros_home" "$RUN_ROOT/ros_log" "$RUN_ROOT/tmp"
export RUN_ROOT TEST_PYTHON
export ROS_HOME="$RUN_ROOT/ros_home"
export ROS_LOG_DIR="$RUN_ROOT/ros_log"
export TMPDIR="$RUN_ROOT/tmp"
export TMP="$RUN_ROOT/tmp"
export TEMP="$RUN_ROOT/tmp"
"$TEST_PYTHON" -c 'import os, pathlib, sys, tempfile; root=pathlib.Path(os.environ["RUN_ROOT"]).resolve(); tmp=pathlib.Path(tempfile.gettempdir()).resolve(); assert tmp == root / "tmp", (root, tmp); print(sys.executable); print(tmp)'
```

Record `RUN_ROOT`, `TEST_PYTHON`, `sys.executable`, `tempfile.gettempdir()` and their read-back results in the ledger. A shell restart, tmux reattach or executor handoff must reload these exact frozen values from the ledger and repeat the assertions; it must not silently create a second task root.

- [ ] **Step 3: Run read-only baseline collection**

Collect, but do not start services: the exact Python executable and origins of `rclpy`, `so101_demo`, `so101_teleop`; current v4 YAML SHA; retired measurement output; package test collection counts. Run the retired CLI only after a copied/source import environment is proven and expect exit `2` with `MEASUREMENT_ENTRY_RETIRED`; this is a fail-closed contract check, not measurement.

- [ ] **Step 4: Commit the baseline checkpoint**

```bash
git add docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md
git diff --cached --check
git commit -m "chore(so101): checkpoint macOS service closure start"
```

Expected: only the new ledger is committed. Stop after commit for Sol/high readback of checkout ownership and evidence registration.

## Gate A: controller 与 runtime closure

### Task 1: 定义 runtime closure、run binding 和 attestation

**Files:**
- Create: `src/so101_demo_py/src/runtime/runtime_closure.py`
- Create: `src/so101_demo_py/test/test_runtime_closure.py`
- Modify: `src/so101_demo_py/src/runtime/task_stack.py`
- Modify: `src/so101_demo_py/setup.py`

**Interfaces:**
- Consumes: copied-install inventory and `OwnedProcessIdentity`
- Produces: `RuntimeClosureIdentity`, `RunBinding`, `RuntimeAttestation`, `verify_runtime_closure(...)`

```python
@dataclass(frozen=True, slots=True)
class RuntimeClosureIdentity:
    source_commit: str
    mujoco_ros2_control_commit: str
    install_inventory_sha256: str
    executable_inventory: tuple[FileDigest, ...]
    library_inventory: tuple[FileDigest, ...]
    config_inventory: tuple[FileDigest, ...]
    normalized_environment_sha256: str

@dataclass(frozen=True, slots=True)
class RunBinding:
    campaign_id: str
    batch_id: str
    ros_domain_id: int
    station_session_id: str
    evidence_root: Path
    owner_generation: int
    started_monotonic_ns: int

@dataclass(frozen=True, slots=True)
class RuntimeAttestation:
    closure_sha256: str
    run_binding_sha256: str
    process_identities: tuple[OwnedProcessIdentity, ...]
    loaded_images: tuple[FileDigest, ...]
    observed_ros_domain_id: int
```

- [ ] **Step 1: Write RED tests**

Cover stable closure hash across fresh domain/session/evidence roots; distinct run and attestation hashes; relative installed inventory; ABI/library origin mismatch; config drift; canonical checkout prefix contamination; missing submodule commit; loaded image outside copied install; symlink and replacement races. Run:

```bash
$TEST_PYTHON -m pytest -q src/so101_demo_py/test/test_runtime_closure.py \
  --junitxml="$RUN_ROOT/task1-red.xml"
```

Expected: collection succeeds and fails because `runtime_closure` is absent.

- [ ] **Step 2: Implement the minimal closed models and safe readers**

Use fd-based regular-file checks, canonical relative paths and SHA256 inventories. Do not include `ROS_DOMAIN_ID`, session id, evidence path or timestamps in `RuntimeClosureIdentity`. `PersistentTaskStack.start()` must verify the expected closure before spawn and produce attestation only after each child identity and loaded image path can be read back.

- [ ] **Step 3: Run GREEN and adjacent ownership tests**

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_runtime_closure.py \
  src/so101_demo_py/test/test_task_stack.py \
  --junitxml="$RUN_ROOT/task1-green.xml"
```

Expected: PASS, nonzero collection, no process starts in unit tests.

- [ ] **Step 4: Commit**

```bash
git add src/so101_demo_py/src/runtime/runtime_closure.py \
  src/so101_demo_py/src/runtime/task_stack.py \
  src/so101_demo_py/test/test_runtime_closure.py src/so101_demo_py/setup.py
git diff --cached --check
git commit -m "feat(so101): attest macOS task runtime closure"
```

### Task 2: 分离 controller 直连查询和 MoveIt 聚合 readiness

**Files:**
- Create: `src/so101_demo_py/src/cli/diagnose_macos_station.py`
- Create: `src/so101_demo_py/test/test_diagnose_macos_station.py`
- Modify: `src/so101_demo_py/src/cli/motion_stack_ready.py`
- Modify: `src/so101_demo_py/test/test_motion_stack_ready.py`
- Modify: `src/so101_demo_py/setup.py`

**Interfaces:**
- Consumes: `RuntimeClosureIdentity`, `RunBinding`
- Produces: `StationPhase`, `DirectControllerObservation`, `StationDiagnosticReport`; console `so101_diagnose_macos_station`

```python
class StationPhase(StrEnum):
    PLUGIN_RESOLVED = "PLUGIN_RESOLVED"
    SIMULATION_ENDPOINT_READY = "SIMULATION_ENDPOINT_READY"
    HARDWARE_INITIALIZING = "HARDWARE_INITIALIZING"
    HARDWARE_READY = "HARDWARE_READY"
    CONTROLLER_MANAGER_SERVICES_READY = "CONTROLLER_MANAGER_SERVICES_READY"
    CONTROLLERS_ACTIVE = "CONTROLLERS_ACTIVE"

@dataclass(frozen=True, slots=True)
class DirectControllerObservation:
    service_visible: bool
    call_completed: bool
    controllers: Mapping[str, str]
    ros_domain_id: int
    observed_monotonic_ns: int
```

- [ ] **Step 1: Write RED tests for the first observable boundary**

Tests must prove controller querying starts as soon as `/controller_manager/list_controllers` is visible and is not gated by all MoveIt services/actions; only one async request is in flight; direct service timeout, DDS invisibility and MoveIt missing have different failure codes. The diagnostic has closed modes `MINIMAL_CONTROLLER_MANAGER` and `ROBOT_SYSTEM_CONTROLLER_MANAGER` and rejects arbitrary launch argv.

- [ ] **Step 2: Run RED**

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_motion_stack_ready.py \
  src/so101_demo_py/test/test_diagnose_macos_station.py \
  --junitxml="$RUN_ROOT/task2-red.xml"
```

Expected: new test fails because direct controller polling/mode types do not exist; old readiness assertions remain collected.

- [ ] **Step 3: Implement independent controller polling and diagnostic records**

`motion_stack_ready` still requires all three active controllers plus the three MoveIt services and actions for final READY. The only semantic change is diagnostic ordering: controller traffic no longer waits behind MoveIt. The diagnostic records server PID/birth, loaded images, ROS domain, direct call result, node/service graph and phase deadlines; it never declares root cause from one observation.

- [ ] **Step 4: Run GREEN and commit**

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_motion_stack_ready.py \
  src/so101_demo_py/test/test_diagnose_macos_station.py \
  --junitxml="$RUN_ROOT/task2-green.xml"
git add src/so101_demo_py/src/cli/diagnose_macos_station.py \
  src/so101_demo_py/src/cli/motion_stack_ready.py \
  src/so101_demo_py/test/test_diagnose_macos_station.py \
  src/so101_demo_py/test/test_motion_stack_ready.py src/so101_demo_py/setup.py
git diff --cached --check
git commit -m "feat(so101): separate controller and MoveIt readiness evidence"
```

### Task 3: Gate A — controller-manager A/B、根因修复和五次 readiness

**Files:**
- Allowed modify set after A/B confirmation: `third_party/mujoco_ros2_control/mujoco_ros2_control/src/mujoco_ros2_control_node.cpp`
- Allowed modify set after A/B confirmation: `third_party/mujoco_ros2_control/mujoco_ros2_control/src/macos_ui_dispatcher.cpp`
- Allowed modify set after A/B confirmation: `third_party/mujoco_ros2_control/mujoco_ros2_control/include/mujoco_ros2_control/macos_ui_dispatcher.hpp`
- Allowed modify set after A/B confirmation: `third_party/mujoco_ros2_control/mujoco_ros2_control/src/mujoco_system_interface.cpp`
- Allowed modify set after A/B confirmation: `third_party/mujoco_ros2_control/mujoco_ros2_control/include/mujoco_ros2_control/mujoco_system_interface.hpp`
- Create after A/B confirmation: `third_party/mujoco_ros2_control/mujoco_ros2_control/tests/test_macos_controller_startup.cpp`
- Modify after A/B confirmation: `third_party/mujoco_ros2_control/mujoco_ros2_control/CMakeLists.txt`
- Modify: `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md`

**Interfaces:**
- Consumes: `so101_diagnose_macos_station`, closure/run/attestation models
- Produces: confirmed first bad boundary, one root-cause regression, five valid FULL_RESTART readiness records

- [ ] **Step 1: Plan EXP-MSC-001/002 before starting a stack**

Freeze the same closure and domain-allocation policy. EXP-MSC-001 launches `MINIMAL_CONTROLLER_MANAGER`; EXP-MSC-002 changes only to `ROBOT_SYSTEM_CONTROLLER_MANAGER`. Each has independent fresh `ROS_DOMAIN_ID`, station session and run binding. Save direct-client, process/load-state and DDS observations.

- [ ] **Step 2: Execute bounded A/B**

Use task-owned processes only. Expected outcomes are evidence, not assumed success: minimal path must show whether controller service registration works without `RobotSystem`; robot-system path must show the last emitted structured phase. If the two runs do not distinguish a boundary, record `UNCONFIRMED` and STOP for Sol/high review. Do not edit C++ based only on timeout length or downstream `STATION_NOT_READY`.

- [ ] **Step 3: Write one root-cause RED at the confirmed C++ boundary**

Always place the regression in `tests/test_macos_controller_startup.cpp`. The RED must recreate the observed ordering/deadlock or missing service transition without launching Web. For a macOS UI-dispatch ordering failure, the assertion is: controller construction and hardware `on_init` may request a main-thread UI task, the main thread services it before the 10 s initialization deadline, and controller-manager services become callable before MoveIt readiness. Product edits are limited to the listed source/header allowlist. If A/B locates the first bad boundary outside that set, record the trace, STOP, and obtain Sol/high plus Astra/high approval for a revised plan before any product edit; this is a diagnostic stop condition, not an unresolved file path.

- [ ] **Step 4: Apply the minimal owning-layer fix and GREEN**

Do not relax `motion_stack_ready`, skip controllers or add sleeps. Build/test only the affected submodule package first; then rebuild the copied parent install and run the direct diagnostic. Expected: original A/B failure flips at the first bad boundary, and loaded dylibs match the attested copied install.

```bash
colcon test --packages-select mujoco_ros2_control \
  --ctest-args -R macos_controller_startup
colcon test-result --verbose
```

Expected RED before the fix and PASS after it; collection/registration failure is INVALID, not RED.

- [ ] **Step 5: Run five FULL_RESTART station gates**

For EXP-MSC-003..007 require one stable `RuntimeClosureIdentity` and five unique run/attestation identities, direct `list_controllers`, all three controllers active, all MoveIt services/actions ready, fresh domain/session, and zero task-owned residue. A VALID failure resets the sequence; INVALID ends the batch and starts new experiment IDs.

- [ ] **Step 6: Commit and checkpoint**

Commit only the confirmed submodule change plus regression and parent gitlink. If no submodule edit was required, do not make an empty fix commit.

```bash
git -C third_party/mujoco_ros2_control add -- \
  mujoco_ros2_control/src/mujoco_ros2_control_node.cpp \
  mujoco_ros2_control/src/macos_ui_dispatcher.cpp \
  mujoco_ros2_control/include/mujoco_ros2_control/macos_ui_dispatcher.hpp \
  mujoco_ros2_control/src/mujoco_system_interface.cpp \
  mujoco_ros2_control/include/mujoco_ros2_control/mujoco_system_interface.hpp \
  mujoco_ros2_control/tests/test_macos_controller_startup.cpp \
  mujoco_ros2_control/CMakeLists.txt
git -C third_party/mujoco_ros2_control diff --cached --check
git -C third_party/mujoco_ros2_control commit -m "fix(mujoco): make macOS controller startup bounded"
git add -- third_party/mujoco_ros2_control \
  docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md
git diff --cached --check
git commit -m "fix(so101): bind bounded macOS controller startup"
```

STOP after `CP-MSC-A` for Sol/high review; Gate B live work is forbidden unless root is `CONFIRMED` and 5/5 readiness is valid.

## Gate B: selected-point execution、journal projection 与 ownership

### Task 4: 实现不可变 SelectionBinding 和 durable shared queue

**Files:**
- Create: `src/so101_demo_py/src/parallel_batch/selection.py`
- Create: `src/so101_demo_py/src/parallel_batch/queue.py`
- Create: `src/so101_demo_py/test/test_parallel_selection.py`
- Create: `src/so101_demo_py/test/test_parallel_point_queue.py`
- Modify: `src/so101_demo_py/src/parallel_batch/w2_composition.py`
- Modify: `src/so101_demo_py/test/test_macos_w2_campaign.py`

**Interfaces:**
- Consumes: Web catalog points and candidate execution identity R
- Produces: `FirstPassSelectionBinding`, `RetrySelectionBinding`, `DurablePointQueue`

```python
@dataclass(frozen=True, slots=True)
class SelectedPoint:
    point_id: str
    position_xyz_m: tuple[float, float, float]
    orientation_xyzw: tuple[float, float, float, float]
    point_sha256: str

@dataclass(frozen=True, slots=True)
class FirstPassSelectionBinding:
    catalog_schema_version: int
    catalog_sha256: str
    coordinate_frame: str
    points: tuple[SelectedPoint, ...]
    selection_sha256: str
    campaign_id: str
    batch_id: str
    execution_identity_sha256: str
    runtime_closure_sha256: str

@dataclass(frozen=True, slots=True)
class RetrySelectionBinding:
    original_catalog_sha256: str
    original_selection_sha256: str
    original_result_sha256: str
    point: SelectedPoint
    campaign_id: str
    batch_id: str
    execution_identity_sha256: str
    runtime_closure_sha256: str

class DurablePointQueue:
    def lease_next(self, worker: WorkerIdentity) -> PointLease | None: ...
    def commit_result(self, lease: PointLease, result: CommittedResult) -> None: ...
```

- [ ] **Step 1: RED selection and queue invariants**

Test first pass 4–20 and four anchors; retry exactly one business-failed point with source hashes and no anchor rule; catalog/coordinate/point hash drift; ordered shared leasing; two slots consuming 20 points; idempotent duplicate lease request; no duplicate active point/result; stale generation; selected-only execution; queue recovery after crash.

- [ ] **Step 2: Verify RED**

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_parallel_selection.py \
  src/so101_demo_py/test/test_parallel_point_queue.py \
  src/so101_demo_py/test/test_macos_w2_campaign.py \
  --junitxml="$RUN_ROOT/task4-red.xml"
```

Expected: failure because bindings/queue are absent and current W2 only assigns the first two selected ids.

- [ ] **Step 3: Implement binding and shared queue**

`exact_w2_slots()` returns two capacity slots without static point assignment. The queue identity is `(campaign_id,batch_id,point_id,attempt_id,generation,worker_id)`. State changes and lease counts are fsync-backed; unselected ids cannot be injected by a Worker.

- [ ] **Step 4: GREEN and commit**

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_parallel_selection.py \
  src/so101_demo_py/test/test_parallel_point_queue.py \
  src/so101_demo_py/test/test_macos_w2_campaign.py \
  src/so101_demo_py/test/test_parallel_batch_coordinator.py \
  --junitxml="$RUN_ROOT/task4-green.xml"
git add -- \
  src/so101_demo_py/src/parallel_batch/selection.py \
  src/so101_demo_py/src/parallel_batch/queue.py \
  src/so101_demo_py/src/parallel_batch/w2_composition.py \
  src/so101_demo_py/test/test_parallel_selection.py \
  src/so101_demo_py/test/test_parallel_point_queue.py \
  src/so101_demo_py/test/test_macos_w2_campaign.py
git diff --cached --check
git commit -m "feat(so101): bind selections to a durable shared queue"
```

Expected: all four files pass; the two slots drain the complete selected set exactly once and no unselected id appears in a lease or result.

### Task 5: 让 Worker 每个 lease 只执行一个被选点

**Files:**
- Create: `src/so101_demo_py/src/parallel_batch/single_point_input.py`
- Create: `src/so101_demo_py/test/test_single_point_input.py`
- Modify: `src/so101_demo_py/src/cli/macos_w2_campaign.py`
- Modify: `src/so101_demo_py/src/cli/macos_w2_worker.py`
- Modify: `src/so101_demo_py/src/parallel_batch/macos_w2_campaign.py`
- Modify: `src/so101_demo_py/test/test_macos_w2_campaign.py`

**Interfaces:**
- Consumes: `PointLease`, `SelectionBinding`
- Produces: hash-bound one-point YAML and `PointExecutionResult`

```python
@dataclass(frozen=True, slots=True)
class PointExecutionInput:
    lease: PointLease
    selection_sha256: str
    relative_points_path: str
    points_sha256: str

def write_single_point_input(
    *, binding: FirstPassSelectionBinding | RetrySelectionBinding,
    lease: PointLease,
    root: Path,
) -> PointExecutionInput: ...
```

- [ ] **Step 1: RED the current full-catalog bug**

Assert a selection containing anchors plus non-default points P09/P14/P20 executes every selected id once across W2; `rgbd_task_points.yaml` is never passed to the Worker; unselected ids have zero leases, MoveIt invocations and results. Retry input contains only the bound failed id.

- [ ] **Step 2: Run RED**

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_single_point_input.py \
  src/so101_demo_py/test/test_macos_w2_campaign.py \
  src/so101_demo_py/test/test_parallel_batch_broker.py \
  src/so101_demo_py/test/test_mujoco_rgbd_batch_cli.py \
  --junitxml="$RUN_ROOT/task5-red.xml"
```

Expected failure must show the current installed full points file or first-two assignment, not a mocked import error.

- [ ] **Step 3: Implement single-point execution**

Generate one immutable point file under the batch root with atomic rename/fsync and bind its hash into the lease. Worker reads back point id/hash before invoking `so101_mujoco_rgbd_batch`; broker inference requests use the same attempt id. Worker commits no business result until station readiness, MoveIt/pick-place result, inference association, evidence manifest and cleanup ownership are durable.

- [ ] **Step 4: GREEN and commit**

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_single_point_input.py \
  src/so101_demo_py/test/test_macos_w2_campaign.py \
  src/so101_demo_py/test/test_parallel_batch_broker.py \
  src/so101_demo_py/test/test_mujoco_rgbd_batch_cli.py \
  --junitxml="$RUN_ROOT/task5-green.xml"
git add -- \
  src/so101_demo_py/src/parallel_batch/single_point_input.py \
  src/so101_demo_py/src/cli/macos_w2_campaign.py \
  src/so101_demo_py/src/cli/macos_w2_worker.py \
  src/so101_demo_py/src/parallel_batch/macos_w2_campaign.py \
  src/so101_demo_py/test/test_single_point_input.py \
  src/so101_demo_py/test/test_macos_w2_campaign.py
git diff --cached --check
git commit -m "feat(so101): execute one selected point per worker lease"
```

Expected: every selected point is invoked exactly once from its one-point file; the installed full catalog never reaches the Worker CLI.

### Task 6: 扩展 CoordinatorJournal committed watermark

**Files:**
- Modify: `src/so101_demo_py/src/parallel_batch/journal.py`
- Modify: `src/so101_demo_py/test/test_parallel_batch_journal.py`
- Modify: `src/so101_demo_py/src/cli/macos_w2_campaign.py`
- Modify: `src/so101_demo_py/test/test_macos_w2_campaign.py`

**Interfaces:**
- Consumes: result commit proposal after result/manifest file and directory fsync
- Produces: `CommittedWatermark`, `read_committed_prefix()`, authenticated ACK

```python
@dataclass(frozen=True, slots=True)
class CommittedWatermark:
    writer_epoch: int
    sequence: int
    event_sha256: str

class CoordinatorJournal:
    def append_committed(self, event_type: str, idempotency_key: str,
                         payload: Mapping[str, object]) -> JournalEvent: ...
    @classmethod
    def read_committed_prefix(cls, root: Path, batch_id: str,
                              watermark: CommittedWatermark) -> JournalReplay: ...
```

- [ ] **Step 1: RED durability order and recovery**

Cover single writer, writer epoch takeover, idempotent replay, result atomic rename/fsync before proposal, journal flush/fsync, watermark temp fsync/rename/directory fsync, ACK only after both barriers, flush-before-fsync invisibility, fsync failure poison, watermark lag, partial tail, orphan complete frame, tamper, sequence gap and terminal append rejection.

- [ ] **Step 2: Run RED**

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_parallel_batch_journal.py \
  src/so101_demo_py/test/test_parallel_batch_crash_recovery.py \
  src/so101_demo_py/test/test_macos_w2_campaign.py \
  --junitxml="$RUN_ROOT/task6-red.xml"
```

Expected: new durability-order, committed-prefix and watermark-lag assertions fail because the journal has no published committed watermark contract.

- [ ] **Step 3: Implement without weakening strict replay**

`read_only_replay()` keeps strict incomplete-tail rejection. `read_committed_prefix()` only returns events at or below matching `(epoch,sequence,hash)`. Writer-exited bytes after watermark become `UNCONFIRMED_DURABILITY`; no truncation or automatic append.

- [ ] **Step 4: GREEN and commit**

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_parallel_batch_journal.py \
  src/so101_demo_py/test/test_parallel_batch_crash_recovery.py \
  src/so101_demo_py/test/test_macos_w2_campaign.py \
  --junitxml="$RUN_ROOT/task6-green.xml"
git add -- \
  src/so101_demo_py/src/parallel_batch/journal.py \
  src/so101_demo_py/src/cli/macos_w2_campaign.py \
  src/so101_demo_py/test/test_parallel_batch_journal.py \
  src/so101_demo_py/test/test_macos_w2_campaign.py
git diff --cached --check
git commit -m "feat(so101): publish fsync-backed campaign watermarks"
```

Expected: strict replay still rejects corrupt tails, while committed-prefix replay excludes unwatermarked bytes and ACK follows both fsync barriers.

### Task 7: 建立 ProjectionSource、唯一 reducer 和事务化 store

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
- Consumes: verified committed events from fixed Linux, macOS W2/W1 or adaptive source
- Produces: `ProjectionSource.read_after()`, `CanonicalCampaignReducer.apply()`, atomic `accept_projection_batch()`

```python
class ProjectionSource(Protocol):
    def read_after(self, cursor: UpstreamCursor | None) -> VerifiedEventBatch: ...

class CanonicalCampaignReducer:
    def apply(self, state: CampaignReducerState,
              event: VerifiedEvent) -> CampaignReducerState: ...

class SupervisorStore:
    def accept_projection_batch(self, *, batch_id: str,
                                expected_cursor: UpstreamCursor | None,
                                events: tuple[VerifiedEvent, ...]) -> CampaignReducerState: ...
```

- [ ] **Step 1: RED the delta/source split**

Sources must only adapt and verify; they cannot merge `payload.delta`. Test orthogonal point status, execution phase, attempt validity/infra outcome and batch business/cleanup/fence; `RESULT_COMMITTED` derives point terminal, while `POINT_TERMINAL` only confirms the same result hash. Reject INVALID->FAILED mapping, terminal without result, illegal append, identity drift and cursor/state split.

- [ ] **Step 2: RED transaction and restart recovery**

SQLite transaction records event idempotency, full reducer state, attempt dedupe and accepted cursor together. Inject failure after reducer update and before cursor update; expected full rollback. Restart must recover state without double-counting attempts.

- [ ] **Step 3: Run RED**

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_teleop/test/teleop/test_expert_validation_coordinator_events.py \
  src/so101_teleop/test/teleop/test_expert_validation_reducer.py \
  src/so101_teleop/test/teleop/test_expert_validation_store.py \
  src/so101_teleop/test/teleop/test_expert_validation_production_projection.py \
  --junitxml="$RUN_ROOT/task7-red.xml"
```

Expected: reducer and transaction tests fail because current coordinator events merge `payload.delta` directly and store cursor/state acceptance is not one atomic operation.

- [ ] **Step 4: Implement and GREEN**

Migrate existing fixed projection to the canonical reducer; React/OpenAPI still consume service state only.

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_teleop/test/teleop/test_expert_validation_coordinator_events.py \
  src/so101_teleop/test/teleop/test_expert_validation_reducer.py \
  src/so101_teleop/test/teleop/test_expert_validation_store.py \
  src/so101_teleop/test/teleop/test_expert_validation_production_projection.py \
  --junitxml="$RUN_ROOT/task7-green.xml"
git add -- \
  src/so101_teleop/so101_teleop/expert_validation/projection_source.py \
  src/so101_teleop/so101_teleop/expert_validation/reducer.py \
  src/so101_teleop/so101_teleop/expert_validation/coordinator_events.py \
  src/so101_teleop/so101_teleop/expert_validation/models.py \
  src/so101_teleop/so101_teleop/expert_validation/store.py \
  src/so101_teleop/so101_teleop/expert_validation/production.py \
  src/so101_teleop/test/teleop/test_expert_validation_coordinator_events.py \
  src/so101_teleop/test/teleop/test_expert_validation_reducer.py \
  src/so101_teleop/test/teleop/test_expert_validation_store.py \
  src/so101_teleop/test/teleop/test_expert_validation_production_projection.py \
  src/so101_teleop/CMakeLists.txt
git diff --cached --check
git commit -m "feat(teleop): reduce committed campaign events transactionally"
```

Expected: all sources feed the same reducer, invalid axes remain orthogonal, and injected cursor/state split rolls back completely.

### Task 8: 持久化完整 owner tree 并闭合 crash cleanup

**Files:**
- Create: `src/so101_teleop/so101_teleop/expert_validation/owner_tree.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_owner_tree.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/models.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/store.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/process_owner.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/supervisor.py`
- Modify: `src/so101_demo_py/src/cli/macos_service_campaign.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_process_owner.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_process_owner_integration.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_operator_recovery.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_macos_service_campaign.py`
- Modify: `src/so101_teleop/CMakeLists.txt`

**Interfaces:**
- Consumes: adapter/campaign/worker/station spawn intents and PID birth identities
- Produces: `OwnerNode`, `OwnerTreeRecovery`, generation-bound cleanup receipt

```python
@dataclass(frozen=True, slots=True)
class OwnerNode:
    batch_id: str
    role: Literal["ADAPTER", "CAMPAIGN", "WORKER", "STATION", "BROKER"]
    parent_role: str | None
    pid: int
    birth_identity: int
    pgid: int
    generation: int
    spawn_state: Literal["INTENT", "CONFIRMED", "EXITED"]

class OwnerTreeRecovery:
    def recover_leaf_first(self, *, batch_id: str,
                           generation: int) -> CleanupReceipt: ...
```

- [ ] **Step 1: RED normal, cancel and SIGKILL paths**

Cover process created in independent session; adapter/campaign/worker/station `SIGKILL`; PID reuse; unknown identity; duplicate reaper; leaf-first stop; station outside worker PGID; cleanup receipt from wrong generation; zero-process scan without ownership. Unknown identity stays fenced and is never signalled.

- [ ] **Step 2: Implement durable nodes at every spawn boundary**

Persist INTENT before spawn and CONFIRMED immediately after readback. Reaper order is station -> worker -> broker/campaign -> adapter. Only matching recovery owner generation may fsync cleanup receipt, append committed cleanup event and clear fence.

- [ ] **Step 3: Run RED**

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_teleop/test/teleop/test_expert_validation_owner_tree.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner_integration.py \
  src/so101_teleop/test/teleop/test_expert_validation_operator_recovery.py \
  src/so101_teleop/test/teleop/test_expert_validation_macos_service_campaign.py \
  --junitxml="$RUN_ROOT/task8-red.xml"
```

Expected: SIGKILL and station-outside-worker-PGID cases expose missing descendant identity and generation-bound cleanup proof.

- [ ] **Step 4: GREEN and commit**

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_teleop/test/teleop/test_expert_validation_owner_tree.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner_integration.py \
  src/so101_teleop/test/teleop/test_expert_validation_operator_recovery.py \
  src/so101_teleop/test/teleop/test_expert_validation_macos_service_campaign.py \
  --junitxml="$RUN_ROOT/task8-green.xml"
git add -- \
  src/so101_teleop/so101_teleop/expert_validation/owner_tree.py \
  src/so101_teleop/so101_teleop/expert_validation/models.py \
  src/so101_teleop/so101_teleop/expert_validation/store.py \
  src/so101_teleop/so101_teleop/expert_validation/process_owner.py \
  src/so101_teleop/so101_teleop/expert_validation/supervisor.py \
  src/so101_teleop/test/teleop/test_expert_validation_owner_tree.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner.py \
  src/so101_teleop/test/teleop/test_expert_validation_process_owner_integration.py \
  src/so101_teleop/test/teleop/test_expert_validation_operator_recovery.py \
  src/so101_teleop/CMakeLists.txt \
  src/so101_demo_py/src/cli/macos_service_campaign.py \
  src/so101_teleop/test/teleop/test_expert_validation_macos_service_campaign.py
git diff --cached --check
git commit -m "feat(teleop): recover macOS campaign ownership leaf first"
```

Expected: recovery only signals birth-identity matches, reaps leaf-first, and clears a fence only after the matching generation's durable cleanup receipt.

- [ ] **Step 5: Gate B checkpoint**

Run the combined offline B suite. Sol/high verifies non-default selection, selected-only single-point invocation, watermark durability, reducer transaction and SIGKILL cleanup. STOP at `CP-MSC-B` if any proof is missing; do not begin live campaign yet.

## Gate C: v5/v6 W1 与 retry admission

### Task 9: 新增 schema v5/v6 和 typed W1 composition

**Files:**
- Create: `src/so101_demo_py/config/mujoco/parallel_batch_v5_macos_mps_w1_retry.yaml`
- Create: `src/so101_demo_py/config/mujoco/parallel_batch_v6_macos_mps_w1_first_pass.yaml`
- Create: `src/so101_demo_py/src/parallel_batch/w1_composition.py`
- Create: `src/so101_demo_py/src/cli/macos_n1_first_pass.py`
- Create: `src/so101_demo_py/src/cli/macos_n1_retry.py`
- Create: `src/so101_demo_py/test/test_macos_w1_composition.py`
- Create: `src/so101_demo_py/test/test_macos_n1_cli.py`
- Modify: `src/so101_demo_py/src/parallel_batch/contracts.py`
- Modify: `src/so101_demo_py/setup.py`
- Modify: `src/so101_demo_py/test/test_parallel_batch_contracts.py`
- Modify: `src/so101_demo_py/test/test_macos_install_contract.py`

**Interfaces:**
- Consumes: `FirstPassSelectionBinding` or `RetrySelectionBinding`
- Produces: `ParallelRuntimeConfigV5`, `ParallelRuntimeConfigV6`, `compose_w1_first_pass()`, `compose_w1_retry()`

- [ ] **Step 1: RED closed version matrix**

Freeze v4 file bytes/SHA and both v4 platform combinations. v5 accepts only Darwin/MPS, N=1, `SEQUENTIAL`, `FULL_RESTART_RETRY`, `FULL_RESTART`, no CPU fallback and retry binding. v6 accepts only Darwin/MPS, N=1, `SEQUENTIAL`, `FIRST_PASS`, no CPU fallback and first-pass binding. Test all cross-version/profile/batch-kind rejections.

- [ ] **Step 2: Run RED**

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_parallel_batch_contracts.py \
  src/so101_demo_py/test/test_macos_w1_composition.py \
  src/so101_demo_py/test/test_macos_n1_cli.py \
  src/so101_demo_py/test/test_macos_install_contract.py \
  --junitxml="$RUN_ROOT/task9-red.xml"
```

- [ ] **Step 3: Implement typed W1 primitive**

The common primitive creates exactly one slot/Worker/domain and reuses broker, station owner, control endpoint and cleanup. Public CLIs accept their one schema only; no generic `--batch-kind` switch and no profile inference from point count.

- [ ] **Step 4: GREEN and commit**

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_parallel_batch_contracts.py \
  src/so101_demo_py/test/test_macos_w1_composition.py \
  src/so101_demo_py/test/test_macos_n1_cli.py \
  src/so101_demo_py/test/test_w2_composition.py \
  src/so101_demo_py/test/test_macos_w2_campaign.py \
  src/so101_demo_py/test/test_macos_install_contract.py \
  src/so101_demo_py/test/test_copied_installed_entrypoint.py \
  --junitxml="$RUN_ROOT/task9-green.xml"
git add -- \
  src/so101_demo_py/config/mujoco/parallel_batch_v5_macos_mps_w1_retry.yaml \
  src/so101_demo_py/config/mujoco/parallel_batch_v6_macos_mps_w1_first_pass.yaml \
  src/so101_demo_py/src/parallel_batch/w1_composition.py \
  src/so101_demo_py/src/cli/macos_n1_first_pass.py \
  src/so101_demo_py/src/cli/macos_n1_retry.py \
  src/so101_demo_py/src/parallel_batch/contracts.py \
  src/so101_demo_py/setup.py \
  src/so101_demo_py/test/test_parallel_batch_contracts.py \
  src/so101_demo_py/test/test_macos_w1_composition.py \
  src/so101_demo_py/test/test_macos_n1_cli.py \
  src/so101_demo_py/test/test_macos_install_contract.py
git diff --cached --check
git commit -m "feat(so101): add closed macOS W1 execution profiles"
```

Expected: v5 and v6 accept only their declared Darwin/MPS W1 inputs; all cross-profile cases fail closed and the v4 config bytes/SHA remain unchanged.

### Task 10: typed retry context 与原子 retry admission

**Files:**
- Create: `src/so101_teleop/so101_teleop/expert_validation/retry_context.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_retry_context.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/api.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/models.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/store.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/statistics.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/supervisor.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/production.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/service.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_api.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_store.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_statistics.py`
- Modify: `src/so101_teleop/test/teleop/test_expert_validation_supervisor.py`
- Modify: `src/so101_teleop/CMakeLists.txt`

**Interfaces:**
- Consumes: business FAILED first-pass result, current lease, v5 config, authority document
- Produces: `RetryStartRequest`, `MeasurementRetryContext`, `ProductionRetryContext`, atomic `admit_retry()`

```python
@dataclass(frozen=True, slots=True)
class RetryStartRequest:
    original_campaign_id: str
    failed_point_id: str
    original_result_sha256: str
    retry_batch_id: str
    config_sha256: str
    runtime_identity_sha256: str
    command_id: str
    lease_generation: int

class SupervisorStore:
    def admit_retry(self, *, request: RetryStartRequest,
                    context: MeasurementRetryContext | ProductionRetryContext,
                    spawn_intent: ExecutionOwnerIntent) -> RetrySelectionBinding: ...
```

- [ ] **Step 1: RED mutually exclusive authority**

Cover missing qualification and missing measurement authorization; context replay/expiry/hash drift; measurement context at production endpoint; production context at measurement endpoint; non-business failure; original batch not terminal-clean; active/unknown owner; fence; stale lease; duplicate command; transaction succeeds then spawn fails.

- [ ] **Step 2: Implement one transaction**

Within one SQLite transaction consume command id, verify result/lease/terminal-clean/fence, create retry binding, write owner spawn intent and bind the context digest. A post-transaction spawn failure leaves recoverable intent/fence; command is not consumed twice. Retry appends history and never overwrites first-pass status/statistics.

- [ ] **Step 3: Run RED**

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_teleop/test/teleop/test_expert_validation_retry_context.py \
  src/so101_teleop/test/teleop/test_expert_validation_api.py \
  src/so101_teleop/test/teleop/test_expert_validation_store.py \
  src/so101_teleop/test/teleop/test_expert_validation_statistics.py \
  src/so101_teleop/test/teleop/test_expert_validation_supervisor.py \
  --junitxml="$RUN_ROOT/task10-red.xml"
```

Expected: admission/context tests fail because there is no typed mutually exclusive context and no atomic command/result/lease/owner-intent transaction.

- [ ] **Step 4: GREEN, OpenAPI regeneration and commit**

Export OpenAPI from the product exporter; do not hand-edit generated JSON/types.

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_teleop/test/teleop/test_expert_validation_retry_context.py \
  src/so101_teleop/test/teleop/test_expert_validation_api.py \
  src/so101_teleop/test/teleop/test_expert_validation_store.py \
  src/so101_teleop/test/teleop/test_expert_validation_statistics.py \
  src/so101_teleop/test/teleop/test_expert_validation_supervisor.py \
  --junitxml="$RUN_ROOT/task10-green.xml"
$TEST_PYTHON -m so101_teleop.openapi_export --validation \
  src/so101_teleop/so101_teleop/expert_validation_openapi.json
cd src/so101_teleop/web
bun run generate:api:validation
cd ../../../
git add -- \
  src/so101_teleop/so101_teleop/expert_validation/retry_context.py \
  src/so101_teleop/so101_teleop/expert_validation/api.py \
  src/so101_teleop/so101_teleop/expert_validation/models.py \
  src/so101_teleop/so101_teleop/expert_validation/store.py \
  src/so101_teleop/so101_teleop/expert_validation/statistics.py \
  src/so101_teleop/so101_teleop/expert_validation/supervisor.py \
  src/so101_teleop/so101_teleop/expert_validation/production.py \
  src/so101_teleop/so101_teleop/expert_validation/service.py \
  src/so101_teleop/so101_teleop/expert_validation_openapi.json \
  src/so101_teleop/test/teleop/test_expert_validation_retry_context.py \
  src/so101_teleop/test/teleop/test_expert_validation_api.py \
  src/so101_teleop/test/teleop/test_expert_validation_store.py \
  src/so101_teleop/test/teleop/test_expert_validation_statistics.py \
  src/so101_teleop/test/teleop/test_expert_validation_supervisor.py \
  src/so101_teleop/web/src/api/expert-validation-schema.d.ts \
  src/so101_teleop/CMakeLists.txt
git diff --cached --check
git commit -m "feat(teleop): admit qualified single-point restart retries"
```

Expected: a retry command is consumed once, a failed spawn remains recoverable, first-pass history/statistics stay immutable, and generated API artifacts match the exporter.

- [ ] **Step 5: Gate C checkpoint**

Sol/high reviews v4 immutability, v5/v6 matrix and retry atomicity. STOP at `CP-MSC-C` if any first-pass/retry identity can cross profiles.

## Gate D: Darwin measurement、budget、provider 与 promotion chain

### Task 11: 重建 sealed macOS measurement authority，保留 retired CLI

**Files:**
- Create: `src/so101_demo_py/src/parallel_batch/measurement_authority.py`
- Create: `src/so101_demo_py/src/parallel_batch/resource_measurement.py`
- Create: `src/so101_demo_py/src/cli/measure_macos_resources.py`
- Create: `src/so101_demo_py/test/test_macos_measurement_authority.py`
- Create: `src/so101_demo_py/test/test_macos_measurement_cli.py`
- Modify: `src/so101_demo_py/setup.py`
- Test unchanged: `src/so101_demo_py/test/test_parallel_measurement_cli.py`

**Interfaces:**
- Consumes: sealed `MeasurementAuthorization`
- Produces: private factory-issued `MeasurementContext`, immutable raw manifest B, console `so101_measure_macos_resources`

```python
@dataclass(frozen=True, slots=True)
class MeasurementAuthorization:
    operator_uid: int
    task_id: str
    dispatch_id: str
    platform_profile_sha256: str
    execution_identity_sha256: str
    exact_worker_count: int
    catalog_sha256: str
    seed: int
    batch_id: str
    evidence_root: Path
    expires_at_ns: int
    max_runs: int
    abort_policy_sha256: str

class MeasurementAuthorityReader:
    def issue_context(self, path: Path, *, expected_sha256: str,
                      command_id: str) -> MeasurementContext: ...
```

- [ ] **Step 1: RED the old and new entry points together**

Old CLI must still return exit 2 and `MEASUREMENT_ENTRY_RETIRED` for every argument set. New CLI rejects absent, symlinked, wrong-owner/mode, replaced, expired or replayed authorization; wrong platform/R/N/catalog/batch/root/owner scope; N>2; production caller; and evidence root outside the registered durable root.

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_parallel_measurement_cli.py \
  src/so101_demo_py/test/test_macos_measurement_authority.py \
  src/so101_demo_py/test/test_macos_measurement_cli.py \
  --junitxml="$RUN_ROOT/task11-red.xml"
```

Expected: the legacy test remains green, while collection of the two new files succeeds and their new CLI/authority assertions fail because those modules and entry point do not exist.

- [ ] **Step 2: Implement sealed reader and raw B**

Use `O_NOFOLLOW`, owner/mode/size/hash before and after read. Candidate does not load P/Q/M/D. It binds one command/run and writes raw manifest B only after samples, owner inventory and cleanup evidence are fsynced.

- [ ] **Step 3: GREEN and commit**

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_parallel_measurement_cli.py \
  src/so101_demo_py/test/test_macos_measurement_authority.py \
  src/so101_demo_py/test/test_macos_measurement_cli.py \
  --junitxml="$RUN_ROOT/task11-green.xml"
git add -- \
  src/so101_demo_py/src/parallel_batch/measurement_authority.py \
  src/so101_demo_py/src/parallel_batch/resource_measurement.py \
  src/so101_demo_py/src/cli/measure_macos_resources.py \
  src/so101_demo_py/test/test_macos_measurement_authority.py \
  src/so101_demo_py/test/test_macos_measurement_cli.py \
  src/so101_demo_py/setup.py
git diff --cached --check
git commit -m "feat(resources): add sealed macOS measurement entry"
```

Expected: the legacy entry still fails with exit 2/`MEASUREMENT_ENTRY_RETIRED`; only the new CLI can consume one valid sealed authorization and emit raw B.

### Task 12: Darwin sampler、pressure helper 与 watchdog

**Files:**
- Create: `src/so101_demo_py/src/parallel_batch/darwin_resource_sampler.py`
- Create: `src/so101_demo_py/assets/macos/memory_pressure.swift`
- Create: `src/so101_demo_py/test/test_darwin_resource_sampler.py`
- Modify: `src/so101_demo_py/src/parallel_batch/accelerator_probe.py`
- Modify: `src/so101_demo_py/src/parallel_batch/resource_measurement.py`
- Modify: `src/so101_demo_py/setup.py`
- Modify: `src/so101_demo_py/test/test_parallel_accelerator_probe.py`
- Modify: `src/so101_demo_py/test/test_parallel_start_guard.py`
- Modify: `src/so101_demo_py/test/test_parallel_start_guard_probe.py`

**Interfaces:**
- Consumes: owner tree and broker telemetry
- Produces: `DarwinResourceSample`, 50/25 ms calibration, authenticated watchdog cancel

```python
@dataclass(frozen=True, slots=True)
class DarwinResourceSample:
    sequence: int
    monotonic_ns: int
    host_total_bytes: int
    host_available_bytes: int
    swap_used_bytes: int
    swapins_pages: int
    swapouts_pages: int
    cpu_active_ticks: int
    cpu_idle_ticks: int
    owned_processes: tuple[OwnedProcessSample, ...]
    broker: BrokerMpsSample | None
    pressure_event: Literal["NO_EVENT_YET", "WARN", "CRITICAL"]
```

- [ ] **Step 1: RED fake Darwin APIs**

Cover page conversion; exact 20% equality and one-byte/tick rejection; gauges may rise/fall; cumulative counters cannot regress; 100 ms/1 s CPU windows; swap used unchanged but swap counter increments; initial pressure `NO_EVENT_YET`; helper heartbeat; sample gap >100 ms; PID reuse; foreign MPS consumer; broker generation drift; reload intent exact +1; old/new overlap; no fake broker sample during reload; unified-memory U not double-counted with owned/MPS values.

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_darwin_resource_sampler.py \
  src/so101_demo_py/test/test_parallel_accelerator_probe.py \
  src/so101_demo_py/test/test_parallel_start_guard.py \
  src/so101_demo_py/test/test_parallel_start_guard_probe.py \
  src/so101_demo_py/test/test_macos_measurement_authority.py \
  --junitxml="$RUN_ROOT/task12-red.xml"
```

Expected: fake Darwin fixtures collect but fail at missing sampler, pressure heartbeat and watchdog semantics; existing start-guard tests must not regress.

- [ ] **Step 2: Implement sampler and helper**

Host/Mach, proc rusage and broker telemetry share one monotonic sequence. Helper publishes WARN/CRITICAL and heartbeat only. Watchdog latches abort, freezes new spawn/lease/recovery and sends authenticated cancel within the next 50 ms period; detection/send/stop latency are recorded separately.

- [ ] **Step 3: GREEN and commit**

Compile the helper only in a task-local build during package gate.

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_darwin_resource_sampler.py \
  src/so101_demo_py/test/test_parallel_accelerator_probe.py \
  src/so101_demo_py/test/test_parallel_start_guard.py \
  src/so101_demo_py/test/test_parallel_start_guard_probe.py \
  src/so101_demo_py/test/test_macos_measurement_authority.py \
  --junitxml="$RUN_ROOT/task12-green.xml"
git add -- \
  src/so101_demo_py/src/parallel_batch/darwin_resource_sampler.py \
  src/so101_demo_py/assets/macos/memory_pressure.swift \
  src/so101_demo_py/src/parallel_batch/accelerator_probe.py \
  src/so101_demo_py/src/parallel_batch/resource_measurement.py \
  src/so101_demo_py/test/test_darwin_resource_sampler.py \
  src/so101_demo_py/test/test_parallel_accelerator_probe.py \
  src/so101_demo_py/test/test_parallel_start_guard.py \
  src/so101_demo_py/test/test_parallel_start_guard_probe.py \
  src/so101_demo_py/setup.py
git diff --cached --check
git commit -m "feat(resources): sample owned Darwin MPS campaigns"
```

Expected: fake Darwin fixtures enforce the exact thresholds and counter semantics, while watchdog cancel and generation drift fail closed.

### Task 13: exact-N provider、candidate profile、promotion/deployment 验证

**Files:**
- Create: `src/so101_demo_py/src/parallel_batch/resource_budget.py`
- Create: `src/so101_demo_py/test/test_macos_exact_n_qualification.py`
- Create: `src/so101_demo_py/test/test_macos_budget_promotion.py`
- Create: `src/so101_teleop/test/teleop/test_expert_validation_macos_resource_budget.py`
- Modify: `src/so101_demo_py/src/parallel_batch/resource_measurement.py`
- Modify: `src/so101_demo_py/src/parallel_batch/resources.py`
- Modify: `src/so101_teleop/so101_teleop/expert_validation/production.py`
- Modify: `src/so101_teleop/CMakeLists.txt`
- Modify: `docs/superpowers/specs/2026-09-18-so101-parallel-unbounded-queue-resource-budget-design.md`
- Modify: `docs/superpowers/plans/2026-09-18-so101-parallel-unbounded-queue-resource-budget-implementation.md`

**Interfaces:**
- Consumes: raw B, execution identity R, coverage policy and independent approvals
- Produces: `ExactNQualification` Q, `ApprovedBudgetProfile` P, promotion M, deployment D, `FixedProductionContext`

```python
class ExactNQualificationProvider:
    def verify(self, *, record: ExactNQualification, worker_count: int,
               execution_identity_sha256: str,
               platform_profile_sha256: str,
               coverage_policy_sha256: str) -> QualificationDecision: ...

class ResourceBudgetProvider:
    def admit_measurement(self, *, context: MeasurementContext,
                          live: DarwinLiveObservation) -> ResourceBudgetAdmission: ...
    def admit_production(self, *, context: FixedProductionContext,
                         live: DarwinLiveObservation) -> ResourceBudgetAdmission: ...
```

- [ ] **Step 1: RED digest graph and platform isolation**

Test B->Q->P->M->D one-way references; no self/future digest; Linux profile rejected on Darwin and vice versa; N1 cannot authorize N2; retry qualification cannot replace N1 resource Q; candidate starts with sealed authority and no P/Q; production rejects the same state; missing coverage/unknown attribution stays disabled.

- [ ] **Step 2: RED normal/fault/retry aggregation**

N1 and N2 each require five consecutive valid 20-point FULL_RESTART normal runs with same R and independent physical/resource/cleanup evidence plus all coverage cells. Fault affects envelope only. `RetryQualification` separately requires five v5 single-point full-restart retries of real business failures and does not change normal N1 resource Q.

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_macos_exact_n_qualification.py \
  src/so101_demo_py/test/test_macos_budget_promotion.py \
  src/so101_demo_py/test/test_parallel_batch_resources.py \
  src/so101_demo_py/test/test_parallel_measurement_cli.py \
  src/so101_teleop/test/teleop/test_expert_validation_macos_resource_budget.py \
  --junitxml="$RUN_ROOT/task13-red.xml"
```

Expected: new exact-N/promotion/production-adapter assertions fail because the Darwin B/Q/P/M/D provider does not exist; the retired CLI test stays green.

- [ ] **Step 3: Implement provider and update old budget boundaries**

Document that the retired Linux-only chain is history, ordinary macOS N1 uses v6/20 points, v5 only feeds `RetryQualification`, and Darwin uses design section 10. Update old plan Task 13/15 accordingly; do not rewrite historical measurements or 2026-09-19 conclusions.

- [ ] **Step 4: GREEN and commit**

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_macos_exact_n_qualification.py \
  src/so101_demo_py/test/test_macos_budget_promotion.py \
  src/so101_demo_py/test/test_parallel_batch_resources.py \
  src/so101_demo_py/test/test_parallel_measurement_cli.py \
  src/so101_teleop/test/teleop/test_expert_validation_macos_resource_budget.py \
  --junitxml="$RUN_ROOT/task13-green.xml"
git add -- \
  src/so101_demo_py/src/parallel_batch/resource_budget.py \
  src/so101_demo_py/src/parallel_batch/resource_measurement.py \
  src/so101_demo_py/src/parallel_batch/resources.py \
  src/so101_demo_py/test/test_macos_exact_n_qualification.py \
  src/so101_demo_py/test/test_macos_budget_promotion.py \
  src/so101_teleop/so101_teleop/expert_validation/production.py \
  src/so101_teleop/test/teleop/test_expert_validation_macos_resource_budget.py \
  src/so101_teleop/CMakeLists.txt
git diff --cached --check
git commit -m "feat(resources): qualify Darwin MPS exact N budgets"
git add -- \
  docs/superpowers/specs/2026-09-18-so101-parallel-unbounded-queue-resource-budget-design.md \
  docs/superpowers/plans/2026-09-18-so101-parallel-unbounded-queue-resource-budget-implementation.md
git diff --cached --check
git commit -m "docs: align budget chain with macOS W1 profiles"
```

Expected: candidate and production contexts are mutually exclusive, exact-N/platform/R mismatches remain disabled, and the old entry point remains retired.

- [ ] **Step 5: Gate D offline checkpoint**

Run package-level non-live tests, copied-install origin checks, OpenAPI/Bun typecheck/unit/build and served-byte hashes. Sol/high reviews results; Astra/high independently reviews provider/parser/digest graph. STOP at `CP-MSC-D-OFFLINE` unless both reviews pass. No measurement or promotion is implied.

## Gate E: bounded candidate live gates、Stage C/D 与 production Chrome acceptance

### Task 14: 冻结 candidate R 并运行有限 candidate live gates

**Files:**
- Modify: `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md` only; product defects return to owning task and create a new R
- Evidence: registered root only

**Interfaces:**
- Consumes: frozen copied install, sealed candidate authorization
- Produces: bounded station/W2/W1/retry candidate evidence; no production context

- [ ] **Step 1: Freeze candidate R and write all experiments PLANNED**

Record source/install inventories, model/config/catalog hashes, v4/v5/v6 files, closure identity, sampler/helper bytes, parser/provider bytes and copied executable origins. Set a finite authorization count and abort policy. Any later product edit invalidates the whole candidate series.

- [ ] **Step 2: Re-run station 5/5 under measurement ownership**

Use the same closure identity and fresh run/attestation each time. Do not reuse Gate A runs if execution bytes changed in Tasks 4–13.

- [ ] **Step 3: Candidate W2 service gate**

Use v4 with 4–20 selected points including non-first-two ids. Require two concurrent Workers/stations, every selected point exactly one physical attempt/result, unselected zero, raw journal equals service projection, fresh Chrome progress/evidence, and zero residue.

- [ ] **Step 4: Candidate W1 first-pass gate**

Use v6 with 20 points, one Worker for the whole run, same candidate R, physical/resource/cleanup evidence and no retry semantics.

- [ ] **Step 5: Candidate N1 retry gate**

First use fault injection only for rejection classification. Then use one terminal-clean real business FAILED point and one-time `MeasurementRetryContext`; require v5, fresh FULL_RESTART, exactly that point once, separate batch/journal/statistics and no residue.

- [ ] **Step 6: Checkpoint and stop conditions**

Any safety abort, unknown owner, incomplete cleanup, sampler gap, projection mismatch, invalid physical evidence or product code edit stops the candidate batch. Record `VALID`/`INVALID` exactly; do not auto-loop until PASS. Sol/high reviews `CP-MSC-E-CANDIDATE` before Stage C.

### Task 15: Stage C — Darwin N1/N2 测量和 RetryQualification

**Files:**
- Modify: `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md` only
- Artifacts: durable evidence root B/Q/candidate-P trees

**Interfaces:**
- Consumes: candidate R, sealed measurement authorizations, offline-approved parser/provider
- Produces: Darwin N1 Q/P, Darwin N2 Q/P, independent `RetryQualification`; all remain CANDIDATE

- [ ] **Step 1: Verify durable-root and calibration preconditions**

Migrate the registered evidence root if required. Run 50/25 ms calibration for exact N1 and N2 separately; calibration failure or >100 ms gap blocks the 20-point run. Save raw counters and error E; never reuse Linux numbers or N2 values for N1.

- [ ] **Step 2: Measure ordinary N1 first**

Run v6 normal 20-point FULL_RESTART series and required coverage/fault cells within authorization. Five consecutive VALID runs qualify resource stability even if a run contains a genuine business failure, but product-success streak remains separate. Unknown/infra/invalid ends the series.

- [ ] **Step 3: Measure exact N2**

Repeat with v4 exact W2 and actual two-slot concurrency. N1 evidence cannot fill N2 cells. No N>2 profile is generated; those choices remain unavailable.

- [ ] **Step 4: Build retry qualification separately**

Using five one-time `MeasurementRetryContext` authorizations, execute five valid v5 retries of real business-failed points. Each has a different batch/run binding and exactly one point. Parser rejection, selection binding, crash cleanup and projection recovery evidence are included; resource admission still references N1 Q/P independently.

- [ ] **Step 5: Seal candidate outputs and checkpoint**

Seal B/Q/P and retry qualification hashes; report `resource_qualified` and `product_qualification_passed` separately. Sol/high reviews raw manifests and arithmetic. STOP at `CP-MSC-STAGE-C`; no approved profile or production context may be created.

### Task 16: Stage D 独立审查、显式批准和部署读回

**Files:**
- Create only after separate authorization: `src/so101_demo_py/config/mujoco/macos_mps_resource_budget_deployment_v1.yaml`
- Modify only after separate authorization: `src/so101_demo_py/test/test_macos_budget_promotion.py`
- Modify only after separate authorization: `src/so101_demo_py/test/test_macos_install_contract.py`
- Modify only after separate authorization: `src/so101_teleop/test/teleop/test_expert_validation_macos_resource_budget.py`
- Modify only after separate authorization: `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md`
- Artifacts: review records, operator approval M, installed deployment audit A1 and receipt D

**Interfaces:**
- Consumes: reviewed candidate P/Q/R and retry qualification
- Produces: operator-approved M/D and `FixedProductionContext`

- [ ] **Step 1: Independent review without mutation**

Sol/high reviews execution/raw manifests; Astra/high independently reviews profile, proposal, parser/provider and digest graph. A review finding returns to the owning task, changes R and invalidates Stage C.

- [ ] **Step 2: STOP for explicit operator approval**

Present exact N, platform profile SHA, P/Q/R, retry qualification and proposed config reference diff. This plan and its dispatch do not authorize promotion. Without an explicit user approval naming exact N/profile hash, leave N/profile disabled and end with PARTIAL.

- [ ] **Step 3: After approval only, write M and deployment refs**

Write the approved exact-N/profile/P/Q/R/M references to `macos_mps_resource_budget_deployment_v1.yaml`; it is the only source-controlled carrier. Add RED->GREEN parser, cross-N/profile/hash rejection and copied-install presence tests in the three files listed above. Rebuild the copied install, produce A1/D and prove only allowed carrier metadata changed while L/S/E/I/R remain equal. Any executable/parser/config semantic byte change invalidates approval and returns to Stage C.

- [ ] **Step 4: Production context readback**

All three production consumers must validate matching P/Q/R/M/D and current lease/owner. Production retry additionally validates `RetryQualification`. Run the scoped tests plus the copied-install contract, then commit only the listed carrier, tests and ledger:

```bash
$TEST_PYTHON -m pytest -q \
  src/so101_demo_py/test/test_macos_budget_promotion.py \
  src/so101_demo_py/test/test_macos_install_contract.py \
  src/so101_teleop/test/teleop/test_expert_validation_macos_resource_budget.py \
  --junitxml="$RUN_ROOT/task16-production-readback.xml"
git add -- \
  src/so101_demo_py/config/mujoco/macos_mps_resource_budget_deployment_v1.yaml \
  src/so101_demo_py/test/test_macos_budget_promotion.py \
  src/so101_demo_py/test/test_macos_install_contract.py \
  src/so101_teleop/test/teleop/test_expert_validation_macos_resource_budget.py \
  docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md
git diff --cached --check
git commit -m "chore(resources): bind approved macOS budget deployment"
```

This local commit is not push/merge authorization.

### Task 17: Production Web + fresh Chrome acceptance

**Files:**
- Modify: `src/so101_teleop/web/e2e/expert-validation/live-sim/02-parallel.spec.ts`
- Modify: `src/so101_teleop/web/e2e/expert-validation/live-sim/06-fixed-n-execution.spec.ts`
- Modify: `src/so101_teleop/web/e2e/expert-validation/live-sim/07-retry-full-restart.spec.ts`
- Modify: `src/so101_teleop/web/e2e/expert-validation/assertions/live-evidence.ts`
- Modify: `src/so101_teleop/web/playwright.live-sim.config.ts`
- Evidence/ledger only after tests exist

**Interfaces:**
- Consumes: `FixedProductionContext`, `ProductionRetryContext`
- Produces: fresh browser/API/raw-journal/physical acceptance tied to production deployment D

- [ ] **Step 1: RED browser assertions against fixtures**

Assert profile/status axes, selected-only execution, worker count 1/2, attempt identities, first-pass/retry separation, failure evidence selection, projection sequence/cursor, cleanup and disabled reasons. Run Bun unit/fixture Playwright; expected RED is a missing field/assertion, never a live service failure.

- [ ] **Step 2: Implement minimal API/UI assertion support and GREEN fixtures**

Modify only the five files listed for Task 17; do not add platform-specific state reconstruction. If a required API/UI field is absent, STOP and return to the owning Task 7, 10 or 13 with a reviewed plan amendment instead of editing an unlisted product file during acceptance. Regenerate OpenAPI/types only when that owning task changes the contract; then run `bun run typecheck`, unit tests, build and contract/installed fixtures before returning to Task 17.

- [ ] **Step 3: Start one production service in an approved exclusive window**

Fresh-read owner/process/port/lease state first. Start from copied install and D-bound config; do not stop an existing unknown service. Use a fresh browser profile and verify UI plus REST/WebSocket readback.

- [ ] **Step 4: Execute production W2 and W1/retry flows**

W2 first pass proves selected-only real pick-place and projection. W1 first pass proves exact one Worker/20 points. Retry uses a real business FAILED point and `ProductionRetryContext`; only that point runs. For every flow verify controller/joint/TF, MuJoCo cup pose/contact/release, MoveIt shadow/world sync, raw journal/watermark, Web evidence and exact cleanup.

- [ ] **Step 5: Run Playwright projects and checkpoint**

```bash
bun run test:e2e:live-sim --project parallel-resource
bun run test:e2e:live-sim --project fixed-n-execution
bun run test:e2e:live-sim --project retry-full-restart
```

These project names are frozen from `playwright.live-sim.config.ts` at base commit `6d5069026fbd322076f58d0d4b9504891abeb861`. A renamed or missing project is configuration drift and STOP; do not substitute another project. Fresh Chrome evidence must belong to this R/D and this service instance.

### Task 18: 最终 package gate、审查和本地交接

**Files:**
- Modify: `docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md`
- Create: `docs/guides/so101-macos-service-campaign-closure.md`

**Interfaces:**
- Consumes: all RED/GREEN/package/live evidence
- Produces: final checkpoint and scoped local commits; no publication

- [ ] **Step 1: Run final non-benchmark package gates**

Use the current macOS ROS environment and direct pytest fallback only under the repository's documented DYLD contract. Require nonzero collection, JUnit, package registration, copied-install origins and no source-tree import leakage. Run teleop CTest registrations, OpenAPI consistency, Bun typecheck/unit/build and served-byte hash.

- [ ] **Step 2: Verify runtime closure and cleanup one last time**

Read back HEAD, copied install inventory, R/P/Q/M/D, service PID/birth, task-owned process tree, controller goals, ROS nodes, broker claim, IPC registry and ports. Unknown residue blocks PASS; foreign processes are preserved and listed.

- [ ] **Step 3: Independent result review**

Sol/high judges implementation results against design section 14. Astra/high independently reviews the final scoped code/docs and production evidence. Findings return to the owning task and invalidate affected live evidence.

- [ ] **Step 4: Final ledger accounting**

Record retained runs, archived runs and deletion candidates separately. Do not delete or archive. State exact incomplete layers and next command if any gate remains. `dst DONE`, tmux exit, a successful Web status or one screenshot never substitutes for the full closure.

- [ ] **Step 5: Write the operator guide**

Use the repository `humanizer-zh` workflow. Document exact W2/v6-W1/v5-retry profile selection, lease/authority prerequisites, disabled reasons, evidence locations, recovery checkpoints and the fact that `so101_measure_parallel_resources` remains retired. Do not describe candidate measurement authorization as a production bypass.

- [ ] **Step 6: Local commit only**

```bash
git add -- \
  docs/experiments/so101-macos-service-campaign-closure-experiment-ledger.md \
  docs/guides/so101-macos-service-campaign-closure.md
git diff --cached --check
git commit -m "docs: record macOS service campaign closure"
```

Do not push or merge. Final handoff reports branch and local HEAD plus explicit statement that publication was not authorized.

## 执行 checkpoint 与停止规则

| Checkpoint | 必须满足 | 不满足时 |
| --- | --- | --- |
| `CP-MSC-A` | controller first bad boundary CONFIRMED；root RED->GREEN；station 5/5 | 停止，不进入 campaign live |
| `CP-MSC-B` | selected-only execution、watermark、reducer transaction、SIGKILL cleanup 离线通过 | 返回 Task 4–8 |
| `CP-MSC-C` | v4 frozen；v5/v6 closed；retry admission atomic | 返回 Task 9–10 |
| `CP-MSC-D-OFFLINE` | measurement/provider/package gates；Sol/Astra 审查通过 | 不做测量 |
| `CP-MSC-E-CANDIDATE` | station/W2/W1/retry candidate gates 有效且无残留 | 不进 Stage C |
| `CP-MSC-STAGE-C` | N1/N2 B/Q/P 和 RetryQualification 已封存、仍为 CANDIDATE | 等待独立审查和 operator approval |
| Stage D approval | 用户明确批准 exact N/profile SHA | 未批准即保持 disabled，不生成 M/D |
| Production Chrome | matching P/Q/R/M/D + production/retry context | 不启动 production Web gate |

## 计划自查

- 设计 §2–3 的目标、非目标和总体决策映射到 Global Constraints 与 Gate A–E；未扩大到真实机械臂、N>2 或自动发布。
- 设计 §4 映射到 Tasks 1–3；稳定 closure 与每轮 binding/attestation 分离，A/B 不预设根因。
- 设计 §5 映射到 Tasks 4–5；覆盖非默认/非前两点、selected 全部一次、unselected 零次和 retry 单点。
- 设计 §6 映射到 Tasks 9–10；v4 不变，v5/v6 互斥，W1 无通用 profile fallback。
- 设计 §7–8 映射到 Tasks 6–8；复用现有 journal，watermark 后投影，唯一 reducer 与完整 owner tree。
- 设计 §9 的代码边界映射到文件与接口总图，并由各 Task 的精确 Files/Interfaces 清单约束。
- 设计 §10 映射到 Tasks 11–13、15–16；旧 CLI fail closed，新 macOS CLI、Darwin sampler、N1/N2 独立 B/Q/P/M/D。
- 设计 §11–14 映射到 Tasks 14–18；candidate/production 顺序、Stage C/D、fresh Chrome、物理证据与 cleanup 均有 gate。
- 未保留待填文本、通用 skip flag、生产 bypass、自动 promotion 或隐含 push/merge。唯一需要现场决定的 C++ root fix 被 Gate A 的确认与计划修订门约束；在确认前没有 speculative product edit。
