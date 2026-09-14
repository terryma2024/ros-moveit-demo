# SO-101 Parallel Adaptive Worker Pool Experiment Ledger

```yaml
task_id: so101-adaptive-worker-pool
goal: Implement and qualify the lightweight adaptive worker pool from W8 through W1 for MuJoCo MoveIt expert execute batches.
success_contract: Complete all 13 implementation tasks, automated gates, two live infrastructure fault injections, one 20/20 execute batch, and valid W1/W2/W4/W6/W8 performance samples without changing v1 behavior.
worktree: /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool
branch: codex/parallel-adaptive-worker-pool
base_commit: 4c777fa722586be92a0b357b861ab4ce460a06ab
current_commit: 3d35cb017caddcb7ffecc667f031fde25a162903
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
  - Task 10 exact startup and active-attempt fault injections each produced one W8-to-W6 transition, preserved task-external sentinels, completed every assigned point, and reported complete cleanup; accepted runs su09 and mr08.
disproven_routes:
  - the superseded heavy AdmissionAuthority/profile/Ed25519/cgroup/canary design is outside this task and will not be reused.
open_hypotheses:
  - the lightweight contracts and factory boundary can extend W1-W8 while preserving frozen v1 W1-W3 behavior and serialized bytes.
  - exact cleanup and persistent Domain markers are sufficient for safe fallback without broad process discovery.
latest_checkpoint: CP-003
next_experiment: EXP-003
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

## EXP-002A — Startup fault before readiness

```yaml
experiment_id: EXP-002A
status: VALID
prior_experiment: EXP-001
hypothesis: Terminating one registered W8 Worker before POOL_RUNNING and before any lease is granted will make the runner clean W8 and continue at W6 without affecting processes outside the batch manifest.
prediction: W8 grants zero leases, one 8-to-6 fallback occurs, W6 reaches readiness and completes all four points, cleanup succeeds, and both task-owned side sentinels survive.
single_variable: Send SIGTERM to the exact registered W8 Worker identity before POOL_RUNNING and LEASE_GRANTED.
lifecycle: ISOLATED_STACK
batch_id: su09
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/su09
provenance:
  source_commit: 3d35cb017caddcb7ffecc667f031fde25a162903
  broker_image_id: sha256:3b1a6661a87359729b848cb92807c0e45f618ae2dec0e20a1f534e51f6148a79
  broker_source_sha256: 286b5d9f4e994e897c1c01bb75c79d399dbbeaba573a7779424e4a498146a37e
  runtime_executable: /usr/bin/python3
  initial_worker_count: 8
  fallback_worker_counts: [6, 4, 2, 1]
observed:
  - The injector selected worker01 with PID and PGID 3911563 and start ticks 118345028 before POOL_RUNNING and before any lease was granted.
  - W8 granted zero leases. The only transition was W8 to W6 after the injected Worker exited with signal 15.
  - W6 completed task_start, cup_test_forward_5cm, sample_05_near_center, and sample_14_far_right as PASSED.
  - The batch finished COMPLETED in 179.47665203316137 seconds with levels_used [8, 6], final_worker_count 6, and batch_cleanup_complete true.
  - Domains 215 through 220 were released, and no owned process remained in either generation manifest.
  - The recorded sleep and ROS Domain 230 sentinels retained their original PID, PGID, session, and start-tick identities after the batch.
invalid_runs:
  - su01 through su08 were retained as diagnostic or invalid attempts and were not used for acceptance.
conclusion: Exact failure of a registered Worker before readiness causes one clean startup fallback from W8 to W6. No task-external process was removed.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/su09
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-10/exp002a-r9-injection.txt
decision: Accept EXP-002A and run the active-attempt fault experiment.
next_experiment: EXP-002B
```

## EXP-002B — Active attempt fault after committed work

```yaml
experiment_id: EXP-002B
status: VALID
prior_experiment: EXP-002A
hypothesis: Terminating the Worker for one active attempt after W8 has committed work will preserve terminal results, mark unfinished work as infrastructure interrupted, and let W6 process only unfinished points.
prediction: The injected attempt receives POINT_INFRA_INTERRUPTED, previously committed points are not rerun, one 8-to-6 fallback occurs, W6 passes the interrupted and remaining points through the initial gate, all 20 points pass, cleanup succeeds, and both side sentinels survive.
single_variable: Send SIGTERM to the exact Worker identity of one active second-wave attempt after eight W8 results are committed.
lifecycle: ISOLATED_STACK
batch_id: mr08
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/mr08
provenance:
  source_commit: 3d35cb017caddcb7ffecc667f031fde25a162903
  broker_image_id: sha256:3b1a6661a87359729b848cb92807c0e45f618ae2dec0e20a1f534e51f6148a79
  broker_source_sha256: 286b5d9f4e994e897c1c01bb75c79d399dbbeaba573a7779424e4a498146a37e
  runtime_executable: /usr/bin/python3
  initial_worker_count: 8
  fallback_worker_counts: [6, 4, 2, 1]
