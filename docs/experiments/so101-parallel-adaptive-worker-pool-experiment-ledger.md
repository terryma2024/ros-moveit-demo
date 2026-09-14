# SO-101 Parallel Adaptive Worker Pool Experiment Ledger

```yaml
task_id: so101-adaptive-worker-pool
goal: Fix the Broker accept-idle deadline defect, add bounded eight-client Broker connections and default C2 independent YOLO execution, and qualify fixed-W8 tail latency without weakening correctness or fallback semantics.
success_contract: Complete each planned RED/GREEN implementation task and commit separately, pass the ordinary package gate, prove eight authenticated clients with YOLO peak two and at-most-once logical inference, complete a fixed-W8 20-point run with zero TRUNCATED_FRAME and READY-to-POSE_ACCEPTED p95 below 5 s, preserve normal adaptive fallback behavior, and perform exact cleanup.
worktree: /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool
branch: codex/parallel-adaptive-worker-pool
base_commit: 4c777fa722586be92a0b357b861ab4ce460a06ab
current_commit: 167c74a941782e37ed1369ee10c42ac6b77088a9
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
  - Task 11 uninjected adaptive execute regression completed all 20 points as PASSED at levels W8 and W6, with complete cleanup and fresh terminal visual evidence; accepted run e2001.
  - EXP-005 measured valid standalone YOLO-Seg levels 1, 2, 4, 6, and 8; the highest admitted stable level is 8, throughput saturation is 4, and conservative initial production Broker parallelism is 2.
  - EXP-006 completed all 20 execute points at fixed W8 with no fallback and complete timing/cleanup evidence; the 1.507 s median composite perception chain was driven by a 1.432 s median serialized Broker round trip, while every configured stage budget remained satisfied.
  - EXP-006 supplemental causal audit confirmed that sample_13_far_center and sample_15_far_center `TRUNCATED_FRAME` errors came from the 5 s AuthenticatedUnixServer cycle deadline starting before accept and exhausting the handler/reply remainder; identical idempotent retries recovered both original QUALIFIED results.
  - EXP-006 used a 240 s consumer get_one timeout, so none of its 20 points timed out under current configuration; against the separate 5 s target SLO, 5/20 exceeded from get_one start to POSE_ACCEPTED and 4/20 exceeded from consumer READY to accepted.
  - Task 15 preflight at CP-010 confirmed the required linked worktree and HEAD, preserved the three existing dirty paths, and found no conflicting process, ROS node on Domains 0/215-222, Docker container, GPU compute app, or tmux session.
  - Task 15 implementation through CP-011 is committed at 3677e9d97f1367f861496817cee5edeb4349871f; EXP-007R2 qualified eight authenticated Broker clients with C2 YOLO execution, queue depth five, eight distinct logical inferences, zero replay, and zero transport truncation.
  - EXP-008 live-01 and live-02 are INVALID preflight attempts, and live-03 is INVALID because systemd-oomd killed its 16.2 GiB tmux scope before any point lease; CP-012.
  - Task 10 independent review is accepted after correcting the audit record: the timeout RED/GREEN stdout streams are unavailable, while the adjacent 40-test log remains retained; CP-019.
  - Task 11 final ordinary package collection at source 167c74a941782e37ed1369ee10c42ac6b77088a9 collected 3035 tests: 3033 passed, 1 skipped, and the sole failure is the preserved task-external dirty test test_transient_unclassified_proc_read_error_is_retried; CP-019.
disproven_routes:
  - the superseded heavy AdmissionAuthority/profile/Ed25519/cgroup/canary design is outside this task and will not be reused.
  - A hidden transport pre-accept delay is the dominant W8 `/cup_pose` cost; its 0.091 s median was below internal Broker queue wait, response delivery, model execution, and the full Broker round trip.
  - YOLO compute, RGB capture, simulation pause/resume, exact-TF localization, numeric capture, pose admission, or DDS callback delivery is the first expected-budget violation in EXP-006; no configured budget was violated.
  - The two EXP-006 `TRUNCATED_FRAME` events are ordinary Broker internal queue waits; their failure boundary was the separate accept-eroded transport server-cycle deadline.
open_hypotheses:
  - NONE; the authorized W8, W6, and W1 live qualification sequence is exhausted, and no further live run is authorized.
latest_checkpoint: CP-019
next_experiment: NONE_TASK11_FINAL
```

## CP-016 — Configured execution timeout restored

```yaml
checkpoint_id: CP-016
last_valid_experiment: EXP-007R2
confirmed_conclusions:
  - EXP-008R5-W6 proved W6 memory-feasible but exposed a Task 10 runtime defect: execute_result used 180 s instead of configured executing_hard_timeout_s 240.0.
  - Operator readback reported RED failed 1 expected and GREEN passed 1, but their stdout was not durably captured; historical RED-before-GREEN ordering is therefore not independently verifiable. The retained adjacent runtime log passed 40. Commit 167c74a941782e37ed1369ee10c42ac6b77088a9 contains only the source fix and regression test.
next_command: Build a fresh candidate-equivalent overlay from commit 167c74a941782e37ed1369ee10c42ac6b77088a9, then launch fresh fixed-W6/C2/no-fallback EXP-008R6-W6 outside the Codex cgroup.
```

## EXP-008R6-W6 — Corrected fixed-W6 no-fallback C2 qualification

```yaml
experiment_id: EXP-008R6-W6
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-15T00:08:00+08:00
  - status: RUNNING
    at: 2026-09-15T00:11:37+08:00
  - status: INVALID
    at: 2026-09-15T00:17:04+08:00
prior_experiment: EXP-008R5-W6
hypothesis: With execute_result honoring the frozen 240 s configured timeout, W6 completes all twenty points under fixed C2 and no fallback.
single_variable: Replace the hard-coded 180 s runtime deadline with the configured 240 s deadline at commit 167c74a941782e37ed1369ee10c42ac6b77088a9; all Task 10 runtime variables remain frozen.
success_criteria: Exactly W6, 20/20 PASSED, no infrastructure fallback, YOLO only, zero TRUNCATED_FRAME, complete correctness/visual/timing evidence, and exact cleanup.
invalid_criteria: Failure to form READY, oomd kill, provenance/config drift, conflicting stack, missing evidence, or cleanup ambiguity.
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r6-w6-c2
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/86w6
source_commit: 167c74a941782e37ed1369ee10c42ac6b77088a9
runner_identity: so101-exp008r6-w6-runner.service invocation 6e6a6f5934624ed49d9ab0fee6214e31; tmux so101-exp008r6-w6/exp008r6-w6-runner; batch scope tmux-spawn-0de73214-febe-49b3-88fc-b292f99e5635.scope.
monitor_identity: so101-exp008r6-w6-monitor.service PID 770538 plus supplemental monitor PID 776248, both outside the runner scope.
observed: All six workers formed READY and twelve points sealed PASSED. The first bad terminal boundary was coordinator LEASE_EXPIRED seq1762 exactly 240.000 s after worker-02 entered EXECUTING for cup_test_forward_5cm; later authorization, port and dynamic errors followed revocation/stop. No oomd or TRUNCATED_FRAME occurred; scope MemoryPeak was 6684532736 bytes. Exit 1, elapsed 327.39634367008694 s, exact cleanup complete with claims 215-220 RELEASED.
conclusion: INVALID under the handoff's unable classification: the clean W6 stack remained memory-safe but could not complete the frozen point within the configured 240 s hard boundary. This authorizes fresh W1; no further source change is warranted.
decision: RETRY_FIXED_AT_W1
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

## EXP-003 — Full adaptive execute regression

```yaml
experiment_id: EXP-003
status: VALID
prior_experiment: EXP-002B
hypothesis: The qualified adaptive ladder can complete the full 20-point catalog without injected faults while preserving each point's initial-state and sealed-evidence contracts.
prediction: Every point passes, the final Worker level is one of W8, W6, W4, W2, or W1, all accepted attempts have fresh initial gates and complete evidence, terminal images agree with the batch result, and cleanup succeeds.
single_variable: Remove fault injection and increase initial-points-per-worker from 1 to 3 for the full execute regression.
lifecycle: ISOLATED_STACK
batch_id: e2001
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/e2001
provenance:
  source_commit: 62cd8e9424a47e25fe5a9e9729268294ee2a13b9
  package_source_commit: 3d35cb017caddcb7ffecc667f031fde25a162903
  install_prefix: /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool/install/so101_demo_py
  runtime_executable: /usr/bin/python3
  catalog_sha256: c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5
  broker_image_id: sha256:3b1a6661a87359729b848cb92807c0e45f618ae2dec0e20a1f534e51f6148a79
  broker_source_sha256: 286b5d9f4e994e897c1c01bb75c79d399dbbeaba573a7779424e4a498146a37e
  yolo_weights_sha256: f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781
  grounded_manifest_sha256: 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775
configuration:
  initial_worker_count: 8
  fallback_worker_counts: [6, 4, 2, 1]
  initial_points_per_worker: 3
  worker_start_timeout_s: 120
  max_infra_attempts_per_point: 5
  ros_domain_ids: [215, 216, 217, 218, 219, 220, 221, 222]
observed:
  - W8 passed readiness and imported eight PASSED first-wave points. A later active attempt became invalid or indeterminate, so the runner retained those terminal results, interrupted the other 12 points, and performed one W8-to-W6 recovery.
  - W6 passed readiness and committed all 12 unfinished points. The batch finished COMPLETED in 456.1064693250228 seconds with levels_used [8, 6], final_worker_count 6, and batch_cleanup_complete true.
  - The accepted load was one point on each W8 Worker and two points on each W6 Worker.
  - All 20 imported results were PASSED and had a valid POINT_INITIAL_GATE, a YOLO-first POSE_ACCEPTED receipt, DONE dynamic execution, empty final attached_object_ids, stable table support without fingertip contact, and a verified sealed hash tree. Grounded-SAM was not needed.
  - All 20 terminal RGB images were opened in a contact sheet. P01, P09, P18, P19, and P20 were also opened at original resolution. Each frame shows the cup upright inside the red target ring and the open gripper retreated clear of the cup.
  - The generated top-view state chart shows all P01 through P20 as successful and agrees with the aggregate result.
  - Both generation owned-process manifests are empty. The cleanup receipt released Domains 215 through 220, no broker container remained, and the wrapper exited 0.
visual_evidence:
  terminal_contact_sheet: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-11/e2001-terminal-rgb-contact-sheet.png
  terminal_contact_sheet_sha256: 55bdafb29999de2abb513b666a49a7ded61a766d2c1be1574666c8c6bc572434
  top_view_png: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-11/e2001-top-view/so101-position-top-view.png
  top_view_png_sha256: e2c2c3eceff87f952af4c41a9313b3f718fe1f01e44d1c17b2885ed14b5dba6b
conclusion: The adaptive execute path completed the full catalog with 20 PASSED results and exact cleanup. Its allowed recovery preserved the eight W8 terminal points and completed the remaining 12 at W6.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/e2001
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-11
decision: Accept EXP-003 and proceed to no-fallback performance samples for W1, W2, W4, W6, and W8.
next_experiment: EXP-004
```

## CP-003 — Full execute acceptance

```yaml
checkpoint_id: CP-003
last_valid_experiment: EXP-003
current_hypothesis: Each fixed Worker level can complete the same 20-point catalog without fallback and provide a comparable elapsed-time sample.
working_tree_status: clean at 62cd8e9424a47e25fe5a9e9729268294ee2a13b9 before this ledger update
source_commit: 62cd8e9424a47e25fe5a9e9729268294ee2a13b9
accepted_batches: [su09, mr08, e2001]
owned_processes: current Codex session only; e2001 generation manifests are empty and its task-owned tmux session exited
preserved_processes: pre-existing process groups 3835752, 3835753, 3882463, and 3882464; tmux sessions codex and codex-task-so101-adaptive-worker-pool
confirmed_conclusions:
  - startup and active-attempt fault injection both converge through exact W8-to-W6 fallback without touching sentinels.
  - the uninjected full execute regression passes all 20 points and all evidence-layer checks after one allowed W8-to-W6 recovery.
  - e2001 terminal images and the top-view state chart agree with the 20/20 aggregate result.
  - e2001 released its Domains, sockets, broker container, and manifest-owned processes.
retained_runs:
  - accepted: r/su09, r/mr08, and r/e2001
  - diagnostic_or_invalid: r/su01 through r/su08 and r/mr01 through r/mr07
archived_runs: []
deletion_candidates:
  - all scratch trees under scratch/r31 through scratch/r39 after their recorded readback
  - no candidate may be deleted without explicit user authorization
