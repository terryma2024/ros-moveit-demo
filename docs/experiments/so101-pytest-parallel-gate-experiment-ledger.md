---
task_id: so101-pytest-parallel-gate
goal: Minimize wall-clock time of the complete ordinary src/so101_demo_py/test pytest gate without changing its collected cases or pass/fail semantics, with default startup concurrency set to 8.
success_contract: Omitting --workers selects pytest subprocess concurrency 8 while explicit overrides remain supported; focused RED/GREEN and a fresh full ordinary pytest run pass before merging into codex/parallel-adaptive-worker-pool.
worktree: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism
branch: codex/pytest-gate-parallelism
base_commit: b0f9e7168198285fba4133026d9d3b132075f88b
current_commit: ae62559645c1a045c53bf5c376a0ef6e8e67343e
evidence_root: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01
confirmed_conclusions:
  - The required base is the current HEAD and the worktree was clean at dispatch (CP-001).
  - Full-gate timing is currently inadmissible because the preserved primary stateless-Broker task owns W10 MuJoCo, ROS, Docker, GPU, and user-service resources (CP-001).
  - The primary task reached COMPLETE and released its runtime resources; fresh admission at 2026-09-15T16:43:26+08:00 found no W10 processes, containers, GPU clients, or active W10 units (CP-002).
  - Exact /usr/bin/python3 command identity is preserved by candidate commit 1c0ec9a7bb04bd435cf38b9af254af7a9df4667b (EXP-006-PROVENANCE-CORRECTION).
  - Candidate e81286bf5aa465168d7d611de349635cbcae8a9e has 27 focused runner contracts GREEN and isolates five source-evidenced sensitive modules (EXP-018-ISOLATION-RED-GREEN).
  - EXP-019 completed normally with exit 1; it is INVALID for timing because a 108-byte Unix-socket path failed and its manifests expose 19 nested ordinary nodes omitted by top-level-only module discovery (EXP-019-W1 result update).
  - A 12-hex physical identity plus a pre-run 107-byte AF_UNIX budget gate fixes the reproduced socket-path boundary with 28 focused contracts GREEN (EXP-020-LAYOUT-BUDGET-RED-GREEN).
  - Recursive deterministic ordinary-module discovery includes nested contract and characterization tests while preserving benchmark exclusion, with 28 focused contracts GREEN (EXP-021-RECURSIVE-DISCOVERY-RED-GREEN).
  - Candidate 1d18b088a87aaa8b6fb2b09bcfa1995325dd801d passes 28 focused contracts and has a fresh dependency-complete merged overlay with exact package/import provenance (EXP-022-CANDIDATE-FOCUSED-AND-BUILD).
  - EXP-023 passed exact 3055-node W1 correctness and cleanup, but its timing sample is INVALID because indented GNU-time labels produced null per-process CPU/RSS metrics (EXP-023 result update).
  - Indented GNU-time resource labels parse exactly after a one-regex correction, with 29 focused contracts GREEN (EXP-024-RESOURCE-METRICS-RED-GREEN).
  - Candidate dab91e3d615d4be61a2414695877910d2c5808ab passes 29 focused contracts and has exact refreshed overlay provenance (EXP-025-CANDIDATE-REFRESH).
  - Pytest concurrency 4 passes all 3056 ordinary nodes in 189.788 seconds, with exact coverage and complete cleanup (EXP-027-PYTEST-P4).
  - Pytest concurrency 6 with fresh timing input passes all 3056 nodes in 99.225 seconds, but a remaining 82.971-second straggler warrants concurrency 8 (EXP-028-PYTEST-P6).
  - Pytest concurrency 8 passes all 3056 nodes in 59.291 seconds; its 43.099-second straggler and fresh timing estimate warrant one bounded concurrency-10 run (EXP-029-PYTEST-P8).
  - Pytest concurrency 10 passes all 3056 nodes in 27.072 seconds; one concurrency-12 run will test the predeclared 10-percent stopping boundary (EXP-030-PYTEST-P10).
  - Pytest concurrency 12 passes all 3056 nodes in 27.952 seconds but is 3.249 percent slower than concurrency 10; select concurrency 10 and stop expansion (EXP-031-PYTEST-P12, CP-007).
  - Omitting --workers selects concurrency 8, while an explicit value still overrides it; the focused contract completed RED then 31/31 GREEN (EXP-032-DEFAULT-P8-TDD).
  - Commit ae62559645c1a045c53bf5c376a0ef6e8e67343e passes all 3058 ordinary pytest nodes when launched without --workers and records worker_count 8 (EXP-035-DEFAULT-P8-FULL-RETRY).
disproven_routes:
  - Running W1/W2/W4 while the primary task is active is rejected as contaminated by the handoff's admission gate (CP-001).
  - SO-101 application Worker W1-W10 correctness validation is explicitly outside the resumed pytest-only optimization scope.
open_hypotheses:
  - The existing required --workers argument can become an optional default of 8 without changing explicit override behavior or full-gate semantics (EXP-032-DEFAULT-P8-TDD).
latest_checkpoint: CP-008
next_experiment: EXP-036-MERGE
---

# SO-101 pytest parallel gate experiment ledger

## Evidence registration

- Registered durable evidence root: `/data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01`
- Dispatch receipt: `/data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/handoff/dispatch-b2bba2a8-3e03-4d03-abbb-af88915ac4d1.receipt`
- Corrected-scope dispatch receipt: `/data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/handoff/dispatch-3ACD66BD-3894-4671-AD70-AA3FE36DDFC4.receipt`
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

## CP-004 — Final corrected measurement candidate

```yaml
checkpoint_id: CP-004
last_valid_experiment: EXP-010-BENCHMARK-PATH-CORRECTION
current_hypothesis: Candidate de1e0aa03b2dfec402f028f9497a037c89935842 will pass exact W1 coverage and scale at W2/W4.
working_tree_status: clean immediately after commit de1e0aa03b2dfec402f028f9497a037c89935842; only this ledger becomes dirty on append
owned_processes: Codex process/session only; no pytest process remains from collection-only diagnostics
preserved_processes: completed stateless-Broker Codex session; inert pre-existing colcon version-check process; all other worktrees and sessions
confirmed_conclusions:
  - 25 focused tests and Ruff checks pass.
  - Prior W1 attempts started no test-execution process and are excluded from timing comparison.
disproven_routes:
  - Generic stripped porcelain output and full-node-ID benchmark substring matching are fixed and regression-tested.
open_risks:
  - Full test execution has not yet completed through the runner.
next_command: fresh admission then tools/so101_pytest_gate.py --workers 1 with run-id exp011-w1
```

## EXP-011-W1 — Authoritative new-runner W1 baseline

```yaml
experiment_id: EXP-011-W1
status: RUNNING
status_history:
  - status: PLANNED
    at: 2026-09-15T17:00:45+08:00
  - status: RUNNING
    at: 2026-09-15T17:01:31+08:00
prior_experiment: EXP-009-W1
hypothesis: Corrected candidate de1e0aa0 preserves exact ordinary collection and provides a valid W1 baseline.
prediction: All expected node IDs execute exactly once across the serial lane and one shard, all tests pass, and benchmark paths remain absent.
single_variable: worker_count=1
lifecycle: REUSE_STACK
preconditions:
  - HEAD is de1e0aa03b2dfec402f028f9497a037c89935842; only the exact task-ledger path is dirty and allowlisted.
  - Python, overlay, timing JUnit hash, serial lane, and fresh scratch are frozen as in EXP-009 except for the corrected committed runner.
  - Fresh admission must be conflict-free.
success_criteria:
  - PASS with exact nonzero node-ID union, benchmark exclusion, all process exits/JUnits/provenance valid, and complete timing/resource summary.
failure_criteria:
  - Any test, process, coverage, provenance, or JUnit gate fails.
invalid_criteria:
  - Admission conflict, source/environment drift, or scratch collision.
provenance:
  source_commit: de1e0aa03b2dfec402f028f9497a037c89935842
  install_overlay: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism/install
  runtime_executable: /usr/bin/python3
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - command: tools/so101_pytest_gate.py --workers 1 --evidence-root /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01 --run-id exp011-w1 --timings /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/s38package8/package.xml --python /usr/bin/python3 --expected-source-commit de1e0aa03b2dfec402f028f9497a037c89935842 --allow-dirty-path docs/experiments/so101-pytest-parallel-gate-experiment-ledger.md --timeout-s 1200
    exit_code: PENDING
observed:
  - PENDING
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp011-w1
decision: PENDING
next_experiment: EXP-012-W2
```

### EXP-011 result update

```yaml
status: VALID
status_history:
  - status: VALID
    at: 2026-09-15T17:05:57+08:00
commands:
  - command: tools/so101_pytest_gate.py --workers 1 --evidence-root /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01 --run-id exp011-w1 --timings /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/s38package8/package.xml --python /usr/bin/python3 --expected-source-commit de1e0aa03b2dfec402f028f9497a037c89935842 --allow-dirty-path docs/experiments/so101-pytest-parallel-gate-experiment-ledger.md --timeout-s 1200
    exit_code: 1
observed:
  - OBSERVED: collection passed and produced 3051 ordinary node IDs; benchmark-path exclusion passed.
  - OBSERVED: the serial lane ran first and stopped the gate after 156 passed and 1 failed in 7.30 seconds; no parallel shard started.
  - OBSERVED: test_parallel_batch_resources.py::test_production_cli_composes_three_workers_with_current_accepted_headroom raised TRUSTED_FINAL_TARGET_INVALID.
  - OBSERVED: so101_demo resolved to the copied overlay path install/so101_demo_py/lib/python3.12/site-packages/so101_demo, so Path(__file__).parents[2] did not contain the package-relative config expected by the contract test.
inferred:
  - INFERRED: this build's setuptools fallback from editable/develop to full install changed import layout relative to the historical accepted baseline, whose so101_demo import resolved through a source-tree symlink.
conclusion: The runner failed closed correctly, but this run cannot serve as a W1 performance baseline because the frozen environment did not reproduce the established source-import layout.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp011-w1
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp011-w1/serial/pytest.log
decision: EXCLUDE_FROM_TIMING_COMPARISON
next_experiment: EXP-012-SOURCE-IMPORT-PROVENANCE
```

## EXP-012-SOURCE-IMPORT-PROVENANCE — Restore established source import layout

```yaml
experiment_id: EXP-012-SOURCE-IMPORT-PROVENANCE
status: PLANNED
prior_experiment: EXP-011-W1
hypothesis: A task-owned PYTHONPATH shim that points so101_demo at this worktree's source tree restores the historical import semantics without modifying source, install artifacts, or any other worktree.
prediction: The previously failing serial-lane node passes with so101_demo.__file__ resolving inside this worktree's src/so101_demo_py/src tree.
single_variable: Prepend a task-owned source-import shim to PYTHONPATH.
lifecycle: REUSE_STACK
preconditions:
  - Candidate commit remains de1e0aa03b2dfec402f028f9497a037c89935842 and only this ledger is dirty.
  - The shim is created under the registered evidence root and targets only the current worktree source tree.
success_criteria:
  - Exact /usr/bin/python3 tempfile verification passes; import provenance resolves to current source; the one previously failing test passes with readable JUnit.
failure_criteria:
  - Import provenance remains installed-copy based or the focused test fails.
invalid_criteria:
  - Scratch collision, source/environment drift, or admission conflict.
provenance:
  source_commit: de1e0aa03b2dfec402f028f9497a037c89935842
  install_overlay: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism/install
  runtime_executable: /usr/bin/python3
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - PENDING
observed:
  - PENDING
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/runtime-python
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp012-source-import
decision: PENDING
next_experiment: EXP-013-W1
```

### EXP-012 result update

```yaml
status: INVALID
status_history:
  - status: RUNNING
    at: 2026-09-15T17:08:00+08:00
  - status: INVALID
    at: 2026-09-15T17:08:07+08:00
commands:
  - command: create task-owned runtime-python/so101_demo symlink; verify exact-Python tempfile and import; run the previously failing node under scratch/exp012-source-import
    exit_code: 1
observed:
  - OBSERVED: /usr/bin/python3 tempfile provenance passed and so101_demo.__file__ resolved to the current worktree source through the task-owned shim.
  - OBSERVED: the trusted-final-target setup passed, disproving the copied-install failure mechanism from EXP-011.
  - OBSERVED: the test then failed before its assertion because the 108-byte fixture Unix socket path exceeded the 107-byte kernel/library guard.
inferred:
  - NONE
conclusion: Source-import provenance is corrected, but this diagnostic scratch identifier is too long for the suite's explicit Unix-socket constraint.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/runtime-python/so101_demo
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/exp012-source-import
decision: RETAIN_INVALID_DIAGNOSTIC
next_experiment: EXP-013-SHORT-SCRATCH-PROVENANCE
```

## EXP-013-SHORT-SCRATCH-PROVENANCE — Verify source import with short durable scratch

