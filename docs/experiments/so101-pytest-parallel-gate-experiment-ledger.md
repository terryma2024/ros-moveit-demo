---
task_id: so101-pytest-parallel-gate
goal: Reduce wall-clock time of the complete ordinary src/so101_demo_py/test pytest gate without changing coverage, semantics, failure criteria, benchmark isolation, or evidence quality.
success_contract: A repository-maintained deterministic runner passes focused RED/GREEN tests, proves exact node-ID coverage and benchmark exclusion, and produces uncontaminated W1/W2/W4 measurements on one committed candidate; the fastest valid mode is selected.
worktree: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism
branch: codex/pytest-gate-parallelism
base_commit: b0f9e7168198285fba4133026d9d3b132075f88b
current_commit: ceb41ec94d09eddc1537cf24859531a033acf61f
evidence_root: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01
confirmed_conclusions:
  - The required base is the current HEAD and the worktree was clean at dispatch (CP-001).
  - Full-gate timing is currently inadmissible because the preserved primary stateless-Broker task owns W10 MuJoCo, ROS, Docker, GPU, and user-service resources (CP-001).
  - The primary task reached COMPLETE and released its runtime resources; fresh admission at 2026-09-15T16:43:26+08:00 found no W10 processes, containers, GPU clients, or active W10 units (CP-002).
  - Exact /usr/bin/python3 command identity is preserved by candidate commit 1c0ec9a7bb04bd435cf38b9af254af7a9df4667b (EXP-006-PROVENANCE-CORRECTION).
disproven_routes:
  - Running W1/W2/W4 while the primary task is active is rejected as contaminated by the handoff's admission gate (CP-001).
open_hypotheses:
  - Deterministic file-level LPT sharding can preserve exact ordinary-gate coverage and reduce critical-path wall time.
  - Additional source-evidenced global-resource owners may need the serial lane beyond the two mandatory modules.
latest_checkpoint: CP-003
next_experiment: EXP-010-BENCHMARK-PATH-CORRECTION
---

# SO-101 pytest parallel gate experiment ledger

## Evidence registration

- Registered durable evidence root: `/data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01`
- Dispatch receipt: `/data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/handoff/dispatch-b2bba2a8-3e03-4d03-abbb-af88915ac4d1.receipt`
- Initial host snapshot: `/data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/initial-state.txt`
- Initial host snapshot SHA256: `2be39531b31968d088361326d942ea4cc7b5dab9e47654199116c60b8ef871db`
- Historical read-only timing input: `/data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/s38package8/package.xml`

## Initial observations

- `OBSERVED` at `2026-09-15T16:28:41+08:00`: hostname `AI-STATION-001`; current directory is the required worktree; branch is `codex/pytest-gate-parallelism`; HEAD is the required base commit; `git status --short` was empty.
- `OBSERVED`: submodule `third_party/mujoco_ros2_control` was uninitialized in this worktree (`-c16b5a5fe880b6e1857f56486dab4ae726576969`). No submodule mutation is authorized or currently needed.
- `OBSERVED`: tmux session `codex-task-so101-stateless-broker` is attached and its Codex process runs in `/data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool`.
- `OBSERVED`: the primary task owns a W10 adaptive batch process, ten MuJoCo/ROS worker process trees, Docker container `e5eb93f44e6a242b5e48a3c9983a2927b0e2309b798fab1bd19573b45c0c1510`, GPU client PID `1931757` using 2646 MiB, and active user services `so101-w10-z.service` and `so101-w10-z-monitor.service`.
- `OBSERVED`: the initial ROS node probe was invalid because `set -u` made `/opt/ros/jazzy/setup.zsh` stop on unset `AMENT_TRACE_SETUP_FILES`; the topic probe still reported only `/parameter_events` and `/rosout`. This invalid ROS node subsection is not used to infer stack absence.
- `OBSERVED`: the snapshot wrapper exited 1 after completing and writing all probe sections because it attempted to assign zsh's read-only `status` parameter. The artifact is retained unchanged; its command-wrapper exit does not invalidate the independently readable state data above.
- `INFERRED`: process-free source inspection and focused runner-unit tests can proceed without touching the primary task, but no real full-gate measurement is admissible until a fresh read-only admission check proves those resources idle.

## Checkpoints

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: A deterministic file-level LPT runner can preserve exact ordinary-gate coverage while reducing the parallel-lane critical path.
working_tree_status: clean at dispatch; this ledger is the first task-owned change
owned_processes: Codex process/session for codex-task-so101-pytest-parallel only; no test or runtime processes started
preserved_processes: codex-task-so101-stateless-broker; so101-w10-z.service; so101-w10-z-monitor.service; W10 MuJoCo/ROS worker trees; broker Docker container; GPU broker client; all other worktrees and tmux sessions
confirmed_conclusions:
  - Required base and branch provenance match the handoff.
  - Full-gate W1/W2/W4 runs are deferred while primary-task resource ownership remains active.
disproven_routes:
  - Treating the initial ROS node subsection as proof of no active ROS work is invalid because shell setup failed under set -u.
open_risks:
  - Source inspection may identify more serial-lane modules.
  - Focused pytest commands must use per-process fresh NVMe scratch roots and exact-Python tempfile verification.
  - Full benchmarks remain blocked by primary-task activity until admission is rechecked.