open_risks:
  - W1, W2, W4, W6, and W8 no-fallback performance samples have not yet been collected.
next_command: implement and dry-run check scripts/run_so101_adaptive_worker_scaling.zsh
```

## CP-004 — Scaling pause and standalone-inference handoff

```yaml
checkpoint_id: CP-004
last_valid_experiment: EXP-003
current_hypothesis: Independent production YOLO-Seg detector instances can expose a standalone GPU concurrency ceiling and an earlier useful saturation point without running ROS, MuJoCo, MoveIt, Gazebo, or physical execution.
working_tree_status: dirty at 48ade9ab132a327ae7ec58001f87323c786093e9; preserved pre-existing paths are src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT; this ledger is the task-owned change.
owned_processes: current Codex dispatch process only; host-level inspection found no so101-adaptive-scaling tmux session, no scaling driver, no ROS/MoveIt/MuJoCo/Gazebo runtime, and no Docker container.
preserved_processes: tmux sessions codex and codex-task-so101-adaptive-worker-pool; neither is touched.
confirmed_conclusions:
  - The final W1 batch wy101 reached 20 PASSED point results at one Worker in 1630.650472841924 s; its first top-level aggregate was INFRA_FAILED only at cleanup classification PROC_CLASSIFICATION_UNVERIFIABLE.
  - The exact owned cleanup rerun for wy101 succeeded, released ROS Domain 215, and left /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/wy101/p/g01w01/owned-processes.json with an empty processes list.
  - The timing report is retained at /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/reports/worker-scaling-wy101.time and the aggregate and cleanup receipt remain under r/wy101.
  - No successor scaling batch was created after wy101 and the so101-adaptive-scaling session is absent; W2 and the rest of the full-stack matrix remain paused.
disproven_routes:
  - Treating the initial wy101 top-level status as a clean performance acceptance is unsupported because cleanup was repaired only by a later exact rerun.
open_risks:
  - Frozen broker image, detector adapter, representative sealed RGB inputs, model hashes, CUDA identity, and baseline GPU process evidence must be recovered before the standalone benchmark starts.
  - Standalone model-instance concurrency does not establish production Broker concurrency because Broker.run_next() remains serialized.
next_command: recover frozen inference provenance and append EXP-004 as PLANNED before starting its isolated harness
```

## EXP-004 — Standalone YOLO-Seg inference concurrency ceiling

```yaml
experiment_id: EXP-004
status: INVALID
prior_experiment: EXP-003
hypothesis: Independent production YOLO-Seg detector instances in the immutable production broker image will remain output-equivalent and stable through a measurable concurrency ceiling, with a useful throughput saturation point at or below that ceiling.
prediction: Admitted levels 1, 2, 4, 6, 8, 12, and 16 complete three repetitions of at least 100 representative sealed-frame requests unless an invalid result, less than 4 GiB free VRAM, or two consecutive sub-5-percent throughput gains without p95 improvement stops higher levels.
single_variable: Number of independent YOLO-Seg model instances and concurrent request slots; image, image inputs, weights, adapter, post-processing, device, and singleton Grounded-SAM resident baseline remain frozen.
lifecycle: ISOLATED_STACK
preconditions:
  - The full-stack W1/W2/W4/W6/W8 matrix is paused after wy101 and no scaling session, Docker container, ROS, MoveIt, MuJoCo, Gazebo, or physical process is running.
  - Production image ID is sha256:c11369640bba27a5415c5467d9b8c5203aee77a6043cf202b2506ea86016758b with source SHA256 674f42465eb726329a3c179079fd1b330d4055fdaf0b424d584386d9a5c338f4.
  - YOLO weights are the read-only best.pt with SHA256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781; Grounded-SAM manifest SHA256 is 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775.
  - Inputs are one immutable sealed rgb.npy per point from accepted 20-point batch e2001, selected deterministically by point ID and hashed before use.
success_criteria:
  - Every admitted level executes at least 100 measured requests in each of three repetitions after representative warmup, with zero errors, timeouts, crashes, OOMs, missing results, or NaNs.
  - Model ID, weights hash, candidate count, class, confidence, bbox, and mask semantics match the concurrency-1 reference within the recorded comparison contract.
  - Raw latency, throughput, GPU, VRAM, power, CPU, RAM, model-load, command, exit, and result-hash evidence is retained with a machine-readable summary.
failure_criteria:
  - Any output mismatch, CUDA error, OOM, process crash, timeout, NaN, missing result, or fewer than the contracted request count makes that level invalid and stops higher levels.
  - Less than 4 GiB free VRAM or two consecutive concurrency increases below 5 percent throughput improvement while p95 does not improve stops higher levels without relabeling prior valid levels.
invalid_criteria:
  - Image, package source, model, input hash, device, process baseline, or output evidence differs from frozen provenance.
  - Any ROS, MoveIt, MuJoCo, Gazebo, or physical execution starts during the benchmark.
provenance:
  source_commit: 48ade9ab132a327ae7ec58001f87323c786093e9
  install_overlay: immutable Docker image sha256:c11369640bba27a5415c5467d9b8c5203aee77a6043cf202b2506ea86016758b
  runtime_executable: /opt/venv/bin/python inside the immutable production broker image
  ros_domain_id: 0
  gz_partition: inference-only-none
commands:
  - command: zsh /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-13-inference-concurrency/exp004-standalone-yolo-ceiling/run_benchmark.zsh
    exit_code: 1
observed:
  - Host baseline before launch is AI-STATION-001 with NVIDIA GeForce RTX 5080, driver 595.84, 16303 MiB total, 537 MiB used, 15272 MiB free, zero reported compute applications, and no active production container.
  - The only host tmux sessions are codex and codex-task-so101-adaptive-worker-pool; no so101-adaptive-scaling session exists.
  - Frozen image, source, model, input, resource, and forbidden-process checks are enforced by the isolated harness before measurements are accepted.
  - Level 1 executed 360 requests with zero inference or equivalence errors, but the resource sampler failed before its first valid row because one /proc/self/status field had an empty value and the parser indexed that empty token list.
  - The level was correctly marked INVALID and no higher level started. The exact owned container exited and no GPU compute process remained.
inferred:
  - The observed level-1 latency and throughput are diagnostic only because the mandatory fine-grained resource record is absent.
conclusion: INVALID_HARNESS_RESOURCE_SAMPLER; no concurrency result from this attempt is accepted.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-13-inference-concurrency/exp004-standalone-yolo-ceiling
decision: REPEAT
next_experiment: EXP-005
```

## CP-005 — EXP-004 invalid harness isolation

```yaml
checkpoint_id: CP-005
last_valid_experiment: EXP-003
current_hypothesis: The production inference path remains benchmarkable after correcting only the empty /proc status-field parser and invalid-level summarizer; no model, input, concurrency, or acceptance variable changes.
working_tree_status: dirty at 48ade9ab132a327ae7ec58001f87323c786093e9; preserved pre-existing paths remain src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT; ledger changes are task-owned.
owned_processes: current Codex dispatch process only; EXP-004 container exited and host nvidia-smi reports no compute application.
preserved_processes: tmux sessions codex and codex-task-so101-adaptive-worker-pool; no scaling or SO-101 stack process was touched.
confirmed_conclusions:
  - EXP-004 is INVALID solely because mandatory resource sampling failed; all 360 diagnostic level-1 inferences were output-equivalent and are retained but excluded.
  - The first retry must write to a new directory and retain the original scripts, logs, summaries, and zero-row resource failure unchanged.
disproven_routes:
  - Accepting point-in-time GPU checkpoints as a substitute for the required fine-grained peak sampler is prohibited.
open_risks:
  - Corrected 100 ms resource sampling and invalid-summary handling require a fresh isolated run before any level can count.
next_command: create the non-overwriting EXP-005 harness copy with the two parser fixes, validate syntax, then mark RUNNING and execute
```

## EXP-005 — Standalone YOLO-Seg inference concurrency ceiling retry

```yaml
experiment_id: EXP-005
status: VALID
prior_experiment: EXP-004
hypothesis: With only the resource-sample parser and invalid-summary robustness corrected, the unchanged isolated production-adapter sweep will produce valid fine-grained metrics and expose the standalone ceiling and saturation point.
prediction: The same frozen levels, three repetitions, 120-or-more requests, output equivalence, singleton Grounded-SAM resident baseline, and stop policy complete with nonempty 100 ms resource samples per admitted level.
single_variable: Harness evidence parsing only; model image, production adapter/post-processing, weights, sealed inputs, CUDA device, concurrency levels, request counts, and stop thresholds are unchanged from EXP-004.
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-004 evidence remains unchanged and excluded.
  - No Docker container, GPU compute process, scaling session, ROS, MoveIt, MuJoCo, Gazebo, or physical process is active.
success_criteria:
  - Every admitted level is output-equivalent, has zero errors, contains three repetitions of at least 100 requests, and retains fine-grained GPU/CPU/RAM samples.
  - The sweep applies the 4 GiB headroom and two-consecutive-sub-5-percent-gain stop rules and emits standalone_max_stable, standalone_saturation_point, and recommended_initial_broker_parallelism separately.
failure_criteria:
  - Any model/output/CUDA/process/resource contract failure invalidates the level and stops higher levels.
invalid_criteria:
  - Any frozen provenance drift, missing resource samples, forbidden stack process, or overwritten EXP-004 artifact invalidates the retry.
provenance:
  source_commit: 48ade9ab132a327ae7ec58001f87323c786093e9
  install_overlay: immutable Docker image sha256:c11369640bba27a5415c5467d9b8c5203aee77a6043cf202b2506ea86016758b
  runtime_executable: /opt/venv/bin/python inside the immutable production broker image
  ros_domain_id: 0
  gz_partition: inference-only-none
commands:
  - command: zsh /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-13-inference-concurrency/exp005-standalone-yolo-ceiling-r2/run_benchmark.zsh
    exit_code: 0
observed:
  - The retry directory is new and EXP-004 remains retained unchanged. Syntax checks pass for both Python programs and the zsh driver.
  - The only active variable is the evidence parser correction: empty /proc status values map to zero, and final aggregation tolerates absent resource fields on invalid attempts.
  - Concurrency levels 1, 2, 4, 6, and 8 each completed three repetitions and 360 measured requests. All 1800 requests succeeded with no errors, NaNs, timeouts, crashes, OOMs, missing results, or output mismatches.
  - Median throughput in requests/s was C1 159.16951733856035, C2 219.42433400614138, C4 240.49865857664452, C6 229.08657927125662, and C8 210.5941610999844.
  - Aggregate p95 latency in milliseconds was C1 6.45629065, C2 9.133219200000001, C4 17.5460698, C6 27.34478475, and C8 49.608332850000004.
  - C4 to C6 throughput changed by -4.745173787217183 percent and C6 to C8 by -8.072239862369123 percent while p95 worsened at both increases. The frozen saturation rule stopped levels 12 and 16 and selected C4 as the useful saturation point.
  - Peak observed GPU memory was 3383 MiB, minimum free memory was 12426 MiB, peak utilization was 43 percent, and peak power was 95.57 W. Every admitted level remained above the 4 GiB headroom gate.
  - The singleton Grounded-SAM resident increment was 2611 MiB and it handled zero measured requests. At C8, independent YOLO replicas added 64 MiB at the resident checkpoint and runtime workspace/input growth added another 168 MiB at peak.
  - Resource sampling retained 58 through 64 samples per level at an approximately 122 to 124 ms median interval, plus raw process CPU and RAM evidence.
  - After completion, no task container, GPU compute application, forbidden full-stack process, or scaling session remained. The full-stack matrix was not resumed.
inferred:
  - C2 is the conservative production starting point: it improves median throughput by 37.855751324178776 percent over C1, while C4 adds only 9.604369846196414 percent over C2 and nearly doubles p95 latency from 9.133219200000001 to 17.5460698 ms.
  - This isolated result does not establish the production Broker limit because the current PerceptionService.run_next() path is serialized.