```yaml
experiment_id: EXP-013-SHORT-SCRATCH-PROVENANCE
status: PLANNED
prior_experiment: EXP-012-SOURCE-IMPORT-PROVENANCE
hypothesis: Using a unique short identifier under the same registered durable scratch root keeps fixture socket paths below 107 bytes while preserving all mandated /data tempfile provenance.
prediction: The exact tempfile and source-import preflight passes and the previously failing node passes.
single_variable: Shorten the task-owned scratch identifier from exp012-source-import/tmp to p/t.
lifecycle: REUSE_STACK
preconditions:
  - Candidate, overlay, Python, source-import shim, and focused node are unchanged.
  - scratch/p does not exist before the experiment.
success_criteria:
  - Preflight passes, the node passes, JUnit is readable, and the measured socket fixture prefix is below 107 bytes.
failure_criteria:
  - Test failure or invalid JUnit/provenance.
invalid_criteria:
  - Scratch collision or source/environment drift.
provenance:
  source_commit: de1e0aa03b2dfec402f028f9497a037c89935842
  install_overlay: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism/install
  runtime_executable: /usr/bin/python3
commands:
  - PENDING
observed:
  - PENDING
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/p
decision: PENDING
next_experiment: EXP-014-W1
```

### EXP-013 result update

```yaml
status: VALID
status_history:
  - status: RUNNING
    at: 2026-09-15T17:12:30+08:00
  - status: VALID
    at: 2026-09-15T17:12:32+08:00
commands:
  - command: exact-Python tempfile/source/socket-length preflight then the previously failing node with JUnit under scratch/p
    exit_code: 0
observed:
  - OBSERVED: tempfile.gettempdir() resolved to the registered /data scratch, so101_demo resolved to the current worktree source, and the representative socket path was 89 bytes.
  - OBSERVED: the previously failing node passed in 0.50 seconds and JUnit was readable.
inferred:
  - NONE
conclusion: The established source-import semantics and short durable scratch layout are suitable for the frozen full-gate measurements.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/p
decision: KEEP
next_experiment: EXP-014-W1
```

## EXP-014-W1 — Authoritative W1 baseline with corrected provenance

```yaml
experiment_id: EXP-014-W1
status: RUNNING
status_history:
  - status: PLANNED
    at: 2026-09-15T17:14:00+08:00
  - status: RUNNING
    at: 2026-09-15T17:15:00+08:00
prior_experiment: EXP-013-SHORT-SCRATCH-PROVENANCE
hypothesis: Candidate de1e0aa0 passes exact ordinary coverage in deterministic serial-plus-one-shard mode under the established source-import layout.
prediction: All 3051 expected node IDs execute exactly once, all subprocess/JUnit/provenance gates pass, and benchmark paths are absent.
single_variable: worker_count=1
lifecycle: REUSE_STACK
preconditions:
  - HEAD is de1e0aa03b2dfec402f028f9497a037c89935842 and only this task ledger is dirty/allowlisted.
  - Python=/usr/bin/python3; current overlay is sourced; PYTHONPATH prepends the task-owned current-source shim; historical timing JUnit and serial lane are frozen.
  - Fresh run ID a is previously nonexistent; its process scratch paths keep representative fixture sockets below 107 bytes.
  - Admission proves no conflicting primary-task pytest, ROS, simulation, Docker, GPU, or active-unit workload.
success_criteria:
  - PASS with exact nonzero node-ID union, benchmark exclusion, zero process/test failures, readable JUnits, valid provenance, cleanup readback, and complete timing/resource summary.
failure_criteria:
  - Any process, test, exact-coverage, JUnit, provenance, timeout, or cleanup failure.
invalid_criteria:
  - Admission conflict, source/environment drift, or scratch collision.
provenance:
  source_commit: de1e0aa03b2dfec402f028f9497a037c89935842
  install_overlay: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism/install
  runtime_executable: /usr/bin/python3
  runtime_source_shim: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/runtime-python
  timing_input_sha256: 6a12dd688dd51a0926906e0aa5c9ee1c9489f66ffdd6b5adfcec52c08eec5a21
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - PENDING
observed:
  - PENDING
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/admission-exp014-w1.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/a
decision: PENDING
next_experiment: EXP-015-W2
```

### EXP-014 result update

```yaml
status: INVALID
status_history:
  - status: INVALID
    at: 2026-09-15T17:28:00+08:00
commands:
  - command: tools/so101_pytest_gate.py --workers 1 --evidence-root /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01 --run-id a --timings /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/s38package8/package.xml --python /usr/bin/python3 --expected-source-commit de1e0aa03b2dfec402f028f9497a037c89935842 --allow-dirty-path docs/experiments/so101-pytest-parallel-gate-experiment-ledger.md --timeout-s 1200
    exit_code: 1
observed:
  - OBSERVED: collection and the 157-test ordered serial lane passed; the one parallel shard completed 2869 passed, 7 failed, 4 warnings in 742.01 seconds.
  - OBSERVED: four failures read the uninitialized third_party/mujoco_ros2_control gitlink; git submodule status was -c16b5a5f and the directory was empty.
  - OBSERVED: two installed-provenance failures showed so101_mujoco_support resolved to /data/work/ws_moveit/install and mujoco_ros2_control to /opt/ros/jazzy instead of this worktree overlay.
  - OBSERVED: one timing-sensitive worker heartbeat test failed independently; it requires focused readback after environment repair.
  - OBSERVED: the runner stopped with a fail-closed summary; all owned subprocesses exited and full JUnit/resource evidence was retained.
inferred:
  - NONE
conclusion: This is not a valid W1 baseline because the pinned submodule and full dependency overlay preconditions were not satisfied.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/a
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp014-w1-outer-time.txt
decision: EXCLUDE_FROM_TIMING_COMPARISON
next_experiment: EXP-015-CURRENT-OVERLAY-REPAIR
```

## EXP-015-CURRENT-OVERLAY-REPAIR — Initialize pinned fork and build dependency-complete overlay

```yaml
experiment_id: EXP-015-CURRENT-OVERLAY-REPAIR
status: PLANNED
prior_experiment: EXP-014-W1
hypothesis: Initializing the recorded gitlink and building the candidate worktree's dependency packages makes every install-contract prefix and fork path resolve within the current candidate.
prediction: The pinned submodule is at c16b5a5f; dependency prefix probes resolve within this worktree; the six environment-caused failing nodes pass.
single_variable: Repair the incomplete current-worktree submodule/build environment; source commit and runner remain unchanged.
lifecycle: REBUILD_STACK
preconditions:
  - Pinned submodule objects are available locally or fetched without changing another worktree.
  - Build and install outputs are confined to this worktree; build logs use this registered evidence root.
success_criteria:
  - Submodule and prefix provenance pass and all six environment-caused nodes pass from fresh NVMe scratch with readable JUnit.
failure_criteria:
  - Initialization/build/provenance/focused tests fail.
invalid_criteria:
  - Source commit changes, unrelated worktree changes, or primary-task activity resumes.
provenance:
  source_commit: de1e0aa03b2dfec402f028f9497a037c89935842
  runtime_executable: /usr/bin/python3
commands:
  - PENDING
observed:
  - PENDING
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-log-exp015
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/q
decision: PENDING
next_experiment: EXP-016-HEARTBEAT-READBACK
```

### EXP-015 result update

```yaml
status: VALID
status_history:
  - status: RUNNING
    at: 2026-09-15T17:32:00+08:00
  - status: VALID
    at: 2026-09-15T17:35:00+08:00
commands:
  - command: git submodule update --init --recursive third_party/mujoco_ros2_control
    exit_code: 0
  - command: initial scoped five-package build
    exit_code: 1
  - command: dependency-closure colcon build --symlink-install with Linux system mujoco_vendor
    exit_code: 0
  - command: exact-Python/prefix preflight and three environment-sensitive test modules under scratch/q
    exit_code: 0
observed:
  - OBSERVED: the pinned gitlink initialized at c16b5a5fe880b6e1857f56486dab4ae726576969 without changing the superproject source commit.
  - OBSERVED: the initial scoped build fail-closed because mujoco_3d_lidar was not selected; the dependency-closure build then completed 7 packages in 55.5 seconds.
  - OBSERVED: so101_demo_py, so101_mujoco_support, mujoco_ros2_control, mujoco_ros2_control_plugins, and mujoco_ros2_control_msgs all resolve inside this worktree's install tree; so101_demo resolves inside its source tree.
  - OBSERVED: all 28 tests across the three previously environment-failing modules passed in 6.12 seconds with readable JUnit.
inferred:
  - NONE
conclusion: The current-worktree submodule and dependency-complete overlay are now valid for measurement.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-log-exp015
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-log-exp015-closure
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/q
decision: KEEP
next_experiment: EXP-016-HEARTBEAT-READBACK
```

## EXP-016-HEARTBEAT-READBACK — Recheck isolated timing-sensitive failure

```yaml
experiment_id: EXP-016-HEARTBEAT-READBACK
status: PLANNED
prior_experiment: EXP-015-CURRENT-OVERLAY-REPAIR
hypothesis: The single worker-heartbeat failure in the invalid 12-minute environment run was transient scheduling jitter rather than a deterministic candidate defect.
prediction: The exact node passes repeatedly in one fresh process under the corrected frozen overlay.
single_variable: Re-run only the isolated node three times through pytest parametrized repetition by three explicit invocations in separate fresh processes.
lifecycle: REUSE_STACK
preconditions:
  - Corrected submodule/overlay provenance from EXP-015 remains unchanged.
  - Each invocation uses a distinct previously nonexistent /data scratch directory.
success_criteria:
  - All three invocations pass with readable JUnit and exact-Python tempfile preflight.
failure_criteria:
  - Any invocation reproduces the failure.
invalid_criteria:
  - Scratch collision or environment/source drift.
provenance:
  source_commit: de1e0aa03b2dfec402f028f9497a037c89935842
  runtime_executable: /usr/bin/python3
commands:
  - PENDING
observed:
  - PENDING
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/r1
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/r2
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/r3
decision: PENDING
next_experiment: EXP-017-W1
```

### EXP-016 result update

```yaml
status: VALID
status_history:
  - status: RUNNING
    at: 2026-09-15T17:36:00+08:00
  - status: VALID
    at: 2026-09-15T17:36:02+08:00
commands:
  - command: three separate exact-node pytest invocations under fresh scratch/r1, r2, and r3
    exit_code: 0
observed:
  - OBSERVED: all three separate processes passed the node in 0.18, 0.18, and 0.17 seconds with exact-Python tempfile preflight and readable JUnit.
inferred:
  - INFERRED: the one failure inside invalid EXP-014 was transient scheduling jitter during a non-authoritative environment run, not a deterministic candidate defect.
conclusion: The node is stable across three corrected-environment readbacks; no test semantic or timeout change is justified.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/r1
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/r2
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/r3
decision: KEEP_TEST_UNCHANGED
next_experiment: EXP-017-W1
```

## EXP-017-W1 — Authoritative corrected-environment W1 baseline

```yaml
experiment_id: EXP-017-W1
status: RUNNING
status_history:
  - status: PLANNED
    at: 2026-09-15T17:28:30+08:00
  - status: RUNNING
    at: 2026-09-15T17:29:00+08:00
prior_experiment: EXP-016-HEARTBEAT-READBACK
hypothesis: The unchanged committed runner passes the complete 3051-node ordinary gate at W1 with the now-complete candidate overlay.
prediction: Exact once-only coverage, all-pass JUnits/provenance, and a complete W1 resource/timing summary.
single_variable: worker_count=1
lifecycle: REUSE_STACK
preconditions:
  - Commit de1e0aa03b2dfec402f028f9497a037c89935842, timing JUnit, Python, serial lane, source shim, and dependency-complete overlay are frozen.
  - Submodule is initialized at the pinned gitlink and only the task ledger is dirty.
  - Fresh run ID b is absent and fresh admission is conflict-free.
success_criteria:
  - PASS with exact nonzero node-ID union, zero missing/duplicate/unexpected IDs, benchmark exclusion, all subprocess/JUnit/provenance gates, cleanup readback, and timing/resource summary.
failure_criteria:
  - Any process, test, coverage, JUnit, provenance, timeout, or cleanup failure.
invalid_criteria:
  - Admission conflict, source/environment drift, or scratch collision.
provenance:
  source_commit: de1e0aa03b2dfec402f028f9497a037c89935842
  install_overlay: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism/install
  runtime_executable: /usr/bin/python3
  runtime_source_shim: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/runtime-python
  timing_input_sha256: 6a12dd688dd51a0926906e0aa5c9ee1c9489f66ffdd6b5adfcec52c08eec5a21
commands:
  - PENDING
observed:
  - PENDING
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/admission-exp017-w1.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/b
decision: PENDING
next_experiment: EXP-018-W2
```

### EXP-017 result update