next_command: rg -n "pytest|unittest|systemd|socket|port|ROS_DOMAIN_ID|docker|subprocess|Process|multiprocessing|cuda|GPU|tmp_path|TemporaryDirectory" src/so101_demo_py/test src/so101_demo_py/setup.py src/so101_demo_py/setup.cfg
```

## EXP-001 — Focused runner contracts RED

```yaml
experiment_id: EXP-001
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-15T16:35:00+08:00
  - status: RUNNING
    at: 2026-09-15T16:37:00+08:00
  - status: VALID
    at: 2026-09-15T16:38:00+08:00
prior_experiment: NONE
hypothesis: The committed base has no repository-maintained deterministic full-gate runner implementing the required sharding, coverage, failure, and scratch contracts.
prediction: The new focused contract module fails during collection because tools.so101_pytest_gate does not exist.
single_variable: Add focused tests only; no runner implementation.
lifecycle: REUSE_STACK
preconditions:
  - The primary stateless-Broker W10 task and all its resources remain untouched.
  - The focused module imports only repository test-runner code and Python standard-library modules.
  - Exact /usr/bin/python3 tempfile routing is verified inside a fresh previously nonexistent NVMe scratch directory.
success_criteria:
  - The focused test command collects nonzero or fails at the expected missing-runner import boundary.
failure_criteria:
  - Existing runner code unexpectedly satisfies the tests, or failure occurs outside the missing implementation boundary.
invalid_criteria:
  - The scratch path exists before setup, tempfile routing differs, wrong Python executes, benchmark tests are collected, or the primary task is disturbed.
provenance:
  source_commit: b0f9e7168198285fba4133026d9d3b132075f88b
  install_overlay: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism
  runtime_executable: /usr/bin/python3
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - command: TMPDIR=<EXP-001-SCRATCH>/tmp TMP=<same> TEMP=<same> ROS_HOME=<EXP-001-SCRATCH>/ros-home ROS_LOG_DIR=<EXP-001-SCRATCH>/ros-log PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider -q src/so101_demo_py/test/test_pytest_full_gate_runner.py --junitxml=<EXP-001-SCRATCH>/red.xml
    exit_code: 2
observed:
  - OBSERVED: /usr/bin/python3 resolved tempfile.gettempdir() to the fresh exp001-red/tmp path.
  - OBSERVED: pytest stopped during collection with ModuleNotFoundError for tools.so101_pytest_gate; no test executed.
  - OBSERVED: pytest wrote a readable red.xml and the wrapper recorded elapsed_ms=403.
inferred:
  - Source inspection classifies test_parallel_adaptive_integration.py as serial because it starts and signals real process groups; the two handoff-mandated modules precede it.
  - Other detected sockets are rooted in per-test temporary paths, and Docker/GPU calls are mocked or source-contract checks, so per-process scratch isolation is the relevant boundary.
conclusion: The base lacks the required runner and the focused suite is RED at the intended missing-implementation boundary.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp001-red
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp001-red/SHA256SUMS
decision: KEEP
next_experiment: EXP-002
```

## EXP-002 — Focused runner contracts GREEN

```yaml
experiment_id: EXP-002
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-15T16:38:00+08:00
  - status: RUNNING
    at: 2026-09-15T16:46:00+08:00
  - status: INVALID
    at: 2026-09-15T16:47:00+08:00
prior_experiment: EXP-001
hypothesis: A standard-library file-level LPT runner and pytest manifest plugin can satisfy deterministic assignment, fallback, ordered serial exclusion, exact node union, fail-closed outcomes, benchmark isolation, and scratch isolation.
prediction: The focused runner module passes all tests after implementation, using the same exact Python and a new verified NVMe scratch root.
single_variable: Add tools/so101_pytest_gate.py and tools/so101_pytest_manifest.py implementing the tested contracts.
lifecycle: REUSE_STACK
preconditions:
  - EXP-001 is a valid RED at the missing-module boundary.
  - Primary stateless-Broker resources remain preserved and focused tests do not invoke the full ordinary suite.
success_criteria:
  - All focused runner tests pass with exit code 0 and readable JUnit.
failure_criteria:
  - Any focused contract fails.
invalid_criteria:
  - Wrong Python, scratch routing, source path, or contamination by primary-task activity.
provenance:
  source_commit: b0f9e7168198285fba4133026d9d3b132075f88b
  install_overlay: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism
  runtime_executable: /usr/bin/python3
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - command: TMPDIR=<EXP-002-SCRATCH>/tmp TMP=<same> TEMP=<same> ROS_HOME=<EXP-002-SCRATCH>/ros-home ROS_LOG_DIR=<EXP-002-SCRATCH>/ros-log PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider -q src/so101_demo_py/test/test_pytest_full_gate_runner.py --junitxml=<EXP-002-SCRATCH>/green.xml
    exit_code: 1
observed:
  - OBSERVED: pytest collected 20 focused cases; 18 passed and two coverage-diagnostic cases failed in 0.11 seconds.
  - OBSERVED: the first failure was a malformed parameter whose expected regex was an empty tuple instead of `missing`.
  - OBSERVED: the mixed missing-and-unexpected case reported only the first category, reducing diagnostic completeness.
inferred:
  - NONE
