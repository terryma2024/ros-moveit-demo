# SO-101 Parallel Adaptive Worker Pool Experiment Ledger

```yaml
task_id: so101-adaptive-worker-pool
goal: Implement and qualify the lightweight adaptive worker pool from W8 through W1 for MuJoCo MoveIt expert execute batches.
success_contract: Complete all 13 implementation tasks, automated gates, two live infrastructure fault injections, one 20/20 execute batch, and valid W1/W2/W4/W6/W8 performance samples without changing v1 behavior.
worktree: /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool
branch: codex/parallel-adaptive-worker-pool
base_commit: 4c777fa722586be92a0b357b861ab4ce460a06ab
current_commit: 467065a0f55e4fad9eea68741598fce0c8c14386
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01
confirmed_conclusions:
  - origin/main equals the reviewed baseline 4c777fa722586be92a0b357b861ab4ce460a06ab; startup preflight CP-001.
  - the legacy worktree remains at 2d13ae65490cf1eccfd57fa683e4b13b41784402 with its untracked admission test preserved; startup preflight CP-001.
  - no SO-101, MoveIt, MuJoCo, Gazebo, or RViz runtime process and no ROS_DOMAIN_ID 0 node was observed before implementation; startup preflight CP-001.
  - Task 1 adaptive contracts passed an auditable missing-module RED replay and a 61-test GREEN gate including frozen v1 contracts; commit eae9742d60d3213137dabe7d3716e0b3082ff127.
  - Task 2 explicit adaptive CLI passed 111 adaptive/CLI tests and 100 frozen v1 contract/journal/crash-recovery tests; commit 79538ee04b850ab0cebc39c46dddbff50b63f04c.
  - Task 3 adaptive point affinity and stealing passed 136 scheduler tests plus 145 coordinator/fault-injection regressions; commit 59f4cc96c7299f998d1c106cc75f77b29c729eef.
  - Task 4 observational W8 resources, persistent claims, authenticated READY barrier, and pre-release linearization passed a 370-test combined gate and 85-test v1 CLI rerun; commit 6b8101099203fa0017dc1e5645140d4704879465.
  - Task 5 fsync-backed cross-generation fallback runner passed 10 state-machine, conflict, path, and replay tests; commit 3ba9abd1561bf028fb2512ef68d542b241485b70.
  - Task 6 production Workers and the adaptive production factory passed 265 split tests; commit b983d521f.
  - Task 7 per-model adaptive perception queues passed 367 Broker, runtime, IPC, and spec tests; commit a50aae938.
  - Task 8 first-failure convergence, verified persistent-claim release, exact external cleanup, adaptive aggregate output, and wrapper supervision passed the focused and specified regression gates; evidence is in task-08/failure-and-cleanup.md.
disproven_routes:
  - the superseded heavy AdmissionAuthority/profile/Ed25519/cgroup/canary design is outside this task and will not be reused.
open_hypotheses:
  - the lightweight contracts and factory boundary can extend W1-W8 while preserving frozen v1 W1-W3 behavior and serialized bytes.
  - exact cleanup and persistent Domain markers are sufficient for safe fallback without broad process discovery.
latest_checkpoint: CP-002
next_experiment: EXP-002A
```

## Evidence policy

- Registered evidence root: `/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01`.
- Every ai-station pytest or colcon invocation uses a unique, previously nonexistent directory under `scratch/<test-run-id>/tmp` for `TMPDIR`, `TMP`, and `TEMP`.
- Scratch directories, logs, manifests, screenshots, and runtime evidence are retained unless the user separately authorizes deletion.
- `/data/work/ws_moveit/.worktrees/parallel-w8-admission-v2`, its untracked test, and `/data/work/so101-evidence/parallel-w8/20260913-q01` are read-only preserved external state.

## EXP-001 — Automated adaptive contracts and package integration