```yaml
status: INVALID
status_history:
  - status: INVALID
    at: 2026-09-15T17:42:45+08:00
commands:
  - command: tools/so101_pytest_gate.py --workers 1 --evidence-root /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01 --run-id b --timings /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/s38package8/package.xml --python /usr/bin/python3 --expected-source-commit de1e0aa03b2dfec402f028f9497a037c89935842 --allow-dirty-path docs/experiments/so101-pytest-parallel-gate-experiment-ledger.md --timeout-s 1200
    exit_code: 1
observed:
  - OBSERVED: the dependency-complete overlay eliminated all six provenance/fork failures from EXP-014.
  - OBSERVED: the shard completed 2874 passed, 2 failed, 4 warnings in 781.39 seconds; outer elapsed was 796.03 seconds at 103 percent CPU and 2731296 KiB peak RSS.
  - OBSERVED: test_parallel_batch_worker.py reproduced its deadline-sensitive background-heartbeat failure only after earlier LPT-ordered modules, despite three isolated passes.
  - OBSERVED: test_inject_so101_parallel_fault.py collided with a prior run because its fixture derives an external scratch key from TMPDIR.parent.name, while every runner invocation used the repeated physical name shard-01.
  - OBSERVED: no other tests failed; the runner retained complete JUnit and failed closed.
inferred:
  - NONE
conclusion: W1 is invalid for comparison; source evidence requires serial-first placement for the load-sensitive worker module and the shared-filesystem fault-injector module, plus a unique bounded physical process directory identity across gate runs.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/b
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp017-w1-outer-time.txt
decision: EXCLUDE_FROM_TIMING_COMPARISON
next_experiment: EXP-018-ISOLATION-RED-GREEN
```

## EXP-018-ISOLATION-RED-GREEN — Complete source-evidenced isolation classification

```yaml
experiment_id: EXP-018-ISOLATION-RED-GREEN
status: PLANNED
prior_experiment: EXP-017-W1
hypothesis: Whole-module serial-first isolation for the deadline-sensitive worker tests and shared-filesystem fault-injector tests, combined with run-unique bounded physical process directory names, removes both reproduced interactions without weakening semantics.
prediction: New focused contracts fail before implementation, then the complete runner-focused suite and Ruff pass after the narrow implementation.
single_variable: Add the two source-evidenced serial classifications and deterministic run-unique physical layout identity.
lifecycle: REUSE_STACK
preconditions:
  - Production code and ordinary test semantics remain unchanged.
  - Only the runner, its focused contract tests, and this ledger may change.
success_criteria:
  - Recorded RED failure; GREEN focused suite; deterministic distinct physical identities for the same logical process across separate run roots; both modules excluded from shards.
failure_criteria:
  - Focused or static checks fail after implementation.
invalid_criteria:
  - Wrong tempfile provenance, unrelated source drift, or scratch collision.
provenance:
  source_commit: de1e0aa03b2dfec402f028f9497a037c89935842
  runtime_executable: /usr/bin/python3
commands:
  - PENDING
observed:
  - PENDING
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/s
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/t
decision: PENDING
next_experiment: EXP-019-W1
```

### EXP-018 result update

```yaml
status: VALID
status_history:
  - status: RUNNING
    at: 2026-09-15T17:44:00+08:00
  - status: VALID
    at: 2026-09-15T17:46:00+08:00
commands:
  - command: focused runner suite before implementation under scratch/s
    exit_code: 1
  - command: focused runner suite plus Ruff check/format after implementation under scratch/t
    exit_code: 0
  - command: local commit e81286bf5aa465168d7d611de349635cbcae8a9e
    exit_code: 0
  - command: candidate-only so101_demo_py rebuild against dependency-complete overlay
    exit_code: 0
observed:
  - OBSERVED: RED produced exactly two failures: missing source-evidenced serial membership and repeated physical process basename across separate run roots.
  - OBSERVED: GREEN passed all 27 focused tests in 0.05 seconds; Ruff check and format-check passed.
  - OBSERVED: physical directory names are deterministic p- plus a 12-hex digest of absolute run root and logical process name; logical process names and summary semantics remain unchanged.
  - OBSERVED: the refreshed so101_demo_py build completed in develop/symlink mode in 1.42 seconds and records candidate commit e81286bf5aa465168d7d611de349635cbcae8a9e.
inferred:
  - NONE
conclusion: The complete source-evidenced isolation policy and cross-run scratch identity are committed and focused-verified without changing production or test semantics.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/s
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/t
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-log-exp018-candidate
decision: KEEP
next_experiment: EXP-019-W1
```

## EXP-019-W1 — Frozen final-candidate W1 baseline

```yaml
experiment_id: EXP-019-W1
status: RUNNING
status_history:
  - status: PLANNED
    at: 2026-09-15T17:47:00+08:00
  - status: RUNNING
    at: 2026-09-15T17:48:00+08:00
prior_experiment: EXP-018-ISOLATION-RED-GREEN
hypothesis: Final candidate e81286bf passes the exact complete ordinary gate at W1 with every source-evidenced sensitive module in the ordered serial lane.
prediction: All 3051 expected nodes execute exactly once with zero failures and a complete summary.
single_variable: worker_count=1
lifecycle: REUSE_STACK
preconditions:
  - Commit e81286bf5aa465168d7d611de349635cbcae8a9e, /usr/bin/python3, dependency-complete overlay, source shim, historical timing input, and five-module serial lane are frozen.
  - Pinned submodule is initialized and only this task ledger is dirty/allowlisted.
  - Fresh run ID c is absent and admission is conflict-free.
success_criteria:
  - PASS; exact nonzero once-only coverage; benchmark exclusion; zero process/test/provenance/JUnit failures; cleanup readback; full timing/resource summary.
failure_criteria:
  - Any process, test, coverage, provenance, JUnit, timeout, or cleanup failure.
invalid_criteria:
  - Admission conflict, source/environment drift, or scratch collision.
provenance:
  source_commit: e81286bf5aa465168d7d611de349635cbcae8a9e
  install_overlay: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism/install
  runtime_executable: /usr/bin/python3
  runtime_source_shim: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/runtime-python
  timing_input_sha256: 6a12dd688dd51a0926906e0aa5c9ee1c9489f66ffdd6b5adfcec52c08eec5a21
commands:
  - PENDING
observed:
  - PENDING
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/admission-exp019-w1.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/c
decision: PENDING
next_experiment: EXP-020-W2
```

### EXP-019 result update

```yaml
status: INVALID
status_history:
  - status: INVALID
    at: 2026-09-15T20:08:23+08:00
commands:
  - command: tools/so101_pytest_gate.py --workers 1 --evidence-root /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01 --run-id c --timings /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/s38package8/package.xml --python /usr/bin/python3 --expected-source-commit e81286bf5aa465168d7d611de349635cbcae8a9e --allow-dirty-path docs/experiments/so101-pytest-parallel-gate-experiment-ledger.md --timeout-s 1200
    exit_code: 1
observed:
  - OBSERVED: The runner command completed normally rather than being killed or externally interrupted; `/usr/bin/time` recorded exit status 1, 736.00 seconds wall time, 103 percent CPU, and 2649688 KiB peak RSS.
  - OBSERVED: The ordered five-module serial lane passed 306 tests in 10.51 seconds and its ownership document records `state=EXITED`, `returncode=0`, and `cleanup_readback=0`.
  - OBSERVED: Shard 1 completed 2729 collected tests as 2728 passed and 1 failed in 718.33 seconds; the failure was `test_parallel_ipc.py::test_client_rejects_wrong_response_schema_and_union`, where `layout.root/ipc-response/s` was 108 bytes and `socket.bind()` raised `OSError: AF_UNIX path too long`.
  - OBSERVED: Shard ownership records `state=EXITED`, `returncode=1`, `timed_out=false`, and `cleanup_readback=1`; no task-owned pytest process remained at restoration.
  - OBSERVED: The whole-directory collection manifest contains 3054 node IDs, while the serial and shard manifests contain 306 and 2729. Exact set subtraction identifies 19 missing nodes under `test/characterization/` and `test/contracts/`, because runner discovery currently uses a top-level-only glob.
  - OBSERVED: The fail-closed summary SHA256 is `7ca5c40b81e12fe443c4f65369196360ec5e9b1755012a1fe87c9c9a34e23d23`; serial JUnit SHA256 is `d086e1f275379e7bd5189820e1a86eba2449f62e2abc2b6081a2bcd38249fec1`; shard JUnit SHA256 is `cdc64e9ef88928d5cfa64e88157f5e3081a86e3a5071a1d5529fd6919e037718`; outer-time SHA256 is `94fa2155b61db3185c4076b636221d606d99ab44480dff03701d6d241a7f1c9a`.
inferred:
  - NONE
conclusion: EXP-019 is INVALID for correctness and timing comparison. Its command completed normally, but the current physical scratch layout exceeds the suite's Unix-socket budget and top-level-only discovery cannot cover the complete ordinary gate.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/admission-exp019-w1.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp019-w1-console.log
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp019-w1-outer-time.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/c
decision: RETAIN_INVALID_DIAGNOSTIC_AND_FIX
next_experiment: EXP-020-LAYOUT-BUDGET-RED-GREEN
```

## CP-005 — Restored checkpoint after corrected-scope dispatch

```yaml
checkpoint_id: CP-005
last_valid_experiment: EXP-018-ISOLATION-RED-GREEN
current_hypothesis: Two runner-boundary defects exposed by EXP-019 must be isolated in separate RED/GREEN rounds before repeating W1: Unix-socket path budget first, then recursive nested-module discovery.
working_tree_status: only docs/experiments/so101-pytest-parallel-gate-experiment-ledger.md is modified; implementation HEAD is e81286bf5aa465168d7d611de349635cbcae8a9e; pinned submodule c16b5a5fe880b6e1857f56486dab4ae726576969 is initialized and clean
owned_processes: current Codex process/session only; no pytest, colcon, ROS, simulation, Docker, GPU-client, or task user-unit process is owned or active
preserved_processes: all other worktrees, tmux sessions, processes, containers, GPU clients, and user units; parallel-adaptive-worker-pool remains out of scope
confirmed_conclusions:
  - EXP-018 is the last valid experiment and candidate e81286bf has 27 focused contracts GREEN.
  - EXP-019 evidence is retained unchanged and is INVALID; the command completed normally with exit 1, so external interruption is not used as its invalidation reason.
  - Formal Worker scaling status is COMPLETE with final_cleanup PASS as of 2026-09-15T19:59:40+08:00.
  - EXP-019 directly observed one 108-byte AF_UNIX bind failure and manifest-set subtraction observed 19 nested ordinary nodes absent from execution assignment.
disproven_routes:
  - Treating EXP-019 as a valid timing sample is rejected because correctness failed.
  - Marking the pytest command itself externally interrupted is rejected by its completed `/usr/bin/time` record and EXITED ownership readbacks.
  - Adding more serial modules cannot repair a deterministic path-budget failure or top-level-only discovery omission.
open_risks:
  - A fresh full resource admission check is still required immediately before each W1/W2/W4 run.
  - The shortest safe physical name must retain cross-run identity and fail closed if the registered evidence path cannot accommodate the reserved socket suffix.
  - Recursive discovery must not enter benchmark_test or split whole modules.
next_command: add a focused failing Unix-socket-budget contract under EXP-020-LAYOUT-BUDGET-RED-GREEN using a fresh registered /data scratch root
```

## EXP-020-LAYOUT-BUDGET-RED-GREEN — Reserve the Unix-socket path budget

```yaml
experiment_id: EXP-020-LAYOUT-BUDGET-RED-GREEN
status: PLANNED
prior_experiment: EXP-019-W1
hypothesis: A path-budget-aware deterministic physical process basename can keep `layout.root/ipc-response/s` within Linux's 107-byte AF_UNIX pathname payload limit while preserving fresh per-process TMP/ROS/JUnit/log isolation and cross-run identity.
prediction: A focused contract using a run-root length matching EXP-019 fails against the 14-byte `p-<12-hex>` basename, then passes when the basename is deterministically shortened only as much as the reserved socket budget requires.
single_variable: Physical process basename length selection in `create_process_layout`; no discovery, production, or ordinary-test semantic change.
lifecycle: REUSE_STACK
preconditions:
  - Candidate HEAD is e81286bf5aa465168d7d611de349635cbcae8a9e and only this ledger is dirty before the RED test is added.
  - Exact /usr/bin/python3 and a unique previously nonexistent scratch directory under the registered evidence root are used for each focused invocation.
success_criteria:
  - RED fails only on the 107-byte derived-socket budget assertion; GREEN passes the complete focused runner suite; deterministic cross-run identity and all existing isolation contracts remain GREEN; Ruff check and format-check pass.
failure_criteria:
  - Any unrelated focused contract fails or the selected layout can exceed 107 bytes without failing closed.
invalid_criteria:
  - Wrong Python/tempfile routing, scratch collision, unrelated source drift, or resource contamination.
provenance:
  source_commit: e81286bf5aa465168d7d611de349635cbcae8a9e
  install_overlay: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism/install
  runtime_executable: /usr/bin/python3
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - PENDING
observed:
  - PENDING
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/u
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/v
decision: PENDING
next_experiment: EXP-021-RECURSIVE-DISCOVERY-RED-GREEN
```