observed:
  - Before injection, W8 had committed exactly eight first-wave points: sample_01_near_left, sample_04_near_left, cup_test_left_5cm, task_start, sample_02_near_center, cup_test_right_5cm, sample_03_near_right, and cup_test_forward_5cm.
  - The injector selected worker05 for sample_05_near_center lease 1 with PID and PGID 30934 and start ticks 118883715 while that second-wave attempt was active.
  - The top journal records POINT_INFRA_INTERRUPTED for sample_05_near_center and every other unfinished point. None of the eight terminal W8 points received another business attempt.
  - W6 admitted sample_05_near_center through a new POINT_INITIAL_GATE with all checks true and later committed it PASSED. W6 committed exactly the interrupted point and the other 11 points that were unfinished at injection.
  - The batch finished COMPLETED in 439.67304879799485 seconds with 20 PASSED points, levels_used [8, 6], one W8-to-W6 transition, final_worker_count 6, and batch_cleanup_complete true.
  - Domains 215 through 220 were released, both generation manifests had no owned process, and no broker container remained.
  - Both recorded side sentinels survived this batch. Their exact process groups were stopped only after identity revalidation, and the dedicated sentinel tmux session was then absent.
invalid_runs:
  - mr01 through mr05 exposed production race and clock defects and were retained as diagnostic evidence.
  - mr06 completed all 20 points but used levels [8, 6, 4], so it was retained as recovery evidence rather than acceptance for the predicted single transition.
  - mr07 failed naturally before injection because a publisher clock became stale. The task-owned runner and watcher were stopped, cleanup completed, and the run was retained as invalid.
fixes_from_diagnostic_runs:
  - f10106bd2, 53a404f99, c128ebbaa, a5fc810ff, 35a9ac8bd, 70598fe26, e5001ade4, be4c08a11, e33e59537, 47dd44445, a6421af8e, 7169a68ce, and 3d35cb017.
conclusion: An exact active-attempt Worker failure preserves committed results and moves only unfinished work to W6. All 20 points passed, cleanup was exact, and the sentinels were unaffected.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/mr08
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-10/exp002b-r8-injection.txt
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-10/sentinels-04/cleanup-readback.txt
decision: Accept EXP-002B and proceed to the uninjected 20-point adaptive regression.
next_experiment: EXP-003
```

## CP-003 — Fault-injection acceptance

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-002B
current_hypothesis: The same qualified W8-to-W1 ladder can complete the 20-point catalog without injection and with every point passing its fresh initial-state gate.
working_tree_status: clean at 3d35cb017caddcb7ffecc667f031fde25a162903 before this ledger update
source_commit: 3d35cb017caddcb7ffecc667f031fde25a162903
accepted_batches: [su09, mr08]
owned_processes: current Codex session only; accepted batch manifests are empty and the dedicated sentinel process groups were stopped after exact identity checks
preserved_processes: pre-existing process groups 3835752, 3835753, 3882463, and 3882464; tmux sessions codex and codex-task-so101-adaptive-worker-pool
confirmed_conclusions:
  - startup Worker loss before readiness grants no W8 lease and falls back once to W6.
  - active-attempt Worker loss preserves eight W8 terminal results and sends only unfinished work to W6.
  - both accepted batches released their Domains, sockets, broker container, and manifest-owned processes.
  - exact task-external sentinel identities survived both fault injections.
retained_runs:
  - accepted: r/su09 and r/mr08
  - diagnostic_or_invalid: r/su01 through r/su08 and r/mr01 through r/mr07
archived_runs: []
deletion_candidates:
  - all scratch trees under scratch/r31 through scratch/r39 after their recorded readback
  - no candidate may be deleted without explicit user authorization
open_risks:
  - uninjected 20-point execution and visual readback have not yet been qualified.
  - W1, W2, W4, W6, and W8 no-fallback performance samples have not yet been collected.
next_command: run EXP-003 as batch e2001 with initial-points-per-worker 3
```