conclusion: This run is invalid for GREEN acceptance because one test parameter was malformed; retain it as diagnostic evidence and rerun after the focused correction.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp002-green
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp002-green/SHA256SUMS
decision: REPEAT
next_experiment: EXP-003
```

## EXP-003 — Corrected focused runner contracts GREEN

```yaml
experiment_id: EXP-003
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-15T16:47:00+08:00
  - status: RUNNING
    at: 2026-09-15T16:48:00+08:00
  - status: VALID
    at: 2026-09-15T16:49:00+08:00
prior_experiment: EXP-002
hypothesis: Correcting the malformed expected-regex fixture and reporting all simultaneous coverage discrepancies will make the focused runner contracts pass.
prediction: The same 20 focused cases pass under a fresh verified NVMe scratch root.
single_variable: Fix the missing-case regex and aggregate missing/unexpected coverage diagnostics.
lifecycle: REUSE_STACK
preconditions:
  - EXP-001 remains the valid RED and EXP-002 is retained as an invalid fixture-diagnostic run.
  - No full ordinary gate or external runtime is started.
success_criteria:
  - All 20 focused tests pass with exit code 0 and readable JUnit.
failure_criteria:
  - Any focused test fails.
invalid_criteria:
  - Wrong Python, tempfile routing, source path, or primary-task contamination.
provenance:
  source_commit: b0f9e7168198285fba4133026d9d3b132075f88b
  install_overlay: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism
  runtime_executable: /usr/bin/python3
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - command: TMPDIR=<EXP-003-SCRATCH>/tmp TMP=<same> TEMP=<same> ROS_HOME=<EXP-003-SCRATCH>/ros-home ROS_LOG_DIR=<EXP-003-SCRATCH>/ros-log PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider -q src/so101_demo_py/test/test_pytest_full_gate_runner.py --junitxml=<EXP-003-SCRATCH>/green.xml
    exit_code: 0
observed:
  - OBSERVED: /usr/bin/python3 resolved tempfile.gettempdir() to the fresh exp003-green/tmp path.
  - OBSERVED: all 20 focused runner contracts passed in 0.03 seconds; wrapper elapsed_ms=290.
  - OBSERVED: readable JUnit and SHA256SUMS were retained in the experiment scratch root.
inferred:
  - NONE
conclusion: The focused deterministic assignment, timing fallback, serial exclusion, exact coverage, failure propagation, benchmark exclusion, scratch isolation, and worker-count contracts are GREEN.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp003-green
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp003-green/SHA256SUMS
decision: KEEP
next_experiment: EXP-004
```

## EXP-004 — Post-format focused regression

```yaml
experiment_id: EXP-004
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-15T16:51:00+08:00
  - status: RUNNING
    at: 2026-09-15T16:52:00+08:00
  - status: VALID
    at: 2026-09-15T16:42:59+08:00
prior_experiment: EXP-003
hypothesis: Mechanical Ruff formatting plus stricter package-origin provenance, concise node-manifest summaries, dirty-tree gating, and failure-summary persistence preserve the focused contracts.
prediction: The focused module remains 20/20 GREEN and Ruff checks remain clean.
single_variable: Runner hardening and mechanical formatting after EXP-003.
lifecycle: REUSE_STACK
preconditions:
  - EXP-003 is valid GREEN.
  - The primary W10 task remains untouched; no full suite or package build is started.
success_criteria:
  - All 20 focused tests pass; Ruff check and format-check pass.
failure_criteria:
  - Any focused or static check fails.
invalid_criteria:
  - Wrong Python, tempfile routing, or source path.
provenance:
  source_commit: b0f9e7168198285fba4133026d9d3b132075f88b
  install_overlay: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism
  runtime_executable: /usr/bin/python3
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - command: TMPDIR=<EXP-004-SCRATCH>/tmp TMP=<same> TEMP=<same> ROS_HOME=<EXP-004-SCRATCH>/ros-home ROS_LOG_DIR=<EXP-004-SCRATCH>/ros-log PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider -q src/so101_demo_py/test/test_pytest_full_gate_runner.py --junitxml=<EXP-004-SCRATCH>/green.xml
    exit_code: 0
  - command: /home/lenovo/.local/bin/ruff check tools/so101_pytest_gate.py tools/so101_pytest_manifest.py src/so101_demo_py/test/test_pytest_full_gate_runner.py
    exit_code: 0
  - command: /home/lenovo/.local/bin/ruff format --check tools/so101_pytest_gate.py tools/so101_pytest_manifest.py src/so101_demo_py/test/test_pytest_full_gate_runner.py
    exit_code: 0
observed:
  - OBSERVED: all 20 focused tests passed in 0.03 seconds; wrapper elapsed_ms=342.
  - OBSERVED: Ruff check passed and Ruff format-check reported all three files already formatted.
  - OBSERVED: exact Python tempfile routing, readable JUnit, logs, and SHA256SUMS were retained.
inferred:
  - NONE
conclusion: Focused behavior and static quality remained GREEN after provenance and summary hardening.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp004-focused
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp004-focused/SHA256SUMS
decision: KEEP
next_experiment: EXP-005
```

## Timestamp correction

```yaml
correction_at: 2026-09-15T16:44:31+08:00
reason: Several manually entered PLANNED/RUNNING timestamps were estimates and were later observed to be ahead of the ai-station clock. Historical status rows are preserved; authoritative completion times below come from retained result-file mtimes.
authoritative_result_times:
  EXP-001: 2026-09-15T16:34:12.792625962+08:00
  EXP-002: 2026-09-15T16:38:21.599608819+08:00
  EXP-003: 2026-09-15T16:39:23.014837988+08:00
  EXP-004: 2026-09-15T16:42:59.894176862+08:00