### EXP-020 result update

```yaml
status: VALID
status_history:
  - status: RUNNING
    at: 2026-09-15T20:10:00+08:00
  - status: VALID
    at: 2026-09-15T20:15:13+08:00
commands:
  - command: exact-/usr/bin/python3 tempfile preflight and focused runner pytest before implementation under scratch/u
    exit_code: 2
  - command: exact-/usr/bin/python3 tempfile preflight and focused runner pytest after implementation under scratch/v
    exit_code: 0
  - command: Ruff check and format-check after implementation under scratch/v
    exit_code: 1
  - command: exact-/usr/bin/python3 tempfile preflight, complete focused runner pytest, Ruff check, and Ruff format-check after targeted formatting under scratch/w
    exit_code: 0
observed:
  - OBSERVED: RED failed during collection only because `validate_process_path_budget` did not exist; exact Python and tempfile routing were valid.
  - OBSERVED: The first behavioral GREEN passed 28 tests, while static checks rejected only import ordering and formatting; this intermediate scratch is retained but is not the acceptance run.
  - OBSERVED: The fresh post-format GREEN passed all 28 focused tests in 0.05 seconds; pytest, Ruff check, and Ruff format-check all exited 0.
  - OBSERVED: A 12-hex SHA256 identity retains 48 bits of deterministic cross-run/process identity while removing the two decorative `p-` bytes; the EXP-019-length reserved path is 106 bytes.
  - OBSERVED: `run_gate` now validates the reserved `ipc-response/s` path before creating the run root and rejects a three-character run ID at 108 bytes with an AF_UNIX-specific error.
inferred:
  - NONE
conclusion: The reproduced socket-path failure is fixed at the runner layout boundary without changing ordinary tests, production code, tempfile isolation, or evidence placement.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/u
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/v
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/w
decision: KEEP
next_experiment: EXP-021-RECURSIVE-DISCOVERY-RED-GREEN
```

## EXP-021-RECURSIVE-DISCOVERY-RED-GREEN — Include nested ordinary modules exactly once

```yaml
experiment_id: EXP-021-RECURSIVE-DISCOVERY-RED-GREEN
status: PLANNED
prior_experiment: EXP-020-LAYOUT-BUDGET-RED-GREEN
hypothesis: Recursive deterministic `test_*.py` discovery beneath `src/so101_demo_py/test/` includes the 19 nested contract and characterization nodes omitted in EXP-019 while preserving whole-module assignment and benchmark exclusion.
prediction: A focused nested-module discovery contract fails before implementation because top-level `glob` returns only the top-level fixture, then the complete focused suite passes after changing only discovery to recursive `rglob`.
single_variable: Ordinary module discovery recursion; physical layout, serial policy, production code, and ordinary-test semantics remain unchanged.
lifecycle: REUSE_STACK
preconditions:
  - EXP-020 is VALID and no full gate starts before this focused round completes.
  - Exact /usr/bin/python3 and distinct previously nonexistent /data scratch roots are used for RED and GREEN.
success_criteria:
  - RED fails only because the nested ordinary module is absent; GREEN passes the complete focused suite; deterministic ordering and benchmark exclusion remain GREEN; Ruff check and format-check pass.
failure_criteria:
  - Nested ordinary modules remain absent, benchmark modules enter discovery, module assignment duplicates paths, or any existing focused/static contract fails.
invalid_criteria:
  - Wrong Python/tempfile routing, scratch collision, unrelated source drift, or resource contamination.
provenance:
  source_commit: e81286bf5aa465168d7d611de349635cbcae8a9e
  install_overlay: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism/install
  runtime_executable: /usr/bin/python3
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - PENDING
observed:
  - PENDING
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/x
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/y
decision: PENDING
next_experiment: EXP-022-CANDIDATE-FOCUSED-AND-BUILD
```

### EXP-021 result update

```yaml
status: VALID
status_history:
  - status: RUNNING
    at: 2026-09-15T20:16:00+08:00
  - status: VALID
    at: 2026-09-15T20:18:15+08:00
commands:
  - command: exact-/usr/bin/python3 tempfile preflight and focused runner pytest before recursive discovery under scratch/x
    exit_code: 1
  - command: exact-/usr/bin/python3 tempfile preflight and focused runner pytest after recursive discovery under scratch/y
    exit_code: 0
  - command: Ruff check and format-check after recursive discovery under scratch/y
    exit_code: 1
  - command: exact-/usr/bin/python3 tempfile preflight, complete focused runner pytest, Ruff check, and Ruff format-check after targeted formatting under scratch/z
    exit_code: 0
observed:
  - OBSERVED: RED ran 28 tests and produced exactly one failure: `discover_ordinary_modules` returned only `test/test_fast.py` and omitted `test/contracts/test_nested.py`; benchmark isolation remained intact.
  - OBSERVED: Changing only `test_root.glob("test_*.py")` to deterministic sorted `test_root.rglob("test_*.py")` made the focused behavior GREEN.
  - OBSERVED: The first GREEN passed pytest and Ruff check but Ruff format-check rejected only the new test fixture's line wrapping; it is retained as an intermediate diagnostic, not acceptance evidence.
  - OBSERVED: Fresh post-format acceptance under scratch/z passed all 28 focused tests in 0.09 seconds; pytest, Ruff check, and Ruff format-check all exited 0.
inferred:
  - NONE
conclusion: Recursive discovery now assigns the complete ordinary test tree by whole module without collecting the sibling benchmark_test tree or weakening exact node-ID verification.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/x
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/y
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/z
decision: KEEP
next_experiment: EXP-022-CANDIDATE-FOCUSED-AND-BUILD
```

## EXP-022-CANDIDATE-FOCUSED-AND-BUILD — Freeze and rebuild the corrected candidate

```yaml
experiment_id: EXP-022-CANDIDATE-FOCUSED-AND-BUILD
status: PLANNED
prior_experiment: EXP-021-RECURSIVE-DISCOVERY-RED-GREEN
hypothesis: Committing the two runner-boundary fixes and their contracts produces one reviewable candidate that retains focused correctness and rebuilds against the dependency-complete local overlay.
prediction: Scoped diff checks pass, the commit contains only runner/test/ledger changes, a fresh focused acceptance passes, and the so101_demo_py symlink build plus package/import provenance resolves inside this worktree.
single_variable: Freeze the already GREEN EXP-020/EXP-021 changes into one candidate commit and refresh its Python package overlay.
lifecycle: REBUILD_STACK
preconditions:
  - EXP-020 and EXP-021 are VALID; no production or ordinary-test semantic file changed.
  - The pinned submodule remains initialized and unchanged; only task-owned runner, focused-test, and ledger paths are dirty.
success_criteria:
  - `git diff --check` passes; scoped commit succeeds; fresh focused pytest and Ruff pass; colcon build exits 0; HEAD, package prefix, import origin, exact Python, and dependency prefixes match the current worktree.
failure_criteria:
  - Any diff, commit-scope, focused, static, build, or provenance gate fails.
invalid_criteria:
  - Unrelated dirty path, source drift after commit, resource conflict, or overlay resolution outside this worktree.
provenance:
  source_commit: PENDING_COMMIT
  install_overlay: /data/work/ws_moveit/.worktrees/pytest-gate-parallelism/install
  runtime_executable: /usr/bin/python3
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - PENDING
observed:
  - PENDING
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/aa
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-log-exp022
decision: PENDING
next_experiment: EXP-023-W1
```

### EXP-022 coordination deferral

```yaml
observed_at: 2026-09-15T20:19:52+08:00
status: REMAINS_PLANNED
coordination_status: RUNNING
coordination_dispatch_id: DF261A05-3907-49C9-95BE-B303D7CF879B
purpose: W10 fixed-Worker reproducibility rerun and guide update
observed:
  - OBSERVED: Fresh admission found no conflicting runtime process, ROS node, container, GPU client, or active task unit at the instant of the probe, but the authoritative coordination file had changed from COMPLETE to RUNNING.
  - OBSERVED: Candidate commit 1d18b088a87aaa8b6fb2b09bcfa1995325dd801d was already created before this status change was observed.
decision: DEFER all build, pytest, colcon, ROS, container, GPU, and benchmark commands until a fresh coordination read returns COMPLETE or BLOCKED; do not disturb the external Worker rerun.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/admission-exp022.txt
```

### EXP-022 result update

```yaml
status: VALID
status_history:
  - status: RUNNING
    at: 2026-09-15T20:46:29+08:00
  - status: VALID
    at: 2026-09-15T20:51:30+08:00
provenance:
  source_commit: 1d18b088a87aaa8b6fb2b09bcfa1995325dd801d
  install_overlay: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/install-exp022
  runtime_executable: /usr/bin/python3
commands:
  - command: git commit -m "fix: complete deterministic pytest gate isolation"
    exit_code: 0
  - command: exact-/usr/bin/python3 committed-candidate focused pytest plus Ruff check and format-check under scratch/aa
    exit_code: 0
  - command: in-place colcon build --packages-select so101_demo_py --symlink-install
    exit_code: 1
  - command: fresh seven-package dependency-closure colcon build with separate build base and merged install base under the registered evidence root
    exit_code: 0
  - command: exact Python/package/import/installed-manifest provenance readback from install-exp022
    exit_code: 0
observed:
  - OBSERVED: Scoped commit 1d18b088a87aaa8b6fb2b09bcfa1995325dd801d contains only `tools/so101_pytest_gate.py`, `src/so101_demo_py/test/test_pytest_full_gate_runner.py`, and this ledger.
  - OBSERVED: Fresh scratch/aa passed all 28 focused tests in 0.05 seconds; pytest, Ruff check, and Ruff format-check exited 0.
  - OBSERVED: The in-place package refresh failed because stale colcon develop state invoked unsupported `setup.py develop --uninstall`; the pre-existing build/install trees were preserved and not cleaned.
  - OBSERVED: A fresh task-owned merged overlay then built the exact seven-package closure successfully in 2 minutes 15 seconds without modifying source or the stale in-place build tree.
  - OBSERVED: `/usr/bin/python3`, the so101_demo source shim, all five required package prefixes, installed bundle source commit, package prefix, and mujoco_ros2_control dependency prefix passed exact provenance readback for candidate 1d18b088a.
inferred:
  - NONE
conclusion: Candidate 1d18b088a is focused-verified and has a fresh dependency-complete overlay suitable for W1/W2/W4 measurements; the failed in-place refresh is retained as an environment diagnostic and does not invalidate the successful isolated rebuild.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/admission-exp022-resume.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/aa
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-exp022.log
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-log-exp022
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-exp022-fresh.log
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-log-exp022-fresh
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-exp022-fresh-provenance.json
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/install-exp022
decision: KEEP
next_experiment: EXP-023-W1
```

## EXP-023-W1 — Final-candidate serial baseline

```yaml
experiment_id: EXP-023-W1
status: RUNNING
status_history:
  - status: PLANNED
    at: 2026-09-15T20:51:30+08:00
  - status: RUNNING
    at: 2026-09-15T20:53:14+08:00
prior_experiment: EXP-022-CANDIDATE-FOCUSED-AND-BUILD
hypothesis: Candidate 1d18b088a passes the complete 3054-node ordinary gate at W1 with exact once-only coverage and establishes the uncontaminated baseline for W2/W4.
prediction: The five-module serial lane and one parallel shard both pass; all 3054 collected node IDs execute exactly once; nested contract/characterization nodes are present; benchmark paths are absent; the fail-closed summary is PASS with complete timing/resource/cleanup evidence.
single_variable: worker_count=1
lifecycle: REUSE_STACK
preconditions:
  - Commit 1d18b088a87aaa8b6fb2b09bcfa1995325dd801d, /usr/bin/python3, merged install-exp022 overlay, source shim, timing input, five-module serial lane, and environment are frozen for W1/W2/W4.
  - Fresh one-character run ID d is previously nonexistent and validates the 106-byte reserved AF_UNIX path budget.
  - Only this ledger is dirty and explicitly allowlisted.
  - Fresh coordination and process/ROS/container/GPU/unit admission must be conflict-free immediately before launch.
success_criteria:
  - PASS with 3054 expected and actual node IDs, identical exact collection hash, zero missing/duplicate/unexpected IDs, benchmark exclusion, all pytest/JUnit/provenance gates, cleanup readback, and complete resource summary.
failure_criteria:
  - Any test/process/coverage/provenance/JUnit/timeout/cleanup gate fails.
invalid_criteria:
  - Admission conflict, source/environment/timing-input drift, scratch collision, or external interruption.
provenance:
  source_commit: 1d18b088a87aaa8b6fb2b09bcfa1995325dd801d
  install_overlay: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/install-exp022
  runtime_executable: /usr/bin/python3
  runtime_source_shim: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/runtime-python
  timing_input_sha256: 6a12dd688dd51a0926906e0aa5c9ee1c9489f66ffdd6b5adfcec52c08eec5a21
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - PENDING
observed:
  - PENDING
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/admission-exp023-w1.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/d
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp023-w1-outer-time.txt
decision: PENDING
next_experiment: EXP-024-W2
```