```yaml
experiment_id: EXP-001
status: VALID
prior_experiment: NONE
hypothesis: The adaptive contracts, scheduler, production adapter, cleanup path, and CLI can satisfy the lightweight design while leaving v1 behavior unchanged.
prediction: Task-level RED tests fail only because each planned interface is absent, then pass after minimal implementation; the final so101_demo_py package gate collects nonzero ordinary tests with zero errors and failures.
single_variable: Introduce only the explicit adaptive-workers path described by the reviewed plan.
lifecycle: ISOLATED_STACK
preconditions:
  - source starts from origin/main commit 4c777fa722586be92a0b357b861ab4ce460a06ab in the dedicated worktree.
  - no live SO-101 stack is used by this automated experiment.
  - each test command receives a fresh NVMe scratch directory and verified tempfile path.
success_criteria:
  - every planned RED fails at the intended missing behavior boundary.
  - every task GREEN and compatibility regression exits 0.
  - package test collects nonzero tests only under src/so101_demo_py/test and reports zero errors and failures.
failure_criteria:
  - a planned contract remains absent, a compatibility regression appears, or package test reports an error or failure.
invalid_criteria:
  - source, Python, install overlay, or scratch provenance differs from the recorded command.
provenance:
  source_commit: 4c777fa722586be92a0b357b861ab4ce460a06ab
  qualified_feature_commit: 467065a0f55e4fad9eea68741598fce0c8c14386
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool/install
  runtime_executable: /usr/bin/python3
  torch: 2.13.0+cu130 from /data/work/venvs/so101-v5-t004-perception/lib/python3.12/site-packages
  submodule_commit: c16b5a5fe880b6e1857f56486dab4ae726576969
  ros_domain_id: 0
  gz_partition: adaptive-worker-exp001-contracts
commands:
  - command: per-task pytest RED/GREEN commands and final colcon package gate from the implementation plan
    exit_code: 0
observed:
  - Startup preflight is recorded at /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/preflight/dispatch-preflight.md.
  - Baseline-007 passed all 1111 existing parallel-batch tests in 50.51 s outside the sandbox with current-checkout so101_demo source mapping and existing ai-station ROS/MuJoCo dependency overlay.
  - Task 2 RED failed at the absent adaptive parser boundary; the final Task 2 GREEN passed 111/111 and the v1 compatibility gate passed 100/100. Evidence is recorded in task-02/cli-contract.md.
  - Task 3 focused RED failed only at the absent adaptive selector module; GREEN passed 136/136 and concurrency/fault regression passed 145/145. Evidence is recorded in task-03/adaptive-scheduler.md.
  - Task 4 final combined gate passed 370/370 after the intended missing-policy RED; a short-path v1 CLI rerun passed 85/85. Evidence is recorded in task-04/readiness-and-resources.md.
  - Task 5 missing-module RED was followed by 10/10 GREEN for startup and runtime fallback, terminal preservation, cleanup failure, attempt limits, append-only events, and crash report-only replay. Evidence is recorded in task-05/fallback-runner.md.
  - Task 6 production adapter RED failed at 12 absent production/factory/classifier boundaries; split GREEN and compatibility gates passed 265/265. Evidence is recorded in task-06/production-adapter.md.
  - Task 7 Broker capacity RED failed at four absent override boundaries; Broker/perception/runtime/IPC/spec GREEN gates passed 367/367. Evidence is recorded in task-07/perception-queue.md.
  - Task 8 RED failed at the four absent supervision/cleanup/output boundaries. The final focused integration gate passed 5/5; process, crash-recovery, resource, and post-review CLI/integration regressions passed 17/17, 33/33, 136/136, and 93/93. Evidence is recorded in task-08/failure-and-cleanup.md.
  - Task 9 targeted adaptive integration passed 71/71. The complete candidate overlay package gate collected 2995 ordinary tests: 2994 passed, 1 skipped, 0 errors, and 0 failures in 90.76 s; benchmark_test was not collected. Evidence is recorded in task-09/package-integration.md.
inferred:
  - The package-local libexec directory must be on PATH for direct console-script invocation; ROS 2 package discovery alone exposes the same commands through ros2 pkg executables.
conclusion: The adaptive implementation and its frozen v1 compatibility contracts pass the complete ordinary package suite from one candidate-local overlay and one absolute system Python provenance chain.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01
decision: Proceed to isolated MuJoCo startup and runtime fault injection.
next_experiment: EXP-002A
```

## CP-001 — Dispatch and implementation baseline

```yaml
checkpoint_id: CP-001
last_valid_experiment: NONE
current_hypothesis: The reviewed lightweight design can be implemented from the clean origin/main baseline without using the preserved heavy branch.
working_tree_status: clean at 4c777fa722586be92a0b357b861ab4ce460a06ab before ledger creation
owned_processes: current Codex session only; no SO-101 runtime process started
preserved_processes: tmux sessions codex and codex-task-so101-adaptive-worker-pool; no codex-cua or legacy admission session existed at preflight
confirmed_conclusions:
  - origin/main was fetched from Gitee and equals the required reviewed commit.
  - target worktree and branch were absent before creation, then created at the required path and commit.
  - ROS_DOMAIN_ID 0 had no visible nodes, and no matching SO-101 runtime process was present.
disproven_routes:
  - reuse of the old heavy W8 worktree is prohibited and unnecessary.
open_risks:
  - the root workspace install overlay contains a stale so101_demo_py hook; all build and runtime provenance must use the new worktree overlay.
  - live MuJoCo, Docker broker, model, GPU, and GUI availability remain unverified until later task gates.
  - baseline-001 through baseline-005 are invalid environment probes and their scratch trees are deletion candidates; baseline-007 is the valid subsystem baseline.
next_command: dispatch Task 1 implementer from its generated brief
```

## CP-002 — Automated implementation and package acceptance

```yaml
checkpoint_id: CP-002
last_valid_experiment: EXP-001
current_hypothesis: Exact owned-identity fault injection will cause the adaptive runner to clean W8 and continue at W6 without touching task-external sentinels.
working_tree_status: Task 9 integration test and this ledger update are the only intended changes after commit 467065a0f.
source_commit: 467065a0f55e4fad9eea68741598fce0c8c14386
install_prefix: /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool/install/so101_demo_py
package_gate: 2995 tests, 0 errors, 0 failures, 1 skipped
owned_processes: current Codex session only; all harmless pytest subprocesses were retired by their owning fixtures
preserved_processes: preflight tmux sessions and the legacy admission worktree remain untouched
confirmed_conclusions:
  - adaptive config and cleanup console entry are installed in the candidate overlay.
  - six explicit adaptive CLI options are present and abandoned heavy-admission options and imports are absent.
  - the pinned mujoco_ros2_control submodule and candidate support/teleop installs satisfy installed provenance.
invalid_runs:
  - task-09-package lacked the approved ML dependency path and collected zero tests.
  - task-09-package-r2 used an incomplete candidate overlay and had six install-provenance failures.
  - task-09-package-r3 had one transient domain-lock race failure; the test passed alone and task-09-package-r4 passed the full suite.
open_risks:
  - live Docker, CUDA, MuJoCo, MoveIt, model, and GUI readiness are not yet proven.
  - direct console commands require the installed package libexec directory on PATH.
next_command: implement and RED/GREEN test exact adaptive Worker fault injection
```