conclusion: The highest stable admitted standalone concurrency is 8, the useful saturation point is 4, and recommended initial production Broker parallelism is 2.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-13-inference-concurrency/exp005-standalone-yolo-ceiling-r2
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-13-inference-concurrency/exp005-standalone-yolo-ceiling-r2/summary.json; file SHA256 7f53d99f17dcfc1890bbf14bc5cf4c195afe91d2c47e79dde796a2f146b10449; internal summary SHA256 bfa9a09dc39eda366b5bcfdd558e2891a0327d53754c8322635515b74538640a.
decision: KEEP
next_experiment: NONE
```

## CP-006 — Standalone inference concurrency acceptance

```yaml
checkpoint_id: CP-006
last_valid_experiment: EXP-005
current_hypothesis: A production Broker implementation with two independent YOLO detector slots should capture most useful standalone throughput while limiting p95 growth; this requires a separate production Broker RED/GREEN and runtime experiment.
working_tree_status: dirty at 48ade9ab132a327ae7ec58001f87323c786093e9; preserved pre-existing paths are src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT; this ledger is the only task-owned source-tree change.
owned_processes: NONE; every EXP-005 container exited, docker-after.txt is empty, and host nvidia-smi reports no compute application.
preserved_processes: tmux sessions codex and codex-task-so101-adaptive-worker-pool remain; no unrelated process or session was stopped.
confirmed_conclusions:
  - EXP-005 is VALID at standalone concurrency 1, 2, 4, 6, and 8 with 1800 of 1800 output-equivalent measured requests and zero errors.
  - standalone_max_stable is 8, defined as the highest level admitted and tested before the frozen saturation stop; levels 12 and 16 are untested, not proven unstable.
  - standalone_saturation_point is 4 because it produced the highest median throughput, and both later increases reduced throughput while worsening p95.
  - recommended_initial_broker_parallelism is 2 because it gains 37.855751324178776 percent over C1, whereas C4 gains only 9.604369846196414 percent over C2 with much higher p95.
  - Peak GPU memory was 3383 MiB, leaving at least 12426 MiB free; the singleton Grounded-SAM resident contribution was 2611 MiB and was not replicated or invoked.
disproven_routes:
  - Increasing standalone concurrency beyond 4 improves throughput on this workload; C6 and C8 both reduced it.
  - EXP-004 diagnostic measurements are acceptable without resource samples; EXP-004 remains INVALID.
open_risks:
  - Current production Broker.run_next() remains serialized, so no production concurrency limit or safety claim follows from this standalone harness.
  - Concurrency 12 and 16 were intentionally not tested after the required saturation stop and must not be described as unstable.
next_command: add a separate production Broker experiment with independent per-slot detector ownership at initial parallelism 2; do not resume the full-stack scaling matrix without a new user instruction
retained_runs:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-13-inference-concurrency/exp005-standalone-yolo-ceiling-r2
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-13-inference-concurrency/exp004-standalone-yolo-ceiling as INVALID diagnostic evidence
  - all prior registered-root evidence including r/wy101 and its cleanup receipt
archived_runs: []
deletion_candidates:
  - NONE from EXP-004 or EXP-005; no evidence was deleted or archived
  - previously recorded scratch deletion candidates remain unchanged and require explicit user authorization
```

## EXP-006 — No-fallback W8 `/cup_pose` critical-path diagnostic

```yaml
experiment_id: EXP-006
status: VALID
prior_experiment: EXP-005
hypothesis: Under exactly eight admitted execute Workers, delay before the serialized production Broker accepts each infer RPC dominates the consumer READY-to-POSE_ACCEPTED interval and causes the first expected-budget violation; GPU execution itself remains below its inference budget.
prediction: Client-side Broker round-trip wait will grow with concurrent W8 demand while the Broker's internal queued-to-started duration and YOLO started-to-completed duration remain within their configured 10 s and 20 s budgets; per-attempt tracing will distinguish this from RGB/RGB-D capture, pause/resume, localization/admission, and DDS delivery.
single_variable: Enable measurement-only per-process monotonic tracing and frequent host/GPU resource sampling during one W8 execute run; worker count is fixed at 8 and fallback is disabled, with production timeouts, scheduling, models, pause semantics, retry policy, catalog, geometry, and motion unchanged.
lifecycle: ISOLATED_STACK
preconditions:
  - CP-006 and EXP-005 are recovered; accepted standalone saturation remains C4 and production Broker execution remains serialized.
  - The authoritative worktree is 48ade9ab132a327ae7ec58001f87323c786093e9 with preserved dirty src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT plus this task-owned ledger.
  - No conflicting SO-101, MoveIt, MuJoCo, Gazebo, scaling, Docker, GPU-compute, or ROS Domain 0 runtime is active before launch.
  - Diagnostic output is new and non-overwriting under /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline; batch runtime identity is w8d1.
success_criteria:
  - Exactly eight Workers are initially admitted and no W6/W4/W2/W1 fallback generation starts.
  - Every W8 attempt has a host-monotonic timeline from consumer spawn/READY/get_one deadline through POSE_ACCEPTED or exact termination, including all stages required by the dispatch.
  - Broker response timestamps, model identity, resource samples, clock-namespace validation, provenance, command/exit code, point outcomes, and exact cleanup are retained and machine-readable.
failure_criteria:
  - A valid failed attempt is accepted as diagnostic evidence only when its first bad boundary and all preceding required timing fields are present.
  - Any W8 infrastructure failure terminates the no-fallback ladder rather than launching a lower Worker count.
invalid_criteria:
  - Missing stage/resource evidence, clock incomparability, provenance drift, conflicting runtime processes, fallback admission, overwritten prior evidence, or incomplete cleanup makes this experiment INVALID.
provenance:
  source_commit: 48ade9ab132a327ae7ec58001f87323c786093e9
  install_overlay: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline/candidate-src/install; clean detached candidate rebuild, package source tree e4a42261b20639d52046f749fd5a5f8b1e284aa31f521d12a1c2fb0a0f636fbe
  runtime_executable: /usr/bin/python3 plus immutable production Broker image sha256:c11369640bba27a5415c5467d9b8c5203aee77a6043cf202b2506ea86016758b
  ros_domain_id: [215, 216, 217, 218, 219, 220, 221, 222]
  gz_partition: not_applicable
commands:
  - command: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline/run_w8_diagnostic_live1.zsh
    exit_code: 0
observed:
  - Preflight dry-run pf061 recorded clean commit 48ade9ab132a327ae7ec58001f87323c786093e9, all 20 catalog points, worker_count 8, fallback_worker_counts [], immutable Broker image sha256:c11369640bba27a5415c5467d9b8c5203aee77a6043cf202b2506ea86016758b, and levels_used [8].
  - Immediately before live launch, no task runtime, Docker container, GPU compute process, or conflicting ROS stack remained; host and Broker-container monotonic and boottime namespace offsets were both zero.
  - The first wrapper invocation exited 1 before creating any runtime, Worker, ROS, Docker, or GPU state because candidate package metadata was absent from PYTHONPATH. It remains preserved as a pre-launch harness diagnostic and is not an experiment run.
  - The corrected single real execute run admitted eight Workers, used only level 8, started no fallback generation, completed in 362.4538940861821 s, and reported all 20 catalog points PASSED with zero infrastructure retries.
  - All 20 attempts contain all 17 required timing segments. READY-to-POSE_ACCEPTED was min 0.565010 s, median 2.283755 s, p95 6.869651 s, and max 7.921919 s.
  - The dominant composite stage was the perception chain at min 0.278100 s, median 1.507415 s, p95 4.322592 s, and max 5.862980 s. The dominant measured segment within it was Broker client round trip at min 0.218828 s, median 1.432061 s, p95 3.663370 s, and max 3.995127 s; its per-attempt share of READY-to-POSE_ACCEPTED was min 23.816%, median 44.501%, p95 81.032%, and max 85.999%.
  - Inside the Broker round trip, hidden transport pre-accept was median 0.090826 s and p95 1.037377 s, internal queue wait was median 0.511249 s and p95 1.403534 s, YOLO execution was median 0.297820 s and p95 0.738712 s, and completed-response delivery was median 0.508258 s and p95 1.424287 s. Observed internal queue depth and model execution concurrency were both 1; client RPC pending depth reached 2.
  - All 20 accepted results used plastic-cup-yolo11n-seg-v1 and were QUALIFIED. Grounded-SAM had zero requests and no fallback transition.
  - sample_13_far_center first called at monotonic 1208842.292283 s, entered the Broker queue at 1208842.484512 s, and received TRUNCATED_FRAME at 1208842.711849 s after 0.419566 s. The identical retry began 0.000187 s later; the original model result completed at 1208844.760345 s and the retry received QUALIFIED at 1208846.287411 s.
  - sample_15_far_center first called at monotonic 1208852.387603 s, entered the Broker queue at 1208852.596306 s, completed model execution at 1208854.676872 s, and received TRUNCATED_FRAME at 1208855.419363 s after 3.031760 s. The identical retry began 0.000107 s later and received QUALIFIED after 0.519415 s.
  - The runtime Broker server cycle deadline was 5 s while the Worker client deadline was 240 s. Both queued timestamps precede retry start, both retries reuse the same request/idempotency identity, and neither caused a second logical outcome, Broker generation change, or point failure.
  - No stage crossed its configured budget: consumer readiness max 3.700331 s <= 20 s, RGB capture max 1.645617 s and inference snapshot max 1.058163 s <= 15 s, internal Broker queue max 1.535714 s <= 10 s, YOLO max 0.740119 s <= 20 s, exact-TF localization max 0.083206 s <= 5 s, and get_one max 8.040159 s <= 240 s. Therefore no first bad boundary was observed.
  - The user-requested 5 s target is separate from the configured 240 s get_one timeout. Recomputing the raw monotonic ranges found 5/20 strict target exceedances from get_one start to POSE_ACCEPTED: sample_08_mid_right 5.885912 s, sample_09_mid_left 5.642495 s, sample_11_mid_right 6.814980 s, sample_14_far_right 8.040159 s, and sample_15_far_center 6.134845 s.
  - Recomputing consumer READY to accepted found 4/20 strict 5 s target exceedances: sample_08_mid_right 5.872835 s, sample_11_mid_right 6.814269 s, sample_14_far_right 7.921919 s, and sample_15_far_center 6.131215 s. sample_09_mid_left was 2.601030 s on this view and is the sole set difference.
  - One attempt, sample_07_mid_center-lease-1, rejected 20 retransmissions while its ROS clock was zero; every rejected sample recorded source stamp 6929999999 ns, age -6.929999999 s, future skew 6.929999999 s, and reason CUP_POSE_STALE: source stamp is too far in the future. It accepted a later retransmission and passed.
  - Resource sampling retained 1281 host samples at 0.274908 s median spacing and 161 GPU samples. GPU utilization was 3% median, 21% p95, and 24% max; GPU memory was 4893 MiB median and 4933 MiB max with at least 10876 MiB free; power was 36.74 W median, 58.45 W p95, and 74.17 W max. This excludes GPU capacity saturation as the W8 limiter.
  - Mean host load inside each attempt's critical interval had descriptive Pearson r=0.7419 with READY-to-POSE_ACCEPTED duration, but CPU pressure had r=-0.0556 and GPU utilization r=0.0989. Overlapping attempts share system samples, so these coefficients are correlation evidence, not causal attribution.
  - Cleanup gates, container cleanup, process cleanup, goal cancellation, recovery, and coordinator completion all succeeded. Domains 215 through 222 were released; the post-cleanup process, Docker, GPU-compute, and ROS-domain probe found no task-owned residual.
inferred:
  - Production Broker serialization is observable, but W8 demand in this run reached only two pending client RPCs and one active/queued model interval at a time; the successful run does not reproduce a timeout or an eight-request inference burst.
  - Host scheduling may amplify long intervals, as suggested by load correlation, but the evidence does not make it the root cause; GPU capacity, YOLO compute, hidden pre-accept transport, pause/resume, localization, and DDS delivery are not dominant in this sample.
  - The two TRUNCATED_FRAME errors were caused by AuthenticatedUnixServer.serve_once starting its 5 s deadline before blocking accept, leaving approximately 0.419566 s for sample_13 and 3.031760 s for sample_15 at client-call start. When the shared remainder expired, the server emitted no reply and client receive_frame mapped EOF to TRUNCATED_FRAME. This is transport/server-deadline erosion, not the Broker queued-to-started interval.
  - `_WorkerBrokerProxy._call()` retried the same message, while `_CoordinatorBackedBrokerAuthority.dispatch()` retained the original mutation/result by idempotency key. The retries therefore recovered the original QUALIFIED results; an isolated accept-idle A/B reproduced TRUNCATED_FRAME versus direct success with handler behavior held fixed.
  - Passing the current 240 s timeout contract and missing the separate 5 s target are simultaneous, non-conflicting results: no configured timeout occurred, but W8 has a measured 25% get_one-view and 20% READY-view tail-latency SLO miss rate in this sample.