evidence: stat readback of each experiment result.txt under the registered evidence root
```

## EXP-005 — Scoped dirty-path and post-change focused gate

```yaml
experiment_id: EXP-005
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-15T16:44:31+08:00
  - status: RUNNING
    at: 2026-09-15T16:45:14+08:00
  - status: VALID
    at: 2026-09-15T16:45:42.461427808+08:00
prior_experiment: EXP-004
hypothesis: Exact audit-only dirty-path admission can preserve one code commit across ledger appends while rejecting any unlisted code change, and bytecode suppression prevents pytest from mutating the source tree.
prediction: All 22 focused tests and Ruff checks pass under a new scratch root.
single_variable: Add exact dirty-path validation, end-of-run status equality, package bytecode suppression, and their focused contracts.
lifecycle: REUSE_STACK
preconditions:
  - The preserved primary task has no W10 process, Docker, GPU, or active W10 user-unit resources at the 2026-09-15T16:43:26+08:00 read-only admission check.
  - No full ordinary test run starts in this experiment.
success_criteria:
  - All 22 focused tests pass and Ruff check/format-check pass.
failure_criteria:
  - Any focused or static contract fails.
invalid_criteria:
  - Wrong Python, tempfile routing, or untracked external interference.
provenance:
  source_commit: b0f9e7168198285fba4133026d9d3b132075f88b
  install_overlay: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism
  runtime_executable: /usr/bin/python3
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - command: TMPDIR=<EXP-005-SCRATCH>/tmp TMP=<same> TEMP=<same> ROS_HOME=<EXP-005-SCRATCH>/ros-home ROS_LOG_DIR=<EXP-005-SCRATCH>/ros-log PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider -q src/so101_demo_py/test/test_pytest_full_gate_runner.py --junitxml=<EXP-005-SCRATCH>/green.xml
    exit_code: 0
  - command: /home/lenovo/.local/bin/ruff check tools/so101_pytest_gate.py tools/so101_pytest_manifest.py src/so101_demo_py/test/test_pytest_full_gate_runner.py
    exit_code: 0
  - command: /home/lenovo/.local/bin/ruff format --check tools/so101_pytest_gate.py tools/so101_pytest_manifest.py src/so101_demo_py/test/test_pytest_full_gate_runner.py
    exit_code: 0
observed:
  - OBSERVED: all 22 focused tests passed in 0.03 seconds; wrapper elapsed_ms=309.
  - OBSERVED: Ruff check and format-check passed.
  - OBSERVED: exact /usr/bin/python3 tempfile routing and fresh scratch ownership were verified.
inferred:
  - NONE
conclusion: The runner can admit only the append-only ledger as dirty while rejecting unlisted code changes; focused behavior and static quality are GREEN.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp005-focused
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp005-focused/SHA256SUMS
decision: KEEP
next_experiment: EXP-006
```

## CP-002 — Committed candidate and released primary resources

```yaml
checkpoint_id: CP-002
last_valid_experiment: EXP-005
current_hypothesis: The committed runner can build against this worktree overlay and then preserve exact coverage with lower wall time at W2 or W4.
working_tree_status: only docs/experiments/so101-pytest-parallel-gate-experiment-ledger.md is modified after candidate commit e97a106a7e1b2048ade92926c8c708012b442c59
owned_processes: Codex process/session codex-task-so101-pytest-parallel only; no pytest, build, ROS, Docker, GPU, or user-unit process started yet
preserved_processes: completed codex-task-so101-stateless-broker session; all other worktrees and tmux sessions
confirmed_conclusions:
  - Candidate implementation, plugin, 22 focused tests, and ledger through EXP-005 are committed as e97a106a7e1b2048ade92926c8c708012b442c59.
  - Read-only primary pane shows CP-044 COMPLETE and final cleanup; independent admission found no W10 processes, Docker containers, GPU clients, or active W10 units.
disproven_routes:
  - Running full gates during the earlier active W10 interval remains invalid and was not attempted.
open_risks:
  - The new worktree overlay has not yet been built or sourced.
  - The runner subprocess/plugin path has not yet been exercised against the installed package.
next_command: source /opt/ros/jazzy/setup.zsh; source /data/work/ws_moveit/install/setup.zsh; colcon --log-base /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-log build --packages-select so101_demo_py --symlink-install
```

## EXP-006 — Candidate package build and overlay provenance

```yaml
experiment_id: EXP-006
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-15T16:46:47+08:00
  - status: RUNNING
    at: 2026-09-15T16:47:27+08:00
  - status: VALID
    at: 2026-09-15T16:48:02+08:00
prior_experiment: EXP-005
hypothesis: The committed runner candidate can use a current-worktree symlink install while retaining the established /usr/bin/python3 plus Grounded-SAM dependency environment.
prediction: so101_demo_py builds successfully; ros2 package prefix and imported so101_demo origin both resolve inside this worktree.
single_variable: Build and source candidate commit e97a106a7e1b2048ade92926c8c708012b442c59; no pytest execution.
lifecycle: REUSE_STACK
preconditions:
  - Primary W10 runtime resources are absent and the prior task is COMPLETE.
  - Only this task ledger is dirty after the committed candidate.