### EXP-023 result update

```yaml
status: INVALID
status_history:
  - status: INVALID
    at: 2026-09-15T21:09:04+08:00
commands:
  - command: tools/so101_pytest_gate.py --workers 1 --evidence-root /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01 --run-id d --timings /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/s38package8/package.xml --python /usr/bin/python3 --expected-source-commit 1d18b088a87aaa8b6fb2b09bcfa1995325dd801d --allow-dirty-path docs/experiments/so101-pytest-parallel-gate-experiment-ledger.md --timeout-s 1200
    exit_code: 0
observed:
  - OBSERVED: The runner returned PASS with 3055 expected and actual node IDs, exact collection SHA256 `0c26a7aaeb045ec9bc70b3df773c0f30eee65344120ab83b74507b3d7e471cd4`, benchmark exclusion, unchanged source status, and all children reaped.
  - OBSERVED: The prior 3054-node prediction was off by one because EXP-020 added a new focused socket-budget contract; 3055 is the authoritative committed-candidate collection count.
  - OBSERVED: The serial lane passed 306 tests in 19.503 seconds; shard 1 passed 2749 tests in 843.918 seconds; total runner elapsed was 869.141 seconds and outer elapsed was 14:29.20.
  - OBSERVED: The nested characterization and contract modules appear in the shard assignment and exact executed-node union.
  - OBSERVED: GNU `time -v` resource files contain tab-indented labels and valid values, including shard user=859.00 seconds, system=12.53 seconds, CPU=103 percent, and peak RSS=2553912 KiB.
  - OBSERVED: Runner summary fields `cpu_time_s=0.0`, `cpu_utilization_percent=0.0`, `maximum_rss_kib=null`, and per-process resource fields are null because `_resource_metrics` requires labels at column zero.
inferred:
  - NONE
conclusion: W1 functional correctness and cleanup pass, but EXP-023 is INVALID for the formal timing comparison because the required machine-readable resource summary is incomplete.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/admission-exp023-w1.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/d
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp023-w1-console.log
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp023-w1-outer-time.txt
decision: RETAIN_INVALID_DIAGNOSTIC_AND_FIX
next_experiment: EXP-024-RESOURCE-METRICS-RED-GREEN
```

## EXP-024-RESOURCE-METRICS-RED-GREEN — Parse indented GNU-time metrics

```yaml
experiment_id: EXP-024-RESOURCE-METRICS-RED-GREEN
status: PLANNED
prior_experiment: EXP-023-W1
hypothesis: Accepting leading whitespace before exact GNU-time labels makes all resource fields machine-readable while retaining strict numeric parsing.
prediction: A focused fixture containing tab-indented real-format labels fails with all-null metrics before implementation, then the complete focused suite and Ruff pass after allowing only leading whitespace in the anchored label regex.
single_variable: Leading-whitespace handling in `_resource_metrics`; no runner scheduling, discovery, isolation, production, or ordinary-test semantic change.
lifecycle: REUSE_STACK
preconditions:
  - EXP-023 is retained unchanged and excluded from timing comparison.
  - Exact /usr/bin/python3 and distinct previously nonexistent /data scratch roots are used for RED and GREEN.
success_criteria:
  - RED fails only on missing parsed values; GREEN parses peak RSS, user time, system time, and CPU percent exactly; complete focused suite and Ruff checks pass.
failure_criteria:
  - Parser accepts malformed labels/numbers or any existing focused/static contract fails.
invalid_criteria:
  - Wrong Python/tempfile routing, scratch collision, unrelated source drift, or resource contamination.
provenance:
  source_commit: 1d18b088a87aaa8b6fb2b09bcfa1995325dd801d
  install_overlay: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/install-exp022
  runtime_executable: /usr/bin/python3
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - PENDING
observed:
  - PENDING
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/ab
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/ac
decision: PENDING
next_experiment: EXP-025-CANDIDATE-REFRESH
```

### EXP-024 result update

```yaml
status: VALID
status_history:
  - status: RUNNING
    at: 2026-09-15T21:10:00+08:00
  - status: VALID
    at: 2026-09-15T21:12:00+08:00
commands:
  - command: exact-/usr/bin/python3 tempfile preflight and focused runner pytest before parser correction under scratch/ab
    exit_code: 1
  - command: exact-/usr/bin/python3 tempfile preflight and focused runner pytest plus Ruff checks after parser correction under scratch/ac
    exit_code: 1
  - command: exact-/usr/bin/python3 tempfile preflight, complete focused runner pytest, Ruff check, and Ruff format-check after targeted import ordering under scratch/ad
    exit_code: 0
observed:
  - OBSERVED: RED ran 29 tests and produced exactly one failure: the real-format tab-indented fixture parsed as `(None, None, None, None)` instead of `(2553912, 859.0, 12.53, 103.0)`.
  - OBSERVED: Allowing only spaces and tabs before the otherwise exact anchored label made all 29 behavioral contracts pass.
  - OBSERVED: The first GREEN had only an import-order Ruff failure; fresh post-ordering acceptance under scratch/ad passed all 29 focused tests in 0.05 seconds and both Ruff checks exited 0.
inferred:
  - NONE
conclusion: The runner now records GNU-time peak RSS, user time, system time, and CPU percentage without loosening numeric or label matching.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/ab
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/ac
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/ad
decision: KEEP
next_experiment: EXP-025-CANDIDATE-REFRESH
```

## EXP-025-CANDIDATE-REFRESH — Commit metrics fix and refresh package manifest

```yaml
experiment_id: EXP-025-CANDIDATE-REFRESH
status: PLANNED
prior_experiment: EXP-024-RESOURCE-METRICS-RED-GREEN
hypothesis: A scoped commit of the parser fix/test/ledger plus a fresh-build-base incremental so101_demo_py install into the existing task-owned merged overlay yields exact final-candidate provenance without rebuilding unchanged dependencies.
prediction: Diff checks and scoped commit pass; so101_demo_py refresh succeeds without stale `--uninstall`; all merged prefixes remain intact; installed manifest source commit matches the new candidate.
single_variable: Freeze the already GREEN resource parser correction and refresh only the commit-bearing Python package manifest in install-exp022.
lifecycle: REBUILD_STACK
preconditions:
  - EXP-024 is VALID; only runner, focused-test, and ledger paths are dirty.
  - install-exp022 is the valid seven-package merged overlay from EXP-022; dependency source/build outputs remain unchanged.
  - A previously nonexistent build base and log base are used; no stale build tree is deleted or overwritten.
success_criteria:
  - `git diff --check`, scoped commit, focused acceptance, incremental package build, and exact package/import/manifest provenance all pass.
failure_criteria:
  - Any scope, test, static, build, or provenance gate fails.
invalid_criteria:
  - Unrelated dirty path, source drift, resource conflict, or dependency prefix drift.
provenance:
  source_commit: PENDING_COMMIT
  install_overlay: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/install-exp022
  runtime_executable: /usr/bin/python3
commands:
  - PENDING
observed:
  - PENDING
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-exp025.log
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-log-exp025
decision: PENDING
next_experiment: EXP-026-W1
```

### EXP-025 result update

```yaml
status: VALID
status_history:
  - status: RUNNING
    at: 2026-09-15T21:13:59+08:00
  - status: VALID
    at: 2026-09-15T21:16:00+08:00
provenance:
  source_commit: dab91e3d615d4be61a2414695877910d2c5808ab
  install_overlay: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/install-exp022
  runtime_executable: /usr/bin/python3
commands:
  - command: git diff --check and scoped commit `fix: record pytest gate resource metrics`
    exit_code: 0
  - command: fresh-build-base incremental merged-install refresh of so101_demo_py
    exit_code: 0
  - command: exact /usr/bin/python3 focused pytest plus Ruff check and format-check under scratch/ae
    exit_code: 0
  - command: exact Python/import/package-prefix/commit provenance readback
    exit_code: 0
observed:
  - OBSERVED: Commit dab91e3d615d4be61a2414695877910d2c5808ab contains only the runner parser, its focused regression test, and this ledger.
  - OBSERVED: Fresh-build-base incremental refresh completed in 1.37 seconds and retained all five required package prefixes in install-exp022.
  - OBSERVED: Fresh scratch/ae resolved tempfile inside its NVMe tmp directory; all 29 focused tests passed in 0.05 seconds and both Ruff gates passed.
  - OBSERVED: `/usr/bin/python3`, the source shim, all required package prefixes, and candidate commit passed exact provenance readback.
inferred:
  - NONE
conclusion: Candidate dab91e3d6 is committed, focused-verified, and installed with exact provenance for the formal W1/W2/W4 comparison.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/admission-exp025.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-exp025.log
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-exp025-time.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-log-exp025
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/build-exp025-provenance.json
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/ae
decision: KEEP
next_experiment: EXP-026-W1
```

## EXP-026-W1 — Resource-complete serial baseline

```yaml
experiment_id: EXP-026-W1
status: RUNNING
status_history:
  - status: PLANNED
    at: 2026-09-15T21:16:00+08:00
  - status: RUNNING
    at: 2026-09-15T21:17:30+08:00
prior_experiment: EXP-025-CANDIDATE-REFRESH
hypothesis: Candidate dab91e3d6 passes the complete ordinary gate at W1 with exact once-only coverage and complete CPU/RSS metrics.
prediction: The five-module serial lane and one parallel shard pass; all collected node IDs execute exactly once; nested tests are present; benchmark paths are absent; every process and aggregate resource field is non-null.
single_variable: worker_count=1
lifecycle: REUSE_STACK
preconditions:
  - Candidate, exact /usr/bin/python3, install-exp022, source shim, timing input, serial lane, and environment are frozen for W1/W2/W4.
  - Fresh one-character run ID g is previously nonexistent and validates the 106-byte reserved AF_UNIX path budget.
  - Only this ledger is dirty and explicitly allowlisted.
  - Fresh coordination and host admission must be conflict-free immediately before launch.
success_criteria:
  - PASS with exact expected/actual node equality, zero missing/duplicate/unexpected IDs, benchmark exclusion, all pytest/JUnit/provenance/cleanup gates, and complete resource evidence.
failure_criteria:
  - Any test, process, coverage, provenance, JUnit, timeout, cleanup, or resource gate fails.
invalid_criteria:
  - Admission conflict, source/environment/timing-input drift, scratch collision, or external interruption.
provenance:
  source_commit: dab91e3d615d4be61a2414695877910d2c5808ab
  install_overlay: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/install-exp022
  runtime_executable: /usr/bin/python3
  runtime_source_shim: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/runtime-python
  timing_input_sha256: 6a12dd688dd51a0926906e0aa5c9ee1c9489f66ffdd6b5adfcec52c08eec5a21
commands:
  - PENDING
observed:
  - PENDING
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/admission-exp026-w1.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/g
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp026-w1-outer-time.txt
decision: PENDING
next_experiment: EXP-027-W2
```

### EXP-026 interruption update

```yaml
status: INVALID
status_history:
  - status: INVALID
    at: 2026-09-15T21:26:30+08:00
commands:
  - command: tools/so101_pytest_gate.py --workers 1 --evidence-root /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01 --run-id g --timings /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/s38package8/package.xml --python /usr/bin/python3 --expected-source-commit dab91e3d615d4be61a2414695877910d2c5808ab --allow-dirty-path docs/experiments/so101-pytest-parallel-gate-experiment-ledger.md --timeout-s 1200
    exit_code: 130
observed:
  - OBSERVED: User requested an immediate pause after 9 minutes 4.61 seconds; the runner received SIGINT and therefore produced no formal summary.
  - OBSERVED: Collection completed with 3056 ordinary nodes and the serial lane passed all 306 tests before interruption; the parallel shard had reached 54 percent.
  - OBSERVED: The outer runner stopped first, leaving its owned pytest process group alive; explicit TERM/KILL cleanup removed that process group.
  - OBSERVED: Cleanup also stopped ROS 2 daemon PID 2421996 and one unrelated stale orphan ROS-setup/colcon process group 750253 as explicitly requested by the user.
  - OBSERVED: Final process, no-daemon ROS graph, Docker, GPU-client, and user-unit readback found no ROS, simulator, pytest, SO-101, or matching container/service residue.
inferred:
  - NONE
conclusion: EXP-026 is INVALID solely because of the requested external interruption; its partial timing is excluded and W1 must use a new run ID after user resume.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/admission-exp026-w1.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/g
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp026-w1-console.log
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp026-w1-outer-time.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/cleanup-user-pause-20260915T2130.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/cleanup-user-pause-final.txt
decision: RETAIN_INVALID_INTERRUPTED_EVIDENCE
next_experiment: PAUSED_BEFORE_EXP-026-W1-RERUN
```