conclusion: EXP-006 is VALID. The dominant `/cup_pose` critical-path component is the serialized Broker round trip inside the broader perception chain, with roughly equal median internal queue wait and post-inference delivery contributions; no configured stage violated its budget and no first bad boundary occurred under the current configuration. Separately, the W8 tail-latency conclusion is 5/20 over the user-targeted 5 s from get_one start and 4/20 over 5 s from consumer READY.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline/live-01/aggregate-timing.json
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline/live-01/per-attempt-timeline.json
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline/live-01/resource-correlation.json
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline/broker-truncated-frame-analysis.json
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline/truncated-frame-causal-repro-r3.json
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline/tail-latency-5s-analysis.json; SHA256 94fd3697e38865a4dbf5bf44e41488899015affd04f9442f609d74b54ca6f848
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/w8d1
decision: KEEP; apply no performance fix in this diagnostic dispatch.
next_experiment: NONE
```

## CP-007 — Fixed-W8 `/cup_pose` diagnostic acceptance

```yaml
checkpoint_id: CP-007
last_valid_experiment: EXP-006
current_hypothesis: NONE; the requested measurement concludes that Broker round trip dominates this successful fixed-W8 sample, but no timeout boundary was reproduced.
working_tree_status: dirty at 48ade9ab132a327ae7ec58001f87323c786093e9; preserved pre-existing paths remain src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT; the ledger is the only task-owned source-tree change.
owned_processes: NONE; exact cleanup completed and post-cleanup probes found no task process, container, GPU compute application, or ROS nodes on domains 215 through 222.
preserved_processes: unrelated tmux sessions and all pre-existing user changes remain untouched.
confirmed_conclusions:
  - EXP-006 is VALID: fixed W8, no fallback, 20 of 20 points PASSED, all mandatory timestamps complete, command exit 0, and exact cleanup complete.
  - The composite perception chain dominates at 1.507415 s median; within it, Broker client round trip dominates measured segments at 1.432061 s median and 44.501% median of READY-to-POSE_ACCEPTED.
  - Every expected budget passed, so EXP-006 has no failed attempt and no first bad boundary.
  - GPU headroom remained large and utilization low; host load correlates descriptively with longer critical intervals, but does not displace the Broker timing result or establish causality.
disproven_routes:
  - Hidden pre-accept transport dominates the interval; its median was 0.090826 s.
  - YOLO execution, pause/resume, exact-TF localization, pose admission, or DDS callback delivery is the first budget violation; none violated a budget.
open_risks:
  - Two automatically recovered TRUNCATED_FRAME responses and the one zero-clock retransmission episode remain observed reliability details, not failed boundaries in this run.
  - One successful 20-point sample does not prove the absence of intermittent timeout behavior in all W8 runs.
next_command: NONE; no performance fix or follow-up experiment is authorized by this diagnostic dispatch.
retained_runs:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/w8d1
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/pf061
  - all earlier evidence under /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01
archived_runs: []
deletion_candidates:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/scratch/exp006-red-*/tmp
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/scratch/exp006-green-*/tmp
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/scratch/exp006-final-verify-01/tmp
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline/candidate-src
  - none deleted; removal requires explicit user authorization
```

## CP-008 — `TRUNCATED_FRAME` causal attribution

```yaml
checkpoint_id: CP-008
last_valid_experiment: EXP-006
current_hypothesis: NONE; the two live TRUNCATED_FRAME sequences match the accept-eroded AuthenticatedUnixServer deadline mechanism, and the same mechanism passed an isolated single-variable A/B.
working_tree_status: dirty at 48ade9ab132a327ae7ec58001f87323c786093e9; preserved pre-existing paths remain src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT; the ledger is the only task-owned source-tree change.
owned_processes: NONE; the causal A/B used only local Unix sockets and retired both server threads.
preserved_processes: unrelated tmux sessions and all pre-existing user changes remain untouched.
confirmed_conclusions:
  - OBSERVED: sample_13_far_center received TRUNCATED_FRAME 0.419566 s after first call; its Broker queue timestamp preceded retry, its model completed after the first connection closed, and its identical retry returned the original QUALIFIED result.
  - OBSERVED: sample_15_far_center received TRUNCATED_FRAME 3.031760 s after first call; its Broker queue and model-completion timestamps both preceded the first connection close, and its identical retry returned the original QUALIFIED result in 0.519415 s.
  - OBSERVED: runtime request_deadline_s was 5 s, Worker client deadline was 240 s, both requests retained the same request/idempotency identity, Broker generation remained 1, and both points passed.
  - INFERRED: AuthenticatedUnixServer.serve_once consumed approximately 4.580434 s and 1.968240 s in its pre-request accept phase, respectively. Exhausting the shared receive/handler/reply remainder closed each connection without a reply, which receive_frame surfaced as TRUNCATED_FRAME.
  - INFERRED: the authority's idempotency lock/cache made each retry a replay of the original mutation/result rather than a second logical inference.
  - CONFIRMED MECHANISM: with handler duration fixed at 0.1 s and server deadline fixed at 0.5 s, adding 0.45 s accept idle reproduced TRUNCATED_FRAME and successful same-message replay with one handler call; zero accept idle succeeded directly.
disproven_routes:
  - These two errors are client-side 240 s receive timeouts; each occurred in less than 3.032 s.
  - These two errors are ordinary application Broker queue timeouts; neither crossed the 10 s queue deadline, and the connection loss is explained at the transport server-cycle boundary.
open_risks:
  - The live instrumentation does not distinguish the final serve_once sub-branch for sample_15 (handler wait expiry versus the immediately following no-reply check), though both branches share the same accept-eroded cycle deadline.
  - The production deadline behavior remains unchanged because this dispatch authorizes attribution only, not a fix.
next_command: NONE; a production fix requires a separate explicitly authorized RED/GREEN change.
retained_runs:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/w8d1
  - all earlier evidence under /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01
archived_runs: []
deletion_candidates:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline/truncated-frame-causal-repro/accept-idle-eroded; invalid sandbox-denied setup, retained
  - previously recorded scratch and candidate-src deletion candidates remain unchanged
  - none deleted; removal requires explicit user authorization
```

## CP-009 — Current timeout versus 5 s W8 tail latency

```yaml
checkpoint_id: CP-009
last_valid_experiment: EXP-006
current_hypothesis: NONE; raw monotonic timestamp reduction confirms both requested 5 s views.
working_tree_status: dirty at 48ade9ab132a327ae7ec58001f87323c786093e9; preserved pre-existing paths remain src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT; the ledger is the only task-owned source-tree change.
owned_processes: NONE; this supplemental calculation used retained reduction artifacts and started no runtime process or stack.
preserved_processes: all pre-existing user changes and unrelated state remain untouched.
confirmed_conclusions:
  - OBSERVED: the EXP-006 runtime config sets executing_hard_timeout_s to 240.0, which the Worker passes to the dynamic consumer as pose_receive_timeout_s; get_one reached at most 8.040159 s, so 0/20 crossed the configured timeout.
  - OBSERVED: strict comparison to the separate 5.0 s target found 5/20 get_one-start-to-POSE_ACCEPTED exceedances: sample_08_mid_right, sample_09_mid_left, sample_11_mid_right, sample_14_far_right, and sample_15_far_center.
  - OBSERVED: strict comparison to the same target from consumer READY found 4/20 exceedances: sample_08_mid_right, sample_11_mid_right, sample_14_far_right, and sample_15_far_center; sample_09_mid_left measured 2.601030 s and is excluded.
  - OBSERVED: direct subtraction of the raw monotonic-nanosecond ranges reproduced both existing reduced metrics with zero-nanosecond difference across all 20 attempts.
  - CONCLUSION: EXP-006 has no current-configuration consumer timeout, but its W8 tail-latency result misses the user-targeted 5 s SLO at 25% by the get_one-start view and 20% by the READY view.
open_risks:
  - The 5 s target is an evaluation SLO, not an enforced runtime timeout in EXP-006; this checkpoint changes no configuration or production behavior.
next_command: NONE; no performance fix or configuration change is authorized by this supplemental accounting request.
retained_runs:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-14-w8-cup-pose-bottleneck/exp006-w8-cup-pose-timeline
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/w8d1
  - all earlier evidence under /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01
archived_runs: []
deletion_candidates:
  - all previously recorded scratch, candidate-src, and invalid causal-reproduction candidates remain unchanged
  - none deleted; removal requires explicit user authorization
```

## CP-010 — Broker concurrency implementation baseline

```yaml
checkpoint_id: CP-010
last_valid_experiment: EXP-006
current_hypothesis: Resetting the request deadline after accept, allowing eight bounded Broker connections, and executing YOLO through two independent detector instances will eliminate transport truncation and reduce W8 tail latency while preserving at-most-once replay and all physical acceptance gates.
working_tree_status: dirty at 48ade9ab132a327ae7ec58001f87323c786093e9; task-owned ledger plus preserved pre-existing src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT.
owned_processes: NONE; no Task 15 runtime has started.
preserved_processes: NONE observed; unrelated future processes remain out of scope.
confirmed_conclusions:
  - EXP-006 and its A/B confirm the accept-idle request-deadline defect; the current 5 s server cycle begins before blocking accept and may close without a reply.
  - EXP-005 selects C2 as the conservative initial production inference parallelism; C4 remains conditional on a 20/20 C2 run whose READY-to-POSE_ACCEPTED p95 is still at least 5 s.
  - Current consumer get_one hard timeout remains 240 s, while 5 s remains a reporting SLO rather than a hard timeout.
  - The current checkout is a linked worktree on codex/parallel-adaptive-worker-pool at 48ade9ab132a327ae7ec58001f87323c786093e9; submodule c16b5a5fe880b6e1857f56486dab4ae726576969 is unchanged.
  - Elevated read-only preflight found no matching SO-101 stack process, no ROS nodes on Domains 0 or 215 through 222, no Docker container, no GPU compute application, and no tmux session.
disproven_routes:
  - Increasing YOLO directly to C4 before the C2 W8 result is not authorized by the selected single-variable sequence.
  - Turning the 5 s performance objective into a hard timeout is outside the approved design.
open_risks:
  - The concurrency spec and plan paths named inside the plan do not exist in the checkout; the dispatch-designated design.md and implementation-plan.md under the Task 15 evidence handoff are authoritative and fully read.
  - Production build, image, eight-client microbenchmark, fixed-W8 correctness, tail latency, adaptive fallback, and visual acceptance remain unverified.
next_command: Add the Task 2 deterministic accept-idle and handler-timeout tests, then run the focused RED with a fresh verified NVMe scratch.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/preflight.md
retained_runs:
  - all existing evidence under /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01
archived_runs: []
deletion_candidates:
  - all previously recorded candidates remain retained; none deleted
```

## EXP-007 — Eight-client production Broker C2 microbenchmark

```yaml
experiment_id: EXP-007
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-14T22:49:31+08:00
  - status: RUNNING
    at: 2026-09-14T22:51:20+08:00
  - status: INVALID
    at: 2026-09-14T22:53:53+08:00
prior_experiment: EXP-006
hypothesis: The committed production Broker with eight bounded authenticated connection handlers, queue capacity eight, and two independent YOLO executors will overlap eight simultaneous requests without transport truncation or duplicate logical inference.
single_variable: Exercise the new production Broker concurrency path at C2; model bytes, image, thresholds, production-sized RGB input, queue capacity, request identity rules, and deadline policy remain frozen.
lifecycle: ISOLATED_STACK
preconditions:
  - Source commit is 3677e9d97f1367f861496817cee5edeb4349871f and the rebuilt overlay resolves so101_demo_py from /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool.
  - Immutable image is sha256:11e9a5ec0a7dedae8e0794d97462e422e78e68157ec94c75f8294b8a2025a7b1 with source and verified source SHA256 148f22e6e1ba6aaf7b99d0fe97d42d141cacd77f8f1928dda8233f0459006006.
  - Frozen YOLO and Grounded-SAM CUDA smoke returned QUALIFIED and post-smoke Docker/GPU probes were empty.
  - Runtime root /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/e007 and EXP-007 output paths do not exist before launch.
method:
  - Start one production Broker container with connection_handler_count=8, queue_capacity_per_model=8, yolo_executor_count=2, grounded_sam_executor_count=1, and request_deadline_s=75.
  - Use eight distinct Worker tokens, bound leases, inference identities, and canonical authenticated RPC messages.
  - Use one identical production-sized 640x480 uint8 RGB source image encoded into eight immutable request paths.
  - Synchronize the eight client threads and the main thread with threading.Barrier(9), then wait for all replies and exact shutdown.