success_criteria:
  - colcon build exits 0; current overlay package prefix is this worktree install; /usr/bin/python3 imports so101_demo from this worktree and torch from the frozen venv dependency path.
failure_criteria:
  - Build fails or any provenance path resolves to another worktree.
invalid_criteria:
  - Primary task restarts conflicting work during build or the source commit changes.
provenance:
  source_commit: e97a106a7e1b2048ade92926c8c708012b442c59
  install_overlay: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism/install
  runtime_executable: /usr/bin/python3
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - command: source /opt/ros/jazzy/setup.zsh; source /data/work/ws_moveit/install/setup.zsh; PYTHONPATH=/data/work/venvs/so101-grounded-sam/lib/python3.12/site-packages:$PYTHONPATH colcon --log-base <EVIDENCE_ROOT>/build-log build --packages-select so101_demo_py --symlink-install
    exit_code: 0
observed:
  - OBSERVED: colcon built so101_demo_py successfully in 2.40 seconds; wrapper elapsed_ms=2698.
  - OBSERVED: /usr/bin/python3 imported so101_demo from this worktree install and torch 2.13.0+cu130 from /data/work/venvs/so101-grounded-sam.
  - OBSERVED: ros2 pkg prefix so101_demo_py returned this worktree's install/so101_demo_py.
  - OBSERVED: build admission found no W10 process, container, GPU client, or active W10 unit.
inferred:
  - NONE
conclusion: The committed candidate overlay and exact Python/dependency provenance are valid for full-gate measurements.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-log
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build.log
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-SHA256SUMS
decision: KEEP
next_experiment: EXP-007-W1
```

## CP-003 — Final code candidate before measurements

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-006-PROVENANCE-CORRECTION
current_hypothesis: Final candidate 1c0ec9a7 can preserve exact W1 coverage and scale at W2/W4.
working_tree_status: clean immediately after commit 1c0ec9a7bb04bd435cf38b9af254af7a9df4667b; only this ledger becomes dirty when this checkpoint is appended
owned_processes: Codex process/session codex-task-so101-pytest-parallel only
preserved_processes: completed codex-task-so101-stateless-broker session; inert pre-existing colcon version-check process; all other worktrees and tmux sessions
confirmed_conclusions:
  - Runner implementation and exact-Python correction are committed in e97a106a7 and 1c0ec9a7.
  - All 23 final focused tests and Ruff checks pass.
disproven_routes:
  - Resolving the user-specified /usr/bin/python3 symlink before launch was rejected because it would alter the frozen command identity.
open_risks:
  - The installed package was built before the final tools/test commit and will be rebuilt once for exact candidate provenance.
next_command: source /opt/ros/jazzy/setup.zsh; source /data/work/ws_moveit/install/setup.zsh; colcon --log-base /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-log-candidate2 build --packages-select so101_demo_py --symlink-install
```

## EXP-006B-CANDIDATE-REBUILD — Final candidate overlay refresh

```yaml
experiment_id: EXP-006B-CANDIDATE-REBUILD
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-15T16:51:50+08:00
  - status: RUNNING
    at: 2026-09-15T16:52:06+08:00
  - status: VALID
    at: 2026-09-15T16:52:24+08:00
prior_experiment: EXP-006-PROVENANCE-CORRECTION
hypothesis: Rebuilding the unchanged Python package after the final test-tool commit yields an overlay with exact candidate provenance and no runtime-resource use.
prediction: Build and package/import provenance pass at commit 1c0ec9a7.
single_variable: Refresh the so101_demo_py symlink install after the final candidate commit.
lifecycle: REUSE_STACK
preconditions:
  - Candidate HEAD is 1c0ec9a7bb04bd435cf38b9af254af7a9df4667b and only the task ledger is dirty.
success_criteria:
  - Build exits 0 and package/import paths remain inside this worktree.
failure_criteria:
  - Build or provenance fails.
invalid_criteria:
  - Conflicting runtime activity or source commit drift.
provenance:
  source_commit: 1c0ec9a7bb04bd435cf38b9af254af7a9df4667b
  install_overlay: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism/install
  runtime_executable: /usr/bin/python3
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - command: colcon --log-base <EVIDENCE_ROOT>/build-log-candidate2 build --packages-select so101_demo_py --symlink-install
    exit_code: 0
observed:
  - OBSERVED: colcon build passed in 1.21 seconds; wrapper elapsed_ms=1352.
  - OBSERVED: HEAD, /usr/bin/python3, so101_demo origin, torch version, and package prefix all matched the frozen candidate environment.
inferred:
  - NONE
conclusion: The final candidate overlay is refreshed and valid for W1/W2/W4.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-candidate2.log
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-candidate2-SHA256SUMS
decision: KEEP
next_experiment: EXP-007-W1
```

## EXP-006-PROVENANCE-CORRECTION — Preserve exact Python command identity