```yaml
checkpoint_id: CP-006
last_valid_experiment: EXP-025-CANDIDATE-REFRESH
current_hypothesis: Candidate dab91e3d6 remains ready for fresh W1/W2/W4 comparison; interrupted scratch/g cannot be reused.
working_tree_status: only this ledger is dirty; implementation candidate dab91e3d6 is committed
owned_processes: NONE
preserved_processes: Codex/tmux control session only; all ROS and pytest processes were removed at user request
confirmed_conclusions:
  - Candidate dab91e3d6 passes 29 focused tests, Ruff, incremental build, and exact overlay provenance.
  - Interrupted EXP-026 collected 3056 ordinary nodes and passed the 306-test serial lane before user-requested termination.
  - Final cleanup readback is empty for ROS, simulator, pytest, containers, GPU clients, and matching user units.
open_risks:
  - Formal W1/W2/W4 measurements and fastest-mode selection remain incomplete.
  - A resumed W1 must use a new previously nonexistent one-character scratch/run ID.
retained_runs:
  - Entire registered evidence root, including interrupted scratch/g and all prior valid/invalid experiments.
archived_runs:
  - NONE
deletion_candidates:
  - All scratch trees and build/install/log trees under the registered evidence root after final readback; no deletion is authorized or performed.
next_command: WAIT_FOR_USER_RESUME
```

## Resumed-scope correction

```yaml
correction_at: 2026-09-15T22:20:33+08:00
user_scope:
  - Optimize only complete ordinary pytest wall-clock time.
  - Pytest-only changes do not require SO-101 application Worker W1-W10 correctness validation.
  - Any change outside pytest runner/test files requires prior user approval.
clarification:
  - P4 and P6 below mean four and six concurrent pytest subprocesses; they do not select or inject an SO-101 application Worker mode into test cases.
allowed_executable_source_paths:
  - tools/so101_pytest_gate.py
  - tools/so101_pytest_manifest.py
  - src/so101_demo_py/test/test_pytest_full_gate_runner.py
audit_path:
  - docs/experiments/so101-pytest-parallel-gate-experiment-ledger.md
acceptance:
  - Full ordinary pytest collection passes exactly once; lowest measured total_elapsed_s wins.
excluded:
  - benchmark_test
  - SO-101 runtime, Gazebo, MoveIt, GUI, and application Worker W1-W10 validation
```

## EXP-027-PYTEST-P4 — Full ordinary pytest at concurrency 4

```yaml
experiment_id: EXP-027-PYTEST-P4
status: RUNNING
status_history:
  - status: PLANNED
    at: 2026-09-15T22:20:33+08:00
  - status: RUNNING
    at: 2026-09-15T22:21:30+08:00
prior_experiment: EXP-026-W1
hypothesis: Four concurrent pytest subprocesses reduce the full-suite wall time substantially while preserving the exact 3056-node ordinary collection.
prediction: The five sensitive modules pass in the serial lane, all remaining modules pass across four balanced shards, and total wall time is substantially below the retained 869.141-second serial-runner observation.
single_variable: pytest subprocess concurrency=4
lifecycle: REUSE_STACK
preconditions:
  - Candidate commit dab91e3d615d4be61a2414695877910d2c5808ab, exact /usr/bin/python3, install-exp022, source shim, timing input, and serial-module classification are frozen.
  - Fresh one-character run ID h is previously nonexistent and only this ledger is dirty/allowlisted.
  - Fresh host admission immediately before launch finds no competing pytest, ROS, simulator, container, GPU, or matching user-unit workload.
success_criteria:
  - PASS; 3056 expected and actual nodes; zero missing, duplicate, or unexpected nodes; every pytest process exits 0; total_elapsed_s is recorded.
failure_criteria:
  - Any test/process/collection/JUnit/provenance/timeout/cleanup gate fails.
invalid_criteria:
  - Admission conflict, source/environment/timing-input drift, scratch collision, or external interruption.
provenance:
  source_commit: dab91e3d615d4be61a2414695877910d2c5808ab
  install_overlay: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/install-exp022
  runtime_executable: /usr/bin/python3
  runtime_source_shim: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/runtime-python
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - PENDING
observed:
  - PENDING
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/admission-exp027-p4.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/h
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp027-p4-outer-time.txt
decision: PENDING
next_experiment: EXP-028-PYTEST-P6
```

### EXP-027 result update

```yaml
status: VALID
status_history:
  - status: VALID
    at: 2026-09-15T22:25:00+08:00
commands:
  - command: tools/so101_pytest_gate.py --workers 4 --evidence-root /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01 --run-id h --timings /data/work/so101-evidence/parallel-adaptive-worker/20260915-w10-a01/scratch/s38package8/package.xml --python /usr/bin/python3 --expected-source-commit dab91e3d615d4be61a2414695877910d2c5808ab --allow-dirty-path docs/experiments/so101-pytest-parallel-gate-experiment-ledger.md --timeout-s 1200
    exit_code: 0
observed:
  - OBSERVED: Runner PASS; expected=3056, actual=3056, collection SHA256 `91a4c4b43fd3a74425b0433282ff739e08faed9dc2c08201431304e749d1a967`, and all children reaped.
  - OBSERVED: Setup=6.553 seconds, serial lane=10.640 seconds, parallel critical path=172.465 seconds, runner total=189.788 seconds, and outer wall=189.86 seconds.
  - OBSERVED: Four shard wall times were 6.535, 10.190, 32.338, and 172.465 seconds, demonstrating severe imbalance from the stale historical timing input.
  - OBSERVED: Aggregate CPU time=237.620 seconds, CPU utilization=125.203 percent, peak per-process RSS=1396596 KiB, and warnings=4.
  - OBSERVED: Compared with the retained 869.141-second successful serial-runner observation from EXP-023, concurrency 4 reduced wall time by 78.16 percent.
  - OBSERVED: The five execution JUnits were merged into a valid 3056-testcase fresh timing artifact with SHA256 `5cb13f3bf15130b85f6df440b76383c4213af081d52c545e45308db8f96a1368`.
inferred:
  - INFERRED: Rebalancing from fresh candidate timings should materially reduce the 172.465-second straggler at concurrency 6.
conclusion: Pytest concurrency 4 is a valid full-suite result and current best at 189.788 seconds; stale timing data, not available CPU count, is now the first performance boundary.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/admission-exp027-p4.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/h
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp027-p4-console.log
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp027-p4-outer-time.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp027-p4-fresh-timings.xml
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp027-p4-fresh-timings-SHA256SUMS
decision: KEEP
next_experiment: EXP-028-PYTEST-P6
```

## EXP-028-PYTEST-P6 — Freshly balanced full ordinary pytest at concurrency 6

```yaml
experiment_id: EXP-028-PYTEST-P6
status: RUNNING
status_history:
  - status: PLANNED
    at: 2026-09-15T22:26:29+08:00
  - status: RUNNING
    at: 2026-09-15T22:28:20+08:00
prior_experiment: EXP-027-PYTEST-P4
hypothesis: Six pytest subprocesses assigned from the fresh candidate JUnit reduce full-suite wall time below the valid 189.788-second concurrency-4 result.
prediction: Exact 3056-node PASS; the fresh LPT estimate places the largest module alone and reduces the parallel critical path below 172.465 seconds.
single_variable: pytest subprocess concurrency=6 and timing input refreshed from the immediately prior candidate run
lifecycle: REUSE_STACK
preconditions:
  - Candidate commit, exact Python, overlay, source shim, serial classification, and host remain unchanged from EXP-027.
  - Fresh timing input contains exactly 3056 testcase elements and has SHA256 `5cb13f3bf15130b85f6df440b76383c4213af081d52c545e45308db8f96a1368`.
  - Fresh one-character run ID i is previously nonexistent; only this ledger is dirty/allowlisted.
  - Fresh host admission immediately before launch is conflict-free.
success_criteria:
  - PASS; exact 3056-node execution; all process exits 0; total_elapsed_s is lower than 189.7883924790658.
failure_criteria:
  - Any test/process/coverage/JUnit/provenance/timeout/cleanup gate fails, or total time is not lower than concurrency 4.
invalid_criteria:
  - Admission conflict, source/environment drift, scratch collision, or external interruption.
provenance:
  source_commit: dab91e3d615d4be61a2414695877910d2c5808ab
  install_overlay: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/install-exp022
  runtime_executable: /usr/bin/python3
  timing_input: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp027-p4-fresh-timings.xml
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - PENDING
observed:
  - PENDING
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/admission-exp028-p6.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/i
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp028-p6-outer-time.txt
decision: PENDING
next_experiment: EXP-029-SELECTION
```

### EXP-028 result update

```yaml
status: VALID
status_history:
  - status: VALID
    at: 2026-09-15T22:30:00+08:00
commands:
  - command: tools/so101_pytest_gate.py --workers 6 --evidence-root /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01 --run-id i --timings /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp027-p4-fresh-timings.xml --python /usr/bin/python3 --expected-source-commit dab91e3d615d4be61a2414695877910d2c5808ab --allow-dirty-path docs/experiments/so101-pytest-parallel-gate-experiment-ledger.md --timeout-s 1200
    exit_code: 0
observed:
  - OBSERVED: Runner PASS with the same exact 3056-node collection SHA256 as EXP-027 and complete child cleanup.
  - OBSERVED: Setup=5.278 seconds, serial lane=10.849 seconds, parallel critical path=82.971 seconds, runner total=99.225 seconds, and outer wall=99.30 seconds.
  - OBSERVED: Concurrency 6 improved total time by 47.72 percent from concurrency 4 and by 88.58 percent from the retained serial-runner observation.
  - OBSERVED: Six shard times were 4.529, 12.148, 82.971, 21.976, 9.739, and 6.637 seconds; one shard still dominates.
  - OBSERVED: Aggregate CPU time=150.080 seconds, CPU utilization=151.253 percent, peak per-process RSS=1361620 KiB, and warnings=4.
  - OBSERVED: Fresh P6 JUnits merge to exactly 3056 testcase elements with SHA256 `a64dede10286fb95f478da1738ea7d6b88b7eac65d5952ee1dc65adacd982cbd`.
inferred:
  - INFERRED: The prior prediction that concurrency above 6 would have little value is disproven by the remaining 82.971-second straggler and the refreshed P8 LPT estimate.
conclusion: Pytest concurrency 6 is valid and current best at 99.225 seconds; one further full concurrency-8 experiment is warranted by new timing evidence.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/admission-exp028-p6.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/i
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp028-p6-console.log
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp028-p6-outer-time.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp028-p6-fresh-timings.xml
decision: KEEP
next_experiment: EXP-029-PYTEST-P8
```

## EXP-029-PYTEST-P8 — Freshly balanced full ordinary pytest at concurrency 8

```yaml
experiment_id: EXP-029-PYTEST-P8
status: RUNNING
status_history:
  - status: PLANNED
    at: 2026-09-15T22:30:37+08:00
  - status: RUNNING
    at: 2026-09-15T22:31:45+08:00
prior_experiment: EXP-028-PYTEST-P6
hypothesis: Eight pytest subprocesses assigned from P6's fresh candidate JUnit reduce full-suite wall time below 99.225 seconds.
prediction: Exact 3056-node PASS and a parallel critical path below 82.971 seconds; refreshed LPT case-time estimate falls from 20.256 seconds at P6 to 15.198 seconds at P8.
single_variable: pytest subprocess concurrency=8 and timing input refreshed from EXP-028
lifecycle: REUSE_STACK
preconditions:
  - Candidate commit, exact Python, overlay, source shim, serial classification, and host remain unchanged.
  - Fresh timing input contains exactly 3056 testcase elements and has SHA256 `a64dede10286fb95f478da1738ea7d6b88b7eac65d5952ee1dc65adacd982cbd`.
  - Fresh one-character run ID j is previously nonexistent; only this ledger is dirty/allowlisted.
  - Fresh host admission immediately before launch is conflict-free.
success_criteria:
  - PASS; exact 3056-node execution; all process exits 0; total_elapsed_s is lower than 99.22460507391952.
failure_criteria:
  - Any test/process/coverage/JUnit/provenance/timeout/cleanup gate fails, or total time is not lower than concurrency 6.
invalid_criteria:
  - Admission conflict, source/environment drift, scratch collision, or external interruption.
provenance:
  source_commit: dab91e3d615d4be61a2414695877910d2c5808ab
  install_overlay: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/install-exp022
  runtime_executable: /usr/bin/python3
  timing_input: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp028-p6-fresh-timings.xml
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - PENDING
observed:
  - PENDING
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/admission-exp029-p8.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/j
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp029-p8-outer-time.txt
decision: PENDING
next_experiment: EXP-030-SELECTION
```

### EXP-029 result update