success_criteria:
  - pending_rpc_peak is 8 and queue_depth_peak is greater than 1.
  - YOLO model_active_peak is exactly 2, all eight replies are QUALIFIED, and all clients terminate.
  - logical_inference_count is 8 with every idempotency key represented once; replay_count is zero.
  - transport_errors contains no TRUNCATED_FRAME and no client reports TRUNCATED_FRAME.
  - Broker container, authority server, socket, owned process, and GPU compute cleanup are exact.
failure_criteria:
  - Any wrong outcome, missing reply, duplicate logical inference, model peak other than 2, transport error, or cleanup failure is a valid failed experiment.
invalid_criteria:
  - Barrier synchronization does not form, source/image/model identity drifts, evidence is incomplete or overwritten, runtime root pre-exists, or cleanup cannot be proven.
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp007-eight-client-c2
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/e007
retention_rule: Retain the report, command log, Broker log, runtime root, provenance, and cleanup evidence; delete nothing without explicit user authorization.
observed:
  - The threading.Barrier(9) synchronization formed and Broker pending_rpc_peak reached 8 with eight authenticated connection owners and zero transport errors.
  - All eight requests were rejected before submission with START_EVENT_NOT_AUTHORIZED, so queue_depth_peak was 0, model_active_peak was empty, and there were zero inference replies.
  - The harness keyed its authorization cache by outer RPC request_id while authorize_inference correctly supplied the nested InferenceRequest.request_id. This is a harness identity mismatch, not a product rejection or concurrency measurement.
  - SIGINT shutdown emitted the bounded Broker summary; authority and perception sockets were removed, the labeled container exited, and Docker/GPU post-probes were empty.
conclusion: INVALID; barrier and pending-RPC evidence are real, but no request reached the model queue, so EXP-007 cannot qualify C2 concurrency.
decision: REPEAT_WITH_CORRECT_NESTED_REQUEST_ID
```

## EXP-007R2 — Corrected eight-client production Broker C2 microbenchmark

```yaml
experiment_id: EXP-007R2
status: VALID
status_history:
  - status: PLANNED
    at: 2026-09-14T22:53:53+08:00
  - status: RUNNING
    at: 2026-09-14T22:54:27+08:00
  - status: VALID
    at: 2026-09-14T22:55:36+08:00
prior_experiment: EXP-007
hypothesis: Correctly binding authority to the nested InferenceRequest.request_id will allow the otherwise unchanged eight authenticated requests to reach the C2 production queue and satisfy the preregistered concurrency criteria.
single_variable: Correct only the harness authorization-cache key from outer RPC request_id to nested inference request_id; retain commit, image, models, input, C2, queue eight, deadlines, Barrier(9), and cleanup method.
lifecycle: ISOLATED_STACK
success_criteria:
  - pending_rpc_peak is 8, queue_depth_peak is greater than 1, and YOLO model_active_peak is exactly 2.
  - Eight distinct authenticated requests return QUALIFIED with candidates; logical_inference_count is 8, replay_count is 0, and TRUNCATED_FRAME is absent.
  - All clients, Broker container, authority thread, sockets, and GPU compute state clean up exactly.
invalid_criteria:
  - The corrected identity is not exercised, barrier synchronization does not form, provenance drifts, output pre-exists, or cleanup evidence is incomplete.
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp007r2-eight-client-c2
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/e7r2
retention_rule: Retain both the invalid first run and corrected repeat; delete nothing without explicit user authorization.
observed:
  - The corrected threading.Barrier(9) formed. All eight distinct authenticated connections were accepted within 0.011 s and pending_rpc_peak was exactly 8.
  - queue_depth_peak was 5 and plastic-cup-yolo11n-seg-v1 model_active_peak was exactly 2; executor indices 0 and 1 both started real requests.
  - All eight replies were QUALIFIED with one candidate each. Client round trips ranged from 0.193664 s to 0.415059 s.
  - logical_inference_count was 8 with exact keys idem-01 through idem-08, replay_count was 0, transport_errors was empty, and no client reported TRUNCATED_FRAME.
  - All client threads and the authority thread terminated. SIGINT triggered Broker finally cleanup and its bounded summary before the wrapper reported the expected container exit 130 as return code 1; both Unix sockets were absent afterward, and exact labeled-container and GPU-compute probes were empty.
  - The committed image identity remained sha256:11e9a5ec0a7dedae8e0794d97462e422e78e68157ec94c75f8294b8a2025a7b1 with source SHA256 148f22e6e1ba6aaf7b99d0fe97d42d141cacd77f8f1928dda8233f0459006006. Input shape was 480x640x3 and all eight immutable NPY inputs had SHA256 2b23b7df49c28c5178896675a2e30e83f903f6cef20879990a1864509c4709fe.
conclusion: VALID; the production Broker demonstrates eight simultaneous authenticated RPCs, a nontrivial queue, exactly C2 YOLO execution, eight successful replies, at-most-once logical inference, zero transport truncation, and exact cleanup.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp007r2-eight-client-c2/report.json; SHA256 e1d201c2be062566bacf077cc585b8d2127d948feca92c05e437d905df0b69fc
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp007r2-eight-client-c2/broker.log; SHA256 18841cd941b003571bcc263db1781b8c1f4c663ed5786b48fd5a1893742a219c
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp007r2-eight-client-c2/run-admission.json; SHA256 e8dbc37b3ab63a52f091bf96d27e118f2555d5700f6be103cfd97ac09e6df558
decision: KEEP_AND_PROCEED_TO_EXP-008
```

## CP-011 — Package, image and production C2 admission

```yaml
checkpoint_id: CP-011
last_valid_experiment: EXP-007R2
current_hypothesis: A fixed no-fallback W8 run on the admitted C2 Broker will retain 20/20 correctness, eliminate TRUNCATED_FRAME, and reduce READY-to-POSE_ACCEPTED p95 below 5 seconds.
working_tree_status: committed executable source at 3677e9d97f1367f861496817cee5edeb4349871f; task ledger plus preserved pre-existing src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT remain modified/untracked.
confirmed_conclusions:
  - The fresh so101_demo_py overlay build passed in 2 seconds and installed parallel_ipc.py is byte-identical to source SHA256 3dbf8b07d83bc69965789a8fbbd4161811f65c0bc56163de09bc542e1fb86916.
  - The complete ordinary package collection reached 3034 tests; 3033 passed and the sole failure is the task-external uncommitted transient-/proc-retry test in the preserved user file. The committed Broker-authority test-double correction passed independently.
  - Rebuilt immutable image sha256:11e9a5ec0a7dedae8e0794d97462e422e78e68157ec94c75f8294b8a2025a7b1 binds source SHA256 148f22e6e1ba6aaf7b99d0fe97d42d141cacd77f8f1928dda8233f0459006006; frozen YOLO and Grounded-SAM CUDA smokes both returned QUALIFIED and cleaned exactly.
  - EXP-007R2 satisfies every production C2 microbenchmark criterion. EXP-007 is retained INVALID because its harness cached the wrong request identity and submitted no model work.
open_risks:
  - The literal full ordinary package gate cannot be marked all-green while the preserved, task-external uncommitted test expects an unrelated /proc retry behavior absent from committed source; this dispatch does not modify or include that user file.
  - Fixed-W8 physical correctness, latency, visual agreement and normal fallback-enabled regression remain unverified on the new image.
next_command: Pre-register EXP-008 fixed W8 C2, run clean-stack preflight, and execute the existing supervised adaptive batch wrapper once with fallback disabled.
retained_runs:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp007-eight-client-c2 as INVALID harness evidence
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp007r2-eight-client-c2 as VALID
  - image-build, image-smoke, reports, and all scratch evidence under the registered root
archived_runs: []
deletion_candidates:
  - scratch/t15pkg1, scratch/t15p2, scratch/t15p3 and scratch/t15d4 are invalid environment/hang diagnostics
  - scratch/t15p4 is the 3033/3034 full gate; scratch/t15b1 and scratch/t15g22 are valid build/focused gates
  - image-build/source and image-build/source.tar are clean committed-source build context candidates after readback
  - none deleted; explicit user authorization is required
```

## EXP-008 — Fixed-W8 no-fallback C2 execute regression

```yaml
experiment_id: EXP-008
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-14T22:57:58+08:00
  - status: RUNNING
    at: 2026-09-14T23:04:02+08:00
  - status: INVALID
    at: 2026-09-14T23:05:09+08:00
prior_experiment: EXP-007R2
hypothesis: The admitted C2 production Broker will preserve all twenty fixed-W8 physical outcomes, eliminate the accept-idle TRUNCATED_FRAME defect, and reduce READY-to-POSE_ACCEPTED p95 below the separate 5 second SLO.
single_variable: Replace the EXP-006 serialized/accept-eroded Broker with committed post-fix source and C2 YOLO execution; preserve fixed W8, no fallback, YOLO-only successful path, catalog order, initial state contract, model bytes, geometry, motion policy, configured hard timeouts, and measurement instrumentation.
lifecycle: ISOLATED_STACK
preconditions:
  - EXP-007R2 is VALID and immutable image sha256:11e9a5ec0a7dedae8e0794d97462e422e78e68157ec94c75f8294b8a2025a7b1 is source-qualified.
  - Runtime root /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/w8c2 and EXP-008 output paths are absent before launch.
  - Domains 215 through 222, task-owned processes, Docker containers and GPU compute applications are empty immediately before execution.
  - The task is headless EGL MuJoCo; fresh sealed initial/terminal RGB images plus numeric physical state are the applicable visual evidence, not a fabricated GUI-window capture.
method:
  - Use scripts/run_so101_adaptive_batch.zsh with adaptive worker_count=8, yolo_executor_count=2, the same twenty-point catalog, execute mode, and the EXP-006 measurement-only sitecustomize probe that freezes fallback_worker_counts to empty.
  - Preserve complete stdout/stderr, append-only journal, manifests, per-point sealed evidence, host/GPU samples, event timelines, aggregate result, exit code and post-cleanup probes.
success_criteria:
  - Exactly level W8 runs, all 20 points are PASSED, command exits zero, and no infrastructure retry or fallback generation occurs.
  - All accepted perception results are plastic-cup-yolo11n-seg-v1; Grounded-SAM invocation count is zero and fallback is not injected.
  - TRUNCATED_FRAME count is zero, Broker cleanup is complete, and Domains 215 through 222, owned processes, containers, sockets and GPU compute applications are empty afterward.
  - Every point passes initial gate, POSE_ACCEPTED, MoveIt plan/execute, controller/joint/TF, MuJoCo cup/support/contact, empty final attachment, sealed-hash, and fresh initial/terminal RGB checks.
  - READY-to-POSE_ACCEPTED p95 is less than 5 seconds; report median, p95, max and every strict over-5-second point. Separately report get_one-start-to-POSE_ACCEPTED and retain the configured 240-second timeout distinction.
failure_criteria:
  - Correctness below 20/20, any transport truncation, unexpected fallback/model, physical/evidence mismatch, incomplete cleanup, or READY-to-POSE_ACCEPTED p95 at least 5 seconds is a valid functional or performance failure.
invalid_criteria:
  - Provenance/config/catalog drift, conflicting stack, overwritten destination, missing timing/evidence layer, non-comparable clock, or cleanup ambiguity makes the run INVALID.
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008-w8-c2
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/w8c2
retention_rule: Retain all runtime, visual, numeric, timeline, resource, log, manifest and cleanup evidence; delete nothing without explicit user authorization.
observed:
  - live-01 exited 1 at preflight with PROVENANCE_SOURCE_DIRTY before a runtime root could be accepted; it is INVALID and is retained outside the correctness denominator.
  - live-02 exited 1 at preflight with PROVENANCE_CONSOLE_CONTENT before a runtime root could be accepted; it is INVALID and is retained outside the correctness denominator.
  - live-03 registered eight Workers but granted zero leases; its aggregate retained all twenty points as UNRUN with zero attempts.
  - The batch wrapper and all Worker process trees disappeared without a batch exit-code file while the detached Broker container survived.
  - At 2026-09-14T23:05:08.144930+08:00 systemd-oomd killed tmux-spawn-67d5b319-bdb4-4cac-999e-4bbf3eaa1049.scope after the user slice exceeded its 50 percent pressure threshold for more than 20 seconds. The victim used 16.2 GiB, reported memory PSI avg10 74.35 percent, and systemd recorded 120 killed processes.
  - The final retained external sampler row had 107 task processes, 8584577024 task RSS bytes, memory PSI some/full avg10 88.63/85.79 percent, IO PSI some/full avg10 87.27/83.84 percent, and a repeated nvidia-smi timeout.
  - Independent recovery read-back found exact labeled-container count zero, matching owned-process count zero, AF_UNIX socket count zero, GPU compute rows zero, and ROS Domains 0 and 215 through 222 empty. The removed container and socket nodes are not recreated; all regular evidence remains retained.