```yaml
experiment_id: EXP-006-PROVENANCE-CORRECTION
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-15T16:49:40+08:00
  - status: RUNNING
    at: 2026-09-15T16:50:06+08:00
  - status: VALID
    at: 2026-09-15T16:50:34.216260275+08:00
prior_experiment: EXP-006
hypothesis: Keeping an absolute user-specified Python path without resolving its symlink preserves the exact /usr/bin/python3 command identity while samefile checks still verify the interpreter.
prediction: The focused suite passes 23 tests and Ruff checks pass after the correction.
single_variable: Replace Path.resolve() for the CLI Python argument with absolute-without-symlink-resolution normalization and add one regression test.
lifecycle: REUSE_STACK
preconditions:
  - W1 remains PLANNED and its scratch root is absent; no full gate has started.
  - EXP-006 package build remains valid because this correction changes only repository test tooling.
success_criteria:
  - All 23 focused tests and Ruff checks pass.
failure_criteria:
  - Any focused or static check fails.
invalid_criteria:
  - Wrong tempfile routing or unrelated source change.
provenance:
  source_commit: e97a106a7e1b2048ade92926c8c708012b442c59
  install_overlay: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism/install
  runtime_executable: /usr/bin/python3
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - command: TMPDIR=<SCRATCH>/tmp TMP=<same> TEMP=<same> ROS_HOME=<SCRATCH>/ros-home ROS_LOG_DIR=<SCRATCH>/ros-log PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider -q src/so101_demo_py/test/test_pytest_full_gate_runner.py --junitxml=<SCRATCH>/green.xml
    exit_code: 0
  - command: /home/lenovo/.local/bin/ruff check and format --check on the three runner files
    exit_code: 0
observed:
  - OBSERVED: all 23 focused tests passed in 0.04 seconds.
  - OBSERVED: Ruff check and format-check passed.
  - OBSERVED: the new regression confirms /usr/bin/python3 remains textually unchanged while relative executable paths become absolute.
inferred:
  - NONE
conclusion: Exact Python command identity is preserved without weakening samefile provenance checks.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp006-python-provenance
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp006-python-provenance/SHA256SUMS
decision: KEEP
next_experiment: EXP-007-W1
```

## EXP-007-W1 — New-runner serial baseline

```yaml
experiment_id: EXP-007-W1
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-15T16:48:25+08:00
  - status: RUNNING
    at: 2026-09-15T16:53:06+08:00
  - status: VALID
    at: 2026-09-15T16:53:47.859130522+08:00
prior_experiment: EXP-006
hypothesis: The new runner at W1 preserves the exact ordinary serial collection and provides the uncontaminated comparison baseline.
prediction: Every expected node ID appears exactly once across the ordered serial lane and one remaining shard; benchmark_test is absent; all tests pass.
single_variable: worker_count=1
lifecycle: REUSE_STACK
preconditions:
  - Candidate commit is 1c0ec9a7bb04bd435cf38b9af254af7a9df4667b and only this audit ledger is dirty.
  - Python is /usr/bin/python3; overlay is /data/work/ws_moveit/.worktrees/pytest-gate-parallelism/install; imported package provenance is inside this worktree.
  - Timing input is historical JUnit SHA256 6a12dd688dd51a0926906e0aa5c9ee1c9489f66ffdd6b5adfcec52c08eec5a21.
  - Serial lane order is test_parallel_batch_resources.py, test_text_pick_agent_e2e_process.py, test_parallel_adaptive_integration.py.
  - Scratch root /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp007-w1 does not exist before launch.
  - Fresh admission must show no conflicting pytest, ROS/MuJoCo/MoveIt/Gazebo, Docker, GPU, or W10 user-unit activity.
success_criteria:
  - Runner result PASS, every pytest process exit 0, readable JUnit and node manifest, exact nonzero node-ID union, and benchmark_test absent.
failure_criteria:
  - Any test or shard fails, times out, is killed, has invalid provenance, lacks readable JUnit, or has missing/duplicate/unexpected nodes.
invalid_criteria:
  - Admission conflict, source/overlay/Python/timing drift, scratch collision, or worktree change during the run.
provenance:
  source_commit: 1c0ec9a7bb04bd435cf38b9af254af7a9df4667b
  install_overlay: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism/install
  runtime_executable: /usr/bin/python3
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - command: tools/so101_pytest_gate.py --workers 1 --evidence-root /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01 --run-id exp007-w1 --timings /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/s38package8/package.xml --python /usr/bin/python3 --expected-source-commit 1c0ec9a7bb04bd435cf38b9af254af7a9df4667b --allow-dirty-path docs/experiments/so101-pytest-parallel-gate-experiment-ledger.md --timeout-s 1200
    exit_code: 1
observed:
  - OBSERVED: the runner failed before launching collection or test pytest processes.
  - OBSERVED: summary.json records RuntimeError with the incorrectly parsed dirty path `ocs/experiments/so101-pytest-parallel-gate-experiment-ledger.md`.
  - OBSERVED: Git porcelain actually reported ` M docs/experiments/so101-pytest-parallel-gate-experiment-ledger.md`; the generic helper's `.strip()` removed the leading worktree-status column.
inferred:
  - NONE
conclusion: W1 timing was not produced; a runner preflight defect is confirmed at porcelain-output normalization.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp007-w1
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp007-w1/summary.json
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp007-w1-SHA256SUMS
decision: KEEP
next_experiment: EXP-008-STATUS-CORRECTION
```

## EXP-008-STATUS-CORRECTION — Preserve Git porcelain columns