```yaml
status: VALID
status_history:
  - status: VALID
    at: 2026-09-15T22:33:00+08:00
commands:
  - command: tools/so101_pytest_gate.py --workers 8 --evidence-root /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01 --run-id j --timings /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp028-p6-fresh-timings.xml --python /usr/bin/python3 --expected-source-commit dab91e3d615d4be61a2414695877910d2c5808ab --allow-dirty-path docs/experiments/so101-pytest-parallel-gate-experiment-ledger.md --timeout-s 1200
    exit_code: 0
observed:
  - OBSERVED: Runner PASS with exact 3056-node collection SHA256 `91a4c4b43fd3a74425b0433282ff739e08faed9dc2c08201431304e749d1a967` and complete cleanup.
  - OBSERVED: Setup=5.233 seconds, serial lane=10.842 seconds, parallel critical path=43.099 seconds, runner total=59.291 seconds, and outer wall=59.36 seconds.
  - OBSERVED: Concurrency 8 improved total time by 40.25 percent from concurrency 6 and by 93.18 percent from the retained serial-runner observation.
  - OBSERVED: Aggregate CPU time=114.500 seconds, CPU utilization=193.116 percent, peak per-process RSS=1835624 KiB, and warnings=4.
  - OBSERVED: Fresh P8 JUnits merge to exactly 3056 testcase elements with SHA256 `aab82183eca12cdf974c789bd7ccc50377040eab8b009ab8cd00a58930253fae`.
inferred:
  - INFERRED: P10 remains warranted because P8 still has a 43.099-second straggler and fresh LPT predicts a lower 9.856-second maximum case-time load versus 11.197 at P8.
conclusion: Pytest concurrency 8 is valid and current best at 59.291 seconds; the stopping rule permits one concurrency-10 experiment.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/admission-exp029-p8.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/j
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp029-p8-console.log
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp029-p8-outer-time.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp029-p8-fresh-timings.xml
decision: KEEP
next_experiment: EXP-030-PYTEST-P10
```

## EXP-030-PYTEST-P10 — Bounded full ordinary pytest at concurrency 10

```yaml
experiment_id: EXP-030-PYTEST-P10
status: RUNNING
status_history:
  - status: PLANNED
    at: 2026-09-15T22:33:28+08:00
  - status: RUNNING
    at: 2026-09-15T22:34:45+08:00
prior_experiment: EXP-029-PYTEST-P8
hypothesis: Ten pytest subprocesses assigned from P8's fresh candidate JUnit reduce full-suite wall time by at least 10 percent from 59.291 seconds.
prediction: Exact 3056-node PASS and total_elapsed_s below 53.362 seconds; otherwise concurrency 8 remains selected and concurrency expansion stops.
single_variable: pytest subprocess concurrency=10 and timing input refreshed from EXP-029
lifecycle: REUSE_STACK
preconditions:
  - Candidate commit, exact Python, overlay, source shim, serial classification, and host remain unchanged.
  - Fresh timing input contains exactly 3056 testcase elements and has SHA256 `aab82183eca12cdf974c789bd7ccc50377040eab8b009ab8cd00a58930253fae`.
  - Fresh one-character run ID k is previously nonexistent; only this ledger is dirty/allowlisted.
  - Fresh host admission immediately before launch is conflict-free.
success_criteria:
  - PASS; exact 3056-node execution; all process exits 0; total_elapsed_s is at least 10 percent lower than 59.290769696002826.
failure_criteria:
  - Any pytest gate fails, or improvement is below 10 percent.
invalid_criteria:
  - Admission conflict, source/environment drift, scratch collision, or external interruption.
provenance:
  source_commit: dab91e3d615d4be61a2414695877910d2c5808ab
  install_overlay: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/install-exp022
  runtime_executable: /usr/bin/python3
  timing_input: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp029-p8-fresh-timings.xml
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - PENDING
observed:
  - PENDING
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/admission-exp030-p10.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/k
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp030-p10-outer-time.txt
decision: PENDING
next_experiment: EXP-031-SELECTION
```

### EXP-030 result update

```yaml
status: VALID
status_history:
  - status: VALID
    at: 2026-09-15T22:35:30+08:00
commands:
  - command: tools/so101_pytest_gate.py --workers 10 --evidence-root /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01 --run-id k --timings /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp029-p8-fresh-timings.xml --python /usr/bin/python3 --expected-source-commit dab91e3d615d4be61a2414695877910d2c5808ab --allow-dirty-path docs/experiments/so101-pytest-parallel-gate-experiment-ledger.md --timeout-s 1200
    exit_code: 0
observed:
  - OBSERVED: Runner PASS with exact 3056-node collection SHA256 `91a4c4b43fd3a74425b0433282ff739e08faed9dc2c08201431304e749d1a967` and complete cleanup.
  - OBSERVED: Setup=5.291 seconds, serial lane=10.754 seconds, parallel critical path=10.840 seconds, runner total=27.072 seconds, and outer wall=27.13 seconds.
  - OBSERVED: Concurrency 10 improved total time by 54.34 percent from concurrency 8 and by 96.89 percent from the retained serial-runner observation.
  - OBSERVED: Aggregate CPU time=88.110 seconds, CPU utilization=325.462 percent, peak per-process RSS=1423700 KiB, and warnings=4.
  - OBSERVED: Fresh P10 JUnits merge to exactly 3056 testcase elements with SHA256 `97643da6456e933769201b18141ea55a031557b4dbfdc05f19058d93ba410df6`.
inferred:
  - INFERRED: Parallel execution is now balanced near 10 seconds; fixed collection and serial work dominate, so P12 is expected to produce less than the 10-percent continuation threshold.
conclusion: Pytest concurrency 10 is valid and current best at 27.072 seconds; one P12 stopping check remains.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/admission-exp030-p10.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/k
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp030-p10-console.log
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp030-p10-outer-time.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp030-p10-fresh-timings.xml
decision: KEEP
next_experiment: EXP-031-PYTEST-P12
```

## EXP-031-PYTEST-P12 — Final stopping-boundary full pytest check

```yaml
experiment_id: EXP-031-PYTEST-P12
status: RUNNING
status_history:
  - status: PLANNED
    at: 2026-09-15T22:35:49+08:00
  - status: RUNNING
    at: 2026-09-15T22:36:37+08:00
prior_experiment: EXP-030-PYTEST-P10
hypothesis: Twelve pytest subprocesses cannot improve total full-suite time by at least 10 percent because collection plus the ordered serial lane already consume about 16 seconds.
prediction: Exact 3056-node PASS, but total_elapsed_s is at least 24.365 seconds; select concurrency 10 if so.
single_variable: pytest subprocess concurrency=12 and timing input refreshed from EXP-030
lifecycle: REUSE_STACK
preconditions:
  - Candidate commit, exact Python, overlay, source shim, serial classification, and host remain unchanged.
  - Fresh timing input contains exactly 3056 testcase elements and has SHA256 `97643da6456e933769201b18141ea55a031557b4dbfdc05f19058d93ba410df6`.
  - Fresh one-character run ID l is previously nonexistent; only this ledger is dirty/allowlisted.
  - Fresh host admission immediately before launch is conflict-free.
success_criteria:
  - PASS with exact 3056-node execution and a measured comparison against the 24.365-second continuation threshold.
failure_criteria:
  - Any pytest gate fails.
invalid_criteria:
  - Admission conflict, source/environment drift, scratch collision, or external interruption.
provenance:
  source_commit: dab91e3d615d4be61a2414695877910d2c5808ab
  install_overlay: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/install-exp022
  runtime_executable: /usr/bin/python3
  timing_input: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp030-p10-fresh-timings.xml
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - Fresh admission recorded at 2026-09-15T22:36:37+08:00 in admission-exp031-p12.txt.
  - Run tools/so101_pytest_gate.py with --workers 12, fresh --run-id l, and the EXP-030 merged timing input under /usr/bin/time -v.
observed:
  - Fresh admission passed: exact candidate commit and timing-input digest, only the ledger dirty/allowlisted, no conflicting processes, ROS daemon, containers, GPU clients, user units, or pre-existing scratch/l.
inferred:
  - The run is admissible under the resumed pytest-only scope.
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/admission-exp031-p12.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/l
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp031-p12-outer-time.txt
decision: RUN
next_experiment: EXP-032-SELECTION
```

### EXP-031 result update

```yaml
status: VALID
status_history:
  - status: VALID
    at: 2026-09-15T22:39:00+08:00
commands:
  - command: tools/so101_pytest_gate.py --workers 12 --evidence-root /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01 --run-id l --timings /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp030-p10-fresh-timings.xml --python /usr/bin/python3 --expected-source-commit dab91e3d615d4be61a2414695877910d2c5808ab --allow-dirty-path docs/experiments/so101-pytest-parallel-gate-experiment-ledger.md --timeout-s 1200
    exit_code: 0
observed:
  - OBSERVED: Runner PASS with exact 3056-node collection SHA256 `91a4c4b43fd3a74425b0433282ff739e08faed9dc2c08201431304e749d1a967` and complete child cleanup.
  - OBSERVED: Setup=5.199 seconds, serial lane=10.696 seconds, parallel critical path=11.902 seconds, runner total=27.952 seconds, and outer wall=28.03 seconds.
  - OBSERVED: Concurrency 12 is 3.249 percent slower than concurrency 10 and does not satisfy the 24.365-second continuation threshold.
  - OBSERVED: Aggregate CPU time=95.280 seconds, CPU utilization=340.872 percent, peak per-process RSS=1299200 KiB, and warnings=4.
inferred:
  - INFERRED: Fixed collection and serial-lane cost now dominates; adding pytest subprocesses beyond 10 increased scheduling overhead without reducing the parallel critical path.
conclusion: Pytest concurrency 12 is valid but slower than concurrency 10; the stopping condition is met and concurrency 10 is selected.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/admission-exp031-p12.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/l
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp031-p12-console.log
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp031-p12-outer-time.txt
decision: STOP_AND_SELECT_P10
next_experiment: CP-007
```

## CP-007 — Pytest concurrency selected; merge-ready verification pending

```yaml
checkpoint_id: CP-007
status: COMPLETE
timestamp: 2026-09-15T22:42:15+08:00
selected_configuration:
  pytest_subprocess_concurrency: 10
  validated_timing_input: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp029-p8-fresh-timings.xml
  total_elapsed_s: 27.072288793046027
selection_evidence:
  - Concurrency 4, 6, 8, 10, and 12 each passed all 3056 ordinary pytest nodes exactly once with the same collection hash and complete cleanup.
  - Concurrency 10 was the fastest valid observation; concurrency 12 took 27.951860055094585 seconds and was 3.249 percent slower.
  - The canonical comparison artifact SHA256 is `bbf05d479a3f58764b3988350c3ee73e32d0eaf842bb2e08a61333b01dd77db8`.
  - An initial derived comparison had incorrect run_id labels only; it is retained as `pytest-concurrency-comparison.invalid-run-labels.json` and excluded from conclusions.
scope_readback:
  - Executable changes are limited to tools/so101_pytest_gate.py, tools/so101_pytest_manifest.py, and src/so101_demo_py/test/test_pytest_full_gate_runner.py.
  - This ledger is the only non-pytest file changed and is required audit documentation.
  - No SO-101 application Worker W1-W10, Gazebo, MoveIt, GUI, or benchmark validation was run after the resumed scope correction.
cleanup:
  - Runner-owned children were fully reaped for every selected-scope full-suite run.
  - Final process readback recorded no pytest-gate, pytest, ROS-daemon, simulator, or MuJoCo process.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/pytest-concurrency-comparison.json
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/pytest-concurrency-comparison.invalid-run-labels.json
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/final-process-cleanup.txt
retained_runs:
  - Entire registered evidence root, including interrupted scratch/g and all valid/invalid experiment artifacts.
archived_runs:
  - NONE
deletion_candidates:
  - All scratch trees and build/install/log trees under the registered evidence root after final readback; no deletion is authorized or performed.
next_experiment: WAIT_FOR_USER
```

## EXP-032-DEFAULT-P8-TDD — Make pytest concurrency 8 the startup default

```yaml
experiment_id: EXP-032-DEFAULT-P8-TDD
status: RUNNING
status_history:
  - status: PLANNED
    at: 2026-09-15T23:17:30+08:00
  - status: RUNNING
    at: 2026-09-15T23:18:22+08:00
prior_experiment: EXP-031-PYTEST-P12
hypothesis: Making --workers optional with default 8 preserves explicit overrides and makes an otherwise valid invocation select concurrency 8.
prediction: A focused parser contract fails before the implementation because --workers is required, then passes after the one-line parser change.
single_variable: CLI default for pytest subprocess concurrency changes from required input to 8.
lifecycle: REUSE_STACK
preconditions:
  - Source starts at commit 6c3763cf4d1df684c4e21f53cebcf4623c447eae with a clean worktree.
  - Target worktree has one pre-existing dirty user file, src/so101_demo_py/test/test_parallel_batch_resources.py, which is outside this change and must remain untouched.
  - No pytest, ROS daemon, Gazebo, or MuJoCo runtime process is active.
success_criteria:
  - Focused test demonstrates RED for the currently required option and GREEN after default 8 is implemented.
  - Explicit --workers remains accepted.
failure_criteria:
  - Default is not 8, explicit override breaks, or any focused runner contract fails.
invalid_criteria:
  - Source drift outside the runner test, runner implementation, and this ledger; scratch collision; external interruption.
provenance:
  source_commit: 6c3763cf4d1df684c4e21f53cebcf4623c447eae
  install_overlay: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/install-exp022
  runtime_executable: /usr/bin/python3
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - Add a focused parser contract, run it RED from fresh scratch/m, apply the minimal parser default, then rerun GREEN from the same isolated focused-test scratch.
observed:
  - Source has only this ledger dirty; target retains exactly its pre-existing test_parallel_batch_resources.py modification; scratch/m is absent and no relevant runtime process is active.
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/m
decision: RUN
next_experiment: EXP-033-DEFAULT-P8-FULL
```