inferred:
  - The controller-spawner lock warnings occurred during the same pressure interval but are symptoms, not the confirmed cause of task loss.
conclusion: INVALID; the run never executed a point and was externally terminated by the confirmed systemd-oomd scope kill, so it is neither a product failure nor a performance sample.
decision: REPEAT_FROM_NEW_SCOPE_AND_ROOT
```

## CP-012 — EXP-008 OOM recovery and isolated-runner rerun boundary

```yaml
checkpoint_id: CP-012
last_valid_experiment: EXP-007R2
current_hypothesis: A fresh fixed-W8 C2 no-fallback run in a separate runner scope can form the READY barrier and complete without placing this Codex observer in the oomd victim scope; otherwise W6 is the approved lightweight retry.
working_tree_status: committed implementation at 3677e9d97f1367f861496817cee5edeb4349871f; task-owned ledger plus preserved pre-existing src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT remain dirty.
owned_processes: NONE from EXP-008; exact labeled-container, owned-process, AF_UNIX socket, GPU-compute and ROS-domain read-backs are empty.
preserved_processes: tmux sessions codex and codex-task-so101-adaptive-worker-pool-recovery plus unrelated user processes and stopped containers remain untouched.
confirmed_conclusions:
  - EXP-008 live-01 and live-02 are INVALID preflight-only attempts and live-03 is INVALID due to the confirmed systemd-oomd scope kill before the first lease.
  - EXP-007R2 remains the last valid experiment and qualifies W8 connections with C2 production inference.
  - The current checkout is the required linked worktree on codex/parallel-adaptive-worker-pool at 3677e9d97f1367f861496817cee5edeb4349871f with submodule c16b5a5fe880b6e1857f56486dab4ae726576969 unchanged.
disproven_routes:
  - Treating live-03 as a normal Codex exit, product failure, point failure, or controller-lock root cause is contradicted by the host journal and zero-lease aggregate.
  - Reusing the w8c2 runtime root or exp008-w8-c2 output paths is prohibited because those paths are retained evidence.
open_risks:
  - A fixed W8 stack may still cross the user-slice pressure threshold even when isolated into its own runner scope.
  - Another unrelated Codex task is present but currently owns no SO-101 stack, Docker container, GPU compute process, or ROS node; it must remain untouched.
next_command: Launch EXP-008R2 once at fixed W8/C2 from a fresh evidence subdirectory and runtime root inside a uniquely named runner tmux/systemd user scope while this Codex task monitors externally.
retained_runs:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008-w8-c2 as INVALID with live-01, live-02 and live-03 retained
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/w8c2 as INVALID runtime evidence
  - all earlier evidence under /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01
archived_runs: []
deletion_candidates:
  - all previously recorded candidates remain retained; none deleted
```

## EXP-008R2 — Fixed-W8 no-fallback C2 execute rerun in isolated runner scope

```yaml
experiment_id: EXP-008R2
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-14T23:19:30+08:00
  - status: RUNNING
    at: 2026-09-14T23:28:38+08:00
  - status: INVALID
    at: 2026-09-14T23:28:39+08:00
prior_experiment: EXP-008
hypothesis: The admitted C2 production Broker can complete the unchanged fixed-W8 twenty-point qualification when the batch runs in a dedicated runner scope and is observed by an external bounded monitor.
prediction: W8 forms its READY barrier, dynamically leases all twenty points across available Workers, completes 20/20 with zero TRUNCATED_FRAME and complete physical/evidence gates, and leaves exact cleanup; if the scope is killed or cannot safely reach readiness, the run is INVALID and qualification retries at W6 from another new root.
single_variable: Isolate the otherwise unchanged fixed-W8/C2/no-fallback qualification in a separate uniquely named runner tmux/systemd user scope with an external bounded resource monitor; source, image, models, catalog, geometry, motion policy, deadlines and acceptance gates remain frozen.
lifecycle: ISOLATED_STACK
preconditions:
  - Source commit is 3677e9d97f1367f861496817cee5edeb4349871f and immutable Broker image is sha256:11e9a5ec0a7dedae8e0794d97462e422e78e68157ec94c75f8294b8a2025a7b1.
  - New evidence subdirectory, runtime root, batch identity and runner session/scope do not exist before launch.
  - Domains 215 through 222, matching task-owned processes, matching containers, AF_UNIX sockets and GPU compute applications are empty immediately before launch.
  - Host memory/IO PSI, task RSS/process count, Docker/GPU state and runner exit state are captured by the external observer.
success_criteria:
  - Exactly W8 runs, all 20 points are PASSED, command exits zero, no infrastructure retry or fallback generation occurs, and every required correctness/visual layer is complete.
  - All accepted perception results are plastic-cup-yolo11n-seg-v1, Grounded-SAM invocation count is zero, TRUNCATED_FRAME count is zero, and actual YOLO concurrency is reported.
  - READY-to-POSE_ACCEPTED median/p95/max and strict-over-5-second points are reported separately from get_one-start timing and the configured 240-second hard timeout.
  - Exact owned cleanup is proven after read-back.
failure_criteria:
  - A fully valid run with correctness below 20/20, transport truncation, model/fallback drift, physical/evidence mismatch, incomplete cleanup, or p95 at least 5 seconds is a functional or performance failure.
invalid_criteria:
  - Failure to form a READY barrier, systemd-oomd scope kill, provenance/config/catalog drift, conflicting stack, missing timing/evidence, or cleanup ambiguity makes the W8 run INVALID and triggers a fresh W6 retry.
provenance:
  source_commit: 3677e9d97f1367f861496817cee5edeb4349871f
  install_overlay: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008-w8-c2/candidate-src/install
  runtime_executable: /usr/bin/python3 plus immutable Broker image sha256:11e9a5ec0a7dedae8e0794d97462e422e78e68157ec94c75f8294b8a2025a7b1
  ros_domain_id: [215, 216, 217, 218, 219, 220, 221, 222]
  gz_partition: not_applicable
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r2-w8-c2
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/w8c2r2
corrections:
  - at: 2026-09-14T23:25:35+08:00
    reason: The production wrapper requires a 1-5 character batch ID and derives the runtime-root leaf from that ID; the six-character illustrative leaf w8c2r2 cannot pass the unchanged wrapper contract.
    correction: Use fresh batch ID e8r2a and runtime root /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/e8r2a. This is an identity-only correction; fixed W8, C2, no fallback, models, catalog, geometry, timeouts and acceptance gates remain frozen.
commands:
  - command: systemd-run --user --unit=so101-exp008r2-monitor.service --collect /tmp/so101-exp008r2-monitor.zsh
    exit_code: 0
  - command: systemd-run --user --unit=so101-exp008r2-runner.service --collect /tmp/so101-exp008r2-holder.zsh
    exit_code: 0
  - command: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008-w8-c2/candidate-src/scripts/run_so101_adaptive_batch.zsh --adaptive-workers --points /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008-w8-c2/candidate-src/src/so101_demo_py/config/mujoco/moveit_expert_validation_points_v1.yaml --config /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008-w8-c2/candidate-src/src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml --adaptive-config /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008-w8-c2/candidate-src/src/so101_demo_py/config/mujoco/parallel_adaptive_workers_v1.yaml --batch-id e8r2a --evidence-root /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01 --worker-count 8 --initial-points-per-worker 3 --worker-start-timeout-s 120 --max-infra-attempts-per-point 5 --yolo-executor-count 2 --broker-image so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1 --yolo-weights /data/work/so101-evidence/act-head-wrist-moveit-baseline/run-1Mv3UyHW/optimization/3c35b60f-2211-4e2b-aca4-181604915188/models/yolo/best.pt --yolo-weights-sha256 f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781 --grounded-root /data/work/so101-models/grounded-sam-v2-scipy-lock --grounded-manifest-sha256 0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775 --run-mode execute
    exit_code: 127
observed:
  - The first orchestration command stopped before systemd-run because of an extraneous shell token; read-back proved no unit, tmux server, runtime root, container or batch process existed, so it was retained as preflight harness evidence only.
  - The sealed repeat created monitor invocation 45cb5f220fa74e21aa6648eb27799cae and runner invocation 685520b35456478eb87c93429e831686. The tmux session started, but the wrapper immediately reported `command not found: so101_parallel_batch` and `command not found: so101_parallel_batch_cleanup` because sourcing the isolated overlay did not add its package libexec directory to PATH.
  - Batch exit code was 127; runtime root /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/e8r2a never existed, no container or ROS stack started, and no point was leased or executed.
  - Exact-command serialization incorrectly quoted the whole argv as one aggregate string; this affects only the evidence rendering, not the argv actually passed by the shell array.
conclusion: INVALID preflight harness attempt; it supplies no W8 product correctness or performance sample and does not trigger the W6 policy.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r2-w8-c2/run.log
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r2-w8-c2/external-monitor.jsonl
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r2-w8-c2/external-monitor-final.txt
decision: REPEAT_W8_WITH_CORRECT_RUNNER_PATH
next_experiment: EXP-008R3-W8
```

## CP-013 — EXP-008R2 preflight harness invalidation

```yaml
checkpoint_id: CP-013
last_valid_experiment: EXP-007R2
current_hypothesis: The unchanged fixed-W8 C2 no-fallback configuration remains untested; adding the immutable overlay package libexec directory to the isolated runner PATH will exercise the intended production command.
working_tree_status: committed implementation at 3677e9d97f1367f861496817cee5edeb4349871f; task-owned ledger plus preserved pre-existing src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT remain dirty.
owned_processes: NONE from EXP-008R2; runner tmux ended and its runtime root was never created.
preserved_processes: tmux sessions codex and codex-task-so101-adaptive-worker-pool-recovery plus unrelated processes remain untouched.
confirmed_conclusions:
  - EXP-008R2 is INVALID preflight-only evidence because the wrapper could not resolve its two console scripts; it contains no point attempt and no W8 behavior sample.
  - The dedicated monitor observed the runner unit enter and leave its own cgroup while host PSI stayed low and Docker/GPU evidence remained empty.
disproven_routes:
  - Sourcing candidate-src/install/setup.zsh alone does not make so101_parallel_batch or so101_parallel_batch_cleanup executable by direct name in this noninteractive systemd/tmux runner.
open_risks:
  - Fixed W8 may still be killed by systemd-oomd after corrected preflight reaches stack startup.
next_command: Pre-register and launch EXP-008R3-W8 from entirely new experiment, runtime, batch, tmux and systemd identities after proving both console scripts, exact argv serialization and clean host ownership.
retained_runs:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r2-w8-c2 as INVALID preflight harness evidence
archived_runs: []
deletion_candidates:
  - EXP-008R2 copied runner/monitor scripts and preflight logs; none deleted and explicit authorization is required.
```

## EXP-008R3-W8 — Corrected isolated-runner fixed-W8 no-fallback C2 qualification

```yaml
experiment_id: EXP-008R3-W8
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-14T23:31:00+08:00
  - status: RUNNING
    at: 2026-09-14T23:32:19+08:00
  - status: INVALID
    at: 2026-09-14T23:32:21+08:00
prior_experiment: EXP-008R2
hypothesis: The admitted C2 Broker can complete the frozen fixed-W8 twenty-point qualification when the fresh isolated runner resolves the immutable overlay console scripts and retains the external monitor.
prediction: Both production console scripts resolve before launch, the W8 READY barrier forms, all twenty points are dynamically leased and pass, TRUNCATED_FRAME is zero, and cleanup is exact; inability to form READY or an oomd kill makes this run INVALID and triggers fresh W6.
single_variable: Correct the runner PATH and exact-command evidence serialization; fixed W8, C2, no fallback, source, image, models, catalog, geometry, motion policy, deadlines and acceptance gates remain frozen.
lifecycle: ISOLATED_STACK
preconditions:
  - Source commit, overlay, image and model hashes equal EXP-008R2; both production console scripts resolve from the immutable candidate overlay.
  - Fresh experiment root, runtime root, batch identity, tmux server/session and systemd units are absent; Domains 0 and 215-222, task processes, matching containers, sockets and GPU compute rows are empty.
success_criteria:
  - Exactly W8 runs, all 20 points pass, exit code is zero, no fallback generation occurs, YOLO is the only accepted model, TRUNCATED_FRAME is zero, every correctness/visual layer passes, timings are complete and cleanup is exact.
failure_criteria:
  - A valid full run has fewer than 20 passed points, any transport/model/evidence/correctness mismatch, incomplete cleanup, or READY-to-POSE_ACCEPTED p95 at least 5 seconds.