```yaml
experiment_id: EXP-008-STATUS-CORRECTION
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-15T16:54:10+08:00
  - status: RUNNING
    at: 2026-09-15T16:54:46+08:00
  - status: VALID
    at: 2026-09-15T16:55:12.223816525+08:00
prior_experiment: EXP-007-W1
hypothesis: Removing only trailing newlines from `git status --short` preserves its leading two-column status and permits the exact ledger allowlist without admitting code changes.
prediction: The focused suite passes 24 tests and Ruff checks pass.
single_variable: Add a porcelain-specific Git status reader and regression test.
lifecycle: REUSE_STACK
preconditions:
  - EXP-007-W1 launched no pytest and produced no timing result.
  - No conflicting primary runtime resource is active.
success_criteria:
  - All 24 focused tests and Ruff checks pass.
failure_criteria:
  - Any focused/static check fails.
invalid_criteria:
  - Wrong tempfile/Python provenance or unrelated source change.
provenance:
  source_commit: 1c0ec9a7bb04bd435cf38b9af254af7a9df4667b
  install_overlay: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism/install
  runtime_executable: /usr/bin/python3
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - command: fresh-scratch focused pytest plus Ruff check and format-check
    exit_code: 0
observed:
  - OBSERVED: all 24 focused tests passed in 0.04 seconds.
  - OBSERVED: Ruff check and format-check passed.
  - OBSERVED: the regression preserves the leading porcelain status column exactly.
inferred:
  - NONE
conclusion: The confirmed preflight defect is fixed without broadening dirty-path admission.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp008-status-correction
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp008-status-correction/SHA256SUMS
decision: KEEP
next_experiment: EXP-009-W1
```

## EXP-008B-CANDIDATE-REBUILD — Final pre-measurement overlay refresh

```yaml
experiment_id: EXP-008B-CANDIDATE-REBUILD
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-15T16:55:48+08:00
  - status: RUNNING
    at: 2026-09-15T16:56:04+08:00
  - status: INVALID
    at: 2026-09-15T16:56:43+08:00
prior_experiment: EXP-008-STATUS-CORRECTION
hypothesis: A final lightweight rebuild binds the overlay checks to committed candidate ceb41ec94f777b59a54bc51ca975e49e9443db3a.
prediction: Build and package provenance pass without runtime resource use.
single_variable: Refresh the so101_demo_py symlink install after the porcelain fix commit.
lifecycle: REUSE_STACK
preconditions:
  - HEAD is ceb41ec94f777b59a54bc51ca975e49e9443db3a and only this ledger is dirty.
success_criteria:
  - Build exits 0; exact package/Python provenance remains local.
failure_criteria:
  - Build or provenance fails.
invalid_criteria:
  - Source drift or conflicting runtime activity.
provenance:
  source_commit: ceb41ec94f777b59a54bc51ca975e49e9443db3a
  install_overlay: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism/install
  runtime_executable: /usr/bin/python3
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - command: colcon --log-base <EVIDENCE_ROOT>/build-log-candidate3 build --packages-select so101_demo_py --symlink-install
    exit_code: 0
observed:
  - OBSERVED: build and package provenance commands exited 0, but actual `git rev-parse HEAD` was ceb41ec94d09eddc1537cf24859531a033acf61f.
  - OBSERVED: the PLANNED entry incorrectly expanded short hash ceb41ec94 using invented suffix bytes rather than command readback.
inferred:
  - NONE
conclusion: Build mechanics passed but the experiment is INVALID because frozen source provenance did not equal actual HEAD.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-candidate3.log
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-candidate3-SHA256SUMS
decision: REPEAT
next_experiment: EXP-008C-CANDIDATE-REBUILD
```

## Commit provenance correction

```yaml
correction_at: 2026-09-15T16:56:43+08:00
incorrect_value: ceb41ec94f777b59a54bc51ca975e49e9443db3a
authoritative_value: ceb41ec94d09eddc1537cf24859531a033acf61f
reason: The incorrect value was inferred from the short commit prefix instead of read from git rev-parse HEAD.
scope: Header current_commit and all future experiments use the authoritative value; EXP-008B remains historically invalid and unmodified apart from status/result fields.
```

## EXP-008C-CANDIDATE-REBUILD — Exact final pre-measurement overlay refresh

```yaml
experiment_id: EXP-008C-CANDIDATE-REBUILD
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-15T16:56:43+08:00
  - status: RUNNING
    at: 2026-09-15T16:57:12+08:00
  - status: VALID
    at: 2026-09-15T16:57:28+08:00
prior_experiment: EXP-008B-CANDIDATE-REBUILD
hypothesis: Repeating the lightweight build with command-read authoritative HEAD yields valid exact candidate provenance.
prediction: Build and provenance pass at ceb41ec94d09eddc1537cf24859531a033acf61f.
single_variable: Correct the frozen source_commit value; build inputs and environment are otherwise unchanged.
lifecycle: REUSE_STACK
preconditions:
  - git rev-parse HEAD equals ceb41ec94d09eddc1537cf24859531a033acf61f; only this ledger is dirty.
success_criteria:
  - Build exits 0 and recorded HEAD/package/Python provenance matches the planned values.
failure_criteria:
  - Build or provenance fails.
invalid_criteria:
  - Source drift or conflicting runtime activity.
provenance:
  source_commit: ceb41ec94d09eddc1537cf24859531a033acf61f
  install_overlay: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism/install
  runtime_executable: /usr/bin/python3
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - command: colcon --log-base <EVIDENCE_ROOT>/build-log-candidate4 build --packages-select so101_demo_py --symlink-install
    exit_code: 0
observed:
  - OBSERVED: build passed in 1.21 seconds; wrapper elapsed_ms=1356.
  - OBSERVED: recorded HEAD exactly matched ceb41ec94d09eddc1537cf24859531a033acf61f; package, Python, and Torch provenance matched the planned environment.
inferred:
  - NONE
conclusion: Final candidate overlay provenance is valid.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-candidate4.log
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-candidate4-SHA256SUMS
decision: KEEP
next_experiment: EXP-009-W1
```

