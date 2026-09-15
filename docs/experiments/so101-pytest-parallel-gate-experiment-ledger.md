---
task_id: so101-pytest-parallel-gate
goal: Reduce wall-clock time of the complete ordinary src/so101_demo_py/test pytest gate without changing coverage, semantics, failure criteria, benchmark isolation, or evidence quality.
success_contract: A repository-maintained deterministic runner passes focused RED/GREEN tests, proves exact node-ID coverage and benchmark exclusion, and produces uncontaminated W1/W2/W4 measurements on one committed candidate; the fastest valid mode is selected.
worktree: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism
branch: codex/pytest-gate-parallelism
base_commit: b0f9e7168198285fba4133026d9d3b132075f88b
current_commit: b0f9e7168198285fba4133026d9d3b132075f88b
evidence_root: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01
confirmed_conclusions:
  - The required base is the current HEAD and the worktree was clean at dispatch (CP-001).
  - Full-gate timing is currently inadmissible because the preserved primary stateless-Broker task owns W10 MuJoCo, ROS, Docker, GPU, and user-service resources (CP-001).
disproven_routes:
  - Running W1/W2/W4 while the primary task is active is rejected as contaminated by the handoff's admission gate (CP-001).
open_hypotheses:
  - Deterministic file-level LPT sharding can preserve exact ordinary-gate coverage and reduce critical-path wall time.
  - Additional source-evidenced global-resource owners may need the serial lane beyond the two mandatory modules.
latest_checkpoint: CP-001
next_experiment: EXP-005
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