invalid_criteria:
  - Failure to form READY, oomd kill, provenance/config/catalog drift, preflight failure, conflicting stack, missing evidence or cleanup ambiguity.
provenance:
  source_commit: 3677e9d97f1367f861496817cee5edeb4349871f
  install_overlay: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008-w8-c2/candidate-src/install
  runtime_executable: immutable overlay console scripts plus Broker image sha256:11e9a5ec0a7dedae8e0794d97462e422e78e68157ec94c75f8294b8a2025a7b1
  ros_domain_id: [215, 216, 217, 218, 219, 220, 221, 222]
  gz_partition: not_applicable
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r3-w8-c2
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/e8r3w
commands:
  - command: systemd-run --user --unit=so101-exp008r3-w8-monitor.service --collect /tmp/so101-exp008r2-monitor.zsh
    exit_code: 0
  - command: systemd-run --user --unit=so101-exp008r3-w8-runner.service --collect /tmp/so101-exp008r2-holder.zsh
    exit_code: 0
  - command: exact production command is retained in exp008r3-w8-c2/exact-command.txt with batch e8r3w, fixed worker-count 8, C2 and no fallback.
    exit_code: 1
observed:
  - Clean host preflight proved both overlay console scripts, immutable source/image/model identities, empty task processes/containers/GPU/ROS Domains, fresh identities and low PSI before launch.
  - The command reached AdaptiveBatchRunner and wrote BATCH_MANIFEST plus POOL_STARTING, but ProductionBatchComposition failed before creating p/g01w08 or any Worker/container; elapsed time was 0.045517 s, all twenty points were startup-interrupted, no point was leased or executed, and aggregate status was INFRA_FAILED.
  - Cleanup then emitted POOL_ROOT because the active POOL_STARTING journal had no pool directory; this was a secondary symptom. Exact post-readback found zero owned processes, containers, sockets, persistent claims, GPU rows and ROS nodes on Domains 0 and 215-222.
  - The retained working EXP-008 launcher sourced ROS, the worktree overlay, then the immutable candidate overlay and explicitly added candidate site-packages/build paths; EXP-008R3 omitted the worktree overlay and those Python paths. This environment drift is the first bad boundary.
conclusion: INVALID startup contamination before READY; it is not a point or W8 product failure, but the approved single fresh W8 retry is exhausted and the lightweight policy now selects fresh W6.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r3-w8-c2/preflight.txt
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r3-w8-c2/cleanup-readback.txt SHA256 3b94907a7bd9fb8acf4345a0192baf923c6568c7d4b8a5f6c85272739c4da506
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/e8r3w/aggregate_results.json SHA256 e08a7f87c84784295057c7e4716222a93d68031aa73cd481500c4e694d8263a8
decision: RETAIN_INVALID_AND_RETRY_W6
next_experiment: EXP-008R4-W6
```

## CP-014 — Fixed-W8 retry exhausted; fresh W6 boundary

```yaml
checkpoint_id: CP-014
last_valid_experiment: EXP-007R2
current_hypothesis: A fresh fixed-W6 C2 no-fallback run using the original ROS/worktree/candidate overlay ordering can remain executable and dynamically complete the same twenty-point qualification.
working_tree_status: implementation remains 3677e9d97f1367f861496817cee5edeb4349871f; only the task ledger plus preserved src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT are dirty.
owned_processes: NONE; EXP-008R3 exact process/container/socket/claim/GPU/ROS read-back is empty.
preserved_processes: tmux sessions codex and codex-task-so101-adaptive-worker-pool-recovery plus unrelated user state remain untouched.
confirmed_conclusions:
  - The W8 rerun did not form READY and is INVALID startup contamination, so it is excluded from point correctness and performance denominators.
  - The fixed-W8 retry allowance is exhausted; W6 is now required by the approved OOM recovery policy, with no W1 fallback unless W6 independently proves unable.
disproven_routes:
  - Candidate-only environment setup is not comparable to the retained working launcher and cannot qualify the runtime.
open_risks:
  - W6 may still cross host pressure limits or expose another startup issue after the full overlay ordering is restored.
next_command: Pre-register EXP-008R4-W6, validate the W6-only no-fallback timing shim and full two-overlay environment, then launch in fresh tmux/systemd identities with an external bounded monitor.
retained_runs:
  - exp008-w8-c2, exp008r2-w8-c2 and exp008r3-w8-c2 plus runtime roots w8c2 and e8r3w remain retained.
archived_runs: []
deletion_candidates:
  - EXP-008R2 and EXP-008R3 orchestration scripts and preflight-only runtime evidence; none deleted.
```

## EXP-008R4-W6 — Fixed-W6 no-fallback C2 lightweight qualification

```yaml
experiment_id: EXP-008R4-W6
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-14T23:37:00+08:00
  - status: RUNNING
    at: 2026-09-14T23:39:26+08:00
  - status: INVALID
    at: 2026-09-14T23:39:28+08:00
prior_experiment: EXP-008R3-W8
hypothesis: W6 lowers stack pressure enough to complete the unchanged twenty-point fixed qualification with C2, no model fallback and exact correctness/cleanup evidence.
prediction: Six Workers form READY, dynamically lease all twenty points, complete 20/20, use YOLO only with zero TRUNCATED_FRAME, and clean exactly without an oomd kill.
single_variable: Reduce fixed worker count from W8 to W6 under the approved lightweight recovery; restore the retained launcher's ROS/worktree/candidate overlay order and explicit candidate Python paths. C2, no fallback, source, image, models, catalog, geometry, motion policy, deadlines and gates remain frozen.
lifecycle: ISOLATED_STACK
preconditions:
  - Fresh experiment/runtime/batch/tmux/systemd identities; clean Domains 0 and 215-220, task ownership, containers, sockets and GPU state.
  - Measurement-only timing shim is copied from EXP-006, changes only the no-fallback expected worker count from 8 to 6, and passes a focused contract smoke before launch.
success_criteria:
  - Exactly W6 runs, all 20 points pass, exit zero, no infrastructure generation fallback, YOLO is the only accepted model, Grounded-SAM count and TRUNCATED_FRAME are zero, all correctness/visual/timing evidence is complete, and cleanup is exact.
failure_criteria:
  - A valid run has fewer than 20 passed points, any transport/model/physical/evidence mismatch, incomplete cleanup, or unsafe Broker health.
invalid_criteria:
  - Failure to form READY, oomd kill, provenance/config/catalog drift, conflicting stack, missing evidence or cleanup ambiguity.
provenance:
  source_commit: 3677e9d97f1367f861496817cee5edeb4349871f
  install_overlay: /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool/install followed by immutable candidate overlay /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008-w8-c2/candidate-src/install
  runtime_executable: immutable candidate console plus Broker image sha256:11e9a5ec0a7dedae8e0794d97462e422e78e68157ec94c75f8294b8a2025a7b1
  ros_domain_id: [215, 216, 217, 218, 219, 220]
  gz_partition: not_applicable
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r4-w6-c2
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/e8r4w
commands:
  - command: Exact fixed-W6/C2/no-fallback production argv is retained in exp008r4-w6-c2/exact-command.txt under runner unit so101-exp008r4-w6-runner.service and tmux server/session so101-exp008r4-w6/exp008r4-w6-runner.
    exit_code: 1
observed:
  - The evidence-only W6 shim passed a focused RED/GREEN: the unchanged EXP-006 probe rejected W6, while the one-line worker-count adaptation produced worker_count 6 with fallback_worker_counts empty.
  - The corrected two-overlay launch reached BATCH_MANIFEST and POOL_STARTING but stopped in 0.032688 s before p/g01w06, Worker, Broker container, READY or any point execution; cleanup's POOL_ROOT was secondary.
  - A constructor-only diagnostic exposed the swallowed first exception as ResourceAllocationError ROS_DOMAIN_UNCLEAN: 215. Claims 215-222 still contained ACTIVE state for invalid OOM batch w8c2-g01-w08 even though its processes, container, sockets, GPU rows and ROS graph were empty.
  - The first production cleanup attempt correctly failed ROS_DOMAIN_ACTIVE because prior read-only `ros2 node list` probes had started exact daemon PIDs 713736 and 713845-714217. After task-owned `ros2 daemon stop` calls, the production cleanup succeeded and transitioned exactly claims 215-222 to RELEASED with cleanup_verified true; cleanup receipt SHA256 ec63115e31d29a125707e5fd9ef8a7c3681c49cf180d1964cf89eb2d7b1f97c6.
  - AF_UNIX 106/107/108-byte bind A/B passed at 106 and 107 and failed only at 108, disproving socket length as this startup cause. Restoring the worktree overlay also did not change the failure, disproving the overlay omission as the root cause.
conclusion: INVALID startup contamination caused by stale persistent domain claims from EXP-008; no point ran and W6 capacity remains untested. Because the contaminant is now exactly reconciled, repeat W6 from fresh identities rather than descend to W1.
evidence:
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r4-w6-c2/constructor-diagnostic-r2.log
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r4-w6-c2/stale-claim-cleanup-r2.log SHA256 74febf19874dea37bb5f3e67556a86f8a1d20461009f55777c2a986d70a99356
  - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/w8c2/cleanup-receipt.json SHA256 ec63115e31d29a125707e5fd9ef8a7c3681c49cf180d1964cf89eb2d7b1f97c6
decision: REPEAT_W6_AFTER_EXACT_CLAIM_RECOVERY
next_experiment: EXP-008R5-W6
```

## CP-015 — Stale persistent claim root cause removed

```yaml
checkpoint_id: CP-015
last_valid_experiment: EXP-007R2
current_hypothesis: With old w8c2 claims now RELEASED and task-created ROS daemons stopped, a fresh fixed-W6 C2/no-fallback run can enter pool construction and form READY.
working_tree_status: implementation remains 3677e9d97f1367f861496817cee5edeb4349871f; task ledger plus preserved test_parallel_batch_resources.py and MUJOCO_LOG.TXT remain dirty.
owned_processes: NONE; exact invalid-run process/container/socket/GPU read-backs are empty and old claims are RELEASED.
preserved_processes: user tmux sessions and unrelated state remain untouched.
confirmed_conclusions:
  - The shared startup root cause was stale persistent claims from the OOM run, not W8/W6 load, overlay order or AF_UNIX length.
  - Production cleanup, rather than hand edits, reconciled all eight exact claims and wrote a verified cleanup receipt.
disproven_routes:
  - W1 is not warranted because W6 has not yet executed after removal of the invariant cleanup contaminant.
open_risks:
  - W6 runtime pressure and physical/timing correctness remain unmeasured.
next_command: Launch fresh EXP-008R5-W6 using four-character batch 84w6, new runtime/output/tmux/systemd identities, full overlays, fixed C2/no-fallback shim and external monitor.
retained_runs:
  - All invalid W8/W6 attempts, both constructor diagnostics and old runtime cleanup evidence remain retained.
archived_runs: []
deletion_candidates:
  - diagnostic runtime roots d84w6 and d84w7 plus invalid startup roots e8r3w and e8r4w; none deleted.
```

## EXP-008R5-W6 — Post-cleanup fixed-W6 no-fallback C2 qualification

```yaml
experiment_id: EXP-008R5-W6
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-14T23:47:00+08:00
  - status: RUNNING
    at: 2026-09-14T23:48:25+08:00
  - status: INVALID
    at: 2026-09-15T00:01:21+08:00
prior_experiment: EXP-008R4-W6
hypothesis: With stale domain claims reconciled, six Workers will form READY and dynamically complete the frozen twenty-point qualification under C2 and no fallback without unsafe host pressure.
prediction: W6 reaches POOL_RUNNING, executes 20/20, uses only YOLO, has zero TRUNCATED_FRAME and exact cleanup; the external monitor remains outside the runner cgroup.
single_variable: Remove the confirmed stale-claim contamination; preserve W6, C2, no fallback, full overlay order, models, catalog, geometry, motion policy, timeouts and gates from EXP-008R4-W6.
lifecycle: ISOLATED_STACK
preconditions:
  - Claims 215-222 are RELEASED with cleanup_verified true; exact task processes, containers, sockets, GPU rows and ROS daemons/nodes are absent.
  - Fresh experiment root exp008r5-w6-c2, runtime /r/84w6, batch 84w6, tmux server/session so101-exp008r5-w6/exp008r5-w6-runner and new systemd units are absent.
success_criteria:
  - Exactly W6 runs and all 20 points pass with exit zero, no infrastructure generation fallback, only YOLO acceptances, zero Grounded-SAM and TRUNCATED_FRAME, full correctness/visual/timing evidence and exact cleanup.