## EXP-009-W1 — Authoritative new-runner serial baseline

```yaml
experiment_id: EXP-009-W1
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-15T16:57:40+08:00
  - status: RUNNING
    at: 2026-09-15T16:58:16+08:00
  - status: VALID
    at: 2026-09-15T16:58:58+08:00
prior_experiment: EXP-007-W1
hypothesis: The corrected committed runner at W1 preserves exact ordinary collection and establishes an uncontaminated baseline.
prediction: Every expected node ID appears exactly once across the ordered serial lane and one remaining shard; benchmark_test is absent; all tests pass.
single_variable: worker_count=1
lifecycle: REUSE_STACK
preconditions:
  - Candidate HEAD is ceb41ec94d09eddc1537cf24859531a033acf61f; only the task ledger is dirty and explicitly allowlisted.
  - Exact Python, current worktree overlay, historical timing input SHA256 6a12dd688dd51a0926906e0aa5c9ee1c9489f66ffdd6b5adfcec52c08eec5a21, serial lane, and scratch root are frozen.
  - Fresh admission shows no conflicting pytest, ROS/MuJoCo/MoveIt/Gazebo, Docker, GPU, or W10 unit activity.
success_criteria:
  - PASS, exact nonzero node-ID coverage, benchmark exclusion, all JUnits readable, all process exits 0, and complete timing/resource summary.
failure_criteria:
  - Any test/process/coverage/provenance/JUnit failure.
invalid_criteria:
  - Admission conflict, source/environment drift, or scratch collision.
provenance:
  source_commit: ceb41ec94d09eddc1537cf24859531a033acf61f
  install_overlay: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism/install
  runtime_executable: /usr/bin/python3
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - command: tools/so101_pytest_gate.py --workers 1 --evidence-root /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01 --run-id exp009-w1 --timings /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/s38package8/package.xml --python /usr/bin/python3 --expected-source-commit ceb41ec94d09eddc1537cf24859531a033acf61f --allow-dirty-path docs/experiments/so101-pytest-parallel-gate-experiment-ledger.md --timeout-s 1200
    exit_code: 1
observed:
  - OBSERVED: collection pytest exited 0, wrote readable JUnit and manifest, and collected 3051 ordinary nodes with hash 862237d395aa3b3fe3e713ccbc927fafd1d838e34b3aac6c6c68d130a6ebb5c8.
  - OBSERVED: no test-execution process launched; the runner rejected `test/test_test_suite_partition.py::test_low_frequency_benchmark_tests_are_outside_default_package_suite` because it searched the full node ID for the benchmark directory token.
  - OBSERVED: the path portion was `test/test_test_suite_partition.py`, so this is an ordinary test whose function name describes benchmark exclusion.
inferred:
  - NONE
conclusion: W1 timing was not produced; benchmark isolation must inspect path components only, not test names or parameter IDs.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp009-w1
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp009-w1/collection/nodeids.json
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp009-w1/summary.json
decision: KEEP
next_experiment: EXP-010-BENCHMARK-PATH-CORRECTION
```

## EXP-010-BENCHMARK-PATH-CORRECTION — Path-scoped benchmark exclusion

```yaml
experiment_id: EXP-010-BENCHMARK-PATH-CORRECTION
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-15T16:59:20+08:00
  - status: RUNNING
    at: 2026-09-15T16:59:49+08:00
  - status: VALID
    at: 2026-09-15T17:00:17.110653458+08:00
prior_experiment: EXP-009-W1
hypothesis: Checking only the node ID's file-path components rejects benchmark_test directories without rejecting ordinary test names that mention benchmark isolation.
prediction: The focused suite passes 25 tests and Ruff checks pass.
single_variable: Scope benchmark detection to the node file path and add one regression.
lifecycle: REUSE_STACK
preconditions:
  - EXP-009-W1 executed collection only and no test modules.
success_criteria:
  - All 25 focused tests and Ruff checks pass.
failure_criteria:
  - Any focused/static check fails.
invalid_criteria:
  - Wrong Python/tempfile provenance or unrelated source change.
provenance:
  source_commit: ceb41ec94d09eddc1537cf24859531a033acf61f
  install_overlay: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism/install
  runtime_executable: /usr/bin/python3
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - command: fresh-scratch focused pytest plus Ruff check and format-check
    exit_code: 0
observed:
  - OBSERVED: all 25 focused tests passed in 0.05 seconds.
  - OBSERVED: Ruff check and format-check passed.
inferred:
  - NONE
conclusion: Benchmark exclusion now distinguishes directory ownership from ordinary test names.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp010-benchmark-path
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp010-benchmark-path/SHA256SUMS
decision: KEEP
next_experiment: EXP-011-W1
```