### EXP-032 result update

```yaml
status: VALID
status_history:
  - status: VALID
    at: 2026-09-15T23:20:28+08:00
commands:
  - command: /usr/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_pytest_full_gate_runner.py::test_cli_defaults_to_eight_workers_when_omitted -q
    exit_code: 1
  - command: /usr/bin/python3 -m pytest -p no:cacheprovider src/so101_demo_py/test/test_pytest_full_gate_runner.py -q
    exit_code: 0
  - command: /home/lenovo/.local/bin/ruff check tools/so101_pytest_gate.py src/so101_demo_py/test/test_pytest_full_gate_runner.py
    exit_code: 0
  - command: /home/lenovo/.local/bin/ruff format --check tools/so101_pytest_gate.py src/so101_demo_py/test/test_pytest_full_gate_runner.py
    exit_code: 0
observed:
  - OBSERVED: RED failed in 0.43 seconds because argparse still required --workers.
  - OBSERVED: After the one-line default=8 change, all 30 focused contracts passed in 0.30 seconds.
  - OBSERVED: An explicit-override compatibility contract then joined the suite; all 31 contracts passed in 0.31 seconds.
  - OBSERVED: Ruff check and format-check both passed for the two modified pytest files.
inferred:
  - NONE
conclusion: Omitting --workers now selects 8, and an explicit --workers 10 continues to override the default.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/m
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/n
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/o
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp032-default-p8-red.log
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp032-default-p8-green.log
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp032-default-p8-compat.log
decision: KEEP
next_experiment: EXP-033-DEFAULT-P8-FULL
```

## EXP-033-DEFAULT-P8-FULL — Committed default-start full ordinary pytest verification

```yaml
experiment_id: EXP-033-DEFAULT-P8-FULL
status: RUNNING
status_history:
  - status: PLANNED
    at: 2026-09-15T23:20:28+08:00
  - status: RUNNING
    at: 2026-09-15T23:21:20+08:00
prior_experiment: EXP-032-DEFAULT-P8-TDD
hypothesis: The committed runner passes the full ordinary pytest gate when --workers is omitted, and records worker_count 8.
prediction: Exact ordinary-node PASS with worker_count=8, unchanged collection semantics, readable JUnit evidence, and complete child cleanup.
single_variable: Invoke the committed runner without --workers.
lifecycle: REUSE_STACK
preconditions:
  - Default-P8 implementation and ledger are committed together; exact /usr/bin/python3 and task overlay/source shim provenance are preserved.
  - A new one-character run ID is previously nonexistent and the timing input remains the validated EXP-028 P6 merged JUnit used by the prior P8 run.
  - No conflicting pytest, ROS daemon, Gazebo, or MuJoCo process is active.
success_criteria:
  - Runner summary reports PASS, worker_count=8, exact expected/actual node equality, benchmark exclusion, and complete cleanup.
failure_criteria:
  - Any test/process/coverage/JUnit/provenance/timeout/cleanup gate fails or worker_count differs from 8.
invalid_criteria:
  - Source/environment/timing-input drift, scratch collision, or external interruption.
provenance:
  source_commit: ae62559645c1a045c53bf5c376a0ef6e8e67343e
  install_overlay: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/install-exp022
  runtime_executable: /usr/bin/python3
  timing_input: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp028-p6-fresh-timings.xml
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - Run tools/so101_pytest_gate.py without --workers from commit ae62559645c1a045c53bf5c376a0ef6e8e67343e using fresh run ID p and the EXP-028 timing input.
observed:
  - PENDING
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/p
decision: RUN
next_experiment: EXP-034-MERGE
```

### EXP-033 invalidation update

```yaml
status: INVALID
status_history:
  - status: INVALID
    at: 2026-09-15T23:22:05+08:00
commands:
  - command: tools/so101_pytest_gate.py without --workers using run ID p
    exit_code: 1
observed:
  - OBSERVED: No pytest subprocess launched; the runner rejected scratch/p with FileExistsError.
  - OBSERVED: scratch/p was created at 2026-09-15T17:08:42+08:00 by an earlier experiment and contains retained evidence.
  - OBSERVED: The runner's failure summary records worker_count=8, independently confirming that omitted --workers resolved to the new default before layout validation.
  - OBSERVED: The admission shell used `test ! -e scratch/p` without fail-fast; subsequent commands masked that nonzero result.
inferred:
  - NONE
conclusion: EXP-033 is INVALID because its selected scratch path was not fresh; runner behavior was correct and no implementation change is required.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/admission-exp033-default-p8-full.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/p/summary.json
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp033-default-p8-full-console.log
decision: RETAIN_INVALID
next_experiment: EXP-034-DEFAULT-P8-FULL-RETRY
```

## EXP-034-DEFAULT-P8-FULL-RETRY — Fresh-scratch committed default verification

```yaml
experiment_id: EXP-034-DEFAULT-P8-FULL-RETRY
status: PLANNED
prior_experiment: EXP-033-DEFAULT-P8-FULL
hypothesis: With a truly fresh scratch path and fail-fast admission, the committed runner invoked without --workers passes the full ordinary gate at worker_count 8.
prediction: Exact ordinary-node PASS, worker_count=8, complete cleanup, and no benchmark collection.
single_variable: Replace stale run ID p with verified-new run ID q; command and candidate remain otherwise unchanged.
lifecycle: REUSE_STACK
preconditions:
  - Candidate remains ae62559645c1a045c53bf5c376a0ef6e8e67343e with only this ledger dirty and allowlisted.
  - A fail-fast admission command verifies scratch/q is absent immediately before launch.
  - Exact Python, overlay, source shim, and EXP-028 timing input remain fixed.
success_criteria:
  - Runner summary reports PASS, worker_count=8, exact expected/actual node equality, benchmark exclusion, and complete cleanup.
failure_criteria:
  - Any test/process/coverage/JUnit/provenance/timeout/cleanup gate fails or worker_count differs from 8.
invalid_criteria:
  - Source/environment/timing-input drift, scratch collision, or external interruption.
provenance:
  source_commit: ae62559645c1a045c53bf5c376a0ef6e8e67343e
  install_overlay: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/install-exp022
  runtime_executable: /usr/bin/python3
  timing_input: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp028-p6-fresh-timings.xml
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - PENDING
observed:
  - PENDING
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/q
decision: PENDING
next_experiment: EXP-035-MERGE
```

### EXP-034 preflight invalidation

```yaml
status: INVALID
status_history:
  - status: RUNNING
    at: 2026-09-15T23:23:11+08:00
  - status: INVALID
    at: 2026-09-15T23:23:11+08:00
commands:
  - command: fail-fast assertion that scratch/q is absent
    exit_code: 1
observed:
  - OBSERVED: The fail-fast admission stopped immediately; no pytest or gate runner launched.
  - OBSERVED: scratch/q was created at 2026-09-15T17:26:27+08:00 and is retained evidence.
inferred:
  - NONE
conclusion: EXP-034 is INVALID before test launch because run ID q was not fresh; the corrected admission behavior prevented reuse.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/q
decision: RETAIN_INVALID
next_experiment: EXP-035-DEFAULT-P8-FULL-RETRY
```

## EXP-035-DEFAULT-P8-FULL-RETRY — Fresh-scratch committed default verification

```yaml
experiment_id: EXP-035-DEFAULT-P8-FULL-RETRY
status: RUNNING
status_history:
  - status: PLANNED
    at: 2026-09-15T23:23:40+08:00
  - status: RUNNING
    at: 2026-09-15T23:24:03+08:00
prior_experiment: EXP-034-DEFAULT-P8-FULL-RETRY
hypothesis: With verified-new run ID r and fail-fast admission, the committed runner invoked without --workers passes the full ordinary gate at worker_count 8.
prediction: Exact ordinary-node PASS, worker_count=8, complete cleanup, and no benchmark collection.
single_variable: Replace stale run ID q with verified-new run ID r; command and candidate remain otherwise unchanged.
lifecycle: REUSE_STACK
preconditions:
  - Candidate remains ae62559645c1a045c53bf5c376a0ef6e8e67343e with only this ledger dirty and allowlisted.
  - A fail-fast admission command verifies scratch/r is absent immediately before launch.
  - Exact Python, overlay, source shim, and EXP-028 timing input remain fixed.
success_criteria:
  - Runner summary reports PASS, worker_count=8, exact expected/actual node equality, benchmark exclusion, and complete cleanup.
failure_criteria:
  - Any test/process/coverage/JUnit/provenance/timeout/cleanup gate fails or worker_count differs from 8.
invalid_criteria:
  - Source/environment/timing-input drift, scratch collision, or external interruption.
provenance:
  source_commit: ae62559645c1a045c53bf5c376a0ef6e8e67343e
  install_overlay: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/install-exp022
  runtime_executable: /usr/bin/python3
  timing_input: /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp028-p6-fresh-timings.xml
  ros_domain_id: UNSET_NO_ROS_RUNTIME
  gz_partition: UNSET_NO_SIMULATOR
commands:
  - Run a fail-fast admission and tools/so101_pytest_gate.py without --workers using fresh run ID r.
observed:
  - PENDING
inferred:
  - NONE
conclusion: PENDING
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/r
decision: RUN
next_experiment: EXP-036-MERGE
```

### EXP-035 result update

```yaml
status: VALID
status_history:
  - status: VALID
    at: 2026-09-15T23:25:30+08:00
commands:
  - command: tools/so101_pytest_gate.py --evidence-root /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01 --run-id r --timings /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp028-p6-fresh-timings.xml --python /usr/bin/python3 --expected-source-commit ae62559645c1a045c53bf5c376a0ef6e8e67343e --allow-dirty-path docs/experiments/so101-pytest-parallel-gate-experiment-ledger.md --timeout-s 1200
    exit_code: 0
observed:
  - OBSERVED: Runner PASS with worker_count=8 and exact 3058 expected/actual nodes; collection SHA256 is `dd1beda7f4370f0faf9361ccec70e48949c4ab4aabf1f0f2ef0cfea832bdbbe5`.
  - OBSERVED: Setup=5.353 seconds, serial lane=10.944 seconds, parallel critical path=49.012 seconds, runner total=65.494 seconds, aggregate CPU time=123.900 seconds, and peak per-process RSS=1814416 KiB.
  - OBSERVED: All child processes were reaped; benchmark paths remained excluded; the only dirty source path remained this allowlisted ledger.
inferred:
  - NONE
conclusion: The committed default-W8 runner passes the complete ordinary pytest gate when --workers is omitted.
evidence:
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/admission-exp035-default-p8-full.txt
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/scratch/r
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp035-default-p8-full-console.log
  - /data/work/so101-evidence/pytest-parallel-gate/20260915-w1-w2-w4-a01/exp035-default-p8-full-outer-time.txt
decision: KEEP
next_experiment: EXP-036-MERGE
```

## CP-008 — Default-W8 source branch ready to merge

```yaml
checkpoint_id: CP-008
status: COMPLETE
timestamp: 2026-09-15T23:25:30+08:00
last_valid_experiment: EXP-035-DEFAULT-P8-FULL-RETRY
current_hypothesis: Local no-ff merge can preserve the target worktree's pre-existing unstaged test modification because the feature branch does not change that file.
working_tree_status: only this ledger is dirty; implementation commit ae62559645c1a045c53bf5c376a0ef6e8e67343e is committed
owned_processes: NONE
preserved_processes: NONE
confirmed_conclusions:
  - Default startup selects pytest concurrency 8 and explicit overrides remain supported.
  - Focused runner contracts are 31/31 GREEN and the default-start full ordinary gate is 3058/3058 PASS.
disproven_routes:
  - Run IDs p and q are not fresh and must not be reused.
open_risks:
  - The target branch has one pre-existing unstaged change in src/so101_demo_py/test/test_parallel_batch_resources.py; its content and unstaged status must survive the merge unchanged.
retained_runs:
  - Entire registered evidence root, including invalid p/q admission attempts and valid scratch/r.
archived_runs:
  - NONE
deletion_candidates:
  - All task scratch, build, install, and log trees; no deletion is authorized or performed.
next_command: git -C /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool merge --no-ff codex/pytest-gate-parallelism
```