failure_criteria:
  - A valid run has fewer than 20 passes or any transport/model/physical/evidence/cleanup mismatch.
invalid_criteria:
  - READY cannot form, oomd kills the scope, provenance/config/catalog drift, conflicting stack, missing evidence or cleanup ambiguity.
provenance:
  source_commit: 3677e9d97f1367f861496817cee5edeb4349871f
  install_overlay: worktree install followed by immutable candidate install
  runtime_executable: immutable candidate console plus image sha256:11e9a5ec0a7dedae8e0794d97462e422e78e68157ec94c75f8294b8a2025a7b1
  ros_domain_id: [215, 216, 217, 218, 219, 220]
  gz_partition: not_applicable
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r5-w6-c2
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/84w6
commands:
  - command: systemd-run --user --unit=so101-exp008r5-w6-monitor.service --collect /tmp/so101-exp008r2-monitor.zsh
    exit_code: 0
  - command: systemd-run --user --unit=so101-exp008r5-w6-runner.service --collect /tmp/so101-exp008r2-holder.zsh
    exit_code: 0
  - command: Exact production argv is retained in exp008r5-w6-c2/exact-command.txt; it selects batch 84w6, fixed W6, C2, no fallback and execute mode.
    exit_code: 1
observed:
  - Runner holder unit invocation b51e56c7328c40d7bf97850acd21d2ef launched unique tmux server/session so101-exp008r5-w6/exp008r5-w6-runner. The batch pane and descendants are in dedicated scope tmux-spawn-17746413-0e0b-4ea0-ad74-ec725869db3e.scope, outside this Codex cgroup.
  - External monitor unit invocation d59986d120f74b62965a47ca5f6606b5 has PID 738245 and independent cgroup so101-exp008r5-w6-monitor.service; it writes external-monitor.jsonl every five seconds.
  - All six Workers reached READY and W6 stayed executable without oomd; seven sealed points passed before a hard-coded 180 s execute_result deadline contradicted the frozen configured 240 s timeout.
  - Receipt verification then produced infrastructure INDETERMINATE results and first-failure convergence stopped the generation. No TRUNCATED_FRAME or model fallback was observed; exact cleanup released claims 215-220 and left no owned process, container, socket, GPU row or unit.
conclusion: INVALID runtime-harness contamination, not a W6 capacity or point failure. W1 remains unauthorized.
decision: FIX_TIMEOUT_AND_REPEAT_W6
next_experiment: EXP-008R6-W6
```

## CP-017 — Clean W6 unable at frozen 240 s execution boundary

```yaml
checkpoint_id: CP-017
confirmed_conclusions:
  - EXP-008R6-W6 exercised the corrected configured timeout and expired cup_test_forward_5cm at exactly 240.000 s; W6 is therefore unable under the approved handoff, authorizing W1.
  - Cleanup read-back is empty and claims 215-220 are RELEASED; source remains frozen at 167c74a941782e37ed1369ee10c42ac6b77088a9.
next_command: Launch a fresh fixed-W1/C2/no-fallback qualification from new output/runtime/batch/tmux/systemd identities.
```

## EXP-008R7-W1 — Fixed-W1 no-fallback C2 qualification

```yaml
experiment_id: EXP-008R7-W1
status: INVALID
status_history:
  - status: PLANNED
    at: 2026-09-15T00:19:30+08:00
  - status: RUNNING
    at: 2026-09-15T00:22:55+08:00
  - status: INVALID
    at: 2026-09-15T00:27:33+08:00
prior_experiment: EXP-008R6-W6
hypothesis: Serial W1 removes inter-worker simulation contention so every frozen point completes within 240 s while preserving C2/no-fallback qualification semantics.
success_criteria: Exactly W1, 20/20 PASSED, YOLO only, zero TRUNCATED_FRAME, complete correctness/visual/timing evidence, and exact cleanup.
evidence_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-15-w8-broker-concurrency/exp008r7-w1-c2
runtime_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/r/87w1
source_commit: 167c74a941782e37ed1369ee10c42ac6b77088a9
runner_identity: so101-exp008r7-w1-runner.service invocation ab1cde2a80b84a4c8baf1a444febd938; tmux so101-exp008r7-w1/exp008r7-w1-runner; batch scope tmux-spawn-65405a2b-b594-4d39-b850-f109d6358be3.scope.
monitor_identity: primary PID 797797 and supplemental PID 799740, both outside the runner scope.
observed: W1 formed READY. Its first ATTEMPT_STARTED was coordinator seq17 at monotonic 1222994.724863698 with deadline 1223234.724863698; LEASE_EXPIRED seq263 occurred at that exact 240.000 s boundary and BATCH_STOPPING seq264 followed. The top aggregate exited 1 after 278.05097205680795 s with 1 INDETERMINATE and 19 UNRUN. One YOLO request completed QUALIFIED, no accepted consumer pose existed, and no fallback, Grounded-SAM usage, logical replay/deadline error, TRUNCATED_FRAME or oomd event occurred.
visual: Original-resolution inspection covered the fresh task_start initial/terminal pair (640x480 RGB PNG): both are coherent and noncorrupt, but no placement occurred before expiry. See task-15-w8-broker-concurrency/visual-inspection-r6-r7-r2.txt.
cleanup: Production ownership-scoped cleanup released Domain 215; exact read-back found no owned process, container, socket, GPU row or tmux session and both runner/monitor units were inactive/dead with successful result. Receipt SHA256 ea1efe2f2fc401a9babd20ced1915016b298718e63feb042788e5cb0ec8a982e; read-back SHA256 3a4a3dda4882735efc6c2214f4edf6eabcd90a554de625a4683a18c43175ebf8.
conclusion: INVALID/unable under the approved recovery policy. W1 is the lowest permitted tier, so live fixed qualification stops without a valid 20/20 result.
decision: STOP_FIXED_QUALIFICATION_BLOCKED
```

## CP-018 — Lowest recovery tier unable; Task 10 blocked

```yaml
checkpoint_id: CP-018
last_valid_experiment: EXP-007R2
current_commit: 167c74a941782e37ed1369ee10c42ac6b77088a9
confirmed_conclusions:
  - Corrected W6 and W1 both remained memory-safe and formed READY, but each proved unable at the frozen exact 240.000 s lease boundary; neither result is a valid fixed qualification.
  - C4 is NOT_RUN because the prerequisite valid 20/20 W8/C2 result does not exist. The fallback-enabled normal adaptive regression is NOT_RUN/BLOCKED because fixed qualification did not complete.
  - EXP-008R6 produced 12 diagnostic PASSED, 4 INDETERMINATE and 4 UNRUN; EXP-008R7 produced 1 INDETERMINATE and 19 UNRUN. No startup/OOM contamination was counted as a point failure.
  - Every EXP-008R6/R7 fresh RGB artifact was inspected at original resolution, and ownership-scoped cleanup is exact with claims RELEASED. No evidence was deleted.
working_tree_status: Task-owned ledger is modified; preserved user src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT remain untouched and unstaged.
retained_runs:
  - All EXP-008 through EXP-008R7 output/runtime roots and Task 10 test/monitor/visual/cleanup evidence under /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01.
archived_runs: []
deletion_candidates:
  - Invalid preflight/diagnostic roots and pytest scratch trees, retained pending explicit deletion authorization.
next_command: Task 11 consumes task-10-report.md and must preserve the blocked conclusion; no further Task 10 live run is authorized.
```

## CP-019 — Task 11 final gate and blocked qualification handoff

```yaml
checkpoint_id: CP-019
last_valid_experiment: EXP-007R2
source_commit: 167c74a941782e37ed1369ee10c42ac6b77088a9
accepted_w8_overlay: /data/work/ws_moveit/.worktrees/parallel-adaptive-worker-pool/install
accepted_broker_image: so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1
accepted_broker_image_digest: sha256:11e9a5ec0a7dedae8e0794d97462e422e78e68157ec94c75f8294b8a2025a7b1
review_acceptance:
  - Task 10 independent review is accepted after its audit correction.
  - Historical stdout for the focused timeout RED and GREEN was not durably captured and is unavailable for independent verification; only the named scratch trees remain.
  - The adjacent runtime suite is independently retained at task-15-w8-broker-concurrency/task10-timeout-adjacent2.log and passed 40 tests.
package_gate:
  command: PYTHONNOUSERSITE=1 /usr/bin/python3 -m pytest -p no:cacheprovider -q src/so101_demo_py/test --junitxml="$scratch_root/so101-demo-py.xml"
  runtime_executable: /usr/bin/python3
  scratch_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/scratch/t11p2
  tempfile_root: /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/scratch/t11p2/tmp
  tempfile_verified: true
  collected: 3035
  passed: 3033
  skipped: 1
  failed: 1
  errors: 0
  warnings: 4
  pytest_elapsed_s: 60.55
  wall_elapsed_s: 61.66
  exit_code: 1
  sole_failure: src/so101_demo_py/test/test_parallel_batch_resources.py::test_transient_unclassified_proc_read_error_is_retried
  scope: src/so101_demo_py/test only; benchmark_test was not collected.
  evidence:
    - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/task-11-final-gate/task11-package-r3.log SHA256 164c709780f5d3fad2212e9543fee3c644abf2c039119603138498c0a2736776
    - /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/scratch/t11p2/so101-demo-py.xml SHA256 f8944d606aacac226897259ebac64b22882f49bcdd04348eb51ab52f170a8df3
  conclusion: NOT_ALL_GREEN because the preserved task-external dirty test fails against committed source; no task-owned source regression was observed in the definitive rerun.
invalid_gate_attempts:
  - task-11-package-20260915-0041 collected 3035 tests but produced 58 failures because its descriptive scratch path made generated AF_UNIX paths exceed the platform limit; retained and excluded as INVALID_ENV.
  - t11p1 used a valid short scratch and produced 3032 passed, 1 skipped, and 2 failed; the additional domain-claim concurrency race disappeared in t11p2, matching the same transient previously recorded by Task 9.
outcome_boundaries:
  ipc_defect: FIXED by the accepted accept-idle RED/GREEN implementation evidence and live TRUNCATED_FRAME=0 in EXP-007R2 and the diagnostic EXP-008R6/R7 runs.
  w8_correctness: BLOCKED; no valid 20/20 fixed-W8 run exists after the authorized recovery sequence.
  five_second_slo: BLOCKED; no valid fixed-W8 20/20 READY-to-POSE_ACCEPTED population exists. The diagnostic W6 p95 13.515607094 s is not a substitute.
  selected_yolo_concurrency: C2 from EXP-005 and qualified by EXP-007R2; C4 is NOT_RUN because its valid-W8 trigger was never met.
  adaptive_fallback: NOT_RUN/BLOCKED because the fixed-qualification prerequisite did not complete.
  fixed_run_boundary: EXP-008R6-W6 and EXP-008R7-W1 each reached READY but expired at the exact 240.000 s lease boundary; their point counts remain diagnostic only.
working_tree_status: The ledger is the only Task 11 staged candidate. Preserved user src/so101_demo_py/test/test_parallel_batch_resources.py and MUJOCO_LOG.TXT remain untouched and unstaged.
owned_processes: NONE from Task 11; the package gate started no live SO-101 stack.
retained_runs:
  - All EXP-008 through EXP-008R7 output/runtime roots, orchestration logs, monitors, images, aggregate objects, cleanup receipts/read-backs, Task 10 test scratch trees, and the adjacent 40-test log remain under /data/work/so101-evidence/parallel-adaptive-worker/20260914-a01.
  - Task 11 preflight, commands, stdout/stderr, elapsed files, exit files, JUnit, hashes, and all three scratch trees remain under the registered root.
archived_runs: []
deletion_candidates:
  - Invalid preflight and diagnostic orchestration roots, generated candidate clones/build trees, all Task 10 pytest scratch trees, and Task 11 scratch/task-11-package-20260915-0041, scratch/t11p1, and scratch/t11p2.
  - No candidate was deleted; explicit user authorization is required before deletion.
open_risks:
  - The required 20/20 fixed-W8 correctness result, fixed-W8 p95 decision, conditional C4 comparison, and normal fallback-enabled adaptive regression remain unavailable.
  - Historical timeout RED/GREEN ordering cannot be independently verified because stdout was not retained.
  - The literal ordinary package gate remains nonzero due only to the preserved user-owned dirty test.
next_command: NONE; Task 11 is finalized with blocked qualification boundaries. No push, merge, evidence deletion, or further live run is authorized.
```
